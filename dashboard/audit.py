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


def _safe_get(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _safe_notional(quantity: Any, price: Any) -> float | None:
    try:
        return round(float(quantity) * float(price), 6)
    except (TypeError, ValueError):
        return None


def _readiness_badge(readiness: dict[str, Any]) -> str:
    passed = readiness.get("ready_checks_passed", 0)
    total = readiness.get("ready_checks_total", 0)
    return f"{passed}/{total} checks" if total else "N/A"


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
                "execution_provider": context.get("execution_provider"),
                "execution_status": context.get("execution_status"),
                "artifact_id": context.get("artifact_id"),
                "live_readiness_status": _safe_get(context, "live_readiness", "status"),
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
            "status": row.get("status"),
            "pnl": row.get("pnl"),
            "artifact_id": row.get("artifact_id"),
            "order_id": row.get("order_id"),
            "execution_provider": row.get("execution_provider"),
        }
        for row in rows
    ]


def format_order_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for row in rows:
        response = _loads_json(row.get("response_json"))
        formatted.append(
            {
                "ts": row.get("ts"),
                "order_id": row.get("id"),
                "run_id": row.get("run_id"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "quantity": row.get("quantity"),
                "order_type": row.get("order_type"),
                "artifact_id": row.get("artifact_id"),
                "execution_provider": row.get("execution_provider"),
                "execution_mode": row.get("execution_mode"),
                "status": row.get("status"),
                "external_order_id": row.get("external_order_id"),
                "notes": row.get("notes"),
                "provider_summary": response,
            }
        )
    return formatted


def format_artifact_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for row in rows:
        payload = _loads_json(row.get("payload_json"))
        readiness = payload.get("validation_readiness", {})
        market_data = payload.get("market_data", {})
        execution = payload.get("execution", {})
        risk = payload.get("risk", {})
        formatted.append(
            {
                "ts": row.get("ts"),
                "artifact_id": row.get("id"),
                "subject": row.get("subject"),
                "type": row.get("artifact_type"),
                "side": payload.get("side"),
                "quantity": payload.get("quantity") or execution.get("filled_quantity"),
                "price": payload.get("price") or execution.get("fill_price"),
                "signal_reason": payload.get("reason"),
                "risk_allowed": risk.get("allowed"),
                "agent_name": payload.get("agent", {}).get("agent_name"),
                "market_data_provider": market_data.get("provider"),
                "kraken_backend": market_data.get("backend"),
                "market_data_status": market_data.get("status"),
                "kraken_cli_status": market_data.get("kraken_cli_status"),
                "execution_provider": execution.get("execution_provider"),
                "execution_mode": execution.get("effective_execution_mode"),
                "execution_status": execution.get("status"),
                "auth_test_status": execution.get("auth_test_status"),
                "validate_preflight_status": execution.get("validate_preflight_status"),
                "live_preflight_status": execution.get("live_preflight_status"),
                "submit_status": execution.get("submit_status"),
                "submit_attempted": execution.get("submit_attempted"),
                "live_order_submission_occurred": execution.get("live_order_submission_occurred"),
                "fill_state": execution.get("fill_state"),
                "local_order_id": execution.get("local_order_id"),
                "trade_intent_artifact_id": payload.get("trade_intent_artifact_id"),
                "readiness": _readiness_badge(readiness),
                "path": row.get("path"),
                "hash": str(row.get("hash_or_digest", ""))[:12],
            }
        )
    return formatted


def format_latest_artifact_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = _loads_json(row.get("payload_json"))
    readiness = payload.get("validation_readiness", {})
    market_data = payload.get("market_data", {})
    execution = payload.get("execution", {})
    risk = payload.get("risk", {})
    artifact_type = row.get("artifact_type")
    summary = (
        "Post-execution receipt linking the trade intent to the local order lifecycle."
        if artifact_type == "ExecutionReceipt"
        else "Pre-execution local TradeIntent artifact saved before a paper trade decision."
    )
    return {
        "artifact_id": row.get("id"),
        "type": artifact_type,
        "subject": row.get("subject"),
        "created_at": row.get("ts"),
        "symbol": payload.get("symbol", row.get("subject")),
        "side": payload.get("side"),
        "quantity": payload.get("quantity") or execution.get("filled_quantity"),
        "price": payload.get("price") or execution.get("fill_price"),
        "signal_reason": payload.get("reason"),
        "risk_allowed": risk.get("allowed"),
        "risk_reason_codes": ", ".join(risk.get("reason_codes", [])),
        "path": row.get("path"),
        "hash": str(row.get("hash_or_digest", ""))[:16],
        "modes": payload.get("modes", {}),
        "market_data": market_data,
        "kraken_backend": market_data.get("backend"),
        "kraken_cli_status": market_data.get("kraken_cli_status"),
        "agent": payload.get("agent", {}),
        "validation_readiness": readiness,
        "execution": execution,
        "trade_intent_artifact_id": payload.get("trade_intent_artifact_id"),
        "no_live_submit_performed": payload.get("no_live_submit_performed"),
        "receipt_status": payload.get("receipt_status"),
        "summary": summary,
    }


def format_run_history_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for row in rows:
        summary = _loads_json(row.get("summary_json"))
        modes = summary.get("modes", {})
        formatted.append(
            {
                "run_id": row.get("id"),
                "run_id_short": str(row.get("id", ""))[:8],
                "ts": row.get("ts"),
                "status": row.get("status"),
                "signal_count": summary.get("signal_count", 0),
                "executed_count": summary.get("executed_count", 0),
                "blocked_count": summary.get("blocked_count", 0),
                "order_count": summary.get("order_count", 0),
                "artifact_count": summary.get("artifact_count", 0),
                "receipt_count": summary.get("receipt_count", 0),
                "latest_prices": summary.get("latest_prices", {}),
                "metrics": summary.get("metrics", {}),
                "modes": modes,
                "market_data_provider": modes.get("market_data_provider"),
                "market_data_status": modes.get("market_data_status"),
                "requested_kraken_backend": modes.get("requested_kraken_backend"),
                "effective_kraken_backend": modes.get("effective_kraken_backend"),
                "kraken_cli_status": modes.get("kraken_cli_status"),
                "execution_provider": modes.get("execution_provider"),
                "execution_status": modes.get("execution_status"),
                "requested_kraken_execution_mode": modes.get("requested_kraken_execution_mode"),
                "effective_kraken_execution_mode": modes.get("effective_kraken_execution_mode"),
                "execution_source_type": modes.get("execution_source_type"),
                "live_readiness_status": modes.get("live_readiness_status"),
                "auth_test_status": modes.get("auth_test_status"),
                "validate_preflight_status": modes.get("validate_preflight_status"),
                "final_live_preflight_status": modes.get("final_live_preflight_status"),
                "submit_status": modes.get("submit_status"),
                "live_order_submission_occurred": modes.get("live_order_submission_occurred"),
                "external_order_id": modes.get("external_order_id"),
                "latest_live_execution": summary.get("latest_live_execution"),
            }
        )
    return formatted


def format_run_option_labels(rows: list[dict[str, Any]]) -> list[str]:
    return [
        (
            f"{row['run_id_short']} | {row['ts']} | "
            f"exec {row['executed_count']} | blocked {row['blocked_count']} | orders {row.get('order_count', 0)}"
        )
        for row in rows
    ]


def format_run_detail(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "run_id": row.get("run_id"),
        "timestamp": row.get("ts"),
        "status": row.get("status"),
        "prices_observed": row.get("latest_prices", {}),
        "metrics_snapshot": row.get("metrics", {}),
        "modes": row.get("modes", {}),
        "signal_count": row.get("signal_count", 0),
        "executed_count": row.get("executed_count", 0),
        "blocked_count": row.get("blocked_count", 0),
        "order_count": row.get("order_count", 0),
        "artifact_count": row.get("artifact_count", 0),
        "receipt_count": row.get("receipt_count", 0),
    }


def build_proof_summary(selected_run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not selected_run:
        return None
    return {
        "signal_count": selected_run.get("signal_count", 0),
        "executed_count": selected_run.get("executed_count", 0),
        "blocked_count": selected_run.get("blocked_count", 0),
        "order_count": selected_run.get("order_count", 0),
        "artifact_count": selected_run.get("artifact_count", 0),
        "receipt_count": selected_run.get("receipt_count", 0),
        "observed_prices": selected_run.get("latest_prices", {}),
        "modes": selected_run.get("modes", {}),
        "market_data_provider": selected_run.get("market_data_provider"),
        "market_data_status": selected_run.get("market_data_status"),
        "requested_kraken_backend": selected_run.get("requested_kraken_backend"),
        "effective_kraken_backend": selected_run.get("effective_kraken_backend"),
        "kraken_cli_status": selected_run.get("kraken_cli_status"),
        "execution_provider": selected_run.get("execution_provider"),
        "execution_status": selected_run.get("execution_status"),
        "requested_kraken_execution_mode": selected_run.get("requested_kraken_execution_mode"),
        "effective_kraken_execution_mode": selected_run.get("effective_kraken_execution_mode"),
        "live_readiness_status": selected_run.get("live_readiness_status"),
        "auth_test_status": selected_run.get("auth_test_status"),
        "validate_preflight_status": selected_run.get("validate_preflight_status"),
        "final_live_preflight_status": selected_run.get("final_live_preflight_status"),
        "submit_status": selected_run.get("submit_status"),
        "live_order_submission_occurred": selected_run.get("live_order_submission_occurred"),
        "external_order_id": selected_run.get("external_order_id"),
        "latest_live_execution": selected_run.get("latest_live_execution"),
        "why_it_matters": "This run preserves a local trail from signal to risk decision to trade intent, order lifecycle, receipt artifact, and final outcome for easier audit and judging.",
    }


def build_agent_identity_summary(settings: Any, mode_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": getattr(settings, "agent_id", "unknown"),
        "agent_name": getattr(settings, "agent_name", "unknown"),
        "version": getattr(settings, "agent_version", "unknown"),
        "capabilities": list(getattr(settings, "agent_capabilities", ())),
        "market_data_mode": mode_summary.get("effective_market_data_mode"),
        "execution_mode": mode_summary.get("effective_execution_mode"),
        "market_data_provider": mode_summary.get("market_data_provider"),
        "market_data_status": mode_summary.get("market_data_status"),
        "requested_kraken_backend": mode_summary.get("requested_kraken_backend"),
        "effective_kraken_backend": mode_summary.get("effective_kraken_backend"),
        "kraken_cli_status": mode_summary.get("kraken_cli_status"),
        "execution_provider": mode_summary.get("execution_provider"),
        "execution_status": mode_summary.get("execution_status"),
        "requested_kraken_execution_mode": mode_summary.get("requested_kraken_execution_mode"),
        "effective_kraken_execution_mode": mode_summary.get("effective_kraken_execution_mode"),
        "live_readiness_status": mode_summary.get("live_readiness_status"),
        "auth_test_status": mode_summary.get("auth_test_status"),
        "validate_preflight_status": mode_summary.get("validate_preflight_status"),
        "final_live_preflight_status": mode_summary.get("final_live_preflight_status"),
        "submit_status": mode_summary.get("submit_status"),
        "live_order_submission_occurred": mode_summary.get("live_order_submission_occurred"),
        "external_order_id": mode_summary.get("external_order_id"),
        "scope": "local-only",
    }


def build_trust_readiness_summary(
    artifact_row: dict[str, Any] | None,
    linked_trade_row: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not artifact_row:
        return None
    payload = _loads_json(artifact_row.get("payload_json"))
    readiness = payload.get("validation_readiness", {})
    checks = dict(readiness.get("checks", {}))
    if linked_trade_row is not None:
        checks["has_execution_outcome_linkage"] = True
    passed = sum(1 for value in checks.values() if value)
    total = len(checks) if checks else 0
    return {
        "profile": readiness.get("profile", "local-erc8004-readiness"),
        "checks": checks,
        "ready_checks_passed": passed,
        "ready_checks_total": total,
        "summary": readiness.get(
            "summary",
            "Locally structured for future ERC-8004-style validation; no on-chain publishing exists in v0.",
        ),
    }


def build_decision_chains(
    signal_rows: list[dict[str, Any]],
    blocked_trade_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    signals = list(signal_rows)
    trade_intents: dict[str, dict[str, Any]] = {}
    receipts_by_trade_intent: dict[str, dict[str, Any]] = {}
    for row in artifact_rows:
        payload = _loads_json(row.get("payload_json"))
        if row.get("artifact_type") == "ExecutionReceipt":
            trade_intent_id = payload.get("trade_intent_artifact_id")
            if trade_intent_id:
                receipts_by_trade_intent[trade_intent_id] = row
        elif row.get("id"):
            trade_intents[row["id"]] = row

    orders_by_artifact_id: dict[str, dict[str, Any]] = {}
    orders_by_order_id: dict[str, dict[str, Any]] = {}
    for row in order_rows or []:
        if row.get("artifact_id"):
            orders_by_artifact_id[row["artifact_id"]] = row
        if row.get("id"):
            orders_by_order_id[row["id"]] = row

    chains: list[dict[str, Any]] = []
    for row in trade_rows:
        artifact = trade_intents.get(row.get("artifact_id"))
        artifact_payload = _loads_json(artifact.get("payload_json")) if artifact else {}
        receipt = receipts_by_trade_intent.get(row.get("artifact_id"))
        receipt_payload = _loads_json(receipt.get("payload_json")) if receipt else {}
        order = orders_by_order_id.get(row.get("order_id")) or orders_by_artifact_id.get(row.get("artifact_id"))
        matched_signal = _match_signal(
            signals=signals,
            symbol=row.get("symbol"),
            reason=row.get("reason"),
            ts=row.get("ts"),
        )
        chains.append(
            {
                "ts": row.get("ts"),
                "symbol": row.get("symbol"),
                "action": row.get("side"),
                "outcome": "EXECUTED",
                "signal_reason": row.get("reason"),
                "signal": _signal_summary(matched_signal),
                "risk": {
                    "allowed": True,
                    "summary": artifact_payload.get("risk", {}).get("summary", "ALLOWED"),
                    "reason_codes": artifact_payload.get("risk", {}).get("reason_codes", []),
                },
                "trade_intent": _artifact_summary(artifact),
                "artifact": _artifact_summary(artifact),
                "order": _order_summary(order),
                "receipt": _receipt_summary(receipt),
                "execution": {
                    "status": row.get("status", "FILLED"),
                    "quantity": row.get("quantity"),
                    "price": row.get("price"),
                    "notional": row.get("notional"),
                    "pnl": row.get("pnl"),
                    "artifact_id": row.get("artifact_id"),
                    "order_id": row.get("order_id"),
                    "execution_provider": row.get("execution_provider"),
                    "receipt_id": receipt.get("id") if receipt else None,
                    "execution_mode": receipt_payload.get("execution", {}).get("effective_execution_mode"),
                    "requested_kraken_execution_mode": receipt_payload.get("execution", {}).get("requested_kraken_execution_mode"),
                    "effective_kraken_execution_mode": receipt_payload.get("execution", {}).get("effective_kraken_execution_mode"),
                },
            }
        )

    traded_order_ids = {row.get("order_id") for row in trade_rows if row.get("order_id")}
    for row in order_rows or []:
        if row.get("id") in traded_order_ids:
            continue
        artifact = trade_intents.get(row.get("artifact_id"))
        artifact_payload = _loads_json(artifact.get("payload_json")) if artifact else {}
        receipt = receipts_by_trade_intent.get(row.get("artifact_id"))
        receipt_payload = _loads_json(receipt.get("payload_json")) if receipt else {}
        matched_signal = _match_signal(
            signals=signals,
            symbol=row.get("symbol"),
            reason=artifact_payload.get("reason"),
            ts=row.get("ts"),
        )
        chains.append(
            {
                "ts": row.get("ts"),
                "symbol": row.get("symbol"),
                "action": row.get("side"),
                "outcome": _order_only_outcome_label(row.get("status")),
                "signal_reason": artifact_payload.get("reason") or row.get("notes"),
                "signal": _signal_summary(matched_signal),
                "risk": {
                    "allowed": artifact_payload.get("risk", {}).get("allowed"),
                    "summary": artifact_payload.get("risk", {}).get("summary"),
                    "reason_codes": artifact_payload.get("risk", {}).get("reason_codes", []),
                },
                "trade_intent": _artifact_summary(artifact),
                "artifact": _artifact_summary(artifact),
                "order": _order_summary(row),
                "receipt": _receipt_summary(receipt),
                "execution": {
                    "status": row.get("status"),
                    "quantity": row.get("quantity"),
                    "price": artifact_payload.get("price"),
                    "notional": _safe_notional(row.get("quantity"), artifact_payload.get("price")),
                    "pnl": None,
                    "artifact_id": row.get("artifact_id"),
                    "order_id": row.get("id"),
                    "execution_provider": row.get("execution_provider"),
                    "receipt_id": receipt.get("id") if receipt else None,
                    "execution_mode": receipt_payload.get("execution", {}).get("effective_execution_mode"),
                    "requested_kraken_execution_mode": receipt_payload.get("execution", {}).get("requested_kraken_execution_mode"),
                    "effective_kraken_execution_mode": receipt_payload.get("execution", {}).get("effective_kraken_execution_mode"),
                    "auth_test_status": receipt_payload.get("execution", {}).get("auth_test_status"),
                    "validate_preflight_status": receipt_payload.get("execution", {}).get("validate_preflight_status"),
                    "live_preflight_status": receipt_payload.get("execution", {}).get("live_preflight_status"),
                    "submit_status": receipt_payload.get("execution", {}).get("submit_status"),
                    "submit_attempted": receipt_payload.get("execution", {}).get("submit_attempted"),
                    "live_order_submission_occurred": receipt_payload.get("execution", {}).get("live_order_submission_occurred"),
                    "fill_state": receipt_payload.get("execution", {}).get("fill_state"),
                    "external_order_id": receipt_payload.get("execution", {}).get("external_order_id") or row.get("external_order_id"),
                    "no_live_submit_performed": receipt_payload.get("no_live_submit_performed", True),
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
                "trade_intent": {
                    "created": bool(context.get("artifact_id")),
                    "artifact_id": context.get("artifact_id"),
                    "summary": "Trade intent exists but execution was blocked." if context.get("artifact_id") else "No artifact created because the risk or execution gate blocked the decision.",
                },
                "artifact": {
                    "created": False,
                    "summary": "No execution receipt exists because execution did not proceed.",
                },
                "order": {
                    "created": False,
                    "status": context.get("execution_status"),
                    "execution_provider": context.get("execution_provider"),
                    "summary": "Order was not created.",
                },
                "receipt": {
                    "created": False,
                    "summary": "Execution receipt unavailable because the order never proceeded.",
                },
                "execution": {
                    "status": row.get("block_reason"),
                    "quantity": row.get("attempted_quantity"),
                    "price": row.get("attempted_price"),
                    "notional": _safe_notional(row.get("attempted_quantity"), row.get("attempted_price")),
                    "pnl": None,
                    "artifact_id": context.get("artifact_id"),
                    "order_id": None,
                    "execution_provider": context.get("execution_provider"),
                    "receipt_id": None,
                    "execution_mode": context.get("execution_status"),
                    "requested_kraken_execution_mode": _safe_get(context, "live_readiness", "requested_kraken_execution_mode"),
                    "effective_kraken_execution_mode": None,
                },
            }
        )

    chains.sort(key=lambda row: _parse_ts(row.get("ts")), reverse=True)
    return chains[:limit]


def format_decision_chain_summary(chain: dict[str, Any]) -> dict[str, Any]:
    signal = chain.get("signal", {})
    risk = chain.get("risk", {})
    artifact = chain.get("trade_intent", chain.get("artifact", {}))
    order = chain.get("order", {})
    receipt = chain.get("receipt", {})
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
        "artifact_agent_name": artifact.get("agent_name"),
        "artifact_readiness": artifact.get("readiness"),
        "artifact_market_data_provider": artifact.get("market_data_provider"),
        "artifact_market_data_backend": artifact.get("kraken_backend"),
        "artifact_market_data_status": artifact.get("market_data_status"),
        "artifact_kraken_cli_status": artifact.get("kraken_cli_status"),
        "order_id": order.get("order_id"),
        "order_status": order.get("status"),
        "order_provider": order.get("execution_provider"),
        "receipt_id": receipt.get("artifact_id"),
        "receipt_status": receipt.get("status"),
        "auth_test_status": execution.get("auth_test_status"),
        "validate_preflight_status": execution.get("validate_preflight_status"),
        "live_preflight_status": execution.get("live_preflight_status"),
        "submit_status": execution.get("submit_status"),
        "fill_state": execution.get("fill_state"),
        "external_order_id": execution.get("external_order_id"),
        "no_live_submit_performed": execution.get("no_live_submit_performed"),
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
            "market_backend": chain.get("trade_intent", {}).get("kraken_backend") or chain.get("artifact", {}).get("kraken_backend") or "mock",
            "artifact": chain.get("trade_intent", {}).get("artifact_id") or chain.get("artifact", {}).get("artifact_id"),
            "order_id": chain.get("order", {}).get("order_id"),
            "receipt_id": chain.get("receipt", {}).get("artifact_id"),
            "trade_status": chain.get("execution", {}).get("status"),
            "auth_test_status": chain.get("execution", {}).get("auth_test_status"),
            "validate_preflight_status": chain.get("execution", {}).get("validate_preflight_status"),
            "submit_status": chain.get("execution", {}).get("submit_status"),
            "fill_state": chain.get("execution", {}).get("fill_state"),
        }
        for chain in chains
    ]


def format_selected_run_caption(selected_run: dict[str, Any] | None) -> str:
    if not selected_run:
        return "No run selected."
    return (
        f"Selected run {selected_run['run_id_short']} at {selected_run['ts']}. "
        "Views below are scoped to this run where reconstruction is reliable."
    )


def scope_records_to_run(
    run_history_rows: list[dict[str, Any]],
    selected_run_id: str,
    signal_rows: list[dict[str, Any]],
    blocked_trade_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]] | None = None,
    decision_chain_limit: int = 5,
) -> dict[str, Any]:
    selected_run = next((row for row in run_history_rows if row.get("run_id") == selected_run_id), None)
    if selected_run is None:
        return {
            "selected_run": None,
            "signals": [],
            "blocked_trades": [],
            "trades": [],
            "orders": [],
            "artifacts": [],
            "decision_chains": [],
            "latest_artifact": None,
        }

    start_ts, end_ts = _run_time_window(run_history_rows, selected_run_id)
    scoped_artifacts = _scope_artifacts_to_run(artifact_rows, selected_run_id, start_ts, end_ts)
    artifact_ids = {row.get("id") for row in scoped_artifacts if row.get("id")}
    scoped_trades = _scope_trades_to_run(trade_rows, artifact_ids, start_ts, end_ts)
    scoped_orders = _scope_orders_to_run(order_rows or [], artifact_ids, start_ts, end_ts)
    scoped_blocked = _filter_rows_by_time_window(blocked_trade_rows, start_ts, end_ts)
    scoped_signals = _filter_rows_by_time_window(signal_rows, start_ts, end_ts)
    scoped_chains = build_decision_chains(
        signal_rows=scoped_signals,
        blocked_trade_rows=scoped_blocked,
        trade_rows=scoped_trades,
        artifact_rows=scoped_artifacts,
        order_rows=scoped_orders,
        limit=decision_chain_limit,
    )
    return {
        "selected_run": selected_run,
        "signals": scoped_signals,
        "blocked_trades": scoped_blocked,
        "trades": scoped_trades,
        "orders": scoped_orders,
        "artifacts": scoped_artifacts,
        "decision_chains": scoped_chains,
        "latest_artifact": scoped_artifacts[0] if scoped_artifacts else None,
        "scoping_note": "Best-effort run scoping uses artifact run_id when available and timestamp windows for related signals, orders, and blocked trades.",
    }


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


def _run_time_window(run_history_rows: list[dict[str, Any]], selected_run_id: str) -> tuple[datetime | None, datetime]:
    selected_index = next(
        (index for index, row in enumerate(run_history_rows) if row.get("run_id") == selected_run_id),
        None,
    )
    if selected_index is None:
        return None, datetime.min
    selected_run = run_history_rows[selected_index]
    end_ts = _parse_ts(selected_run.get("ts"))
    older_run = run_history_rows[selected_index + 1] if selected_index + 1 < len(run_history_rows) else None
    start_ts = _parse_ts(older_run.get("ts")) if older_run else None
    return start_ts, end_ts


def _filter_rows_by_time_window(
    rows: list[dict[str, Any]],
    start_ts: datetime | None,
    end_ts: datetime,
) -> list[dict[str, Any]]:
    filtered = []
    for row in rows:
        row_ts = _parse_ts(row.get("ts"))
        if row_ts <= end_ts and (start_ts is None or row_ts > start_ts):
            filtered.append(row)
    return filtered


def _scope_artifacts_to_run(
    artifact_rows: list[dict[str, Any]],
    run_id: str,
    start_ts: datetime | None,
    end_ts: datetime,
) -> list[dict[str, Any]]:
    matched = []
    fallback = []
    for row in artifact_rows:
        payload = _loads_json(row.get("payload_json"))
        row_ts = _parse_ts(row.get("ts"))
        if payload.get("run_id") == run_id:
            matched.append(row)
        elif row_ts <= end_ts and (start_ts is None or row_ts > start_ts):
            fallback.append(row)
    rows = matched if matched else fallback
    rows.sort(key=lambda row: _parse_ts(row.get("ts")), reverse=True)
    return rows


def _scope_trades_to_run(
    trade_rows: list[dict[str, Any]],
    artifact_ids: set[Any],
    start_ts: datetime | None,
    end_ts: datetime,
) -> list[dict[str, Any]]:
    matched = []
    fallback = []
    for row in trade_rows:
        row_ts = _parse_ts(row.get("ts"))
        if row.get("artifact_id") in artifact_ids and row.get("artifact_id") is not None:
            matched.append(row)
        elif row_ts <= end_ts and (start_ts is None or row_ts > start_ts):
            fallback.append(row)
    rows = matched if matched else fallback
    rows.sort(key=lambda row: _parse_ts(row.get("ts")), reverse=True)
    return rows


def _scope_orders_to_run(
    order_rows: list[dict[str, Any]],
    artifact_ids: set[Any],
    start_ts: datetime | None,
    end_ts: datetime,
) -> list[dict[str, Any]]:
    matched = []
    fallback = []
    for row in order_rows:
        row_ts = _parse_ts(row.get("ts"))
        if row.get("artifact_id") in artifact_ids and row.get("artifact_id") is not None:
            matched.append(row)
        elif row_ts <= end_ts and (start_ts is None or row_ts > start_ts):
            fallback.append(row)
    rows = matched if matched else fallback
    rows.sort(key=lambda row: _parse_ts(row.get("ts")), reverse=True)
    return rows


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
    payload = _loads_json(row.get("payload_json"))
    readiness = payload.get("validation_readiness", {})
    market_data = payload.get("market_data", {})
    return {
        "created": True,
        "artifact_id": row.get("id"),
        "type": row.get("artifact_type"),
        "path": row.get("path"),
        "hash": str(row.get("hash_or_digest", ""))[:16],
        "agent_name": payload.get("agent", {}).get("agent_name"),
        "market_data_provider": market_data.get("provider"),
        "kraken_backend": market_data.get("backend"),
        "market_data_status": market_data.get("status"),
        "kraken_cli_status": market_data.get("kraken_cli_status"),
        "readiness": _readiness_badge(readiness),
        "summary": "TradeIntent artifact created before execution.",
    }


def _order_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"created": False, "summary": "No order recorded for this decision."}
    return {
        "created": True,
        "order_id": row.get("id"),
        "status": row.get("status"),
        "execution_provider": row.get("execution_provider"),
        "execution_mode": row.get("execution_mode"),
        "external_order_id": row.get("external_order_id"),
        "summary": "Local order lifecycle entry created.",
    }


def _receipt_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"created": False, "summary": "No execution receipt linked to this decision."}
    payload = _loads_json(row.get("payload_json"))
    execution = payload.get("execution", {})
    return {
        "created": True,
        "artifact_id": row.get("id"),
        "status": execution.get("status"),
        "execution_provider": execution.get("execution_provider"),
        "execution_mode": execution.get("effective_execution_mode"),
        "summary": "Execution receipt artifact saved after order persistence.",
        "auth_test_status": execution.get("auth_test_status"),
        "validate_preflight_status": execution.get("validate_preflight_status"),
        "live_preflight_status": execution.get("live_preflight_status"),
        "submit_status": execution.get("submit_status"),
        "fill_state": execution.get("fill_state"),
        "external_order_id": execution.get("external_order_id"),
        "no_live_submit_performed": payload.get("no_live_submit_performed", True),
        "receipt_status": payload.get("receipt_status"),
    }


def _order_only_outcome_label(status: str | None) -> str:
    normalized = str(status or "").upper()
    if normalized.startswith("SUBMITTED"):
        return "SUBMITTED"
    if normalized.startswith("PREFLIGHT"):
        return "PREFLIGHT"
    if normalized == "BLOCKED":
        return "BLOCKED"
    return "ORDER_ONLY"
