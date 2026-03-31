from __future__ import annotations


class KrakenExecutorStub:
    """Non-live placeholder for a future Kraken execution adapter."""

    mode_name = "kraken"

    def availability_note(self) -> str:
        return "Kraken execution is not available in Aegis v0. Use paper execution for local demos."

    def execute(self, *args, **kwargs):
        raise NotImplementedError("Kraken execution is deferred in Aegis v0.")
