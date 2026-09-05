"""Create a consistent timestamped SQLite backup using SQLite's backup API."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.db.database import Database


def create_backup(database: Database, retention_count: int) -> Path:
    database.initialize()
    backup_dir = database.path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{database.path.stem}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.db"
    source = sqlite3.connect(database.path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
        result = destination.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError("backup integrity validation failed")
    finally:
        destination.close()
        source.close()
    backups = sorted(backup_dir.glob(f"{database.path.stem}_*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    for obsolete in backups[retention_count:]:
        obsolete.unlink()
    return target


if __name__ == "__main__":
    settings = get_settings()
    print(create_backup(Database(settings), settings.backup_retention_count))
