from __future__ import annotations

from typing import Any


def build_dashboard_metrics(daily_metrics: dict[str, Any] | None) -> dict[str, float]:
    if not daily_metrics:
        return {"cumulative_pnl": 0.0, "max_drawdown": 0.0, "ending_cash": 0.0}

    cumulative_pnl = float(daily_metrics["realized_pnl"]) + float(daily_metrics["unrealized_pnl"])
    return {
        "cumulative_pnl": round(cumulative_pnl, 6),
        "max_drawdown": float(daily_metrics["max_drawdown"]),
        "ending_cash": float(daily_metrics["ending_cash"]),
    }
