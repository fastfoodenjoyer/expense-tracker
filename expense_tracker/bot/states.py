"""FSM states for bot dialogs."""

from aiogram.fsm.state import State, StatesGroup


class ImportStates(StatesGroup):
    """States for PDF import flow."""

    waiting_for_bank = State()
    waiting_for_pdf = State()


class SummaryStates(StatesGroup):
    """States for summary report flow."""

    waiting_for_period = State()


class TopExpensesStates(StatesGroup):
    """States for top expenses flow."""

    waiting_for_count = State()


class TransactionsStates(StatesGroup):
    """States for transactions list flow."""

    waiting_for_category = State()
    viewing_transactions = State()


class ExportExcelStates(StatesGroup):
    """States for Excel export flow."""

    waiting_for_period = State()


class GoogleSheetsStates(StatesGroup):
    """States for Google Sheets export flow."""

    waiting_for_confirmation = State()
