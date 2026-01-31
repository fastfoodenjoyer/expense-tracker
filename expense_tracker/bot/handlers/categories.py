"""Categories handler."""

from aiogram import Router, F
from aiogram.types import Message

from expense_tracker.bot.keyboards import ButtonText
from expense_tracker.models import Category

router = Router()


@router.message(F.text == ButtonText.CATEGORIES)
async def list_categories(message: Message) -> None:
    """Show all available categories."""
    lines = ["📑 Доступные категории:\n"]

    for cat in Category:
        lines.append(f"• {cat.value}")

    await message.answer("\n".join(lines))
