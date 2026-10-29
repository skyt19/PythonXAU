"""Position sizing and risk management"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PositionSize:
    """Position size calculation result."""
    lots: float
    risk_amount: float
    stop_distance_pips: float
    position_value: float

    def to_dict(self) -> dict:
        return {
            'lots': self.lots,
            'risk_amount': self.risk_amount,
            'stop_distance_pips': self.stop_distance_pips,
            'position_value': self.position_value,
        }


class PositionSizer:
    """Calculate position sizes based on risk parameters."""

    def __init__(
        self,
        max_risk_per_trade: float = 0.02,  # 2% max risk per trade
        max_lots: float = 1.0,
        min_lots: float = 0.01,
        pip_value_per_lot: float = 10.0,
        volume_step: float = 0.01,
    ):
        """
        Initialize position sizer.

        Args:
            max_risk_per_trade: Maximum fraction of balance risked per trade
            max_lots: Broker maximum volume
            min_lots: Broker minimum volume
            pip_value_per_lot: Dollar value of one pip for 1.00 lot.
                XAUUSD on HFM: 0.10 move = 10 ticks x $1.00/tick = $10.00 per lot.
            volume_step: Broker volume step
        """
        if not 0 < max_risk_per_trade <= 0.05:
            raise ValueError("max_risk_per_trade must be (0, 0.05]")

        self.max_risk_per_trade = max_risk_per_trade
        self.max_lots = max_lots
        self.min_lots = min_lots
        self.pip_value_per_lot = pip_value_per_lot
        self.volume_step = volume_step

    def calculate(
        self,
        balance: float,
        entry_price: float,
        stop_loss_price: float,
        confidence: float = 1.0,
    ) -> Optional[PositionSize]:
        """
        Calculate position size.

        Returns None when no volume can satisfy the risk budget. The result is
        never rounded UP to the broker minimum: if the minimum lot would
        exceed the risk budget, the trade is rejected instead.
        """
        if balance <= 0:
            logger.warning("Invalid balance")
            return None

        if entry_price <= 0 or stop_loss_price <= 0:
            logger.warning("Invalid prices")
            return None

        # Stop distance in pips (1 pip = 0.10 price move for XAUUSD)
        stop_distance_pips = abs(entry_price - stop_loss_price) * 10

        if stop_distance_pips < 10:
            logger.warning(f"Stop too tight: {stop_distance_pips:.1f} pips")
            return None

        # Risk amount (scaled by confidence)
        risk_amount = balance * self.max_risk_per_trade * confidence

        # Position size in lots
        lots = risk_amount / (stop_distance_pips * self.pip_value_per_lot)

        # Round DOWN to the broker volume step. Rounding up would silently
        # breach the risk budget.
        lots = (lots // self.volume_step) * self.volume_step
        lots = round(lots, 4)

        if lots < self.min_lots:
            # The smallest tradable lot exceeds the risk budget. Rounding up to
            # the broker minimum would breach the risk limit, so reject.
            min_lot_risk = self.min_lots * stop_distance_pips * self.pip_value_per_lot
            logger.warning(
                f"Trade rejected: min lot {self.min_lots} risks ${min_lot_risk:.2f} "
                f"but risk budget is only ${risk_amount:.2f} "
                f"(balance ${balance:.2f}, {stop_distance_pips:.0f} pip stop)"
            )
            return None

        if lots > self.max_lots:
            lots = self.max_lots

        position_value = lots * 100 * entry_price

        return PositionSize(
            lots=lots,
            risk_amount=risk_amount,
            stop_distance_pips=stop_distance_pips,
            position_value=position_value,
        )



class RiskManager:
    """Enforce risk limits."""

    def __init__(
        self,
        max_open_trades: int = 1,
        max_daily_loss: float = 0.05,  # 5% max daily loss
        max_drawdown: float = 0.15,  # 15% max drawdown
    ):
        self.max_open_trades = max_open_trades
        self.max_daily_loss = max_daily_loss
        self.max_drawdown = max_drawdown

    def can_open_trade(
        self,
        balance: float,
        equity: float,
        peak_balance: float,
        daily_pnl: float,
        open_positions: int,
    ) -> tuple[bool, str]:
        """Check if new trade is allowed."""
        # Max open trades
        if open_positions >= self.max_open_trades:
            return False, "Max open trades reached"

        # Daily loss limit
        daily_loss_pct = abs(daily_pnl) / balance if balance > 0 else 0
        if daily_pnl < 0 and daily_loss_pct >= self.max_daily_loss:
            return False, f"Daily loss limit reached: {daily_loss_pct:.1%}"

        # Drawdown limit
        drawdown = (peak_balance - equity) / peak_balance if peak_balance > 0 else 0
        if drawdown >= self.max_drawdown:
            return False, f"Max drawdown reached: {drawdown:.1%}"

        return True, "OK"
