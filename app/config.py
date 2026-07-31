"""Environment-based application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _csv_setting(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        item.strip() for item in os.getenv(name, default).split(",") if item.strip()
    )


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENVIRONMENT", "production")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    model_path: Path = Path(os.getenv("MODEL_PATH", str(ROOT / "model" / "model.json")))
    max_request_bytes: int = int(os.getenv("MAX_REQUEST_BYTES", str(128 * 1024 * 1024)))
    max_json_samples: int = int(os.getenv("MAX_JSON_SAMPLES", "1000000"))
    max_csv_samples: int = int(os.getenv("MAX_CSV_SAMPLES", "1000000"))
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    cors_origins: tuple[str, ...] = _csv_setting("CORS_ORIGINS", "*")
    allowed_hosts: tuple[str, ...] = _csv_setting("ALLOWED_HOSTS", "*")


settings = Settings()
