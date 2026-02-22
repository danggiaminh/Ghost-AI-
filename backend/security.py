from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

import bcrypt
import jwt

from .config import Settings


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    session_id: str
    refresh_jti: str


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def now_ts() -> int:
    return int(time.time())


def _encode(payload: dict, secret: str) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


def _decode(token: str, secret: str, expected_type: str) -> dict:
    try:
        data = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid token") from exc
    if data.get("type") != expected_type:
        raise AuthError("Unexpected token type")
    return data


def build_tokens(settings: Settings, user_id: int, session_id: str | None = None) -> TokenBundle:
    now = now_ts()
    sid = session_id or secrets.token_urlsafe(24)
    refresh_jti = secrets.token_urlsafe(18)

    access_payload = {
        "sub": str(user_id),
        "sid": sid,
        "type": "access",
        "iat": now,
        "exp": now + settings.access_ttl_minutes * 60,
    }
    refresh_payload = {
        "sub": str(user_id),
        "sid": sid,
        "jti": refresh_jti,
        "type": "refresh",
        "iat": now,
        "exp": now + settings.refresh_ttl_days * 86400,
    }

    return TokenBundle(
        access_token=_encode(access_payload, settings.access_secret),
        refresh_token=_encode(refresh_payload, settings.refresh_secret),
        session_id=sid,
        refresh_jti=refresh_jti,
    )


def decode_access_token(settings: Settings, token: str) -> dict:
    return _decode(token, settings.access_secret, "access")


def decode_refresh_token(settings: Settings, token: str) -> dict:
    return _decode(token, settings.refresh_secret, "refresh")


def hash_refresh_jti(jti: str) -> str:
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def anonymize_identifier(raw: str | None) -> str:
    if not raw:
        return "unknown"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:14]
