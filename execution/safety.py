from __future__ import annotations

from typing import Any

from config import (
    EXECUTION_MODE_KRAKEN,
    KRAKEN_EXECUTION_MODE_LIVE,
    KRAKEN_EXECUTION_MODE_PAPER,
    Settings,
)

LIVE_READINESS_STATUS_INTERNAL_PAPER = "INTERNAL_PAPER_ACTIVE"
LIVE_READINESS_STATUS_KRAKEN_PAPER = "KRAKEN_PAPER_ACTIVE"
LIVE_READINESS_STATUS_BLOCKED_DISABLED = "BLOCKED_DISABLED"
LIVE_READINESS_STATUS_BLOCKED_KILL_SWITCH = "BLOCKED_KILL_SWITCH"
LIVE_READINESS_STATUS_BLOCKED_GATES = "BLOCKED_GATES"
LIVE_READINESS_STATUS_PREFLIGHT_READY = "PREFLIGHT_READY"
LIVE_READINESS_STATUS_PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
LIVE_READINESS_STATUS_PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
LIVE_READINESS_STATUS_SUBMIT_READY = "SUBMIT_READY"


def build_live_readiness_snapshot(
    settings: Settings,
    requested_execution_mode: str,
    requested_kraken_execution_mode: str | None,
    *,
    candidate_symbol: str | None = None,
    candidate_notional: float | None = None,
    live_candidate_count: int | None = None,
    daily_live_notional: float | None = None,
) -> dict[str, Any]:
    confirmation_phrase = settings.kraken_live_confirmation_text.strip()
    confirmation_input = settings.session_live_confirmation_input.strip()
    confirmation_matches = bool(
        confirmation_phrase and confirmation_input and confirmation_input == confirmation_phrase
    )
    candidate_symbol_supported = candidate_symbol in settings.symbols if candidate_symbol else True
    submit_symbol_allowed = candidate_symbol in settings.kraken_live_allowed_symbols if candidate_symbol else True
    per_order_cap_configured = settings.kraken_live_max_notional_per_order > 0
    daily_cap_configured = settings.kraken_live_max_daily_notional > 0
    max_orders_configured = settings.kraken_live_max_orders_per_cycle > 0
    candidate_notional_within_cap = True
    daily_notional_within_cap = True
    live_candidate_limit_respected = True
    if candidate_notional is not None and per_order_cap_configured:
        candidate_notional_within_cap = candidate_notional <= settings.kraken_live_max_notional_per_order
    if candidate_notional is not None and daily_live_notional is not None and daily_cap_configured:
        daily_notional_within_cap = (
            daily_live_notional + candidate_notional <= settings.kraken_live_max_daily_notional
        )
    if live_candidate_count is not None and max_orders_configured:
        live_candidate_limit_respected = (
            live_candidate_count == 1 and live_candidate_count <= settings.kraken_live_max_orders_per_cycle
        )

    checks = {
        "kill_switch_clear": not settings.kill_switch,
        "live_toggle_enabled": bool(settings.enable_kraken_live),
        "per_session_opt_in": bool(settings.session_live_opt_in),
        "typed_confirmation_configured": bool(confirmation_phrase),
        "typed_confirmation_matches": confirmation_matches,
        "validate_required": bool(settings.kraken_live_require_validate),
        "live_submit_enabled": bool(settings.enable_kraken_live_submit),
        "session_submit_opt_in": bool(settings.session_live_submit_opt_in),
        "max_notional_per_order_configured": per_order_cap_configured,
        "max_daily_notional_configured": daily_cap_configured,
        "max_orders_per_cycle_configured": max_orders_configured,
        "candidate_symbol_supported": candidate_symbol_supported,
        "submit_symbol_allowed": submit_symbol_allowed,
        "candidate_notional_within_cap": candidate_notional_within_cap,
        "daily_notional_within_cap": daily_notional_within_cap,
        "live_candidate_limit_respected": live_candidate_limit_respected,
        "milestone_live_submit_enabled": bool(settings.enable_kraken_live_submit),
    }
    snapshot = {
        "requested_live": requested_kraken_execution_mode == KRAKEN_EXECUTION_MODE_LIVE,
        "requested_execution_mode": requested_execution_mode,
        "requested_kraken_execution_mode": requested_kraken_execution_mode,
        "checks": checks,
        "caps": _live_caps(settings),
        "candidate": {
            "symbol": candidate_symbol,
            "notional": candidate_notional,
            "live_candidate_count": live_candidate_count,
            "daily_live_notional": daily_live_notional,
        },
        "auth_test_status": None,
        "validate_preflight_status": None,
        "submit_attempted": False,
        "submit_status": None,
        "submit_ready": False,
        "preflight_ran": False,
        "no_live_submit_performed": True,
    }

    if requested_execution_mode != EXECUTION_MODE_KRAKEN:
        return {
            **snapshot,
            "status": LIVE_READINESS_STATUS_INTERNAL_PAPER,
            "summary": "Internal paper execution is the safe default.",
        }

    if requested_kraken_execution_mode == KRAKEN_EXECUTION_MODE_PAPER:
        return {
            **snapshot,
            "status": LIVE_READINESS_STATUS_KRAKEN_PAPER,
            "summary": "Kraken CLI paper execution is a simulation path. Live execution remains disabled in this milestone.",
        }

    if settings.kill_switch:
        return {
            **snapshot,
            "status": LIVE_READINESS_STATUS_BLOCKED_KILL_SWITCH,
            "summary": "Global kill switch is active. Kraken live execution is blocked.",
        }

    gate_order = (
        "live_toggle_enabled",
        "per_session_opt_in",
        "typed_confirmation_configured",
        "typed_confirmation_matches",
        "validate_required",
        "max_notional_per_order_configured",
        "max_daily_notional_configured",
        "max_orders_per_cycle_configured",
        "candidate_symbol_supported",
        "candidate_notional_within_cap",
        "daily_notional_within_cap",
        "live_candidate_limit_respected",
    )
    preflight_ready = all(checks.get(key) for key in gate_order)
    submit_gate_order = (
        *gate_order,
        "live_submit_enabled",
        "session_submit_opt_in",
        "submit_symbol_allowed",
    )
    submit_ready = all(checks.get(key) for key in submit_gate_order)
    if preflight_ready:
        return {
            **snapshot,
            "status": LIVE_READINESS_STATUS_SUBMIT_READY if submit_ready else LIVE_READINESS_STATUS_PREFLIGHT_READY,
            "submit_ready": submit_ready,
            "summary": (
                "Kraken live readiness and submit gates passed. Aegis may run auth, validate, and then a guarded live submit."
                if submit_ready
                else "Kraken live readiness gates passed. Aegis may run auth and validate preflight only; submit remains gated."
            ),
        }

    if not settings.enable_kraken_live:
        return {
            **snapshot,
            "status": LIVE_READINESS_STATUS_BLOCKED_DISABLED,
            "summary": "Kraken live execution is planned and guarded, but disabled in this milestone.",
        }

    return {
        **snapshot,
        "status": LIVE_READINESS_STATUS_BLOCKED_GATES,
        "summary": "Kraken live preflight is blocked until all session and safety gates pass.",
    }


