"""Pure approval checks that keep rejected plans explainable."""

from datetime import datetime

from app.config import Settings
from app.market.models import FeedState, MarketFeedStatus
from app.risk.models import RiskAccountState
from app.strategy.models import SignalDirection, SignalSnapshot


def signal_rejection_reasons(signal: SignalSnapshot, settings: Settings, now: datetime) -> list[str]:
    reasons: list[str] = []
    if signal.direction not in (SignalDirection.LONG, SignalDirection.SHORT) or not signal.is_actionable:
        reasons.append("Strategy signal is not an actionable long or short candidate")
    if signal.score < settings.signal_min_score:
        reasons.append("Strategy signal score is below the configured threshold")
    if signal.candle_open_time is None or signal.candle_close_time is None:
        reasons.append("Strategy signal is missing its closed-candle identity")
    if signal.generated_at is None:
        reasons.append("Strategy signal is missing its generation time")
    elif (now - signal.generated_at).total_seconds() > settings.max_signal_age_seconds:
        reasons.append("Strategy signal is stale")
    if signal.context.close is None or signal.context.close <= 0:
        reasons.append("Entry reference price is unavailable or invalid")
    if signal.context.atr_14 is None or signal.context.atr_14 <= 0:
        reasons.append("ATR is unavailable or invalid")
    return reasons


def market_rejection_reasons(symbol: str, status: MarketFeedStatus | None) -> list[str]:
    if status is None:
        return []
    symbol_status = status.symbols.get(symbol)
    state = symbol_status.status if symbol_status else status.status
    if state in (FeedState.STALE, FeedState.DISCONNECTED, FeedState.ERROR):
        return [f"Market feed is {state.value}"]
    return []


def account_rejection_reasons(account: RiskAccountState, proposed_risk: object, settings: Settings) -> list[str]:
    reasons: list[str] = []
    if account.open_position_count >= settings.max_open_positions:
        reasons.append("Maximum open-position limit reached")
    daily_limit = account.current_equity * _decimal(settings.max_daily_loss)
    if account.daily_loss_used >= daily_limit:
        reasons.append("Daily loss limit has already been reached")
    elif account.daily_loss_used + _decimal(proposed_risk) > daily_limit:
        reasons.append("Daily loss limit would be exceeded")
    return reasons


def _decimal(value: object):
    from decimal import Decimal
    return Decimal(str(value))
