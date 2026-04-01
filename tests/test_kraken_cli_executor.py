import subprocess

import pytest

from execution.kraken_cli_executor import (
    KrakenCliExecutionError,
    KrakenCliLivePreflightExecutor,
    KrakenCliPaperExecutor,
    KrakenCliPaperRunner,
)
from models import ExecutionRequest


def _completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["kraken"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_cli_paper_runner_raises_when_binary_is_missing(monkeypatch):
    def _missing(*_args, **_kwargs):
        raise FileNotFoundError("kraken not found")

    monkeypatch.setattr("execution.kraken_cli_executor.subprocess.run", _missing)
    runner = KrakenCliPaperRunner(command_prefix="kraken", timeout_seconds=5)

    with pytest.raises(KrakenCliExecutionError, match="not found"):
        runner.run_json("status")


def test_cli_paper_runner_raises_on_non_zero_exit(monkeypatch):
    monkeypatch.setattr(
        "execution.kraken_cli_executor.subprocess.run",
        lambda *_args, **_kwargs: _completed(
            '{"error":"paper","message":"paper state missing"}',
            returncode=2,
        ),
    )
    runner = KrakenCliPaperRunner(command_prefix="kraken", timeout_seconds=5)

    with pytest.raises(KrakenCliExecutionError, match="paper state missing"):
        runner.run_json("status")


def test_cli_paper_runner_raises_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        "execution.kraken_cli_executor.subprocess.run",
        lambda *_args, **_kwargs: _completed("not-json"),
    )
    runner = KrakenCliPaperRunner(command_prefix="kraken", timeout_seconds=5)

    with pytest.raises(KrakenCliExecutionError, match="invalid JSON"):
        runner.run_json("status")


def test_cli_paper_executor_initializes_when_status_is_unavailable(monkeypatch):
    calls = []

    def _run(argv, **_kwargs):
        calls.append(argv)
        if argv[1:] == ["paper", "status", "-o", "json"]:
            return _completed('{"error":"paper","message":"missing state"}', returncode=2)
        return _completed('{"status":"ready","balance":"100000"}')

    monkeypatch.setattr("execution.kraken_cli_executor.subprocess.run", _run)
    executor = KrakenCliPaperExecutor(command_prefix="kraken", timeout_seconds=5)

    payload = executor.ensure_paper_ready(100000.0)

    assert payload["status"] == "ready"
    assert any("init" in " ".join(call) for call in calls)


def test_cli_paper_executor_parses_buy_execution(monkeypatch):
    monkeypatch.setattr(
        "execution.kraken_cli_executor.subprocess.run",
        lambda *_args, **_kwargs: _completed(
            '{"order":{"id":"paper-123","status":"FILLED","filled_qty":"0.1","fill_price":"69420.0"}}'
        ),
    )
    executor = KrakenCliPaperExecutor(command_prefix="kraken", timeout_seconds=5)
    request = ExecutionRequest(
        run_id="run-1",
        symbol="BTC/USD",
        side="BUY",
        quantity=0.1,
        price=69420.0,
        order_type="market",
        artifact_id="artifact-1",
        requested_execution_mode="kraken",
        requested_kraken_execution_mode="paper",
        requested_execution_provider="Kraken CLI Paper Suite",
        mode_summary={
            "effective_execution_mode": "kraken",
            "effective_kraken_execution_mode": "paper",
        },
        signal_reason="EMA_BULLISH_BREAKOUT",
    )

    outcome = executor.execute(connection=None, request=request)

    assert outcome.execution_provider == "Kraken CLI Paper Suite"
    assert outcome.execution_source_type == "cli-paper"
    assert outcome.external_order_id == "paper-123"
    assert outcome.filled_quantity == 0.1
    assert outcome.fill_price == 69420.0


def test_cli_paper_executor_raises_when_order_payload_is_missing_fields(monkeypatch):
    monkeypatch.setattr(
        "execution.kraken_cli_executor.subprocess.run",
        lambda *_args, **_kwargs: _completed('{"order":{"status":"FILLED","filled_qty":"not-a-number"}}'),
    )
    executor = KrakenCliPaperExecutor(command_prefix="kraken", timeout_seconds=5)
    request = ExecutionRequest(
        run_id="run-1",
        symbol="BTC/USD",
        side="BUY",
        quantity=0.1,
        price=69420.0,
        order_type="market",
        artifact_id="artifact-1",
        requested_execution_mode="kraken",
        requested_kraken_execution_mode="paper",
        requested_execution_provider="Kraken CLI Paper Suite",
        mode_summary={
            "effective_execution_mode": "kraken",
            "effective_kraken_execution_mode": "paper",
        },
        signal_reason="EMA_BULLISH_BREAKOUT",
    )

    with pytest.raises(KrakenCliExecutionError, match="filled quantity"):
        executor.execute(connection=None, request=request)


def test_cli_live_preflight_auth_test_succeeds(monkeypatch):
    monkeypatch.setattr(
        "execution.kraken_cli_executor.subprocess.run",
        lambda *_args, **_kwargs: _completed('{"authenticated": true, "status": "ok"}'),
    )
    executor = KrakenCliLivePreflightExecutor(command_prefix="kraken", timeout_seconds=5)

    payload = executor.auth_test()

    assert payload["authenticated"] is True


