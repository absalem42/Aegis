from __future__ import annotations


class ERC8004StubPublisher:
    """Placeholder for a future trust/publish integration."""

    def publish(self, artifact_path: str) -> dict[str, str]:
        return {
            "status": "stub",
            "message": "ERC-8004 publication is deferred in Aegis v0.",
            "artifact_path": artifact_path,
        }
