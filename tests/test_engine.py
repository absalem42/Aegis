from config import Settings
from db import get_connection, init_db, list_positions, list_recent
from engine import reseed_demo_state, run_engine_cycle


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
