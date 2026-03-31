from __future__ import annotations

from typing import Any
from uuid import uuid4

from models import RiskDecision, Signal, utc_now_iso


def build_trade_intent(
    run_id: str,
    signal: Signal,
    risk_decision: RiskDecision,
    quantity: float,
    price: float,
    latest_price: float,
    mode_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_id": str(uuid4()),
        "artifact_type": "TradeIntent",
        "schema_version": "v0",
        "created_at": utc_now_iso(),
        "run_id": run_id,
        "mode": "paper",
        "executor": "paper",
        "symbol": signal.symbol,
        "side": signal.action,
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
        },
        "market_snapshot": {
            "latest_price": round(latest_price, 6),
        },
        "modes": mode_summary,
    }
