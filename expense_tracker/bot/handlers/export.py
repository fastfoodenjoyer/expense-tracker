"""Export handlers: Excel and Google Sheets."""

import json
import logging
import tempfile
import traceback
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
from expense_tracker.bot.config import get_settings
from expense_tracker.crypto import Encryptor
from expense_tracker.exporter import Exporter
from expense_tracker.storage import Storage

router = Router()
logger = logging.getLogger(__name__)


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


def get_user_google_credentials(user_id: int) -> tuple[dict | None, str | None]:
    """Get decrypted Google credentials for user.

    Returns:
        Tuple of (credentials_dict, spreadsheet_id).
    """
    storage = Storage()
    creds_encrypted, spreadsheet_id = storage.get_user_google_settings(user_id)

    logger.info(f"User {user_id}: creds_encrypted={bool(creds_encrypted)}, spreadsheet_id={spreadsheet_id}")

    if not creds_encrypted:
        return None, spreadsheet_id

    settings = get_settings()
    encryptor = Encryptor(settings.encryption_key)

    try:
        creds_json = encryptor.decrypt(creds_encrypted)
        creds_dict = json.loads(creds_json)
        logger.info(f"User {user_id}: credentials decrypted OK, client_email={creds_dict.get('client_email', 'N/A')}")
        return creds_dict, spreadsheet_id
    except Exception as e:
        logger.error(f"Failed to decrypt credentials for user {user_id}: {e}")
        logger.error(traceback.format_exc())
        return None, spreadsheet_id


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
        filename = get_export_filename(period)
        with tempfile.TemporaryDirectory() as tmp_dir:
            filepath = Path(tmp_dir) / filename

            exporter = Exporter()
            exporter.export_to_excel(transactions, filepath)

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
    user_id = message.from_user.id
    credentials, spreadsheet_id = get_user_google_credentials(user_id)

    if not credentials:
        await message.answer(
            "⚠️ Google Sheets не настроен.\n\n"
            "Используйте /set_credentials чтобы загрузить JSON ключ.\n"
            "Используйте /set_spreadsheet чтобы указать ID таблицы.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not spreadsheet_id:
        await message.answer(
            "⚠️ Не указан ID таблицы.\n\n"
            "Используйте /set_spreadsheet чтобы указать ID таблицы.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.set_state(GoogleSheetsStates.waiting_for_confirmation)
    await message.answer(
        "Отправить данные в Google Sheets?\n"
        f"📋 ID таблицы: <code>{spreadsheet_id[:30]}...</code>",
        reply_markup=google_sheets_confirm_keyboard(),
    )


@router.callback_query(F.data == "gsheets:confirm")
async def export_gsheets(callback: CallbackQuery, state: FSMContext) -> None:
    """Export to Google Sheets."""
    user_id = callback.from_user.id
    logger.info(f"User {user_id}: Starting Google Sheets export")

    await callback.message.edit_text("⏳ Отправляю данные в Google Sheets...")
    await callback.answer()

    credentials, spreadsheet_id = get_user_google_credentials(user_id)

    if not credentials or not spreadsheet_id:
        await callback.message.edit_text(
            "❌ Ошибка: credentials или spreadsheet_id не найдены.\n"
            "Используйте /set_credentials и /set_spreadsheet для настройки."
        )
        await state.clear()
        return

    storage = Storage()
    transactions = storage.get_transactions(include_internal_transfers=False)
    logger.info(f"User {user_id}: Found {len(transactions)} transactions to export")

    if not transactions:
        await callback.message.edit_text(
            "📤 Google Sheets\n\n"
            "Нет транзакций для экспорта."
        )
        await state.clear()
        return

    try:
        logger.info(f"User {user_id}: Creating exporter and calling export_to_google_sheets")
        exporter = Exporter(credentials_info=credentials)
        added, skipped = exporter.export_to_google_sheets(
            transactions,
            spreadsheet_id,
            "Транзакции",
        )

        logger.info(f"User {user_id}: Export successful - added={added}, skipped={skipped}")
        await callback.message.edit_text(
            "✅ Данные отправлены в Google Sheets\n\n"
            f"➕ Добавлено: {added} записей\n"
            f"⏭️ Пропущено (дубликаты): {skipped}"
        )

    except Exception as e:
        # Log full traceback
        logger.error(f"Google Sheets export failed: {e}")
        logger.error(traceback.format_exc())

        error_msg = str(e) if str(e) else type(e).__name__

        # User-friendly error messages
        error_lower = error_msg.lower()
        if "invalid_grant" in error_lower:
            error_msg = "Невалидные credentials. Попробуйте загрузить их заново."
        elif "not found" in error_lower or "404" in error_lower:
            error_msg = (
                "Таблица не найдена или нет доступа.\n"
                "Убедитесь, что поделились таблицей с Service Account email."
            )
        elif "permission" in error_lower or "403" in error_lower:
            error_msg = (
                "Нет доступа к таблице.\n"
                "Поделитесь таблицей с Service Account email."
            )
        elif "quota" in error_lower or "rate" in error_lower:
            error_msg = "Превышен лимит запросов. Попробуйте позже."

        await callback.message.edit_text(
            f"❌ Ошибка экспорта в Google Sheets:\n\n<code>{error_msg[:500]}</code>"
        )

    await state.clear()
