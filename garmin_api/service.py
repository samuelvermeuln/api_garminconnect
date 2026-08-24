"""Garmin account orchestration for the HTTP API."""

import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from .security import create_api_key, decrypt_text, encrypt_text, hash_api_key
from .store import Account, AccountStore


class GarminApiError(Exception):
    status_code = 500


class GarminApiAuthError(GarminApiError):
    status_code = 401


class GarminApiRateLimitError(GarminApiError):
    status_code = 429


class GarminApiConnectionError(GarminApiError):
    status_code = 502


class GarminAccountService:
    def __init__(
        self,
        *,
        store: AccountStore,
        cipher: Fernet,
        storage_path: Path,
        cache_ttl_seconds: int,
    ) -> None:
        self.store = store
        self.cipher = cipher
        self.storage_path = storage_path
        self.cache_ttl_seconds = cache_ttl_seconds
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._pending_mfa: dict[str, Garmin] = {}
        self._cache: dict[tuple[Any, ...], tuple[float, Any]] = {}

    def create_account(
        self, *, email: str, password: str, label: str | None, is_cn: bool
    ) -> tuple[Account, str, bool]:
        account_id = uuid.uuid4().hex
        api_key = create_api_key()
        account = self.store.create_account(
            account_id=account_id,
            label=label,
            email_encrypted=encrypt_text(self.cipher, email),
            password_encrypted=encrypt_text(self.cipher, password),
            api_key_hash=hash_api_key(api_key),
            is_cn=is_cn,
        )
        try:
            mfa_required = self.login_account(account, return_on_mfa=True)
        except Exception:
            self.store.delete_account(account.id)
            raise
        return account, api_key, mfa_required

    def authenticate_account(self, api_key: str) -> Account:
        account = self.store.get_account_by_api_key_hash(hash_api_key(api_key))
        if account is None:
            raise GarminApiAuthError("invalid API key")
        return account

    def complete_mfa(self, account: Account, mfa_code: str) -> None:
        garmin = self._pending_mfa.get(account.id)
        if garmin is None:
            raise GarminApiAuthError("no pending MFA login for this account")
        try:
            garmin.resume_login({}, mfa_code)
            garmin.client.dump(str(self._token_dir(account.id)))
            self._pending_mfa.pop(account.id, None)
        except GarminConnectAuthenticationError as err:
            raise GarminApiAuthError(str(err)) from err
        except GarminConnectTooManyRequestsError as err:
            raise GarminApiRateLimitError(str(err)) from err
        except GarminConnectConnectionError as err:
            raise GarminApiConnectionError(str(err)) from err

    def login_account(self, account: Account, *, return_on_mfa: bool = False) -> bool:
        garmin = self._build_garmin(account, return_on_mfa=return_on_mfa)
        try:
            mfa_status, _ = garmin.login(str(self._token_dir(account.id)))
            if mfa_status == "needs_mfa":
                self._pending_mfa[account.id] = garmin
                return True
            return False
        except GarminConnectAuthenticationError as err:
            raise GarminApiAuthError(str(err)) from err
        except GarminConnectTooManyRequestsError as err:
            raise GarminApiRateLimitError(str(err)) from err
        except GarminConnectConnectionError as err:
            raise GarminApiConnectionError(str(err)) from err

    def revalidate_account(self, account: Account) -> bool:
        return self.login_account(account, return_on_mfa=True)

    def get_garmin(self, account: Account) -> Garmin:
        garmin = self._build_garmin(account, return_on_mfa=False)
        try:
            garmin.login(str(self._token_dir(account.id)))
            return garmin
        except GarminConnectAuthenticationError as err:
            raise GarminApiAuthError(str(err)) from err
        except GarminConnectTooManyRequestsError as err:
            raise GarminApiRateLimitError(str(err)) from err
        except GarminConnectConnectionError as err:
            raise GarminApiConnectionError(str(err)) from err

    def cached_call(self, account: Account, cache_key: tuple[Any, ...], fn: Any) -> Any:
        key = (account.id, *cache_key)
        cached = self._cache.get(key)
        now = time.time()
        if cached and now - cached[0] <= self.cache_ttl_seconds:
            return cached[1], True
        try:
            data = fn()
        except GarminConnectAuthenticationError as err:
            raise GarminApiAuthError(str(err)) from err
        except GarminConnectTooManyRequestsError as err:
            raise GarminApiRateLimitError(str(err)) from err
        except GarminConnectConnectionError as err:
            raise GarminApiConnectionError(str(err)) from err
        self._cache[key] = (now, data)
        return data, False

    def _build_garmin(self, account: Account, *, return_on_mfa: bool) -> Garmin:
        return Garmin(
            email=decrypt_text(self.cipher, account.email_encrypted),
            password=decrypt_text(self.cipher, account.password_encrypted),
            is_cn=account.is_cn,
            return_on_mfa=return_on_mfa,
        )

    def _token_dir(self, account_id: str) -> Path:
        token_dir = self.storage_path / "tokens" / account_id
        token_dir.mkdir(parents=True, exist_ok=True)
        return token_dir
