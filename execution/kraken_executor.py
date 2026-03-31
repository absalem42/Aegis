from __future__ import annotations

from .kraken_cli_executor import KrakenCliExecutionError, KrakenCliPaperExecutor


class KrakenExecutorStub:
    """Non-live placeholder for a future Kraken execution adapter."""

    mode_name = "kraken"
    provider_name = "Kraken CLI Live"
    source_type = "cli-live-blocked"

    def availability_note(self) -> str:
        return (
            "Kraken live execution is planned and guarded, but not enabled in this milestone. "
            "Use internal paper or Kraken CLI paper execution for demos."
        )

    def execute(self, *args, **kwargs):
        raise NotImplementedError("Kraken live execution is blocked in this milestone.")


__all__ = [
    "KrakenCliExecutionError",
    "KrakenCliPaperExecutor",
    "KrakenExecutorStub",
]
