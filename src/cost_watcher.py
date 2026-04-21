#!/usr/bin/env python3
"""
Cost Watcher Module
===================
Observability layer for HybridRAG API spend. Pure logging + reporting —
NEVER enforces. Enforcement is `BudgetGuard`'s job; both classes share the
same SQLite `calls` table so one write serves both.

Every paid API call (ingest, enrichment, query, embed_query, llm_synth)
should route through either:
  - `BudgetGuard.check_and_log(..., database_name=..., operation=...)`
      for ENFORCED operations (ingest, enrichment).
  - `CostWatcher.record(...)`
      for OBSERVE-ONLY operations (query, embed_query, llm_synth).

Reports are always read-only SELECTs — safe to call from MCP tools or CLI
without any interference with the enforcement path.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Default pricing per 1M tokens (OpenAI, April 2026)
DEFAULT_COST_EMBED = 0.02       # text-embedding-3-small
DEFAULT_COST_LLM_IN = 0.10      # gpt-4.1-nano input
DEFAULT_COST_LLM_OUT = 0.40     # gpt-4.1-nano output

# Valid operation tags for analytics grouping
ALLOWED_OPERATIONS = {
    "ingest",        # bulk/realtime worker writes via ainsert/ainsert_fast
    "enrichment",    # enrichment_worker fills KG on existing chunks
    "query",         # user-initiated query (aggregated)
    "embed_query",   # LightRAG's query-side embedding of the user's question
    "llm_synth",     # LightRAG's query-side LLM synthesis of the answer
}

# Valid group_by columns for report()
ALLOWED_GROUP_COLUMNS = {
    "database_name",
    "operation",
    "call_type",
    "day",           # synthetic: date(timestamp)
    "hour",          # synthetic: strftime('%Y-%m-%d %H', timestamp)
}

_SINCE_PATTERN = re.compile(r"^(\d+)([hdwm])$")


def _parse_since(since: str) -> timedelta:
    """Parse '24h', '7d', '4w', '1m' → timedelta. Default 24h."""
    if not since:
        return timedelta(hours=24)
    m = _SINCE_PATTERN.match(since.strip().lower())
    if not m:
        raise ValueError(f"invalid 'since' value: {since!r} (expected '24h', '7d', '4w', '1m')")
    n, unit = int(m.group(1)), m.group(2)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    if unit == "w":
        return timedelta(weeks=n)
    if unit == "m":
        return timedelta(days=30 * n)  # approximate
    raise ValueError(f"unit {unit!r} unsupported")


def estimate_cost(tokens: int, call_type: str,
                  cost_embed: float = DEFAULT_COST_EMBED,
                  cost_llm_in: float = DEFAULT_COST_LLM_IN,
                  cost_llm_out: float = DEFAULT_COST_LLM_OUT) -> float:
    """Shared cost estimator so BudgetGuard and CostWatcher agree on math."""
    per_m = (tokens or 0) / 1_000_000.0
    if call_type == "embed":
        return per_m * cost_embed
    if call_type == "llm_in":
        return per_m * cost_llm_in
    if call_type == "llm_out":
        return per_m * cost_llm_out
    return 0.0


class CostWatcher:
    """Pure observability over the BudgetGuard SQLite `calls` table.

    NEVER raises on valid input. If the DB path doesn't exist yet, an empty
    report is returned. Enforcement decisions are NOT the CostWatcher's job.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def record(
        self,
        database_name: str,
        operation: str,
        file_hash: str | None,
        estimated_tokens: int,
        call_type: str,
        file_path: str | None = None,
        cost_usd: float | None = None,
    ) -> None:
        """Append a row. No enforcement. No exceptions bubble out — observability
        must never block the primary workflow.
        """
        if cost_usd is None:
            cost_usd = estimate_cost(estimated_tokens, call_type)
        try:
            with sqlite3.connect(self.db_path, isolation_level=None) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute(
                    "INSERT INTO calls "
                    "(file_path, file_hash, token_count, cost_usd, call_type, "
                    " database_name, operation) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        file_path,
                        file_hash,
                        estimated_tokens,
                        cost_usd,
                        call_type,
                        database_name,
                        operation,
                    ),
                )
        except Exception as e:
            logger.warning(
                "CostWatcher.record failed (non-fatal): %s | db=%s op=%s",
                e, database_name, operation,
            )

    def report(
        self,
        since: str = "24h",
        db_name: str | None = None,
        group_by: Iterable[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Aggregate recent calls.

        Args:
            since: window like '24h', '7d', '4w', '1m'.
            db_name: optional filter. None = all databases.
            group_by: list of columns from {database_name, operation,
                call_type, day, hour}. Default: ['operation'].
            limit: max result rows.
        """
        # None → default to operation grouping; empty list → no grouping (roll-up)
        if group_by is None:
            group_by = ["operation"]
        else:
            group_by = list(group_by)
        for col in group_by:
            if col not in ALLOWED_GROUP_COLUMNS:
                raise ValueError(
                    f"invalid group_by column: {col!r}. "
                    f"Allowed: {sorted(ALLOWED_GROUP_COLUMNS)}"
                )

        window = _parse_since(since)
        cutoff = (datetime.now() - window).isoformat()

        select_exprs: list[str] = []
        group_exprs: list[str] = []
        for col in group_by:
            if col == "day":
                select_exprs.append("date(timestamp) AS day")
                group_exprs.append("date(timestamp)")
            elif col == "hour":
                select_exprs.append(
                    "strftime('%Y-%m-%d %H:00', timestamp) AS hour"
                )
                group_exprs.append("strftime('%Y-%m-%d %H:00', timestamp)")
            else:
                select_exprs.append(col)
                group_exprs.append(col)

        select_clause = ", ".join(select_exprs) + (
            ", " if select_exprs else ""
        ) + (
            "COUNT(*) AS calls, "
            "COALESCE(SUM(cost_usd), 0) AS cost_usd, "
            "COALESCE(SUM(token_count), 0) AS tokens"
        )

        where_clauses = ["timestamp >= ?"]
        params: list[Any] = [cutoff]
        if db_name:
            where_clauses.append("database_name = ?")
            params.append(db_name)

        sql = (
            f"SELECT {select_clause} FROM calls "
            f"WHERE {' AND '.join(where_clauses)} "
            + (f"GROUP BY {', '.join(group_exprs)} " if group_exprs else "")
            + "ORDER BY cost_usd DESC "
            f"LIMIT {int(limit)}"
        )

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                cur = conn.execute(sql, params)
                columns = [d[0] for d in cur.description]
                rows = [dict(zip(columns, r)) for r in cur.fetchall()]
            for r in rows:
                if "cost_usd" in r and r["cost_usd"] is not None:
                    r["cost_usd"] = round(float(r["cost_usd"]), 6)
            return rows
        except sqlite3.OperationalError as e:
            logger.warning(
                "CostWatcher.report failed (returning empty): %s", e
            )
            return []

    def totals(self, since: str = "24h",
               db_name: str | None = None) -> dict[str, Any]:
        """Convenience: single-row roll-up for a window."""
        rows = self.report(since=since, db_name=db_name, group_by=[])
        if not rows:
            return {"calls": 0, "cost_usd": 0.0, "tokens": 0, "window": since}
        row = rows[0]
        row["window"] = since
        return row

    def render_markdown(
        self,
        since: str = "24h",
        db_name: str | None = None,
        group_by: Iterable[str] | None = None,
        limit: int = 200,
    ) -> str:
        """Render a markdown table for CLI / MCP output."""
        rows = self.report(
            since=since, db_name=db_name, group_by=group_by, limit=limit
        )
        if not rows:
            return f"_No calls recorded in the last {since}._"
        columns = list(rows[0].keys())
        head = "| " + " | ".join(columns) + " |"
        sep = "|" + "|".join(["---"] * len(columns)) + "|"
        body = "\n".join(
            "| "
            + " | ".join(
                (f"${v:.4f}" if c == "cost_usd" and isinstance(v, (int, float))
                 else f"{v:,}" if isinstance(v, (int, float))
                 else str(v if v is not None else "-"))
                for c, v in r.items()
            )
            + " |"
            for r in rows
        )
        total_cost = sum(
            float(r.get("cost_usd", 0) or 0) for r in rows
        )
        footer = f"\n\n**Total cost (window={since}): ${total_cost:.4f}**"
        return "\n".join([head, sep, body]) + footer
