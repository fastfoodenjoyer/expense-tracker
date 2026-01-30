"""Parsers for bank statement PDFs."""

from .base import BaseParser
from .tbank import TBankParser
from .alfabank import AlfaBankParser
from .yandex import YandexBankParser
from .ozon import OzonBankParser

__all__ = [
    "BaseParser",
    "TBankParser",
    "AlfaBankParser",
    "YandexBankParser",
    "OzonBankParser",
]

# List of all available parsers for auto-detection
PARSERS = [
    TBankParser,
    AlfaBankParser,
    YandexBankParser,
    OzonBankParser,
]


def get_parser_for_file(file_path):
    """Find the appropriate parser for a given file.

    Args:
        file_path: Path to the statement file

    Returns:
        Parser instance if found, None otherwise
    """
    for parser_class in PARSERS:
        parser = parser_class()
        if parser.can_parse(file_path):
            return parser
    return None
