from __future__ import annotations

from typing import Any
from uuid import uuid4

from models import RiskDecision, Signal, utc_now_iso
from proof.agent_identity import build_validation_readiness


def build_trade_intent(
    run_id: str,
    signal: Signal,
    risk_decision: RiskDecision,
    quantity: float,
    price: float,
    latest_price: float,
    mode_summary: dict[str, Any],
    agent_identity: dict[str, Any],
) -> dict[str, Any]:
    observed_at = utc_now_iso()
    effective_execution_mode = str(mode_summary.get("effective_execution_mode", "paper"))
    payload = {
        "artifact_id": str(uuid4()),
        "artifact_type": "TradeIntent",
        "schema_version": "v0",
        "created_at": utc_now_iso(),
        "timestamp": observed_at,
        "run_id": run_id,
        "mode": effective_execution_mode,
        "executor": effective_execution_mode,
        "agent": agent_identity,
        "symbol": signal.symbol,
        "side": signal.action,
        "action": signal.action,
        "quantity": round(quantity, 6),
        "price": round(price, 6),
        "notional": round(quantity * price, 6),
        "reason": signal.reason,
        "signal": {
            "id": signal.id,
            "reason": signal.reason,
            "indicators": signal.indicators,
            "should_execute": signal.should_execute,
        },
        "risk": {
            "allowed": risk_decision.allowed,
            "reason_codes": risk_decision.reason_codes,
            "summary": risk_decision.summary(),
        },
        "market_snapshot": {
            "latest_price": round(latest_price, 6),
            "observed_at": observed_at,
        },
        "market_data": {
            "provider": mode_summary.get("market_data_provider"),
            "backend": mode_summary.get("effective_kraken_backend"),
            "status": mode_summary.get("market_data_status"),
            "kraken_cli_status": mode_summary.get("kraken_cli_status"),
            "source_type": mode_summary.get("market_data_source_type"),
            "ohlc_interval_minutes": mode_summary.get("kraken_ohlc_interval_minutes"),
            "history_length": mode_summary.get("kraken_history_length"),
            "requested_kraken_backend": mode_summary.get("requested_kraken_backend"),
            "requested_market_data_mode": mode_summary.get("requested_market_data_mode"),
            "effective_market_data_mode": mode_summary.get("effective_market_data_mode"),
            "requested_execution_mode": mode_summary.get("requested_execution_mode"),
            "effective_execution_mode": mode_summary.get("effective_execution_mode"),
            "observed_at": observed_at,
        },
        "modes": mode_summary,
    }
    payload["validation_readiness"] = build_validation_readiness(payload, has_execution_outcome_linkage=False)
    return payload
