"""Start command and main menu handler."""

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from expense_tracker.bot.keyboards import main_menu_keyboard, ButtonText
from expense_tracker.bot.config import config

router = Router()


def is_user_allowed(user_id: int) -> bool:
    """Check if user is allowed to use the bot."""
    if not config.allowed_users:
        return True
    return user_id in config.allowed_users


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start command."""
    if not is_user_allowed(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этому боту.")
        return

    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в Expense Tracker!\n\n"
        "Я помогу вам управлять расходами:\n"
        "• Импортировать выписки из банков\n"
        "• Просматривать статистику по категориям\n"
        "• Экспортировать данные в Excel и Google Sheets\n\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == ButtonText.CANCEL)
async def handle_cancel(message: Message, state: FSMContext) -> None:
    """Handle cancel button from reply keyboard."""
    await state.clear()
    await message.answer(
        "Действие отменено. Выберите действие:",
        reply_markup=main_menu_keyboard(),
    )
