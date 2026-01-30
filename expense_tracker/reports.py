"""Report generation for expense tracking."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from rich.console import Console
from rich.table import Table

from expense_tracker.models import Category, Transaction
from expense_tracker.storage import Storage


class ReportGenerator:
    """Generate expense reports."""

    def __init__(self, storage: Storage):
        """Initialize report generator.

        Args:
            storage: Storage instance to fetch data from
        """
        self.storage = storage
        self.console = Console()

    def print_summary(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> None:
        """Print expense summary by category.

        Args:
            date_from: Filter by start date
            date_to: Filter by end date
        """
        summary = self.storage.get_summary(date_from, date_to)
        income, expense = self.storage.get_totals(date_from, date_to)

        # Create period string
        period = self._format_period(date_from, date_to)

        # Create summary table
        table = Table(title=f"Расходы по категориям{period}")
        table.add_column("Категория", style="cyan")
        table.add_column("Сумма", justify="right", style="red")
        table.add_column("%", justify="right", style="yellow")

        total = sum(summary.values())

        for category, amount in sorted(summary.items(), key=lambda x: x[1], reverse=True):
            percentage = (amount / total * 100) if total > 0 else Decimal("0")
            table.add_row(
                category,
                f"{amount:,.2f} ₽",
                f"{percentage:.1f}%",
            )

        table.add_section()
        table.add_row(
            "[bold]Всего расходов[/bold]",
            f"[bold red]{total:,.2f} ₽[/bold red]",
            "[bold]100%[/bold]",
        )

        self.console.print()
        self.console.print(table)

        # Print income/expense balance
        self.console.print()
        self.console.print(f"[green]Пополнения: +{income:,.2f} ₽[/green]")
        self.console.print(f"[red]Расходы: -{expense:,.2f} ₽[/red]")
        balance = income - expense
        color = "green" if balance >= 0 else "red"
        self.console.print(f"[{color}]Баланс: {balance:+,.2f} ₽[/{color}]")

    def print_transactions(
        self,
        transactions: list[Transaction],
        title: str = "Транзакции",
    ) -> None:
        """Print transaction list as a table.

        Args:
            transactions: List of transactions to print
            title: Table title
        """
        table = Table(title=title)
        table.add_column("Дата", style="cyan")
        table.add_column("Описание", style="white", max_width=40)
        table.add_column("Категория", style="yellow")
        table.add_column("Сумма", justify="right")
        table.add_column("Карта", style="dim")

        for t in transactions:
            amount_style = "green" if t.amount > 0 else "red"
            amount_str = f"{t.amount:+,.2f} ₽"
            category = t.category.value if t.category else "-"
            card = f"*{t.card_number}" if t.card_number else "-"

            table.add_row(
                t.date.strftime("%d.%m.%Y %H:%M"),
                t.description[:40] + "..." if len(t.description) > 40 else t.description,
                category,
                f"[{amount_style}]{amount_str}[/{amount_style}]",
                card,
            )

        self.console.print()
        self.console.print(table)
        self.console.print(f"\nВсего: {len(transactions)} транзакций")

    def print_top_expenses(
        self,
        category: Optional[Category] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 10,
    ) -> None:
        """Print top expenses.

        Args:
            category: Filter by category
            date_from: Filter by start date
            date_to: Filter by end date
            limit: Maximum number of results
        """
        transactions = self.storage.get_top_expenses(
            category=category,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

        period = self._format_period(date_from, date_to)
        cat_str = f" ({category.value})" if category else ""
        title = f"Топ {limit} расходов{cat_str}{period}"

        self.print_transactions(transactions, title=title)

    def print_import_result(
        self,
        added: int,
        duplicates: int,
        total_income: Decimal,
        total_expense: Decimal,
    ) -> None:
        """Print import result summary.

        Args:
            added: Number of added transactions
            duplicates: Number of duplicate transactions
            total_income: Total income from imported statement
            total_expense: Total expense from imported statement
        """
        self.console.print()
        self.console.print("[bold green]Импорт завершён![/bold green]")
        self.console.print(f"  Добавлено: {added} транзакций")
        if duplicates > 0:
            self.console.print(f"  Пропущено (дубликаты): {duplicates}")
        self.console.print()
        self.console.print(f"[green]Пополнения в выписке: +{total_income:,.2f} ₽[/green]")
        self.console.print(f"[red]Расходы в выписке: -{total_expense:,.2f} ₽[/red]")

    def _format_period(
        self,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> str:
        """Format period string for display."""
        if date_from and date_to:
            return f" ({date_from.strftime('%d.%m.%Y')} - {date_to.strftime('%d.%m.%Y')})"
        elif date_from:
            return f" (с {date_from.strftime('%d.%m.%Y')})"
        elif date_to:
            return f" (по {date_to.strftime('%d.%m.%Y')})"
        return ""
