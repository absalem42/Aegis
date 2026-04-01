from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any
from uuid import uuid4

from config import (
    EXECUTION_MODE_KRAKEN,
    EXECUTION_MODE_PAPER,
    KRAKEN_BACKEND_CLI,
    KRAKEN_BACKEND_REST,
    KRAKEN_EXECUTION_MODE_LIVE,
    KRAKEN_EXECUTION_MODE_PAPER,
    MARKET_DATA_MODE_KRAKEN,
    MARKET_DATA_MODE_MOCK,
    Settings,
    load_settings,
)
from db import (
    apply_execution_outcome,
    count_open_positions,
    get_cash_balance,
    get_connection,
    get_daily_live_preflight_notional,
    get_position,
    get_recent_trade_pnls,
    get_total_market_value,
    init_db,
    insert_blocked_trade,
    insert_signal,
    record_agent_run,
    refresh_position_prices,
    reset_runtime_state,
    upsert_daily_metrics,
)
from execution import (
    ExecutionProvider,
    KrakenCliExecutionError,
    KrakenCliLivePreflightExecutor,
    KrakenCliPaperExecutor,
)
from execution.kraken_executor import KrakenExecutorStub
from execution.paper_executor import PaperExecutor
from execution.safety import (
    build_live_readiness_snapshot,
    live_execution_is_blocked,
    live_preflight_can_run,
    LIVE_READINESS_STATUS_PREFLIGHT_FAILED,
    LIVE_READINESS_STATUS_PREFLIGHT_PASSED,
)
from market import MarketDataProvider
from market.kraken_cli import KrakenCliError, KrakenCliMarketDataProvider
from market.kraken_client import KrakenMarketDataError, KrakenPublicMarketDataProvider
from market.mock_data import MockMarketDataProvider
from models import EngineCycleResult, ExecutionOutcome, ExecutionRequest, Signal
from proof.agent_identity import build_agent_identity
from proof.artifact_store import save_artifact, save_trade_artifact
from proof.execution_receipt import build_execution_receipt
from proof.trade_intent import build_trade_intent
from risk.engine import RiskEngine
from strategy.regime_strategy import RegimeStrategy

logger = logging.getLogger(__name__)

MARKET_DATA_STATUS_ACTIVE = "ACTIVE"
MARKET_DATA_STATUS_FALLBACK_TO_MOCK = "FALLBACK_TO_MOCK"
MARKET_DATA_STATUS_UNAVAILABLE = "UNAVAILABLE"
MARKET_DATA_STATUS_NOT_REQUESTED = "NOT_REQUESTED"
KRAKEN_CLI_STATUS_ACTIVE = "ACTIVE"
KRAKEN_CLI_STATUS_FALLBACK_TO_REST = "FALLBACK_TO_REST"
KRAKEN_CLI_STATUS_FALLBACK_TO_MOCK = "FALLBACK_TO_MOCK"
KRAKEN_CLI_STATUS_UNAVAILABLE = "UNAVAILABLE"
KRAKEN_CLI_STATUS_NOT_REQUESTED = "NOT_REQUESTED"
EXECUTION_STATUS_ACTIVE = "ACTIVE"
EXECUTION_STATUS_FALLBACK_TO_INTERNAL_PAPER = "FALLBACK_TO_INTERNAL_PAPER"
EXECUTION_STATUS_BLOCKED = "BLOCKED"
EXECUTION_STATUS_PREFLIGHT_ONLY = "PREFLIGHT_ONLY"
EXECUTION_STATUS_PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
EXECUTION_STATUS_PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
EXECUTION_STATUS_NOT_REQUESTED = "NOT_REQUESTED"
EXECUTION_MODE_BLOCKED = "blocked"


@dataclass(slots=True)
class RuntimeModeState:
    requested_market_data_mode: str
    effective_market_data_mode: str
    requested_execution_mode: str
    effective_execution_mode: str
    requested_kraken_backend: str | None
    effective_kraken_backend: str | None
    requested_kraken_execution_mode: str | None
    effective_kraken_execution_mode: str | None
    market_data_provider: str
    market_data_status: str
    kraken_cli_status: str
    market_data_source_type: str
    execution_provider: str
    execution_status: str
    execution_source_type: str
    live_readiness_status: str
    live_readiness: dict[str, Any]
    auth_test_status: str | None
    validate_preflight_status: str | None
    final_live_preflight_status: str | None
    kraken_ohlc_interval_minutes: int
    kraken_history_length: int
    warnings: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_market_data_mode": self.requested_market_data_mode,
            "effective_market_data_mode": self.effective_market_data_mode,
            "requested_execution_mode": self.requested_execution_mode,
            "effective_execution_mode": self.effective_execution_mode,
            "requested_kraken_backend": self.requested_kraken_backend,
            "effective_kraken_backend": self.effective_kraken_backend,
            "requested_kraken_execution_mode": self.requested_kraken_execution_mode,
            "effective_kraken_execution_mode": self.effective_kraken_execution_mode,
            "market_data_provider": self.market_data_provider,
            "market_data_status": self.market_data_status,
            "kraken_cli_status": self.kraken_cli_status,
            "market_data_source_type": self.market_data_source_type,
            "execution_provider": self.execution_provider,
            "execution_status": self.execution_status,
            "execution_source_type": self.execution_source_type,
            "live_readiness_status": self.live_readiness_status,
            "live_readiness": self.live_readiness,
            "auth_test_status": self.auth_test_status,
            "validate_preflight_status": self.validate_preflight_status,
            "final_live_preflight_status": self.final_live_preflight_status,
            "kraken_ohlc_interval_minutes": self.kraken_ohlc_interval_minutes,
            "kraken_history_length": self.kraken_history_length,
            "warnings": self.warnings,
        }


