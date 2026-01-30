"""SQLite storage for transactions."""

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from expense_tracker.models import Category, INTERNAL_TRANSFER_PATTERN, Transaction


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
        include_internal_transfers: bool = True,
    ) -> list[Transaction]:
        """Get transactions with optional filters.

        Args:
            category: Filter by category
            date_from: Filter by start date
            date_to: Filter by end date
            limit: Maximum number of results
            include_internal_transfers: Include internal transfers (default True)

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

        transactions = [self._row_to_transaction(row) for row in rows]

        if not include_internal_transfers:
            transactions = [t for t in transactions if not t.is_internal_transfer()]

        return transactions

    def get_summary(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        include_internal_transfers: bool = False,
    ) -> dict[str, Decimal]:
        """Get expense summary by category.

        Args:
            date_from: Filter by start date
            date_to: Filter by end date
            include_internal_transfers: Include internal transfers (default False)

        Returns:
            Dictionary mapping category names to total amounts
        """
        # Fetch all expense transactions and filter in Python for internal transfers
        transactions = self.get_transactions(
            date_from=date_from,
            date_to=date_to,
            include_internal_transfers=include_internal_transfers,
        )

        summary: dict[str, Decimal] = {}
        for t in transactions:
            if t.is_expense():
                cat_name = t.category.value if t.category else "Прочее"
                if cat_name not in summary:
                    summary[cat_name] = Decimal("0")
                summary[cat_name] += abs(t.amount)

        return summary

    def get_top_expenses(
        self,
        category: Optional[Category] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 10,
        include_internal_transfers: bool = False,
    ) -> list[Transaction]:
        """Get top expenses by amount.

        Args:
            category: Filter by category
            date_from: Filter by start date
            date_to: Filter by end date
            limit: Maximum number of results
            include_internal_transfers: Include internal transfers (default False)

        Returns:
            List of top expense transactions
        """
        # Fetch more than needed to account for filtered internal transfers
        fetch_limit = limit * 3 if not include_internal_transfers else limit

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
        params.append(fetch_limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        transactions = [self._row_to_transaction(row) for row in rows]

        if not include_internal_transfers:
            transactions = [t for t in transactions if not t.is_internal_transfer()]

        return transactions[:limit]

    def get_totals(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        include_internal_transfers: bool = False,
    ) -> tuple[Decimal, Decimal]:
        """Get total income and expenses.

        Args:
            date_from: Filter by start date
            date_to: Filter by end date
            include_internal_transfers: Include internal transfers (default False)

        Returns:
            Tuple of (total_income, total_expense)
        """
        transactions = self.get_transactions(
            date_from=date_from,
            date_to=date_to,
            include_internal_transfers=include_internal_transfers,
        )

        income = Decimal("0")
        expense = Decimal("0")

        for t in transactions:
            if t.amount > 0:
                income += t.amount
            else:
                expense += abs(t.amount)

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
