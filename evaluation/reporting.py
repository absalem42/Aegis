from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import uuid4

from config import (
    EXECUTION_MODE_PAPER,
    KRAKEN_BACKEND_CLI,
    KRAKEN_BACKEND_REST,
    KRAKEN_EXECUTION_MODE_PAPER,
    MARKET_DATA_MODE_KRAKEN,
    MARKET_DATA_MODE_MOCK,
    Settings,
)
from db import (
    get_cash_balance,
    get_connection,
    get_total_market_value,
    get_total_realized_pnl,
    get_total_unrealized_pnl,
    init_db,
    list_positions,
    list_recent,
    reset_runtime_state,
)
from engine import run_engine_cycle
from models import utc_now_iso
from proof.agent_identity import build_agent_identity


def run_evaluation(
    settings: Settings,
    cycles: int,
    reset_first: bool = True,
    label: str | None = None,
) -> dict[str, Any]:
    evaluation_settings = replace(
        settings,
        execution_mode=EXECUTION_MODE_PAPER,
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_PAPER,
        session_live_opt_in=False,
        session_live_confirmation_input="",
        session_live_submit_opt_in=False,
    )
    evaluation_settings.ensure_paths()
    cycles = max(1, int(cycles))
    report_id = str(uuid4())
    started_at = utc_now_iso()
    evaluation_label = _normalize_label(label) or f"eval-{started_at[:19].replace(':', '-')}"

    if reset_first:
        reset_runtime_state(evaluation_settings)

    with get_connection(evaluation_settings.db_path) as connection:
        init_db(connection)
        baseline = _collect_baseline_snapshot(connection, evaluation_settings)

    cycle_results: list[dict[str, Any]] = []
    for _ in range(cycles):
        cycle_results.append(run_engine_cycle(evaluation_settings).to_dict())

    with get_connection(evaluation_settings.db_path) as connection:
        init_db(connection)
        report = build_evaluation_report(
            connection=connection,
            settings=evaluation_settings,
            report_id=report_id,
            label=evaluation_label,
            cycles=cycles,
            reset_first=reset_first,
            started_at=started_at,
            cycle_results=cycle_results,
            baseline=baseline,
        )

    report_path = save_evaluation_report(evaluation_settings, report)
    report["report_path"] = str(report_path)
    return report


