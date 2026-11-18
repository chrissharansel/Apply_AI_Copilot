from cryptography.fernet import Fernet

from ..config import settings


def _f() -> Fernet | None:
    return Fernet(settings.encryption_key.encode()) if settings.encryption_key else None


def encrypt_bytes(data: bytes) -> bytes:
    f = _f()
    return f.encrypt(data) if f else data


def decrypt_bytes(data: bytes) -> bytes:
    f = _f()
    return f.decrypt(data) if f else data
