from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from local_ledger.csv_service import import_transactions
from local_ledger.database import Database
from local_ledger.validation import ValidationError, parse_amount_to_cents, parse_transaction_date


class ValidationTests(unittest.TestCase):
    def test_amount_uses_exact_pennies(self):
        self.assertEqual(parse_amount_to_cents("£1,234.567"), 123457)

    def test_non_numeric_amount_is_rejected(self):
        with self.assertRaises(ValidationError):
            parse_amount_to_cents("twelve pounds")

    def test_future_date_is_rejected(self):
        with self.assertRaises(ValidationError):
            parse_transaction_date("2026-11-08", today=date(2026, 11, 7))


class DatabaseAndCsvTests(unittest.TestCase):
    def setUp(self):
        workspace_temp = Path.cwd() / "work"
        workspace_temp.mkdir(exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=workspace_temp)
        self.database = Database(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_foreign_keys_are_enforced(self):
        with self.assertRaises(Exception):
            self.database.add_transaction("2026-10-01", "Invalid category", 100, 99999)

    def test_summary_joins_transactions_to_category_kind(self):
        salary = self.database.get_or_create_category("Test salary", "income")
        food = self.database.get_or_create_category("Test food", "expense")
        self.database.add_transaction("2026-10-01", "Pay", 200000, salary)
        self.database.add_transaction("2026-10-02", "Lunch", 1250, food)
        self.assertEqual(
            self.database.monthly_summary("2026-10"),
            {"income": 200000, "expenses": 1250, "balance": 198750},
        )

    def test_csv_import_keeps_valid_rows_and_reports_bad_rows(self):
        csv_path = Path(self.temp_dir.name) / "statement.csv"
        csv_path.write_text(
            "Transaction Date;Details;Amount;Category\n"
            "01/10/2026;Wages;1000.00;Salary\n"
            "02/10/2026;Lunch;-8.50;Food\n"
            "bad-date;Broken;-3.00;Food\n",
            encoding="utf-8",
        )
        result = import_transactions(self.database, csv_path)
        self.assertEqual(result.imported, 2)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].line_number, 4)
        self.assertEqual(len(self.database.list_transactions("2026-10")), 2)


if __name__ == "__main__":
    unittest.main()
