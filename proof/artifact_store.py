from __future__ import annotations

import hashlib
import json
from typing import Any

from config import Settings
from db import insert_artifact


def save_trade_artifact(connection, settings: Settings, payload: dict[str, Any]) -> dict[str, Any]:
    artifact_id = payload["artifact_id"]
    artifact_date = payload["created_at"][:10]
    target_dir = settings.artifact_dir / artifact_date
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{artifact_id}.json"

    body = json.dumps(payload, indent=2, sort_keys=True)
    target_path.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()

    insert_artifact(
        connection,
        artifact_id=artifact_id,
        artifact_type=payload["artifact_type"],
        subject=payload["symbol"],
        payload=payload,
        digest=digest,
        notes="Pre-execution paper trade intent.",
        path=str(target_path),
    )

    return {"artifact_id": artifact_id, "path": str(target_path), "hash": digest}
