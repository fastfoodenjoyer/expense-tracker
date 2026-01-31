"""Report handlers: summary, top expenses, transactions list."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from expense_tracker.bot.keyboards import (
    period_selection_keyboard,
    top_count_keyboard,
    category_filter_keyboard,
    pagination_keyboard,
    main_menu_keyboard,
    ButtonText,
)
from expense_tracker.bot.states import (
    SummaryStates,
    TopExpensesStates,
    TransactionsStates,
)
from expense_tracker.models import Category
from expense_tracker.storage import Storage

router = Router()

TRANSACTIONS_PER_PAGE = 20


def get_period_dates(period: str) -> tuple[Optional[datetime], Optional[datetime]]:
    """Get date range for a period.

    Args:
        period: Period identifier (current_month, last_month, all_time).

    Returns:
        Tuple of (from_date, to_date).
    """
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


def format_period_name(period: str) -> str:
    """Format period name for display."""
    now = datetime.now()
    months = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
    ]

    if period == "current_month":
        return f"{months[now.month - 1]} {now.year}"
    elif period == "last_month":
        if now.month == 1:
            return f"{months[11]} {now.year - 1}"
        return f"{months[now.month - 2]} {now.year}"
    return "всё время"


# ============ Summary handlers ============


@router.message(F.text == ButtonText.SUMMARY)
async def start_summary(message: Message, state: FSMContext) -> None:
    """Start summary report flow."""
    await state.set_state(SummaryStates.waiting_for_period)
    await message.answer(
        "За какой период?",
        reply_markup=period_selection_keyboard("summary"),
    )


@router.callback_query(F.data.startswith("summary:"))
async def show_summary(callback: CallbackQuery, state: FSMContext) -> None:
    """Show summary report for selected period."""
    period = callback.data.split(":")[1]
    from_dt, to_dt = get_period_dates(period)
    period_name = format_period_name(period)

    storage = Storage()
    summary = storage.get_summary(
        date_from=from_dt,
        date_to=to_dt,
        include_internal_transfers=False,
    )
    income, expense = storage.get_totals(
        date_from=from_dt,
        date_to=to_dt,
        include_internal_transfers=False,
    )

    if not summary:
        await callback.message.edit_text(
            f"📊 Расходы по категориям ({period_name})\n\n"
            "Нет данных за этот период."
        )
        await state.clear()
        await callback.answer()
        return

    total = sum(summary.values())

    # Format summary
    lines = [f"📊 Расходы по категориям ({period_name})\n"]

    sorted_summary = sorted(summary.items(), key=lambda x: x[1], reverse=True)
    for category, amount in sorted_summary:
        percentage = (amount / total * 100) if total > 0 else Decimal("0")
        lines.append(f"{category}: {amount:,.0f} ₽ ({percentage:.0f}%)")

    lines.append("─" * 25)
    lines.append(f"Всего: {total:,.0f} ₽")
    lines.append("")
    lines.append(f"💰 Пополнения: +{income:,.0f} ₽")
    lines.append(f"💸 Расходы: -{expense:,.0f} ₽")

    balance = income - expense
    balance_emoji = "📈" if balance >= 0 else "📉"
    lines.append(f"{balance_emoji} Баланс: {balance:+,.0f} ₽")

    await callback.message.edit_text("\n".join(lines))
    await state.clear()
    await callback.answer()


# ============ Top expenses handlers ============


@router.message(F.text == ButtonText.TOP_EXPENSES)
async def start_top(message: Message, state: FSMContext) -> None:
    """Start top expenses flow."""
    await state.set_state(TopExpensesStates.waiting_for_count)
    await message.answer(
        "Сколько показать?",
        reply_markup=top_count_keyboard(),
    )


@router.callback_query(F.data.startswith("top:"))
async def show_top(callback: CallbackQuery, state: FSMContext) -> None:
    """Show top expenses."""
    limit = int(callback.data.split(":")[1])

    storage = Storage()
    transactions = storage.get_top_expenses(
        limit=limit,
        include_internal_transfers=False,
    )

    if not transactions:
        await callback.message.edit_text(
            f"🔝 Топ {limit} расходов\n\n"
            "Нет данных."
        )
        await state.clear()
        await callback.answer()
        return

    # Format transactions
    lines = [f"🔝 Топ {limit} расходов\n"]

    for i, t in enumerate(transactions, 1):
        date_str = t.date.strftime("%d.%m")
        # Truncate description
        desc = t.description[:25] + "..." if len(t.description) > 25 else t.description
        lines.append(f"{i}. {date_str} {desc} {t.amount:,.0f} ₽")

    await callback.message.edit_text("\n".join(lines))
    await state.clear()
    await callback.answer()


# ============ Transactions list handlers ============


@router.message(F.text == ButtonText.TRANSACTIONS)
async def start_transactions(message: Message, state: FSMContext) -> None:
    """Start transactions list flow."""
    await state.set_state(TransactionsStates.waiting_for_category)
    await message.answer(
        "Фильтр по категории?",
        reply_markup=category_filter_keyboard("txn_cat"),
    )


@router.callback_query(F.data.startswith("txn_cat:"))
async def select_category(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle category selection for transactions."""
    cat_key = callback.data.split(":")[1]

    category = None
    if cat_key != "all":
        try:
            category = Category[cat_key]
        except KeyError:
            await callback.answer("Неизвестная категория", show_alert=True)
            return

    await state.update_data(category=cat_key, page=0)
    await show_transactions_page(callback, state)


async def show_transactions_page(callback: CallbackQuery, state: FSMContext) -> None:
    """Show transactions page."""
    data = await state.get_data()
    cat_key = data.get("category", "all")
    page = data.get("page", 0)

    category = None
    cat_name = "Все категории"
    if cat_key != "all":
        try:
            category = Category[cat_key]
            cat_name = category.value
        except KeyError:
            pass

    storage = Storage()
    all_transactions = storage.get_transactions(
        category=category,
        include_internal_transfers=False,
    )

    total_count = len(all_transactions)
    total_pages = (total_count + TRANSACTIONS_PER_PAGE - 1) // TRANSACTIONS_PER_PAGE

    if total_count == 0:
        await callback.message.edit_text(
            f"📋 Транзакции ({cat_name})\n\n"
            "Нет транзакций."
        )
        await state.clear()
        await callback.answer()
        return

    # Get page
    start = page * TRANSACTIONS_PER_PAGE
    end = start + TRANSACTIONS_PER_PAGE
    transactions = all_transactions[start:end]

    # Format transactions
    lines = [f"📋 Транзакции ({cat_name})\n"]

    for t in transactions:
        date_str = t.date.strftime("%d.%m")
        desc = t.description[:20] + "..." if len(t.description) > 20 else t.description
        amount_str = f"{t.amount:+,.0f} ₽"
        lines.append(f"{date_str} {desc} {amount_str} {t.bank}")

    lines.append("")
    lines.append(f"Показано {start + 1}-{min(end, total_count)} из {total_count}")

    await state.set_state(TransactionsStates.viewing_transactions)

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=pagination_keyboard(page, total_pages, "txn_page"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("txn_page:"))
async def change_page(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle pagination."""
    page = int(callback.data.split(":")[1])
    await state.update_data(page=page)
    await show_transactions_page(callback, state)
