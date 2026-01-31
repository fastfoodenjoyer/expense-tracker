"""Bot entry point."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery

from expense_tracker.bot.config import config
from expense_tracker.bot.handlers import setup_routers
from expense_tracker.bot.keyboards import main_menu_keyboard


async def cancel_callback_handler(callback: CallbackQuery) -> None:
    """Global handler for cancel callbacks."""
    from aiogram.fsm.context import FSMContext

    state: FSMContext = callback.bot.fsm_storage.resolve_context(
        callback.bot, callback.from_user.id, callback.message.chat.id
    )
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    await callback.answer()


async def run_bot() -> None:
    """Run the bot."""
    # Validate config
    errors = config.validate()
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create bot and dispatcher
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register global cancel handler
    @dp.callback_query(lambda c: c.data == "cancel")
    async def handle_cancel(callback: CallbackQuery) -> None:
        """Handle cancel button."""
        await callback.message.edit_text("Действие отменено.")
        await callback.answer()

    # Setup routers
    main_router = setup_routers()
    dp.include_router(main_router)

    # Start polling
    logging.info("Starting bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    """Entry point for the bot."""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\nBot stopped.")


if __name__ == "__main__":
    main()
