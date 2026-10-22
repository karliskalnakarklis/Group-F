#!/usr/bin/env bash
# Stops each service of the running stack in turn and records which use cases
# still work. Prints a JSON array to stdout and a table to stderr.
# Usage: bench/blast_radius.sh <baseline|a|b>      (the stack must be running)
set -euo pipefail

stack="$1"
root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/variant-$stack"; [ "$stack" = "baseline" ] && dir="$root/baseline"
compose=(docker compose -p pos -f "$dir/docker-compose.yml")
runner="$root/tests/runner.sh"

probe() { "$runner" "$stack" python bench/probe.py "$1"; }

rows=("$(probe none)")
for service in $("${compose[@]}" config --services | sort); do
  [ "$service" = "gateway" ] && continue
  echo "--- stopping $service" >&2
  "${compose[@]}" stop "$service" >/dev/null 2>&1
  rows+=("$(probe "$service")")
  "${compose[@]}" up -d --wait >/dev/null 2>&1      # all services healthy again
  "$runner" "$stack" python tests/wait_for_stack.py 90 >&2
  sleep 3                                              # let services reconnect before the next row
done

printf '[\n%s\n]\n' "$(IFS=,; echo "${rows[*]}" | sed 's/},{/},\n{/g')"
printf '%s\n' "${rows[@]}" | "$runner" "$stack" python -c '
import json, sys
rows = [json.loads(l) for l in sys.stdin if l.strip()]
cases = list(rows[0]["results"])
print("stopped".ljust(16) + "".join(c[:10].rjust(11) for c in cases), file=sys.stderr)
for r in rows:
    marks = ["ok" if r["results"][c] in (200, 201) else "FAIL" for c in cases]
    print(r["stopped"][:15].ljust(16) + "".join(m.rjust(11) for m in marks), file=sys.stderr)
'
