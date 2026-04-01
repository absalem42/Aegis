from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv

MARKET_DATA_MODE_MOCK = "mock"
MARKET_DATA_MODE_KRAKEN = "kraken"
EXECUTION_MODE_PAPER = "paper"
EXECUTION_MODE_KRAKEN = "kraken"
KRAKEN_EXECUTION_MODE_PAPER = "paper"
KRAKEN_EXECUTION_MODE_LIVE = "live"
KRAKEN_BACKEND_REST = "rest"
KRAKEN_BACKEND_CLI = "cli"
MARKET_DATA_MODES = (MARKET_DATA_MODE_MOCK, MARKET_DATA_MODE_KRAKEN)
EXECUTION_MODES = (EXECUTION_MODE_PAPER, EXECUTION_MODE_KRAKEN)
KRAKEN_EXECUTION_MODES = (KRAKEN_EXECUTION_MODE_PAPER, KRAKEN_EXECUTION_MODE_LIVE)
KRAKEN_BACKENDS = (KRAKEN_BACKEND_REST, KRAKEN_BACKEND_CLI)
DEFAULT_AGENT_CAPABILITIES = (
    "paper-trading",
    "risk-checks",
    "trade-intent-artifacts",
    "decision-audit-trail",
    "kraken-public-market-data",
    "kraken-cli-market-data-readiness",
    "kraken-cli-paper-execution",
    "kraken-live-readiness-guarded",
    "erc8004-ready-structure",
)
DEFAULT_LIVE_ALLOWED_SYMBOLS = ("BTC/USD", "ETH/USD", "SOL/USD")


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_market_data_mode(value: str | None) -> str:
    if value in MARKET_DATA_MODES:
        return value
    return MARKET_DATA_MODE_MOCK


def _parse_execution_mode(value: str | None) -> str:
    if value in EXECUTION_MODES:
        return value
    return EXECUTION_MODE_PAPER


def _parse_kraken_execution_mode(value: str | None) -> str:
    if value in KRAKEN_EXECUTION_MODES:
        return value
    return KRAKEN_EXECUTION_MODE_PAPER


def _parse_kraken_backend(value: str | None) -> str:
    if value in KRAKEN_BACKENDS:
        return value
    return KRAKEN_BACKEND_REST


def _parse_capabilities(value: str | None) -> Tuple[str, ...]:
    if not value:
        return DEFAULT_AGENT_CAPABILITIES
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or DEFAULT_AGENT_CAPABILITIES


def _parse_symbols(value: str | None, default: Tuple[str, ...]) -> Tuple[str, ...]:
    if not value:
        return default
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default


