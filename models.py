from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Signal:
    symbol: str
    action: str
    reason: str
    indicators: dict[str, float]
    should_execute: bool
    id: str = field(default_factory=lambda: str(uuid4()))
    ts: str = field(default_factory=utc_now_iso)

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "symbol": self.symbol,
            "action": self.action,
            "reason": self.reason,
            "indicator_json": self.indicators,
            "should_execute": int(self.should_execute),
        }


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    reason_codes: list[str]
    quantity: float
    price: float
    side: str

    def summary(self) -> str:
        return ", ".join(self.reason_codes) if self.reason_codes else "ALLOWED"


@dataclass(slots=True)
class ExecutionResult:
    trade_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    notional: float
    pnl: float
    artifact_id: str
    ts: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EngineCycleResult:
    run_id: str
    signal_count: int
    executed_count: int
    blocked_count: int
    latest_prices: dict[str, float]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
