import json

from config import (
    EXECUTION_MODE_PAPER,
    KRAKEN_BACKEND_CLI,
    KRAKEN_BACKEND_REST,
    MARKET_DATA_MODE_KRAKEN,
    Settings,
)
from db import get_connection, init_db, list_positions, list_recent
from engine import reseed_demo_state, run_engine_cycle
from market.kraken_cli import KrakenCliError
from market.kraken_client import KrakenMarketDataError
from market.mock_data import MockMarketDataProvider


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
        artifacts = list_recent(connection, "artifacts", limit=1)

    payload = json.loads(artifacts[0]["payload_json"])
    assert payload["market_data"]["provider"] == "Kraken Public REST"
    assert payload["market_data"]["backend"] == KRAKEN_BACKEND_REST
    assert payload["market_data"]["status"] == "ACTIVE"
    assert payload["market_data"]["source_type"] == "public-rest"


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
        artifacts = list_recent(connection, "artifacts", limit=1)

    payload = json.loads(artifacts[0]["payload_json"])
    assert payload["market_data"]["provider"] == "Kraken Official CLI"
    assert payload["market_data"]["backend"] == KRAKEN_BACKEND_CLI
    assert payload["market_data"]["status"] == "ACTIVE"
    assert payload["market_data"]["kraken_cli_status"] == "ACTIVE"
    assert payload["market_data"]["source_type"] == "cli-json"


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
