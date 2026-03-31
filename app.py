from __future__ import annotations

from dataclasses import replace

import pandas as pd
import streamlit as st

from config import (
    EXECUTION_MODE_KRAKEN,
    EXECUTION_MODE_PAPER,
    KRAKEN_BACKEND_CLI,
    KRAKEN_BACKEND_REST,
    MARKET_DATA_MODE_KRAKEN,
    MARKET_DATA_MODE_MOCK,
    load_settings,
)
from dashboard.audit import (
    build_agent_identity_summary,
    build_proof_summary,
    build_trust_readiness_summary,
    format_decision_chain_rows,
    format_decision_chain_summary,
    format_artifact_rows,
    format_blocked_trade_rows,
    format_latest_artifact_summary,
    format_run_detail,
    format_run_history_rows,
    format_run_option_labels,
    format_selected_run_caption,
    format_signal_rows,
    format_trade_rows,
    scope_records_to_run,
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
from evaluation import (
    build_provider_capabilities_summary,
    format_evaluation_comparison_rows,
    format_evaluation_history_rows,
    list_evaluation_reports,
    load_latest_evaluation_report,
    run_evaluation,
)
from engine import (
    MARKET_DATA_STATUS_ACTIVE,
    MARKET_DATA_STATUS_FALLBACK_TO_MOCK,
    MARKET_DATA_STATUS_UNAVAILABLE,
    KRAKEN_CLI_STATUS_ACTIVE,
    KRAKEN_CLI_STATUS_FALLBACK_TO_MOCK,
    KRAKEN_CLI_STATUS_FALLBACK_TO_REST,
    KRAKEN_CLI_STATUS_NOT_REQUESTED,
    KRAKEN_CLI_STATUS_UNAVAILABLE,
    reseed_demo_state,
    resolve_runtime_components,
    run_engine_cycle,
)
from market.kraken_client import KrakenMarketDataError


MARKET_MODE_LABELS = {
    MARKET_DATA_MODE_MOCK: "Mock (deterministic demo)",
    MARKET_DATA_MODE_KRAKEN: "Kraken public market data",
}
KRAKEN_BACKEND_LABELS = {
    KRAKEN_BACKEND_REST: "Public REST",
    KRAKEN_BACKEND_CLI: "Official Kraken CLI",
}
EXECUTION_MODE_LABELS = {
    EXECUTION_MODE_PAPER: "Paper (safe local execution)",
    EXECUTION_MODE_KRAKEN: "Kraken execution (stub, disabled)",
}
CLI_STATUS_LABELS = {
    KRAKEN_CLI_STATUS_ACTIVE: "ACTIVE",
    KRAKEN_CLI_STATUS_FALLBACK_TO_REST: "FALLBACK TO REST",
    KRAKEN_CLI_STATUS_FALLBACK_TO_MOCK: "FALLBACK TO MOCK",
    KRAKEN_CLI_STATUS_UNAVAILABLE: "UNAVAILABLE",
    KRAKEN_CLI_STATUS_NOT_REQUESTED: "NOT REQUESTED",
}


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _show_table(title: str, rows: list[dict], empty_message: str) -> None:
    st.subheader(title)
    if rows:
        st.dataframe(_frame(rows), use_container_width=True)
    else:
        st.info(empty_message)


def _empty_daily_metrics(starting_cash: float) -> dict[str, float]:
    return {
        "trading_day": "",
        "starting_cash": starting_cash,
        "ending_cash": starting_cash,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "trade_count": 0,
        "blocked_trade_count": 0,
        "max_drawdown": 0.0,
    }


def _backend_label(value: str | None) -> str:
    if not value:
        return "N/A"
    return KRAKEN_BACKEND_LABELS.get(value, value.upper())


def _ratio_label(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.0%}"


def main() -> None:
    base_settings = load_settings()
    st.set_page_config(page_title="Aegis v0", layout="wide")
    st.title("Aegis v0")
    st.caption("Local paper-trading demo for BTC/USD, ETH/USD, and SOL/USD.")
    reseed_cycles = 2
    if "aegis_notice" not in st.session_state:
        st.session_state.aegis_notice = None

    with st.sidebar:
        st.header("Demo Controls")
        st.caption("Safe local-only controls for paper-trading demos.")
        market_data_mode = st.selectbox(
            "Market data mode",
            options=[MARKET_DATA_MODE_MOCK, MARKET_DATA_MODE_KRAKEN],
            index=[MARKET_DATA_MODE_MOCK, MARKET_DATA_MODE_KRAKEN].index(base_settings.market_data_mode),
            format_func=lambda value: MARKET_MODE_LABELS[value],
        )
        kraken_backend = base_settings.kraken_backend
        if market_data_mode == MARKET_DATA_MODE_KRAKEN:
            kraken_backend = st.selectbox(
                "Kraken backend",
                options=[KRAKEN_BACKEND_REST, KRAKEN_BACKEND_CLI],
                index=[KRAKEN_BACKEND_REST, KRAKEN_BACKEND_CLI].index(base_settings.kraken_backend),
                format_func=lambda value: KRAKEN_BACKEND_LABELS[value],
            )
        execution_mode = st.selectbox(
            "Execution mode",
            options=[EXECUTION_MODE_PAPER, EXECUTION_MODE_KRAKEN],
            index=[EXECUTION_MODE_PAPER, EXECUTION_MODE_KRAKEN].index(base_settings.execution_mode),
            format_func=lambda value: EXECUTION_MODE_LABELS[value],
        )
        reseed_cycles = int(
            st.number_input("Reseed cycles", min_value=1, max_value=5, value=2, step=1)
        )
        settings = replace(
            base_settings,
            market_data_mode=market_data_mode,
            execution_mode=execution_mode,
            kraken_backend=kraken_backend,
        )
        provider, _executor, mode_state = resolve_runtime_components(settings)
        runs_blocked = mode_state.market_data_status == MARKET_DATA_STATUS_UNAVAILABLE
        if runs_blocked:
            st.error("The selected Kraken market-data path is unavailable and no safe fallback remains.")
        if st.button(
            "Run One Engine Cycle",
            type="primary",
            use_container_width=True,
            disabled=runs_blocked,
        ):
            try:
                latest_result = run_engine_cycle(settings)
            except KrakenMarketDataError as exc:
                st.session_state.aegis_notice = ("error", str(exc))
            else:
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
        if st.button("Reseed Demo State", use_container_width=True, disabled=runs_blocked):
            try:
                summary = reseed_demo_state(settings, cycles=reseed_cycles)
            except KrakenMarketDataError as exc:
                st.session_state.aegis_notice = ("error", str(exc))
            else:
                last_result = summary["results"][-1]
                st.session_state.aegis_notice = (
                    "success",
                    f"Demo reseeded with {summary['cycles']} deterministic cycles. "
                    f"Last run executed {last_result['executed_count']} trades and blocked {last_result['blocked_count']}.",
                )
            st.rerun()

        st.divider()
        st.header("Evaluation")
        st.caption("Run a local paper-only evaluation and save a judge-friendly report under `reports/`.")
        evaluation_market_data_mode = st.selectbox(
            "Evaluation market data mode",
            options=[MARKET_DATA_MODE_MOCK, MARKET_DATA_MODE_KRAKEN],
            index=[MARKET_DATA_MODE_MOCK, MARKET_DATA_MODE_KRAKEN].index(base_settings.market_data_mode),
            format_func=lambda value: MARKET_MODE_LABELS[value],
            key="evaluation_market_data_mode",
        )
        evaluation_kraken_backend = base_settings.kraken_backend
        if evaluation_market_data_mode == MARKET_DATA_MODE_KRAKEN:
            evaluation_kraken_backend = st.selectbox(
                "Evaluation Kraken backend",
                options=[KRAKEN_BACKEND_REST, KRAKEN_BACKEND_CLI],
                index=[KRAKEN_BACKEND_REST, KRAKEN_BACKEND_CLI].index(base_settings.kraken_backend),
                format_func=lambda value: KRAKEN_BACKEND_LABELS[value],
                key="evaluation_kraken_backend",
            )
        evaluation_cycles = int(
            st.number_input("Evaluation cycles", min_value=1, max_value=25, value=5, step=1)
        )
        evaluation_label = st.text_input("Evaluation label", value="")
        evaluation_reset_first = st.checkbox("Reset before evaluation", value=True)
        evaluation_settings = replace(
            base_settings,
            market_data_mode=evaluation_market_data_mode,
            kraken_backend=evaluation_kraken_backend,
            execution_mode=EXECUTION_MODE_PAPER,
        )
        _evaluation_provider, _evaluation_executor, evaluation_mode_state = resolve_runtime_components(
            evaluation_settings
        )
        evaluation_blocked = (
            evaluation_mode_state.market_data_status == MARKET_DATA_STATUS_UNAVAILABLE
        )
        if evaluation_blocked:
            st.error("The selected evaluation data source is unavailable and no safe fallback remains.")
        st.caption("Execution stays paper-only during evaluation. This score is local and not the official leaderboard.")
        if st.button(
            "Run Evaluation",
            use_container_width=True,
            disabled=evaluation_blocked,
        ):
            try:
                report = run_evaluation(
                    evaluation_settings,
                    cycles=evaluation_cycles,
                    reset_first=evaluation_reset_first,
                    label=evaluation_label or None,
                )
            except KrakenMarketDataError as exc:
                st.session_state.aegis_notice = ("error", str(exc))
            else:
                st.session_state.aegis_notice = (
                    "success",
                    f"Evaluation {report['label']} completed: "
                    f"score {report['scorecard']['score']}, "
                    f"total PnL {report['metrics']['total_pnl']:.2f}.",
                )
            st.rerun()

    latest_prices: dict[str, float] = {}
    if not runs_blocked:
        try:
            latest_prices = provider.get_latest_prices()
        except KrakenMarketDataError as exc:
            st.warning(f"Latest Kraken prices could not be loaded: {exc}")
            latest_prices = {}

    if st.session_state.aegis_notice:
        level, message = st.session_state.aegis_notice
        getattr(st, level)(message)
        st.session_state.aegis_notice = None
    for warning in mode_state.warnings:
        st.warning(warning)

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        prices_df = pd.DataFrame(
            [{"symbol": symbol, "price": price} for symbol, price in latest_prices.items()]
        ) if latest_prices else pd.DataFrame(columns=["symbol", "price"])
        signals = list_recent(connection, "signals", limit=10)
        positions = list_positions(connection)
        trades = list_recent(connection, "trades", limit=10)
        blocked = list_recent(connection, "blocked_trades", limit=10)
        artifacts = list_recent(connection, "artifacts", limit=10)
        agent_runs = list_recent(connection, "agent_runs", limit=10)
        latest_artifact = load_latest_artifact(connection)
        if latest_prices:
            daily_metrics = upsert_daily_metrics(connection, settings, latest_prices)
        else:
            daily_metrics = list_recent(
                connection,
                "daily_metrics",
                limit=1,
                order_by="trading_day",
            )
            daily_metrics = daily_metrics[0] if daily_metrics else _empty_daily_metrics(settings.starting_cash)
        status_summary = get_status_summary(connection, settings)
        signal_rows = format_signal_rows(signals)
        blocked_rows = format_blocked_trade_rows(blocked)
        trade_rows = format_trade_rows(trades)
        artifact_rows = format_artifact_rows(artifacts)
        run_history_rows = format_run_history_rows(agent_runs)
        selected_run_scope = None
        decision_chains = []

    metrics = build_dashboard_metrics(daily_metrics)
    agent_identity_summary = build_agent_identity_summary(settings, mode_state.to_dict())
    latest_linked_trade = trades[0] if trades else None
    trust_readiness_summary = build_trust_readiness_summary(latest_artifact, latest_linked_trade)
    evaluation_reports = list_evaluation_reports(settings, limit=10)
    latest_evaluation_report = load_latest_evaluation_report(settings)
    provider_capabilities = build_provider_capabilities_summary()

    st.markdown("### Local Status")
    mode_cols = st.columns(6)
    mode_cols[0].metric("Requested Market", mode_state.requested_market_data_mode.upper())
    mode_cols[1].metric("Effective Market", str(mode_state.effective_market_data_mode).upper())
    mode_cols[2].metric("Requested Execution", mode_state.requested_execution_mode.upper())
    mode_cols[3].metric("Effective Execution", mode_state.effective_execution_mode.upper())
    mode_cols[4].metric("Requested Kraken Backend", _backend_label(mode_state.requested_kraken_backend))
    mode_cols[5].metric("Effective Kraken Backend", _backend_label(mode_state.effective_kraken_backend))

    status_cols = st.columns(5)
    status_cols[0].metric("Kraken CLI Status", CLI_STATUS_LABELS.get(mode_state.kraken_cli_status, mode_state.kraken_cli_status))
    status_cols[1].metric("Kraken Data Status", mode_state.market_data_status.replace("_", " "))
    status_cols[2].metric("Trades", f"{status_summary['trade_count']}")
    status_cols[3].metric("Blocked Trades", f"{status_summary['blocked_trade_count']}")
    status_cols[4].metric("Open Positions", f"{status_summary['open_position_count']}")

    with st.expander("Environment Details", expanded=False):
        st.write(f"Database path: `{status_summary['database_path']}`")
        st.write(f"Artifact directory: `{status_summary['artifact_directory']}`")
        st.write(f"Market data provider: `{mode_state.market_data_provider}`")
        st.write(f"Requested Kraken backend: `{_backend_label(mode_state.requested_kraken_backend)}`")
        st.write(f"Effective Kraken backend: `{_backend_label(mode_state.effective_kraken_backend)}`")
        st.write(f"Kraken CLI status: `{CLI_STATUS_LABELS.get(mode_state.kraken_cli_status, mode_state.kraken_cli_status)}`")
        st.write(f"Market data source type: `{mode_state.market_data_source_type}`")
        st.write(f"Kraken data status: `{mode_state.market_data_status}`")
        st.write(f"Execution mode: `{mode_state.effective_execution_mode}`")
        st.write(f"Requested market data mode: `{mode_state.requested_market_data_mode}`")
        st.write(f"Requested execution mode: `{mode_state.requested_execution_mode}`")

    st.markdown("### Readiness Status")
    st.caption(
        "Kraken public market data can feed the strategy through REST or the official Kraken CLI. "
        "Execution remains local paper execution in this milestone."
    )
    readiness_cols = st.columns(4)
    readiness_cols[0].metric("Market Provider", mode_state.market_data_provider)
    readiness_cols[1].metric("Kraken Backend", _backend_label(mode_state.effective_kraken_backend))
    readiness_cols[2].metric("CLI Status", CLI_STATUS_LABELS.get(mode_state.kraken_cli_status, mode_state.kraken_cli_status))
    readiness_cols[3].metric("Execution Safety", "PAPER ONLY")

    trust_left, trust_right = st.columns(2)
    with trust_left:
        st.markdown("### Agent Identity")
        st.caption("Local agent identity used to structure proof artifacts for future ERC-8004-style validation.")
        st.json(agent_identity_summary)
    with trust_right:
        st.markdown("### Trust / Validation Readiness")
        st.caption("Local readiness only. No on-chain publishing or signing occurs in v0.")
        if trust_readiness_summary:
            st.metric(
                "Artifact Readiness",
                f"{trust_readiness_summary['ready_checks_passed']}/{trust_readiness_summary['ready_checks_total']}",
            )
            st.write(trust_readiness_summary["summary"])
            st.json({"checks": trust_readiness_summary["checks"]})
        else:
            st.info("No trust artifact yet. Run one engine cycle or reseed the demo state.")

    st.markdown("### Provider Capabilities")
    st.caption("Source quality is explicit: mock is deterministic, Kraken REST is public exchange data, Kraken CLI is optional and local, and execution remains paper-only.")
    st.dataframe(_frame(provider_capabilities), use_container_width=True)

    st.markdown("### Evaluation Summary")
    st.caption("Local/internal score only. It is intended for transparent comparison inside Aegis and is not the official leaderboard.")
    if latest_evaluation_report:
        latest_metrics = latest_evaluation_report["metrics"]
        latest_scorecard = latest_evaluation_report["scorecard"]
        summary_cols = st.columns(6)
        summary_cols[0].metric("Label", latest_evaluation_report["label"])
        summary_cols[1].metric("Source Quality", latest_metrics["source_quality_indicator"])
        summary_cols[2].metric("Local Score", f"{latest_scorecard['score']:.2f}")
        summary_cols[3].metric("Total PnL", f"{latest_metrics['total_pnl']:.2f}")
        summary_cols[4].metric("Max Drawdown", f"{latest_metrics['max_drawdown']:.2%}")
        summary_cols[5].metric(
            "Artifact Coverage",
            _ratio_label(latest_metrics.get("artifact_coverage_for_executed_decisions")),
        )
        secondary_summary_cols = st.columns(4)
        secondary_summary_cols[0].metric(
            "Win Rate",
            _ratio_label(latest_metrics.get("win_rate")),
        )
        secondary_summary_cols[1].metric(
            "Profit Factor",
            "N/A" if latest_metrics.get("profit_factor") is None else f"{latest_metrics['profit_factor']:.2f}",
        )
        secondary_summary_cols[2].metric(
            "Avg Closed Trade PnL",
            "N/A"
            if latest_metrics.get("average_pnl_per_closed_trade") is None
            else f"{latest_metrics['average_pnl_per_closed_trade']:.2f}",
        )
        secondary_summary_cols[3].metric("Executed / Blocked", f"{latest_metrics['executed_count']} / {latest_metrics['blocked_count']}")
        st.write(latest_scorecard["caption"])
        st.json(
            {
                "generated_at": latest_evaluation_report["generated_at"],
                "requested_market_data_mode": latest_evaluation_report["requested_market_data_mode"],
                "effective_market_data_mode": latest_evaluation_report["effective_market_data_mode"],
                "requested_kraken_backend": _backend_label(latest_evaluation_report.get("requested_kraken_backend")),
                "effective_kraken_backend": _backend_label(latest_evaluation_report.get("effective_kraken_backend")),
                "requested_execution_mode": latest_evaluation_report["requested_execution_mode"],
                "effective_execution_mode": latest_evaluation_report["effective_execution_mode"],
                "market_data_provider": latest_evaluation_report["market_data_provider"],
                "market_data_source_type": latest_evaluation_report["market_data_source_type"],
                "kraken_cli_status": latest_evaluation_report["kraken_cli_status"],
                "proof_summary": latest_evaluation_report["proof_summary"],
                "score_formula": latest_scorecard["formula"],
                "report_path": latest_evaluation_report.get("report_path"),
            }
        )
    else:
        st.info("No evaluation report yet. Use the sidebar to run a local evaluation.")

    st.markdown("### Evaluation Report History")
    if evaluation_reports:
        st.dataframe(
            _frame(format_evaluation_history_rows(evaluation_reports)),
            use_container_width=True,
        )
    else:
        st.info("No saved evaluation reports yet.")

    st.markdown("### Evaluation Comparison")
    if evaluation_reports:
        st.dataframe(
            _frame(format_evaluation_comparison_rows(evaluation_reports[:5])),
            use_container_width=True,
        )
    else:
        st.info("Run a few evaluations to compare source quality, PnL, drawdown, artifact coverage, and local score.")

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
                "market_data": (
                    f"{row['market_data_provider']} / "
                    f"{_backend_label(row.get('effective_kraken_backend'))} / "
                    f"{row['market_data_status']}"
                    if row.get("market_data_provider")
                    else "N/A"
                ),
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
            "Select a recent run",
            options=run_labels,
            index=0,
        )
        selected_run = run_history_rows[run_labels.index(selected_label)]
        selected_run_scope = scope_records_to_run(
            run_history_rows=run_history_rows,
            selected_run_id=selected_run["run_id"],
            signal_rows=signals,
            blocked_trade_rows=blocked,
            trade_rows=trades,
            artifact_rows=artifacts,
            decision_chain_limit=5,
        )
        decision_chains = selected_run_scope["decision_chains"]
        signal_rows = format_signal_rows(selected_run_scope["signals"])
        blocked_rows = format_blocked_trade_rows(selected_run_scope["blocked_trades"])
        trade_rows = format_trade_rows(selected_run_scope["trades"])
        artifact_rows = format_artifact_rows(selected_run_scope["artifacts"])
        latest_artifact = selected_run_scope["latest_artifact"]
        run_detail = format_run_detail(selected_run)
        proof_summary = build_proof_summary(selected_run)
        st.caption(format_selected_run_caption(selected_run))
        if run_detail:
            detail_left, detail_right = st.columns(2)
            with detail_left:
                st.subheader("Selected Run Summary")
                st.json(
                    {
                        "run_id": run_detail["run_id"],
                        "timestamp": run_detail["timestamp"],
                        "status": run_detail["status"],
                        "market_data_provider": selected_run.get("market_data_provider"),
                        "market_data_status": selected_run.get("market_data_status"),
                        "requested_kraken_backend": _backend_label(selected_run.get("requested_kraken_backend")),
                        "effective_kraken_backend": _backend_label(selected_run.get("effective_kraken_backend")),
                        "kraken_cli_status": CLI_STATUS_LABELS.get(
                            selected_run.get("kraken_cli_status"),
                            selected_run.get("kraken_cli_status"),
                        ),
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
                        "modes": run_detail["modes"],
                    }
                )
        if proof_summary:
            st.subheader("Proof-Oriented Summary")
            st.caption("Select a run, inspect its decision chain, then review the artifact and final outcome.")
            proof_cols = st.columns(5)
            proof_cols[0].metric("Signals", proof_summary["signal_count"])
            proof_cols[1].metric("Executed", proof_summary["executed_count"])
            proof_cols[2].metric("Blocked", proof_summary["blocked_count"])
            proof_cols[3].metric("Artifacts", proof_summary["artifact_count"])
            proof_cols[4].metric("Observed Prices", len(proof_summary["observed_prices"]))
            st.write(proof_summary["why_it_matters"])
            st.json(
                {
                    "observed_prices": proof_summary["observed_prices"],
                    "market_data_provider": proof_summary["market_data_provider"],
                    "market_data_status": proof_summary["market_data_status"],
                    "effective_kraken_backend": _backend_label(proof_summary.get("effective_kraken_backend")),
                    "kraken_cli_status": CLI_STATUS_LABELS.get(
                        proof_summary.get("kraken_cli_status"),
                        proof_summary.get("kraken_cli_status"),
                    ),
                    "modes": proof_summary["modes"],
                    "agent": agent_identity_summary,
                }
            )
        if selected_run_scope:
            st.caption(selected_run_scope["scoping_note"])
    else:
        st.info("No agent runs yet. Run one engine cycle or reseed the demo state to populate run history.")

    st.markdown("### Latest Decision Chain")
    st.caption("Compact explanation of how the selected run's meaningful signal flowed through risk, artifact creation, and execution.")
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
            st.write(f"Agent: `{latest_summary['artifact_agent_name'] or 'N/A'}`")
            st.write(f"Readiness: `{latest_summary['artifact_readiness'] or 'N/A'}`")
            st.write(
                "Market data: "
                f"`{latest_summary['artifact_market_data_provider'] or 'N/A'}` "
                f"({latest_summary['artifact_market_data_status'] or 'N/A'})"
            )
            st.write(f"Kraken backend: `{_backend_label(latest_summary['artifact_market_data_backend'])}`")
            st.write(
                "CLI status: "
                f"`{CLI_STATUS_LABELS.get(latest_summary['artifact_kraken_cli_status'], latest_summary['artifact_kraken_cli_status'] or 'N/A')}`"
            )
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
        if mode_state.market_data_status == MARKET_DATA_STATUS_ACTIVE:
            st.caption("Live public Kraken market data for the current session.")
        elif mode_state.market_data_status == MARKET_DATA_STATUS_FALLBACK_TO_MOCK:
            st.caption("Kraken public market data fell back to deterministic mock prices for this session.")
        else:
            st.caption("Deterministic local demo prices for the current session.")
        if latest_prices:
            st.dataframe(prices_df, use_container_width=True)
        else:
            st.info("Latest prices are unavailable for the current mode selection.")

    with right:
        _show_table(
            "Latest Signals",
            signal_rows,
            "No signals found for the selected run. Try another run or reseed the demo state.",
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
            "No executed trades found for the selected run.",
        )

    left, right = st.columns(2)
    with left:
        _show_table(
            "Recent Blocked Trades",
            blocked_rows,
            "No blocked trades found for the selected run.",
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
                    "modes": preview["modes"],
                    "market_data": preview["market_data"],
                    "kraken_backend": _backend_label(preview.get("kraken_backend")),
                    "kraken_cli_status": CLI_STATUS_LABELS.get(
                        preview.get("kraken_cli_status"),
                        preview.get("kraken_cli_status"),
                    ),
                    "agent": preview["agent"],
                    "validation_readiness": preview["validation_readiness"],
                    "path": preview["path"],
                    "hash": preview["hash"],
                }
            )
        else:
            st.info("No artifacts found for the selected run.")

    st.markdown("### Artifact History")
    if artifact_rows:
        st.dataframe(_frame(artifact_rows), use_container_width=True)
    else:
        st.info("Artifact history is empty for the selected run.")


if __name__ == "__main__":
    main()
