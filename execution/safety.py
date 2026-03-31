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


def build_live_readiness_snapshot(
    settings: Settings,
    requested_execution_mode: str,
    requested_kraken_execution_mode: str | None,
) -> dict[str, Any]:
    checks = {
        "kill_switch_clear": not settings.kill_switch,
        "live_toggle_enabled": bool(settings.enable_kraken_live),
        "typed_confirmation_configured": bool(settings.kraken_live_confirmation_text.strip()),
        "validate_required": bool(settings.kraken_live_require_validate),
        "max_notional_per_order_configured": settings.kraken_live_max_notional_per_order > 0,
        "max_daily_notional_configured": settings.kraken_live_max_daily_notional > 0,
        "max_orders_per_cycle_configured": settings.kraken_live_max_orders_per_cycle > 0,
        "milestone_live_submit_enabled": False,
    }

    if requested_execution_mode != EXECUTION_MODE_KRAKEN:
        return {
            "status": LIVE_READINESS_STATUS_INTERNAL_PAPER,
            "requested_live": False,
            "requested_execution_mode": requested_execution_mode,
            "requested_kraken_execution_mode": requested_kraken_execution_mode,
            "summary": "Internal paper execution is the safe default.",
            "checks": checks,
            "caps": _live_caps(settings),
        }

    if requested_kraken_execution_mode == KRAKEN_EXECUTION_MODE_PAPER:
        return {
            "status": LIVE_READINESS_STATUS_KRAKEN_PAPER,
            "requested_live": False,
            "requested_execution_mode": requested_execution_mode,
            "requested_kraken_execution_mode": requested_kraken_execution_mode,
            "summary": "Kraken CLI paper execution is a simulation path. Live execution remains disabled in this milestone.",
            "checks": checks,
            "caps": _live_caps(settings),
        }

    if settings.kill_switch:
        return {
            "status": LIVE_READINESS_STATUS_BLOCKED_KILL_SWITCH,
            "requested_live": requested_kraken_execution_mode == KRAKEN_EXECUTION_MODE_LIVE,
            "requested_execution_mode": requested_execution_mode,
            "requested_kraken_execution_mode": requested_kraken_execution_mode,
            "summary": "Global kill switch is active. Kraken live execution is blocked.",
            "checks": checks,
            "caps": _live_caps(settings),
        }

    return {
        "status": LIVE_READINESS_STATUS_BLOCKED_DISABLED,
        "requested_live": requested_kraken_execution_mode == KRAKEN_EXECUTION_MODE_LIVE,
        "requested_execution_mode": requested_execution_mode,
        "requested_kraken_execution_mode": requested_kraken_execution_mode,
        "summary": "Kraken live execution is planned and guarded, but disabled in this milestone.",
        "checks": checks,
        "caps": _live_caps(settings),
    }


def live_execution_is_blocked(readiness: dict[str, Any]) -> bool:
    return bool(readiness.get("requested_live")) and readiness.get("status") not in {
        LIVE_READINESS_STATUS_INTERNAL_PAPER,
        LIVE_READINESS_STATUS_KRAKEN_PAPER,
    }


def _live_caps(settings: Settings) -> dict[str, float | int | str]:
    return {
        "max_notional_per_order": settings.kraken_live_max_notional_per_order,
        "max_daily_notional": settings.kraken_live_max_daily_notional,
        "max_orders_per_cycle": settings.kraken_live_max_orders_per_cycle,
        "confirmation_text": settings.kraken_live_confirmation_text,
    }
