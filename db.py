from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import Settings
from models import ExecutionResult, Signal, utc_now_iso


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            notional REAL NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            pnl REAL NOT NULL DEFAULT 0,
            artifact_id TEXT
        );

        CREATE TABLE IF NOT EXISTS blocked_trades (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            attempted_quantity REAL NOT NULL,
            attempted_price REAL NOT NULL,
            block_reason TEXT NOT NULL,
            context_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            quantity REAL NOT NULL,
            average_cost REAL NOT NULL,
            last_price REAL NOT NULL,
            market_value REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            hash_or_digest TEXT NOT NULL,
            notes TEXT NOT NULL,
            path TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_metrics (
            trading_day TEXT PRIMARY KEY,
            starting_cash REAL NOT NULL,
            ending_cash REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            trade_count INTEGER NOT NULL,
            blocked_trade_count INTEGER NOT NULL,
            max_drawdown REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            indicator_json TEXT NOT NULL,
            should_execute INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            status TEXT NOT NULL,
            summary_json TEXT NOT NULL
        );
        """
    )
    connection.commit()


def insert_signal(connection: sqlite3.Connection, signal: Signal) -> None:
    connection.execute(
        """
        INSERT INTO signals (id, ts, symbol, action, reason, indicator_json, should_execute)
        VALUES (:id, :ts, :symbol, :action, :reason, :indicator_json, :should_execute)
        """,
        {
            **signal.to_record(),
            "indicator_json": json.dumps(signal.indicators, sort_keys=True),
        },
    )
    connection.commit()


def insert_artifact(
    connection: sqlite3.Connection,
    artifact_id: str,
    artifact_type: str,
    subject: str,
    payload: dict[str, Any],
    digest: str,
    notes: str,
    path: str,
) -> None:
    connection.execute(
        """
        INSERT INTO artifacts (id, ts, artifact_type, subject, payload_json, hash_or_digest, notes, path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            utc_now_iso(),
            artifact_type,
            subject,
            json.dumps(payload, sort_keys=True),
            digest,
            notes,
            path,
        ),
    )
    connection.commit()


def insert_blocked_trade(
    connection: sqlite3.Connection,
    symbol: str,
    side: str,
    attempted_quantity: float,
    attempted_price: float,
    block_reason: str,
    context: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO blocked_trades (
            id, ts, symbol, side, attempted_quantity, attempted_price, block_reason, context_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            utc_now_iso(),
            symbol,
            side,
            attempted_quantity,
            attempted_price,
            block_reason,
            json.dumps(context, sort_keys=True),
        ),
    )
    connection.commit()


def get_position(connection: sqlite3.Connection, symbol: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,)).fetchone()


def list_positions(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM positions WHERE quantity > 0 ORDER BY symbol"
    ).fetchall()
    return [dict(row) for row in rows]


def upsert_position(
    connection: sqlite3.Connection,
    symbol: str,
    quantity: float,
    average_cost: float,
    last_price: float,
    updated_at: str | None = None,
) -> None:
    ts = updated_at or utc_now_iso()
    market_value = round(quantity * last_price, 6)
    unrealized_pnl = round((last_price - average_cost) * quantity, 6)
    connection.execute(
        """
        INSERT INTO positions (symbol, quantity, average_cost, last_price, market_value, unrealized_pnl, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            quantity = excluded.quantity,
            average_cost = excluded.average_cost,
            last_price = excluded.last_price,
            market_value = excluded.market_value,
            unrealized_pnl = excluded.unrealized_pnl,
            updated_at = excluded.updated_at
        """,
        (symbol, quantity, average_cost, last_price, market_value, unrealized_pnl, ts),
    )
    connection.commit()


def delete_position(connection: sqlite3.Connection, symbol: str) -> None:
    connection.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
    connection.commit()


def refresh_position_prices(connection: sqlite3.Connection, latest_prices: dict[str, float]) -> None:
    for symbol, price in latest_prices.items():
        row = get_position(connection, symbol)
        if row is None:
            continue
        upsert_position(
            connection,
            symbol=symbol,
            quantity=float(row["quantity"]),
            average_cost=float(row["average_cost"]),
            last_price=price,
        )


