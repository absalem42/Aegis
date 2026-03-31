import pytest

from config import (
    EXECUTION_MODE_KRAKEN,
    EXECUTION_MODE_PAPER,
    KRAKEN_BACKEND_CLI,
    KRAKEN_BACKEND_REST,
    KRAKEN_EXECUTION_MODE_LIVE,
    KRAKEN_EXECUTION_MODE_PAPER,
    MARKET_DATA_MODE_KRAKEN,
    MARKET_DATA_MODE_MOCK,
    Settings,
)
from engine import (
    EXECUTION_STATUS_BLOCKED,
    EXECUTION_STATUS_FALLBACK_TO_INTERNAL_PAPER,
    KRAKEN_CLI_STATUS_ACTIVE,
    KRAKEN_CLI_STATUS_FALLBACK_TO_MOCK,
    KRAKEN_CLI_STATUS_FALLBACK_TO_REST,
    KRAKEN_CLI_STATUS_NOT_REQUESTED,
    KRAKEN_CLI_STATUS_UNAVAILABLE,
    MARKET_DATA_STATUS_ACTIVE,
    MARKET_DATA_STATUS_FALLBACK_TO_MOCK,
    MARKET_DATA_STATUS_NOT_REQUESTED,
    MARKET_DATA_STATUS_UNAVAILABLE,
    resolve_runtime_components,
    run_engine_cycle,
)
from execution.paper_executor import PaperExecutor
from execution.kraken_cli_executor import KrakenCliExecutionError, KrakenCliPaperExecutor
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


class ActiveKrakenCliPaperExecutor(KrakenCliPaperExecutor):
    def __init__(self):
        return None

    def ensure_paper_ready(self, starting_cash: float) -> None:
        return None


class FailingKrakenCliPaperExecutor(KrakenCliPaperExecutor):
    def __init__(self):
        return None

    def ensure_paper_ready(self, starting_cash: float) -> None:
        raise KrakenCliExecutionError("simulated Kraken CLI paper outage")


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
    assert mode_state.kraken_cli_status == KRAKEN_CLI_STATUS_NOT_REQUESTED
    assert mode_state.warnings == []


def test_runtime_resolution_uses_kraken_rest_backend_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenPublicMarketDataProvider", ActiveKrakenRestProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        kraken_backend=KRAKEN_BACKEND_REST,
        execution_mode=EXECUTION_MODE_PAPER,
    )

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, ActiveKrakenRestProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.effective_market_data_mode == MARKET_DATA_MODE_KRAKEN
    assert mode_state.effective_kraken_backend == KRAKEN_BACKEND_REST
    assert mode_state.market_data_provider == "Kraken Public REST"
    assert mode_state.market_data_status == MARKET_DATA_STATUS_ACTIVE
    assert mode_state.kraken_cli_status == KRAKEN_CLI_STATUS_NOT_REQUESTED
    assert mode_state.warnings == []


def test_runtime_resolution_uses_kraken_cli_backend_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenCliMarketDataProvider", ActiveKrakenCliProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        kraken_backend=KRAKEN_BACKEND_CLI,
        execution_mode=EXECUTION_MODE_PAPER,
    )

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, ActiveKrakenCliProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.effective_market_data_mode == MARKET_DATA_MODE_KRAKEN
    assert mode_state.effective_kraken_backend == KRAKEN_BACKEND_CLI
    assert mode_state.market_data_provider == "Kraken Official CLI"
    assert mode_state.market_data_source_type == "cli-json"
    assert mode_state.market_data_status == MARKET_DATA_STATUS_ACTIVE
    assert mode_state.kraken_cli_status == KRAKEN_CLI_STATUS_ACTIVE
    assert mode_state.warnings == []


