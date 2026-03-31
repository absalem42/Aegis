from __future__ import annotations

from config import Settings
from models import RiskDecision, Signal


class RiskEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def assess(
        self,
        signal: Signal,
        quantity: float,
        price: float,
        cash_balance: float,
        open_positions: int,
        existing_position_qty: float,
        daily_drawdown: float,
        consecutive_losses: int,
    ) -> RiskDecision:
        reason_codes: list[str] = []

        if self.settings.kill_switch:
            reason_codes.append("KILL_SWITCH_ENABLED")

        if daily_drawdown >= self.settings.max_daily_drawdown:
            reason_codes.append("MAX_DAILY_DRAWDOWN_REACHED")

        if consecutive_losses >= self.settings.cooldown_after_losses:
            reason_codes.append("COOLDOWN_ACTIVE")

        if quantity <= 0:
            reason_codes.append("INVALID_QUANTITY")

        if signal.action == "BUY":
            if open_positions >= self.settings.max_open_positions and existing_position_qty <= 0:
                reason_codes.append("MAX_OPEN_POSITIONS_REACHED")

            if quantity * price > cash_balance * self.settings.max_risk_per_trade:
                reason_codes.append("MAX_RISK_PER_TRADE_EXCEEDED")

            if quantity * price > cash_balance:
                reason_codes.append("INSUFFICIENT_CASH")

        elif signal.action == "SELL":
            if existing_position_qty <= 0:
                reason_codes.append("NO_OPEN_POSITION")
            if quantity > existing_position_qty > 0:
                reason_codes.append("SELL_SIZE_EXCEEDS_POSITION")
        else:
            reason_codes.append("UNSUPPORTED_SIDE")

        return RiskDecision(
            allowed=not reason_codes,
            reason_codes=reason_codes,
            quantity=quantity,
            price=price,
            side=signal.action,
        )
