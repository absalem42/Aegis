from __future__ import annotations


class KrakenMarketClientStub:
    """Placeholder for a future Kraken market-data adapter."""

    def get_latest_prices(self) -> dict[str, float]:
        raise NotImplementedError("Kraken market data is deferred in Aegis v0.")

    def get_price_history(self, symbol: str, length: int = 60) -> list[float]:
        raise NotImplementedError("Kraken market data is deferred in Aegis v0.")