def test_runtime_resolution_falls_back_from_cli_to_rest(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenCliMarketDataProvider", FailingKrakenCliProvider)
    monkeypatch.setattr("engine.KrakenPublicMarketDataProvider", ActiveKrakenRestProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        kraken_backend=KRAKEN_BACKEND_CLI,
        execution_mode=EXECUTION_MODE_PAPER,
    )

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, ActiveKrakenRestProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.effective_market_data_mode == MARKET_DATA_MODE_KRAKEN
    assert mode_state.effective_kraken_backend == KRAKEN_BACKEND_REST
    assert mode_state.market_data_provider == "Kraken Public REST"
    assert mode_state.kraken_cli_status == KRAKEN_CLI_STATUS_FALLBACK_TO_REST
    assert len(mode_state.warnings) == 1


def test_runtime_resolution_falls_back_from_cli_to_mock_when_rest_fallback_disabled(
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

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, MockMarketDataProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.effective_market_data_mode == MARKET_DATA_MODE_MOCK
    assert mode_state.effective_kraken_backend is None
    assert mode_state.market_data_status == MARKET_DATA_STATUS_FALLBACK_TO_MOCK
    assert mode_state.kraken_cli_status == KRAKEN_CLI_STATUS_FALLBACK_TO_MOCK
    assert len(mode_state.warnings) == 1


def test_runtime_resolution_blocks_when_cli_is_unavailable_and_all_fallbacks_disabled(
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
        kraken_allow_fallback_to_mock=False,
    )
    settings.ensure_paths()

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, MockMarketDataProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.market_data_status == MARKET_DATA_STATUS_UNAVAILABLE
    assert mode_state.effective_market_data_mode == "unavailable"
    assert mode_state.kraken_cli_status == KRAKEN_CLI_STATUS_UNAVAILABLE

    with pytest.raises(KrakenMarketDataError):
        run_engine_cycle(settings)


def test_runtime_resolution_gracefully_falls_back_from_kraken_execution_request(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenPublicMarketDataProvider", FailingKrakenRestProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        kraken_backend=KRAKEN_BACKEND_REST,
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


def test_runtime_resolution_uses_kraken_cli_paper_execution_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr("engine._build_kraken_cli_paper_executor", lambda settings: ActiveKrakenCliPaperExecutor())
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        execution_mode=EXECUTION_MODE_KRAKEN,
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_PAPER,
    )

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, MockMarketDataProvider)
    assert isinstance(executor, ActiveKrakenCliPaperExecutor)
    assert mode_state.effective_execution_mode == EXECUTION_MODE_KRAKEN
    assert mode_state.effective_kraken_execution_mode == KRAKEN_EXECUTION_MODE_PAPER
    assert mode_state.execution_provider == "Kraken CLI Paper Suite"
    assert mode_state.execution_status == "ACTIVE"


def test_runtime_resolution_falls_back_to_internal_paper_when_cli_paper_is_unavailable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("engine._build_kraken_cli_paper_executor", lambda settings: FailingKrakenCliPaperExecutor())
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        execution_mode=EXECUTION_MODE_KRAKEN,
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_PAPER,
    )

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, MockMarketDataProvider)
    assert isinstance(executor, PaperExecutor)
    assert mode_state.effective_execution_mode == EXECUTION_MODE_PAPER
    assert mode_state.effective_kraken_execution_mode is None
    assert mode_state.execution_status == EXECUTION_STATUS_FALLBACK_TO_INTERNAL_PAPER
    assert mode_state.warnings


def test_runtime_resolution_blocks_kraken_live_without_silent_fallback(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        execution_mode=EXECUTION_MODE_KRAKEN,
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
    )

    provider, executor, mode_state = resolve_runtime_components(settings)

    assert isinstance(provider, MockMarketDataProvider)
    assert mode_state.effective_execution_mode == "blocked"
    assert mode_state.effective_kraken_execution_mode == KRAKEN_EXECUTION_MODE_LIVE
    assert mode_state.execution_status == EXECUTION_STATUS_BLOCKED
    assert mode_state.live_readiness_status == "BLOCKED_DISABLED"
