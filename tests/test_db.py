from db import get_connection, init_db, table_names


def test_init_db_creates_expected_tables(tmp_path):
    db_path = tmp_path / "aegis.db"
    with get_connection(db_path) as connection:
        init_db(connection)
        names = table_names(connection)

    assert {"trades", "blocked_trades", "positions", "artifacts", "daily_metrics"}.issubset(names)
