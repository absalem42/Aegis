from config import (
    EXECUTION_MODE_KRAKEN,
    EXECUTION_MODE_PAPER,
    MARKET_DATA_MODE_KRAKEN,
    MARKET_DATA_MODE_MOCK,
    Settings,
)
from engine import resolve_runtime_components, run_engine_cycle
from execution.paper_executor import PaperExecutor
from market.mock_data import MockMarketDataProvider


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
    assert mode_state.warnings == []


def test_runtime_resolution_gracefully_falls_back_from_kraken_modes(tmp_path):
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
    assert len(mode_state.warnings) == 2


def test_engine_cycle_records_requested_and_effective_modes(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        execution_mode=EXECUTION_MODE_KRAKEN,
    )
    settings.ensure_paths()

    result = run_engine_cycle(settings)

    assert result.summary["modes"]["requested_market_data_mode"] == MARKET_DATA_MODE_KRAKEN
    assert result.summary["modes"]["requested_execution_mode"] == EXECUTION_MODE_KRAKEN
    assert result.summary["modes"]["effective_market_data_mode"] == MARKET_DATA_MODE_MOCK
    assert result.summary["modes"]["effective_execution_mode"] == EXECUTION_MODE_PAPER
