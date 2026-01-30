"""Yandex Bank PDF statement parser."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import pdfplumber

from expense_tracker.models import Statement, Transaction

from .base import BaseParser


class YandexBankParser(BaseParser):
    """Parser for Yandex Bank PDF statements."""

    # Pattern for period extraction
    PERIOD_PATTERN = re.compile(
        r"за период с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4})"
    )

    # Pattern for account number
    ACCOUNT_PATTERN = re.compile(r"открыт счёт\s+(\d+)")

    # Pattern for contract number
    CONTRACT_PATTERN = re.compile(r"договор\s*№\s*([A-ZА-Я0-9]+)", re.IGNORECASE)

    # Pattern for totals
    INCOME_PATTERN = re.compile(r"Всего приходных операций\s*([+]?[\d\s]+,\d{2})\s*₽")
    EXPENSE_PATTERN = re.compile(r"Всего расходных операций\s*([–\-]?[\d\s]+,\d{2})\s*₽")

    # Transaction line pattern - matches lines with date and amount
    # Format: Description DD.MM.YYYY DD.MM.YYYY [*card] Amount ₽ Amount ₽
    TRANSACTION_PATTERN = re.compile(
        r"^(.+?)\s+"                           # Description
        r"(\d{2}\.\d{2}\.\d{4})\s+"            # Date 1
        r"(\d{2}\.\d{2}\.\d{4})\s+"            # Date 2
        r"(\*\d{4})?\s*"                       # Optional card number
        r"([+–\-]?[\d\s]+,\d{2})\s*₽\s+"       # Amount 1
        r"([+–\-]?[\d\s]+,\d{2})\s*₽\s*$"      # Amount 2
    )

    # Time continuation pattern
    TIME_PATTERN = re.compile(r"^в\s+(\d{2}:\d{2})\s*$")

    # Lines to skip
    SKIP_PATTERNS = [
        "Описание операции",
        "Дата и время",
        "Дата обработки",
        "Сумма в валюте",
        "операции",
        "Договора",
        "МСК",
        "Карта",
        "Страница",
        "Продолжение на",
        "Входящий остаток",
        "Исходящий остаток",
        "Всего расходных",
        "Всего приходных",
        "С уважением",
        "Начальник отдела",
        "платёжным картам",
        "АО «Яндекс Банк»",
        "Яндекс Банк",
    ]

    def can_parse(self, file_path: Path) -> bool:
        """Check if this is a Yandex Bank PDF statement."""
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
                    for marker in ["яндекс банк", "yandex bank", "bank.yandex"]
                )
        except Exception:
            return False

    def parse(self, file_path: Path) -> Statement:
        """Parse Yandex Bank PDF statement."""
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
        contract_number = self._extract_contract_number(full_text)
        total_income, total_expense = self._extract_totals(full_text)

        return Statement(
            account_number=account_number,
            contract_number=contract_number,
            period_start=period_start,
            period_end=period_end,
            transactions=transactions,
            total_income=total_income,
            total_expense=total_expense,
            bank="Yandex-Bank",
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
                description = match.group(1).strip()
                date1_str = match.group(2)
                date2_str = match.group(3)
                card_number = match.group(4)
                amount1_str = match.group(5)
                amount2_str = match.group(6)

                # Look for time in next line
                time_str = None
                j = i + 1
                description_parts = [description]

                while j < len(lines):
                    next_line = lines[j].strip()

                    # Check for time pattern
                    time_match = self.TIME_PATTERN.match(next_line)
                    if time_match:
                        time_str = time_match.group(1)
                        j += 1
                        continue

                    # Check for description continuation
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
                    if time_str:
                        date = datetime.strptime(f"{date1_str} {time_str}", "%d.%m.%Y %H:%M")
                    else:
                        date = datetime.strptime(date1_str, "%d.%m.%Y")

                    posting_date = datetime.strptime(date2_str, "%d.%m.%Y")
                    amount = self._parse_amount(amount2_str)

                    if amount is not None and full_description:
                        # Clean card number
                        card = card_number.replace("*", "") if card_number else None

                        transaction = Transaction(
                            date=date,
                            posting_date=posting_date,
                            amount=amount,
                            description=full_description,
                            card_number=card,
                            bank="Yandex-Bank",
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

        # Not a continuation if it contains a date pattern at specific position
        if re.search(r"\d{2}\.\d{2}\.\d{4}\s+\d{2}\.\d{2}\.\d{4}", line):
            return False

        # Not a continuation if it's a time line
        if self.TIME_PATTERN.match(line):
            return False

        # Not a continuation if it matches skip patterns
        if self._should_skip_line(line):
            return False

        # Check for typical continuation patterns (e.g., "Банк", "Андреевич П.")
        if any(marker in line for marker in ["Банк", "Андреевич", "YANDEX", "MARKET", "AFISHA"]):
            return True

        return False

    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse amount string to Decimal."""
        if not amount_str:
            return None

        # Clean: remove spaces, replace special minus, replace comma with dot
        cleaned = amount_str.strip()
        cleaned = cleaned.replace(" ", "").replace("–", "-").replace(",", ".")

        try:
            return Decimal(cleaned)
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

    def _extract_contract_number(self, text: str) -> Optional[str]:
        """Extract contract number from text."""
        match = self.CONTRACT_PATTERN.search(text)
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
            if income:
                income = abs(income)

        expense_match = self.EXPENSE_PATTERN.search(text)
        if expense_match:
            expense = self._parse_amount(expense_match.group(1))
            if expense:
                expense = abs(expense)

        return income, expense
