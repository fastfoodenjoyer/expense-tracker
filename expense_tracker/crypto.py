"""Encryption utilities for sensitive data."""

import base64
import secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def generate_key() -> str:
    """Generate a new encryption key."""
    return Fernet.generate_key().decode()


def _derive_key(secret: str, salt: bytes = b"expense-tracker-salt") -> bytes:
    """Derive a Fernet key from a secret string."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return key


class Encryptor:
    """Encrypt and decrypt sensitive data."""

    def __init__(self, secret_key: str):
        """Initialize with a secret key.

        Args:
            secret_key: Secret key for encryption (from env var).
        """
        key = _derive_key(secret_key)
        self._fernet = Fernet(key)

    def encrypt(self, data: str) -> str:
        """Encrypt a string.

        Args:
            data: Plain text to encrypt.

        Returns:
            Base64-encoded encrypted data.
        """
        encrypted = self._fernet.encrypt(data.encode())
        return encrypted.decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a string.

        Args:
            encrypted_data: Base64-encoded encrypted data.

        Returns:
            Decrypted plain text.
        """
        decrypted = self._fernet.decrypt(encrypted_data.encode())
        return decrypted.decode()
