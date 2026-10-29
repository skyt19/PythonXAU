"""Test risk management"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.risk.position_sizing import PositionSizer, RiskManager


def test_position_sizer_basic():
    """Test basic position sizing."""
    sizer = PositionSizer(max_risk_per_trade=0.02, max_lots=1.0)

    pos = sizer.calculate(
        balance=10000,
        entry_price=2000,
        stop_loss_price=1960,  # 40 pip stop = 400 pips
        confidence=1.0,
    )

    assert pos is not None
    assert 0.01 <= pos.lots <= 1.0
    assert pos.risk_amount <= 200  # 2% of 10000
    assert pos.stop_distance_pips == 400


def test_position_sizer_confidence_scaling():
    """Test position size scales with confidence."""
    sizer = PositionSizer(max_risk_per_trade=0.02)

    pos_high = sizer.calculate(10000, 2000, 1960, confidence=1.0)
    pos_low = sizer.calculate(10000, 2000, 1960, confidence=0.5)

    assert pos_low.lots < pos_high.lots
    assert pos_low.risk_amount == pos_high.risk_amount * 0.5


def test_position_sizer_invalid_inputs():
    """Test invalid inputs."""
    sizer = PositionSizer()

    assert sizer.calculate(0, 2000, 1960) is None  # Invalid balance
    assert sizer.calculate(10000, 0, 1960) is None  # Invalid price
    assert sizer.calculate(10000, 2000, 1999.5) is None  # Stop too tight (5 pips)


def test_risk_manager_max_trades():
    """Test max open trades limit."""
    manager = RiskManager(max_open_trades=1)

    can_trade, reason = manager.can_open_trade(
        balance=10000,
        equity=10000,
        peak_balance=10000,
        daily_pnl=0,
        open_positions=0,
    )
    assert can_trade

    can_trade, reason = manager.can_open_trade(
        balance=10000,
        equity=10000,
        peak_balance=10000,
        daily_pnl=0,
        open_positions=1,
    )
    assert not can_trade
    assert "Max open trades" in reason


def test_risk_manager_daily_loss():
    """Test daily loss limit."""
    manager = RiskManager(max_daily_loss=0.05)

    can_trade, reason = manager.can_open_trade(
        balance=10000,
        equity=9600,
        peak_balance=10000,
        daily_pnl=-500,  # 5% loss
        open_positions=0,
    )
    assert not can_trade
    assert "Daily loss" in reason


def test_risk_manager_drawdown():
    """Test max drawdown limit."""
    manager = RiskManager(max_drawdown=0.15)

    can_trade, reason = manager.can_open_trade(
        balance=8500,
        equity=8500,
        peak_balance=10000,
        daily_pnl=0,
        open_positions=0,
    )
    assert not can_trade
    assert "drawdown" in reason


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
