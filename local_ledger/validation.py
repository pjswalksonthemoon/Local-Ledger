"""Validation and conversion functions used before database operations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


class ValidationError(ValueError):
    """Raised when user supplied data cannot safely be accepted."""


MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def require_text(value: str, field_name: str, max_length: int = 200) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError(f"{field_name} is required.")
    if len(cleaned) > max_length:
        raise ValidationError(f"{field_name} must be {max_length} characters or fewer.")
    return cleaned


def parse_amount_to_cents(value: str | int | float | Decimal) -> int:
    """Convert a human amount to positive integer pennies without float errors."""
    cleaned = str(value).strip().replace("£", "").replace(",", "")
    if not cleaned:
        raise ValidationError("Amount is required.")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValidationError("Amount must be a number, for example 12.50.") from exc
    if not amount.is_finite():
        raise ValidationError("Amount must be a normal finite number.")
    amount = abs(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero.")
    if amount > Decimal("999999999.99"):
        raise ValidationError("Amount is too large.")
    return int(amount * 100)


def parse_transaction_date(value: str, today: date | None = None) -> str:
    cleaned = value.strip()
    formats = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y")
    parsed: date | None = None
    for date_format in formats:
        try:
            parsed = datetime.strptime(cleaned, date_format).date()
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValidationError("Date must use YYYY-MM-DD or a common bank format such as DD/MM/YYYY.")
    if parsed > (today or date.today()):
        raise ValidationError("Transaction date cannot be in the future.")
    if parsed < date(1900, 1, 1):
        raise ValidationError("Transaction date must be 1900-01-01 or later.")
    return parsed.isoformat()


def validate_month(value: str) -> str:
    cleaned = value.strip()
    if not MONTH_PATTERN.fullmatch(cleaned):
        raise ValidationError("Month must use YYYY-MM, for example 2026-11.")
    return cleaned


def validate_kind(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in {"income", "expense"}:
        raise ValidationError("Type must be income or expense.")
    return cleaned


def format_pounds(cents: int) -> str:
    return f"£{cents / 100:,.2f}"

