"""Validated application configuration."""

from functools import lru_cache
from pathlib import Path
import json
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    trading_mode: str = "paper"
    starting_balance: Annotated[float, Field(gt=0)] = 100.0
    symbols: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    default_timeframe: str = "1m"
    risk_per_trade: Annotated[float, Field(gt=0, le=1)] = 0.005
    max_daily_loss: Annotated[float, Field(gt=0, le=1)] = 0.03
    max_open_positions: Annotated[int, Field(gt=0)] = 1
    backend_host: str = "127.0.0.1"
    backend_port: Annotated[int, Field(gt=0, le=65535)] = 8000
    frontend_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    market_exchange: str = "binance"
    market_stale_after_seconds: Annotated[int, Field(gt=0, le=300)] = 10
    market_history_limit: Annotated[int, Field(gt=0, le=500)] = 500
    market_reconnect_max_seconds: Annotated[int, Field(gt=1, le=300)] = 30
    market_data_enabled: bool = True
    indicator_warmup_enabled: bool = True
    ema_fast_period: Annotated[int, Field(gt=0)] = 9
    ema_slow_period: Annotated[int, Field(gt=0)] = 21
    rsi_period: Annotated[int, Field(gt=0)] = 14
    atr_period: Annotated[int, Field(gt=0)] = 14
    volume_ma_period: Annotated[int, Field(gt=0)] = 20
    signal_min_score: Annotated[int, Field(ge=0, le=100)] = 70
    rsi_long_min: Annotated[float, Field(ge=0, le=100)] = 52
    rsi_long_max: Annotated[float, Field(ge=0, le=100)] = 68
    rsi_short_min: Annotated[float, Field(ge=0, le=100)] = 32
    rsi_short_max: Annotated[float, Field(ge=0, le=100)] = 48
    min_vwap_distance_bps: Annotated[float, Field(ge=0)] = 3
    min_ema_separation_bps: Annotated[float, Field(ge=0)] = 2
    min_volume_ratio: Annotated[float, Field(gt=0)] = 1.0
    min_atr_bps: Annotated[float, Field(ge=0)] = 5
    max_atr_bps: Annotated[float, Field(gt=0)] = 150
    atr_stop_multiplier: Annotated[float, Field(gt=0)] = 1.5
    target_rr: Annotated[float, Field(gt=0)] = 1.5
    min_rr: Annotated[float, Field(gt=0)] = 1.5
    min_stop_distance_bps: Annotated[float, Field(gt=0)] = 5
    max_stop_distance_bps: Annotated[float, Field(gt=0)] = 100
    max_position_notional_multiplier: Annotated[float, Field(gt=0)] = 1.0
    max_signal_age_seconds: Annotated[int, Field(gt=0)] = 90
    estimated_fee_bps: Annotated[float, Field(ge=0)] = 10
    estimated_slippage_bps: Annotated[float, Field(ge=0)] = 2
    execution_mode: str = "paper"
    paper_fee_bps: Annotated[float, Field(ge=0)] = 10
    paper_entry_slippage_bps: Annotated[float, Field(ge=0)] = 2
    paper_exit_slippage_bps: Annotated[float, Field(ge=0)] = 2
    max_paper_trade_history: Annotated[int, Field(gt=0, le=10_000)] = 1000
    backtest_starting_balance: Annotated[float, Field(gt=0)] = 100.0
    max_backtest_days: Annotated[int, Field(gt=0, le=365)] = 90
    max_backtest_runs: Annotated[int, Field(gt=0, le=100)] = 20
    max_optimization_combinations: Annotated[int, Field(gt=0, le=500)] = 500
    max_optimization_runs: Annotated[int, Field(gt=0, le=50)] = 10
    min_evaluation_trades: Annotated[int, Field(gt=0)] = 30
    max_acceptable_drawdown_percent: Annotated[float, Field(gt=0, le=100)] = 20
    min_acceptable_profit_factor: Annotated[float, Field(gt=0)] = 1.0
    database_url: str = "sqlite:///./data/scalping_bot.db"
    strategy_profile: str = "baseline"
    research_candidate_parameters_json: str = ""
    alert_cooldown_seconds: Annotated[int, Field(gt=0, le=86_400)] = 300
    recovery_history_limit: Annotated[int, Field(gt=0, le=2_000)] = 1_440
    app_env: str = "development"
    log_format: str = "text"
    app_version: str = "0.11.0"
    build_commit: str = ""
    build_timestamp: str = ""
    max_concurrent_backtests: Annotated[int, Field(gt=0, le=4)] = 1
    max_concurrent_optimizations: Annotated[int, Field(gt=0, le=2)] = 1
    heavy_request_limit_per_minute: Annotated[int, Field(gt=0, le=60)] = 6
    backup_retention_count: Annotated[int, Field(gt=0, le=100)] = 10
    alert_retention_days: Annotated[int, Field(gt=0, le=3650)] = 90
    max_request_body_bytes: Annotated[int, Field(gt=1024, le=5_000_000)] = 250_000
    min_forward_trades: Annotated[int, Field(gt=0, le=10_000)] = 30
    min_forward_days: Annotated[int, Field(gt=0, le=3650)] = 7
    preferred_forward_trades: Annotated[int, Field(gt=0, le=100_000)] = 100
    preferred_forward_days: Annotated[int, Field(gt=0, le=3650)] = 30
    min_forward_expectancy_r: Annotated[float, Field(ge=0, le=10)] = 0.05
    min_forward_profit_factor: Annotated[float, Field(gt=0, le=100)] = 1.10
    max_forward_drawdown_percent: Annotated[float, Field(gt=0, le=100)] = 5.0
    max_daily_lock_events: Annotated[int, Field(ge=0, le=3650)] = 2
    max_consecutive_losses: Annotated[int, Field(gt=0, le=10_000)] = 8
    min_expectancy_retention: Annotated[float, Field(ge=0, le=10)] = 0.50
    min_profit_factor_retention: Annotated[float, Field(ge=0, le=10)] = 0.50
    min_trade_frequency_retention: Annotated[float, Field(gt=0, le=1)] = 0.50
    max_trade_frequency_multiple: Annotated[float, Field(ge=1, le=100)] = 2.0
    min_healthy_symbols: Annotated[int, Field(gt=0, le=100)] = 2
    min_forward_trades_per_symbol: Annotated[int, Field(gt=0, le=10_000)] = 5
    validation_short_window_days: Annotated[int, Field(gt=0, le=365)] = 7
    validation_long_window_days: Annotated[int, Field(gt=0, le=3650)] = 30
    max_underwater_days: Annotated[int, Field(gt=0, le=3650)] = 14
    max_forward_cost_ratio: Annotated[float, Field(gt=0, le=10)] = 0.50
    pause_paper_on_validation_fail: bool = True
    exchange_api_key: str = ""
    exchange_api_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        enable_decoding=False,
        extra="ignore",
    )

    @field_validator("trading_mode")
    @classmethod
    def validate_trading_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "paper":
            raise ValueError("only trading mode 'paper' is supported in Phase 1")
        return normalized

    @field_validator("execution_mode")
    @classmethod
    def validate_execution_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "paper":
            raise ValueError("only execution mode 'paper' is supported in Phase 6")
        return normalized

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"development", "test", "paper-production"}:
            raise ValueError("app_env must be development, test, or paper-production")
        return normalized

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"text", "json"}:
            raise ValueError("log_format must be text or json")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not (value.startswith("sqlite:///") or value.startswith("postgresql")):
            raise ValueError("database_url must be sqlite:/// or postgresql")
        return value

    @field_validator("strategy_profile")
    @classmethod
    def validate_strategy_profile(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"baseline", "research_candidate"}:
            raise ValueError("strategy_profile must be 'baseline' or 'research_candidate'")
        return normalized

    @field_validator("research_candidate_parameters_json")
    @classmethod
    def validate_research_parameters(cls, value: str, info: object) -> str:
        profile = getattr(info, "data", {}).get("strategy_profile", "baseline")
        if profile == "research_candidate":
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as error:
                raise ValueError("research_candidate_parameters_json must be a JSON object") from error
            if not isinstance(parsed, dict) or not parsed:
                raise ValueError("research_candidate_parameters_json is required for research_candidate profile")
        return value

    def effective_strategy_settings(self) -> "Settings":
        """Apply an explicitly configured research profile through full validation."""
        if self.strategy_profile == "baseline":
            return self
        allowed = {"EMA_FAST_PERIOD": "ema_fast_period", "EMA_SLOW_PERIOD": "ema_slow_period", "RSI_LONG_MIN": "rsi_long_min", "RSI_LONG_MAX": "rsi_long_max", "RSI_SHORT_MIN": "rsi_short_min", "RSI_SHORT_MAX": "rsi_short_max", "SIGNAL_MIN_SCORE": "signal_min_score", "MIN_VWAP_DISTANCE_BPS": "min_vwap_distance_bps", "MIN_EMA_SEPARATION_BPS": "min_ema_separation_bps", "MIN_VOLUME_RATIO": "min_volume_ratio", "MIN_ATR_BPS": "min_atr_bps", "MAX_ATR_BPS": "max_atr_bps", "ATR_STOP_MULTIPLIER": "atr_stop_multiplier", "TARGET_RR": "target_rr"}
        parameters = json.loads(self.research_candidate_parameters_json)
        if any(name.upper() not in allowed for name in parameters):
            raise ValueError("research candidate includes a non-optimizable parameter")
        values = self.model_dump()
        values.update({allowed[name.upper()]: value for name, value in parameters.items()})
        return Settings(**values)

    @model_validator(mode="after")
    def enforce_paper_only_invariant(self) -> "Settings":
        if self.trading_mode != "paper" or self.execution_mode != "paper":
            raise ValueError("this application supports paper-only trading and paper-only execution")
        return self

    @model_validator(mode="after")
    def validate_validation_windows(self) -> "Settings":
        if self.preferred_forward_trades < self.min_forward_trades:
            raise ValueError("preferred_forward_trades must be at least min_forward_trades")
        if self.preferred_forward_days < self.min_forward_days:
            raise ValueError("preferred_forward_days must be at least min_forward_days")
        if self.validation_long_window_days < self.validation_short_window_days:
            raise ValueError("validation_long_window_days must be at least validation_short_window_days")
        if self.min_healthy_symbols > len(self.symbols):
            raise ValueError("min_healthy_symbols cannot exceed configured symbols")
        return self

    @field_validator("symbols", mode="before")
    @classmethod
    def parse_symbols(cls, value: object) -> list[str]:
        if isinstance(value, str):
            value = [item.strip().upper() for item in value.split(",") if item.strip()]
        if not isinstance(value, list) or not value:
            raise ValueError("symbols must contain at least one symbol")
        if any(not isinstance(item, str) or not item for item in value):
            raise ValueError("symbols must contain non-empty names")
        return value

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_frontend_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if not isinstance(value, list) or not value:
            raise ValueError("frontend_origins must contain at least one origin")
        return value

    @field_validator("market_exchange")
    @classmethod
    def validate_market_exchange(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "binance":
            raise ValueError("only the public 'binance' market exchange is supported in Phase 2")
        return normalized

    @field_validator("ema_slow_period")
    @classmethod
    def validate_ema_periods(cls, value: int, info: object) -> int:
        fast_period = getattr(info, "data", {}).get("ema_fast_period")
        if fast_period is not None and fast_period >= value:
            raise ValueError("ema_fast_period must be less than ema_slow_period")
        return value

    @field_validator("rsi_long_max")
    @classmethod
    def validate_long_rsi_range(cls, value: float, info: object) -> float:
        minimum = getattr(info, "data", {}).get("rsi_long_min")
        if minimum is not None and minimum >= value:
            raise ValueError("rsi_long_min must be less than rsi_long_max")
        return value

    @field_validator("rsi_short_max")
    @classmethod
    def validate_short_rsi_range(cls, value: float, info: object) -> float:
        minimum = getattr(info, "data", {}).get("rsi_short_min")
        if minimum is not None and minimum >= value:
            raise ValueError("rsi_short_min must be less than rsi_short_max")
        return value

    @field_validator("max_atr_bps")
    @classmethod
    def validate_atr_range(cls, value: float, info: object) -> float:
        minimum = getattr(info, "data", {}).get("min_atr_bps")
        if minimum is not None and minimum > value:
            raise ValueError("min_atr_bps must be less than or equal to max_atr_bps")
        return value

    @field_validator("max_stop_distance_bps")
    @classmethod
    def validate_stop_distance_range(cls, value: float, info: object) -> float:
        minimum = getattr(info, "data", {}).get("min_stop_distance_bps")
        if minimum is not None and minimum >= value:
            raise ValueError("min_stop_distance_bps must be less than max_stop_distance_bps")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
