#!/usr/bin/env bash
# Criterion C4: in how many data stores is personal data of a customer or an
# employee from the seed? Dumps every store of the running stack (containers of
# compose project 'pos' with label pos.role=store) and searches the dump,
# ignoring case, for the email and the last name of every customer and every
# employee in shared/seed.json. The dump is lowercased and split at commas
# first, because grep of Git Bash crashes on its very long INSERT lines.
# Prints JSON to stdout.
# Usage: bench/personal_data.sh <baseline|a|b>      (the stack must be running)
#        LEVEL=v2 bench/personal_data.sh b           (level is only recorded)
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: do not rewrite container paths

stack="$1"
level="${LEVEL:-v1}"
root="$(cd "$(dirname "$0")/.." && pwd)"
runner="$root/tests/runner.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# The search terms, one per line: "customer<TAB>term" or "employee<TAB>term".
# Python runs in the test image, because the host may have none.
"$runner" "$stack" python -c '
import json
seed = json.load(open("shared/seed.json", encoding="utf-8"))
for kind, table in (("customer", "customer_info"), ("employee", "employee_info")):
    terms = set()
    for row in seed[table]:
        terms.update(str(row[c]).strip() for c in ("email", "last_name") if row.get(c))
    for term in sorted(terms):
        print(f"{kind}\t{term}")
' | tr -d '\r' > "$work/terms.tsv"

count_found() {  # <kind> <dump file>: how many terms of that kind occur in the dump
  local kind="$1" dump="$2" n=0 term
  while IFS=$'\t' read -r k term; do
    [ "$k" = "$kind" ] || continue
    term="$(printf '%s' "$term" | tr 'A-Z' 'a-z')"
    if grep -qF -- "$term" "$dump"; then n=$((n + 1)); fi
  done < "$work/terms.tsv"
  echo "$n"
}

entries=()
with_data=0
for c in $(docker ps --filter label=com.docker.compose.project=pos --filter label=pos.role=store \
             --format '{{.Names}}' | tr -d '\r' | sort); do
  owner="$(docker inspect -f '{{index .Config.Labels "pos.owner"}}' "$c" | tr -d '\r')"
  name="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$c" | tr -d '\r')"
  dump="$work/$name.sql"
  if ! docker exec "$c" sh -c 'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --all-databases' \
       > "$dump.raw" 2> "$work/$name.err"; then
    echo "skipped $name: cannot dump ($(head -c 200 "$work/$name.err"))" >&2
    entries+=("{\"store\": \"$name\", \"owner\": \"$owner\", \"skipped\": \"cannot be dumped\"}")
    continue
  fi
  tr 'A-Z' 'a-z' < "$dump.raw" | tr ',(' '\n\n' > "$dump"
  customers="$(count_found customer "$dump")"
  employees="$(count_found employee "$dump")"
  [ $((customers + employees)) -gt 0 ] && with_data=$((with_data + 1))
  echo "$name (owner $owner): customer terms $customers, employee terms $employees" >&2
  entries+=("{\"store\": \"$name\", \"owner\": \"$owner\", \"customer_terms_found\": $customers, \"employee_terms_found\": $employees}")
done

printf '{"stack": "%s", "level": "%s", "stores": [' "$stack" "$level"
(IFS=,; printf '%s' "${entries[*]:-}" | sed 's/},{/}, {/g')
printf '], "stores_with_personal_data": %d}\n' "$with_data"
