from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    host: str
    port: int
    db_path: Path
    access_secret: str
    refresh_secret: str
    access_ttl_minutes: int
    refresh_ttl_days: int
    session_inactivity_minutes: int
    cookie_secure: bool
    cookie_domain: str | None
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    smtp_from: str
    smtp_use_tls: bool
    ai_timeout_seconds: float
    max_upload_bytes: int
    cors_origins: list[str]


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _must_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    root = Path(__file__).resolve().parent.parent
    db_default = root / "data" / "ghost.db"

    access_secret = _must_env("JWT_ACCESS_SECRET")
    refresh_secret = _must_env("JWT_REFRESH_SECRET")

    smtp_host = _must_env("SMTP_HOST")
    smtp_user = _must_env("SMTP_USER")
    smtp_pass = _must_env("SMTP_PASS")
    smtp_from = _must_env("SMTP_FROM")

    raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

    return Settings(
        app_name="Ghost",
        app_env=os.getenv("APP_ENV", "production"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        db_path=Path(os.getenv("DB_PATH", str(db_default))),
        access_secret=access_secret,
        refresh_secret=refresh_secret,
        access_ttl_minutes=int(os.getenv("ACCESS_TTL_MINUTES", "15")),
        refresh_ttl_days=int(os.getenv("REFRESH_TTL_DAYS", "14")),
        session_inactivity_minutes=int(os.getenv("SESSION_INACTIVITY_MINUTES", "60")),
        cookie_secure=_to_bool(os.getenv("COOKIE_SECURE", "false")),
        cookie_domain=os.getenv("COOKIE_DOMAIN") or None,
        smtp_host=smtp_host,
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        smtp_from=smtp_from,
        smtp_use_tls=_to_bool(os.getenv("SMTP_USE_TLS", "true"), default=True),
        ai_timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "10")),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))),
        cors_origins=cors_origins or ["http://localhost:5173"],
    )
