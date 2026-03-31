from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class KrakenMarketDataError(RuntimeError):
    """Raised when Kraken public market data is unavailable or malformed."""


@dataclass(slots=True)
class ResolvedKrakenPair:
    aegis_symbol: str
    pair_id: str
    altname: str
    wsname: str
    status: str

    @property
    def query_pair(self) -> str:
        return self.altname or self.pair_id

    @property
    def response_keys(self) -> tuple[str, ...]:
        wsname_compact = self.wsname.replace("/", "") if self.wsname else ""
        return tuple(
            key
            for key in (self.pair_id, self.altname, wsname_compact)
            if key
        )


class KrakenPublicMarketDataProvider:
    """Kraken public REST market-data provider for safe paper-trading demos."""

    mode_name = "kraken"
    provider_name = "Kraken Public REST"
    source_type = "public-rest"

    def __init__(
        self,
        symbols: Iterable[str],
        base_url: str,
        timeout_seconds: float,
        ohlc_interval_minutes: int,
        history_length: int,
        user_agent: str,
    ) -> None:
        self.symbols = tuple(symbols)
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.ohlc_interval_minutes = max(1, int(ohlc_interval_minutes))
        self.history_length = max(60, int(history_length))
        self.user_agent = user_agent
        self._pair_map: dict[str, ResolvedKrakenPair] | None = None
        self._latest_prices_cache: dict[str, float] | None = None
        self._history_cache: dict[tuple[str, int], list[float]] = {}

    def availability_note(self) -> str:
        return "Kraken public market data is available while execution remains local paper-only."

    def ensure_available(self) -> None:
        prices = self.get_latest_prices()
        missing = [symbol for symbol in self.symbols if symbol not in prices]
        if missing:
            raise KrakenMarketDataError(
                f"Missing Kraken prices for symbols: {', '.join(missing)}"
            )

    def get_latest_prices(self) -> dict[str, float]:
        if self._latest_prices_cache is not None:
            return dict(self._latest_prices_cache)

        pair_map = self._load_pair_map()
        query_pairs = ",".join(pair.query_pair for pair in pair_map.values())
        payload = self._request_json("/0/public/Ticker", {"pair": query_pairs})
        result = payload.get("result")
        if not isinstance(result, dict):
            raise KrakenMarketDataError("Kraken ticker payload did not contain a result object.")

        prices: dict[str, float] = {}
        for symbol, pair in pair_map.items():
            ticker_row = self._match_result_row(result, pair.response_keys)
            close_values = ticker_row.get("c")
            if not isinstance(close_values, list) or not close_values:
                raise KrakenMarketDataError(
                    f"Kraken ticker payload for {symbol} did not contain last-trade data."
                )
            try:
                prices[symbol] = round(float(close_values[0]), 6)
            except (TypeError, ValueError) as exc:
                raise KrakenMarketDataError(
                    f"Kraken ticker payload for {symbol} contained a non-numeric last price."
                ) from exc

        self._latest_prices_cache = dict(prices)
        return prices

    def get_price_history(self, symbol: str, length: int = 60) -> list[float]:
        pair_map = self._load_pair_map()
        pair = pair_map.get(symbol)
        if pair is None:
            raise KrakenMarketDataError(f"Symbol is not configured for Kraken market data: {symbol}")

        required_length = max(length, self.history_length, 60)
        cache_key = (symbol, required_length)
        if cache_key in self._history_cache:
            return list(self._history_cache[cache_key])

        payload = self._request_json(
            "/0/public/OHLC",
            {"pair": pair.query_pair, "interval": str(self.ohlc_interval_minutes)},
        )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise KrakenMarketDataError("Kraken OHLC payload did not contain a result object.")

        raw_rows = self._match_result_row(result, pair.response_keys)
        if not isinstance(raw_rows, list):
            raise KrakenMarketDataError(f"Kraken OHLC payload for {symbol} did not contain candle rows.")

        closes: list[float] = []
        for row in raw_rows:
            if not isinstance(row, list) or len(row) < 5:
                raise KrakenMarketDataError(f"Kraken OHLC payload for {symbol} contained a malformed candle row.")
            try:
                closes.append(round(float(row[4]), 6))
            except (TypeError, ValueError) as exc:
                raise KrakenMarketDataError(
                    f"Kraken OHLC payload for {symbol} contained a non-numeric close price."
                ) from exc

        if len(closes) < required_length:
            raise KrakenMarketDataError(
                f"Kraken OHLC payload for {symbol} returned only {len(closes)} closes, "
                f"but {required_length} are required."
            )

        history = closes[-required_length:]
        self._history_cache[cache_key] = history
        return list(history)

    def get_histories(self, length: int = 60) -> dict[str, list[float]]:
        required_length = max(length, self.history_length, 60)
        return {
            symbol: self.get_price_history(symbol, length=required_length)
            for symbol in self.symbols
        }

    def _load_pair_map(self) -> dict[str, ResolvedKrakenPair]:
        if self._pair_map is not None:
            return self._pair_map

        payload = self._request_json("/0/public/AssetPairs")
        result = payload.get("result")
        if not isinstance(result, dict) or not result:
            raise KrakenMarketDataError("Kraken AssetPairs payload did not contain tradable pair data.")

        pair_map: dict[str, ResolvedKrakenPair] = {}
        for symbol in self.symbols:
            pair_map[symbol] = self._resolve_pair(symbol, result)

        self._pair_map = pair_map
        return pair_map

    def _resolve_pair(
        self,
        symbol: str,
        asset_pairs: dict[str, Any],
    ) -> ResolvedKrakenPair:
        target_symbol = _normalize_symbol(symbol)
        for pair_id, details in asset_pairs.items():
            if not isinstance(details, dict):
                continue
            if _normalized_symbol_from_pair_details(details) != target_symbol:
                continue

            status = str(details.get("status", "unknown"))
            if status != "online":
                raise KrakenMarketDataError(
                    f"Kraken pair for {symbol} is not online. Reported status: {status}."
                )

            return ResolvedKrakenPair(
                aegis_symbol=target_symbol,
                pair_id=str(pair_id),
                altname=str(details.get("altname", "")),
                wsname=str(details.get("wsname", "")),
                status=status,
            )

        raise KrakenMarketDataError(f"Kraken does not expose a supported public pair for {symbol}.")

    def _match_result_row(self, result: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in result:
                return result[key]
        raise KrakenMarketDataError(
            "Kraken response did not include the expected pair key for the requested symbol."
        )

    def _request_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        query = urlencode(params or {})
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise KrakenMarketDataError(f"Kraken public market data request failed: {exc}") from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise KrakenMarketDataError("Kraken public market data returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise KrakenMarketDataError("Kraken public market data returned a non-object payload.")

        errors = payload.get("error")
        if isinstance(errors, list) and errors:
            raise KrakenMarketDataError(f"Kraken public market data returned errors: {', '.join(errors)}")

        return payload


def _normalized_symbol_from_pair_details(details: dict[str, Any]) -> str:
    wsname = details.get("wsname")
    if isinstance(wsname, str) and "/" in wsname:
        return _normalize_symbol(wsname)

    base = _normalize_asset_code(str(details.get("base", "")))
    quote = _normalize_asset_code(str(details.get("quote", "")))
    if base and quote:
        return f"{base}/{quote}"

    altname = details.get("altname")
    if isinstance(altname, str) and altname.endswith("USD"):
        return f"{_normalize_asset_code(altname[:-3])}/USD"

    return ""


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/").replace(" ", "")
    if "/" in normalized:
        base, quote = normalized.split("/", 1)
        return f"{_normalize_asset_code(base)}/{_normalize_asset_code(quote)}"

    if normalized.endswith("USD"):
        return f"{_normalize_asset_code(normalized[:-3])}/USD"

    return normalized


def _normalize_asset_code(code: str) -> str:
    normalized = code.upper().strip()
    if normalized in {"XXBT", "XBT"}:
        return "BTC"
    if normalized in {"XETH", "ETH"}:
        return "ETH"
    if normalized in {"ZUSD", "USD"}:
        return "USD"
    if normalized.startswith(("X", "Z")) and len(normalized) > 3:
        normalized = normalized[1:]
    if normalized == "XBT":
        return "BTC"
    return normalized


__all__ = ["KrakenMarketDataError", "KrakenPublicMarketDataProvider", "ResolvedKrakenPair"]
