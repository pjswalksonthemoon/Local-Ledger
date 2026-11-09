# Local Ledger

A desktop budget tracker I built with Python, CustomTkinter, and SQLite. It records income and expenses, tracks monthly category budgets, imports bank CSV files, and exports monthly reports. Data stays in a local SQLite file.

## Run it

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

The default database is `LocalLedgerData/local_ledger.db` in your user folder. For a test database, run `python run.py --database demo.db`.

## CSV import

The required columns are date, description, and amount. Common alternatives such as `Transaction Date`, `Details`, and `Value` are recognised. Category, type, and notes are optional.

```csv
Date,Description,Amount,Category,Type
2026-10-01,Salary,1450.00,Salary,income
2026-10-02,Supermarket,-42.73,Food,expense
```

If type is omitted, a positive amount is treated as income and a negative amount as an expense. Valid rows import even when another row is rejected; the app lists the rejected line numbers. Re-importing the same file can create duplicates.

## Tests

```powershell
python -m unittest discover -v
```

The tests use temporary databases. GitHub Actions runs them on pushes and pull requests.

See [project notes](docs/PROJECT_EXPLANATION.md) for the data model and known limits. The database is not encrypted, so protect the computer account and back up the file if it holds important records.

## Licence

MIT. See [LICENSE](LICENSE).
