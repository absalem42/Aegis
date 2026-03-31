from __future__ import annotations

import pandas as pd
import streamlit as st

from config import load_settings
from dashboard.audit import (
    build_decision_chains,
    format_decision_chain_rows,
    format_decision_chain_summary,
    format_artifact_rows,
    format_blocked_trade_rows,
    format_latest_artifact_summary,
    format_run_detail,
    format_run_history_rows,
    format_run_option_labels,
    format_signal_rows,
    format_trade_rows,
)
from dashboard.metrics import build_dashboard_metrics
from db import (
    get_connection,
    get_status_summary,
    init_db,
    list_positions,
    list_recent,
    load_latest_artifact,
    reset_runtime_state,
    upsert_daily_metrics,
)
from engine import reseed_demo_state, run_engine_cycle
from market.mock_data import MockMarketDataProvider


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _show_table(title: str, rows: list[dict], empty_message: str) -> None:
    st.subheader(title)
    if rows:
        st.dataframe(_frame(rows), use_container_width=True)
    else:
        st.info(empty_message)


def main() -> None:
    settings = load_settings()
    st.set_page_config(page_title="Aegis v0", layout="wide")
    st.title("Aegis v0")
    st.caption("Local paper-trading demo for BTC/USD, ETH/USD, and SOL/USD.")

    provider = MockMarketDataProvider(settings.symbols)
    latest_prices = provider.get_latest_prices()
    reseed_cycles = 2
    if "aegis_notice" not in st.session_state:
        st.session_state.aegis_notice = None

    with st.sidebar:
        st.header("Demo Controls")
        st.caption("Safe local-only controls for paper-trading demos.")
        reseed_cycles = int(
            st.number_input("Reseed cycles", min_value=1, max_value=5, value=2, step=1)
        )
        if st.button("Run One Engine Cycle", type="primary", use_container_width=True):
            latest_result = run_engine_cycle(settings)
            st.session_state.aegis_notice = (
                "success",
                f"Run {latest_result.run_id[:8]} completed: "
                f"{latest_result.executed_count} executed, "
                f"{latest_result.blocked_count} blocked.",
            )
            st.rerun()
        if st.button("Reset Local State", use_container_width=True):
            summary = reset_runtime_state(settings)
            st.session_state.aegis_notice = (
                "warning",
                "Local runtime state reset. "
                f"DB reset: {summary['database_reset']}. "
                f"Artifact entries removed: {summary['artifact_entries_removed']}.",
            )
            st.rerun()
        if st.button("Reseed Demo State", use_container_width=True):
            summary = reseed_demo_state(settings, cycles=reseed_cycles)
            last_result = summary["results"][-1]
            st.session_state.aegis_notice = (
                "success",
                f"Demo reseeded with {summary['cycles']} deterministic cycles. "
                f"Last run executed {last_result['executed_count']} trades and blocked {last_result['blocked_count']}.",
            )
            st.rerun()

    if st.session_state.aegis_notice:
        level, message = st.session_state.aegis_notice
        getattr(st, level)(message)
        st.session_state.aegis_notice = None

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        prices_df = pd.DataFrame(
            [{"symbol": symbol, "price": price} for symbol, price in latest_prices.items()]
        )
        signals = list_recent(connection, "signals", limit=10)
        positions = list_positions(connection)
        trades = list_recent(connection, "trades", limit=10)
        blocked = list_recent(connection, "blocked_trades", limit=10)
        artifacts = list_recent(connection, "artifacts", limit=10)
        agent_runs = list_recent(connection, "agent_runs", limit=10)
        latest_artifact = load_latest_artifact(connection)
        daily_metrics = upsert_daily_metrics(connection, settings, latest_prices)
        status_summary = get_status_summary(connection, settings)
        signal_rows = format_signal_rows(signals)
        blocked_rows = format_blocked_trade_rows(blocked)
        trade_rows = format_trade_rows(trades)
        artifact_rows = format_artifact_rows(artifacts)
        run_history_rows = format_run_history_rows(agent_runs)
        decision_chains = build_decision_chains(
            signal_rows=signals,
            blocked_trade_rows=blocked,
            trade_rows=trades,
            artifact_rows=artifacts,
            limit=5,
        )

    metrics = build_dashboard_metrics(daily_metrics)
    st.markdown("### Local Status")
    status_cols = st.columns(5)
    status_cols[0].metric("Mode", status_summary["mode"].upper())
    status_cols[1].metric("Trades", f"{status_summary['trade_count']}")
    status_cols[2].metric("Blocked Trades", f"{status_summary['blocked_trade_count']}")
    status_cols[3].metric("Open Positions", f"{status_summary['open_position_count']}")
    status_cols[4].metric("Tracked Symbols", f"{len(settings.symbols)}")

    with st.expander("Environment Details", expanded=False):
        st.write(f"Database path: `{status_summary['database_path']}`")
        st.write(f"Artifact directory: `{status_summary['artifact_directory']}`")
        st.write("Execution mode: `paper`")

    st.markdown("### Trading Metrics")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Cumulative PnL", f"{metrics['cumulative_pnl']:.2f}")
    metric_cols[1].metric("Max Drawdown", f"{metrics['max_drawdown']:.2%}")
    metric_cols[2].metric("Ending Cash", f"{metrics['ending_cash']:.2f}")
    metric_cols[3].metric("Starting Cash", f"{settings.starting_cash:.2f}")

    st.markdown("### Agent Run History")
    st.caption("Compact cycle history showing what the engine observed and decided each run.")
    if run_history_rows:
        history_table = [
            {
                "run_id": row["run_id_short"],
                "ts": row["ts"],
                "status": row["status"],
                "signals": row["signal_count"],
                "executed": row["executed_count"],
                "blocked": row["blocked_count"],
                "artifacts": row["artifact_count"],
            }
            for row in run_history_rows
        ]
        st.dataframe(_frame(history_table), use_container_width=True)

        run_labels = format_run_option_labels(run_history_rows)
        selected_label = st.selectbox(
            "Inspect a recent run",
            options=run_labels,
            index=0,
        )
        selected_run = run_history_rows[run_labels.index(selected_label)]
        run_detail = format_run_detail(selected_run)
        if run_detail:
            detail_left, detail_right = st.columns(2)
            with detail_left:
                st.subheader("Selected Run Summary")
                st.json(
                    {
                        "run_id": run_detail["run_id"],
                        "timestamp": run_detail["timestamp"],
                        "status": run_detail["status"],
                        "signal_count": run_detail["signal_count"],
                        "executed_count": run_detail["executed_count"],
                        "blocked_count": run_detail["blocked_count"],
                        "artifact_count": run_detail["artifact_count"],
                    }
                )
            with detail_right:
                st.subheader("Observed Prices and Metrics")
                st.json(
                    {
                        "prices_observed": run_detail["prices_observed"],
                        "metrics_snapshot": run_detail["metrics_snapshot"],
                    }
                )
    else:
        st.info("No agent runs yet. Run one engine cycle or reseed the demo state to populate run history.")

    st.markdown("### Latest Decision Chain")
    st.caption("Compact explanation of how the latest meaningful signal flowed through risk, artifact creation, and execution.")
    if decision_chains:
        latest_chain = decision_chains[0]
        latest_summary = format_decision_chain_summary(latest_chain)
        signal_col, risk_col, artifact_col, execution_col = st.columns(4)
        with signal_col:
            st.subheader("Signal")
            st.write(f"Symbol: `{latest_summary['symbol']}`")
            st.write(f"Action: `{latest_summary['action']}`")
            st.write(f"Reason: `{latest_summary['signal_reason']}`")
            st.write(
                f"Indicators: price `{latest_summary['price']}`, "
                f"ema20 `{latest_summary['ema20']}`, ema50 `{latest_summary['ema50']}`"
            )
        with risk_col:
            st.subheader("Risk")
            st.write(f"Allowed: `{latest_summary['risk_allowed']}`")
            st.write(f"Summary: `{latest_summary['risk_summary']}`")
            st.write(f"Reason codes: `{latest_summary['risk_reason_codes'] or 'None'}`")
        with artifact_col:
            st.subheader("Artifact")
            st.write(f"Artifact id: `{latest_summary['artifact_id'] or 'Not created'}`")
            st.write(f"Path: `{latest_summary['artifact_path'] or 'N/A'}`")
            st.write(f"Short hash: `{latest_summary['artifact_hash'] or 'N/A'}`")
        with execution_col:
            st.subheader("Execution Outcome")
            st.write(f"Status: `{latest_summary['trade_status']}`")
            st.write(f"Quantity: `{latest_summary['quantity']}`")
            st.write(f"Price: `{latest_summary['price_executed']}`")
            st.write(f"PnL: `{latest_summary['pnl']}`")

        with st.expander("Latest Decision Chain Details", expanded=False):
            st.json(latest_chain)

        st.subheader("Recent Decision Chains")
        st.dataframe(_frame(format_decision_chain_rows(decision_chains)), use_container_width=True)
    else:
        st.info("No decision chain available yet. Run one engine cycle or reseed the demo state.")

    st.markdown("### Market and Signals")
    left, right = st.columns(2)
    with left:
        st.subheader("Latest Prices")
        st.caption("Deterministic local demo prices for the current session.")
        st.dataframe(prices_df, use_container_width=True)

    with right:
        _show_table(
            "Latest Signals",
            signal_rows,
            "No signals yet. Run one engine cycle or reseed the demo state.",
        )

    st.markdown("### Portfolio and Execution")
    left, right = st.columns(2)
    with left:
        _show_table(
            "Open Positions",
            positions,
            "No open positions yet. Use 'Reseed Demo State' for a predictable populated view.",
        )
    with right:
        _show_table(
            "Recent Trades",
            trade_rows,
            "No trades yet. Run one engine cycle to generate paper executions.",
        )

    left, right = st.columns(2)
    with left:
        _show_table(
            "Recent Blocked Trades",
            blocked_rows,
            "No blocked trades yet. Risk checks have not rejected any actions in this state.",
        )
    with right:
        st.subheader("Latest Artifact")
        st.caption("TradeIntent-style artifact saved locally before execution for auditability.")
        preview = format_latest_artifact_summary(latest_artifact)
        if preview:
            st.write(preview["summary"])
            st.json(
                {
                    "artifact_id": preview["artifact_id"],
                    "symbol": preview["symbol"],
                    "side": preview["side"],
                    "quantity": preview["quantity"],
                    "price": preview["price"],
                    "signal_reason": preview["signal_reason"],
                    "risk_allowed": preview["risk_allowed"],
                    "risk_reason_codes": preview["risk_reason_codes"],
                    "path": preview["path"],
                    "hash": preview["hash"],
                }
            )
        else:
            st.info("No artifacts yet. Execute or reseed to create a local proof artifact.")

    st.markdown("### Artifact History")
    if artifact_rows:
        st.dataframe(_frame(artifact_rows), use_container_width=True)
    else:
        st.info("Artifact history is empty. Reseed the demo state to populate this view.")


if __name__ == "__main__":
    main()
