"""Money is computed with Decimal and rounded half up to 0.01, as in the monolith."""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def now() -> datetime:
    return datetime.now(ZURICH)
