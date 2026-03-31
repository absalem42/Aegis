from __future__ import annotations

import json
from typing import Any


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def format_signal_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for row in rows:
        indicators = _loads_json(row.get("indicator_json"))
        formatted.append(
            {
                "ts": row.get("ts"),
                "symbol": row.get("symbol"),
                "action": row.get("action"),
                "reason": row.get("reason"),
                "should_execute": bool(row.get("should_execute")),
                "price": indicators.get("price"),
                "ema20": indicators.get("ema20"),
                "ema50": indicators.get("ema50"),
                "recent_high": indicators.get("recent_high"),
                "recent_low": indicators.get("recent_low"),
            }
        )
    return formatted


def format_blocked_trade_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for row in rows:
        context = _loads_json(row.get("context_json"))
        reason_codes = context.get("risk_reason_codes", [])
        formatted.append(
            {
                "ts": row.get("ts"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "attempted_quantity": row.get("attempted_quantity"),
                "attempted_price": row.get("attempted_price"),
                "block_reason": row.get("block_reason"),
                "risk_reason_codes": ", ".join(reason_codes) if isinstance(reason_codes, list) else "",
                "signal_reason": context.get("signal_reason"),
            }
        )
    return formatted


def format_trade_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ts": row.get("ts"),
            "symbol": row.get("symbol"),
            "side": row.get("side"),
            "quantity": row.get("quantity"),
            "price": row.get("price"),
            "notional": row.get("notional"),
            "reason": row.get("reason"),
            "pnl": row.get("pnl"),
            "artifact_id": row.get("artifact_id"),
        }
        for row in rows
    ]


def format_artifact_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for row in rows:
        payload = _loads_json(row.get("payload_json"))
        risk = payload.get("risk", {})
        formatted.append(
            {
                "ts": row.get("ts"),
                "subject": row.get("subject"),
                "type": row.get("artifact_type"),
                "side": payload.get("side"),
                "quantity": payload.get("quantity"),
                "price": payload.get("price"),
                "signal_reason": payload.get("reason"),
                "risk_allowed": risk.get("allowed"),
                "path": row.get("path"),
                "hash": str(row.get("hash_or_digest", ""))[:12],
            }
        )
    return formatted


def format_latest_artifact_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = _loads_json(row.get("payload_json"))
    risk = payload.get("risk", {})
    return {
        "artifact_id": row.get("id"),
        "type": row.get("artifact_type"),
        "subject": row.get("subject"),
        "created_at": row.get("ts"),
        "symbol": payload.get("symbol", row.get("subject")),
        "side": payload.get("side"),
        "quantity": payload.get("quantity"),
        "price": payload.get("price"),
        "signal_reason": payload.get("reason"),
        "risk_allowed": risk.get("allowed"),
        "risk_reason_codes": ", ".join(risk.get("reason_codes", [])),
        "path": row.get("path"),
        "hash": str(row.get("hash_or_digest", ""))[:16],
        "summary": "Pre-execution local TradeIntent artifact saved before a paper trade decision.",
    }


def format_run_history_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for row in rows:
        summary = _loads_json(row.get("summary_json"))
        formatted.append(
            {
                "run_id": row.get("id"),
                "run_id_short": str(row.get("id", ""))[:8],
                "ts": row.get("ts"),
                "status": row.get("status"),
                "signal_count": summary.get("signal_count", 0),
                "executed_count": summary.get("executed_count", 0),
                "blocked_count": summary.get("blocked_count", 0),
                "artifact_count": summary.get("artifact_count", 0),
                "latest_prices": summary.get("latest_prices", {}),
                "metrics": summary.get("metrics", {}),
            }
        )
    return formatted


def format_run_option_labels(rows: list[dict[str, Any]]) -> list[str]:
    return [
        (
            f"{row['run_id_short']} | {row['ts']} | "
            f"exec {row['executed_count']} | blocked {row['blocked_count']}"
        )
        for row in rows
    ]


def format_run_detail(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    metrics = row.get("metrics", {})
    return {
        "run_id": row.get("run_id"),
        "timestamp": row.get("ts"),
        "status": row.get("status"),
        "prices_observed": row.get("latest_prices", {}),
        "metrics_snapshot": metrics,
        "signal_count": row.get("signal_count", 0),
        "executed_count": row.get("executed_count", 0),
        "blocked_count": row.get("blocked_count", 0),
        "artifact_count": row.get("artifact_count", 0),
    }
