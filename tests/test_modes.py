import pytest

from config import (
    EXECUTION_MODE_KRAKEN,
    EXECUTION_MODE_PAPER,
    MARKET_DATA_MODE_KRAKEN,
    MARKET_DATA_MODE_MOCK,
    Settings,
)
from engine import (
    MARKET_DATA_STATUS_ACTIVE,
    MARKET_DATA_STATUS_FALLBACK_TO_MOCK,
    MARKET_DATA_STATUS_NOT_REQUESTED,
    MARKET_DATA_STATUS_UNAVAILABLE,
    resolve_runtime_components,
    run_engine_cycle,
)
from execution.paper_executor import PaperExecutor
from market.kraken_client import KrakenMarketDataError
from market.mock_data import MockMarketDataProvider


class ActiveKrakenProvider:
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


class FailingKrakenProvider:
    provider_name = "Kraken Public REST"
    source_type = "public-rest"

    def __init__(self, *_args, **_kwargs):
        return None

    def ensure_available(self) -> None:
        raise KrakenMarketDataError("simulated Kraken outage")


def test_runtime_resolution_defaults_to_safe_local_modes(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_MOCK,
        execution_mode=EXECUTION_MODE_PAPER,
    )

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, MockMarketDataProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.effective_market_data_mode == MARKET_DATA_MODE_MOCK
    assert mode_state.effective_execution_mode == EXECUTION_MODE_PAPER
    assert mode_state.market_data_status == MARKET_DATA_STATUS_NOT_REQUESTED
    assert mode_state.warnings == []


def test_runtime_resolution_uses_real_kraken_provider_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenPublicMarketDataProvider", ActiveKrakenProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        execution_mode=EXECUTION_MODE_PAPER,
    )

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, ActiveKrakenProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.effective_market_data_mode == MARKET_DATA_MODE_KRAKEN
    assert mode_state.effective_execution_mode == EXECUTION_MODE_PAPER
    assert mode_state.market_data_provider == "Kraken Public REST"
    assert mode_state.market_data_status == MARKET_DATA_STATUS_ACTIVE
    assert mode_state.warnings == []


def test_runtime_resolution_gracefully_falls_back_from_kraken_modes(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenPublicMarketDataProvider", FailingKrakenProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        execution_mode=EXECUTION_MODE_KRAKEN,
    )

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, MockMarketDataProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.requested_market_data_mode == MARKET_DATA_MODE_KRAKEN
    assert mode_state.requested_execution_mode == EXECUTION_MODE_KRAKEN
    assert mode_state.effective_market_data_mode == MARKET_DATA_MODE_MOCK
    assert mode_state.effective_execution_mode == EXECUTION_MODE_PAPER
    assert mode_state.market_data_status == MARKET_DATA_STATUS_FALLBACK_TO_MOCK
    assert len(mode_state.warnings) == 2


def test_engine_cycle_blocks_when_kraken_is_unavailable_and_fallback_is_disabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("engine.KrakenPublicMarketDataProvider", FailingKrakenProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        execution_mode=EXECUTION_MODE_PAPER,
        kraken_allow_fallback_to_mock=False,
    )
    settings.ensure_paths()

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, MockMarketDataProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.market_data_status == MARKET_DATA_STATUS_UNAVAILABLE
    assert mode_state.effective_market_data_mode == "unavailable"

    with pytest.raises(KrakenMarketDataError):
        run_engine_cycle(settings)
