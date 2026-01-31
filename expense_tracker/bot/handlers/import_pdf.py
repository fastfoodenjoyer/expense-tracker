"""PDF import handler."""

import tempfile
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from expense_tracker.bot.keyboards import (
    bank_selection_keyboard,
    main_menu_keyboard,
    ButtonText,
)
from expense_tracker.bot.states import ImportStates
from expense_tracker.categorizer import Categorizer
from expense_tracker.parsers import (
    TBankParser,
    AlfaBankParser,
    YandexBankParser,
    OzonBankParser,
)
from expense_tracker.storage import Storage

router = Router()

# Bank name to parser mapping
BANK_PARSERS = {
    "tbank": (TBankParser, "T-Bank"),
    "alfa": (AlfaBankParser, "Альфа-Банк"),
    "yandex": (YandexBankParser, "Яндекс Банк"),
    "ozon": (OzonBankParser, "Озон Банк"),
}


@router.message(F.text == ButtonText.ADD_TRANSACTIONS)
async def start_import(message: Message, state: FSMContext) -> None:
    """Start PDF import flow."""
    await state.set_state(ImportStates.waiting_for_bank)
    await message.answer(
        "Выберите банк:",
        reply_markup=bank_selection_keyboard(),
    )


@router.callback_query(F.data.startswith("bank:"))
async def select_bank(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle bank selection."""
    bank_key = callback.data.split(":")[1]

    if bank_key not in BANK_PARSERS:
        await callback.answer("Неизвестный банк", show_alert=True)
        return

    _, bank_name = BANK_PARSERS[bank_key]

    await state.update_data(bank=bank_key)
    await state.set_state(ImportStates.waiting_for_pdf)

    await callback.message.edit_text(
        f"Отправьте PDF-выписку из {bank_name}"
    )
    await callback.answer()


@router.message(ImportStates.waiting_for_pdf, F.document)
async def process_pdf(message: Message, state: FSMContext, bot: Bot) -> None:
    """Process uploaded PDF file."""
    document = message.document

    # Check file extension
    if not document.file_name.lower().endswith(".pdf"):
        await message.answer(
            "⚠️ Пожалуйста, отправьте файл в формате PDF."
        )
        return

    # Get selected bank
    data = await state.get_data()
    bank_key = data.get("bank")

    if not bank_key or bank_key not in BANK_PARSERS:
        await message.answer(
            "⚠️ Ошибка: банк не выбран. Начните заново.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        return

    parser_class, bank_name = BANK_PARSERS[bank_key]

    # Download file
    await message.answer("⏳ Обрабатываю файл...")

    try:
        file = await bot.get_file(document.file_id)
        file_bytes = await bot.download_file(file.file_path)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes.read())
            tmp_path = Path(tmp.name)

        try:
            # Parse statement
            parser = parser_class()
            statement = parser.parse(tmp_path)

            if not statement.transactions:
                await message.answer(
                    "⚠️ Транзакции не найдены в файле.",
                    reply_markup=main_menu_keyboard(),
                )
                await state.clear()
                return

            # Categorize transactions
            categorizer = Categorizer()
            categorizer.categorize_all(statement.transactions)

            # Store transactions
            storage = Storage()
            added, duplicates = storage.add_transactions(statement.transactions)

            # Calculate totals
            total_income = statement.calculated_income
            total_expense = statement.calculated_expense

            # Format result
            result_text = (
                f"✅ Импорт завершён!\n\n"
                f"🏦 Банк: {bank_name}\n"
                f"➕ Добавлено: {added} транзакций\n"
            )

            if duplicates > 0:
                result_text += f"⏭️ Пропущено (дубликаты): {duplicates}\n"

            result_text += (
                f"\n💰 Пополнения: +{total_income:,.2f} ₽\n"
                f"💸 Расходы: -{total_expense:,.2f} ₽"
            )

            await message.answer(result_text, reply_markup=main_menu_keyboard())

        finally:
            # Clean up temp file
            tmp_path.unlink(missing_ok=True)

    except Exception as e:
        await message.answer(
            f"❌ Ошибка обработки файла: {e}",
            reply_markup=main_menu_keyboard(),
        )

    await state.clear()


@router.message(ImportStates.waiting_for_pdf)
async def invalid_file(message: Message) -> None:
    """Handle non-PDF messages during import."""
    await message.answer(
        "⚠️ Пожалуйста, отправьте файл в формате PDF."
    )
