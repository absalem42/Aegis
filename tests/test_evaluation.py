from config import (
    EXECUTION_MODE_KRAKEN,
    EXECUTION_MODE_PAPER,
    KRAKEN_BACKEND_CLI,
    KRAKEN_EXECUTION_MODE_LIVE,
    MARKET_DATA_MODE_KRAKEN,
    Settings,
)
from evaluation import (
    build_best_vs_latest_summary,
    calculate_local_evaluation_score,
    format_evaluation_proof_snapshot_rows,
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


def test_run_evaluation_forces_internal_paper_even_if_kraken_execution_is_requested(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        report_dir=tmp_path / "reports",
        execution_mode=EXECUTION_MODE_KRAKEN,
        kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
    )
    settings.ensure_paths()

    report = run_evaluation(settings, cycles=1, reset_first=True, label="Forced Internal Paper")

    assert report["requested_execution_mode"] == EXECUTION_MODE_PAPER
    assert report["effective_execution_mode"] == EXECUTION_MODE_PAPER


def test_build_best_vs_latest_summary_prefers_highest_local_score():
    reports = [
        {
            "report_id": "latest",
            "label": "Latest Eval",
            "generated_at": "2026-03-31T10:00:00Z",
            "metrics": {
                "source_quality_indicator": "mock",
                "total_pnl": 120.0,
                "max_drawdown": 0.03,
                "artifact_coverage_for_executed_decisions": 1.0,
            },
            "scorecard": {"score": 61.5},
        },
        {
            "report_id": "best",
            "label": "Best Eval",
            "generated_at": "2026-03-31T09:00:00Z",
            "metrics": {
                "source_quality_indicator": "Kraken REST",
                "total_pnl": 480.0,
                "max_drawdown": 0.01,
                "artifact_coverage_for_executed_decisions": 1.0,
            },
            "scorecard": {"score": 77.0},
        },
    ]

    summary = build_best_vs_latest_summary(reports)

    assert summary is not None
    assert summary["latest"]["label"] == "Latest Eval"
    assert summary["best"]["label"] == "Best Eval"
    assert summary["same_report"] is False


def test_format_evaluation_proof_snapshot_rows_surfaces_agent_and_readiness_fields():
    reports = [
        {
            "generated_at": "2026-03-31T10:00:00Z",
            "label": "Judge Eval",
            "agent": {"agent_name": "Aegis", "version": "0.1.0"},
            "metrics": {
                "source_quality_indicator": "Kraken CLI",
                "artifact_coverage_for_executed_decisions": 1.0,
            },
            "proof_summary": {
                "artifact_count": 3,
                "artifact_readiness_summary": "Artifacts contain agent identity and decision context.",
            },
            "scorecard": {"score": 74.25},
        }
    ]

    rows = format_evaluation_proof_snapshot_rows(reports)

    assert rows[0]["agent_name"] == "Aegis"
    assert rows[0]["agent_version"] == "0.1.0"
    assert rows[0]["source_quality"] == "Kraken CLI"
    assert rows[0]["artifact_coverage"] == 1.0
    assert "decision context" in rows[0]["readiness_summary"]
