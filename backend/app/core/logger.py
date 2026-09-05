"""Structured console and file logging."""

import json
import logging
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname, "module": record.name, "message": record.getMessage(), "request_id": getattr(record, "request_id", "-")}, separators=(",", ":"))

def configure_logging(log_dir: Path, log_format: str = "text") -> None:
    """Configure non-secret console and file log handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter() if log_format == "json" else logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    for handler in (logging.StreamHandler(), RotatingFileHandler(log_dir / "bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")):
        handler.setFormatter(formatter)
        handler.addFilter(ContextFilter())
        root.addHandler(handler)
