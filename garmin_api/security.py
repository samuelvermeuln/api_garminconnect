"""Credential encryption and API key helpers."""

import hashlib
import secrets

from cryptography.fernet import Fernet


def build_cipher(encryption_key: str) -> Fernet:
    return Fernet(encryption_key.encode())


def encrypt_text(cipher: Fernet, value: str) -> str:
    return cipher.encrypt(value.encode()).decode()


def decrypt_text(cipher: Fernet, value: str) -> str:
    return cipher.decrypt(value.encode()).decode()


def create_api_key() -> str:
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(api_key: str, expected_hash: str) -> bool:
    return secrets.compare_digest(hash_api_key(api_key), expected_hash)
