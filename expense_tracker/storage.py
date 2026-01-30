"""SQLite storage for transactions."""

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from expense_tracker.models import Category, Transaction


class Storage:
    """SQLite storage for expense tracking."""

    DEFAULT_DB_PATH = Path.home() / ".expense-tracker" / "expenses.db"

    def __init__(self, db_path: Path | None = None):
        """Initialize storage.

        Args:
            db_path: Path to SQLite database. Uses default if not provided.
        """
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    posting_date TEXT,
                    amount TEXT NOT NULL,
                    amount_original TEXT,
                    currency TEXT DEFAULT 'RUB',
                    description TEXT NOT NULL,
                    category TEXT,
                    card_number TEXT,
                    bank TEXT DEFAULT 'T-Bank',
                    imported_at TEXT NOT NULL,
                    UNIQUE(date, amount, description, bank)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    rules TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_date
                ON transactions(date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_category
                ON transactions(category)
            """)

            conn.commit()

    def add_transaction(self, transaction: Transaction) -> bool:
        """Add a transaction to the database.

        Args:
            transaction: Transaction to add

        Returns:
            True if added, False if duplicate
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO transactions (
                        date, posting_date, amount, amount_original,
                        currency, description, category, card_number,
                        bank, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        transaction.date.isoformat(),
                        transaction.posting_date.isoformat()
                        if transaction.posting_date
                        else None,
                        str(transaction.amount),
                        str(transaction.amount_original)
                        if transaction.amount_original
                        else None,
                        transaction.currency,
                        transaction.description,
                        transaction.category.value if transaction.category else None,
                        transaction.card_number,
                        transaction.bank,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def add_transactions(self, transactions: list[Transaction]) -> tuple[int, int]:
        """Add multiple transactions to the database.

        Args:
            transactions: List of transactions to add

        Returns:
            Tuple of (added_count, duplicate_count)
        """
        added = 0
        duplicates = 0

        for transaction in transactions:
            if self.add_transaction(transaction):
                added += 1
            else:
                duplicates += 1

        return added, duplicates

    def get_transactions(
        self,
        category: Optional[Category] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[Transaction]:
        """Get transactions with optional filters.

        Args:
            category: Filter by category
            date_from: Filter by start date
            date_to: Filter by end date
            limit: Maximum number of results

        Returns:
            List of matching transactions
        """
        query = "SELECT * FROM transactions WHERE 1=1"
        params: list = []

        if category:
            query += " AND category = ?"
            params.append(category.value)

        if date_from:
            query += " AND date >= ?"
            params.append(date_from.isoformat())

        if date_to:
            query += " AND date <= ?"
            params.append(date_to.isoformat())

        query += " ORDER BY date DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        return [self._row_to_transaction(row) for row in rows]

    def get_summary(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> dict[str, Decimal]:
        """Get expense summary by category.

        Args:
            date_from: Filter by start date
            date_to: Filter by end date

        Returns:
            Dictionary mapping category names to total amounts
        """
        query = """
            SELECT category, SUM(CAST(amount AS REAL)) as total
            FROM transactions
            WHERE CAST(amount AS REAL) < 0
        """
        params: list = []

        if date_from:
            query += " AND date >= ?"
            params.append(date_from.isoformat())

        if date_to:
            query += " AND date <= ?"
            params.append(date_to.isoformat())

        query += " GROUP BY category ORDER BY total ASC"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        return {row[0] or "Прочее": Decimal(str(abs(row[1]))) for row in rows}

    def get_top_expenses(
        self,
        category: Optional[Category] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 10,
    ) -> list[Transaction]:
        """Get top expenses by amount.

        Args:
            category: Filter by category
            date_from: Filter by start date
            date_to: Filter by end date
            limit: Maximum number of results

        Returns:
            List of top expense transactions
        """
        query = """
            SELECT * FROM transactions
            WHERE CAST(amount AS REAL) < 0
        """
        params: list = []

        if category:
            query += " AND category = ?"
            params.append(category.value)

        if date_from:
            query += " AND date >= ?"
            params.append(date_from.isoformat())

        if date_to:
            query += " AND date <= ?"
            params.append(date_to.isoformat())

        query += " ORDER BY CAST(amount AS REAL) ASC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        return [self._row_to_transaction(row) for row in rows]

    def get_totals(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> tuple[Decimal, Decimal]:
        """Get total income and expenses.

        Args:
            date_from: Filter by start date
            date_to: Filter by end date

        Returns:
            Tuple of (total_income, total_expense)
        """
        query = "SELECT amount FROM transactions WHERE 1=1"
        params: list = []

        if date_from:
            query += " AND date >= ?"
            params.append(date_from.isoformat())

        if date_to:
            query += " AND date <= ?"
            params.append(date_to.isoformat())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        income = Decimal("0")
        expense = Decimal("0")

        for row in rows:
            amount = Decimal(row[0])
            if amount > 0:
                income += amount
            else:
                expense += abs(amount)

        return income, expense

    def _row_to_transaction(self, row: sqlite3.Row) -> Transaction:
        """Convert database row to Transaction object."""
        category = None
        if row["category"]:
            try:
                category = Category(row["category"])
            except ValueError:
                pass

        return Transaction(
            date=datetime.fromisoformat(row["date"]),
            posting_date=datetime.fromisoformat(row["posting_date"])
            if row["posting_date"]
            else None,
            amount=Decimal(row["amount"]),
            amount_original=Decimal(row["amount_original"])
            if row["amount_original"]
            else None,
            currency=row["currency"],
            description=row["description"],
            category=category,
            card_number=row["card_number"],
            bank=row["bank"],
        )

    def clear(self) -> None:
        """Clear all transactions from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM transactions")
            conn.commit()