def record_trade(connection: sqlite3.Connection, result: ExecutionResult, reason: str = "EXECUTED") -> None:
    connection.execute(
        """
        INSERT INTO trades (id, ts, symbol, side, quantity, price, notional, reason, status, pnl, artifact_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.trade_id,
            result.ts,
            result.symbol,
            result.side,
            result.quantity,
            result.price,
            result.notional,
            reason,
            "FILLED",
            result.pnl,
            result.artifact_id,
        ),
    )
    connection.commit()


def list_recent(
    connection: sqlite3.Connection, table: str, limit: int = 10, order_by: str = "ts"
) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"SELECT * FROM {table} ORDER BY {order_by} DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_recent_trade_pnls(connection: sqlite3.Connection, limit: int = 5) -> list[float]:
    rows = connection.execute(
        """
        SELECT pnl FROM trades
        WHERE side = 'SELL'
        ORDER BY ts DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [float(row["pnl"]) for row in rows]


def count_open_positions(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM positions WHERE quantity > 0"
    ).fetchone()
    return int(row["count"]) if row else 0


def get_cash_balance(connection: sqlite3.Connection, starting_cash: float) -> float:
    row = connection.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN side = 'BUY' THEN -notional WHEN side = 'SELL' THEN notional ELSE 0 END), 0) AS net_cash
        FROM trades
        """
    ).fetchone()
    net_cash = float(row["net_cash"]) if row else 0.0
    return round(starting_cash + net_cash, 6)


def get_total_unrealized_pnl(connection: sqlite3.Connection) -> float:
    row = connection.execute(
        "SELECT COALESCE(SUM(unrealized_pnl), 0) AS total_unrealized FROM positions"
    ).fetchone()
    return float(row["total_unrealized"]) if row else 0.0


def get_total_market_value(connection: sqlite3.Connection) -> float:
    row = connection.execute(
        "SELECT COALESCE(SUM(market_value), 0) AS total_market_value FROM positions"
    ).fetchone()
    return float(row["total_market_value"]) if row else 0.0


def get_total_realized_pnl(connection: sqlite3.Connection) -> float:
    row = connection.execute("SELECT COALESCE(SUM(pnl), 0) AS total_realized FROM trades").fetchone()
    return float(row["total_realized"]) if row else 0.0


def upsert_daily_metrics(
    connection: sqlite3.Connection,
    settings: Settings,
    latest_prices: dict[str, float],
) -> dict[str, Any]:
    refresh_position_prices(connection, latest_prices)
    trading_day = utc_now_iso()[:10]
    ending_cash = get_cash_balance(connection, settings.starting_cash)
    realized_pnl = get_total_realized_pnl(connection)
    unrealized_pnl = get_total_unrealized_pnl(connection)
    market_value = get_total_market_value(connection)
    trade_count = _count_table(connection, "trades")
    blocked_trade_count = _count_table(connection, "blocked_trades")
    equity = ending_cash + market_value
    max_drawdown = max(0.0, (settings.starting_cash - equity) / settings.starting_cash)
    record = {
        "trading_day": trading_day,
        "starting_cash": settings.starting_cash,
        "ending_cash": round(ending_cash, 6),
        "realized_pnl": round(realized_pnl, 6),
        "unrealized_pnl": round(unrealized_pnl, 6),
        "trade_count": trade_count,
        "blocked_trade_count": blocked_trade_count,
        "max_drawdown": round(max_drawdown, 6),
    }
    connection.execute(
        """
        INSERT INTO daily_metrics (
            trading_day, starting_cash, ending_cash, realized_pnl, unrealized_pnl,
            trade_count, blocked_trade_count, max_drawdown
        )
        VALUES (
            :trading_day, :starting_cash, :ending_cash, :realized_pnl, :unrealized_pnl,
            :trade_count, :blocked_trade_count, :max_drawdown
        )
        ON CONFLICT(trading_day) DO UPDATE SET
            ending_cash = excluded.ending_cash,
            realized_pnl = excluded.realized_pnl,
            unrealized_pnl = excluded.unrealized_pnl,
            trade_count = excluded.trade_count,
            blocked_trade_count = excluded.blocked_trade_count,
            max_drawdown = excluded.max_drawdown
        """,
        record,
    )
    connection.commit()
    return record


def record_agent_run(
    connection: sqlite3.Connection,
    run_id: str,
    status: str,
    summary: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO agent_runs (id, ts, status, summary_json)
        VALUES (?, ?, ?, ?)
        """,
        (run_id, utc_now_iso(), status, json.dumps(summary, sort_keys=True)),
    )
    connection.commit()


def load_latest_artifact(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM artifacts ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _count_table(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"]) if row else 0
