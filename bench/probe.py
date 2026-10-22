"""Runs every use case once and prints which ones work, as one JSON line.
Used by blast_radius.sh while one service is stopped.
Usage: probe.py <name of the stopped service, or "none">"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx  # noqa: E402

import pos  # noqa: E402
from usecases import USE_CASES, REGISTER, new_id  # noqa: E402

pos.http = httpx.Client(timeout=5.0)
results = {}
try:
    pos.ensure_open(REGISTER)
except Exception:  # noqa: BLE001
    pass
for name, run in USE_CASES.items():
    try:
        response = run(new_id())
        results[name] = response.status_code
    except AssertionError as error:  # setup of the use case failed
        results[name] = f"setup failed: {str(error)[:60]}"
    except httpx.HTTPError as error:
        results[name] = type(error).__name__
print(json.dumps({"stopped": sys.argv[1], "results": results,
                  "working": sorted(n for n, r in results.items() if r in (200, 201))}))
