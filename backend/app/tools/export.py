"""Explicit JSON/CSV export for durable PAPER operational records."""

import argparse
import csv
import json
from io import StringIO
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.db.database import Database

TABLES = {"paper-trades": "paper_trades", "daily-metrics": "daily_metrics", "alerts": "alerts"}


def render_records(rows: list[dict[str, object]], fmt: str) -> tuple[str, str]:
    """Render safe operational data for a download without exposing SQL details."""
    if fmt == "json":
        return json.dumps(rows, indent=2, default=str), "application/json"
    fields = sorted({key for row in rows for key in row}) or ["empty"]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, default=str) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    return buffer.getvalue(), "text/csv"


def export_records(kind: str, fmt: str, database: Database) -> Path:
    table = TABLES[kind]
    output_dir = database.path.parent / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "json" if fmt == "json" else "csv"
    target = output_dir / f"{kind}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.{suffix}"
    with database.connection() as connection:
        rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
    contents, _ = render_records(rows, fmt)
    target.write_text(contents, encoding="utf-8", newline="" if fmt == "csv" else None)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=TABLES)
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    args = parser.parse_args()
    print(export_records(args.kind, args.format, Database(get_settings())))
