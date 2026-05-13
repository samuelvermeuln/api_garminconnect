"""SQLite storage for Garmin API accounts."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Account:
    id: str
    label: str | None
    email_encrypted: str
    password_encrypted: str
    api_key_hash: str
    is_cn: bool


class AccountStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    label TEXT,
                    email_encrypted TEXT NOT NULL,
                    password_encrypted TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL,
                    is_cn INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_accounts_api_key_hash
                ON accounts(api_key_hash)
                """
            )

    def create_account(
        self,
        *,
        account_id: str,
        label: str | None,
        email_encrypted: str,
        password_encrypted: str,
        api_key_hash: str,
        is_cn: bool,
    ) -> Account:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts (
                    id, label, email_encrypted, password_encrypted,
                    api_key_hash, is_cn
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    label,
                    email_encrypted,
                    password_encrypted,
                    api_key_hash,
                    int(is_cn),
                ),
            )
        account = self.get_account(account_id)
        if account is None:
            raise RuntimeError("account was not created")
        return account

    def update_credentials(
        self,
        *,
        account_id: str,
        email_encrypted: str,
        password_encrypted: str,
        is_cn: bool,
        label: str | None,
    ) -> Account:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE accounts
                SET email_encrypted = ?,
                    password_encrypted = ?,
                    is_cn = ?,
                    label = COALESCE(?, label),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    email_encrypted,
                    password_encrypted,
                    int(is_cn),
                    label,
                    account_id,
                ),
            )
        account = self.get_account(account_id)
        if account is None:
            raise KeyError(account_id)
        return account

    def get_account(self, account_id: str) -> Account | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, label, email_encrypted, password_encrypted,
                       api_key_hash, is_cn
                FROM accounts
                WHERE id = ?
                """,
                (account_id,),
            ).fetchone()
        return self._row_to_account(row) if row else None

    def get_account_by_api_key_hash(self, api_key_hash: str) -> Account | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, label, email_encrypted, password_encrypted,
                       api_key_hash, is_cn
                FROM accounts
                WHERE api_key_hash = ?
                """,
                (api_key_hash,),
            ).fetchone()
        return self._row_to_account(row) if row else None

    def delete_account(self, account_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    @staticmethod
    def _row_to_account(row: sqlite3.Row) -> Account:
        return Account(
            id=row["id"],
            label=row["label"],
            email_encrypted=row["email_encrypted"],
            password_encrypted=row["password_encrypted"],
            api_key_hash=row["api_key_hash"],
            is_cn=bool(row["is_cn"]),
        )
