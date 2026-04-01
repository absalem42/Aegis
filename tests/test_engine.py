import json
from uuid import uuid4

from config import (
    EXECUTION_MODE_PAPER,
    KRAKEN_BACKEND_CLI,
    KRAKEN_BACKEND_REST,
    KRAKEN_EXECUTION_MODE_LIVE,
    KRAKEN_EXECUTION_MODE_PAPER,
    MARKET_DATA_MODE_KRAKEN,
    Settings,
)
from db import get_connection, init_db, list_positions, list_recent
from engine import reseed_demo_state, run_engine_cycle
from market.kraken_cli import KrakenCliError
from market.kraken_client import KrakenMarketDataError
from market.mock_data import MockMarketDataProvider
from models import ExecutionOutcome
from execution.kraken_cli_executor import KrakenCliExecutionError
from models import Signal


class ActiveKrakenRestProvider:
    backend_name = "rest"
    provider_name = "Kraken Public REST"
    source_type = "public-rest"

    def __init__(self, symbols, **_kwargs):
        self.delegate = MockMarketDataProvider(symbols)

    def ensure_available(self) -> None:
        return None

    def get_latest_prices(self) -> dict[str, float]:
        return self.delegate.get_latest_prices()

    def get_price_history(self, symbol: str, length: int = 60) -> list[float]:
        return self.delegate.get_price_history(symbol, length=length)

    def get_histories(self, length: int = 60) -> dict[str, list[float]]:
        return self.delegate.get_histories(length=length)


class ActiveKrakenCliProvider:
    backend_name = "cli"
    provider_name = "Kraken Official CLI"
    source_type = "cli-json"

    def __init__(self, symbols, **_kwargs):
        self.delegate = MockMarketDataProvider(symbols)

    def ensure_available(self) -> None:
        return None

    def get_latest_prices(self) -> dict[str, float]:
        return self.delegate.get_latest_prices()

    def get_price_history(self, symbol: str, length: int = 60) -> list[float]:
        return self.delegate.get_price_history(symbol, length=length)

    def get_histories(self, length: int = 60) -> dict[str, list[float]]:
        return self.delegate.get_histories(length=length)


class FailingKrakenRestProvider:
    backend_name = "rest"
    provider_name = "Kraken Public REST"
    source_type = "public-rest"

    def __init__(self, *_args, **_kwargs):
        return None

    def ensure_available(self) -> None:
        raise KrakenMarketDataError("simulated Kraken REST outage")


class FailingKrakenCliProvider:
    backend_name = "cli"
    provider_name = "Kraken Official CLI"
    source_type = "cli-json"

    def __init__(self, *_args, **_kwargs):
        return None

    def ensure_available(self) -> None:
        raise KrakenCliError("simulated Kraken CLI outage")


class ActiveKrakenCliPaperExecutor:
    provider_name = "Kraken CLI Paper Suite"
    source_type = "cli-paper"

    def ensure_paper_ready(self, starting_cash: float):
        return {"status": "ready", "starting_cash": starting_cash}

    def reset_and_init(self, starting_cash: float):
        return {"reset": {"status": "ok"}, "init": {"balance": starting_cash}}

    def execute(self, connection, request):
        return ExecutionOutcome(
            run_id=request.run_id,
            local_order_id=str(uuid4()),
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled_quantity=request.quantity,
            price=request.price,
            fill_price=request.price,
            notional=round(request.quantity * request.price, 6),
            artifact_id=request.artifact_id,
            order_type=request.order_type,
            status="FILLED",
            execution_provider=self.provider_name,
            execution_source_type=self.source_type,
            requested_execution_mode=request.requested_execution_mode,
            effective_execution_mode=request.mode_summary.get("effective_execution_mode"),
            requested_kraken_execution_mode=request.requested_kraken_execution_mode,
            effective_kraken_execution_mode=request.mode_summary.get("effective_kraken_execution_mode"),
            provider_metadata={"paper_response": {"status": "filled", "id": "paper-123"}},
            external_order_id="paper-123",
            external_status="FILLED",
        )


class FailingKrakenCliPaperExecutor:
    provider_name = "Kraken CLI Paper Suite"
    source_type = "cli-paper"

    def ensure_paper_ready(self, starting_cash: float):
        raise KrakenCliExecutionError("simulated Kraken CLI paper failure")


