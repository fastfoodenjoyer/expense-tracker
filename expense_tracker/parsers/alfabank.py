"""Alfa Bank PDF statement parser."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import pdfplumber

from expense_tracker.models import Statement, Transaction

from .base import BaseParser


class AlfaBankParser(BaseParser):
    """Parser for Alfa Bank PDF statements."""

    # Pattern for period extraction
    PERIOD_PATTERN = re.compile(
        r"За период с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4})"
    )

    # Pattern for account number
    ACCOUNT_PATTERN = re.compile(r"Номер счета\s+(\d+)")

    # Pattern for totals
    INCOME_PATTERN = re.compile(r"Поступления\s+([\d\s]+,\d{2})\s*RUR")
    EXPENSE_PATTERN = re.compile(r"Расходы\s+([\d\s]+,\d{2})\s*RUR")

    # Pattern for transaction line: DD.MM.YYYY CODE Description Amount RUR
    TRANSACTION_PATTERN = re.compile(
        r"^(\d{2}\.\d{2}\.\d{4})\s+"      # Date
        r"([A-Z0-9_]+)\s+"                 # Operation code
        r"(.+?)\s+"                        # Description (non-greedy)
        r"(-?[\d\s]+,\d{2})\s*RUR\s*$"    # Amount with RUR
    )

    # Pattern for card operation to extract card number
    CARD_PATTERN = re.compile(r"карте?:\s*(\d+\+*\d*)")

    # Lines to skip
    SKIP_PATTERNS = [
        "Дата проводки",
        "Код операции",
        "Описание",
        "Сумма",
        "в валюте счета",
        "Страница",
        "АЛЬФА-БАНК",
        "alfabank.ru",
        "Уполномоченное лицо",
        "подпись сотрудника",
        "Ф.И.О. сотрудника",
        "к/с",
        "ул. Каланч",
        "Москва, 107078",
        "+7 495",
        "mail@",
        "Т.Т. Трофимова",
    ]

    def can_parse(self, file_path: Path) -> bool:
        """Check if this is an Alfa Bank PDF statement."""
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
                    for marker in ["альфа-банк", "alfabank", "альфа банк"]
                )
        except Exception:
            return False

    def parse(self, file_path: Path) -> Statement:
        """Parse Alfa Bank PDF statement."""
        full_text = ""
        all_lines: list[str] = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"
                all_lines.extend(page_text.split("\n"))

        # Parse transactions from lines
        transactions = self._parse_lines(all_lines)

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
            bank="Alfa-Bank",
        )

    def _parse_lines(self, lines: list[str]) -> list[Transaction]:
        """Parse transaction lines from PDF text."""
        transactions = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines and known non-transaction lines
            if not line or self._should_skip_line(line):
                i += 1
                continue

            # Try to match a transaction line
            match = self.TRANSACTION_PATTERN.match(line)
            if match:
                date_str = match.group(1)
                code = match.group(2)
                description = match.group(3)
                amount_str = match.group(4)

                # Collect continuation lines
                description_parts = [description]
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()

                    # Check if this is a continuation line
                    if self._is_continuation_line(next_line):
                        description_parts.append(next_line)
                        j += 1
                    else:
                        break

                # Build full description
                full_description = " ".join(description_parts)
                full_description = self._clean_description(full_description)

                # Parse date and amount
                try:
                    date = datetime.strptime(date_str, "%d.%m.%Y")
                    amount = self._parse_amount(amount_str)

                    if amount is not None and full_description:
                        # Extract card number if present
                        card_number = self._extract_card_number(full_description)

                        transaction = Transaction(
                            date=date,
                            posting_date=date,
                            amount=amount,
                            description=full_description,
                            card_number=card_number,
                            bank="Alfa-Bank",
                        )
                        transactions.append(transaction)

                except (ValueError, InvalidOperation):
                    pass

                i = j
            else:
                i += 1

        return transactions

    def _should_skip_line(self, line: str) -> bool:
        """Check if line should be skipped."""
        for pattern in self.SKIP_PATTERNS:
            if pattern in line:
                return True
        return False

    def _is_continuation_line(self, line: str) -> bool:
        """Check if line is a continuation of previous transaction."""
        if not line:
            return False

        # Not a continuation if it starts with a date
        if re.match(r"^\d{2}\.\d{2}\.\d{4}", line):
            return False

        # Not a continuation if it matches skip patterns
        if self._should_skip_line(line):
            return False

        # Lines like "Без НДС.", "операции:", "MCC5814" are continuations
        continuation_markers = [
            "Без НДС",
            "операции:",
            "MCC",
            "место совершения",
        ]
        for marker in continuation_markers:
            if marker in line:
                return True

        # Short lines that look like continuations
        if len(line) < 50 and not re.search(r"\d{2}\.\d{2}\.\d{4}", line):
            if not any(c.isdigit() for c in line[-10:]):  # No amount at end
                return True

        return False

    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse amount string to Decimal."""
        if not amount_str:
            return None

        # Remove RUR suffix and clean
        cleaned = amount_str.strip()
        cleaned = re.sub(r"\s*RU[RB]\s*$", "", cleaned, flags=re.IGNORECASE)

        # Remove spaces (thousands separator), replace comma with dot
        cleaned = cleaned.replace(" ", "").replace(",", ".")

        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    def _clean_description(self, description: str) -> str:
        """Clean and normalize transaction description."""
        # Remove extra whitespace
        cleaned = " ".join(description.split())
        return cleaned.strip()

    def _extract_card_number(self, description: str) -> Optional[str]:
        """Extract card number from description."""
        match = self.CARD_PATTERN.search(description)
        if match:
            card = match.group(1)
            # Extract last 4 digits
            digits = re.findall(r"\d+", card)
            if digits:
                return digits[-1][-4:] if len(digits[-1]) >= 4 else digits[-1]
        return None

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
            income = self._parse_amount(income_match.group(1))

        expense_match = self.EXPENSE_PATTERN.search(text)
        if expense_match:
            expense = self._parse_amount(expense_match.group(1))

        return income, expense
