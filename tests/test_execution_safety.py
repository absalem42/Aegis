from config import (
    EXECUTION_MODE_KRAKEN,
    EXECUTION_MODE_PAPER,
    KRAKEN_EXECUTION_MODE_LIVE,
    KRAKEN_EXECUTION_MODE_PAPER,
    Settings,
)
from execution.safety import (
    LIVE_READINESS_STATUS_BLOCKED_DISABLED,
    LIVE_READINESS_STATUS_BLOCKED_KILL_SWITCH,
    LIVE_READINESS_STATUS_INTERNAL_PAPER,
    LIVE_READINESS_STATUS_KRAKEN_PAPER,
    build_live_readiness_snapshot,
    live_execution_is_blocked,
)


def test_live_readiness_defaults_to_internal_paper_safe_mode():
    settings = Settings()

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_PAPER,
        requested_kraken_execution_mode=None,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_INTERNAL_PAPER
    assert readiness["requested_live"] is False
    assert readiness["checks"]["kill_switch_clear"] is True


def test_live_readiness_marks_kraken_paper_as_simulation():
    settings = Settings(execution_mode=EXECUTION_MODE_KRAKEN)

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_KRAKEN,
        requested_kraken_execution_mode=KRAKEN_EXECUTION_MODE_PAPER,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_KRAKEN_PAPER
    assert readiness["requested_live"] is False
    assert live_execution_is_blocked(readiness) is False


def test_live_readiness_blocks_live_by_default():
    settings = Settings(execution_mode=EXECUTION_MODE_KRAKEN)

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_KRAKEN,
        requested_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_BLOCKED_DISABLED
    assert readiness["requested_live"] is True
    assert readiness["caps"]["max_notional_per_order"] == settings.kraken_live_max_notional_per_order
    assert live_execution_is_blocked(readiness) is True


def test_live_readiness_honors_kill_switch():
    settings = Settings(
        execution_mode=EXECUTION_MODE_KRAKEN,
        kill_switch=True,
    )

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_KRAKEN,
        requested_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_BLOCKED_KILL_SWITCH
    assert readiness["checks"]["kill_switch_clear"] is False