def build_evaluation_report(
    connection,
    settings: Settings,
    report_id: str,
    label: str,
    cycles: int,
    reset_first: bool,
    started_at: str,
    cycle_results: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    all_trades = list_recent(connection, "trades", limit=10_000)
    all_blocked = list_recent(connection, "blocked_trades", limit=10_000)
    all_artifacts = list_recent(connection, "artifacts", limit=10_000)
    all_runs = list_recent(connection, "agent_runs", limit=10_000)
    all_positions = list_positions(connection)

    new_trades = all_trades[: max(0, len(all_trades) - baseline["trade_count"])]
    new_blocked = all_blocked[: max(0, len(all_blocked) - baseline["blocked_trade_count"])]
    new_artifacts = all_artifacts[: max(0, len(all_artifacts) - baseline["artifact_count"])]
    new_runs = all_runs[: max(0, len(all_runs) - baseline["agent_run_count"])]

    new_trades = list(reversed(new_trades))
    new_blocked = list(reversed(new_blocked))
    new_artifacts = list(reversed(new_artifacts))
    new_runs = list(reversed(new_runs))

    run_summaries = [_loads_json(row.get("summary_json")) for row in new_runs]
    ending_cash = get_cash_balance(connection, settings.starting_cash)
    ending_market_value = get_total_market_value(connection)
    ending_realized_total = get_total_realized_pnl(connection)
    ending_unrealized_total = get_total_unrealized_pnl(connection)
    ending_equity = ending_cash + ending_market_value

    realized_pnl = round(ending_realized_total - baseline["realized_total"], 6)
    unrealized_pnl = round(ending_unrealized_total - baseline["unrealized_total"], 6)
    total_pnl = round(ending_equity - baseline["starting_equity"], 6)
    closed_trade_pnls = [float(row.get("pnl", 0.0)) for row in new_trades if row.get("side") == "SELL"]
    positive_pnls = [pnl for pnl in closed_trade_pnls if pnl > 0]
    negative_pnls = [pnl for pnl in closed_trade_pnls if pnl < 0]
    artifact_linked_trade_count = sum(1 for row in new_trades if row.get("artifact_id"))
    artifact_coverage = (
        round(artifact_linked_trade_count / len(new_trades), 6) if new_trades else None
    )

    requested_market_modes = _unique_values(run_summaries, "modes", "requested_market_data_mode")
    effective_market_modes = _unique_values(run_summaries, "modes", "effective_market_data_mode")
    requested_execution_modes = _unique_values(run_summaries, "modes", "requested_execution_mode")
    effective_execution_modes = _unique_values(run_summaries, "modes", "effective_execution_mode")
    requested_kraken_backends = _unique_values(run_summaries, "modes", "requested_kraken_backend")
    effective_kraken_backends = _unique_values(run_summaries, "modes", "effective_kraken_backend")
    market_data_providers = _unique_values(run_summaries, "modes", "market_data_provider")
    market_data_source_types = _unique_values(run_summaries, "modes", "market_data_source_type")
    market_data_statuses = _unique_values(run_summaries, "modes", "market_data_status")
    kraken_cli_statuses = _unique_values(run_summaries, "modes", "kraken_cli_status")
    warnings = _collect_warnings(run_summaries)

    signal_count = sum(int(summary.get("signal_count", 0)) for summary in run_summaries)
    executed_count = sum(int(summary.get("executed_count", 0)) for summary in run_summaries)
    blocked_count = sum(int(summary.get("blocked_count", 0)) for summary in run_summaries)
    latest_prices = run_summaries[-1].get("latest_prices", {}) if run_summaries else {}
    max_drawdown = max(
        float(summary.get("metrics", {}).get("max_drawdown", 0.0)) for summary in run_summaries
    ) if run_summaries else 0.0

    win_rate, win_rate_note = _derive_win_rate(closed_trade_pnls)
    profit_factor, profit_factor_note = _derive_profit_factor(positive_pnls, negative_pnls)
    avg_pnl_per_closed_trade, avg_pnl_note = _derive_average_closed_trade_pnl(closed_trade_pnls)
    source_quality = _derive_source_quality(
        effective_market_modes=effective_market_modes,
        effective_kraken_backends=effective_kraken_backends,
    )
    source_quality_indicator = source_quality["value"]

    metrics = {
        "cycle_count": cycles,
        "signal_count": signal_count,
        "executed_count": executed_count,
        "blocked_count": blocked_count,
        "trade_count": len(new_trades),
        "blocked_trade_count": len(new_blocked),
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "total_pnl": total_pnl,
        "ending_cash": round(ending_cash, 6),
        "ending_equity": round(ending_equity, 6),
        "starting_equity": round(baseline["starting_equity"], 6),
        "max_drawdown": round(max_drawdown, 6),
        "artifact_count": len(new_artifacts),
        "artifact_coverage_for_executed_decisions": artifact_coverage,
        "closed_trade_count": len(closed_trade_pnls),
        "win_rate": win_rate,
        "win_rate_note": win_rate_note,
        "profit_factor": profit_factor,
        "profit_factor_note": profit_factor_note,
        "average_pnl_per_closed_trade": avg_pnl_per_closed_trade,
        "average_pnl_note": avg_pnl_note,
        "source_quality_indicator": source_quality_indicator,
        "source_quality_note": source_quality["note"],
    }
    scorecard = calculate_local_evaluation_score(metrics)
    latest_mode_summary = run_summaries[-1].get("modes", {}) if run_summaries else {}
    agent_identity = build_agent_identity(settings, latest_mode_summary)

    report = {
        "report_id": report_id,
        "label": label,
        "generated_at": utc_now_iso(),
        "started_at": started_at,
        "reset_first": reset_first,
        "agent": agent_identity,
        "requested_market_data_mode": _single_or_mixed(requested_market_modes),
        "effective_market_data_mode": _single_or_mixed(effective_market_modes),
        "requested_execution_mode": _single_or_mixed(requested_execution_modes),
        "effective_execution_mode": _single_or_mixed(effective_execution_modes),
        "requested_kraken_backend": _single_or_mixed(requested_kraken_backends),
        "effective_kraken_backend": _single_or_mixed(effective_kraken_backends),
        "market_data_provider": _single_or_mixed(market_data_providers),
        "market_data_source_type": _single_or_mixed(market_data_source_types),
        "market_data_status": _single_or_mixed(market_data_statuses),
        "kraken_cli_status": _single_or_mixed(kraken_cli_statuses),
        "metrics": metrics,
        "scorecard": scorecard,
        "proof_summary": {
            "artifact_count": len(new_artifacts),
            "artifact_coverage_for_executed_decisions": artifact_coverage,
            "artifact_readiness_summary": (
                "Aegis preserved local TradeIntent artifacts with agent identity, mode metadata, and decision context."
                if new_artifacts
                else "No new artifacts were generated during this evaluation."
            ),
        },
        "latest_prices": latest_prices,
        "run_ids": [row.get("id") for row in new_runs],
        "warnings": warnings,
        "comparison_snapshot": {
            "source_quality": source_quality_indicator,
            "total_pnl": total_pnl,
            "max_drawdown": round(max_drawdown, 6),
            "executed_count": executed_count,
            "artifact_coverage": artifact_coverage,
            "local_score": scorecard["score"],
        },
        "positions_snapshot": all_positions,
    }
    return report


def save_evaluation_report(settings: Settings, report: dict[str, Any]) -> Path:
    settings.ensure_paths()
    file_stem = f"{report['generated_at'][:19].replace(':', '-')}_{_slugify(report['label'])}_{report['report_id'][:8]}"
    path = settings.report_dir / f"{file_stem}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def list_evaluation_reports(settings: Settings, limit: int = 10) -> list[dict[str, Any]]:
    settings.ensure_paths()
    reports: list[dict[str, Any]] = []
    for path in sorted(settings.report_dir.glob("*.json"), reverse=True):
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(loaded, dict):
            continue
        loaded["report_path"] = str(path)
        reports.append(loaded)
        if len(reports) >= limit:
            break
    return reports


def load_latest_evaluation_report(settings: Settings) -> dict[str, Any] | None:
    reports = list_evaluation_reports(settings, limit=1)
    return reports[0] if reports else None


def calculate_local_evaluation_score(metrics: dict[str, Any]) -> dict[str, Any]:
    # Simple, explicit local score. This is an internal comparison aid, not an official leaderboard score.
    starting_equity = max(float(metrics.get("starting_equity") or 0.0), 1.0)
    total_pnl = float(metrics.get("total_pnl") or 0.0)
    realized_pnl = float(metrics.get("realized_pnl") or 0.0)
    max_drawdown = max(float(metrics.get("max_drawdown") or 0.0), 0.0)
    artifact_coverage = float(metrics.get("artifact_coverage_for_executed_decisions") or 0.0)
    executed_count = float(metrics.get("executed_count") or 0.0)
    blocked_count = float(metrics.get("blocked_count") or 0.0)
    execution_ratio = executed_count / max(executed_count + blocked_count, 1.0)
    scale = max(starting_equity * 0.02, 1.0)

    total_pnl_component = _clamp((total_pnl / scale) * 20.0, -20.0, 20.0)
    realized_pnl_component = _clamp((realized_pnl / scale) * 10.0, -10.0, 10.0)
    artifact_component = artifact_coverage * 20.0
    execution_component = execution_ratio * 10.0
    drawdown_penalty = min(max_drawdown * 100.0 * 1.5, 25.0)
    raw_score = 50.0 + total_pnl_component + realized_pnl_component + artifact_component + execution_component - drawdown_penalty
    score = round(_clamp(raw_score, 0.0, 100.0), 2)

    return {
        "score": score,
        "label": "Local Evaluation Score",
        "caption": "Local/internal score for transparent comparison only. It is not an official leaderboard or hackathon score.",
        "formula": {
            "base_score": 50.0,
            "total_pnl_component": round(total_pnl_component, 2),
            "realized_pnl_component": round(realized_pnl_component, 2),
            "artifact_coverage_component": round(artifact_component, 2),
            "execution_ratio_component": round(execution_component, 2),
            "drawdown_penalty": round(drawdown_penalty, 2),
        },
    }


def format_evaluation_history_rows(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        metrics = report.get("metrics", {})
        scorecard = report.get("scorecard", {})
        rows.append(
            {
                "generated_at": report.get("generated_at"),
                "label": report.get("label"),
                "source_quality": metrics.get("source_quality_indicator"),
                "market_data": report.get("market_data_provider"),
                "backend": report.get("effective_kraken_backend") or "mock",
                "cycles": metrics.get("cycle_count"),
                "executed": metrics.get("executed_count"),
                "blocked": metrics.get("blocked_count"),
                "total_pnl": metrics.get("total_pnl"),
                "max_drawdown": metrics.get("max_drawdown"),
                "artifact_coverage": metrics.get("artifact_coverage_for_executed_decisions"),
                "local_score": scorecard.get("score"),
            }
        )
    return rows


def format_evaluation_comparison_rows(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        metrics = report.get("metrics", {})
        rows.append(
            {
                "label": report.get("label"),
                "source_quality": metrics.get("source_quality_indicator"),
                "total_pnl": metrics.get("total_pnl"),
                "max_drawdown": metrics.get("max_drawdown"),
                "executed_count": metrics.get("executed_count"),
                "artifact_coverage": metrics.get("artifact_coverage_for_executed_decisions"),
                "local_score": report.get("scorecard", {}).get("score"),
            }
        )
    return rows


def build_best_vs_latest_summary(reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not reports:
        return None

    latest = reports[0]
    best = max(reports, key=lambda report: float(report.get("scorecard", {}).get("score") or 0.0))
    return {
        "latest": _build_report_comparison_summary(latest),
        "best": _build_report_comparison_summary(best),
        "same_report": latest.get("report_id") == best.get("report_id"),
        "caption": "Compares the highest local/internal score with the latest saved evaluation. It is not the official leaderboard.",
    }


def format_evaluation_proof_snapshot_rows(
    reports: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports[:limit]:
        metrics = report.get("metrics", {})
        proof_summary = report.get("proof_summary", {})
        agent = report.get("agent", {})
        rows.append(
            {
                "generated_at": report.get("generated_at"),
                "label": report.get("label"),
                "agent_name": agent.get("agent_name") or "Aegis",
                "agent_version": agent.get("version") or "unknown",
                "source_quality": metrics.get("source_quality_indicator"),
                "artifact_coverage": metrics.get("artifact_coverage_for_executed_decisions"),
                "artifact_count": proof_summary.get("artifact_count"),
                "readiness_summary": proof_summary.get("artifact_readiness_summary"),
                "local_score": report.get("scorecard", {}).get("score"),
            }
        )
    return rows


def build_provider_capabilities_summary() -> list[dict[str, str]]:
    return [
        {
            "provider": "Mock",
            "status": "Available",
            "notes": "Deterministic local demo data for repeatable evaluations.",
        },
        {
            "provider": "Kraken REST",
            "status": "Available",
            "notes": "Public market data only. No authenticated trading.",
        },
        {
            "provider": "Kraken CLI",
            "status": "Optional",
            "notes": "Requires local Kraken CLI binary. Supports read-only market data and optional CLI paper execution.",
        },
        {
            "provider": "Execution",
            "status": "Paper Only",
            "notes": "Evaluations stay internal-paper-only. Demo runs may use internal paper or Kraken CLI paper. Kraken live remains blocked.",
        },
    ]


def _collect_baseline_snapshot(connection, settings: Settings) -> dict[str, Any]:
    starting_cash = get_cash_balance(connection, settings.starting_cash)
    starting_market_value = get_total_market_value(connection)
    return {
        "trade_count": _count_rows(connection, "trades"),
        "blocked_trade_count": _count_rows(connection, "blocked_trades"),
        "artifact_count": _count_rows(connection, "artifacts"),
        "agent_run_count": _count_rows(connection, "agent_runs"),
        "realized_total": get_total_realized_pnl(connection),
        "unrealized_total": get_total_unrealized_pnl(connection),
        "starting_cash": starting_cash,
        "starting_equity": starting_cash + starting_market_value,
    }


def _build_report_comparison_summary(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics", {})
    return {
        "label": report.get("label"),
        "generated_at": report.get("generated_at"),
        "source_quality": metrics.get("source_quality_indicator"),
        "total_pnl": metrics.get("total_pnl"),
        "max_drawdown": metrics.get("max_drawdown"),
        "artifact_coverage": metrics.get("artifact_coverage_for_executed_decisions"),
        "local_score": report.get("scorecard", {}).get("score"),
    }


def _derive_win_rate(closed_trade_pnls: list[float]) -> tuple[float | None, str]:
    if not closed_trade_pnls:
        return None, "Not enough closed sell trades yet."
    wins = sum(1 for pnl in closed_trade_pnls if pnl > 0)
    return round(wins / len(closed_trade_pnls), 6), ""


def _derive_profit_factor(positive_pnls: list[float], negative_pnls: list[float]) -> tuple[float | None, str]:
    if not positive_pnls or not negative_pnls:
        return None, "Not enough winning and losing closed trades yet."
    gross_profit = sum(positive_pnls)
    gross_loss = abs(sum(negative_pnls))
    if gross_loss <= 0:
        return None, "Not enough losing closed trades yet."
    return round(gross_profit / gross_loss, 6), ""


def _derive_average_closed_trade_pnl(closed_trade_pnls: list[float]) -> tuple[float | None, str]:
    if not closed_trade_pnls:
        return None, "Not enough closed sell trades yet."
    return round(mean(closed_trade_pnls), 6), ""


def _derive_source_quality(
    effective_market_modes: list[str],
    effective_kraken_backends: list[str | None],
) -> dict[str, str]:
    market_mode = _single_or_mixed(effective_market_modes)
    backend = _single_or_mixed(effective_kraken_backends)
    if market_mode == MARKET_DATA_MODE_MOCK:
        return {"value": "mock", "note": "Deterministic mock market data backed this evaluation."}
    if market_mode == MARKET_DATA_MODE_KRAKEN and backend == KRAKEN_BACKEND_REST:
        return {"value": "Kraken REST", "note": "Real Kraken public REST market data backed this evaluation."}
    if market_mode == MARKET_DATA_MODE_KRAKEN and backend == KRAKEN_BACKEND_CLI:
        return {"value": "Kraken CLI", "note": "Real Kraken market data arrived through the local Kraken CLI path."}
    return {"value": "mixed", "note": "Effective market-data source varied during this evaluation."}


def _collect_warnings(run_summaries: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for summary in run_summaries:
        for warning in summary.get("modes", {}).get("warnings", []):
            if not isinstance(warning, str) or warning in seen:
                continue
            warnings.append(warning)
            seen.add(warning)
    return warnings


def _unique_values(run_summaries: list[dict[str, Any]], section: str, key: str) -> list[Any]:
    values = []
    seen = set()
    for summary in run_summaries:
        container = summary.get(section, {})
        if not isinstance(container, dict):
            continue
        value = container.get(key)
        marker = json.dumps(value, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        values.append(value)
    return values


def _single_or_mixed(values: list[Any]) -> Any:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return "mixed"


def _count_rows(connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"]) if row else 0


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_label(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split()).strip()


def _slugify(value: str) -> str:
    safe = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "evaluation"


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
