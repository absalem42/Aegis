from __future__ import annotations

from typing import Protocol

from .kraken_cli import KrakenCliError, KrakenCliMarketDataProvider
from .kraken_client import KrakenMarketDataError, KrakenPublicMarketDataProvider
from .mock_data import MockMarketDataProvider


class MarketDataProvider(Protocol):
    def get_latest_prices(self) -> dict[str, float]: ...
    def get_price_history(self, symbol: str, length: int = 60) -> list[float]: ...
    def get_histories(self, length: int = 60) -> dict[str, list[float]]: ...

__all__ = [
    "KrakenCliError",
    "KrakenCliMarketDataProvider",
    "KrakenMarketDataError",
    "KrakenPublicMarketDataProvider",
    "MarketDataProvider",
    "MockMarketDataProvider",
]
