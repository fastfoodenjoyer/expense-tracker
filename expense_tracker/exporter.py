"""Export transactions to Excel and Google Sheets."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from expense_tracker.models import Transaction

# Column headers for export
EXPORT_COLUMNS = [
    "Дата",
    "Время",
    "Дата списания",
    "Сумма",
    "Сумма в валюте операции",
    "Валюта",
    "Категория",
    "Описание",
    "Карта",
    "Банк",
]


class Exporter:
    """Export transactions to Excel and Google Sheets."""

    def __init__(self, credentials_path: Optional[Path] = None):
        """Initialize exporter.

        Args:
            credentials_path: Path to Google service account JSON.
                            Defaults to ~/.expense-tracker/credentials.json
        """
        self.credentials_path = credentials_path or (
            Path.home() / ".expense-tracker" / "credentials.json"
        )

    def _transaction_to_row(self, transaction: Transaction) -> list:
        """Convert transaction to a row for export.

        Args:
            transaction: Transaction to convert

        Returns:
            List of values for each column
        """
        return [
            transaction.date.strftime("%d.%m.%Y"),
            transaction.date.strftime("%H:%M:%S"),
            transaction.posting_date.strftime("%d.%m.%Y")
            if transaction.posting_date
            else "",
            float(transaction.amount),
            float(transaction.amount_original)
            if transaction.amount_original
            else "",
            transaction.currency,
            transaction.category.value if transaction.category else "",
            transaction.description,
            transaction.card_number or "",
            transaction.bank,
        ]

    def export_to_excel(
        self, transactions: list[Transaction], filepath: Path
    ) -> Path:
        """Export transactions to Excel file.

        Args:
            transactions: List of transactions to export
            filepath: Path to output Excel file

        Returns:
            Path to created file
        """
        wb = Workbook()
        ws = wb.active
        ws.title = "Транзакции"

        # Style definitions
        header_font = Font(bold=True)
        header_alignment = Alignment(horizontal="center", vertical="center")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        # Write headers
        for col_idx, header in enumerate(EXPORT_COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thin_border

        # Write data
        for row_idx, transaction in enumerate(transactions, start=2):
            row_data = self._transaction_to_row(transaction)
            for col_idx, value in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = thin_border

        # Auto-adjust column widths
        for col_idx, _ in enumerate(EXPORT_COLUMNS, start=1):
            col_letter = get_column_letter(col_idx)
            max_length = 0
            for row in ws.iter_rows(
                min_col=col_idx, max_col=col_idx, min_row=1, max_row=ws.max_row
            ):
                for cell in row:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = min(max_length + 2, 50)

        # Save file
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        wb.save(filepath)

        return filepath

    def _get_gspread_client(self):
        """Get authenticated gspread client.

        Returns:
            Authenticated gspread client

        Raises:
            FileNotFoundError: If credentials file not found
        """
        import gspread
        from google.oauth2.service_account import Credentials

        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"Google credentials not found at {self.credentials_path}\n"
                "Please create a service account and download the JSON key:\n"
                "1. Go to https://console.cloud.google.com/\n"
                "2. Create a service account\n"
                "3. Download the JSON key\n"
                f"4. Save it to {self.credentials_path}"
            )

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = Credentials.from_service_account_file(
            str(self.credentials_path), scopes=scopes
        )
        return gspread.authorize(credentials)

    def _find_duplicates(
        self, worksheet, transactions: list[Transaction]
    ) -> set[tuple]:
        """Find existing transactions in worksheet to avoid duplicates.

        Args:
            worksheet: gspread worksheet
            transactions: Transactions to check

        Returns:
            Set of tuples representing existing rows (all fields)
        """
        existing_rows = set()

        # Get all existing data (skip header row)
        all_values = worksheet.get_all_values()
        if len(all_values) > 1:
            for row in all_values[1:]:
                # Convert row to tuple for comparison
                if len(row) >= len(EXPORT_COLUMNS):
                    existing_rows.add(tuple(row[: len(EXPORT_COLUMNS)]))

        return existing_rows

    def export_to_google_sheets(
        self,
        transactions: list[Transaction],
        spreadsheet_id: str,
        worksheet_name: str = "Транзакции",
    ) -> tuple[int, int]:
        """Export transactions to Google Sheets.

        Args:
            transactions: List of transactions to export
            spreadsheet_id: Google Sheets spreadsheet ID
            worksheet_name: Name of worksheet to use

        Returns:
            Tuple of (added_count, skipped_duplicates_count)
        """
        client = self._get_gspread_client()
        spreadsheet = client.open_by_key(spreadsheet_id)

        # Get or create worksheet
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except Exception:
            worksheet = spreadsheet.add_worksheet(
                title=worksheet_name, rows=1000, cols=len(EXPORT_COLUMNS)
            )

        # Check if headers exist
        all_values = worksheet.get_all_values()
        if not all_values:
            # Add headers
            worksheet.append_row(EXPORT_COLUMNS)
            all_values = [EXPORT_COLUMNS]

        # Find duplicates
        existing_rows = self._find_duplicates(worksheet, transactions)

        # Prepare rows to add
        rows_to_add = []
        skipped = 0

        for transaction in transactions:
            row_data = self._transaction_to_row(transaction)
            # Convert to strings for comparison (as they come from sheet)
            row_tuple = tuple(str(v) if v != "" else "" for v in row_data)

            if row_tuple in existing_rows:
                skipped += 1
            else:
                rows_to_add.append(row_data)
                existing_rows.add(row_tuple)

        # Batch append new rows
        if rows_to_add:
            worksheet.append_rows(rows_to_add)

        return len(rows_to_add), skipped
