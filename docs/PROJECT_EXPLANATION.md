# Local Ledger: Complete Project and Interview Guide

## What you built

Local Ledger is a desktop application for managing personal finances. A user can record income and expenses, group them into categories, set monthly spending limits, analyse where money went, import bank statements and export reports. The program does not send information to a web server. Everything is stored in an SQLite database on the same computer.

The project combines event driven programming, validation, relational database design, SQL aggregation, robust file processing, modular design, testing and privacy decisions. Those connections make it useful for a degree apprenticeship interview.

## A 30 second interview description

> I built a private desktop budgeting application in Python using CustomTkinter and SQLite. I separated the interface, validation, database and CSV processing into modules. The schema uses categories as the parent table for transactions and monthly budgets, with foreign keys enforcing valid relationships. I store money as integer pennies to avoid floating point errors. The CSV importer reads one row at a time, recognises several common bank headings and records line specific errors without losing valid rows. I added automated tests for validation, foreign keys, SQL summaries and malformed imports.

Practise saying this naturally. An interviewer will probably choose one phrase and ask you to go deeper.

## How the program runs

The entry point is `run.py`. It imports and calls `main()` from `local_ledger/app.py`.

`main()` performs four steps:

1. It reads the optional `--database` command line argument.
2. It chooses a default local database path if no argument was supplied.
3. It constructs a `Database`, which creates the schema and default categories when needed.
4. It constructs `LocalLedgerApp` and starts the GUI event loop with `mainloop()`.

The event loop waits for actions such as a button click. Clicking **Add transaction** calls `add_transaction()`. That method validates the date, description and amount, looks up the category ID, writes through the database class and refreshes the screens.

This is event driven programming. The application stays alive and reacts to events instead of running once from top to bottom.

## Architecture

| Module | Responsibility | Reason for separation |
|---|---|---|
| `app.py` | Widgets, button events, tables, dashboard and messages | Interface changes do not require rewriting SQL |
| `validation.py` | Checks and converts user supplied values | Invalid data is rejected consistently before database calls |
| `database.py` | Schema and parameterised SQL | Persistence rules are in one place and testable without a GUI |
| `csv_service.py` | Header mapping, row parsing, import results and export | File problems are isolated from the interface and database |

This applies decomposition and separation of concerns. Each module has a focused job. It also improves testability because tests can call validation and database functions without opening a window.

### Flow when adding a transaction

```text
Text typed into GUI
       |
       v
validation.py converts date and amount, or raises ValidationError
       |
       v
app.py finds the chosen category's integer ID
       |
       v
database.py runs a parameterised INSERT inside a transaction
       |
       v
SQLite checks NOT NULL, CHECK and FOREIGN KEY constraints
       |
       v
GUI queries fresh totals and redraws the dashboard
```

Python validation gives friendly errors, while database constraints protect integrity if another part of the program makes a mistake.

## Relational database design

### Categories

`categories` stores each category once. `id` is the primary key, `name` is unique without case sensitivity, and `kind` must be `income` or `expense`.

The type belongs to the category, so the program cannot treat one Food transaction as income and another Food transaction as an expense. It also avoids repeating category details in every transaction.

### Transactions

`transactions` stores a date, description, positive amount in pennies, category ID and notes. `category_id` is a foreign key to `categories.id`.

This is one-to-many: one category can classify many transactions, while every transaction has exactly one category. `ON DELETE RESTRICT` prevents deletion of a category still used by transaction history.

### Budgets

`budgets` stores a category ID, month such as `2026-11`, and limit in pennies. The pair `(category_id, month)` is unique. Food can have one November limit and a different December limit, but cannot have conflicting November limits.

`set_budget()` uses an upsert:

```sql
INSERT INTO budgets(category_id, month, limit_cents)
VALUES (?, ?, ?)
ON CONFLICT(category_id, month)
DO UPDATE SET limit_cents = excluded.limit_cents;
```

SQLite inserts a new row or updates the existing limit in one atomic statement.

