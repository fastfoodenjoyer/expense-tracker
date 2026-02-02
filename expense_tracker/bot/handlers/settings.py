"""User settings handlers: Google credentials management."""

import json

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from expense_tracker.bot.config import get_settings
from expense_tracker.bot.keyboards import main_menu_keyboard
from expense_tracker.crypto import Encryptor
from expense_tracker.storage import Storage

router = Router()


class SettingsStates(StatesGroup):
    """States for settings management."""

    waiting_for_credentials = State()
    waiting_for_spreadsheet_id = State()


# ============ Google Credentials ============


@router.message(F.text == "⚙️ Настройки")
async def show_settings_menu(message: Message) -> None:
    """Show settings menu."""
    storage = Storage()
    user_id = message.from_user.id

    creds_encrypted, spreadsheet_id = storage.get_user_google_settings(user_id)

    status_lines = ["⚙️ <b>Настройки Google Sheets</b>\n"]

    if creds_encrypted:
        status_lines.append("✅ Credentials: установлены")
    else:
        status_lines.append("❌ Credentials: не установлены")

    if spreadsheet_id:
        status_lines.append(f"📋 Spreadsheet ID: <code>{spreadsheet_id[:20]}...</code>")
    else:
        status_lines.append("❌ Spreadsheet ID: не установлен")

    status_lines.append("\n<b>Команды:</b>")
    status_lines.append("/set_credentials - загрузить JSON ключ")
    status_lines.append("/set_spreadsheet - установить ID таблицы")
    status_lines.append("/clear_credentials - удалить credentials")

    await message.answer("\n".join(status_lines))


@router.message(F.text.startswith("/set_credentials"))
async def start_set_credentials(message: Message, state: FSMContext) -> None:
    """Start credentials setup flow."""
    await state.set_state(SettingsStates.waiting_for_credentials)
    await message.answer(
        "📤 Отправьте JSON файл с credentials от Google Service Account.\n\n"
        "<b>Как получить:</b>\n"
        "1. Откройте <a href='https://console.cloud.google.com/'>Google Cloud Console</a>\n"
        "2. Создайте проект (или выберите существующий)\n"
        "3. Включите Google Sheets API\n"
        "4. IAM → Service Accounts → Create\n"
        "5. Keys → Add Key → Create new key → JSON\n"
        "6. Отправьте скачанный JSON файл сюда\n\n"
        "⚠️ Credentials будут зашифрованы и сохранены в базе.",
        disable_web_page_preview=True,
    )


@router.message(SettingsStates.waiting_for_credentials, F.document)
async def process_credentials_file(message: Message, state: FSMContext, bot: Bot) -> None:
    """Process uploaded credentials JSON file."""
    document = message.document

    # Check file extension
    if not document.file_name.lower().endswith(".json"):
        await message.answer("⚠️ Пожалуйста, отправьте файл в формате JSON.")
        return

    # Check file size (service account JSON is usually < 5KB)
    if document.file_size > 50 * 1024:  # 50KB max
        await message.answer("⚠️ Файл слишком большой. Credentials JSON обычно < 5KB.")
        return

    try:
        # Download file
        file = await bot.get_file(document.file_id)
        file_bytes = await bot.download_file(file.file_path)
        content = file_bytes.read().decode("utf-8")

        # Validate JSON
        try:
            creds_data = json.loads(content)
        except json.JSONDecodeError:
            await message.answer("❌ Невалидный JSON файл.")
            return

        # Validate it looks like a service account
        required_fields = ["type", "project_id", "private_key", "client_email"]
        missing = [f for f in required_fields if f not in creds_data]
        if missing:
            await message.answer(
                f"❌ Это не похоже на Service Account JSON.\n"
                f"Отсутствуют поля: {', '.join(missing)}"
            )
            return

        if creds_data.get("type") != "service_account":
            await message.answer(
                "❌ Это не Service Account JSON.\n"
                f"type = {creds_data.get('type')}, ожидается service_account"
            )
            return

        # Encrypt and save
        settings = get_settings()
        encryptor = Encryptor(settings.encryption_key)
        encrypted = encryptor.encrypt(content)

        storage = Storage()
        storage.save_user_google_settings(
            user_id=message.from_user.id,
            credentials_encrypted=encrypted,
        )

        await message.answer(
            f"✅ Credentials сохранены!\n\n"
            f"📧 Service Account: <code>{creds_data.get('client_email', 'N/A')}</code>\n\n"
            "⚠️ Не забудьте поделиться таблицей с этим email!",
            reply_markup=main_menu_keyboard(),
        )

    except Exception as e:
        await message.answer(
            f"❌ Ошибка обработки файла: {e}",
            reply_markup=main_menu_keyboard(),
        )

    await state.clear()


@router.message(SettingsStates.waiting_for_credentials)
async def invalid_credentials_file(message: Message) -> None:
    """Handle non-file messages during credentials setup."""
    await message.answer("⚠️ Пожалуйста, отправьте JSON файл.")


@router.message(F.text.startswith("/set_spreadsheet"))
async def start_set_spreadsheet(message: Message, state: FSMContext) -> None:
    """Start spreadsheet ID setup."""
    # Check if user provided ID directly
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        spreadsheet_id = parts[1].strip()
        await save_spreadsheet_id(message, spreadsheet_id)
        return

    await state.set_state(SettingsStates.waiting_for_spreadsheet_id)
    await message.answer(
        "📋 Отправьте ID таблицы Google Sheets.\n\n"
        "<b>Как найти ID:</b>\n"
        "Откройте таблицу, ID находится в URL:\n"
        "<code>docs.google.com/spreadsheets/d/<b>SPREADSHEET_ID</b>/edit</code>\n\n"
        "Отправьте ID или полную ссылку на таблицу."
    )


@router.message(SettingsStates.waiting_for_spreadsheet_id, F.text)
async def process_spreadsheet_id(message: Message, state: FSMContext) -> None:
    """Process spreadsheet ID input."""
    await save_spreadsheet_id(message, message.text.strip())
    await state.clear()


async def save_spreadsheet_id(message: Message, input_text: str) -> None:
    """Parse and save spreadsheet ID."""
    spreadsheet_id = input_text

    # Extract ID from URL if provided
    if "docs.google.com" in input_text:
        # URL format: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/...
        try:
            parts = input_text.split("/d/")
            if len(parts) > 1:
                spreadsheet_id = parts[1].split("/")[0]
        except Exception:
            pass

    # Validate ID format (alphanumeric, dashes, underscores)
    if not spreadsheet_id or len(spreadsheet_id) < 10:
        await message.answer(
            "❌ Неверный формат ID. ID таблицы обычно выглядит как:\n"
            "<code>1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms</code>"
        )
        return

    storage = Storage()
    storage.save_user_google_settings(
        user_id=message.from_user.id,
        spreadsheet_id=spreadsheet_id,
    )

    await message.answer(
        f"✅ Spreadsheet ID сохранён!\n\n"
        f"📋 ID: <code>{spreadsheet_id}</code>",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text.startswith("/clear_credentials"))
async def clear_credentials(message: Message) -> None:
    """Clear user's Google credentials."""
    storage = Storage()
    deleted = storage.delete_user_google_credentials(message.from_user.id)

    if deleted:
        await message.answer(
            "✅ Credentials удалены.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            "ℹ️ Credentials не были установлены.",
            reply_markup=main_menu_keyboard(),
        )
