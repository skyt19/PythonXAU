"""Test trading strategy"""
import pytest
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.strategy.signals import SignalGenerator, SignalType


def test_signal_generation_trend_long():
    """Test long signal in trend regime."""
    gen = SignalGenerator(confidence_threshold=0.6)

    signal = gen.generate(
        regime_pred='TREND',
        regime_probs={'TREND': 0.8, 'RANGE': 0.1, 'HIGH_VOLATILITY': 0.1},
        features={'ema_alignment': 1.0},
        timestamp=datetime.now(),
    )

    assert signal.signal == SignalType.LONG
    assert signal.regime == 'TREND'
    assert signal.confidence == 0.8


def test_signal_generation_trend_short():
    """Test short signal in trend regime."""
    gen = SignalGenerator(confidence_threshold=0.6)

    signal = gen.generate(
        regime_pred='TREND',
        regime_probs={'TREND': 0.8, 'RANGE': 0.1, 'HIGH_VOLATILITY': 0.1},
        features={'ema_alignment': -1.0},
        timestamp=datetime.now(),
    )

    assert signal.signal == SignalType.SHORT


def test_signal_generation_low_confidence():
    """Test neutral signal when confidence is low."""
    gen = SignalGenerator(confidence_threshold=0.6)

    signal = gen.generate(
        regime_pred='TREND',
        regime_probs={'TREND': 0.5, 'RANGE': 0.3, 'HIGH_VOLATILITY': 0.2},
        features={'ema_alignment': 1.0},
        timestamp=datetime.now(),
    )

    assert signal.signal == SignalType.NEUTRAL
    assert signal.rejection_reason is not None
    assert 'onfidence' in signal.rejection_reason


def test_signal_generation_range():
    """Range regime does not permit directional entries."""
    gen = SignalGenerator()

    signal = gen.generate(
        regime_pred='RANGE',
        regime_probs={'TREND': 0.1, 'RANGE': 0.8, 'HIGH_VOLATILITY': 0.1},
        features={'ema_alignment': 0.5},
        timestamp=datetime.now(),
    )

    assert signal.signal == SignalType.NEUTRAL
    assert 'RANGE' in signal.rejection_reason


def test_signal_generation_high_volatility():
    """High volatility regime blocks entries."""
    gen = SignalGenerator()

    signal = gen.generate(
        regime_pred='HIGH_VOLATILITY',
        regime_probs={'TREND': 0.1, 'RANGE': 0.1, 'HIGH_VOLATILITY': 0.8},
        features={'ema_alignment': 1.0},
        timestamp=datetime.now(),
    )

    assert signal.signal == SignalType.NEUTRAL
    assert 'HIGH_VOLATILITY' in signal.rejection_reason


def test_no_alignment_indicator_holds():
    """Without a trend direction indicator the decision is HOLD."""
    gen = SignalGenerator(confidence_threshold=0.6)

    signal = gen.generate(
        regime_pred='TREND',
        regime_probs={'TREND': 0.9, 'RANGE': 0.05, 'HIGH_VOLATILITY': 0.05},
        features={},
        timestamp=datetime.now(),
    )

    assert signal.signal == SignalType.NEUTRAL
    assert signal.rejection_reason is not None


def test_ema_trend_short_fallback():
    """ema_trend_short is used when ema_alignment is absent."""
    gen = SignalGenerator(confidence_threshold=0.6)

    bullish = gen.generate(
        regime_pred='TREND',
        regime_probs={'TREND': 0.9, 'RANGE': 0.05, 'HIGH_VOLATILITY': 0.05},
        features={'ema_trend_short': 1.0},
        timestamp=datetime.now(),
    )
    bearish = gen.generate(
        regime_pred='TREND',
        regime_probs={'TREND': 0.9, 'RANGE': 0.05, 'HIGH_VOLATILITY': 0.05},
        features={'ema_trend_short': 0.0},
        timestamp=datetime.now(),
    )

    assert bullish.signal == SignalType.LONG
    assert bearish.signal == SignalType.SHORT


def test_allowed_regimes_are_configurable():
    """The set of regimes that may trade is configurable."""
    gen = SignalGenerator(confidence_threshold=0.6, allowed_regimes={'TREND', 'RANGE'})

    signal = gen.generate(
        regime_pred='RANGE',
        regime_probs={'TREND': 0.1, 'RANGE': 0.9, 'HIGH_VOLATILITY': 0.0},
        features={'ema_alignment': 1.0},
        timestamp=datetime.now(),
    )

    assert signal.signal == SignalType.LONG


def test_rejection_reason_always_set_on_hold():
    """Every HOLD carries an explanatory reason."""
    gen = SignalGenerator(confidence_threshold=0.99)

    for regime in ['TREND', 'RANGE', 'HIGH_VOLATILITY']:
        signal = gen.generate(
            regime_pred=regime,
            regime_probs={regime: 0.5},
            features={'ema_alignment': 1.0},
            timestamp=datetime.now(),
        )
        if signal.signal == SignalType.NEUTRAL:
            assert signal.rejection_reason, f"No reason for {regime}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
