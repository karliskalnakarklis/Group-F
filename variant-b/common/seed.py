"""The legacy data from /shared/seed.json. Each service loads only its own part,
and only when its tables are still empty, so that a restart keeps the data."""
import json
import os
from pathlib import Path

from .db import one, transaction


def load() -> dict:
    return json.loads(Path(os.getenv("SEED_PATH", "/shared/seed.json")).read_text(encoding="utf-8"))


def load_once(marker_table: str, fill) -> None:
    """Calls fill(cur, seed) in one transaction if marker_table is empty."""
    with transaction() as cur:
        if one(cur, f"SELECT COUNT(*) AS n FROM {marker_table}")["n"]:
            return
        fill(cur, load())
