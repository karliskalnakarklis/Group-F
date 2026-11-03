#!/usr/bin/env bash
# C4: in how many data stores is personal data of the seed's customers and
# employees? Dumps every data store of the running stack (the containers with
# the label pos.role=store) and searches each dump for the emails and last
# names of customer_info and employee_info in shared/seed.json.
#
# A last name only counts as a whole stored value ('Meier', or "Meier" inside
# JSON), so the vendor "Huber Handels GmbH" is not a match for the employee
# Huber. Emails are matched anywhere, ignoring case.
#
# Usage: bench/personal_data.sh <baseline|a|b>   (the stack must be running)
# Run it after the acceptance tests, so that the stores also hold what normal
# use writes (sales, returns, ledger entries), not only the seed.
# Prints JSON to stdout and a table to stderr.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: do not rewrite container paths

stack="$1"
level="${POS_LEVEL:-v1}"
root="$(cd "$(dirname "$0")/.." && pwd)"
runner="$root/tests/runner.sh"
project=(--filter label=com.docker.compose.project=pos)

# Search terms from the seed: one line per term, "<kind> <value>".
terms="$("$runner" "$stack" python -c '
import json
seed = json.load(open("shared/seed.json"))
seen = set()
for table in ("customer_info", "employee_info"):
    for row in seed[table]:
        for kind in ("email", "last_name"):
            if (kind, row[kind]) not in seen:
                seen.add((kind, row[kind]))
                print(kind, row[kind])
' </dev/null)"
term_count="$(printf '%s\n' "$terms" | grep -c .)"

stores="$(docker ps "${project[@]}" --filter label=pos.role=store \
  --format '{{.Label "com.docker.compose.service"}}' | sort)"
[ -n "$stores" ] || { echo "no data store of the stack 'pos' is running" >&2; exit 1; }

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
rows=(); with_personal=0; total=0

for store in $stores; do
  container="$(docker ps -q "${project[@]}" --filter "label=com.docker.compose.service=$store")"
  owner="$(docker inspect -f '{{index .Config.Labels "pos.owner"}}' "$container")"
  dump="$tmp/$store.sql"
  docker exec "$container" mariadb-dump -uroot -proot --skip-comments --skip-extended-insert pos > "$dump"

  found=0; : > "$tmp/tables"
  while read -r kind value; do
    if [ "$kind" = email ]; then
      matches="$(grep -iF -- "$value" "$dump" || true)"
    else
      matches="$(grep -E -- "[\"']${value}"'(\\)?'"[\"']" "$dump" || true)"
    fi
    [ -n "$matches" ] || continue
    found=$((found + 1))
    printf '%s\n' "$matches" | sed -n 's/^INSERT INTO `\([^`]*\)`.*/\1/p' >> "$tmp/tables"
  done <<< "$terms"

  tables="$(sort -u "$tmp/tables" | paste -sd, -)"
  total=$((total + 1))
  personal=false; [ "$found" -gt 0 ] && { personal=true; with_personal=$((with_personal + 1)); }
  rows+=("$(printf '{"store": "%s", "owner": "%s", "personal_data": %s, "terms_found": %d, "tables": [%s]}' \
    "$store" "$owner" "$personal" "$found" "$(printf '%s' "$tables" | sed 's/[^,][^,]*/"&"/g')")")
  printf '%-16s %-12s %-6s %3d of %d terms   %s\n' "$store" "$owner" "$personal" "$found" "$term_count" "$tables" >&2
done

joined=""
for row in "${rows[@]}"; do joined+="${joined:+,$'\n'  }$row"; done
printf '{"stack": "%s", "level": "%s", "measured_at": "%s", "search_terms": %d,\n "stores_with_personal_data": %d, "stores_total": %d,\n "stores": [\n  %s\n ]}\n' \
  "$stack" "$level" "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" "$term_count" "$with_personal" "$total" "$joined"
echo "data stores with personal data: $with_personal of $total" >&2
