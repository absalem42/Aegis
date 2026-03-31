from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import shlex
import subprocess
from typing import Any, Iterable

from .kraken_client import KrakenMarketDataError

SAFE_KRAKEN_CLI_COMMANDS = frozenset({"status", "ticker", "ohlc"})
KRAKEN_CLI_PAIR_MAP = {
    "BTC/USD": "BTCUSD",
    "ETH/USD": "ETHUSD",
    "SOL/USD": "SOLUSD",
}


class KrakenCliError(KrakenMarketDataError):
    """Raised when Kraken CLI market data is unavailable or malformed."""


@dataclass(slots=True)
class KrakenCliRunner:
    command_prefix: str
    timeout_seconds: float
    command_tokens: list[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.timeout_seconds = max(1.0, float(self.timeout_seconds))
        self.command_tokens = _split_command_prefix(self.command_prefix)

    def run_json(self, command_name: str, *args: str) -> Any:
        if command_name not in SAFE_KRAKEN_CLI_COMMANDS:
            raise KrakenCliError(
                f"Kraken CLI command is not allowed in Aegis v0: {command_name}"
            )

        argv = [*self.command_tokens, command_name, *[str(arg) for arg in args], "-o", "json"]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                check=False,
                shell=False,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise KrakenCliError(
                f"Kraken CLI command was not found: {' '.join(self.command_tokens)}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise KrakenCliError(
                f"Kraken CLI command timed out after {self.timeout_seconds:.0f} seconds."
            ) from exc
        except OSError as exc:
            raise KrakenCliError(f"Kraken CLI command failed to start: {exc}") from exc

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if completed.returncode != 0:
            raise KrakenCliError(_error_message_from_cli_failure(stdout, stderr, completed.returncode))

        payload = _loads_json(stdout)
        if isinstance(payload, dict) and payload.get("error"):
            raise KrakenCliError(_error_message_from_payload(payload))
        return payload


class KrakenCliMarketDataProvider:
    """Kraken CLI-backed public market-data provider for safe paper-trading demos."""

    mode_name = "kraken"
    backend_name = "cli"
    provider_name = "Kraken Official CLI"
    source_type = "cli-json"

    def __init__(
        self,
        symbols: Iterable[str],
        command_prefix: str,
        timeout_seconds: float,
        ohlc_interval_minutes: int,
        history_length: int,
    ) -> None:
        self.symbols = tuple(symbols)
        self.runner = KrakenCliRunner(command_prefix=command_prefix, timeout_seconds=timeout_seconds)
        self.ohlc_interval_minutes = max(1, int(ohlc_interval_minutes))
        self.history_length = max(60, int(history_length))
        self._latest_prices_cache: dict[str, float] | None = None
        self._history_cache: dict[tuple[str, int], list[float]] = {}

        unsupported_symbols = [symbol for symbol in self.symbols if symbol not in KRAKEN_CLI_PAIR_MAP]
        if unsupported_symbols:
            raise KrakenCliError(
                f"Kraken CLI does not have an Aegis symbol mapping for: {', '.join(unsupported_symbols)}"
            )

    def availability_note(self) -> str:
        return "Kraken CLI market data is available while execution remains local paper-only."

    def ensure_available(self) -> None:
        payload = self.runner.run_json("status")
        if not isinstance(payload, dict):
            raise KrakenCliError("Kraken CLI status returned a non-object JSON payload.")

    def get_latest_prices(self) -> dict[str, float]:
        if self._latest_prices_cache is not None:
            return dict(self._latest_prices_cache)

        pairs = [self._pair_for_symbol(symbol) for symbol in self.symbols]
        payload = self.runner.run_json("ticker", *pairs)
        prices: dict[str, float] = {}
        for symbol in self.symbols:
            pair = self._pair_for_symbol(symbol)
            row = _extract_ticker_row(payload, pair)
            prices[symbol] = _parse_last_price(row, pair)

        self._latest_prices_cache = dict(prices)
        return prices

    def get_price_history(self, symbol: str, length: int = 60) -> list[float]:
        if symbol not in KRAKEN_CLI_PAIR_MAP:
            raise KrakenCliError(f"Symbol is not configured for Kraken CLI market data: {symbol}")

        required_length = max(length, self.history_length, 60)
        cache_key = (symbol, required_length)
        if cache_key in self._history_cache:
            return list(self._history_cache[cache_key])

        pair = self._pair_for_symbol(symbol)
        payload = self.runner.run_json(
            "ohlc",
            pair,
            "--interval",
            str(self.ohlc_interval_minutes),
        )
        candle_rows = _extract_ohlc_rows(payload, pair)
        closes = [_parse_close_price(row, pair) for row in candle_rows]
        if len(closes) < required_length:
            raise KrakenCliError(
                f"Kraken CLI OHLC returned only {len(closes)} closes for {symbol}, "
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

    def _pair_for_symbol(self, symbol: str) -> str:
        return KRAKEN_CLI_PAIR_MAP[symbol]


def _split_command_prefix(command_prefix: str) -> list[str]:
    raw = command_prefix.strip()
    if not raw:
        raise KrakenCliError("AEGIS_KRAKEN_CLI_COMMAND must not be empty.")

    try:
        tokens = shlex.split(raw, posix=os.name != "nt")
    except ValueError as exc:
        raise KrakenCliError(f"Kraken CLI command is not parseable: {exc}") from exc

    if not tokens:
        raise KrakenCliError("AEGIS_KRAKEN_CLI_COMMAND must contain a runnable command.")
    return tokens


def _loads_json(raw: str) -> Any:
    if not raw:
        raise KrakenCliError("Kraken CLI returned an empty stdout payload.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KrakenCliError("Kraken CLI returned invalid JSON.") from exc


def _error_message_from_cli_failure(stdout: str, stderr: str, returncode: int) -> str:
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return _error_message_from_payload(payload)

    if stderr:
        return f"Kraken CLI exited with code {returncode}: {stderr}"
    if stdout:
        return f"Kraken CLI exited with code {returncode}: {stdout}"
    return f"Kraken CLI exited with code {returncode}."


def _error_message_from_payload(payload: dict[str, Any]) -> str:
    error_value = payload.get("error")
    message = payload.get("message")
    if isinstance(error_value, str) and isinstance(message, str):
        return f"{error_value}: {message}"
    if isinstance(message, str):
        return message
    if isinstance(error_value, str):
        return error_value
    if isinstance(error_value, list) and error_value:
        return ", ".join(str(item) for item in error_value)
    return "Kraken CLI returned an unknown JSON error envelope."


def _extract_ticker_row(payload: Any, pair: str) -> Any:
    if isinstance(payload, dict):
        if pair in payload:
            return payload[pair]
        for key in ("result", "data"):
            nested = payload.get(key)
            if isinstance(nested, dict) and pair in nested:
                return nested[pair]
            if isinstance(nested, list):
                matched = _match_pair_item(nested, pair)
                if matched is not None:
                    return matched
        if "tickers" in payload and isinstance(payload["tickers"], list):
            matched = _match_pair_item(payload["tickers"], pair)
            if matched is not None:
                return matched
    if isinstance(payload, list):
        matched = _match_pair_item(payload, pair)
        if matched is not None:
            return matched
    raise KrakenCliError(f"Kraken CLI ticker output did not contain pair data for {pair}.")


def _match_pair_item(items: list[Any], pair: str) -> Any | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("pair", "symbol", "market", "wsname"):
            if _normalize_pair_value(item.get(key)) == pair:
                return item
    return None


def _parse_last_price(row: Any, pair: str) -> float:
    if isinstance(row, dict):
        if isinstance(row.get("c"), list) and row["c"]:
            return _to_float(row["c"][0], f"Kraken CLI ticker last price for {pair}")
        for key in ("last", "close", "price"):
            if key not in row:
                continue
            value = row[key]
            if isinstance(value, dict):
                for nested_key in ("price", "value", "last"):
                    if nested_key in value:
                        return _to_float(value[nested_key], f"Kraken CLI ticker {key} for {pair}")
            if isinstance(value, list) and value:
                return _to_float(value[0], f"Kraken CLI ticker {key} for {pair}")
            return _to_float(value, f"Kraken CLI ticker {key} for {pair}")

    raise KrakenCliError(f"Kraken CLI ticker output for {pair} did not contain a last price.")


def _extract_ohlc_rows(payload: Any, pair: str) -> list[Any]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        if pair in payload and isinstance(payload[pair], list):
            return payload[pair]
        for key in ("result", "data"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                if pair in nested and isinstance(nested[pair], list):
                    return nested[pair]
                for nested_key in ("candles", "ohlc", "rows"):
                    if isinstance(nested.get(nested_key), list):
                        return nested[nested_key]
            if isinstance(nested, list):
                return nested
        for key in ("candles", "ohlc", "rows"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows

    raise KrakenCliError(f"Kraken CLI OHLC output did not contain candle rows for {pair}.")


def _parse_close_price(row: Any, pair: str) -> float:
    if isinstance(row, list):
        if len(row) < 5:
            raise KrakenCliError(f"Kraken CLI OHLC row for {pair} was malformed.")
        return round(_to_float(row[4], f"Kraken CLI OHLC close price for {pair}"), 6)

    if isinstance(row, dict):
        for key in ("close", "c", "last"):
            if key in row:
                return round(_to_float(row[key], f"Kraken CLI OHLC close price for {pair}"), 6)

    raise KrakenCliError(f"Kraken CLI OHLC row for {pair} did not contain a close price.")


def _normalize_pair_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.upper().replace("/", "")


def _to_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise KrakenCliError(f"{label} was not numeric.") from exc


__all__ = [
    "KRAKEN_CLI_PAIR_MAP",
    "KrakenCliError",
    "KrakenCliMarketDataProvider",
    "KrakenCliRunner",
    "SAFE_KRAKEN_CLI_COMMANDS",
]
