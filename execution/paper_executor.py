from __future__ import annotations

from uuid import uuid4

from models import ExecutionOutcome, ExecutionRequest


class PaperExecutor:
    provider_name = "Internal Paper Engine"
    source_type = "internal-sim"
    backend_name = "internal"

    def availability_note(self) -> str:
        return "Internal paper execution is the safe default path."

    def execute(self, connection, request: ExecutionRequest) -> ExecutionOutcome:
        filled_quantity = round(request.quantity, 6)
        fill_price = round(request.price, 6)
        return ExecutionOutcome(
            run_id=request.run_id,
            local_order_id=str(uuid4()),
            symbol=request.symbol,
            side=request.side.upper(),
            quantity=filled_quantity,
            filled_quantity=filled_quantity,
            price=fill_price,
            fill_price=fill_price,
            notional=round(filled_quantity * fill_price, 6),
            artifact_id=request.artifact_id,
            order_type=request.order_type,
            status="FILLED",
            execution_provider=self.provider_name,
            execution_source_type=self.source_type,
            requested_execution_mode=request.requested_execution_mode,
            effective_execution_mode=request.mode_summary.get("effective_execution_mode", request.requested_execution_mode),
            requested_kraken_execution_mode=request.requested_kraken_execution_mode,
            effective_kraken_execution_mode=request.mode_summary.get("effective_kraken_execution_mode"),
            provider_metadata={"simulated": True},
        )
