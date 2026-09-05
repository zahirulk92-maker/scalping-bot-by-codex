"""Domain exceptions reserved for future trading modules."""


class BotError(Exception):
    """Base exception for the bot."""


class ConfigurationError(BotError):
    """Raised when application configuration is invalid."""


class MarketDataError(BotError):
    """Raised by future market-data integrations."""


class StrategyError(BotError):
    """Raised by future strategy modules."""


class RiskError(BotError):
    """Raised by future risk modules."""


class ExecutionError(BotError):
    """Raised by future execution modules."""
