"""Runtime configuration for the Garmin HTTP API."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    storage_path: Path
    encryption_key: str
    admin_key: str | None
    cache_ttl_seconds: int


def get_settings() -> Settings:
    storage_path = Path(os.getenv("GARMIN_API_STORAGE", "your_data/garmin_api"))
    database_path = Path(
        os.getenv("GARMIN_API_DATABASE", str(storage_path / "garmin_api.sqlite3"))
    )
    encryption_key = os.getenv("GARMIN_API_ENCRYPTION_KEY", "")
    if not encryption_key:
        raise RuntimeError(
            "GARMIN_API_ENCRYPTION_KEY is required. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )

    return Settings(
        database_path=database_path,
        storage_path=storage_path,
        encryption_key=encryption_key,
        admin_key=os.getenv("GARMIN_API_ADMIN_KEY"),
        cache_ttl_seconds=int(os.getenv("GARMIN_API_CACHE_TTL_SECONDS", "120")),
    )
