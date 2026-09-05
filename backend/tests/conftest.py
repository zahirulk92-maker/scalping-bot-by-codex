"""Disable external feed startup for deterministic unit and API tests."""

import os

os.environ.setdefault("MARKET_DATA_ENABLED", "false")
os.environ.setdefault("INDICATOR_WARMUP_ENABLED", "false")