### Foreign keys and referential integrity

Without a foreign key, a transaction could contain `category_id = 99999` when no category has that ID. Queries would fail to find its name. `PRAGMA foreign_keys = ON` makes SQLite reject the invalid insert.

SQLite requires enforcement on each connection, so `Database.connect()` runs the pragma every time. This is a strong interview detail: defining a constraint and enabling its enforcement are separate concerns in SQLite.

### Normalisation

The design is close to third normal form for this scope:

- Fields contain atomic values.
- Category details depend on the category primary key and are stored once.
- Transaction details depend on the transaction ID.
- Budget limits depend on the category and month combination.

Copying category names into every transaction would cause an update anomaly. Renaming Entertainment to Leisure would require many updates and could leave inconsistent spellings. The category table prevents that.

### Parameterised SQL

Methods use placeholders:

```python
connection.execute(
    "DELETE FROM transactions WHERE id = ?",
    (transaction_id,),
)
```

The value is sent separately from the SQL instruction, so SQLite treats it as data rather than executable SQL. This reduces SQL injection risk and handles quoting safely.

### Analysis queries

The monthly summary joins transactions to categories and uses conditional aggregation:

```sql
SELECT
  COALESCE(SUM(CASE WHEN c.kind='income' THEN t.amount_cents END), 0) AS income,
  COALESCE(SUM(CASE WHEN c.kind='expense' THEN t.amount_cents END), 0) AS expenses
FROM transactions t
JOIN categories c ON c.id = t.category_id
WHERE substr(t.transaction_date, 1, 7) = ?;
```

`JOIN` connects related rows. `WHERE` selects the month. `CASE` places values into the correct total. `SUM` aggregates them. `COALESCE` turns a missing `NULL` total into zero.

The budget query uses a `LEFT JOIN` because a budget must appear even when it has no transactions. An inner join would hide budgets with zero spending.

## Validation before database access

Validation lives in pure functions, so manual entry and CSV import use the same rules.

### Exact money

`parse_amount_to_cents()` removes a pound sign and comma separators, creates a `Decimal`, checks it is finite and positive, rounds to two places, and returns integer pennies.

Binary floating point cannot exactly represent many decimal fractions. Repeated currency calculations can therefore produce small errors. Storing `£12.34` as integer `1234` gives exact penny arithmetic. `Decimal` is used only while parsing and rounding text.

### Dates and text

`parse_transaction_date()` accepts ISO dates and common bank formats, converts them to `YYYY-MM-DD`, rejects dates before 1900 and rejects future dates before `add_transaction()` is called.

ISO text has a database advantage: alphabetical ordering is chronological, and the `YYYY-MM` prefix selects a month.

`require_text()` strips whitespace, rejects blanks and limits length. `validate_kind()` only permits income or expense. `validate_month()` uses a regular expression that permits months 01 through 12.

The database repeats critical rules using `NOT NULL`, `CHECK`, `UNIQUE` and `FOREIGN KEY`. Interface validation improves usability; schema constraints guarantee integrity.

## CSV processing and messy data

The importer opens files as `utf-8-sig`, which removes a byte order mark exported by some spreadsheet programs. `newline=""` lets Python's CSV module handle line endings.

It reads an 8 KB sample and asks `csv.Sniffer` to identify comma, semicolon, tab or pipe delimiters. If detection fails, it uses normal comma separated CSV.

### Flexible headings

Banks use different names for the same field. `HEADER_ALIASES` maps `Transaction Date`, `Posted Date` and `Booking Date` to the program's canonical `date`. Similar aliases exist for description and amount.

Date, description and amount are required. Category, type and notes are optional. When type is absent, a leading minus sign means expense and a positive amount means income.

### Line by line errors

`csv.DictReader` is an iterator. The loop requests one row at a time rather than loading the whole statement into memory. This uses O(1) auxiliary memory as the statement grows, apart from the error list and stored data.

Each row has its own `try` block. A valid row is inserted. A bad row creates an `ImportErrorDetail` with its line number and the loop continues. The interface then reports how many rows imported and exactly which lines failed.

