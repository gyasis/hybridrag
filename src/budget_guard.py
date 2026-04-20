#!/usr/bin/env python3
"""
Budget Guard Module
===================
Hard safety net against runaway embedding / LLM costs in HybridRAG.

Two independent guards:
1. Per-content-hash call counter — refuses to re-embed the same file hash
   more than N times (catches idempotence bugs, watcher restart loops).
2. Rolling 24-hour cost cap — halts the pipeline when estimated spend
   in the trailing 24h would exceed a configured USD threshold.

Every embed/LLM call is logged to SQLite for post-hoc audit.

Env overrides:
- HYBRIDRAG_MAX_EMBEDS_PER_HASH   default 3
- HYBRIDRAG_MAX_DAILY_COST_USD    default 5.0
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class BudgetExceededError(RuntimeError):
    """Raised when a budget guard refuses a call. Halts the caller."""


class BudgetGuard:
    # Default pricing per 1M tokens (OpenAI, April 2026).
    DEFAULT_COST_EMBED = 0.02       # text-embedding-3-small
    DEFAULT_COST_LLM_IN = 0.10      # gpt-4.1-nano input
    DEFAULT_COST_LLM_OUT = 0.40     # gpt-4.1-nano output

    def __init__(
        self,
        db_path: str,
        max_embeds_per_hash: int = 3,
        max_daily_cost_usd: float = 5.0,
        cost_per_million_embed: float = DEFAULT_COST_EMBED,
        cost_per_million_llm_in: float = DEFAULT_COST_LLM_IN,
        cost_per_million_llm_out: float = DEFAULT_COST_LLM_OUT,
    ) -> None:
        self.db_path = db_path
        self.max_embeds_per_hash = max_embeds_per_hash
        self.max_daily_cost_usd = max_daily_cost_usd
        self.cost_embed = cost_per_million_embed
        self.cost_llm_in = cost_per_million_llm_in
        self.cost_llm_out = cost_per_million_llm_out
        self._init_db()

    def _init_db(self) -> None:
        # WAL mode + NORMAL sync is the safe multi-process combo.
        # Without WAL, two processes reading+inserting race and could bypass
        # the 24h cost cap (see $5K incident 2026-04-14).
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_path TEXT,
                    file_hash TEXT,
                    token_count INTEGER,
                    cost_usd REAL,
                    call_type TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON calls(file_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON calls(timestamp)")

    def _estimate_cost(self, call_type: str, tokens: int) -> float:
        per_m = (tokens or 0) / 1_000_000.0
        if call_type == 'embed':
            return per_m * self.cost_embed
        if call_type == 'llm_in':
            return per_m * self.cost_llm_in
        if call_type == 'llm_out':
            return per_m * self.cost_llm_out
        return 0.0

    def check_and_log(
        self,
        file_path: str,
        file_hash: str,
        estimated_tokens: int,
        call_type: str = 'embed',
    ) -> None:
        """Validate a planned call. Raise BudgetExceededError to halt the pipeline.

        MUST be called BEFORE the paid API invocation, not after.

        Multi-process safe: BEGIN IMMEDIATE takes the SQLite write lock up front,
        so two concurrent Claude Code sessions cannot both see the same cap
        value and both exceed it.
        """
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM calls WHERE file_hash = ? AND call_type = ?",
                    (file_hash, call_type),
                )
                prior_count = cur.fetchone()[0]
                if prior_count >= self.max_embeds_per_hash:
                    conn.execute("ROLLBACK")
                    raise BudgetExceededError(
                        f"Hash-repeat guard: {call_type} for hash {file_hash[:12]}… already "
                        f"invoked {prior_count} times (cap={self.max_embeds_per_hash}). "
                        f"Refusing re-call for {file_path}."
                    )

                day_ago = (datetime.now() - timedelta(hours=24)).isoformat()
                cur = conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE timestamp >= ?",
                    (day_ago,),
                )
                rolling_cost = float(cur.fetchone()[0] or 0.0)
                projected = self._estimate_cost(call_type, estimated_tokens)

                if rolling_cost + projected > self.max_daily_cost_usd:
                    conn.execute("ROLLBACK")
                    raise BudgetExceededError(
                        f"24h cost cap: rolling ${rolling_cost:.4f} + projected ${projected:.4f} "
                        f"> cap ${self.max_daily_cost_usd:.2f}. Halting pipeline. File: {file_path}"
                    )

                conn.execute(
                    "INSERT INTO calls (file_path, file_hash, token_count, cost_usd, call_type) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (file_path, file_hash, estimated_tokens, projected, call_type),
                )
                conn.execute("COMMIT")

                logger.info(
                    "BudgetGuard: %s ok. hash_count=%d/%d, 24h_cost=$%.4f/$%.2f",
                    call_type,
                    prior_count + 1,
                    self.max_embeds_per_hash,
                    rolling_cost + projected,
                    self.max_daily_cost_usd,
                )
            except BudgetExceededError:
                raise
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def status(self) -> dict:
        """Snapshot for monitoring / CLI."""
        day_ago = (datetime.now() - timedelta(hours=24)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(cost_usd), 0) FROM calls WHERE timestamp >= ?",
                (day_ago,),
            )
            calls_24h, cost_24h = cur.fetchone()
            cur = conn.execute(
                "SELECT file_hash, COUNT(*) c FROM calls "
                "WHERE timestamp >= ? GROUP BY file_hash ORDER BY c DESC LIMIT 5",
                (day_ago,),
            )
            top_hashes = cur.fetchall()
        return {
            'calls_24h': int(calls_24h or 0),
            'cost_usd_24h': round(float(cost_24h or 0.0), 4),
            'daily_cap_usd': self.max_daily_cost_usd,
            'utilization_pct': round(
                100.0 * float(cost_24h or 0.0) / self.max_daily_cost_usd, 1
            ) if self.max_daily_cost_usd > 0 else 0.0,
            'top_repeated_hashes_24h': [
                {'hash': h[:12] + '…', 'count': c} for h, c in top_hashes
            ],
        }
