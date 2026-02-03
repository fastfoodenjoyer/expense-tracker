"""Bot entry point."""

import asyncio
import gc
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from expense_tracker.backup import BackupService
from expense_tracker.bot.config import get_settings
from expense_tracker.bot.handlers import setup_routers

# Global instances
scheduler: AsyncIOScheduler | None = None
bot_instance: Bot | None = None


async def notify_admins(message: str, is_error: bool = False) -> None:
    """Send notification to all admins."""
    if not bot_instance:
        logging.warning("Bot instance not available for admin notifications")
        return

    settings = get_settings()
    if not settings.admin_ids:
        logging.debug("No admin IDs configured for notifications")
        return

    prefix = "❌ Ошибка" if is_error else "✅"
    full_message = f"<b>{prefix}</b>\n\n{message}"

    for admin_id in settings.admin_ids:
        try:
            await bot_instance.send_message(admin_id, full_message)
        except Exception as e:
            logging.error(f"Failed to notify admin {admin_id}: {e}")


async def scheduled_backup() -> None:
    """Scheduled backup job - runs daily at midnight Moscow time (21:00 UTC)."""
    try:
        logging.info("Starting scheduled backup...")
        backup_service = BackupService()
        backup_path, r2_key = backup_service.create_and_upload_backup()

        # Cleanup old backups (keep last 7)
        local_removed = backup_service.cleanup_old_backups(keep_count=7)
        r2_removed = backup_service.cleanup_old_r2_backups(keep_count=7)

        logging.info(
            f"Scheduled backup completed: {backup_path} -> R2:{r2_key}, "
            f"cleaned up {local_removed} local, {r2_removed} R2 backups"
        )

        # Notify admins about success
        if r2_key:
            message = (
                f"База данных успешно забэкаплена в Cloudflare R2.\n\n"
                f"📁 Локальный файл: <code>{backup_path.name}</code>\n"
                f"☁️ R2 путь: <code>{r2_key}</code>\n\n"
                f"🗑 Удалено старых бэкапов:\n"
                f"• Локальных: {local_removed}\n"
                f"• R2: {r2_removed}"
            )
        else:
            message = (
                f"База данных забэкаплена локально (R2 не настроен).\n\n"
                f"📁 Локальный файл: <code>{backup_path.name}</code>\n\n"
                f"🗑 Удалено старых локальных бэкапов: {local_removed}"
            )

        await notify_admins(message, is_error=False)

    except Exception as e:
        error_msg = f"Не удалось создать бэкап базы данных.\n\n<b>Ошибка:</b>\n<code>{str(e)}</code>"
        logging.error(f"Scheduled backup failed: {e}")
        await notify_admins(error_msg, is_error=True)


async def memory_cleanup() -> None:
    """Periodic memory cleanup job."""
    collected = gc.collect()
    logging.debug(f"Garbage collector: collected {collected} objects")


def setup_scheduler() -> AsyncIOScheduler:
    """Setup APScheduler for periodic tasks."""
    global scheduler
    scheduler = AsyncIOScheduler(
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }
    )

    # Daily backup at 00:00 Moscow time (UTC+3) = 21:00 UTC
    scheduler.add_job(
        scheduled_backup,
        CronTrigger(hour=21, minute=0, timezone="UTC"),
        id="daily_backup",
        name="Daily database backup to R2",
        replace_existing=True,
    )

    # Memory cleanup every 30 minutes
    scheduler.add_job(
        memory_cleanup,
        IntervalTrigger(minutes=30),
        id="memory_cleanup",
        name="Periodic memory cleanup",
        replace_existing=True,
    )

    logging.info(
        "Scheduler configured: daily backup at 00:00 Moscow time (21:00 UTC), "
        "memory cleanup every 30 min"
    )
    return scheduler


async def on_startup(bot: Bot) -> None:
    """Startup actions."""
    global bot_instance
    bot_instance = bot

    settings = get_settings()
    settings.ensure_directories()

    # Try to restore from R2 if database doesn't exist
    backup_service = BackupService()
    if not backup_service.check_database_exists() and settings.r2_enabled:
        logging.info("Database not found, attempting to restore from R2...")
        if backup_service.restore_latest_from_r2():
            logging.info("Database restored from R2 backup")
            await notify_admins("База данных восстановлена из R2 бэкапа при запуске.")
        else:
            logging.info("No R2 backup found or restore failed, starting fresh")

    # Migrate categories (re-categorize TRANSFERS and OTHER with current rules)
    from expense_tracker.storage import Storage
    storage = Storage()
    checked, updated = storage.migrate_categories()
    if updated > 0:
        logging.info(f"Category migration: checked {checked}, updated {updated} transactions")
    else:
        logging.debug(f"Category migration: checked {checked}, no updates needed")

    # Setup and start scheduler
    sched = setup_scheduler()
    sched.start()
    logging.info("Backup scheduler started")

    # Notify admins about startup
    await notify_admins("🚀 Бот запущен")


async def on_shutdown(bot: Bot) -> None:
    """Shutdown actions."""
    global scheduler
    logging.info("Shutting down bot...")

    # Create final backup before shutdown
    try:
        logging.info("Creating final backup before shutdown...")
        backup_service = BackupService()
        if backup_service.check_database_exists():
            backup_path, r2_key = backup_service.create_and_upload_backup()
            logging.info(f"Final backup created: {backup_path} -> R2:{r2_key}")
    except Exception as e:
        logging.error(f"Failed to create final backup: {e}")

    # Stop scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logging.info("Scheduler stopped")


async def run_bot() -> None:
    """Run the bot."""
    settings = get_settings()

    # Validate config
    errors = settings.validate()
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
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register startup/shutdown handlers
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

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
