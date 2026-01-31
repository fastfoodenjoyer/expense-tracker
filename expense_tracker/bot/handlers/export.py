"""Export handlers: Excel and Google Sheets."""

import tempfile
from datetime import datetime
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from expense_tracker.bot.keyboards import (
    period_selection_keyboard,
    google_sheets_confirm_keyboard,
    main_menu_keyboard,
    ButtonText,
)
from expense_tracker.bot.states import ExportExcelStates, GoogleSheetsStates
from expense_tracker.bot.config import config
from expense_tracker.exporter import Exporter
from expense_tracker.storage import Storage

router = Router()


def get_period_dates(period: str) -> tuple:
    """Get date range for a period."""
    now = datetime.now()

    if period == "current_month":
        from_dt = datetime(now.year, now.month, 1)
        if now.month == 12:
            to_dt = datetime(now.year + 1, 1, 1)
        else:
            to_dt = datetime(now.year, now.month + 1, 1)
        return from_dt, to_dt

    elif period == "last_month":
        if now.month == 1:
            from_dt = datetime(now.year - 1, 12, 1)
            to_dt = datetime(now.year, 1, 1)
        else:
            from_dt = datetime(now.year, now.month - 1, 1)
            to_dt = datetime(now.year, now.month, 1)
        return from_dt, to_dt

    return None, None


def get_export_filename(period: str) -> str:
    """Generate export filename based on period."""
    now = datetime.now()

    if period == "current_month":
        return f"expenses_{now.year}_{now.month:02d}.xlsx"
    elif period == "last_month":
        if now.month == 1:
            return f"expenses_{now.year - 1}_12.xlsx"
        return f"expenses_{now.year}_{now.month - 1:02d}.xlsx"
    return "expenses_all.xlsx"


# ============ Excel export handlers ============


@router.message(F.text == ButtonText.EXPORT_EXCEL)
async def start_excel_export(message: Message, state: FSMContext) -> None:
    """Start Excel export flow."""
    await state.set_state(ExportExcelStates.waiting_for_period)
    await message.answer(
        "За какой период?",
        reply_markup=period_selection_keyboard("excel"),
    )


@router.callback_query(F.data.startswith("excel:"))
async def export_excel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Export to Excel for selected period."""
    period = callback.data.split(":")[1]
    from_dt, to_dt = get_period_dates(period)

    storage = Storage()
    transactions = storage.get_transactions(
        date_from=from_dt,
        date_to=to_dt,
        include_internal_transfers=False,
    )

    if not transactions:
        await callback.message.edit_text(
            "📁 Экспорт Excel\n\n"
            "Нет транзакций для экспорта."
        )
        await state.clear()
        await callback.answer()
        return

    await callback.message.edit_text("⏳ Формирую файл...")
    await callback.answer()

    try:
        # Create temp file
        filename = get_export_filename(period)
        with tempfile.TemporaryDirectory() as tmp_dir:
            filepath = Path(tmp_dir) / filename

            exporter = Exporter()
            exporter.export_to_excel(transactions, filepath)

            # Send file
            document = FSInputFile(filepath, filename=filename)
            await bot.send_document(
                callback.message.chat.id,
                document,
                caption=f"📁 Экспортировано {len(transactions)} транзакций",
            )

    except Exception as e:
        await bot.send_message(
            callback.message.chat.id,
            f"❌ Ошибка экспорта: {e}",
            reply_markup=main_menu_keyboard(),
        )

    await state.clear()


# ============ Google Sheets export handlers ============


@router.message(F.text == ButtonText.GOOGLE_SHEETS)
async def start_gsheets_export(message: Message, state: FSMContext) -> None:
    """Start Google Sheets export flow."""
    if not config.google_spreadsheet_id:
        await message.answer(
            "⚠️ Google Sheets не настроен.\n\n"
            "Добавьте GOOGLE_SPREADSHEET_ID в файл .env",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.set_state(GoogleSheetsStates.waiting_for_confirmation)
    await message.answer(
        "Отправить данные в Google Sheets?\n"
        f"📋 ID таблицы: {config.google_spreadsheet_id[:20]}...",
        reply_markup=google_sheets_confirm_keyboard(),
    )


@router.callback_query(F.data == "gsheets:confirm")
async def export_gsheets(callback: CallbackQuery, state: FSMContext) -> None:
    """Export to Google Sheets."""
    await callback.message.edit_text("⏳ Отправляю данные в Google Sheets...")
    await callback.answer()

    storage = Storage()
    transactions = storage.get_transactions(include_internal_transfers=False)

    if not transactions:
        await callback.message.edit_text(
            "📤 Google Sheets\n\n"
            "Нет транзакций для экспорта."
        )
        await state.clear()
        return

    try:
        exporter = Exporter(credentials_path=config.credentials_path)
        added, skipped = exporter.export_to_google_sheets(
            transactions,
            config.google_spreadsheet_id,
            "Транзакции",
        )

        await callback.message.edit_text(
            "✅ Данные отправлены в Google Sheets\n\n"
            f"➕ Добавлено: {added} записей\n"
            f"⏭️ Пропущено (дубликаты): {skipped}"
        )

    except FileNotFoundError as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {e}\n\n"
            "Создайте service account и сохраните credentials.json в "
            "~/.expense-tracker/"
        )

    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")

    await state.clear()