def resolve_runtime_components(
    settings: Settings,
) -> tuple[MarketDataProvider, ExecutionProvider, RuntimeModeState]:
    warnings: list[str] = []
    market_provider: MarketDataProvider = MockMarketDataProvider(settings.symbols)
    execution_provider: ExecutionProvider = PaperExecutor()
    effective_market_mode = MARKET_DATA_MODE_MOCK
    effective_execution_mode = EXECUTION_MODE_PAPER
    requested_kraken_backend: str | None = None
    effective_kraken_backend: str | None = None
    requested_kraken_execution_mode: str | None = None
    effective_kraken_execution_mode: str | None = None
    market_data_provider = "Mock Deterministic Demo"
    market_data_status = MARKET_DATA_STATUS_NOT_REQUESTED
    kraken_cli_status = KRAKEN_CLI_STATUS_NOT_REQUESTED
    market_data_source_type = "mock"
    execution_provider_name = execution_provider.provider_name
    execution_status = EXECUTION_STATUS_ACTIVE
    execution_source_type = execution_provider.source_type
    auth_test_status: str | None = None
    validate_preflight_status: str | None = None
    final_live_preflight_status: str | None = None

    if settings.market_data_mode == MARKET_DATA_MODE_KRAKEN:
        requested_kraken_backend = settings.kraken_backend
        if settings.kraken_backend == KRAKEN_BACKEND_CLI:
            try:
                kraken_provider = _build_kraken_cli_provider(settings)
                kraken_provider.ensure_available()
            except KrakenCliError as exc:
                if settings.kraken_cli_allow_fallback_to_rest:
                    warnings.append(
                        "Kraken CLI market data is unavailable "
                        f"({exc}). Falling back to Kraken public REST."
                    )
                    (
                        market_provider,
                        effective_market_mode,
                        effective_kraken_backend,
                        market_data_provider,
                        market_data_status,
                        market_data_source_type,
                    ) = _resolve_rest_market_provider(settings, warnings)
                    if effective_market_mode == MARKET_DATA_MODE_KRAKEN:
                        kraken_cli_status = KRAKEN_CLI_STATUS_FALLBACK_TO_REST
                    elif effective_market_mode == MARKET_DATA_MODE_MOCK:
                        kraken_cli_status = KRAKEN_CLI_STATUS_FALLBACK_TO_MOCK
                    else:
                        kraken_cli_status = KRAKEN_CLI_STATUS_UNAVAILABLE
                elif settings.kraken_allow_fallback_to_mock:
                    warnings.append(
                        "Kraken CLI market data is unavailable "
                        f"({exc}). Kraken REST fallback is disabled, so Aegis is using mock market data."
                    )
                    market_provider = MockMarketDataProvider(settings.symbols)
                    effective_market_mode = MARKET_DATA_MODE_MOCK
                    effective_kraken_backend = None
                    market_data_provider = "Mock Deterministic Demo"
                    market_data_status = MARKET_DATA_STATUS_FALLBACK_TO_MOCK
                    kraken_cli_status = KRAKEN_CLI_STATUS_FALLBACK_TO_MOCK
                    market_data_source_type = "mock"
                else:
                    warnings.append(
                        "Kraken CLI market data is unavailable "
                        f"({exc}). All fallbacks are disabled, so engine runs are blocked."
                    )
                    market_provider = MockMarketDataProvider(settings.symbols)
                    effective_market_mode = "unavailable"
                    effective_kraken_backend = None
                    market_data_provider = "Kraken Official CLI"
                    market_data_status = MARKET_DATA_STATUS_UNAVAILABLE
                    kraken_cli_status = KRAKEN_CLI_STATUS_UNAVAILABLE
                    market_data_source_type = "cli-json"
            else:
                market_provider = kraken_provider
                effective_market_mode = MARKET_DATA_MODE_KRAKEN
                effective_kraken_backend = KRAKEN_BACKEND_CLI
                market_data_provider = kraken_provider.provider_name
                market_data_status = MARKET_DATA_STATUS_ACTIVE
                kraken_cli_status = KRAKEN_CLI_STATUS_ACTIVE
                market_data_source_type = kraken_provider.source_type
        else:
            (
                market_provider,
                effective_market_mode,
                effective_kraken_backend,
                market_data_provider,
                market_data_status,
                market_data_source_type,
            ) = _resolve_rest_market_provider(settings, warnings)

    if settings.execution_mode == EXECUTION_MODE_KRAKEN:
        requested_kraken_execution_mode = settings.kraken_execution_mode
        if settings.kraken_execution_mode == KRAKEN_EXECUTION_MODE_PAPER:
            try:
                kraken_execution = _build_kraken_cli_paper_executor(settings)
                kraken_execution.ensure_paper_ready(settings.starting_cash)
            except KrakenCliExecutionError as exc:
                if settings.kraken_execution_allow_fallback_to_internal_paper:
                    warnings.append(
                        "Kraken CLI paper execution is unavailable "
                        f"({exc}). Falling back to the internal paper executor."
                    )
                    execution_provider = PaperExecutor()
                    effective_execution_mode = EXECUTION_MODE_PAPER
                    effective_kraken_execution_mode = None
                    execution_provider_name = execution_provider.provider_name
                    execution_status = EXECUTION_STATUS_FALLBACK_TO_INTERNAL_PAPER
                    execution_source_type = execution_provider.source_type
                else:
                    warnings.append(
                        "Kraken CLI paper execution is unavailable "
                        f"({exc}). Internal paper fallback is disabled, so execution is blocked."
                    )
                    execution_provider = KrakenExecutorStub()
                    effective_execution_mode = EXECUTION_MODE_BLOCKED
                    effective_kraken_execution_mode = KRAKEN_EXECUTION_MODE_PAPER
                    execution_provider_name = "Kraken CLI Paper Suite"
                    execution_status = EXECUTION_STATUS_BLOCKED
                    execution_source_type = "cli-paper"
            else:
                execution_provider = kraken_execution
                effective_execution_mode = EXECUTION_MODE_KRAKEN
                effective_kraken_execution_mode = KRAKEN_EXECUTION_MODE_PAPER
                execution_provider_name = kraken_execution.provider_name
                execution_status = EXECUTION_STATUS_ACTIVE
                execution_source_type = kraken_execution.source_type
        else:
            try:
                execution_provider = _build_kraken_cli_live_preflight_executor(settings)
            except KrakenCliExecutionError as exc:
                warnings.append(
                    "Kraken live preflight is not runnable "
                    f"({exc}). Live readiness remains blocked in this milestone."
                )
                execution_provider = KrakenExecutorStub()
                effective_execution_mode = "kraken_live_preflight"
                effective_kraken_execution_mode = KRAKEN_EXECUTION_MODE_LIVE
                execution_provider_name = execution_provider.provider_name
                execution_status = EXECUTION_STATUS_BLOCKED
                execution_source_type = execution_provider.source_type
            else:
                effective_execution_mode = "kraken_live_preflight"
                effective_kraken_execution_mode = KRAKEN_EXECUTION_MODE_LIVE
                execution_provider_name = execution_provider.provider_name
                execution_status = EXECUTION_STATUS_PREFLIGHT_ONLY
                execution_source_type = execution_provider.source_type

    live_readiness = build_live_readiness_snapshot(
        settings,
        requested_execution_mode=settings.execution_mode,
        requested_kraken_execution_mode=requested_kraken_execution_mode,
    )
    mode_state = RuntimeModeState(
        requested_market_data_mode=settings.market_data_mode,
        effective_market_data_mode=effective_market_mode,
        requested_execution_mode=settings.execution_mode,
        effective_execution_mode=effective_execution_mode,
        requested_kraken_backend=requested_kraken_backend,
        effective_kraken_backend=effective_kraken_backend,
        requested_kraken_execution_mode=requested_kraken_execution_mode,
        effective_kraken_execution_mode=effective_kraken_execution_mode,
        market_data_provider=market_data_provider,
        market_data_status=market_data_status,
        kraken_cli_status=kraken_cli_status,
        market_data_source_type=market_data_source_type,
        execution_provider=execution_provider_name,
        execution_status=execution_status,
        execution_source_type=execution_source_type,
        live_readiness_status=str(live_readiness.get("status", "UNKNOWN")),
        live_readiness=live_readiness,
        auth_test_status=auth_test_status,
        validate_preflight_status=validate_preflight_status,
        final_live_preflight_status=final_live_preflight_status,
        kraken_ohlc_interval_minutes=settings.kraken_ohlc_interval_minutes,
        kraken_history_length=settings.kraken_history_length,
        warnings=warnings,
    )
    return market_provider, execution_provider, mode_state


