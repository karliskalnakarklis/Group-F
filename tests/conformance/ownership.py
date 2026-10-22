"""Checks the stack rules and the data-ownership rules of docs/contract.md in
the compose configuration (JSON on stdin, from 'docker compose config --format
json'). Run it through 'make conformance-a' or 'make conformance-b'."""
import json
import os
import sys

LEGACY_TABLES = [
    "customer_info", "employee_info", "stores", "store_registers", "vendorinfo", "product_inventory",
    "gift_card", "tax_table", "registers_table", "ticket_system", "cart_inprogress", "item_list",
    "ticket_gift_payment", "return_table", "return_items", "orders_ticket", "orders",
]

config = json.load(sys.stdin)
variant = os.environ.get("POS_VARIANT", "")
services = config.get("services", {})
failures, passes = [], []


def check(ok: bool, message: str) -> None:
    (passes if ok else failures).append(message)


def labels(name: str) -> dict:
    return services[name].get("labels") or {}


def role(name: str) -> str:
    return labels(name).get("pos.role", "app")


apps = [s for s in services if role(s) == "app"]
stores = [s for s in services if role(s) == "store"]

check(config.get("name") == "pos", "compose project name is 'pos'")
check("gateway" in services, "there is a service named 'gateway'")
for name, service in services.items():
    published = [str(p.get("published")) for p in service.get("ports", []) if p.get("published")]
    if name == "gateway":
        check(published == ["8000"], "gateway publishes port 8000 and nothing else")
    else:
        check(not published, f"{name} publishes no port")

for name in apps:
    mounts = [v for v in services[name].get("volumes", []) if v.get("target") == "/logs"]
    check(any(v.get("source") == "calllogs" for v in mounts), f"{name} mounts the volume 'calllogs' at /logs")

for store in stores:
    owner = labels(store).get("pos.owner")
    check(owner in apps, f"store {store} has an owner that is an application service (pos.owner={owner!r})")
    networks = set(services[store].get("networks") or {"default": None})
    sharing = sorted(a for a in apps if networks & set(services[a].get("networks") or {"default": None}))
    check(sharing == [owner], f"store {store} shares a network only with its owner {owner} (shares with {sharing})")

if variant in ("a", "b"):
    others = [a for a in apps if a != "gateway"]
    check(len(others) >= 3, f"at least three application services besides the gateway ({others})")
    gateway_stores = [s for s in stores if labels(s).get("pos.owner") == "gateway"]
    check(not gateway_stores, f"the gateway owns no store ({gateway_stores})")

if variant == "a":
    owners: dict[str, list[str]] = {}
    for name in apps:
        for table in filter(None, (t.strip() for t in labels(name).get("pos.tables", "").split(","))):
            owners.setdefault(table, []).append(name)
    for table in LEGACY_TABLES:
        check(len(owners.get(table, [])) == 1,
              f"legacy table {table} has exactly one owner (pos.tables: {owners.get(table, [])})")
    for table in sorted(set(owners) - set(LEGACY_TABLES)):
        check(False, f"pos.tables names {table}, which is not a legacy table")

for message in passes:
    print("PASS ", message)
for message in failures:
    print("FAIL ", message)
print(f"\n{len(passes)} passed, {len(failures)} failed")
sys.exit(1 if failures else 0)
