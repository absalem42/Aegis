from __future__ import annotations

from typing import Protocol

from .kraken_executor import KrakenExecutorStub
from .paper_executor import PaperExecutor


class ExecutionProvider(Protocol):
    def execute(self, connection, signal, quantity: float, price: float, artifact_id: str): ...


__all__ = ["ExecutionProvider", "KrakenExecutorStub", "PaperExecutor"]
