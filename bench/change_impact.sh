#!/usr/bin/env bash
# How far did the change requests spread? Compares two git tags per variant
# and counts files and lines changed per service folder.
# Usage: bench/change_impact.sh [from-tag] [to-tag]      (default: v1 v2)
set -euo pipefail

from="${1:-v1}"; to="${2:-v2}"
cd "$(dirname "$0")/.."

for variant in variant-a variant-b; do
  echo "## $variant: $from → $to"
  echo
  echo "| Service folder | Files | Lines added | Lines deleted |"
  echo "|---|---|---|---|"
  git diff --numstat "$from" "$to" -- "$variant" | awk -v v="$variant/" '
    { path = substr($3, length(v) + 1); n = split(path, part, "/")
      service = (n > 1) ? part[1] : "(variant root)"
      files[service]++; added[service] += $1; deleted[service] += $2 }
    END { for (s in files) { printf "| %s | %d | %d | %d |\n", s, files[s], added[s], deleted[s]; total++ }
          printf "\nService folders touched: %d\n", total }'
  echo
done
