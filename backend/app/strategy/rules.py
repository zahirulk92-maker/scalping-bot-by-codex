"""Transparent closed-candle momentum rules; no market or execution imports."""

from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from app.config import Settings
from app.indicators.models import IndicatorSnapshot
from app.strategy.filters import bps_distance, ratio, relative_bps
from app.strategy.models import SignalDirection
from app.strategy.scoring import WEIGHTS


@dataclass(frozen=True)
class RuleEvaluation:
    direction: SignalDirection
    score: int
    reasons: tuple[str, ...]
    mandatory_rules_passed: bool


def evaluate(snapshot: IndicatorSnapshot, settings: Settings) -> RuleEvaluation:
    """Evaluate all rules from one ready, closed-candle indicator snapshot."""
    values = (snapshot.close, snapshot.ema_9, snapshot.ema_21, snapshot.rsi_14, snapshot.atr_14, snapshot.vwap, snapshot.volume, snapshot.volume_ma_20)
    if not snapshot.is_ready:
        return RuleEvaluation(SignalDirection.NO_TRADE, 0, ("Indicators not ready",), False)
    if any(value is None for value in values):
        return RuleEvaluation(SignalDirection.NO_TRADE, 0, ("Invalid snapshot: missing required indicator value",), False)

    close, ema_fast, ema_slow, rsi, atr, vwap, volume, volume_ma = cast(tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal], values)
    if ema_fast == ema_slow:
        return RuleEvaluation(SignalDirection.NO_TRADE, 0, ("No directional EMA trend",), False)
    direction = SignalDirection.LONG if ema_fast > ema_slow else SignalDirection.SHORT
    bullish = direction == SignalDirection.LONG
    reasons: list[str] = []
    score = 0
    mandatory_passed = True

    ema_distance = bps_distance(ema_fast, ema_slow)
    if ema_distance is not None and ema_distance >= Decimal(str(settings.min_ema_separation_bps)):
        score += WEIGHTS.trend
        reasons.append("EMA 9 above EMA 21" if bullish else "EMA 9 below EMA 21")
    else:
        mandatory_passed = False
        reasons.append("EMA separation below minimum")

    vwap_distance = bps_distance(close, vwap)
    price_on_side = close > vwap if bullish else close < vwap
    if price_on_side and vwap_distance is not None and vwap_distance >= Decimal(str(settings.min_vwap_distance_bps)):
        score += WEIGHTS.vwap
        reasons.append("Close above VWAP" if bullish else "Close below VWAP")
    else:
        mandatory_passed = False
        reasons.append("Price too close to or on the wrong side of VWAP")

    rsi_min, rsi_max = (settings.rsi_long_min, settings.rsi_long_max) if bullish else (settings.rsi_short_min, settings.rsi_short_max)
    if Decimal(str(rsi_min)) <= rsi <= Decimal(str(rsi_max)):
        score += WEIGHTS.rsi
        reasons.append("RSI within long momentum zone" if bullish else "RSI within short momentum zone")
    else:
        mandatory_passed = False
        reasons.append("RSI outside configured momentum zone")

    volume_ratio = ratio(volume, volume_ma)
    if volume_ratio is not None and volume_ratio >= Decimal(str(settings.min_volume_ratio)):
        score += WEIGHTS.volume
        reasons.append("Volume meets confirmation threshold")
    else:
        mandatory_passed = False
        reasons.append("Volume ratio below confirmation threshold")

    atr_bps = relative_bps(atr, close)
    if atr_bps is not None and Decimal(str(settings.min_atr_bps)) <= atr_bps <= Decimal(str(settings.max_atr_bps)):
        score += WEIGHTS.atr
        reasons.append("ATR is within volatility guardrails")
    else:
        mandatory_passed = False
        reasons.append("ATR outside volatility guardrails")

    if score < settings.signal_min_score:
        reasons.append(f"Score {score}/100 is below the {settings.signal_min_score}/100 threshold")
    if not mandatory_passed:
        reasons.append("Signal blocked: one or more mandatory strategy rules failed")
    return RuleEvaluation(direction, score, tuple(reasons), mandatory_passed)