@dataclass(slots=True)
class Settings:
    db_path: Path = Path(os.getenv("AEGIS_DB_PATH", "data/aegis.db"))
    artifact_dir: Path = Path(os.getenv("AEGIS_ARTIFACT_DIR", "artifacts"))
    report_dir: Path = Path(os.getenv("AEGIS_REPORT_DIR", "reports"))
    symbols: Tuple[str, ...] = ("BTC/USD", "ETH/USD", "SOL/USD")
    market_data_mode: str = MARKET_DATA_MODE_MOCK
    execution_mode: str = EXECUTION_MODE_PAPER
    kraken_execution_mode: str = KRAKEN_EXECUTION_MODE_PAPER
    kraken_backend: str = KRAKEN_BACKEND_REST
    kraken_base_url: str = os.getenv("AEGIS_KRAKEN_BASE_URL", "https://api.kraken.com")
    kraken_timeout_seconds: float = float(os.getenv("AEGIS_KRAKEN_TIMEOUT_SECONDS", "5"))
    kraken_ohlc_interval_minutes: int = int(os.getenv("AEGIS_KRAKEN_OHLC_INTERVAL_MINUTES", "60"))
    kraken_history_length: int = int(os.getenv("AEGIS_KRAKEN_HISTORY_LENGTH", "60"))
    kraken_allow_fallback_to_mock: bool = field(
        default_factory=lambda: _parse_bool(os.getenv("AEGIS_KRAKEN_ALLOW_FALLBACK_TO_MOCK"), True)
    )
    kraken_user_agent: str = os.getenv("AEGIS_KRAKEN_USER_AGENT", "Aegis-local-demo")
    kraken_cli_command: str = os.getenv("AEGIS_KRAKEN_CLI_COMMAND", "kraken")
    kraken_cli_timeout_seconds: float = float(os.getenv("AEGIS_KRAKEN_CLI_TIMEOUT_SECONDS", "10"))
    kraken_cli_allow_fallback_to_rest: bool = field(
        default_factory=lambda: _parse_bool(os.getenv("AEGIS_KRAKEN_CLI_ALLOW_FALLBACK_TO_REST"), True)
    )
    kraken_execution_allow_fallback_to_internal_paper: bool = field(
        default_factory=lambda: _parse_bool(
            os.getenv("AEGIS_KRAKEN_EXECUTION_ALLOW_FALLBACK_TO_INTERNAL_PAPER"),
            True,
        )
    )
    enable_kraken_live: bool = field(
        default_factory=lambda: _parse_bool(os.getenv("AEGIS_ENABLE_KRAKEN_LIVE"), False)
    )
    enable_kraken_live_submit: bool = field(
        default_factory=lambda: _parse_bool(os.getenv("AEGIS_ENABLE_KRAKEN_LIVE_SUBMIT"), False)
    )
    kraken_live_require_validate: bool = field(
        default_factory=lambda: _parse_bool(os.getenv("AEGIS_KRAKEN_LIVE_REQUIRE_VALIDATE"), True)
    )
    kraken_live_max_notional_per_order: float = float(
        os.getenv("AEGIS_KRAKEN_LIVE_MAX_NOTIONAL_PER_ORDER", "50")
    )
    kraken_live_max_daily_notional: float = float(
        os.getenv("AEGIS_KRAKEN_LIVE_MAX_DAILY_NOTIONAL", "100")
    )
    kraken_live_max_orders_per_cycle: int = int(
        os.getenv("AEGIS_KRAKEN_LIVE_MAX_ORDERS_PER_CYCLE", "1")
    )
    kraken_live_confirmation_text: str = os.getenv(
        "AEGIS_KRAKEN_LIVE_CONFIRMATION_TEXT",
        "ENABLE_LIVE_ORDERS",
    )
    kraken_live_allowed_symbols: Tuple[str, ...] = DEFAULT_LIVE_ALLOWED_SYMBOLS
    session_live_opt_in: bool = False
    session_live_confirmation_input: str = ""
    session_live_submit_opt_in: bool = False
    agent_id: str = os.getenv("AEGIS_AGENT_ID", "aegis-local-agent")
    agent_name: str = os.getenv("AEGIS_AGENT_NAME", "Aegis")
    agent_version: str = os.getenv("AEGIS_AGENT_VERSION", "0.1.0")
    agent_capabilities: Tuple[str, ...] = DEFAULT_AGENT_CAPABILITIES
    starting_cash: float = float(os.getenv("AEGIS_STARTING_CASH", "100000"))
    trade_fraction: float = float(os.getenv("AEGIS_TRADE_FRACTION", "0.10"))
    max_risk_per_trade: float = float(os.getenv("AEGIS_MAX_RISK_PER_TRADE", "0.10"))
    max_daily_drawdown: float = float(os.getenv("AEGIS_MAX_DAILY_DRAWDOWN", "0.05"))
    max_open_positions: int = int(os.getenv("AEGIS_MAX_OPEN_POSITIONS", "3"))
    cooldown_after_losses: int = int(os.getenv("AEGIS_COOLDOWN_AFTER_LOSSES", "2"))
    kill_switch: bool = field(default_factory=lambda: _parse_bool(os.getenv("AEGIS_KILL_SWITCH"), False))
    log_level: str = os.getenv("AEGIS_LOG_LEVEL", "INFO")

    def ensure_paths(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    load_dotenv()
    settings = Settings(
        db_path=Path(os.getenv("AEGIS_DB_PATH", "data/aegis.db")),
        artifact_dir=Path(os.getenv("AEGIS_ARTIFACT_DIR", "artifacts")),
        report_dir=Path(os.getenv("AEGIS_REPORT_DIR", "reports")),
        market_data_mode=_parse_market_data_mode(os.getenv("AEGIS_MARKET_DATA_MODE")),
        execution_mode=_parse_execution_mode(os.getenv("AEGIS_EXECUTION_MODE")),
        kraken_execution_mode=_parse_kraken_execution_mode(
            os.getenv("AEGIS_KRAKEN_EXECUTION_MODE")
        ),
        kraken_backend=_parse_kraken_backend(os.getenv("AEGIS_KRAKEN_BACKEND")),
        kraken_base_url=os.getenv("AEGIS_KRAKEN_BASE_URL", "https://api.kraken.com"),
        kraken_timeout_seconds=float(os.getenv("AEGIS_KRAKEN_TIMEOUT_SECONDS", "5")),
        kraken_ohlc_interval_minutes=int(os.getenv("AEGIS_KRAKEN_OHLC_INTERVAL_MINUTES", "60")),
        kraken_history_length=int(os.getenv("AEGIS_KRAKEN_HISTORY_LENGTH", "60")),
        kraken_allow_fallback_to_mock=_parse_bool(
            os.getenv("AEGIS_KRAKEN_ALLOW_FALLBACK_TO_MOCK"),
            True,
        ),
        kraken_user_agent=os.getenv("AEGIS_KRAKEN_USER_AGENT", "Aegis-local-demo"),
        kraken_cli_command=os.getenv("AEGIS_KRAKEN_CLI_COMMAND", "kraken"),
        kraken_cli_timeout_seconds=float(os.getenv("AEGIS_KRAKEN_CLI_TIMEOUT_SECONDS", "10")),
        kraken_cli_allow_fallback_to_rest=_parse_bool(
            os.getenv("AEGIS_KRAKEN_CLI_ALLOW_FALLBACK_TO_REST"),
            True,
        ),
        kraken_execution_allow_fallback_to_internal_paper=_parse_bool(
            os.getenv("AEGIS_KRAKEN_EXECUTION_ALLOW_FALLBACK_TO_INTERNAL_PAPER"),
            True,
        ),
        enable_kraken_live=_parse_bool(os.getenv("AEGIS_ENABLE_KRAKEN_LIVE"), False),
        enable_kraken_live_submit=_parse_bool(
            os.getenv("AEGIS_ENABLE_KRAKEN_LIVE_SUBMIT"),
            False,
        ),
        kraken_live_require_validate=_parse_bool(
            os.getenv("AEGIS_KRAKEN_LIVE_REQUIRE_VALIDATE"),
            True,
        ),
        kraken_live_max_notional_per_order=float(
            os.getenv("AEGIS_KRAKEN_LIVE_MAX_NOTIONAL_PER_ORDER", "50")
        ),
        kraken_live_max_daily_notional=float(
            os.getenv("AEGIS_KRAKEN_LIVE_MAX_DAILY_NOTIONAL", "100")
        ),
        kraken_live_max_orders_per_cycle=int(
            os.getenv("AEGIS_KRAKEN_LIVE_MAX_ORDERS_PER_CYCLE", "1")
        ),
        kraken_live_confirmation_text=os.getenv(
            "AEGIS_KRAKEN_LIVE_CONFIRMATION_TEXT",
            "ENABLE_LIVE_ORDERS",
        ),
        kraken_live_allowed_symbols=_parse_symbols(
            os.getenv("AEGIS_KRAKEN_LIVE_ALLOWED_SYMBOLS"),
            DEFAULT_LIVE_ALLOWED_SYMBOLS,
        ),
        agent_id=os.getenv("AEGIS_AGENT_ID", "aegis-local-agent"),
        agent_name=os.getenv("AEGIS_AGENT_NAME", "Aegis"),
        agent_version=os.getenv("AEGIS_AGENT_VERSION", "0.1.0"),
        agent_capabilities=_parse_capabilities(os.getenv("AEGIS_AGENT_CAPABILITIES")),
        starting_cash=float(os.getenv("AEGIS_STARTING_CASH", "100000")),
        trade_fraction=float(os.getenv("AEGIS_TRADE_FRACTION", "0.10")),
        max_risk_per_trade=float(os.getenv("AEGIS_MAX_RISK_PER_TRADE", "0.10")),
        max_daily_drawdown=float(os.getenv("AEGIS_MAX_DAILY_DRAWDOWN", "0.05")),
        max_open_positions=int(os.getenv("AEGIS_MAX_OPEN_POSITIONS", "3")),
        cooldown_after_losses=int(os.getenv("AEGIS_COOLDOWN_AFTER_LOSSES", "2")),
        kill_switch=_parse_bool(os.getenv("AEGIS_KILL_SWITCH"), False),
        log_level=os.getenv("AEGIS_LOG_LEVEL", "INFO"),
    )
    settings.ensure_paths()
    return settings
