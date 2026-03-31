from __future__ import annotations

from models import Signal


def _ema(values: list[float], period: int) -> float:
    multiplier = 2 / (period + 1)
    ema_value = values[0]
    for value in values[1:]:
        ema_value = (value - ema_value) * multiplier + ema_value
    return round(ema_value, 6)


class RegimeStrategy:
    def generate_signals(self, histories: dict[str, list[float]]) -> list[Signal]:
        signals: list[Signal] = []
        for symbol, prices in histories.items():
            price = prices[-1]
            ema20 = _ema(prices[-20:], 20)
            ema50 = _ema(prices[-50:], 50)
            recent_high = max(prices[-10:-1])
            recent_low = min(prices[-10:-1])

            indicators = {
                "price": round(price, 6),
                "ema20": ema20,
                "ema50": ema50,
                "recent_high": round(recent_high, 6),
                "recent_low": round(recent_low, 6),
            }

            if price > ema20 > ema50 and price >= recent_high * 1.001:
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="BUY",
                        reason="EMA_BULLISH_BREAKOUT",
                        indicators=indicators,
                        should_execute=True,
                    )
                )
                continue

            if price > ema20 > ema50 and price <= ema20 * 1.005:
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="BUY",
                        reason="EMA_BULLISH_PULLBACK",
                        indicators=indicators,
                        should_execute=True,
                    )
                )
                continue

            if price < ema20 < ema50 and price <= recent_low * 0.999:
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="SELL",
                        reason="EMA_BEARISH_BREAKDOWN",
                        indicators=indicators,
                        should_execute=True,
                    )
                )
                continue

            if price < ema20 < ema50 and price >= ema20 * 0.995:
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="SELL",
                        reason="EMA_BEARISH_REVERSION",
                        indicators=indicators,
                        should_execute=True,
                    )
                )
                continue

            signals.append(
                Signal(
                    symbol=symbol,
                    action="HOLD",
                    reason="NO_EDGE",
                    indicators=indicators,
                    should_execute=False,
                )
            )
        return signals
