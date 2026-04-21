#!/usr/bin/env python3
"""
Safety Wrapper
==============
Unified entry point for paid API calls in HybridRAG.

Combines:
- BudgetGuard  (enforcement — refuses over-budget ingestion/enrichment calls)
- CostWatcher  (observability — records every paid call for reporting)
- Mode-aware gating (spoonfeed daily quota, batch, oneshot)

Use `guarded_call(...)` for any operation that spends money. On success,
the paid API's result is returned. On budget breach, BudgetExceededError
is raised (caller decides whether to halt the pipeline or skip the file).

A thin CostWatcher.record() happens AFTER the call, so observability
captures actual work done (successes only). BudgetGuard.check_and_log()
still happens BEFORE the call, since enforcement has to be pre-spend.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from src.budget_guard import BudgetGuard, BudgetExceededError
from src.cost_watcher import CostWatcher, estimate_cost

logger = logging.getLogger(__name__)


# Operations that are ENFORCED (can block past budget).
# Queries are observability-only — we never refuse a user's query mid-flow.
ENFORCED_OPERATIONS = {"ingest", "enrichment"}

# Modes
MODE_SPOONFEED = "spoonfeed"   # daily file quota + budget + hash cap
MODE_BATCH = "batch"           # budget + hash cap, no daily quota
MODE_ONESHOT = "oneshot"       # per-run cost cap, no watcher, hash cap


@dataclass
class ModeConfig:
    mode: str = MODE_BATCH
    # spoonfeed
    files_per_day: int = 10
    # batch / oneshot
    max_run_cost_usd: float | None = None


class DailyQuotaExceeded(BudgetExceededError):
    """Raised when spoonfeed daily file quota is exhausted."""


def _count_ingest_files_24h(db_path: str, database_name: str) -> int:
    """Count DISTINCT file_paths ingested by this DB in the last 24h."""
    day_ago = (datetime.now() - timedelta(hours=24)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        cur = conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM calls "
            "WHERE timestamp >= ? AND database_name = ? "
            "  AND operation IN ('ingest', 'enrichment')",
            (day_ago, database_name),
        )
        return int(cur.fetchone()[0] or 0)


async def guarded_call(
    *,
    db_path: str,
    database_name: str,
    operation: str,
    file_hash: str | None,
    estimated_tokens: int,
    call_type: str,
    coroutine_factory: Callable[[], Awaitable[Any]],
    file_path: str | None = None,
    budget_guard: BudgetGuard | None = None,
    cost_watcher: CostWatcher | None = None,
    mode: ModeConfig | None = None,
) -> Any:
    """Execute a paid API call with enforcement + observability.

    Args:
        db_path: shared SQLite path (budget.db).
        database_name: which registered DB this belongs to
            (e.g., 'specstory', 'athena-lightrag').
        operation: one of {'ingest', 'enrichment', 'query',
            'embed_query', 'llm_synth'}.
        file_hash: content hash of the unit of work (or None for queries).
        estimated_tokens: pre-spend token estimate (use tiktoken).
        call_type: 'embed' | 'llm_in' | 'llm_out' — selects the pricing row.
        coroutine_factory: zero-arg function returning the actual await-able
            paid call. Using a factory lets us decide NOT to call it when
            budget is breached.
        file_path: optional, stored for audit.
        budget_guard / cost_watcher: injectable; defaults constructed on
            `db_path` if omitted.
        mode: ModeConfig controlling spoonfeed / batch / oneshot behavior.

    Returns:
        Whatever the coroutine returns.

    Raises:
        BudgetExceededError: when enforcement blocks the call. Propagate up
            — caller decides halt vs skip. Observability is NOT recorded for
            blocked calls (the paid call didn't happen).
    """
    mode = mode or ModeConfig()
    if budget_guard is None:
        budget_guard = BudgetGuard(db_path=db_path)
    if cost_watcher is None:
        cost_watcher = CostWatcher(db_path=db_path)

    # ── ENFORCEMENT PATH (only for ingest/enrichment) ────────────────────
    if operation in ENFORCED_OPERATIONS:
        # 1) Mode-specific gates (daily quota for spoonfeed)
        if mode.mode == MODE_SPOONFEED:
            done_today = _count_ingest_files_24h(db_path, database_name)
            if done_today >= mode.files_per_day:
                raise DailyQuotaExceeded(
                    f"spoonfeed quota: {database_name} has processed "
                    f"{done_today} files in the last 24h "
                    f"(cap={mode.files_per_day}). Sleeping until window rolls."
                )

        # 2) Core budget + hash-repeat enforcement
        budget_guard.check_and_log(
            file_path=file_path or "",
            file_hash=file_hash or "",
            estimated_tokens=estimated_tokens,
            call_type=call_type,
            database_name=database_name,
            operation=operation,
        )

        # 3) Per-run cap (batch / oneshot modes)
        if mode.max_run_cost_usd is not None:
            totals = cost_watcher.report(
                since="24h", db_name=database_name, group_by=[]
            )
            run_cost = float(totals[0]["cost_usd"]) if totals else 0.0
            if run_cost > mode.max_run_cost_usd:
                raise BudgetExceededError(
                    f"per-run cap breached: ${run_cost:.4f} > "
                    f"${mode.max_run_cost_usd:.2f} (db={database_name}, "
                    f"mode={mode.mode})"
                )

    # ── RUN THE PAID CALL ────────────────────────────────────────────────
    result = await coroutine_factory()

    # ── OBSERVABILITY PATH (ALL operations, after the call lands) ────────
    # For ENFORCED ops, BudgetGuard already inserted a calls row — skip
    # double-insert here. For observe-only ops (queries), record now.
    if operation not in ENFORCED_OPERATIONS:
        cost_watcher.record(
            database_name=database_name,
            operation=operation,
            file_hash=file_hash,
            estimated_tokens=estimated_tokens,
            call_type=call_type,
            file_path=file_path,
        )

    return result


def resolve_mode_from_env(
    mode_name: str | None,
    *,
    default_files_per_day: int = 10,
    default_run_cap: float | None = None,
) -> ModeConfig:
    """Build ModeConfig, honoring env var overrides where they exist.

    Env precedence (high → low):
      HYBRIDRAG_SPOONFEED_FILES_PER_DAY
      HYBRIDRAG_MAX_RUN_COST_USD
    """
    m = (mode_name or MODE_BATCH).lower()
    if m not in {MODE_SPOONFEED, MODE_BATCH, MODE_ONESHOT}:
        logger.warning(
            "unknown ingestion_mode %r; falling back to batch", mode_name
        )
        m = MODE_BATCH

    files_per_day = int(
        os.environ.get(
            "HYBRIDRAG_SPOONFEED_FILES_PER_DAY", str(default_files_per_day)
        )
    )
    run_cap_env = os.environ.get("HYBRIDRAG_MAX_RUN_COST_USD")
    run_cap = (
        float(run_cap_env) if run_cap_env is not None
        else default_run_cap
    )

    return ModeConfig(
        mode=m,
        files_per_day=files_per_day,
        max_run_cost_usd=run_cap,
    )
