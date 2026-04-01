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
            "auth_test_status": outcome.auth_test_status,
            "validate_preflight_status": outcome.validate_preflight_status,
            "live_preflight_status": outcome.live_preflight_status,
            "submit_attempted": _submit_attempted_for_outcome(outcome),
            "submit_status": _submit_status_for_outcome(outcome),
            "live_order_submission_occurred": _live_submission_occurred(outcome),
            "fill_state": _fill_state_for_outcome(outcome, persisted),
            "filled_quantity": persisted.get("filled_quantity", outcome.filled_quantity),
            "fill_price": persisted.get("fill_price", outcome.fill_price),
            "pnl": persisted.get("pnl"),
            "provider_metadata": outcome.provider_metadata,
        },
        "safety_snapshot": safety_snapshot,
        "modes": mode_summary,
        "receipt_status": _receipt_status_for_outcome(outcome, persisted),
        "notes": (
            "Execution receipt linking the trade intent to the local order lifecycle. "
            "For Kraken live execution, this artifact records whether the flow stopped at preflight, "
            "was blocked, or submitted a real order. Fill state remains explicit when unknown."
        ),
        "no_live_submit_performed": not _live_submission_occurred(outcome),
    }
    payload["validation_readiness"] = build_validation_readiness(
        payload,
        has_execution_outcome_linkage=True,
    )
    return payload


def _receipt_status_for_outcome(outcome: ExecutionOutcome, persisted: dict[str, Any]) -> str:
    if outcome.status == "BLOCKED":
        return "blocked"
    if outcome.status == "PREFLIGHT_PASSED":
        return "preflight_passed"
    if outcome.status == "PREFLIGHT_FAILED":
        return "preflight_failed"
    if outcome.status == "LIVE_SUBMIT_FAILED":
        return "live_submit_failed"
    if outcome.status == "SUBMITTED_FILL_UNKNOWN":
        return "fill_unknown"
    if outcome.status == "SUBMITTED_WITH_FILL" or persisted.get("trade_id"):
        return "fill_recorded"
    return "live_submitted"


def _submit_status_for_outcome(outcome: ExecutionOutcome) -> str:
    if outcome.submit_status:
        return outcome.submit_status
    if outcome.status in {"SUBMITTED_WITH_FILL", "SUBMITTED_FILL_UNKNOWN"}:
        return "live_submitted"
    if outcome.status == "LIVE_SUBMIT_FAILED":
        return "live_submit_failed"
    if outcome.status in {"PREFLIGHT_PASSED", "PREFLIGHT_FAILED", "BLOCKED"}:
        return "preflight_only"
    return "unknown"


def _fill_state_for_outcome(outcome: ExecutionOutcome, persisted: dict[str, Any]) -> str:
    if outcome.fill_state:
        return outcome.fill_state
    if persisted.get("trade_id") or outcome.status == "SUBMITTED_WITH_FILL":
        return "fill_recorded"
    if outcome.status == "SUBMITTED_FILL_UNKNOWN":
        return "fill_unknown"
    return "not_submitted"


def _submit_attempted_for_outcome(outcome: ExecutionOutcome) -> bool:
    if outcome.submit_attempted is not None:
        return outcome.submit_attempted
    return bool(outcome.provider_metadata.get("submit_attempted"))


def _live_submission_occurred(outcome: ExecutionOutcome) -> bool:
    if outcome.live_order_submission_occurred is not None:
        return outcome.live_order_submission_occurred
    return not bool(outcome.provider_metadata.get("no_live_submit_performed", False))
