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
class ExecutionRequest:
    run_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    order_type: str
    artifact_id: str
    requested_execution_mode: str
    requested_kraken_execution_mode: str | None
    requested_execution_provider: str
    mode_summary: dict[str, Any]
    signal_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionOutcome:
    run_id: str
    local_order_id: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float
    price: float
    fill_price: float
    notional: float
    artifact_id: str
    order_type: str
    status: str
    execution_provider: str
    execution_source_type: str
    requested_execution_mode: str
    effective_execution_mode: str
    requested_kraken_execution_mode: str | None
    effective_kraken_execution_mode: str | None
    provider_metadata: dict[str, Any]
    trade_id: str | None = None
    pnl: float | None = None
    external_order_id: str | None = None
    external_status: str | None = None
    auth_test_status: str | None = None
    validate_preflight_status: str | None = None
    live_preflight_status: str | None = None
    notes: str = ""
    ts: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Compatibility alias for older code paths and tests.
ExecutionResult = ExecutionOutcome


@dataclass(slots=True)
class EngineCycleResult:
    run_id: str
    signal_count: int
    executed_count: int
    blocked_count: int
    latest_prices: dict[str, float]
    summary: dict[str, Any]
    order_count: int = 0
    artifact_count: int = 0
    receipt_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
