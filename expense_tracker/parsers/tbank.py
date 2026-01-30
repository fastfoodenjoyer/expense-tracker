"""T-Bank PDF statement parser."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import pdfplumber

from expense_tracker.models import Statement, Transaction

from .base import BaseParser


class TBankParser(BaseParser):
    """Parser for T-Bank (Tinkoff) PDF statements."""

    # Pattern for transaction line: DD.MM.YYYY DD.MM.YYYY [+-]amount ₽ [+-]amount ₽ description card
    # First line format: date1 date2 amount1 amount2 description card_number
    # Note: amount can use either dot or comma as decimal separator
    TRANSACTION_LINE_PATTERN = re.compile(
        r"^(\d{2}\.\d{2}\.\d{4})\s+"  # Date 1
        r"(\d{2}\.\d{2}\.\d{4})\s+"   # Date 2
        r"([+-][\d\s]+[.,]\d{2})\s*₽\s+"  # Amount 1 (dot or comma)
        r"([+-][\d\s]+[.,]\d{2})\s*₽\s+"  # Amount 2 (dot or comma)
        r"(.+?)\s+"                    # Description
        r"(\d{4})$"                    # Card number (last 4 digits)
    )

    # Continuation line with time: HH:MM HH:MM continuation_text
    TIME_LINE_PATTERN = re.compile(
        r"^(\d{2}:\d{2})\s+(\d{2}:\d{2})\s*(.*?)$"
    )

    # Pattern for period extraction
    PERIOD_PATTERN = re.compile(
        r"за период с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4})"
    )

    # Pattern for account number
    ACCOUNT_PATTERN = re.compile(r"Номер лицевого счета[:\s]+(\d+)")

    # Pattern for contract number
    CONTRACT_PATTERN = re.compile(r"Номер договора[:\s]+(\d+)")

    # Pattern for totals
    TOTALS_PATTERN = re.compile(
        r"Пополнения[:\s]+([+-]?[\d\s]+,\d{2})\s*₽.*?"
        r"Расходы[:\s]+([+-]?[\d\s]+,\d{2})\s*₽",
        re.DOTALL
    )

    def can_parse(self, file_path: Path) -> bool:
        """Check if this is a T-Bank PDF statement."""
        if not file_path.suffix.lower() == ".pdf":
            return False

        try:
            with pdfplumber.open(file_path) as pdf:
                if not pdf.pages:
                    return False
                first_page_text = pdf.pages[0].extract_text() or ""
                # Check for T-Bank markers (case insensitive)
                text_lower = first_page_text.lower()
                return any(
                    marker in text_lower
                    for marker in ["т-банк", "тинькофф", "t-bank", "tinkoff", "тбанк", "tbank"]
                )
        except Exception:
            return False

    def parse(self, file_path: Path) -> Statement:
        """Parse T-Bank PDF statement."""
        transactions: list[Transaction] = []
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
            bank="T-Bank",
        )

    def _parse_lines(self, lines: list[str]) -> list[Transaction]:
        """Parse transaction lines from PDF text."""
        transactions = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Try to match a transaction start line
            match = self.TRANSACTION_LINE_PATTERN.match(line)
            if match:
                date1_str = match.group(1)
                date2_str = match.group(2)
                amount1_str = match.group(3)
                amount2_str = match.group(4)
                description = match.group(5)
                card_number = match.group(6)

                # Look for time and continuation in next line(s)
                time1 = None
                time2 = None
                description_parts = [description]

                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()

                    # Check if this is a time line
                    time_match = self.TIME_LINE_PATTERN.match(next_line)
                    if time_match:
                        if time1 is None:
                            time1 = time_match.group(1)
                            time2 = time_match.group(2)
                        continuation = time_match.group(3).strip()
                        if continuation:
                            description_parts.append(continuation)
                        j += 1
                    elif self._is_continuation_line(next_line):
                        # Pure continuation line (no time)
                        description_parts.append(next_line)
                        j += 1
                    else:
                        # Not a continuation - stop
                        break

                # Build full description
                full_description = " ".join(description_parts)
                full_description = self._clean_description(full_description)

                # Parse date with time
                try:
                    if time1:
                        date = datetime.strptime(
                            f"{date1_str} {time1}", "%d.%m.%Y %H:%M"
                        )
                        posting_date = datetime.strptime(
                            f"{date2_str} {time2}", "%d.%m.%Y %H:%M"
                        )
                    else:
                        date = datetime.strptime(date1_str, "%d.%m.%Y")
                        posting_date = datetime.strptime(date2_str, "%d.%m.%Y")

                    # Parse amounts
                    amount = self._parse_amount(amount2_str)  # Card currency amount
                    amount_original = self._parse_amount(amount1_str)

                    if amount is not None and full_description:
                        transaction = Transaction(
                            date=date,
                            posting_date=posting_date,
                            amount=amount,
                            amount_original=amount_original if amount_original != amount else None,
                            description=full_description,
                            card_number=card_number,
                            bank="T-Bank",
                        )
                        transactions.append(transaction)

                except (ValueError, InvalidOperation):
                    pass

                i = j
            else:
                i += 1

        return transactions

    def _is_continuation_line(self, line: str) -> bool:
        """Check if line is a continuation of description."""
        # Not a continuation if it's empty
        if not line:
            return False

        # Not a continuation if it starts with date pattern
        if re.match(r"^\d{2}\.\d{2}\.\d{4}", line):
            return False

        # Not a continuation if it's a header or footer
        skip_patterns = [
            "Дата и время",
            "операции",
            "списания",
            "АО «ТБанк»",
            "универсальная лицензия",
            "БИК",
            "Пополнения",
            "Расходы",
            "Итого",
        ]
        for pattern in skip_patterns:
            if pattern in line:
                return False

        # Not a continuation if it's just a page number
        if re.match(r"^\d+$", line):
            return False

        return True

    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse amount string to Decimal."""
        if not amount_str:
            return None

        # Clean the string: remove spaces, replace comma with dot
        cleaned = amount_str.strip()
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
        match = self.TOTALS_PATTERN.search(text)
        if match:
            income = self._parse_amount(match.group(1))
            expense = self._parse_amount(match.group(2))
            return income, expense
        return None, None
