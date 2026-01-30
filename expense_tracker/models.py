"""Data models for expense tracking."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    """Transaction categories."""

    GROCERIES = "Продукты"
    RESTAURANTS = "Рестораны"
    TRANSPORT = "Транспорт"
    TRANSFERS = "Переводы"
    COMMUNICATION = "Связь"
    ENTERTAINMENT = "Развлечения"
    HEALTH = "Здоровье"
    CLOTHING = "Одежда"
    CASHBACK = "Кэшбэк"
    CASH = "Наличные"
    OTHER = "Прочее"


class Transaction(BaseModel):
    """Single financial transaction."""

    date: datetime = Field(description="Transaction date and time")
    posting_date: Optional[datetime] = Field(
        default=None, description="Date when transaction was posted"
    )
    amount: Decimal = Field(description="Transaction amount (negative for expenses)")
    amount_original: Optional[Decimal] = Field(
        default=None, description="Amount in original currency"
    )
    currency: str = Field(default="RUB", description="Transaction currency")
    description: str = Field(description="Transaction description")
    category: Optional[Category] = Field(
        default=None, description="Transaction category"
    )
    card_number: Optional[str] = Field(
        default=None, description="Last 4 digits of card number"
    )
    bank: str = Field(default="T-Bank", description="Bank name")

    def is_expense(self) -> bool:
        """Check if transaction is an expense."""
        return self.amount < 0

    def is_income(self) -> bool:
        """Check if transaction is an income."""
        return self.amount > 0


class Statement(BaseModel):
    """Bank statement with transactions."""

    account_number: Optional[str] = Field(
        default=None, description="Bank account number"
    )
    contract_number: Optional[str] = Field(default=None, description="Contract number")
    period_start: Optional[datetime] = Field(
        default=None, description="Statement period start"
    )
    period_end: Optional[datetime] = Field(
        default=None, description="Statement period end"
    )
    transactions: list[Transaction] = Field(
        default_factory=list, description="List of transactions"
    )
    total_income: Optional[Decimal] = Field(
        default=None, description="Total income amount"
    )
    total_expense: Optional[Decimal] = Field(
        default=None, description="Total expense amount"
    )
    bank: str = Field(default="T-Bank", description="Bank name")

    @property
    def calculated_income(self) -> Decimal:
        """Calculate total income from transactions."""
        return sum(
            (t.amount for t in self.transactions if t.is_income()), Decimal("0")
        )

    @property
    def calculated_expense(self) -> Decimal:
        """Calculate total expenses from transactions."""
        return sum(
            (abs(t.amount) for t in self.transactions if t.is_expense()), Decimal("0")
        )
