from __future__ import annotations

from typing import Any
from uuid import uuid4

from models import ExecutionOutcome, utc_now_iso
from proof.agent_identity import build_validation_readiness


def build_execution_receipt(
    run_id: str,
    symbol: str,
    trade_intent_artifact_id: str,
    outcome: ExecutionOutcome,
    persisted: dict[str, Any],
    mode_summary: dict[str, Any],
    agent_identity: dict[str, Any],
    safety_snapshot: dict[str, Any],
) -> dict[str, Any]:
    observed_at = utc_now_iso()
    payload = {
        "artifact_id": str(uuid4()),
        "artifact_type": "ExecutionReceipt",
        "schema_version": "v0",
        "created_at": observed_at,
        "timestamp": observed_at,
        "run_id": run_id,
        "symbol": symbol,
        "trade_intent_artifact_id": trade_intent_artifact_id,
        "agent": agent_identity,
        "execution": {
            "local_order_id": outcome.local_order_id,
            "trade_id": persisted.get("trade_id"),
            "external_order_id": outcome.external_order_id,
            "external_status": outcome.external_status,
            "execution_provider": outcome.execution_provider,
            "execution_source_type": outcome.execution_source_type,
            "requested_execution_mode": outcome.requested_execution_mode,
            "effective_execution_mode": outcome.effective_execution_mode,
            "requested_kraken_execution_mode": outcome.requested_kraken_execution_mode,
            "effective_kraken_execution_mode": outcome.effective_kraken_execution_mode,
            "status": persisted.get("status", outcome.status),
            "filled_quantity": persisted.get("filled_quantity", outcome.filled_quantity),
            "fill_price": persisted.get("fill_price", outcome.fill_price),
            "pnl": persisted.get("pnl"),
            "provider_metadata": outcome.provider_metadata,
        },
        "safety_snapshot": safety_snapshot,
        "modes": mode_summary,
        "notes": "Post-execution receipt linking the trade intent to the local order lifecycle.",
    }
    payload["validation_readiness"] = build_validation_readiness(
        payload,
        has_execution_outcome_linkage=True,
    )
    return payload
