from __future__ import annotations

from dataclasses import dataclass
import logging
from uuid import uuid4

from config import (
    EXECUTION_MODE_KRAKEN,
    EXECUTION_MODE_PAPER,
    KRAKEN_BACKEND_CLI,
    KRAKEN_BACKEND_REST,
    MARKET_DATA_MODE_KRAKEN,
    MARKET_DATA_MODE_MOCK,
    Settings,
    load_settings,
)
from db import (
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
    upsert_daily_metrics,
)
from execution import ExecutionProvider
from execution.kraken_executor import KrakenExecutorStub
from execution.paper_executor import PaperExecutor
from market import MarketDataProvider
from market.kraken_cli import KrakenCliError, KrakenCliMarketDataProvider
from market.kraken_client import KrakenMarketDataError, KrakenPublicMarketDataProvider
from market.mock_data import MockMarketDataProvider
from models import EngineCycleResult, Signal
from proof.agent_identity import build_agent_identity
from proof.artifact_store import save_trade_artifact
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


@dataclass(slots=True)
class RuntimeModeState:
    requested_market_data_mode: str
    effective_market_data_mode: str
    requested_execution_mode: str
    effective_execution_mode: str
    requested_kraken_backend: str | None
    effective_kraken_backend: str | None
    market_data_provider: str
    market_data_status: str
    kraken_cli_status: str
    market_data_source_type: str
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
            "market_data_provider": self.market_data_provider,
            "market_data_status": self.market_data_status,
            "kraken_cli_status": self.kraken_cli_status,
            "market_data_source_type": self.market_data_source_type,
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
    market_data_provider = "Mock Deterministic Demo"
    market_data_status = MARKET_DATA_STATUS_NOT_REQUESTED
    kraken_cli_status = KRAKEN_CLI_STATUS_NOT_REQUESTED
    market_data_source_type = "deterministic-demo"

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
                    market_data_source_type = "deterministic-demo"
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
        warnings.append(
            "Kraken execution mode is stubbed in v0. Using paper execution for this session."
        )
        _ = KrakenExecutorStub()

    mode_state = RuntimeModeState(
        requested_market_data_mode=settings.market_data_mode,
        effective_market_data_mode=effective_market_mode,
        requested_execution_mode=settings.execution_mode,
        effective_execution_mode=effective_execution_mode,
        requested_kraken_backend=requested_kraken_backend,
        effective_kraken_backend=effective_kraken_backend,
        market_data_provider=market_data_provider,
        market_data_status=market_data_status,
        kraken_cli_status=kraken_cli_status,
        market_data_source_type=market_data_source_type,
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
                "deterministic-demo",
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

            executor.execute(
                connection=connection,
                signal=signal,
                quantity=quantity,
                price=latest_prices[signal.symbol],
                artifact_id=artifact_meta["artifact_id"],
            )
            executed_count += 1
            logger.info("Executed %s %s", signal.action, signal.symbol)

        metrics = upsert_daily_metrics(connection, settings, latest_prices)
        summary = {
            "signal_count": len(signals),
            "executed_count": executed_count,
            "blocked_count": blocked_count,
            "artifact_count": artifact_count,
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
    )


def reseed_demo_state(settings: Settings | None = None, cycles: int = 2) -> dict[str, object]:
    settings = settings or load_settings()
    cycles = max(1, cycles)

    from db import reset_runtime_state

    reset_summary = reset_runtime_state(settings)
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
