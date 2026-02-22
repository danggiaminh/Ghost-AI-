from __future__ import annotations

from .config import load_settings
from .db import ensure_database


def main() -> None:
    settings = load_settings()
    ensure_database(settings.db_path)
    print(f"Database ready at {settings.db_path}")


if __name__ == "__main__":
    main()
