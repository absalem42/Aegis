from __future__ import annotations

from uuid import uuid4

from db import delete_position, get_position, record_trade, upsert_position
from models import ExecutionResult, Signal, utc_now_iso


class PaperExecutor:
    def execute(
        self,
        connection,
        signal: Signal,
        quantity: float,
        price: float,
        artifact_id: str,
    ) -> ExecutionResult:
        now = utc_now_iso()
        position = get_position(connection, signal.symbol)
        existing_qty = float(position["quantity"]) if position else 0.0
        average_cost = float(position["average_cost"]) if position else 0.0
        pnl = 0.0

        if signal.action == "BUY":
            new_quantity = existing_qty + quantity
            new_average_cost = (
                ((existing_qty * average_cost) + (quantity * price)) / new_quantity
                if new_quantity > 0
                else price
            )
            upsert_position(
                connection,
                symbol=signal.symbol,
                quantity=new_quantity,
                average_cost=new_average_cost,
                last_price=price,
                updated_at=now,
            )
        elif signal.action == "SELL":
            sell_quantity = min(quantity, existing_qty)
            pnl = round((price - average_cost) * sell_quantity, 6)
            remaining_quantity = round(existing_qty - sell_quantity, 6)
            if remaining_quantity <= 0:
                delete_position(connection, signal.symbol)
            else:
                upsert_position(
                    connection,
                    symbol=signal.symbol,
                    quantity=remaining_quantity,
                    average_cost=average_cost,
                    last_price=price,
                    updated_at=now,
                )
            quantity = sell_quantity
        else:
            raise ValueError(f"Unsupported paper execution action: {signal.action}")

        result = ExecutionResult(
            trade_id=str(uuid4()),
            symbol=signal.symbol,
            side=signal.action,
            quantity=round(quantity, 6),
            price=round(price, 6),
            notional=round(quantity * price, 6),
            pnl=pnl,
            artifact_id=artifact_id,
            ts=now,
        )
        record_trade(connection, result, reason=signal.reason)
        return result
