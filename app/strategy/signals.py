"""Trading signal generation"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Signal types."""
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


@dataclass
class TradingSignal:
    """Trading signal with metadata."""
    timestamp: datetime
    signal: SignalType
    regime: str
    confidence: float
    features: dict
    rejection_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'signal': self.signal.value,
            'regime': self.regime,
            'confidence': self.confidence,
            'rejection_reason': self.rejection_reason,
            'features': self.features,
        }


class SignalGenerator:
    """
    Generate trading signals from model predictions.

    The regime policy is explicit and configurable:

    - TREND           -> trend entries are allowed, subject to the trend
                         alignment filter and the confidence threshold.
    - RANGE           -> no trend entries (a range strategy would be a
                         separate, independently validated component).
    - HIGH_VOLATILITY -> no entries at all.
    - Low confidence or a missing alignment indicator -> HOLD.
    """

    # Which regimes permit a directional entry.
    ALLOWED_REGIMES = {"TREND"}

    def __init__(
        self,
        confidence_threshold: float = 0.6,
        allowed_regimes: Optional[set] = None,
    ):
        """
        Initialize signal generator.

        Args:
            confidence_threshold: Minimum regime probability to act on
            allowed_regimes: Regimes that may produce a directional signal
        """
        self.confidence_threshold = confidence_threshold
        self.allowed_regimes = set(allowed_regimes or self.ALLOWED_REGIMES)

        logger.info(
            f"SignalGenerator: confidence>={confidence_threshold:.2f}, "
            f"allowed_regimes={sorted(self.allowed_regimes)}"
        )

    def generate(
        self,
        regime_pred: str,
        regime_probs: dict,
        features: dict,
        timestamp: datetime,
    ) -> TradingSignal:
        """Generate signal from regime prediction."""
        confidence = regime_probs.get(regime_pred, 0.0)

        def _make(signal_type, reason=None):
            return TradingSignal(
                timestamp=timestamp,
                signal=signal_type,
                regime=regime_pred,
                confidence=confidence,
                features=features,
                rejection_reason=reason,
            )

        # Regime policy gate
        if regime_pred not in self.allowed_regimes:
            reason = (
                f"Regime {regime_pred} does not permit directional entries "
                f"(allowed: {sorted(self.allowed_regimes)})"
            )
            logger.info(f"-> HOLD: {reason}")
            return _make(SignalType.NEUTRAL, reason)

        # Confidence gate
        if confidence < self.confidence_threshold:
            reason = (
                f"Confidence {confidence:.2%} below threshold "
                f"{self.confidence_threshold:.2%}"
            )
            logger.info(f"-> HOLD: {reason}")
            return _make(SignalType.NEUTRAL, reason)

        # Trend alignment filter
        ema_alignment = features.get('ema_alignment', None)
        ema_trend_short = features.get('ema_trend_short', None)

        if ema_alignment is not None:
            if ema_alignment > 0:
                return _make(SignalType.LONG)
            if ema_alignment < 0:
                return _make(SignalType.SHORT)
            reason = "No trend alignment (ema_alignment == 0)"
            logger.info(f"-> HOLD: {reason}")
            return _make(SignalType.NEUTRAL, reason)

        if ema_trend_short is not None:
            if ema_trend_short > 0.5:
                return _make(SignalType.LONG)
            if ema_trend_short < 0.5:
                return _make(SignalType.SHORT)

        reason = "No trend direction indicator available"
        logger.info(f"-> HOLD: {reason}")
        return _make(SignalType.NEUTRAL, reason)
