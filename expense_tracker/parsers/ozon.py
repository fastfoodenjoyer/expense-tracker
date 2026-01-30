"""Ozon Bank PDF statement parser."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import pdfplumber

from expense_tracker.models import Statement, Transaction

from .base import BaseParser


class OzonBankParser(BaseParser):
    """Parser for Ozon Bank PDF statements."""

    # Pattern for period extraction
    PERIOD_PATTERN = re.compile(
        r"Период выписки:\s*(\d{2}\.\d{2}\.\d{4})\s*[–\-]\s*(\d{2}\.\d{2}\.\d{4})"
    )

    # Pattern for account number
    ACCOUNT_PATTERN = re.compile(r"№\s*(\d{20})")

    # Pattern for totals
    INCOME_PATTERN = re.compile(r"Итого зачислений за период:\s*([\d\s]+\.\d{2})\s*₽")
    EXPENSE_PATTERN = re.compile(r"Итого списаний за период:\s*([\d\s]+\.\d{2})\s*₽")

    def can_parse(self, file_path: Path) -> bool:
        """Check if this is an Ozon Bank PDF statement."""
        if not file_path.suffix.lower() == ".pdf":
            return False

        try:
            with pdfplumber.open(file_path) as pdf:
                if not pdf.pages:
                    return False
                first_page_text = pdf.pages[0].extract_text() or ""
                text_lower = first_page_text.lower()
                return any(
                    marker in text_lower
                    for marker in ["озон банк", "ozon банк", "ozon bank", "ооо «озон банк»"]
                )
        except Exception:
            return False

    def parse(self, file_path: Path) -> Statement:
        """Parse Ozon Bank PDF statement."""
        transactions: list[Transaction] = []
        full_text = ""

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # Try to extract tables
                tables = page.extract_tables()
                for table in tables:
                    transactions.extend(self._parse_table(table))

                page_text = page.extract_text() or ""
                full_text += page_text + "\n"

        # Extract metadata
        period_start, period_end = self._extract_period(full_text)
        account_number = self._extract_account_number(full_text)
        total_income, total_expense = self._extract_totals(full_text)

        return Statement(
            account_number=account_number,
            period_start=period_start,
            period_end=period_end,
            transactions=transactions,
            total_income=total_income,
            total_expense=total_expense,
            bank="Ozon-Bank",
        )

    def _parse_table(self, table: list) -> list[Transaction]:
        """Parse transactions from extracted table."""
        transactions = []

        if not table:
            return transactions

        for row in table:
            if not row or len(row) < 4:
                continue

            try:
                transaction = self._parse_table_row(row)
                if transaction:
                    transactions.append(transaction)
            except (ValueError, InvalidOperation):
                continue

        return transactions

    def _parse_table_row(self, row: list) -> Optional[Transaction]:
        """Parse a single table row into a Transaction.

        Columns: Дата операции | Документ | Назначение платежа | Сумма операции (Российские рубли | Валюта)
        """
        # Find date - look for DD.MM.YYYY pattern with time
        date_str = None
        time_str = None
        description = None
        amount_str = None

        for cell in row:
            cell_str = str(cell or "").strip()

            # Look for date with time pattern (DD.MM.YYYY HH:MM:SS or DD.MM.YYYY\nHH:MM:SS)
            date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", cell_str)
            time_match = re.search(r"(\d{2}:\d{2}:\d{2})", cell_str)

            if date_match and not date_str:
                date_str = date_match.group(1)
                if time_match:
                    time_str = time_match.group(1)

            # Look for description (contains "Ozon" or "товар" or "заказ")
            if any(kw in cell_str.lower() for kw in ["ozon", "товар", "заказ", "платеж", "перевод"]):
                if not description or len(cell_str) > len(description):
                    description = cell_str

            # Look for amount (with ₽ symbol)
            amount_match = re.search(r"([+\-]?\s*[\d\s]+\.\d{2})\s*₽", cell_str)
            if amount_match:
                amount_str = cell_str

        # Skip header rows
        if not date_str or not description:
            return None

        if "Дата операции" in description or "Назначение" in description:
            return None

        # Parse date
        try:
            if time_str:
                date = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
            else:
                date = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            return None

        # Parse amount
        amount = self._parse_amount(amount_str) if amount_str else None
        if amount is None:
            # Try to find amount in any cell
            for cell in row:
                cell_str = str(cell or "").strip()
                amount = self._parse_amount(cell_str)
                if amount is not None:
                    break

        if amount is None:
            return None

        # Clean description
        description = self._clean_description(description)
        if not description:
            return None

        return Transaction(
            date=date,
            posting_date=date,
            amount=amount,
            description=description,
            bank="Ozon-Bank",
        )

    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse amount string to Decimal."""
        if not amount_str:
            return None

        # Extract amount with sign - Ozon uses dot as decimal separator
        match = re.search(r"([+\-]?)\s*([\d\s]+\.\d{2})\s*₽", amount_str)
        if not match:
            return None

        sign = match.group(1)
        value = match.group(2)

        # Clean: remove spaces
        cleaned = value.replace(" ", "")

        try:
            result = Decimal(cleaned)
            if sign == "-":
                result = -abs(result)
            return result
        except InvalidOperation:
            return None

    def _clean_description(self, description: str) -> str:
        """Clean and normalize transaction description."""
        cleaned = " ".join(description.split())
        return cleaned.strip()

    def _extract_period(
        self, text: str
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """Extract statement period from text."""
        match = self.PERIOD_PATTERN.search(text)
        if match:
            start = datetime.strptime(match.group(1), "%d.%m.%Y")
            end = datetime.strptime(match.group(2), "%d.%m.%Y")
            return start, end
        return None, None

    def _extract_account_number(self, text: str) -> Optional[str]:
        """Extract account number from text."""
        match = self.ACCOUNT_PATTERN.search(text)
        return match.group(1) if match else None

    def _extract_totals(
        self, text: str
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Extract total income and expense from text."""
        income = None
        expense = None

        income_match = self.INCOME_PATTERN.search(text)
        if income_match:
            value = income_match.group(1).replace(" ", "")
            try:
                income = Decimal(value)
            except InvalidOperation:
                pass

        expense_match = self.EXPENSE_PATTERN.search(text)
        if expense_match:
            value = expense_match.group(1).replace(" ", "")
            try:
                expense = Decimal(value)
            except InvalidOperation:
                pass

        return income, expense
