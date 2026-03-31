import subprocess

import pytest

from market.kraken_cli import KrakenCliError, KrakenCliMarketDataProvider, KrakenCliRunner


def _completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["kraken"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class StubCliRunner:
    def __init__(self, responses):
        self.responses = responses

    def run_json(self, command_name: str, *args: str):
        key = (command_name, *args)
        if key not in self.responses:
            raise AssertionError(f"Unexpected CLI request: {key}")
        return self.responses[key]


def test_cli_runner_raises_when_binary_is_missing(monkeypatch):
    def _missing(*_args, **_kwargs):
        raise FileNotFoundError("kraken not found")

    monkeypatch.setattr("market.kraken_cli.subprocess.run", _missing)
    runner = KrakenCliRunner(command_prefix="kraken", timeout_seconds=5)

    with pytest.raises(KrakenCliError, match="not found"):
        runner.run_json("status")


def test_cli_runner_raises_on_json_error_envelope(monkeypatch):
    monkeypatch.setattr(
        "market.kraken_cli.subprocess.run",
        lambda *_args, **_kwargs: _completed(
            '{"error":"config","message":"missing configuration"}',
            returncode=2,
        ),
    )
    runner = KrakenCliRunner(command_prefix="kraken", timeout_seconds=5)

    with pytest.raises(KrakenCliError, match="missing configuration"):
        runner.run_json("status")


def test_cli_runner_raises_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        "market.kraken_cli.subprocess.run",
        lambda *_args, **_kwargs: _completed("not-json"),
    )
    runner = KrakenCliRunner(command_prefix="kraken", timeout_seconds=5)

    with pytest.raises(KrakenCliError, match="invalid JSON"):
        runner.run_json("status")


def test_cli_provider_parses_status_and_ticker_prices():
    provider = KrakenCliMarketDataProvider(
        symbols=("BTC/USD", "ETH/USD", "SOL/USD"),
        command_prefix="kraken",
        timeout_seconds=5,
        ohlc_interval_minutes=60,
        history_length=60,
    )
    provider.runner = StubCliRunner(
        {
            ("status",): {"status": "online"},
            ("ticker", "BTCUSD", "ETHUSD", "SOLUSD"): {
                "BTCUSD": {"c": ["66650.4", "0.1"]},
                "ETHUSD": {"c": ["2035.27", "0.5"]},
                "SOLUSD": {"c": ["80.65", "1.0"]},
            },
        }
    )

    provider.ensure_available()
    prices = provider.get_latest_prices()

    assert prices == {
        "BTC/USD": 66650.4,
        "ETH/USD": 2035.27,
        "SOL/USD": 80.65,
    }


def test_cli_provider_parses_ohlc_close_history():
    closes = [66000 + index for index in range(60)]
    candles = [
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
        for index, close in enumerate(closes)
    ]

    provider = KrakenCliMarketDataProvider(
        symbols=("BTC/USD",),
        command_prefix="kraken",
        timeout_seconds=5,
        ohlc_interval_minutes=60,
        history_length=60,
    )
    provider.runner = StubCliRunner(
        {
            ("ohlc", "BTCUSD", "--interval", "60"): {
                "BTCUSD": candles,
            }
        }
    )

    history = provider.get_price_history("BTC/USD", length=60)

    assert len(history) == 60
    assert history[0] == 66000.0
    assert history[-1] == 66059.0


def test_cli_provider_raises_on_malformed_ticker_payload():
    provider = KrakenCliMarketDataProvider(
        symbols=("BTC/USD",),
        command_prefix="kraken",
        timeout_seconds=5,
        ohlc_interval_minutes=60,
        history_length=60,
    )
    provider.runner = StubCliRunner(
        {
            ("ticker", "BTCUSD"): {
                "BTCUSD": {"c": []},
            }
        }
    )

    with pytest.raises(KrakenCliError):
        provider.get_latest_prices()
