# Local Ledger notes

Local Ledger keeps transactions and budgets in a local SQLite database. The interface is built with CustomTkinter; CSV import and validation are separate from the interface so they can be tested without opening a window.

## Code layout

| File | Purpose |
| --- | --- |
| `local_ledger/app.py` | Window, forms, tables, and button handlers |
| `local_ledger/validation.py` | Dates, amounts, text, and transaction types |
| `local_ledger/database.py` | Schema and SQL queries |
| `local_ledger/csv_service.py` | Bank CSV import and report export |

`run.py` starts the app. It accepts `--database` to use a different SQLite file.

## Data model

A category has a name and a type: income or expense. Transactions belong to a category and store amounts as integer pennies. Budgets set one limit per category and month. SQLite foreign keys are enabled for every connection.

The monthly summary joins transactions to categories to calculate income and expenses. A budget query uses a left join so a budget still appears when it has no spending.

## CSV imports

The importer accepts several common header names for date, description, and amount. It detects comma, semicolon, tab, and pipe separators. Valid rows are saved even if another row fails; the result reports the line numbers of rejected rows. Imports do not currently detect duplicates, so check a file before importing it twice.

## Current limits

- The database is local but not encrypted.
- Ambiguous dates such as `03/04/2026` follow day/month/year order.
- The chart shows the seven largest expense categories.
- The app does not yet edit transactions or manage category names.

## Tests

Run `python -m unittest discover -v`. The tests cover amount and date validation, foreign keys, monthly totals, and partial CSV imports.
