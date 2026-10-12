"""Exact amounts (Decimal, half-up to cents) and calendar helpers."""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .errors import MxsatError

CENT = Decimal("0.01")


def dec(value: str | Decimal | int, field: str = "amount") -> Decimal:
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise MxsatError("bad_amount", f"{field} is not a number") from None
    if not d.is_finite():
        raise MxsatError("bad_amount", f"{field} is not a number")
    return d


def r2(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def s2(d: Decimal) -> str:
    """Two-decimal string, as the SAT portal writes totals."""
    return f"{r2(d):.2f}"


def cents(d: Decimal) -> int:
    return int(r2(d) * 100)


def money_out(value: str | None) -> str | None:
    """Normalize an amount read from a document: '5000.000000' -> '5000.00'; extra precision is kept."""
    if value is None or value == "":
        return None
    d = dec(value)
    return s2(d) if d == r2(d) else format(d.normalize(), "f")


def parse_date(value: str, field: str = "date") -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise MxsatError("bad_date", f"{field} must be YYYY-MM-DD") from None


def parse_period(value: str) -> tuple[int, int]:
    try:
        y, m = value.split("-")
        year, month = int(y), int(m)
    except ValueError:
        raise MxsatError("bad_period", "period must be YYYY-MM") from None
    if not (1 <= month <= 12 and 2000 <= year <= 2100):
        raise MxsatError("bad_period", "period must be YYYY-MM")
    return year, month


def add_months(year: int, month: int, n: int) -> tuple[int, int]:
    i = year * 12 + (month - 1) + n
    return i // 12, i % 12 + 1


def months_between(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (b[0] * 12 + b[1]) - (a[0] * 12 + a[1])


def last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]
