from __future__ import annotations


class ERC8004StubPublisher:
    """Placeholder for a future trust/publish integration boundary."""

    def readiness_status(self) -> dict[str, str]:
        return {
            "status": "local-readiness-only",
            "message": "Artifacts are structured for future ERC-8004-style validation, but no on-chain publishing is implemented in v0.",
        }

    def publish(self, artifact_path: str) -> dict[str, str]:
        return {
            "status": "stub",
            "message": "ERC-8004 publication is deferred in Aegis v0.",
            "artifact_path": artifact_path,
        }