def _build_kraken_rest_provider(settings: Settings) -> KrakenPublicMarketDataProvider:
    return KrakenPublicMarketDataProvider(
        symbols=settings.symbols,
        base_url=settings.kraken_base_url,
        timeout_seconds=settings.kraken_timeout_seconds,
        ohlc_interval_minutes=settings.kraken_ohlc_interval_minutes,
        history_length=settings.kraken_history_length,
        user_agent=settings.kraken_user_agent,
    )


def _build_kraken_cli_provider(settings: Settings) -> KrakenCliMarketDataProvider:
    return KrakenCliMarketDataProvider(
        symbols=settings.symbols,
        command_prefix=settings.kraken_cli_command,
        timeout_seconds=settings.kraken_cli_timeout_seconds,
        ohlc_interval_minutes=settings.kraken_ohlc_interval_minutes,
        history_length=settings.kraken_history_length,
    )


def _build_kraken_cli_paper_executor(settings: Settings) -> KrakenCliPaperExecutor:
    return KrakenCliPaperExecutor(
        command_prefix=settings.kraken_cli_command,
        timeout_seconds=settings.kraken_cli_timeout_seconds,
    )


def _build_kraken_cli_live_preflight_executor(settings: Settings) -> KrakenCliLivePreflightExecutor:
    return KrakenCliLivePreflightExecutor(
        command_prefix=settings.kraken_cli_command,
        timeout_seconds=settings.kraken_cli_timeout_seconds,
    )


