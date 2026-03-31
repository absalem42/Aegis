from __future__ import annotations

import math
from typing import Iterable


class MockMarketDataProvider:
    """Deterministic demo prices for local development and tests."""

    def __init__(self, symbols: Iterable[str]):
        self.symbols = tuple(symbols)

    def get_price_history(self, symbol: str, length: int = 60) -> list[float]:
        if symbol not in {"BTC/USD", "ETH/USD", "SOL/USD"}:
            raise ValueError(f"Unsupported symbol: {symbol}")
        if length < 60:
            length = 60

        if symbol == "BTC/USD":
            series = [62000 + (i * 90) + ((i % 4) - 1.5) * 55 for i in range(length - 3)]
            series.extend([67200.0, 68050.0, 69420.0])
            return [round(value, 2) for value in series]

        if symbol == "ETH/USD":
            series = [3200 + math.sin(i / 3.0) * 22 + math.cos(i / 4.0) * 8 for i in range(length)]
            return [round(value, 2) for value in series]

        series = [188 - (i * 0.55) + math.sin(i / 4.0) * 1.2 for i in range(length - 3)]
        series.extend([156.0, 153.5, 149.25])
        return [round(value, 2) for value in series]

    def get_latest_prices(self) -> dict[str, float]:
        return {symbol: self.get_price_history(symbol)[-1] for symbol in self.symbols}

    def get_histories(self, length: int = 60) -> dict[str, list[float]]:
        return {symbol: self.get_price_history(symbol, length=length) for symbol in self.symbols}
