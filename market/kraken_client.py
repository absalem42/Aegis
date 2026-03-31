from __future__ import annotations


class KrakenMarketClientStub:
    """Non-live placeholder for a future Kraken market-data adapter."""

    mode_name = "kraken"

    def availability_note(self) -> str:
        return "Kraken market data is not available in Aegis v0. Use mock mode for local demos."

    def get_latest_prices(self) -> dict[str, float]:
        raise NotImplementedError("Kraken market data is deferred in Aegis v0.")

    def get_price_history(self, symbol: str, length: int = 60) -> list[float]:
        raise NotImplementedError("Kraken market data is deferred in Aegis v0.")

    def get_histories(self, length: int = 60) -> dict[str, list[float]]:
        raise NotImplementedError("Kraken market data is deferred in Aegis v0.")