This is graceful degradation: one malformed line does not destroy the useful work. The tradeoff is a partial import. A later banking grade version could preview every row and commit the approved batch atomically.

## Graphical interface

The interface has four tabs:

- **Dashboard**: income, expenses, balance, spending bars and budget progress.
- **Transactions**: validated manual entry and a monthly table.
- **Budgets**: monthly expense limits using the upsert.
- **Import & Export**: native file dialogs and line specific import results.

The chart uses a Tkinter `Canvas`. Each bar width is proportional to the largest category. The view is limited to seven categories for readability.

People choose category names, while the database uses stable integer keys. A Python dictionary maps each visible name to its ID.

## Links to your A Level Computer Science topics

These links use the topics in your uploaded revision guide.

| Topic already studied | Evidence in Local Ledger | Interview link |
|---|---|---|
| Relational databases and SQL | Tables, keys, joins, grouping, aggregation and constraints | “I applied referential integrity and normalisation instead of repeating category text.” |
| Programming constructs and subroutines | Selection in validation, loops in imports, functions and methods | “Small functions have clear inputs, outputs and exceptions.” |
| Computational thinking and decomposition | Separate UI, validation, database and CSV modules | “I decomposed by responsibility so each part is testable.” |
| Data structures | Lists, lookup dictionaries and import result dataclasses | “A dictionary gives average O(1) key lookup; a list preserves error order.” |
| Big O | Streaming import O(n), dictionary lookup average O(1) | “Import time grows linearly with CSV rows.” |
| Searching and sorting | SQL `ORDER BY`; indexes on date and category | “The database can use indexes instead of scanning Python lists.” |
| Floating point and number representation | `Decimal` parsing and integer pennies | “Currency is persisted as integers because binary floats are inexact.” |
| Ethics, law and privacy | Local storage, data minimisation and no analytics | “Financial records are sensitive, so this version has no network path.” |
| Network security and threats | Parameterised SQL and reduced remote attack surface | “SQL code and user data are bound separately.” |
| Operating systems and file systems | User data directory, dialogs and local files | “Persistent user data is separated from source code.” |
| Translators | Python interpreter, modules and dependencies | “Python parses and executes the source; packages are resolved at runtime.” |
| Web and networking | An intentional absence | “A desktop design satisfies the offline privacy requirement without HTTP.” |
| Boolean logic | Combined validation conditions and budget status | “Boolean conditions guard every operation.” |
| Static and dynamic structures | Collections grow with imported rows | “The program handles a dynamic record count.” |

Processor registers, assembly, compression and virtual machines are less directly visible. Do not force every syllabus topic into the project; accurate links are stronger.

## Ideas learned specifically for this project

1. **GUI event loops:** callbacks run when events occur.
2. **SQLite connection management:** contexts commit or roll back and always close.
3. **Transactions:** successful operations commit; exceptions roll back.
4. **Schema constraints:** application and database rules defend different layers.
5. **Upserts:** `ON CONFLICT DO UPDATE` performs insert-or-update atomically.
6. **Streaming CSV parsing:** iterators avoid loading an entire file.
7. **Dialect and header normalisation:** external data rarely follows one clean format.
8. **Exact currency:** `Decimal` and integer pennies avoid float errors.
9. **Temporary database tests:** tests never touch real user finance data.
10. **Packaging:** `pyproject.toml` describes the installable program and command.

## Tests and evidence

`tests/test_local_ledger.py` verifies that:

- formatted money becomes exact pennies;
- text in an amount field is rejected;
- a future date is rejected;
- SQLite rejects a missing category foreign key;
- joined SQL separates income and expense totals;
- a semicolon CSV imports two good lines and reports one bad date.

Tests do not prove an absence of bugs. They provide repeatable evidence for important requirements and reduce regressions.

Useful boundary tests to add include zero, the maximum allowed amount, one penny above it, month `2026-00`, month `2026-13`, today's date and tomorrow's date.