def _resolve_rest_market_provider(
    settings: Settings,
    warnings: list[str],
) -> tuple[MarketDataProvider, str, str | None, str, str, str]:
    try:
        kraken_provider = _build_kraken_rest_provider(settings)
        kraken_provider.ensure_available()
    except KrakenMarketDataError as exc:
        if settings.kraken_allow_fallback_to_mock:
            warnings.append(
                "Kraken public REST market data is unavailable "
                f"({exc}). Using mock market data for this session."
            )
            return (
                MockMarketDataProvider(settings.symbols),
                MARKET_DATA_MODE_MOCK,
                None,
                "Mock Deterministic Demo",
                MARKET_DATA_STATUS_FALLBACK_TO_MOCK,
                "mock",
            )
        warnings.append(
            "Kraken public REST market data is unavailable "
            f"({exc}). Fallback to mock is disabled, so engine runs are blocked."
        )
        return (
            MockMarketDataProvider(settings.symbols),
            "unavailable",
            None,
            "Kraken Public REST",
            MARKET_DATA_STATUS_UNAVAILABLE,
            "public-rest",
        )

    return (
        kraken_provider,
        MARKET_DATA_MODE_KRAKEN,
        KRAKEN_BACKEND_REST,
        kraken_provider.provider_name,
        MARKET_DATA_STATUS_ACTIVE,
        kraken_provider.source_type,
    )


