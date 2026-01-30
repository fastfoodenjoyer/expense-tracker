"""Transaction categorization based on rules."""

import re
from dataclasses import dataclass

from expense_tracker.models import Category, Transaction


@dataclass
class CategoryRule:
    """Rule for categorizing transactions."""

    category: Category
    patterns: list[str]
    _compiled: re.Pattern | None = None

    @property
    def regex(self) -> re.Pattern:
        """Get compiled regex pattern."""
        if self._compiled is None:
            combined = "|".join(self.patterns)
            self._compiled = re.compile(combined, re.IGNORECASE)
        return self._compiled

    def matches(self, description: str) -> bool:
        """Check if description matches this rule."""
        return bool(self.regex.search(description))


# Default categorization rules
DEFAULT_RULES: list[CategoryRule] = [
    # Groceries - supermarkets and food stores
    CategoryRule(
        category=Category.GROCERIES,
        patterns=[
            r"DIXY",
            r"ДИКСИ",
            r"LENTA",
            r"ЛЕНТА",
            r"MAGNIT",
            r"МАГНИТ",
            r"PYATEROCHKA",
            r"ПЯТЕРОЧКА",
            r"PEREKRESTOK",
            r"PEREKRYOSTOK",
            r"ПЕРЕКРЕСТОК",
            r"ПЕРЕКРЁСТОК",
            r"VKUSVILL",
            r"ВКУСВИЛЛ",
            r"АШАН",
            r"AUCHAN",
            r"METRO\s*C",
            r"МЕТРО\s*К",
            r"OKEY",
            r"ОКЕЙ",
            r"SPAR",
            r"СПАР",
            r"BILLA",
            r"АЗБУКА\s*ВКУСА",
            r"AZBUKA\s*VKUSA",
            r"GLOBUS",
            r"ГЛОБУС",
            r"SAMOKAT",
            r"САМОКАТ",
            r"YANDEX\.?LAVKA",
            r"ЯНДЕКС\.?ЛАВКА",
            r"SBERMARKET",
            r"СБЕРМАРКЕТ",
        ],
    ),
    # Restaurants and cafes
    CategoryRule(
        category=Category.RESTAURANTS,
        patterns=[
            r"TOKYO\s*CITY",
            r"ТОКИО\s*СИТИ",
            r"SUBWAY",
            r"САБВЕЙ",
            r"ROSTIC",
            r"РОСТИК",
            r"KFC",
            r"КФС",
            r"CINNABON",
            r"СИННАБОН",
            r"BURGER\s*KING",
            r"БУРГЕР\s*КИНГ",
            r"MCDONALD",
            r"МАКДОНАЛДС",
            r"ВКУСНО\s*И\s*ТОЧКА",
            r"VKUSNOITOCHKA",
            r"STARBUCKS",
            r"СТАРБАКС",
            r"COFFEE",
            r"КОФЕ",
            r"CAFE",
            r"КАФЕ",
            r"РЕСТОРАН",
            r"RESTAURANT",
            r"СУШИ",
            r"SUSHI",
            r"PIZZA",
            r"ПИЦЦА",
            r"DODO",
            r"ДОДО",
            r"DOMINO",
            r"ДОМИНО",
            r"DELIVERY\s*CLUB",
            r"ДЕЛИВЕРИ\s*КЛАБ",
            r"YANDEX\.?EDA",
            r"ЯНДЕКС\.?ЕДА",
        ],
    ),
    # Transport
    CategoryRule(
        category=Category.TRANSPORT,
        patterns=[
            r"UBER",
            r"УБЕР",
            r"YANDEX\.?TAXI",
            r"ЯНДЕКС\.?ТАКСИ",
            r"CITYMOBIL",
            r"СИТИМОБИЛ",
            r"GETT",
            r"МЕТРО",
            r"METRO(?!\s*C)",  # Metro but not Metro Cash
            r"МОСМЕТРО",
            r"ТРОЙКА",
            r"TROIKA",
            r"РЖД",
            r"RZD",
            r"AEROFLOT",
            r"АЭРОФЛОТ",
            r"S7",
            r"POBEDA",
            r"ПОБЕДА",
            r"АЗС",
            r"ЛУКОЙЛ",
            r"LUKOIL",
            r"ГАЗПРОМ",
            r"GAZPROM",
            r"РОСНЕФТЬ",
            r"ROSNEFT",
            r"SHELL",
            r"BP\s",
            r"КАРШЕРИНГ",
            r"CARSHARING",
            r"ДЕЛИМОБИЛЬ",
            r"DELIMOBIL",
            r"ЯНДЕКС\.?ДРАЙВ",
            r"YANDEX\.?DRIVE",
        ],
    ),
    # Communication and internet
    CategoryRule(
        category=Category.COMMUNICATION,
        patterns=[
            r"BEELINE",
            r"БИЛАЙН",
            r"MTS\b",
            r"МТС\b",
            r"MEGAFON",
            r"МЕГАФОН",
            r"TELE2",
            r"ТЕЛЕ2",
            r"YOTA",
            r"ЙОТА",
            r"ROSTELECOM",
            r"РОСТЕЛЕКОМ",
            r"DOM\.?RU",
            r"ДОМ\.?РУ",
        ],
    ),
    # Entertainment
    CategoryRule(
        category=Category.ENTERTAINMENT,
        patterns=[
            r"CINEMA",
            r"КИНО",
            r"KINOPOISK",
            r"КИНОПОИСК",
            r"OKKO",
            r"ОККО",
            r"IVI\b",
            r"ИВИ\b",
            r"NETFLIX",
            r"SPOTIFY",
            r"APPLE\s*MUSIC",
            r"YANDEX\.?MUSIC",
            r"ЯНДЕКС\.?МУЗЫКА",
            r"YANDEX\.?PLUS",
            r"ЯНДЕКС\.?ПЛЮС",
            r"STEAM",
            r"PLAYSTATION",
            r"XBOX",
            r"NINTENDO",
            r"ТЕАТР",
            r"THEATER",
            r"КОНЦЕРТ",
            r"CONCERT",
            r"MUSEUM",
            r"МУЗЕЙ",
            r"ПАРК",
            r"PARK",
            r"WILDBERRIES",
            r"ВАЙЛДБЕРРИЗ",
            r"OZON",
            r"ОЗОН",
            r"ALIEXPRESS",
            r"АЛИЭКСПРЕСС",
        ],
    ),
    # Health
    CategoryRule(
        category=Category.HEALTH,
        patterns=[
            r"АПТЕКА",
            r"PHARMACY",
            r"APTEKA",
            r"GORZDRAV",
            r"ГОРЗДРАВ",
            r"RIGLA",
            r"РИГЛА",
            r"EAPTEKA",
            r"СТОЛИЧК",
            r"КЛИНИКА",
            r"CLINIC",
            r"МЕДЦЕНТР",
            r"ПОЛИКЛИНИКА",
            r"HOSPITAL",
            r"БОЛЬНИЦА",
            r"СТОМАТОЛОГ",
            r"DENTAL",
            r"OZON\.?PHARMA",
        ],
    ),
    # Clothing
    CategoryRule(
        category=Category.CLOTHING,
        patterns=[
            r"ZARA\b",
            r"ЗАРА\b",
            r"H&M",
            r"UNIQLO",
            r"ЮНИКЛО",
            r"BERSHKA",
            r"БЕРШКА",
            r"MASSIMO\s*DUTTI",
            r"PULL\s*&\s*BEAR",
            r"GLORIA\s*JEANS",
            r"ГЛОРИЯ\s*ДЖИНС",
            r"СПОРТМАСТЕР",
            r"SPORTMASTER",
            r"DECATHLON",
            r"ДЕКАТЛОН",
            r"ADIDAS",
            r"АДИДАС",
            r"NIKE\b",
            r"НАЙК",
            r"PUMA\b",
            r"ПУМА",
            r"RENDEZ-?VOUS",
            r"РАНДЕВУ",
            r"KARI\b",
            r"КАРИ\b",
        ],
    ),
    # Transfers
    CategoryRule(
        category=Category.TRANSFERS,
        patterns=[
            r"перевод",
            r"ПЕРЕВОД",
            r"transfer",
            r"TRANSFER",
            r"Внутрибанковский",
            r"Внутренний",
            r"Внешний",
            r"СБП",
            r"Система\s*быстрых\s*платежей",
        ],
    ),
    # Cashback
    CategoryRule(
        category=Category.CASHBACK,
        patterns=[
            r"кэшбэк",
            r"кешбек",
            r"cashback",
            r"CASHBACK",
            r"cash\s*back",
        ],
    ),
    # Cash withdrawal
    CategoryRule(
        category=Category.CASH,
        patterns=[
            r"снятие\s*наличных",
            r"банкомат",
            r"ATM",
            r"cash\s*withdrawal",
        ],
    ),
]


class Categorizer:
    """Transaction categorizer based on rules."""

    def __init__(self, rules: list[CategoryRule] | None = None):
        """Initialize categorizer with rules.

        Args:
            rules: List of category rules. Uses DEFAULT_RULES if not provided.
        """
        self.rules = rules if rules is not None else DEFAULT_RULES

    def categorize(self, transaction: Transaction) -> Category:
        """Determine category for a transaction.

        Args:
            transaction: Transaction to categorize

        Returns:
            Detected category or Category.OTHER
        """
        description = transaction.description

        for rule in self.rules:
            if rule.matches(description):
                return rule.category

        return Category.OTHER

    def categorize_all(self, transactions: list[Transaction]) -> list[Transaction]:
        """Categorize all transactions in a list.

        Args:
            transactions: List of transactions to categorize

        Returns:
            Same transactions with category field filled
        """
        for transaction in transactions:
            if transaction.category is None:
                transaction.category = self.categorize(transaction)
        return transactions