def test_cli_live_preflight_auth_test_fails(monkeypatch):
    monkeypatch.setattr(
        "execution.kraken_cli_executor.subprocess.run",
        lambda *_args, **_kwargs: _completed('{"authenticated": false, "status": "failed"}'),
    )
    executor = KrakenCliLivePreflightExecutor(command_prefix="kraken", timeout_seconds=5)

    with pytest.raises(KrakenCliExecutionError, match="auth test failed"):
        executor.auth_test()


def test_cli_live_preflight_validate_succeeds(monkeypatch):
    monkeypatch.setattr(
        "execution.kraken_cli_executor.subprocess.run",
        lambda *_args, **_kwargs: _completed('{"status":"validated","validated":true}'),
    )
    executor = KrakenCliLivePreflightExecutor(command_prefix="kraken", timeout_seconds=5)
    request = ExecutionRequest(
        run_id="run-1",
        symbol="BTC/USD",
        side="BUY",
        quantity=0.1,
        price=69420.0,
        order_type="market",
        artifact_id="artifact-1",
        requested_execution_mode="kraken",
        requested_kraken_execution_mode="live",
        requested_execution_provider="Kraken CLI Live Preflight",
        mode_summary={
            "effective_execution_mode": "kraken_live_preflight",
            "effective_kraken_execution_mode": "live",
        },
        signal_reason="EMA_BULLISH_BREAKOUT",
    )

    payload = executor.validate_market_order(request)

    assert payload["status"] == "validated"


def test_cli_live_preflight_validate_fails_on_non_zero_exit(monkeypatch):
    monkeypatch.setattr(
        "execution.kraken_cli_executor.subprocess.run",
        lambda *_args, **_kwargs: _completed(
            '{"error":"validation","message":"order rejected"}',
            returncode=2,
        ),
    )
    executor = KrakenCliLivePreflightExecutor(command_prefix="kraken", timeout_seconds=5)
    request = ExecutionRequest(
        run_id="run-1",
        symbol="BTC/USD",
        side="BUY",
        quantity=0.1,
        price=69420.0,
        order_type="market",
        artifact_id="artifact-1",
        requested_execution_mode="kraken",
        requested_kraken_execution_mode="live",
        requested_execution_provider="Kraken CLI Live Preflight",
        mode_summary={
            "effective_execution_mode": "kraken_live_preflight",
            "effective_kraken_execution_mode": "live",
        },
        signal_reason="EMA_BULLISH_BREAKOUT",
    )

    with pytest.raises(KrakenCliExecutionError, match="order rejected"):
        executor.validate_market_order(request)


def test_cli_live_submit_uses_current_pair_and_market_syntax(monkeypatch):
    calls = []

    def _run(argv, **_kwargs):
        calls.append(argv)
        if argv[1:3] == ["auth", "test"]:
            return _completed('{"authenticated": true, "status": "ok"}')
        if "--validate" in argv:
            return _completed('{"status":"validated","validated":true}')
        return _completed('{"order_id":"live-123","status":"submitted"}')

    monkeypatch.setattr("execution.kraken_cli_executor.subprocess.run", _run)
    executor = KrakenCliLivePreflightExecutor(command_prefix="kraken", timeout_seconds=5)
    request = ExecutionRequest(
        run_id="run-1",
        symbol="BTC/USD",
        side="BUY",
        quantity=0.1,
        price=69420.0,
        order_type="market",
        artifact_id="artifact-1",
        requested_execution_mode="kraken",
        requested_kraken_execution_mode="live",
        requested_execution_provider="Kraken CLI Live Preflight",
        mode_summary={
            "effective_execution_mode": "kraken_live",
            "effective_kraken_execution_mode": "live",
        },
        signal_reason="EMA_BULLISH_BREAKOUT",
    )

    auth_payload = executor.auth_test()
    validate_payload = executor.validate_market_order(request)
    outcome = executor.submit_after_preflight(request, auth_payload, validate_payload)

    assert outcome.status == "SUBMITTED_FILL_UNKNOWN"
    assert outcome.external_order_id == "live-123"
    assert outcome.submit_attempted is True
    assert outcome.live_order_submission_occurred is True
    validate_call = next(call for call in calls if "--validate" in call)
    submit_call = next(call for call in calls if call[1:3] == ["order", "buy"] and "--validate" not in call)
    assert validate_call[3] == "BTCUSD"
    assert "--type" in validate_call and "market" in validate_call
    assert "--sandbox" not in validate_call
    assert "--json" not in validate_call
    assert submit_call[3] == "BTCUSD"
    assert "--type" in submit_call and "market" in submit_call


def test_cli_live_submit_raises_on_non_zero_exit(monkeypatch):
    monkeypatch.setattr(
        "execution.kraken_cli_executor.subprocess.run",
        lambda *_args, **_kwargs: _completed(
            '{"error":"submit","message":"real order rejected"}',
            returncode=2,
        ),
    )
    executor = KrakenCliLivePreflightExecutor(command_prefix="kraken", timeout_seconds=5)
    request = ExecutionRequest(
        run_id="run-1",
        symbol="BTC/USD",
        side="BUY",
        quantity=0.1,
        price=69420.0,
        order_type="market",
        artifact_id="artifact-1",
        requested_execution_mode="kraken",
        requested_kraken_execution_mode="live",
        requested_execution_provider="Kraken CLI Live Preflight",
        mode_summary={
            "effective_execution_mode": "kraken_live",
            "effective_kraken_execution_mode": "live",
        },
        signal_reason="EMA_BULLISH_BREAKOUT",
    )

    with pytest.raises(KrakenCliExecutionError, match="real order rejected"):
        executor.submit_market_order(request)
