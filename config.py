from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    db_path: Path = Path(os.getenv("AEGIS_DB_PATH", "data/aegis.db"))
    artifact_dir: Path = Path(os.getenv("AEGIS_ARTIFACT_DIR", "artifacts"))
    symbols: Tuple[str, ...] = ("BTC/USD", "ETH/USD", "SOL/USD")
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


def load_settings() -> Settings:
    load_dotenv()
    settings = Settings(
        db_path=Path(os.getenv("AEGIS_DB_PATH", "data/aegis.db")),
        artifact_dir=Path(os.getenv("AEGIS_ARTIFACT_DIR", "artifacts")),
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
