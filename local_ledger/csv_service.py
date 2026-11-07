"""Streaming CSV import and report export."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .database import Database
from .validation import (
    ValidationError,
    parse_amount_to_cents,
    parse_transaction_date,
    require_text,
    validate_kind,
    validate_month,
)


HEADER_ALIASES = {
    "date": {"date", "transaction date", "transaction_date", "posted date", "booking date"},
    "description": {"description", "details", "narrative", "memo", "merchant", "name"},
    "amount": {"amount", "value", "transaction amount", "transaction_amount"},
    "category": {"category", "group"},
    "kind": {"type", "kind", "transaction type", "income/expense"},
    "notes": {"notes", "note", "reference"},
}


@dataclass
class ImportErrorDetail:
    line_number: int
    message: str


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    errors: list[ImportErrorDetail] = field(default_factory=list)


def _normalise_header(header: str) -> str:
    return " ".join(header.strip().lower().replace("_", " ").split())


def _map_headers(fieldnames: list[str]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for original in fieldnames:
        normalised = _normalise_header(original)
        for canonical, aliases in HEADER_ALIASES.items():
            if normalised in aliases and canonical not in mapped:
                mapped[canonical] = original
    missing = {"date", "description", "amount"} - mapped.keys()
    if missing:
        raise ValidationError(f"CSV is missing required column(s): {', '.join(sorted(missing))}.")
    return mapped


def import_transactions(database: Database, csv_path: str | Path) -> ImportResult:
    """Read one row at a time; valid rows import while bad rows are reported."""
    result = ImportResult()
    path = Path(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        sample = source.read(8192)
        source.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(source, dialect=dialect)
        if not reader.fieldnames:
            raise ValidationError("CSV has no header row.")
        header_map = _map_headers(reader.fieldnames)

        for line_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                result.skipped += 1
                continue
            try:
                raw_amount = row.get(header_map["amount"], "") or ""
                explicit_kind = row.get(header_map.get("kind", ""), "") or ""
                if explicit_kind.strip():
                    kind = validate_kind(explicit_kind)
                else:
                    kind = "expense" if raw_amount.strip().startswith("-") else "income"
                transaction_date = parse_transaction_date(row.get(header_map["date"], "") or "")
                description = require_text(
                    row.get(header_map["description"], "") or "", "Description"
                )
                amount_cents = parse_amount_to_cents(raw_amount)
                default_category = "Other expense" if kind == "expense" else "Other income"
                category_name = require_text(
                    row.get(header_map.get("category", ""), "") or default_category,
                    "Category",
                    80,
                )
                notes = (row.get(header_map.get("notes", ""), "") or "").strip()[:500]

                category_id = database.get_or_create_category(category_name, kind)
                database.add_transaction(
                    transaction_date, description, amount_cents, category_id, notes
                )
                result.imported += 1
            except (ValidationError, ValueError) as exc:
                result.errors.append(ImportErrorDetail(line_number, str(exc)))
    return result


def export_monthly_report(database: Database, month: str, output_path: str | Path) -> None:
    month = validate_month(month)
    summary = database.monthly_summary(month)
    category_rows = database.spending_by_category(month)
    budget_rows = {row["category_name"]: row for row in database.budget_status(month)}

    with Path(output_path).open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.writer(destination)
        writer.writerow(["Local Ledger monthly report", month])
        writer.writerow([])
        writer.writerow(["Summary", "Amount (GBP)"])
        writer.writerow(["Income", f"{summary['income'] / 100:.2f}"])
        writer.writerow(["Expenses", f"{summary['expenses'] / 100:.2f}"])
        writer.writerow(["Balance", f"{summary['balance'] / 100:.2f}"])
        writer.writerow([])
        writer.writerow(["Expense category", "Spent (GBP)", "Budget (GBP)", "Remaining (GBP)"])
        for row in category_rows:
            budget = budget_rows.get(row["category_name"])
            limit = int(budget["limit_cents"]) if budget else 0
            spent = int(row["spent_cents"])
            writer.writerow(
                [row["category_name"], f"{spent / 100:.2f}", f"{limit / 100:.2f}", f"{(limit - spent) / 100:.2f}"]
            )

