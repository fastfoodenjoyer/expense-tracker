"""Keyboard layouts for the bot."""

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from expense_tracker.models import Category


# Button texts
class ButtonText:
    """Button text constants."""

    # Main menu
    ADD_TRANSACTIONS = "📥 Добавить транзакции"
    SUMMARY = "📊 Сводка по категориям"
    TOP_EXPENSES = "🔝 Топ расходов"
    TRANSACTIONS = "📋 Транзакции"
    EXPORT_EXCEL = "📁 Экспорт Excel"
    GOOGLE_SHEETS = "📤 Google Sheets"
    CATEGORIES = "📑 Категории"

    # Banks
    TBANK = "T-Bank"
    ALFA = "Альфа-Банк"
    YANDEX = "Яндекс Банк"
    OZON = "Озон Банк"

    # Periods
    CURRENT_MONTH = "Текущий месяц"
    LAST_MONTH = "Прошлый месяц"
    ALL_TIME = "За всё время"

    # Top counts
    TOP_5 = "5"
    TOP_10 = "10"
    TOP_20 = "20"

    # Category filter
    ALL_CATEGORIES = "Все"

    # Navigation
    BACK = "◀️ Назад"
    NEXT = "▶️ Далее"

    # Actions
    CANCEL = "❌ Отмена"
    CONFIRM = "✅ Отправить"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Create main menu keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=ButtonText.ADD_TRANSACTIONS)],
            [KeyboardButton(text=ButtonText.SUMMARY)],
            [
                KeyboardButton(text=ButtonText.TOP_EXPENSES),
                KeyboardButton(text=ButtonText.TRANSACTIONS),
            ],
            [
                KeyboardButton(text=ButtonText.EXPORT_EXCEL),
                KeyboardButton(text=ButtonText.GOOGLE_SHEETS),
            ],
            [KeyboardButton(text=ButtonText.CATEGORIES)],
        ],
        resize_keyboard=True,
    )


def bank_selection_keyboard() -> InlineKeyboardMarkup:
    """Create bank selection inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=ButtonText.TBANK, callback_data="bank:tbank"),
                InlineKeyboardButton(text=ButtonText.ALFA, callback_data="bank:alfa"),
            ],
            [
                InlineKeyboardButton(
                    text=ButtonText.YANDEX, callback_data="bank:yandex"
                ),
                InlineKeyboardButton(text=ButtonText.OZON, callback_data="bank:ozon"),
            ],
            [
                InlineKeyboardButton(
                    text=ButtonText.CANCEL, callback_data="cancel"
                ),
            ],
        ]
    )


def period_selection_keyboard(prefix: str = "period") -> InlineKeyboardMarkup:
    """Create period selection inline keyboard.

    Args:
        prefix: Callback data prefix for routing.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ButtonText.CURRENT_MONTH,
                    callback_data=f"{prefix}:current_month",
                ),
                InlineKeyboardButton(
                    text=ButtonText.LAST_MONTH,
                    callback_data=f"{prefix}:last_month",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=ButtonText.ALL_TIME, callback_data=f"{prefix}:all_time"
                ),
            ],
            [
                InlineKeyboardButton(text=ButtonText.CANCEL, callback_data="cancel"),
            ],
        ]
    )


def top_count_keyboard() -> InlineKeyboardMarkup:
    """Create top count selection inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=ButtonText.TOP_5, callback_data="top:5"),
                InlineKeyboardButton(text=ButtonText.TOP_10, callback_data="top:10"),
                InlineKeyboardButton(text=ButtonText.TOP_20, callback_data="top:20"),
            ],
            [
                InlineKeyboardButton(text=ButtonText.CANCEL, callback_data="cancel"),
            ],
        ]
    )


def category_filter_keyboard(prefix: str = "cat_filter") -> InlineKeyboardMarkup:
    """Create category filter inline keyboard.

    Args:
        prefix: Callback data prefix for routing.
    """
    # Create buttons for each category (2 per row)
    buttons = [
        [
            InlineKeyboardButton(
                text=ButtonText.ALL_CATEGORIES, callback_data=f"{prefix}:all"
            )
        ]
    ]

    category_buttons = []
    for cat in Category:
        category_buttons.append(
            InlineKeyboardButton(
                text=cat.value, callback_data=f"{prefix}:{cat.name}"
            )
        )

    # Group in pairs
    for i in range(0, len(category_buttons), 2):
        row = category_buttons[i : i + 2]
        buttons.append(row)

    buttons.append(
        [InlineKeyboardButton(text=ButtonText.CANCEL, callback_data="cancel")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def pagination_keyboard(
    current_page: int,
    total_pages: int,
    prefix: str = "page",
) -> InlineKeyboardMarkup:
    """Create pagination inline keyboard.

    Args:
        current_page: Current page number (0-indexed).
        total_pages: Total number of pages.
        prefix: Callback data prefix for routing.
    """
    buttons = []

    if current_page > 0:
        buttons.append(
            InlineKeyboardButton(
                text=ButtonText.BACK, callback_data=f"{prefix}:{current_page - 1}"
            )
        )

    if current_page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                text=ButtonText.NEXT, callback_data=f"{prefix}:{current_page + 1}"
            )
        )

    keyboard = []
    if buttons:
        keyboard.append(buttons)

    keyboard.append(
        [InlineKeyboardButton(text=ButtonText.CANCEL, callback_data="cancel")]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def google_sheets_confirm_keyboard() -> InlineKeyboardMarkup:
    """Create Google Sheets confirmation inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ButtonText.CONFIRM, callback_data="gsheets:confirm"
                ),
                InlineKeyboardButton(
                    text=ButtonText.CANCEL, callback_data="cancel"
                ),
            ],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Create cancel-only inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ButtonText.CANCEL, callback_data="cancel")],
        ]
    )
