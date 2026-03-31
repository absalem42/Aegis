import subprocess

import pytest

from execution.kraken_cli_executor import (
    KrakenCliExecutionError,
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