def run_engine_cycle(settings: Settings | None = None) -> EngineCycleResult:
    settings = settings or load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    settings.ensure_paths()

    provider, executor, mode_state = resolve_runtime_components(settings)
    if mode_state.market_data_status == MARKET_DATA_STATUS_UNAVAILABLE:
        raise KrakenMarketDataError(_unavailable_market_data_message(mode_state))
    strategy = RegimeStrategy()
    risk_engine = RiskEngine(settings)
    run_id = str(uuid4())
    agent_identity = build_agent_identity(settings, mode_state.to_dict())

    with get_connection(settings.db_path) as connection:
        init_db(connection)
        histories = provider.get_histories()
        latest_prices = {symbol: history[-1] for symbol, history in histories.items()}
        refresh_position_prices(connection, latest_prices)
        signals = strategy.generate_signals(histories)

        executed_count = 0
        blocked_count = 0
        artifact_count = 0
        order_count = 0
        receipt_count = 0
        executable_decisions: list[dict[str, Any]] = []
        live_preflight_summary: dict[str, Any] | None = None

        for signal in signals:
            insert_signal(connection, signal)
            if not signal.should_execute:
                continue

            quantity = _suggest_quantity(connection, settings, signal, latest_prices[signal.symbol])
            position = get_position(connection, signal.symbol)
            existing_position_qty = float(position["quantity"]) if position else 0.0
            cash_balance = get_cash_balance(connection, settings.starting_cash)
            daily_drawdown = _current_drawdown(connection, settings)
            consecutive_losses = _consecutive_losses(connection, settings.cooldown_after_losses)
            open_positions = count_open_positions(connection)

            risk_decision = risk_engine.assess(
                signal=signal,
                quantity=quantity,
                price=latest_prices[signal.symbol],
                cash_balance=cash_balance,
                open_positions=open_positions,
                existing_position_qty=existing_position_qty,
                daily_drawdown=daily_drawdown,
                consecutive_losses=consecutive_losses,
            )

            if not risk_decision.allowed:
                blocked_count += 1
                insert_blocked_trade(
                    connection,
                    symbol=signal.symbol,
                    side=signal.action,
                    attempted_quantity=quantity,
                    attempted_price=latest_prices[signal.symbol],
                    block_reason=risk_decision.summary(),
                    context={
                        "signal_reason": signal.reason,
                        "risk_reason_codes": risk_decision.reason_codes,
                        "indicators": signal.indicators,
                        "execution_provider": mode_state.execution_provider,
                        "execution_status": mode_state.execution_status,
                    },
                )
                logger.info("Blocked %s %s: %s", signal.action, signal.symbol, risk_decision.summary())
                continue

            executable_decisions.append(
                {
                    "signal": signal,
                    "risk_decision": risk_decision,
                    "quantity": quantity,
                    "price": latest_prices[signal.symbol],
                }
            )

        live_candidate_count = (
            len(executable_decisions)
            if mode_state.requested_execution_mode == EXECUTION_MODE_KRAKEN
            and mode_state.requested_kraken_execution_mode == KRAKEN_EXECUTION_MODE_LIVE
            else None
        )

        for decision in executable_decisions:
            signal = decision["signal"]
            risk_decision = decision["risk_decision"]
            quantity = float(decision["quantity"])
            signal_price = float(decision["price"])
            artifact_payload = build_trade_intent(
                run_id=run_id,
                signal=signal,
                risk_decision=risk_decision,
                quantity=quantity,
                price=signal_price,
                latest_price=signal_price,
                mode_summary=mode_state.to_dict(),
                agent_identity=agent_identity,
            )
            artifact_meta = save_trade_artifact(connection, settings, artifact_payload)
            artifact_count += 1

            request = ExecutionRequest(
                run_id=run_id,
                symbol=signal.symbol,
                side=signal.action,
                quantity=quantity,
                price=signal_price,
                order_type="market",
                artifact_id=artifact_meta["artifact_id"],
                requested_execution_mode=mode_state.requested_execution_mode,
                requested_kraken_execution_mode=mode_state.requested_kraken_execution_mode,
                requested_execution_provider=mode_state.execution_provider,
                mode_summary=mode_state.to_dict(),
                signal_reason=signal.reason,
            )

            if mode_state.requested_execution_mode == EXECUTION_MODE_KRAKEN and (
                mode_state.requested_kraken_execution_mode == KRAKEN_EXECUTION_MODE_LIVE
            ):
                daily_live_notional = get_daily_live_preflight_notional(connection)
                live_readiness = build_live_readiness_snapshot(
                    settings,
                    requested_execution_mode=mode_state.requested_execution_mode,
                    requested_kraken_execution_mode=mode_state.requested_kraken_execution_mode,
                    candidate_symbol=signal.symbol,
                    candidate_notional=round(quantity * signal_price, 6),
                    live_candidate_count=live_candidate_count,
                    daily_live_notional=daily_live_notional,
                )
                mode_state.live_readiness = live_readiness
                mode_state.live_readiness_status = str(live_readiness.get("status", "UNKNOWN"))
                request.mode_summary = mode_state.to_dict()

                if mode_state.execution_status == EXECUTION_STATUS_BLOCKED or not live_preflight_can_run(live_readiness):
                    mode_state.execution_status = EXECUTION_STATUS_BLOCKED
                    mode_state.auth_test_status = "NOT_RUN"
                    mode_state.validate_preflight_status = "NOT_RUN"
                    mode_state.final_live_preflight_status = "BLOCKED"
                    blocked_count += 1
                    outcome = _build_live_preflight_outcome(
                        request=request,
                        execution_provider=mode_state.execution_provider,
                        execution_source_type=mode_state.execution_source_type,
                        status="BLOCKED",
                        auth_test_status="NOT_RUN",
                        validate_preflight_status="NOT_RUN",
                        live_preflight_status="BLOCKED",
                        external_status="blocked",
                        provider_metadata={
                            "readiness": live_readiness,
                            "requested_notional": round(quantity * signal_price, 6),
                            "no_live_submit_performed": True,
                        },
                        notes="Kraken live preflight was blocked before auth and validate checks.",
                    )
                else:
                    preflight_executor = _build_kraken_cli_live_preflight_executor(settings)
                    try:
                        auth_payload = preflight_executor.auth_test()
                    except KrakenCliExecutionError as exc:
                        mode_state.execution_status = EXECUTION_STATUS_PREFLIGHT_FAILED
                        mode_state.auth_test_status = "FAILED"
                        mode_state.validate_preflight_status = "NOT_RUN"
                        mode_state.final_live_preflight_status = "PREFLIGHT_FAILED"
                        live_readiness = {
                            **live_readiness,
                            "status": LIVE_READINESS_STATUS_PREFLIGHT_FAILED,
                            "summary": "Kraken auth test failed before validate preflight.",
                            "auth_test_status": "FAILED",
                            "validate_preflight_status": "NOT_RUN",
                            "preflight_ran": True,
                        }
                        blocked_count += 1
                        outcome = _build_live_preflight_outcome(
                            request=request,
                            execution_provider=preflight_executor.provider_name,
                            execution_source_type=preflight_executor.source_type,
                            status="PREFLIGHT_FAILED",
                            auth_test_status="FAILED",
                            validate_preflight_status="NOT_RUN",
                            live_preflight_status="PREFLIGHT_FAILED",
                            external_status="auth_failed",
                            provider_metadata={
                                "auth_test_error": str(exc),
                                "requested_notional": round(quantity * signal_price, 6),
                                "no_live_submit_performed": True,
                            },
                            notes="Kraken auth test failed. No live submit was performed.",
                        )
                    else:
                        try:
                            validate_payload = preflight_executor.validate_market_order(request)
                        except KrakenCliExecutionError as exc:
                            mode_state.execution_status = EXECUTION_STATUS_PREFLIGHT_FAILED
                            mode_state.auth_test_status = "PASSED"
                            mode_state.validate_preflight_status = "FAILED"
                            mode_state.final_live_preflight_status = "PREFLIGHT_FAILED"
                            live_readiness = {
                                **live_readiness,
                                "status": LIVE_READINESS_STATUS_PREFLIGHT_FAILED,
                                "summary": "Kraken auth test passed, but validate preflight failed.",
                                "auth_test_status": "PASSED",
                                "validate_preflight_status": "FAILED",
                                "preflight_ran": True,
                            }
                            blocked_count += 1
                            outcome = _build_live_preflight_outcome(
                                request=request,
                                execution_provider=preflight_executor.provider_name,
                                execution_source_type=preflight_executor.source_type,
                                status="PREFLIGHT_FAILED",
                                auth_test_status="PASSED",
                                validate_preflight_status="FAILED",
                                live_preflight_status="PREFLIGHT_FAILED",
                                external_status="validate_failed",
                                provider_metadata={
                                    "auth_test": auth_payload,
                                    "validate_preflight_error": str(exc),
                                    "requested_notional": round(quantity * signal_price, 6),
                                    "no_live_submit_performed": True,
                                },
                                notes="Kraken validate preflight failed. No live submit was performed.",
                            )
                        else:
                            mode_state.execution_status = EXECUTION_STATUS_PREFLIGHT_PASSED
                            mode_state.auth_test_status = "PASSED"
                            mode_state.validate_preflight_status = "PASSED"
                            mode_state.final_live_preflight_status = "PREFLIGHT_PASSED"
                            live_readiness = {
                                **live_readiness,
                                "status": LIVE_READINESS_STATUS_PREFLIGHT_PASSED,
                                "summary": "Kraken auth test and validate preflight both passed. No live submit was performed.",
                                "auth_test_status": "PASSED",
                                "validate_preflight_status": "PASSED",
                                "preflight_ran": True,
                            }
                            outcome = _build_live_preflight_outcome(
                                request=request,
                                execution_provider=preflight_executor.provider_name,
                                execution_source_type=preflight_executor.source_type,
                                status="PREFLIGHT_PASSED",
                                auth_test_status="PASSED",
                                validate_preflight_status="PASSED",
                                live_preflight_status="PREFLIGHT_PASSED",
                                external_status="validated",
                                provider_metadata={
                                    "auth_test": auth_payload,
                                    "validate_preflight": validate_payload,
                                    "requested_notional": round(quantity * signal_price, 6),
                                    "no_live_submit_performed": True,
                                },
                                notes="Kraken live preflight passed auth and validate checks. No live submit was performed.",
                            )
                    mode_state.live_readiness = live_readiness
                    mode_state.live_readiness_status = str(live_readiness.get("status", "UNKNOWN"))

                request.mode_summary = mode_state.to_dict()
                persisted = apply_execution_outcome(connection, outcome, reason=signal.reason)
                order_count += 1
                receipt_payload = build_execution_receipt(
                    run_id=run_id,
                    symbol=signal.symbol,
                    trade_intent_artifact_id=artifact_meta["artifact_id"],
                    outcome=outcome,
                    persisted=persisted,
                    mode_summary=mode_state.to_dict(),
                    agent_identity=agent_identity,
                    safety_snapshot=mode_state.live_readiness,
                )
                save_artifact(connection, settings, receipt_payload, notes="Live preflight execution receipt.")
                artifact_count += 1
                receipt_count += 1
                live_preflight_summary = {
                    "symbol": signal.symbol,
                    "status": outcome.status,
                    "auth_test_status": outcome.auth_test_status,
                    "validate_preflight_status": outcome.validate_preflight_status,
                    "order_id": outcome.local_order_id,
                    "artifact_id": artifact_meta["artifact_id"],
                    "receipt_live_preflight_status": outcome.live_preflight_status,
                }
                logger.info("Recorded live preflight for %s %s with status %s", signal.action, signal.symbol, outcome.status)
                continue

            if mode_state.execution_status == EXECUTION_STATUS_BLOCKED or live_execution_is_blocked(
                mode_state.live_readiness
            ):
                blocked_count += 1
                insert_blocked_trade(
                    connection,
                    symbol=signal.symbol,
                    side=signal.action,
                    attempted_quantity=quantity,
                    attempted_price=latest_prices[signal.symbol],
                    block_reason=_execution_block_message(mode_state),
                    context={
                        "signal_reason": signal.reason,
                        "risk_reason_codes": risk_decision.reason_codes,
                        "indicators": signal.indicators,
                        "execution_provider": mode_state.execution_provider,
                        "execution_status": mode_state.execution_status,
                        "live_readiness": mode_state.live_readiness,
                        "artifact_id": artifact_meta["artifact_id"],
                    },
                )
                logger.info("Execution blocked for %s %s", signal.action, signal.symbol)
                continue

            try:
                outcome = executor.execute(connection=connection, request=request)
            except KrakenCliExecutionError as exc:
                if settings.kraken_execution_allow_fallback_to_internal_paper:
                    warnings = list(mode_state.warnings)
                    warnings.append(
                        f"Kraken CLI paper execution failed during order placement ({exc}). Falling back to the internal paper executor."
                    )
                    mode_state.execution_provider = PaperExecutor.provider_name
                    mode_state.execution_status = EXECUTION_STATUS_FALLBACK_TO_INTERNAL_PAPER
                    mode_state.execution_source_type = PaperExecutor.source_type
                    mode_state.effective_execution_mode = EXECUTION_MODE_PAPER
                    mode_state.effective_kraken_execution_mode = None
                    mode_state.warnings = warnings
                    request.mode_summary = mode_state.to_dict()
                    outcome = PaperExecutor().execute(connection=connection, request=request)
                else:
                    raise

            persisted = apply_execution_outcome(connection, outcome, reason=signal.reason)
            order_count += 1
            if persisted.get("trade_id"):
                executed_count += 1

            receipt_payload = build_execution_receipt(
                run_id=run_id,
                symbol=signal.symbol,
                trade_intent_artifact_id=artifact_meta["artifact_id"],
                outcome=outcome,
                persisted=persisted,
                mode_summary=mode_state.to_dict(),
                agent_identity=agent_identity,
                safety_snapshot=mode_state.live_readiness,
            )
            save_artifact(connection, settings, receipt_payload, notes="Post-execution receipt.")
            artifact_count += 1
            receipt_count += 1
            logger.info("Executed %s %s via %s", signal.action, signal.symbol, outcome.execution_provider)

        metrics = upsert_daily_metrics(connection, settings, latest_prices)
        summary = {
            "signal_count": len(signals),
            "executed_count": executed_count,
            "blocked_count": blocked_count,
            "order_count": order_count,
            "artifact_count": artifact_count,
            "receipt_count": receipt_count,
            "latest_prices": latest_prices,
            "metrics": metrics,
            "modes": mode_state.to_dict(),
            "latest_live_preflight": live_preflight_summary,
        }
        record_agent_run(connection, run_id=run_id, status="COMPLETED", summary=summary)

    return EngineCycleResult(
        run_id=run_id,
        signal_count=len(signals),
        executed_count=executed_count,
        blocked_count=blocked_count,
        latest_prices=latest_prices,
        summary=summary,
        order_count=order_count,
        artifact_count=artifact_count,
        receipt_count=receipt_count,
    )


