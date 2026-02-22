from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def _open_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def ensure_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        conn = _open_connection(db_path)
        try:
            check = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        finally:
            conn.close()
        if check.lower() != "ok":
            backup_path = db_path.with_suffix(f".corrupt-{int(time.time())}.db")
            db_path.rename(backup_path)

    conn = _open_connection(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                refresh_jti_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_active INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS login_attempts (
                key TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                first_attempt INTEGER NOT NULL,
                blocked_until INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS routing_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                session_id TEXT,
                intent TEXT NOT NULL,
                model_tier TEXT NOT NULL,
                message_length INTEGER NOT NULL,
                decision_ms REAL NOT NULL,
                response_ms REAL NOT NULL,
                fallback_used INTEGER NOT NULL DEFAULT 0,
                downgraded INTEGER NOT NULL DEFAULT 0,
                reason TEXT,
                created_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_messages_user_created ON messages(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_routing_logs_created ON routing_logs(created_at);
            """
        )
    finally:
        conn.close()


@contextmanager
def db_cursor(db_path: Path):
    conn = _open_connection(db_path)
    try:
        cur = conn.cursor()
        yield cur
    finally:
        conn.commit()
        conn.close()
