from __future__ import annotations

import logging
from uuid import uuid4

from config import Settings, load_settings
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
from execution.paper_executor import PaperExecutor
from market.mock_data import MockMarketDataProvider
from models import EngineCycleResult, Signal
from proof.artifact_store import save_trade_artifact
from proof.trade_intent import build_trade_intent
from risk.engine import RiskEngine
from strategy.regime_strategy import RegimeStrategy

logger = logging.getLogger(__name__)


def run_engine_cycle(settings: Settings | None = None) -> EngineCycleResult:
    settings = settings or load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    settings.ensure_paths()

    provider = MockMarketDataProvider(settings.symbols)
    strategy = RegimeStrategy()
    risk_engine = RiskEngine(settings)
    executor = PaperExecutor()
    run_id = str(uuid4())

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
