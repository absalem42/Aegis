from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.min
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min


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


def build_decision_chains(
    signal_rows: list[dict[str, Any]],
    blocked_trade_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    signals = list(signal_rows)
    artifacts_by_id = {row.get("id"): row for row in artifact_rows if row.get("id")}
    chains: list[dict[str, Any]] = []

    for row in trade_rows:
        trade_ts = row.get("ts")
        matched_signal = _match_signal(
            signals=signals,
            symbol=row.get("symbol"),
            reason=row.get("reason"),
            ts=trade_ts,
        )
        artifact = artifacts_by_id.get(row.get("artifact_id"))
        artifact_payload = _loads_json(artifact.get("payload_json")) if artifact else {}
        risk = artifact_payload.get("risk", {})
        chains.append(
            {
                "ts": trade_ts,
                "symbol": row.get("symbol"),
                "action": row.get("side"),
                "outcome": "EXECUTED",
                "signal_reason": row.get("reason"),
                "signal": _signal_summary(matched_signal),
                "risk": {
                    "allowed": True,
                    "summary": "ALLOWED",
                    "reason_codes": risk.get("reason_codes", []),
                },
                "artifact": _artifact_summary(artifact),
                "execution": {
                    "status": row.get("status", "FILLED"),
                    "quantity": row.get("quantity"),
                    "price": row.get("price"),
                    "notional": row.get("notional"),
                    "pnl": row.get("pnl"),
                    "artifact_id": row.get("artifact_id"),
                },
            }
        )

    for row in blocked_trade_rows:
        context = _loads_json(row.get("context_json"))
        matched_signal = _match_signal(
            signals=signals,
            symbol=row.get("symbol"),
            reason=context.get("signal_reason"),
            ts=row.get("ts"),
        )
        signal_summary = _signal_summary(matched_signal)
        if not signal_summary["indicators"] and isinstance(context.get("indicators"), dict):
            signal_summary["indicators"] = context["indicators"]
        chains.append(
            {
                "ts": row.get("ts"),
                "symbol": row.get("symbol"),
                "action": row.get("side"),
                "outcome": "BLOCKED",
                "signal_reason": context.get("signal_reason") or row.get("block_reason"),
                "signal": signal_summary,
                "risk": {
                    "allowed": False,
                    "summary": row.get("block_reason"),
                    "reason_codes": context.get("risk_reason_codes", []),
                },
                "artifact": {
                    "created": False,
                    "summary": "No artifact created because the risk check blocked execution.",
                },
                "execution": {
                    "status": "BLOCKED",
                    "quantity": row.get("attempted_quantity"),
                    "price": row.get("attempted_price"),
                    "notional": _safe_notional(row.get("attempted_quantity"), row.get("attempted_price")),
                    "pnl": None,
                    "artifact_id": None,
                },
            }
        )

    chains.sort(key=lambda row: _parse_ts(row.get("ts")), reverse=True)
    return chains[:limit]


def format_decision_chain_summary(chain: dict[str, Any]) -> dict[str, Any]:
    signal = chain.get("signal", {})
    risk = chain.get("risk", {})
    artifact = chain.get("artifact", {})
    execution = chain.get("execution", {})
    indicators = signal.get("indicators", {})
    return {
        "timestamp": chain.get("ts"),
        "symbol": chain.get("symbol"),
        "action": chain.get("action"),
        "signal_reason": chain.get("signal_reason"),
        "price": indicators.get("price"),
        "ema20": indicators.get("ema20"),
        "ema50": indicators.get("ema50"),
        "recent_high": indicators.get("recent_high"),
        "recent_low": indicators.get("recent_low"),
        "risk_allowed": risk.get("allowed"),
        "risk_summary": risk.get("summary"),
        "risk_reason_codes": ", ".join(risk.get("reason_codes", [])),
        "artifact_id": artifact.get("artifact_id"),
        "artifact_path": artifact.get("path"),
        "artifact_hash": artifact.get("hash"),
        "trade_status": execution.get("status"),
        "quantity": execution.get("quantity"),
        "price_executed": execution.get("price"),
        "pnl": execution.get("pnl"),
    }


def format_decision_chain_rows(chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ts": chain.get("ts"),
            "symbol": chain.get("symbol"),
            "action": chain.get("action"),
            "outcome": chain.get("outcome"),
            "signal_reason": chain.get("signal_reason"),
            "risk": chain.get("risk", {}).get("summary"),
            "artifact": chain.get("artifact", {}).get("artifact_id"),
            "trade_status": chain.get("execution", {}).get("status"),
        }
        for chain in chains
    ]


def _match_signal(
    signals: list[dict[str, Any]],
    symbol: str | None,
    reason: str | None,
    ts: str | None,
) -> dict[str, Any] | None:
    target_ts = _parse_ts(ts)
    candidates = [
        row
        for row in signals
        if row.get("symbol") == symbol and (reason is None or row.get("reason") == reason)
    ]
    if not candidates and reason is not None:
        candidates = [row for row in signals if row.get("symbol") == symbol]
    if not candidates:
        return None
    candidates.sort(key=lambda row: abs((_parse_ts(row.get("ts")) - target_ts).total_seconds()))
    return candidates[0]


def _signal_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"action": None, "reason": None, "should_execute": None, "indicators": {}}
    indicators = _loads_json(row.get("indicator_json")) if "indicator_json" in row else row.get("indicators", {})
    return {
        "action": row.get("action"),
        "reason": row.get("reason"),
        "should_execute": bool(row.get("should_execute")) if row.get("should_execute") is not None else None,
        "indicators": indicators if isinstance(indicators, dict) else {},
    }


def _artifact_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"created": False, "summary": "No artifact linked to this decision."}
    return {
        "created": True,
        "artifact_id": row.get("id"),
        "type": row.get("artifact_type"),
        "path": row.get("path"),
        "hash": str(row.get("hash_or_digest", ""))[:16],
        "summary": "TradeIntent artifact created before execution.",
    }


def _safe_notional(quantity: Any, price: Any) -> float | None:
    try:
        return round(float(quantity) * float(price), 6)
    except (TypeError, ValueError):
        return None
