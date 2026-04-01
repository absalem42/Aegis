from config import (
    EXECUTION_MODE_KRAKEN,
    EXECUTION_MODE_PAPER,
    KRAKEN_EXECUTION_MODE_LIVE,
    KRAKEN_EXECUTION_MODE_PAPER,
    Settings,
)
from execution.safety import (
    LIVE_READINESS_STATUS_BLOCKED_DISABLED,
    LIVE_READINESS_STATUS_BLOCKED_GATES,
    LIVE_READINESS_STATUS_BLOCKED_KILL_SWITCH,
    LIVE_READINESS_STATUS_INTERNAL_PAPER,
    LIVE_READINESS_STATUS_KRAKEN_PAPER,
    LIVE_READINESS_STATUS_PREFLIGHT_READY,
    LIVE_READINESS_STATUS_SUBMIT_READY,
    build_live_readiness_snapshot,
    live_execution_is_blocked,
    live_preflight_can_run,
    live_submit_can_run,
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


def test_live_readiness_requires_session_opt_in_and_confirmation():
    settings = Settings(
        execution_mode=EXECUTION_MODE_KRAKEN,
        enable_kraken_live=True,
    )

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_KRAKEN,
        requested_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        candidate_symbol="BTC/USD",
        candidate_notional=25.0,
        live_candidate_count=1,
        daily_live_notional=0.0,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_BLOCKED_GATES
    assert readiness["checks"]["per_session_opt_in"] is False
    assert readiness["checks"]["typed_confirmation_matches"] is False
    assert live_preflight_can_run(readiness) is False


def test_live_readiness_becomes_preflight_ready_when_all_gates_pass():
    settings = Settings(
        execution_mode=EXECUTION_MODE_KRAKEN,
        enable_kraken_live=True,
        session_live_opt_in=True,
        session_live_confirmation_input="ENABLE_LIVE_ORDERS",
    )

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_KRAKEN,
        requested_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        candidate_symbol="BTC/USD",
        candidate_notional=25.0,
        live_candidate_count=1,
        daily_live_notional=0.0,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_PREFLIGHT_READY
    assert readiness["checks"]["candidate_symbol_supported"] is True
    assert readiness["checks"]["candidate_notional_within_cap"] is True
    assert live_preflight_can_run(readiness) is True
    assert live_submit_can_run(readiness) is False


def test_live_readiness_requires_explicit_submit_gate_for_real_orders():
    settings = Settings(
        execution_mode=EXECUTION_MODE_KRAKEN,
        enable_kraken_live=True,
        enable_kraken_live_submit=True,
        session_live_opt_in=True,
        session_live_confirmation_input="ENABLE_LIVE_ORDERS",
        session_live_submit_opt_in=True,
    )

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_KRAKEN,
        requested_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        candidate_symbol="BTC/USD",
        candidate_notional=25.0,
        live_candidate_count=1,
        daily_live_notional=0.0,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_SUBMIT_READY
    assert readiness["checks"]["live_submit_enabled"] is True
    assert readiness["checks"]["session_submit_opt_in"] is True
    assert live_preflight_can_run(readiness) is True
    assert live_submit_can_run(readiness) is True


def test_live_readiness_blocks_submit_when_symbol_is_outside_allowlist():
    settings = Settings(
        execution_mode=EXECUTION_MODE_KRAKEN,
        enable_kraken_live=True,
        enable_kraken_live_submit=True,
        session_live_opt_in=True,
        session_live_confirmation_input="ENABLE_LIVE_ORDERS",
        session_live_submit_opt_in=True,
        kraken_live_allowed_symbols=("BTC/USD",),
    )

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_KRAKEN,
        requested_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        candidate_symbol="ETH/USD",
        candidate_notional=25.0,
        live_candidate_count=1,
        daily_live_notional=0.0,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_PREFLIGHT_READY
    assert readiness["checks"]["submit_symbol_allowed"] is False
    assert live_preflight_can_run(readiness) is True
    assert live_submit_can_run(readiness) is False


def test_live_readiness_blocks_when_notional_caps_are_exceeded():
    settings = Settings(
        execution_mode=EXECUTION_MODE_KRAKEN,
        enable_kraken_live=True,
        session_live_opt_in=True,
        session_live_confirmation_input="ENABLE_LIVE_ORDERS",
    )

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_KRAKEN,
        requested_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        candidate_symbol="BTC/USD",
        candidate_notional=settings.kraken_live_max_notional_per_order + 1,
        live_candidate_count=1,
        daily_live_notional=0.0,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_BLOCKED_GATES
    assert readiness["checks"]["candidate_notional_within_cap"] is False


def test_live_readiness_blocks_when_multiple_live_candidates_exist():
    settings = Settings(
        execution_mode=EXECUTION_MODE_KRAKEN,
        enable_kraken_live=True,
        session_live_opt_in=True,
        session_live_confirmation_input="ENABLE_LIVE_ORDERS",
    )

    readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=EXECUTION_MODE_KRAKEN,
        requested_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        candidate_symbol="BTC/USD",
        candidate_notional=25.0,
        live_candidate_count=2,
        daily_live_notional=0.0,
    )

    assert readiness["status"] == LIVE_READINESS_STATUS_BLOCKED_GATES
    assert readiness["checks"]["live_candidate_limit_respected"] is False
