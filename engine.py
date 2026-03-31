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
    KrakenCliPaperExecutor,
)
from execution.kraken_executor import KrakenExecutorStub
from execution.paper_executor import PaperExecutor
from execution.safety import (
    build_live_readiness_snapshot,
    live_execution_is_blocked,
)
from market import MarketDataProvider
from market.kraken_cli import KrakenCliError, KrakenCliMarketDataProvider
from market.kraken_client import KrakenMarketDataError, KrakenPublicMarketDataProvider
from market.mock_data import MockMarketDataProvider
from models import EngineCycleResult, ExecutionRequest, Signal
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
            warnings.append(
                "Kraken live execution is planned and guarded, but not enabled in this milestone."
            )
            execution_provider = KrakenExecutorStub()
            effective_execution_mode = EXECUTION_MODE_BLOCKED
            effective_kraken_execution_mode = KRAKEN_EXECUTION_MODE_LIVE
            execution_provider_name = execution_provider.provider_name
            execution_status = EXECUTION_STATUS_BLOCKED
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

            artifact_payload = build_trade_intent(
                run_id=run_id,
                signal=signal,
                risk_decision=risk_decision,
                quantity=quantity,
                price=latest_prices[signal.symbol],
                latest_price=latest_prices[signal.symbol],
                mode_summary=mode_state.to_dict(),
                agent_identity=agent_identity,
            )
            artifact_meta = save_trade_artifact(connection, settings, artifact_payload)
            artifact_count += 1

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

            request = ExecutionRequest(
                run_id=run_id,
                symbol=signal.symbol,
                side=signal.action,
                quantity=quantity,
                price=latest_prices[signal.symbol],
                order_type="market",
                artifact_id=artifact_meta["artifact_id"],
                requested_execution_mode=mode_state.requested_execution_mode,
                requested_kraken_execution_mode=mode_state.requested_kraken_execution_mode,
                requested_execution_provider=mode_state.execution_provider,
                mode_summary=mode_state.to_dict(),
                signal_reason=signal.reason,
            )

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
