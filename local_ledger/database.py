"""SQLite persistence layer for Local Ledger."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    transaction_date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    category_id INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL,
    month TEXT NOT NULL CHECK (length(month) = 7),
    limit_cents INTEGER NOT NULL CHECK (limit_cents > 0),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    UNIQUE (category_id, month)
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_budgets_month ON budgets(month);
"""


DEFAULT_CATEGORIES = (
    ("Salary", "income"),
    ("Other income", "income"),
    ("Housing", "expense"),
    ("Food", "expense"),
    ("Transport", "expense"),
    ("Utilities", "expense"),
    ("Entertainment", "expense"),
    ("Shopping", "expense"),
    ("Health", "expense"),
    ("Education", "expense"),
    ("Other expense", "expense"),
)


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self.session() as connection:
            connection.executescript(SCHEMA)
            connection.executemany(
                "INSERT OR IGNORE INTO categories(name, kind) VALUES (?, ?)",
                DEFAULT_CATEGORIES,
            )

    def list_categories(self, kind: str | None = None) -> list[sqlite3.Row]:
        query = "SELECT id, name, kind FROM categories"
        parameters: tuple[object, ...] = ()
        if kind:
            query += " WHERE kind = ?"
            parameters = (kind,)
        query += " ORDER BY kind, name COLLATE NOCASE"
        with self.session() as connection:
            return list(connection.execute(query, parameters))

    def get_or_create_category(self, name: str, kind: str) -> int:
        with self.session() as connection:
            row = connection.execute(
                "SELECT id, kind FROM categories WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if row:
                if row["kind"] != kind:
                    raise ValueError(f"Category '{name}' already exists as {row['kind']}.")
                return int(row["id"])
            cursor = connection.execute(
                "INSERT INTO categories(name, kind) VALUES (?, ?)", (name, kind)
            )
            return int(cursor.lastrowid)

    def add_transaction(
        self,
        transaction_date: str,
        description: str,
        amount_cents: int,
        category_id: int,
        notes: str = "",
    ) -> int:
        with self.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO transactions(transaction_date, description, amount_cents, category_id, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (transaction_date, description, amount_cents, category_id, notes),
            )
            return int(cursor.lastrowid)

    def delete_transaction(self, transaction_id: int) -> None:
        with self.session() as connection:
            connection.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))

    def list_transactions(self, month: str | None = None) -> list[sqlite3.Row]:
        query = """
            SELECT t.id, t.transaction_date, t.description, t.amount_cents, t.notes,
                   c.id AS category_id, c.name AS category_name, c.kind
            FROM transactions t
            JOIN categories c ON c.id = t.category_id
        """
        parameters: tuple[object, ...] = ()
        if month:
            query += " WHERE substr(t.transaction_date, 1, 7) = ?"
            parameters = (month,)
        query += " ORDER BY t.transaction_date DESC, t.id DESC"
        with self.session() as connection:
            return list(connection.execute(query, parameters))

    def set_budget(self, category_id: int, month: str, limit_cents: int) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO budgets(category_id, month, limit_cents)
                VALUES (?, ?, ?)
                ON CONFLICT(category_id, month)
                DO UPDATE SET limit_cents = excluded.limit_cents
                """,
                (category_id, month, limit_cents),
            )

    def budget_status(self, month: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """
                    SELECT c.id AS category_id, c.name AS category_name,
                           b.limit_cents,
                           COALESCE(SUM(t.amount_cents), 0) AS spent_cents
                    FROM budgets b
                    JOIN categories c ON c.id = b.category_id
                    LEFT JOIN transactions t
                      ON t.category_id = b.category_id
                     AND substr(t.transaction_date, 1, 7) = b.month
                    WHERE b.month = ? AND c.kind = 'expense'
                    GROUP BY c.id, c.name, b.limit_cents
                    ORDER BY c.name COLLATE NOCASE
                    """,
                    (month,),
                )
            )

    def monthly_summary(self, month: str) -> dict[str, int]:
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN c.kind='income' THEN t.amount_cents END), 0) AS income,
                    COALESCE(SUM(CASE WHEN c.kind='expense' THEN t.amount_cents END), 0) AS expenses
                FROM transactions t
                JOIN categories c ON c.id = t.category_id
                WHERE substr(t.transaction_date, 1, 7) = ?
                """,
                (month,),
            ).fetchone()
        income = int(row["income"])
        expenses = int(row["expenses"])
        return {"income": income, "expenses": expenses, "balance": income - expenses}

    def spending_by_category(self, month: str) -> list[sqlite3.Row]:
        with self.session() as connection:
            return list(
                connection.execute(
                    """
                    SELECT c.name AS category_name, SUM(t.amount_cents) AS spent_cents
                    FROM transactions t
                    JOIN categories c ON c.id = t.category_id
                    WHERE c.kind = 'expense' AND substr(t.transaction_date, 1, 7) = ?
                    GROUP BY c.id, c.name
                    ORDER BY spent_cents DESC, c.name
                    """,
                    (month,),
                )
            )