class ActiveKrakenCliLivePreflightExecutor:
    provider_name = "Kraken CLI Live Preflight"
    source_type = "cli-live-preflight"

    def auth_test(self):
        return {"authenticated": True, "status": "ok"}

    def validate_market_order(self, request):
        return {"status": "validated", "symbol": request.symbol}


class AuthFailingKrakenCliLivePreflightExecutor(ActiveKrakenCliLivePreflightExecutor):
    def auth_test(self):
        raise KrakenCliExecutionError("simulated auth failure")


class ValidateFailingKrakenCliLivePreflightExecutor(ActiveKrakenCliLivePreflightExecutor):
    def validate_market_order(self, request):
        raise KrakenCliExecutionError(f"simulated validate failure for {request.symbol}")


class SingleSignalStrategy:
    def generate_signals(self, histories):
        symbol = next(iter(histories))
        price = histories[symbol][-1]
        return [
            Signal(
                symbol=symbol,
                action="BUY",
                reason="EMA_BULLISH_BREAKOUT",
                indicators={"price": price, "ema20": price - 1, "ema50": price - 2},
                should_execute=True,
            )
        ]


def test_engine_cycle_creates_expected_records(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        starting_cash=100000.0,
        trade_fraction=0.10,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.signal_count == 3
    assert result.executed_count >= 1
    assert result.blocked_count >= 1

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        trades = list_recent(connection, "trades", limit=10)
        blocked = list_recent(connection, "blocked_trades", limit=10)
        artifacts = list_recent(connection, "artifacts", limit=10)
        signals = list_recent(connection, "signals", limit=10)
        positions = list_positions(connection)

    assert trades
    assert blocked
    assert artifacts
    assert len(signals) == 3
    assert any(position["symbol"] == "BTC/USD" for position in positions)


def test_reseed_demo_state_creates_predictable_demo_records(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        starting_cash=100000.0,
        trade_fraction=0.10,
    )
    settings.ensure_paths()

    summary = reseed_demo_state(settings, cycles=2)

    assert summary["cycles"] == 2
    assert len(summary["results"]) == 2

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        trades = list_recent(connection, "trades", limit=20)
        blocked = list_recent(connection, "blocked_trades", limit=20)
        artifacts = list_recent(connection, "artifacts", limit=20)

    assert len(trades) >= 2
    assert len(blocked) >= 1
    assert len(artifacts) >= len(trades)


def test_engine_cycle_records_rest_market_data_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenPublicMarketDataProvider", ActiveKrakenRestProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        kraken_backend=KRAKEN_BACKEND_REST,
        execution_mode=EXECUTION_MODE_PAPER,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.summary["modes"]["effective_market_data_mode"] == MARKET_DATA_MODE_KRAKEN
    assert result.summary["modes"]["market_data_provider"] == "Kraken Public REST"
    assert result.summary["modes"]["market_data_source_type"] == "public-rest"
    assert result.summary["modes"]["effective_kraken_backend"] == KRAKEN_BACKEND_REST

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        artifacts = list_recent(connection, "artifacts", limit=5)

    trade_intent = next(
        json.loads(row["payload_json"])
        for row in artifacts
        if row["artifact_type"] == "TradeIntent"
    )
    receipt = next(
        json.loads(row["payload_json"])
        for row in artifacts
        if row["artifact_type"] == "ExecutionReceipt"
    )
    assert trade_intent["market_data"]["provider"] == "Kraken Public REST"
    assert trade_intent["market_data"]["backend"] == KRAKEN_BACKEND_REST
    assert trade_intent["market_data"]["status"] == "ACTIVE"
    assert trade_intent["market_data"]["source_type"] == "public-rest"
    assert receipt["execution"]["execution_provider"] == "Internal Paper Engine"


def test_engine_cycle_records_cli_market_data_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenCliMarketDataProvider", ActiveKrakenCliProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        kraken_backend=KRAKEN_BACKEND_CLI,
        execution_mode=EXECUTION_MODE_PAPER,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.summary["modes"]["effective_market_data_mode"] == MARKET_DATA_MODE_KRAKEN
    assert result.summary["modes"]["market_data_provider"] == "Kraken Official CLI"
    assert result.summary["modes"]["market_data_source_type"] == "cli-json"
    assert result.summary["modes"]["effective_kraken_backend"] == KRAKEN_BACKEND_CLI
    assert result.summary["modes"]["kraken_cli_status"] == "ACTIVE"

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        artifacts = list_recent(connection, "artifacts", limit=5)

    trade_intent = next(
        json.loads(row["payload_json"])
        for row in artifacts
        if row["artifact_type"] == "TradeIntent"
    )
    receipt = next(
        json.loads(row["payload_json"])
        for row in artifacts
        if row["artifact_type"] == "ExecutionReceipt"
    )
    assert trade_intent["market_data"]["provider"] == "Kraken Official CLI"
    assert trade_intent["market_data"]["backend"] == KRAKEN_BACKEND_CLI
    assert trade_intent["market_data"]["status"] == "ACTIVE"
    assert trade_intent["market_data"]["kraken_cli_status"] == "ACTIVE"
    assert trade_intent["market_data"]["source_type"] == "cli-json"
    assert receipt["execution"]["execution_provider"] == "Internal Paper Engine"


def test_engine_cycle_records_rest_fallback_when_cli_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenCliMarketDataProvider", FailingKrakenCliProvider)
    monkeypatch.setattr("engine.KrakenPublicMarketDataProvider", ActiveKrakenRestProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        kraken_backend=KRAKEN_BACKEND_CLI,
        execution_mode=EXECUTION_MODE_PAPER,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.summary["modes"]["effective_market_data_mode"] == "kraken"
    assert result.summary["modes"]["effective_kraken_backend"] == KRAKEN_BACKEND_REST
    assert result.summary["modes"]["kraken_cli_status"] == "FALLBACK_TO_REST"
    assert result.summary["modes"]["warnings"]


def test_engine_cycle_records_mock_fallback_when_cli_and_rest_fallback_are_unavailable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("engine.KrakenCliMarketDataProvider", FailingKrakenCliProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        kraken_backend=KRAKEN_BACKEND_CLI,
        execution_mode=EXECUTION_MODE_PAPER,
        kraken_cli_allow_fallback_to_rest=False,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.summary["modes"]["effective_market_data_mode"] == "mock"
    assert result.summary["modes"]["effective_kraken_backend"] is None
    assert result.summary["modes"]["market_data_status"] == "FALLBACK_TO_MOCK"
    assert result.summary["modes"]["kraken_cli_status"] == "FALLBACK_TO_MOCK"
    assert result.summary["modes"]["warnings"]


def test_engine_cycle_records_orders_and_execution_receipts(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        starting_cash=100000.0,
        trade_fraction=0.10,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.order_count >= 1
    assert result.receipt_count >= 1

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        orders = list_recent(connection, "orders", limit=10)
        trades = list_recent(connection, "trades", limit=10)
        artifacts = list_recent(connection, "artifacts", limit=10)

    assert orders
    assert trades
    assert trades[0]["order_id"]
    assert trades[0]["execution_provider"] == "Internal Paper Engine"
    assert any(row["artifact_type"] == "ExecutionReceipt" for row in artifacts)


def test_engine_cycle_uses_kraken_cli_paper_execution_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr("engine._build_kraken_cli_paper_executor", lambda settings: ActiveKrakenCliPaperExecutor())
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        execution_mode="kraken",
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_PAPER,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.executed_count >= 1
    assert result.summary["modes"]["execution_provider"] == "Kraken CLI Paper Suite"
    assert result.summary["modes"]["effective_execution_mode"] == "kraken"
    assert result.summary["modes"]["effective_kraken_execution_mode"] == KRAKEN_EXECUTION_MODE_PAPER

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        trades = list_recent(connection, "trades", limit=10)
        artifacts = list_recent(connection, "artifacts", limit=10)

    assert trades[0]["execution_provider"] == "Kraken CLI Paper Suite"
    receipt = next(
        json.loads(row["payload_json"])
        for row in artifacts
        if row["artifact_type"] == "ExecutionReceipt"
    )
    assert receipt["execution"]["execution_provider"] == "Kraken CLI Paper Suite"
    assert receipt["execution"]["effective_kraken_execution_mode"] == KRAKEN_EXECUTION_MODE_PAPER


def test_engine_cycle_blocks_when_kraken_live_is_requested(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        execution_mode="kraken",
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.executed_count == 0
    assert result.blocked_count >= 1
    assert result.summary["modes"]["effective_execution_mode"] == "kraken_live_preflight"
    assert result.summary["modes"]["effective_kraken_execution_mode"] == KRAKEN_EXECUTION_MODE_LIVE
    assert result.summary["modes"]["execution_status"] == "BLOCKED"
    assert result.summary["modes"]["auth_test_status"] == "NOT_RUN"
    assert result.summary["modes"]["validate_preflight_status"] == "NOT_RUN"

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        orders = list_recent(connection, "orders", limit=10)
        trades = list_recent(connection, "trades", limit=10)
        artifacts = list_recent(connection, "artifacts", limit=10)

    assert orders
    assert not trades
    assert any(row["status"] == "BLOCKED" for row in orders)
    assert any(row["artifact_type"] == "ExecutionReceipt" for row in artifacts)


def test_engine_cycle_runs_live_preflight_without_creating_a_trade(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.RegimeStrategy", lambda: SingleSignalStrategy())
    monkeypatch.setattr(
        "engine._build_kraken_cli_live_preflight_executor",
        lambda settings: ActiveKrakenCliLivePreflightExecutor(),
    )
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        execution_mode="kraken",
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        enable_kraken_live=True,
        session_live_opt_in=True,
        session_live_confirmation_input="ENABLE_LIVE_ORDERS",
        kraken_live_max_notional_per_order=100000.0,
        kraken_live_max_daily_notional=100000.0,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.executed_count == 0
    assert result.summary["modes"]["execution_status"] == "PREFLIGHT_PASSED"
    assert result.summary["modes"]["auth_test_status"] == "PASSED"
    assert result.summary["modes"]["validate_preflight_status"] == "PASSED"

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        orders = list_recent(connection, "orders", limit=10)
        trades = list_recent(connection, "trades", limit=10)
        artifacts = list_recent(connection, "artifacts", limit=10)

    assert orders
    assert orders[0]["status"] == "PREFLIGHT_PASSED"
    assert not trades
    receipt = next(json.loads(row["payload_json"]) for row in artifacts if row["artifact_type"] == "ExecutionReceipt")
    assert receipt["execution"]["auth_test_status"] == "PASSED"
    assert receipt["execution"]["validate_preflight_status"] == "PASSED"
    assert receipt["execution"]["live_preflight_status"] == "PREFLIGHT_PASSED"
    assert receipt["no_live_submit_performed"] is True


def test_engine_cycle_records_live_preflight_auth_failure_without_trade(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.RegimeStrategy", lambda: SingleSignalStrategy())
    monkeypatch.setattr(
        "engine._build_kraken_cli_live_preflight_executor",
        lambda settings: AuthFailingKrakenCliLivePreflightExecutor(),
    )
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        execution_mode="kraken",
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        enable_kraken_live=True,
        session_live_opt_in=True,
        session_live_confirmation_input="ENABLE_LIVE_ORDERS",
        kraken_live_max_notional_per_order=100000.0,
        kraken_live_max_daily_notional=100000.0,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.executed_count == 0
    assert result.blocked_count >= 1
    assert result.summary["modes"]["execution_status"] == "PREFLIGHT_FAILED"
    assert result.summary["modes"]["auth_test_status"] == "FAILED"
    assert result.summary["modes"]["validate_preflight_status"] == "NOT_RUN"

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        trades = list_recent(connection, "trades", limit=10)
        orders = list_recent(connection, "orders", limit=10)

    assert not trades
    assert orders[0]["status"] == "PREFLIGHT_FAILED"


def test_engine_cycle_records_live_preflight_validate_failure_without_trade(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.RegimeStrategy", lambda: SingleSignalStrategy())
    monkeypatch.setattr(
        "engine._build_kraken_cli_live_preflight_executor",
        lambda settings: ValidateFailingKrakenCliLivePreflightExecutor(),
    )
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        execution_mode="kraken",
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        enable_kraken_live=True,
        session_live_opt_in=True,
        session_live_confirmation_input="ENABLE_LIVE_ORDERS",
        kraken_live_max_notional_per_order=100000.0,
        kraken_live_max_daily_notional=100000.0,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.executed_count == 0
    assert result.blocked_count >= 1
    assert result.summary["modes"]["execution_status"] == "PREFLIGHT_FAILED"
    assert result.summary["modes"]["auth_test_status"] == "PASSED"
    assert result.summary["modes"]["validate_preflight_status"] == "FAILED"
