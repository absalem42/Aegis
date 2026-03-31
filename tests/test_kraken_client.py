import pytest

from market.kraken_client import KrakenMarketDataError, KrakenPublicMarketDataProvider


def _request_key(path: str, params: dict[str, str] | None = None) -> tuple[str, tuple[tuple[str, str], ...]]:
    return path, tuple(sorted((params or {}).items()))


def _asset_pairs_payload() -> dict[str, object]:
    return {
        "error": [],
        "result": {
            "XXBTZUSD": {
                "altname": "XBTUSD",
                "wsname": "XBT/USD",
                "base": "XXBT",
                "quote": "ZUSD",
                "status": "online",
            },
            "XETHZUSD": {
                "altname": "ETHUSD",
                "wsname": "ETH/USD",
                "base": "XETH",
                "quote": "ZUSD",
                "status": "online",
            },
            "SOLUSD": {
                "altname": "SOLUSD",
                "wsname": "SOL/USD",
                "base": "SOL",
                "quote": "ZUSD",
                "status": "online",
            },
        },
    }


def _ohlc_payload(pair_key: str, closes: list[float]) -> dict[str, object]:
    candles = []
    for index, close in enumerate(closes):
        candles.append(
            [
                1772362800 + (index * 3600),
                f"{close - 10:.1f}",
                f"{close + 15:.1f}",
                f"{close - 20:.1f}",
                f"{close:.1f}",
                f"{close - 2:.1f}",
                "12.50000000",
                1200 + index,
            ]
        )
    return {"error": [], "result": {pair_key: candles, "last": 1772362800}}


class StubKrakenProvider(KrakenPublicMarketDataProvider):
    def __init__(
        self,
        responses: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, object]],
        symbols: tuple[str, ...],
    ) -> None:
        super().__init__(
            symbols=symbols,
            base_url="https://api.kraken.com",
            timeout_seconds=5,
            ohlc_interval_minutes=60,
            history_length=60,
            user_agent="Aegis-tests",
        )
        self.responses = responses

    def _request_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, object]:
        key = _request_key(path, params)
        if key not in self.responses:
            raise AssertionError(f"Unexpected request: {key}")
        return self.responses[key]


def test_kraken_provider_resolves_aegis_symbols_and_ticker_prices():
    responses = {
        _request_key("/0/public/AssetPairs"): _asset_pairs_payload(),
        _request_key("/0/public/Ticker", {"pair": "XBTUSD,ETHUSD,SOLUSD"}): {
            "error": [],
            "result": {
                "XXBTZUSD": {"c": ["66650.4", "0.1"]},
                "XETHZUSD": {"c": ["2035.27", "0.5"]},
                "SOLUSD": {"c": ["80.65", "1.0"]},
            },
        },
    }
    provider = StubKrakenProvider(responses, symbols=("BTC/USD", "ETH/USD", "SOL/USD"))

    prices = provider.get_latest_prices()

    assert prices == {
        "BTC/USD": 66650.4,
        "ETH/USD": 2035.27,
        "SOL/USD": 80.65,
    }


def test_kraken_provider_parses_ohlc_close_history():
    closes = [66000 + index for index in range(60)]
    responses = {
        _request_key("/0/public/AssetPairs"): _asset_pairs_payload(),
        _request_key("/0/public/OHLC", {"pair": "XBTUSD", "interval": "60"}): _ohlc_payload(
            "XXBTZUSD",
            closes,
        ),
    }
    provider = StubKrakenProvider(responses, symbols=("BTC/USD",))

    history = provider.get_price_history("BTC/USD", length=60)

    assert len(history) == 60
    assert history[0] == 66000.0
    assert history[-1] == 66059.0


def test_kraken_provider_raises_on_error_response():
    responses = {
        _request_key("/0/public/AssetPairs"): {
            "error": ["EGeneral:Temporary lockout"],
            "result": {},
        }
    }
    provider = StubKrakenProvider(responses, symbols=("BTC/USD",))

    with pytest.raises(KrakenMarketDataError):
        provider.get_latest_prices()


def test_kraken_provider_raises_on_malformed_ticker_payload():
    responses = {
        _request_key("/0/public/AssetPairs"): _asset_pairs_payload(),
        _request_key("/0/public/Ticker", {"pair": "XBTUSD"}): {
            "error": [],
            "result": {"XXBTZUSD": {"c": []}},
        },
    }
    provider = StubKrakenProvider(responses, symbols=("BTC/USD",))

    with pytest.raises(KrakenMarketDataError):
        provider.get_latest_prices()