def reset_demo_state(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or load_settings()
    local_reset = reset_runtime_state(settings)
    execution_reset = None
    warnings: list[str] = []

    if (
        settings.execution_mode == EXECUTION_MODE_KRAKEN
        and settings.kraken_execution_mode == KRAKEN_EXECUTION_MODE_PAPER
    ):
        try:
            execution_reset = _build_kraken_cli_paper_executor(settings).reset_and_init(
                settings.starting_cash
            )
        except KrakenCliExecutionError as exc:
            warnings.append(f"Kraken CLI paper state was not reset: {exc}")

    return {
        "local_reset": local_reset,
        "execution_reset": execution_reset,
        "warnings": warnings,
    }


def reseed_demo_state(settings: Settings | None = None, cycles: int = 2) -> dict[str, object]:
    settings = settings or load_settings()
    cycles = max(1, cycles)
    if (
        settings.execution_mode == EXECUTION_MODE_KRAKEN
        and settings.kraken_execution_mode == KRAKEN_EXECUTION_MODE_LIVE
    ):
        raise KrakenCliExecutionError(
            "Kraken live preflight is single-cycle only in this milestone. Reseed remains disabled for live readiness mode."
        )

    reset_summary = reset_demo_state(settings)
    cycle_results: list[dict[str, object]] = []
    for _ in range(cycles):
        cycle_results.append(run_engine_cycle(settings).to_dict())

    return {
        "cycles": cycles,
        "reset": reset_summary,
        "results": cycle_results,
    }


def _suggest_quantity(connection, settings: Settings, signal: Signal, price: float) -> float:
    if signal.action == "BUY":
        cash_balance = get_cash_balance(connection, settings.starting_cash)
        target_fraction = min(settings.trade_fraction, settings.max_risk_per_trade) * 0.99
        notional = min(cash_balance * target_fraction, cash_balance)
        quantity = notional / price if price > 0 else 0.0
        return round(quantity, 6)

    if signal.action == "SELL":
        position = get_position(connection, signal.symbol)
        if position is None:
            return 0.0
        return round(float(position["quantity"]), 6)

    return 0.0


def _consecutive_losses(connection, limit: int) -> int:
    recent_pnls = get_recent_trade_pnls(connection, limit=limit)
    losses = 0
    for pnl in recent_pnls:
        if pnl < 0:
            losses += 1
            continue
        break
    return losses


def _current_drawdown(connection, settings: Settings) -> float:
    cash_balance = get_cash_balance(connection, settings.starting_cash)
    market_value = get_total_market_value(connection)
    equity = cash_balance + market_value
    return max(0.0, (settings.starting_cash - equity) / settings.starting_cash)


def _unavailable_market_data_message(mode_state: RuntimeModeState) -> str:
    if mode_state.requested_kraken_backend == KRAKEN_BACKEND_CLI:
        return (
            "Kraken CLI market data is unavailable and no allowed fallback remained. "
            "Aegis did not run this cycle."
        )
    return (
        "Kraken public market data is unavailable and fallback to mock is disabled. "
        "Aegis did not run this cycle."
    )


def _execution_block_message(mode_state: RuntimeModeState) -> str:
    if mode_state.requested_kraken_execution_mode == KRAKEN_EXECUTION_MODE_LIVE:
        return "KRAKEN_LIVE_DISABLED"
    return "EXECUTION_BLOCKED"


def _build_live_preflight_outcome(
    request: ExecutionRequest,
    execution_provider: str,
    execution_source_type: str,
    *,
    status: str,
    auth_test_status: str,
    validate_preflight_status: str,
    live_preflight_status: str,
    external_status: str,
    provider_metadata: dict[str, Any],
    notes: str,
) -> ExecutionOutcome:
    return executor_outcome_factory(
        request=request,
        execution_provider=execution_provider,
        execution_source_type=execution_source_type,
        status=status,
        auth_test_status=auth_test_status,
        validate_preflight_status=validate_preflight_status,
        live_preflight_status=live_preflight_status,
        external_status=external_status,
        provider_metadata=provider_metadata,
        notes=notes,
    )


def executor_outcome_factory(
    request: ExecutionRequest,
    execution_provider: str,
    execution_source_type: str,
    *,
    status: str,
    auth_test_status: str,
    validate_preflight_status: str,
    live_preflight_status: str,
    external_status: str,
    provider_metadata: dict[str, Any],
    notes: str,
) -> ExecutionOutcome:
    return ExecutionOutcome(
        run_id=request.run_id,
        local_order_id=str(uuid4()),
        symbol=request.symbol,
        side=request.side.upper(),
        quantity=round(request.quantity, 6),
        filled_quantity=0.0,
        price=round(request.price, 6),
        fill_price=0.0,
        notional=round(request.quantity * request.price, 6),
        artifact_id=request.artifact_id,
        order_type=request.order_type,
        status=status,
        execution_provider=execution_provider,
        execution_source_type=execution_source_type,
        requested_execution_mode=request.requested_execution_mode,
        effective_execution_mode="kraken_live_preflight",
        requested_kraken_execution_mode=request.requested_kraken_execution_mode,
        effective_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
        provider_metadata=provider_metadata,
        external_status=external_status,
        auth_test_status=auth_test_status,
        validate_preflight_status=validate_preflight_status,
        live_preflight_status=live_preflight_status,
        notes=notes,
    )
