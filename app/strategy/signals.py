"""Trading signal generation"""
import logging
from dataclasses import dataclass
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

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'signal': self.signal.value,
            'regime': self.regime,
            'confidence': self.confidence,
            'features': self.features,
        }


class SignalGenerator:
    """Generate trading signals from model predictions."""

    def __init__(self, confidence_threshold: float = 0.6):
        self.confidence_threshold = confidence_threshold

    def generate(
        self,
        regime_pred: str,
        regime_probs: dict,
        features: dict,
        timestamp: datetime,
    ) -> TradingSignal:
        """Generate signal from regime prediction."""
        confidence = regime_probs.get(regime_pred, 0.0)

        # Signal logic based on regime
        if regime_pred == "TREND":
            # Use trend indicators if available
            ema_alignment = features.get('ema_alignment', None)
            ema_trend_short = features.get('ema_trend_short', None)

            if ema_alignment is not None:
                if ema_alignment > 0 and confidence >= self.confidence_threshold:
                    signal = SignalType.LONG
                elif ema_alignment < 0 and confidence >= self.confidence_threshold:
                    signal = SignalType.SHORT
                else:
                    signal = SignalType.NEUTRAL
            elif ema_trend_short is not None:
                if ema_trend_short > 0.5 and confidence >= self.confidence_threshold:
                    signal = SignalType.LONG
                elif ema_trend_short < 0.5 and confidence >= self.confidence_threshold:
                    signal = SignalType.SHORT
                else:
                    signal = SignalType.NEUTRAL
            else:
                # Default: long in trend if confident
                if confidence >= self.confidence_threshold:
                    signal = SignalType.LONG
                else:
                    signal = SignalType.NEUTRAL

        elif regime_pred == "RANGE":
            # Range-bound: mean reversion or neutral
            signal = SignalType.NEUTRAL

        else:  # HIGH_VOLATILITY
            # High volatility: stay out
            signal = SignalType.NEUTRAL

        return TradingSignal(
            timestamp=timestamp,
            signal=signal,
            regime=regime_pred,
            confidence=confidence,
            features=features,
        )
