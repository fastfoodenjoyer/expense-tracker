"""CLI interface for expense tracker."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from expense_tracker.categorizer import Categorizer
from expense_tracker.exporter import Exporter
from expense_tracker.models import Category
from expense_tracker.parsers.tbank import TBankParser
from expense_tracker.reports import ReportGenerator
from expense_tracker.storage import Storage

app = typer.Typer(
    name="expense-tracker",
    help="CLI application for expense analysis based on bank PDF statements.",
    no_args_is_help=True,
)

console = Console()


def get_storage() -> Storage:
    """Get storage instance."""
    return Storage()


def get_reports() -> ReportGenerator:
    """Get report generator instance."""
    return ReportGenerator(get_storage())


def parse_date(date_str: str) -> datetime:
    """Parse date string in DD.MM.YYYY format."""
    return datetime.strptime(date_str, "%d.%m.%Y")


def parse_category(category_str: str) -> Optional[Category]:
    """Parse category string to Category enum."""
    for cat in Category:
        if cat.value.lower() == category_str.lower():
            return cat
    return None


@app.command("import")
def import_statement(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to bank statement PDF file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
) -> None:
    """Import transactions from a bank statement PDF."""
    console.print(f"[cyan]Импорт файла: {path}[/cyan]")

    # Try T-Bank parser
    parser = TBankParser()
    if not parser.can_parse(path):
        console.print("[red]Ошибка: Формат файла не распознан как выписка Т-Банка[/red]")
        raise typer.Exit(1)

    # Parse statement
    try:
        statement = parser.parse(path)
    except Exception as e:
        console.print(f"[red]Ошибка парсинга: {e}[/red]")
        raise typer.Exit(1)

    if not statement.transactions:
        console.print("[yellow]Предупреждение: Транзакции не найдены в файле[/yellow]")
        raise typer.Exit(0)

    # Categorize transactions
    categorizer = Categorizer()
    categorizer.categorize_all(statement.transactions)

    # Store transactions
    storage = get_storage()
    added, duplicates = storage.add_transactions(statement.transactions)

    # Calculate totals
    total_income = statement.calculated_income
    total_expense = statement.calculated_expense

    # Print result
    reports = ReportGenerator(storage)
    reports.print_import_result(added, duplicates, total_income, total_expense)


@app.command("list")
def list_transactions(
    category: Annotated[
        Optional[str],
        typer.Option(
            "--category", "-c",
            help="Filter by category (Продукты, Рестораны, Транспорт, etc.)",
        ),
    ] = None,
    date_from: Annotated[
        Optional[str],
        typer.Option(
            "--from", "-f",
            help="Start date (DD.MM.YYYY)",
        ),
    ] = None,
    date_to: Annotated[
        Optional[str],
        typer.Option(
            "--to", "-t",
            help="End date (DD.MM.YYYY)",
        ),
    ] = None,
    limit: Annotated[
        Optional[int],
        typer.Option(
            "--limit", "-n",
            help="Maximum number of transactions to show",
        ),
    ] = None,
    include_internal_transfers: Annotated[
        bool,
        typer.Option(
            "--include-internal-transfers", "-i",
            help="Include internal transfers between accounts (excluded by default)",
        ),
    ] = False,
) -> None:
    """List transactions with optional filters."""
    # Parse filters
    cat = parse_category(category) if category else None
    from_dt = parse_date(date_from) if date_from else None
    to_dt = parse_date(date_to) if date_to else None

    if category and not cat:
        console.print(f"[yellow]Категория '{category}' не найдена. Доступные категории:[/yellow]")
        for c in Category:
            console.print(f"  - {c.value}")
        raise typer.Exit(1)

    # Get transactions
    storage = get_storage()
    transactions = storage.get_transactions(
        category=cat,
        date_from=from_dt,
        date_to=to_dt,
        limit=limit,
        include_internal_transfers=include_internal_transfers,
    )

    if not transactions:
        console.print("[yellow]Транзакции не найдены[/yellow]")
        raise typer.Exit(0)

    # Print transactions
    reports = ReportGenerator(storage)
    cat_str = f" ({cat.value})" if cat else ""
    reports.print_transactions(transactions, title=f"Транзакции{cat_str}")


@app.command("summary")
def show_summary(
    month: Annotated[
        Optional[int],
        typer.Option(
            "--month", "-m",
            help="Month (1-12)",
            min=1,
            max=12,
        ),
    ] = None,
    year: Annotated[
        Optional[int],
        typer.Option(
            "--year", "-y",
            help="Year (e.g., 2024)",
        ),
    ] = None,
    include_internal_transfers: Annotated[
        bool,
        typer.Option(
            "--include-internal-transfers", "-i",
            help="Include internal transfers between accounts (excluded by default)",
        ),
    ] = False,
) -> None:
    """Show expense summary by category."""
    # Calculate date range
    from_dt = None
    to_dt = None

    if month or year:
        now = datetime.now()
        y = year or now.year
        m = month or now.month

        from_dt = datetime(y, m, 1)
        if m == 12:
            to_dt = datetime(y + 1, 1, 1)
        else:
            to_dt = datetime(y, m + 1, 1)

    # Print summary
    reports = get_reports()
    reports.print_summary(
        date_from=from_dt,
        date_to=to_dt,
        include_internal_transfers=include_internal_transfers,
    )


@app.command("top")
def show_top(
    category: Annotated[
        Optional[str],
        typer.Option(
            "--category", "-c",
            help="Filter by category",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(
            "--limit", "-n",
            help="Number of top expenses to show",
        ),
    ] = 10,
    date_from: Annotated[
        Optional[str],
        typer.Option(
            "--from", "-f",
            help="Start date (DD.MM.YYYY)",
        ),
    ] = None,
    date_to: Annotated[
        Optional[str],
        typer.Option(
            "--to", "-t",
            help="End date (DD.MM.YYYY)",
        ),
    ] = None,
    include_internal_transfers: Annotated[
        bool,
        typer.Option(
            "--include-internal-transfers", "-i",
            help="Include internal transfers between accounts (excluded by default)",
        ),
    ] = False,
) -> None:
    """Show top expenses."""
    # Parse filters
    cat = parse_category(category) if category else None
    from_dt = parse_date(date_from) if date_from else None
    to_dt = parse_date(date_to) if date_to else None

    if category and not cat:
        console.print(f"[yellow]Категория '{category}' не найдена. Доступные категории:[/yellow]")
        for c in Category:
            console.print(f"  - {c.value}")
        raise typer.Exit(1)

    # Print top expenses
    reports = get_reports()
    reports.print_top_expenses(
        category=cat,
        date_from=from_dt,
        date_to=to_dt,
        limit=limit,
        include_internal_transfers=include_internal_transfers,
    )


@app.command("categories")
def list_categories() -> None:
    """List all available categories."""
    console.print("\n[bold]Доступные категории:[/bold]\n")
    for cat in Category:
        console.print(f"  • {cat.value}")
    console.print()


@app.command("export")
def export_transactions(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to output Excel file (.xlsx)",
        ),
    ],
    google_sheet: Annotated[
        Optional[str],
        typer.Option(
            "--google-sheet", "-g",
            help="Google Sheets spreadsheet ID for sync",
        ),
    ] = None,
    worksheet: Annotated[
        str,
        typer.Option(
            "--worksheet", "-w",
            help="Google Sheets worksheet name",
        ),
    ] = "Транзакции",
    credentials: Annotated[
        Optional[Path],
        typer.Option(
            "--credentials",
            help="Path to Google service account JSON",
        ),
    ] = None,
    month: Annotated[
        Optional[int],
        typer.Option(
            "--month", "-m",
            help="Filter by month (1-12)",
            min=1,
            max=12,
        ),
    ] = None,
    year: Annotated[
        Optional[int],
        typer.Option(
            "--year", "-y",
            help="Filter by year (e.g., 2024)",
        ),
    ] = None,
    include_internal_transfers: Annotated[
        bool,
        typer.Option(
            "--include-internal-transfers", "-i",
            help="Include internal transfers between accounts (excluded by default)",
        ),
    ] = False,
) -> None:
    """Export transactions to Excel file and optionally sync to Google Sheets."""
    # Calculate date range
    from_dt = None
    to_dt = None

    if month or year:
        now = datetime.now()
        y = year or now.year
        m = month or now.month

        from_dt = datetime(y, m, 1)
        if m == 12:
            to_dt = datetime(y + 1, 1, 1)
        else:
            to_dt = datetime(y, m + 1, 1)

    # Get transactions
    storage = get_storage()
    transactions = storage.get_transactions(
        date_from=from_dt,
        date_to=to_dt,
        include_internal_transfers=include_internal_transfers,
    )

    if not transactions:
        console.print("[yellow]Нет транзакций для экспорта[/yellow]")
        raise typer.Exit(0)

    # Export to Excel
    exporter = Exporter(credentials_path=credentials)

    try:
        excel_path = exporter.export_to_excel(transactions, path)
        console.print(f"[green]Экспортировано {len(transactions)} транзакций в {excel_path}[/green]")
    except Exception as e:
        console.print(f"[red]Ошибка экспорта в Excel: {e}[/red]")
        raise typer.Exit(1)

    # Sync to Google Sheets if requested
    if google_sheet:
        console.print(f"[cyan]Синхронизация с Google Sheets...[/cyan]")
        try:
            added, skipped = exporter.export_to_google_sheets(
                transactions, google_sheet, worksheet
            )
            console.print(
                f"[green]Google Sheets: добавлено {added}, пропущено дубликатов {skipped}[/green]"
            )
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Ошибка синхронизации с Google Sheets: {e}[/red]")
            raise typer.Exit(1)


if __name__ == "__main__":
    app()
