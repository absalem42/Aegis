from __future__ import annotations

from typing import Protocol

from models import ExecutionOutcome, ExecutionRequest

from .kraken_cli_executor import KrakenCliExecutionError, KrakenCliPaperExecutor
from .kraken_executor import KrakenExecutorStub
from .paper_executor import PaperExecutor


class ExecutionProvider(Protocol):
    provider_name: str
    source_type: str

    def execute(self, connection, request: ExecutionRequest) -> ExecutionOutcome: ...


__all__ = [
    "ExecutionProvider",
    "KrakenCliExecutionError",
    "KrakenCliPaperExecutor",
    "KrakenExecutorStub",
    "PaperExecutor",
]
