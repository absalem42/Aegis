from db import get_connection, init_db, reset_runtime_state, table_names


def test_init_db_creates_expected_tables(tmp_path):
    db_path = tmp_path / "aegis.db"
    with get_connection(db_path) as connection:
        init_db(connection)
        names = table_names(connection)

    assert {"trades", "blocked_trades", "positions", "artifacts", "daily_metrics"}.issubset(names)


def test_reset_runtime_state_clears_db_and_artifacts(tmp_path):
    from config import Settings

    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
    )
    settings.ensure_paths()
    settings.db_path.write_text("stale", encoding="utf-8")
    day_dir = settings.artifact_dir / "2026-03-31"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "artifact.json").write_text("{}", encoding="utf-8")

    summary = reset_runtime_state(settings)

    assert summary["database_reset"] is True
    assert settings.db_path.exists()
    assert settings.artifact_dir.exists()
    assert list(settings.artifact_dir.iterdir()) == []
