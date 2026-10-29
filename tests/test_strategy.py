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


def test_signal_generation_range():
    """Test neutral signal in range regime."""
    gen = SignalGenerator()

    signal = gen.generate(
        regime_pred='RANGE',
        regime_probs={'TREND': 0.1, 'RANGE': 0.8, 'HIGH_VOLATILITY': 0.1},
        features={'ema_alignment': 0.5},
        timestamp=datetime.now(),
    )

    assert signal.signal == SignalType.NEUTRAL


def test_signal_generation_high_volatility():
    """Test neutral signal in high volatility regime."""
    gen = SignalGenerator()

    signal = gen.generate(
        regime_pred='HIGH_VOLATILITY',
        regime_probs={'TREND': 0.1, 'RANGE': 0.1, 'HIGH_VOLATILITY': 0.8},
        features={'ema_alignment': 1.0},
        timestamp=datetime.now(),
    )

    assert signal.signal == SignalType.NEUTRAL


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