def live_execution_is_blocked(readiness: dict[str, Any]) -> bool:
    return bool(readiness.get("requested_live")) and readiness.get("status") not in {
        LIVE_READINESS_STATUS_INTERNAL_PAPER,
        LIVE_READINESS_STATUS_KRAKEN_PAPER,
        LIVE_READINESS_STATUS_PREFLIGHT_READY,
        LIVE_READINESS_STATUS_PREFLIGHT_PASSED,
        LIVE_READINESS_STATUS_SUBMIT_READY,
    }


def live_preflight_can_run(readiness: dict[str, Any]) -> bool:
    return bool(readiness.get("requested_live")) and readiness.get("status") in {
        LIVE_READINESS_STATUS_PREFLIGHT_READY,
        LIVE_READINESS_STATUS_SUBMIT_READY,
    }


def live_submit_can_run(readiness: dict[str, Any]) -> bool:
    return bool(readiness.get("requested_live")) and bool(readiness.get("submit_ready"))


def _live_caps(settings: Settings) -> dict[str, float | int | str]:
    return {
        "max_notional_per_order": settings.kraken_live_max_notional_per_order,
        "max_daily_notional": settings.kraken_live_max_daily_notional,
        "max_orders_per_cycle": settings.kraken_live_max_orders_per_cycle,
        "confirmation_text": settings.kraken_live_confirmation_text,
        "allowed_symbols": list(settings.kraken_live_allowed_symbols),
    }
