#!/usr/bin/env bash
# Runs a command in the test image against the stack that is running on this
# machine. Usage: tests/runner.sh <baseline|a|b> <command...>
# Standard input is passed through (used by the conformance check).
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: do not rewrite container paths

variant="$1"; shift
root="$(cd "$(dirname "$0")/.." && pwd)"
host="host.docker.internal"

docker image inspect pos-tests >/dev/null 2>&1 || docker build -q -t pos-tests "$root/tests" >/dev/null

exec docker run --rm -i --add-host="$host:host-gateway" \
  -v "$root":/repo:ro -w /repo \
  -v pos_calllogs:/logs:ro \
  -e POS_URL="http://$host:8000" \
  -e POS_VARIANT="$variant" -e POS_LEVEL \
  -e BENCH_N -e BENCH_WARMUP \
  pos-tests "$@"
