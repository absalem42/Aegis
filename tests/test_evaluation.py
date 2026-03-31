from config import (
    EXECUTION_MODE_PAPER,
    KRAKEN_BACKEND_CLI,
    MARKET_DATA_MODE_KRAKEN,
    Settings,
)
from evaluation import (
    calculate_local_evaluation_score,
    list_evaluation_reports,
    load_latest_evaluation_report,
    run_evaluation,
)
from market.mock_data import MockMarketDataProvider


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


def test_run_evaluation_generates_and_persists_mock_report(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        report_dir=tmp_path / "reports",
        starting_cash=100000.0,
        trade_fraction=0.10,
    )
    settings.ensure_paths()

    report = run_evaluation(settings, cycles=2, reset_first=True, label="Mock Judge Eval")

    assert report["label"] == "Mock Judge Eval"
    assert report["metrics"]["cycle_count"] == 2
    assert report["metrics"]["signal_count"] == 6
    assert report["metrics"]["trade_count"] >= 2
    assert report["metrics"]["artifact_count"] >= 2
    assert report["metrics"]["source_quality_indicator"] == "mock"
    assert report["requested_execution_mode"] == EXECUTION_MODE_PAPER
    assert report["effective_execution_mode"] == EXECUTION_MODE_PAPER
    assert report["report_path"].endswith(".json")

    latest = load_latest_evaluation_report(settings)
    history = list_evaluation_reports(settings, limit=5)

    assert latest is not None
    assert latest["report_id"] == report["report_id"]
    assert history[0]["report_id"] == report["report_id"]


def test_evaluation_report_handles_not_enough_closed_trade_data(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        report_dir=tmp_path / "reports",
    )
    settings.ensure_paths()

    report = run_evaluation(settings, cycles=1, reset_first=True, label="Short Eval")

    assert report["metrics"]["win_rate"] is None
    assert report["metrics"]["profit_factor"] is None
    assert report["metrics"]["average_pnl_per_closed_trade"] is None
    assert "Not enough" in report["metrics"]["win_rate_note"]
    assert "Not enough" in report["metrics"]["profit_factor_note"]


def test_local_score_rewards_better_performance_and_coverage():
    weak_score = calculate_local_evaluation_score(
        {
            "starting_equity": 100000.0,
            "total_pnl": -500.0,
            "realized_pnl": -250.0,
            "max_drawdown": 0.08,
            "artifact_coverage_for_executed_decisions": 0.5,
            "executed_count": 2,
            "blocked_count": 4,
        }
    )
    strong_score = calculate_local_evaluation_score(
        {
            "starting_equity": 100000.0,
            "total_pnl": 1500.0,
            "realized_pnl": 600.0,
            "max_drawdown": 0.01,
            "artifact_coverage_for_executed_decisions": 1.0,
            "executed_count": 5,
            "blocked_count": 1,
        }
    )

    assert strong_score["score"] > weak_score["score"]
    assert strong_score["caption"].startswith("Local/internal score")


def test_run_evaluation_records_cli_source_quality_when_cli_backend_is_active(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.KrakenCliMarketDataProvider", ActiveKrakenCliProvider)
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        report_dir=tmp_path / "reports",
        market_data_mode=MARKET_DATA_MODE_KRAKEN,
        kraken_backend=KRAKEN_BACKEND_CLI,
        execution_mode=EXECUTION_MODE_PAPER,
    )
    settings.ensure_paths()

    report = run_evaluation(settings, cycles=1, reset_first=True, label="CLI Eval")

    assert report["effective_market_data_mode"] == MARKET_DATA_MODE_KRAKEN
    assert report["effective_kraken_backend"] == KRAKEN_BACKEND_CLI
    assert report["market_data_source_type"] == "cli-json"
    assert report["metrics"]["source_quality_indicator"] == "Kraken CLI"
    assert report["kraken_cli_status"] == "ACTIVE"