## Interview questions and model answers

### Why SQLite?

SQLite comes with Python, needs no server and stores a relational database in one local file. That matches the offline privacy requirement while supporting SQL, joins, indexes, transactions and constraints. Multiple remote users would suggest PostgreSQL, but that would change the architecture.

### Explain the foreign keys

`categories.id` is the parent primary key. `transactions.category_id` and `budgets.category_id` are child foreign keys. One category relates to many child rows. The constraint prevents a child from pointing to a nonexistent category. Restricting category deletion protects transaction history; cascading budget deletion is reasonable because a budget has no meaning without its category.

### How did you parse messy CSV?

I used Python's CSV module instead of splitting strings, because quoted commas and different delimiters make splitting unreliable. I detect delimiters, remove an optional UTF-8 byte order mark, map common bank headings and process each row independently. Invalid lines are reported with their physical line number while valid lines continue.

### How do you know validation occurs first?

The UI and CSV service call pure validation functions before `database.add_transaction()`. Tests verify that invalid values raise exceptions. The schema then provides a final integrity layer.

### Why integer pennies?

Currency has fixed decimal precision while binary floats cannot exactly represent many decimal fractions. Integer pennies make addition and comparison exact. `Decimal` rounds the user's input before persistence.

### What if a database operation fails?

The `session()` context manager commits successful work. An exception triggers rollback, then the connection closes in a `finally` block. This prevents half-completed operations and leaked connections.

### What would you improve before real financial use?

I would add encryption or encrypted backups, duplicate detection, import previews and reconciliation, recurring transactions, migrations, accessibility tests and a signed installer.

## Honest limitations

- The local database is not encrypted.
- The GUI does not yet rename or archive categories.
- Imports do not detect duplicates.
- `03/04/2026` is interpreted as 3 April, which may surprise a US user.
- Imported rows commit separately; this is friendly for partial success but slower than a batch.
- The chart shows only the seven largest expense categories.
- There is no schema migration framework.
- Windows scaling and screen reader behaviour need manual testing.

Honest limitations demonstrate engineering judgement. Pair each one with a specific improvement.

## Future roadmap

1. **Category management:** add create, rename and archive actions.
2. **Transaction editing:** load a selected row, validate it and run an `UPDATE`.
3. **Duplicate detection:** compare a fingerprint of date, description and amount.
4. **Import preview:** map columns and approve a batch before committing.
5. **Recurring transactions:** generate planned rent and salary entries.
6. **Trend analysis:** show month comparisons, savings rate and moving averages.
7. **Migrations:** version the schema before changing existing installations.
8. **Encrypted backups:** add password protected export and recovery guidance.
9. **Accessibility:** test keyboard order, contrast and screen reader labels.
10. **Packaging:** create and test a signed Windows executable.

A good release sequence is version 1.1 for editing and categories, 1.2 for import preview and duplicates, 1.3 for trends and recurring transactions, and 2.0 for encryption, migrations and packaging.

## Five minute code walkthrough

1. Show `validation.py` and explain independent amount and date rules.
2. Show the schema in `database.py`; explain keys, checks and indexes.
3. Show `monthly_summary()`; explain `JOIN`, `CASE`, `SUM`, `WHERE` and `COALESCE`.
4. Trace one row through `import_transactions()`.
5. Show the test mixing valid and invalid CSV rows.
6. Run the app and demonstrate invalid amount handling, a budget and an import error.

## Final revision checklist

Be ready to answer:

- Why is this a desktop app rather than a website?
- What do the three tables represent?
- Which fields are primary and foreign keys?
- What does referential integrity prevent?
- Why are amounts integers?
- What happens from button click to committed row?
- How do parameterised queries work?
- Why does the budget query use a left join?
- How does import handle delimiters, headings and bad lines?
- What are the time and memory complexities for n rows?
- Which tests prove the requirements?
- What would you improve next, and how?

If you can explain these and trace one transaction through the code, you understand the project at a strong interview level.
