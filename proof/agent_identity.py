from __future__ import annotations

from typing import Any

from config import Settings
from models import utc_now_iso


def build_agent_identity(settings: Settings, mode_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": settings.agent_id,
        "agent_name": settings.agent_name,
        "version": settings.agent_version,
        "capabilities": list(settings.agent_capabilities),
        "execution_mode": mode_summary.get("effective_execution_mode"),
        "market_data_mode": mode_summary.get("effective_market_data_mode"),
        "requested_modes": {
            "market_data_mode": mode_summary.get("requested_market_data_mode"),
            "execution_mode": mode_summary.get("requested_execution_mode"),
        },
        "effective_modes": {
            "market_data_mode": mode_summary.get("effective_market_data_mode"),
            "execution_mode": mode_summary.get("effective_execution_mode"),
        },
        "identity_scope": "local",
        "declared_at": utc_now_iso(),
    }


def build_validation_readiness(
    payload: dict[str, Any],
    has_execution_outcome_linkage: bool = False,
) -> dict[str, Any]:
    checks = {
        "has_agent_identity": bool(payload.get("agent")),
        "has_signal_context": bool(payload.get("signal", {}).get("indicators")) and bool(payload.get("signal", {}).get("reason")),
        "has_risk_decision": "allowed" in payload.get("risk", {}) and "summary" in payload.get("risk", {}),
        "has_mode_metadata": bool(payload.get("modes")),
        "has_run_id": bool(payload.get("run_id")),
        "has_execution_outcome_linkage": has_execution_outcome_linkage,
    }
    passed = sum(1 for value in checks.values() if value)
    total = len(checks)
    return {
        "profile": "local-erc8004-readiness",
        "checks": checks,
        "ready_checks_passed": passed,
        "ready_checks_total": total,
        "summary": (
            "Locally structured for future ERC-8004-style validation and trust workflows; "
            "no on-chain publishing or signing is performed in v0."
        ),
    }
