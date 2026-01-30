"""Tests for T-Bank PDF parser."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from expense_tracker.models import Transaction
from expense_tracker.parsers.tbank import TBankParser


class TestTBankParser:
    """Tests for TBankParser."""

    def test_parse_amount_positive(self):
        """Test parsing positive amount."""
        parser = TBankParser()
        assert parser._parse_amount("+1 000.50") == Decimal("1000.50")
        assert parser._parse_amount("+100.00") == Decimal("100.00")
        assert parser._parse_amount("+50 000.99") == Decimal("50000.99")
        # Also works with comma
        assert parser._parse_amount("+1 000,50") == Decimal("1000.50")

    def test_parse_amount_negative(self):
        """Test parsing negative amount."""
        parser = TBankParser()
        assert parser._parse_amount("-1 000.50") == Decimal("-1000.50")
        assert parser._parse_amount("-100.00") == Decimal("-100.00")
        assert parser._parse_amount("-50 000.99") == Decimal("-50000.99")

    def test_parse_amount_without_sign(self):
        """Test parsing amount without explicit sign."""
        parser = TBankParser()
        assert parser._parse_amount("1 000.50") == Decimal("1000.50")
        assert parser._parse_amount("100.00") == Decimal("100.00")

    def test_parse_amount_invalid(self):
        """Test parsing invalid amount."""
        parser = TBankParser()
        assert parser._parse_amount("") is None
        assert parser._parse_amount("abc") is None
        assert parser._parse_amount(None) is None

    def test_clean_description(self):
        """Test description cleaning."""
        parser = TBankParser()
        assert parser._clean_description("  Оплата в   DIXY  ") == "Оплата в DIXY"
        assert parser._clean_description("Перевод\n\nна карту") == "Перевод на карту"

    def test_transaction_line_pattern(self):
        """Test transaction line pattern matching."""
        parser = TBankParser()
        test_lines = [
            "28.01.2026 28.01.2026 -1 382.63 ₽ -1 382.63 ₽ Оплата в LENTA-0010 4015",
            "28.01.2026 28.01.2026 +5 000.00 ₽ +5 000.00 ₽ Внутрибанковский перевод 2934",
        ]

        for line in test_lines:
            match = parser.TRANSACTION_LINE_PATTERN.match(line)
            assert match is not None, f"Failed to match: {line}"

    def test_time_line_pattern(self):
        """Test time line pattern matching."""
        parser = TBankParser()
        test_lines = [
            "18:30 18:45 SANKT-PETERBU RUS",
            "17:51 18:06 N3044 g. Sankt-Pete RUS",
            "10:07 10:08 номеру телефона",
        ]

        for line in test_lines:
            match = parser.TIME_LINE_PATTERN.match(line)
            assert match is not None, f"Failed to match: {line}"
            assert match.group(1) is not None  # time1
            assert match.group(2) is not None  # time2

    def test_is_continuation_line(self):
        """Test continuation line detection."""
        parser = TBankParser()

        # Should be continuation
        assert parser._is_continuation_line("SANKT-PETERBU RUS") is True
        assert parser._is_continuation_line("+79992182326") is True
        assert parser._is_continuation_line("договор 5651052226") is True

        # Should NOT be continuation
        assert parser._is_continuation_line("") is False
        assert parser._is_continuation_line("28.01.2026 28.01.2026 ...") is False
        assert parser._is_continuation_line("Дата и время операции") is False
        assert parser._is_continuation_line("АО «ТБанк» универсальная лицензия") is False
        assert parser._is_continuation_line("123") is False  # Page number

    def test_extract_period(self):
        """Test period extraction from text."""
        parser = TBankParser()
        text = "Движение средств за период с 01.01.2024 по 31.01.2024"
        start, end = parser._extract_period(text)

        assert start == datetime(2024, 1, 1)
        assert end == datetime(2024, 1, 31)

    def test_extract_period_not_found(self):
        """Test period extraction when not found."""
        parser = TBankParser()
        text = "Some random text without period"
        start, end = parser._extract_period(text)

        assert start is None
        assert end is None

    def test_extract_account_number(self):
        """Test account number extraction."""
        parser = TBankParser()
        text = "Номер лицевого счета: 40817810700005933169"
        account = parser._extract_account_number(text)
        assert account == "40817810700005933169"

    def test_extract_contract_number(self):
        """Test contract number extraction."""
        parser = TBankParser()
        text = "Номер договора: 5082383349"
        contract = parser._extract_contract_number(text)
        assert contract == "5082383349"

    def test_can_parse_non_pdf(self):
        """Test can_parse returns False for non-PDF files."""
        parser = TBankParser()
        assert parser.can_parse(Path("test.txt")) is False
        assert parser.can_parse(Path("test.csv")) is False

    def test_parse_lines(self):
        """Test parsing transaction lines."""
        parser = TBankParser()
        lines = [
            "28.01.2026 28.01.2026 -1 382.63 ₽ -1 382.63 ₽ Оплата в LENTA-0010 4015",
            "18:30 18:45 SANKT-PETERBU RUS",
            "28.01.2026 28.01.2026 +5 000.00 ₽ +5 000.00 ₽ Внутрибанковский перевод 2934",
            "17:50 17:51 с договора 8121253515",
        ]

        transactions = parser._parse_lines(lines)
        assert len(transactions) == 2

        # First transaction
        assert transactions[0].amount == Decimal("-1382.63")
        assert "LENTA" in transactions[0].description
        assert transactions[0].card_number == "4015"
        assert transactions[0].date == datetime(2026, 1, 28, 18, 30)

        # Second transaction (income)
        assert transactions[1].amount == Decimal("5000.00")
        assert "перевод" in transactions[1].description.lower()
        assert transactions[1].card_number == "2934"


class TestCategorizer:
    """Tests for transaction categorizer."""

    def test_categorize_groceries(self):
        """Test categorizing grocery transactions."""
        from expense_tracker.categorizer import Categorizer
        from expense_tracker.models import Category

        categorizer = Categorizer()

        transactions = [
            Transaction(
                date=datetime.now(),
                amount=Decimal("-500"),
                description="Оплата в DIXY-78598D SANKT-PETERBU RUS",
            ),
            Transaction(
                date=datetime.now(),
                amount=Decimal("-1000"),
                description="PYATEROCHKA 123",
            ),
            Transaction(
                date=datetime.now(),
                amount=Decimal("-2000"),
                description="Оплата в LENTA-0010 SANKT-PETERBU RUS",
            ),
            Transaction(
                date=datetime.now(),
                amount=Decimal("-500"),
                description="Оплата в MAGNIT MM KARGO",
            ),
            Transaction(
                date=datetime.now(),
                amount=Decimal("-300"),
                description="Оплата в PEREKRYOSTOK VARSHAVSK",
            ),
        ]

        for t in transactions:
            category = categorizer.categorize(t)
            assert category == Category.GROCERIES, f"Failed for: {t.description}"

    def test_categorize_restaurants(self):
        """Test categorizing restaurant transactions."""
        from expense_tracker.categorizer import Categorizer
        from expense_tracker.models import Category

        categorizer = Categorizer()

        transactions = [
            Transaction(
                date=datetime.now(),
                amount=Decimal("-500"),
                description="Оплата в TOKYO CITY SANKT-PETERBU RUS",
            ),
            Transaction(
                date=datetime.now(),
                amount=Decimal("-300"),
                description="Оплата в Y.M*VKUSNOITOCHKA MOSKVA RUS",
            ),
            Transaction(
                date=datetime.now(),
                amount=Decimal("-400"),
                description="Оплата в Rostics Moskva RUS",
            ),
        ]

        for t in transactions:
            category = categorizer.categorize(t)
            assert category == Category.RESTAURANTS, f"Failed for: {t.description}"

    def test_categorize_transfers(self):
        """Test categorizing transfer transactions."""
        from expense_tracker.categorizer import Categorizer
        from expense_tracker.models import Category

        categorizer = Categorizer()

        transactions = [
            Transaction(
                date=datetime.now(),
                amount=Decimal("-5000"),
                description="Внутрибанковский перевод с договора 8121253515",
            ),
            Transaction(
                date=datetime.now(),
                amount=Decimal("-10000"),
                description="Внешний перевод по номеру телефона +79992182326",
            ),
            Transaction(
                date=datetime.now(),
                amount=Decimal("-1000"),
                description="Внутренний перевод на договор 5651052226",
            ),
        ]

        for t in transactions:
            category = categorizer.categorize(t)
            assert category == Category.TRANSFERS, f"Failed for: {t.description}"

    def test_categorize_communication(self):
        """Test categorizing communication transactions."""
        from expense_tracker.categorizer import Categorizer
        from expense_tracker.models import Category

        categorizer = Categorizer()

        t = Transaction(
            date=datetime.now(),
            amount=Decimal("-500"),
            description="Оплата в BEELINE SVYAZ MOSKVA RUS",
        )

        category = categorizer.categorize(t)
        assert category == Category.COMMUNICATION

    def test_categorize_unknown(self):
        """Test categorizing unknown transactions."""
        from expense_tracker.categorizer import Categorizer
        from expense_tracker.models import Category

        categorizer = Categorizer()

        t = Transaction(
            date=datetime.now(),
            amount=Decimal("-500"),
            description="Some unknown merchant XYZ",
        )

        category = categorizer.categorize(t)
        assert category == Category.OTHER
