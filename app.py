from __future__ import annotations

import pandas as pd
import streamlit as st

from config import load_settings
from dashboard.metrics import build_dashboard_metrics
from db import get_connection, init_db, list_positions, list_recent, load_latest_artifact, upsert_daily_metrics
from engine import run_engine_cycle
from market.mock_data import MockMarketDataProvider


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def main() -> None:
    settings = load_settings()
    st.set_page_config(page_title="Aegis v0", layout="wide")
    st.title("Aegis v0")
    st.caption("Local paper-trading scaffold for BTC/USD, ETH/USD, and SOL/USD.")

    provider = MockMarketDataProvider(settings.symbols)
    latest_prices = provider.get_latest_prices()

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        daily_metrics = upsert_daily_metrics(connection, settings, latest_prices)

    if st.button("Run Engine Cycle", type="primary"):
        result = run_engine_cycle(settings)
        st.success(
            f"Run {result.run_id[:8]} completed: "
            f"{result.executed_count} executed, {result.blocked_count} blocked, {result.signal_count} signals."
        )

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        prices_df = pd.DataFrame(
            [{"symbol": symbol, "price": price} for symbol, price in latest_prices.items()]
        )
        signals = list_recent(connection, "signals", limit=10)
        positions = list_positions(connection)
        trades = list_recent(connection, "trades", limit=10)
        blocked = list_recent(connection, "blocked_trades", limit=10)
        artifacts = list_recent(connection, "artifacts", limit=5)
        latest_artifact = load_latest_artifact(connection)
        daily_metrics = upsert_daily_metrics(connection, settings, latest_prices)

    metrics = build_dashboard_metrics(daily_metrics)
    metric_cols = st.columns(3)
    metric_cols[0].metric("Cumulative PnL", f"{metrics['cumulative_pnl']:.2f}")
    metric_cols[1].metric("Max Drawdown", f"{metrics['max_drawdown']:.2%}")
    metric_cols[2].metric("Ending Cash", f"{metrics['ending_cash']:.2f}")

    left, right = st.columns(2)
    with left:
        st.subheader("Latest Prices")
        st.dataframe(prices_df, use_container_width=True)

        st.subheader("Latest Signals")
        st.dataframe(_frame(signals), use_container_width=True)

        st.subheader("Open Positions")
        st.dataframe(_frame(positions), use_container_width=True)

    with right:
        st.subheader("Recent Trades")
        st.dataframe(_frame(trades), use_container_width=True)

        st.subheader("Recent Blocked Trades")
        st.dataframe(_frame(blocked), use_container_width=True)

        st.subheader("Latest Artifact")
        if latest_artifact:
            preview = {
                "id": latest_artifact["id"],
                "subject": latest_artifact["subject"],
                "type": latest_artifact["artifact_type"],
                "path": latest_artifact["path"],
                "hash": latest_artifact["hash_or_digest"],
            }
            st.json(preview)
        else:
            st.info("No artifacts yet.")

    st.subheader("Artifact History")
    st.dataframe(_frame(artifacts), use_container_width=True)


if __name__ == "__main__":
    main()
