# Change impact preview, variant B: b-v1 → b-v2

Preview only. The tags b-v1 and b-v2 do not exist yet (the agent was told not to make git changes),
so this compares a copy of variant-b/ taken at b-v1 with the working tree at b-v2, with the same
counting as bench/change_impact.sh. The official numbers come from 'make impact' on the group tags.

## variant-b: b-v1 → b-v2

| Service folder | Files | Lines added | Lines deleted |
|---|---|---|---|
| till | 2 | 95 | 39 |
| reporting | 2 | 26 | 1 |
| purchasing | 1 | 3 | 2 |
| customers | 2 | 77 | 9 |

Service folders touched: 4

By change request (from the code, not measured separately: both were made in one step):
CR1 (VAT) touched till, purchasing (price list adds the category) and reporting (VAT per rate in the ledger);
CR2 (loyalty tiers) touched customers (movements, spend, tiers, refund step) and till (earn with date, tier
stored with the sale, refund call in the return). gateway, common/ and docker-compose.yml are unchanged.
