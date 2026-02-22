from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .db import db_cursor

MAX_LOGIN_ATTEMPTS = 6
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_BLOCK_SECONDS = 15 * 60


@dataclass
class User:
    id: int
    email: str
    password_hash: str


@dataclass
class Session:
    id: str
    user_id: int
    refresh_jti_hash: str
    last_active: int
    revoked: int


def now_ts() -> int:
    return int(time.time())


def create_user(db_path: Path, email: str, password_hash: str) -> User:
    with db_cursor(db_path) as cur:
        cur.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, password_hash, now_ts()),
        )
        user_id = cur.lastrowid
    return User(id=user_id, email=email, password_hash=password_hash)


def get_user_by_email(db_path: Path, email: str) -> User | None:
    with db_cursor(db_path) as cur:
        row = cur.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    if not row:
        return None
    return User(id=row["id"], email=row["email"], password_hash=row["password_hash"])


def get_user_by_id(db_path: Path, user_id: int) -> User | None:
    with db_cursor(db_path) as cur:
        row = cur.execute(
            "SELECT id, email, password_hash FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return User(id=row["id"], email=row["email"], password_hash=row["password_hash"])


def create_session(
    db_path: Path,
    session_id: str,
    user_id: int,
    refresh_jti_hash: str,
    ip_address: str,
    user_agent: str,
) -> None:
    now = now_ts()
    with db_cursor(db_path) as cur:
        cur.execute(
            """
            INSERT INTO sessions (id, user_id, refresh_jti_hash, created_at, last_active, revoked, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (session_id, user_id, refresh_jti_hash, now, now, ip_address, user_agent[:255]),
        )


def get_session(db_path: Path, session_id: str) -> Session | None:
    with db_cursor(db_path) as cur:
        row = cur.execute(
            "SELECT id, user_id, refresh_jti_hash, last_active, revoked FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    return Session(
        id=row["id"],
        user_id=row["user_id"],
        refresh_jti_hash=row["refresh_jti_hash"],
        last_active=row["last_active"],
        revoked=row["revoked"],
    )


def update_session_activity(db_path: Path, session_id: str) -> None:
    with db_cursor(db_path) as cur:
        cur.execute(
            "UPDATE sessions SET last_active = ? WHERE id = ?",
            (now_ts(), session_id),
        )


def rotate_refresh_jti(db_path: Path, session_id: str, refresh_jti_hash: str) -> None:
    with db_cursor(db_path) as cur:
        cur.execute(
            "UPDATE sessions SET refresh_jti_hash = ?, last_active = ? WHERE id = ? AND revoked = 0",
            (refresh_jti_hash, now_ts(), session_id),
        )


def revoke_session(db_path: Path, session_id: str) -> None:
    with db_cursor(db_path) as cur:
        cur.execute("UPDATE sessions SET revoked = 1 WHERE id = ?", (session_id,))


def revoke_all_user_sessions(db_path: Path, user_id: int) -> None:
    with db_cursor(db_path) as cur:
        cur.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))


def save_message(db_path: Path, user_id: int, session_id: str, role: str, content: str) -> None:
    with db_cursor(db_path) as cur:
        cur.execute(
            "INSERT INTO messages (user_id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, session_id, role, content[:4000], now_ts()),
        )


def get_last_user_message(db_path: Path, user_id: int) -> str:
    with db_cursor(db_path) as cur:
        row = cur.execute(
            "SELECT content FROM messages WHERE user_id = ? AND role = 'user' ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return row["content"] if row else ""


def is_login_blocked(db_path: Path, key: str) -> tuple[bool, int]:
    now = now_ts()
    with db_cursor(db_path) as cur:
        row = cur.execute(
            "SELECT count, first_attempt, blocked_until FROM login_attempts WHERE key = ?",
            (key,),
        ).fetchone()
        if not row:
            return False, 0

        if row["blocked_until"] > now:
            return True, row["blocked_until"] - now

        if now - row["first_attempt"] > LOGIN_WINDOW_SECONDS:
            cur.execute("DELETE FROM login_attempts WHERE key = ?", (key,))
            return False, 0

    return False, 0


def register_failed_login(db_path: Path, key: str) -> int:
    now = now_ts()
    with db_cursor(db_path) as cur:
        row = cur.execute(
            "SELECT count, first_attempt, blocked_until FROM login_attempts WHERE key = ?",
            (key,),
        ).fetchone()

        if not row:
            cur.execute(
                "INSERT INTO login_attempts (key, count, first_attempt, blocked_until) VALUES (?, 1, ?, 0)",
                (key, now),
            )
            return 0

        count = row["count"]
        first_attempt = row["first_attempt"]
        blocked_until = row["blocked_until"]

        if blocked_until > now:
            return blocked_until - now

        if now - first_attempt > LOGIN_WINDOW_SECONDS:
            count = 1
            first_attempt = now
        else:
            count += 1

        if count >= MAX_LOGIN_ATTEMPTS:
            blocked_until = now + LOGIN_BLOCK_SECONDS

        cur.execute(
            "UPDATE login_attempts SET count = ?, first_attempt = ?, blocked_until = ? WHERE key = ?",
            (count, first_attempt, blocked_until, key),
        )

        return max(0, blocked_until - now)


def clear_login_attempts(db_path: Path, key: str) -> None:
    with db_cursor(db_path) as cur:
        cur.execute("DELETE FROM login_attempts WHERE key = ?", (key,))


def save_routing_log(
    db_path: Path,
    user_id: int | None,
    session_id: str | None,
    intent: str,
    model_tier: str,
    message_length: int,
    decision_ms: float,
    response_ms: float,
    fallback_used: bool,
    downgraded: bool,
    reason: str | None,
) -> None:
    with db_cursor(db_path) as cur:
        cur.execute(
            """
            INSERT INTO routing_logs (
                user_id, session_id, intent, model_tier, message_length, decision_ms, response_ms,
                fallback_used, downgraded, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                session_id,
                intent,
                model_tier,
                message_length,
                decision_ms,
                response_ms,
                1 if fallback_used else 0,
                1 if downgraded else 0,
                reason,
                now_ts(),
            ),
        )
