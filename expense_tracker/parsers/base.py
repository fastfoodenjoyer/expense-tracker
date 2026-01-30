"""Base parser interface for bank statements."""

from abc import ABC, abstractmethod
from pathlib import Path

from expense_tracker.models import Statement


class BaseParser(ABC):
    """Abstract base class for bank statement parsers."""

    @abstractmethod
    def parse(self, file_path: Path) -> Statement:
        """Parse a bank statement file and return a Statement object.

        Args:
            file_path: Path to the statement file (PDF, CSV, etc.)

        Returns:
            Statement object with parsed transactions
        """
        pass

    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the statement file

        Returns:
            True if this parser can handle the file
        """
        pass
