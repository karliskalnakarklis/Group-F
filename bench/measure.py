"""Latency and hops per use case. Run it through 'make bench-a' (or -b, -baseline).

Prints JSON to stdout (saved to bench/results/) and a table to stderr.
Hops are counted from the call log (docs/contract.md): every "out" line with
the request id of the measured request is one hop.

Environment variables:
  BENCH_N       measured requests per use case (default 30)
  BENCH_WARMUP  requests per use case before measuring (default 3)

This is a starting point: extend it, or add your own scripts, for the
criteria in docs/criteria.md."""
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pos  # noqa: E402
from usecases import USE_CASES, REGISTER, new_id  # noqa: E402

N = int(os.environ.get("BENCH_N", "30"))
WARMUP = int(os.environ.get("BENCH_WARMUP", "3"))
LOGS = Path("/logs")


def read_call_log() -> dict[str, list[dict]]:
    by_request = defaultdict(list)
    for file in LOGS.glob("*.jsonl"):
        for line in file.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            by_request[entry.get("request_id")].append(entry)
    return by_request


def main() -> None:
    pos.ensure_open(REGISTER)
    measured: dict[str, list[tuple[str, float]]] = {}
    for name, run in USE_CASES.items():
        print(f"measuring {name} ...", file=sys.stderr, flush=True)
        for _ in range(WARMUP):
            run(new_id())
        samples = []
        for _ in range(N):
            rid = new_id()
            start = time.perf_counter()
            response = run(rid)
            elapsed = (time.perf_counter() - start) * 1000
            assert response.status_code in (200, 201), f"{name}: {response.status_code} {response.text}"
            samples.append((rid, elapsed))
        measured[name] = samples

    time.sleep(1.0)  # let asynchronous consumers write their log lines
    log = read_call_log()
    if not log:
        sys.exit("no call log found in /logs: every service must write it (docs/contract.md, 'Call log')")

    result = {"variant": os.environ.get("POS_VARIANT"), "level": pos.LEVEL,
              "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "settings": {"n": N, "warmup": WARMUP}, "use_cases": {}}
    for name, samples in measured.items():
        ms = sorted(e for _, e in samples)
        hops = [sum(1 for entry in log.get(rid, []) if entry.get("direction") == "out") for rid, _ in samples]
        services = [len({entry.get("service") for entry in log.get(rid, [])}) for rid, _ in samples]
        result["use_cases"][name] = {
            "latency_ms": {"mean": round(statistics.fmean(ms), 2), "p50": round(ms[len(ms) // 2], 2),
                           "p95": round(ms[min(len(ms) - 1, int(len(ms) * 0.95))], 2), "max": round(ms[-1], 2)},
            "hops": {"median": statistics.median(hops), "max": max(hops)},
            "services_involved": {"median": statistics.median(services), "max": max(services)},
        }
    print(json.dumps(result, indent=2))

    err = sys.stderr
    print(f"\n{result['variant']} {pos.LEVEL}  (n={N}, warm-up={WARMUP})", file=err)
    print(f"{'use case':<16}{'mean ms':>9}{'p95 ms':>9}{'hops':>6}{'services':>10}", file=err)
    for name, r in result["use_cases"].items():
        print(f"{name:<16}{r['latency_ms']['mean']:>9}{r['latency_ms']['p95']:>9}"
              f"{r['hops']['median']:>6}{r['services_involved']['median']:>10}", file=err)


if __name__ == "__main__":
    main()
