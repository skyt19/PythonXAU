"""Backtesting engine with realistic costs"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import pandas as pd

from app.strategy.signals import SignalType, TradingSignal
from app.risk.position_sizing import PositionSizer, RiskManager

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Completed trade record."""
    entry_time: datetime
    exit_time: datetime
    direction: str
    entry_price: float
    exit_price: float
    lots: float
    pnl_pips: float
    pnl_gross: float
    pnl_net: float
    commission: float
    slippage_cost: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exit_reason: str = ""

    def to_dict(self) -> dict:
        return {
            'entry_time': self.entry_time.isoformat(),
            'exit_time': self.exit_time.isoformat(),
            'direction': self.direction,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'lots': self.lots,
            'pnl_pips': self.pnl_pips,
            'pnl_gross': self.pnl_gross,
            'pnl_net': self.pnl_net,
            'commission': self.commission,
            'slippage_cost': self.slippage_cost,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'exit_reason': self.exit_reason,
        }


@dataclass
class Position:
    """Open position."""
    entry_time: datetime
    direction: str
    entry_price: float
    lots: float
    stop_loss: float
    take_profit: Optional[float] = None


@dataclass
class BacktestResult:
    """Backtest results with metrics."""
    trades: List[Trade] = field(default_factory=list)
    initial_balance: float = 0
    final_balance: float = 0
    total_return: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    win_rate: float = 0
    profit_factor: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    total_trades: int = 0
    total_pips: float = 0
    total_commission: float = 0
    total_slippage: float = 0

    def to_dict(self) -> dict:
        return {
            'initial_balance': self.initial_balance,
            'final_balance': self.final_balance,
            'total_return': self.total_return,
            'max_drawdown': self.max_drawdown,
            'sharpe_ratio': self.sharpe_ratio,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'total_trades': self.total_trades,
            'total_pips': self.total_pips,
            'total_commission': self.total_commission,
            'total_slippage': self.total_slippage,
            'trades': [t.to_dict() for t in self.trades],
        }


class BacktestEngine:
    """Backtest trading strategy with realistic costs."""

    def __init__(
        self,
        initial_balance: float = 10000,
        commission_per_lot: float = 7.0,  # $7 per round trip lot
        slippage_pips: float = 1.0,  # 1 pip avg slippage
        position_sizer: Optional[PositionSizer] = None,
        risk_manager: Optional[RiskManager] = None,
    ):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance
        self.peak_balance = initial_balance

        self.commission_per_lot = commission_per_lot
        self.slippage_pips = slippage_pips

        self.position_sizer = position_sizer or PositionSizer()
        self.risk_manager = risk_manager or RiskManager()

        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.equity_curve = []

    def run(
        self,
        df: pd.DataFrame,
        signals: List[TradingSignal],
    ) -> BacktestResult:
        """Run backtest."""
        logger.info(f"Starting backtest with {len(df)} bars, {len(signals)} signals")

        signal_map = {s.timestamp: s for s in signals}

        daily_pnl = 0
        last_date = None

        for idx, row in df.iterrows():
            timestamp = row['timestamp']
            current_date = timestamp.date()

            # Reset daily PnL
            if last_date and current_date != last_date:
                daily_pnl = 0
            last_date = current_date

            # Update open position
            if self.position:
                self._update_position(row)

            # Check for new signal
            if timestamp in signal_map and not self.position:
                signal = signal_map[timestamp]
                self._process_signal(signal, row, daily_pnl)

            # Track equity
            self.equity_curve.append({
                'timestamp': timestamp,
                'balance': self.balance,
                'equity': self.equity,
            })

        # Close any open position
        if self.position:
            last_row = df.iloc[-1]
            self._close_position(last_row, 'end_of_backtest')

        return self._compute_metrics()

    def _process_signal(
        self,
        signal: TradingSignal,
        row: pd.Series,
        daily_pnl: float,
    ) -> None:
        """Process trading signal."""
        if signal.signal == SignalType.NEUTRAL:
            return

        # Risk check
        can_trade, reason = self.risk_manager.can_open_trade(
            balance=self.balance,
            equity=self.equity,
            peak_balance=self.peak_balance,
            daily_pnl=daily_pnl,
            open_positions=1 if self.position else 0,
        )

        if not can_trade:
            logger.debug(f"Trade rejected: {reason}")
            return

        # Entry
        entry_price = row['close']

        # Stop loss (2% of price ≈ 400 pips for gold)
        stop_distance_pct = 0.02
        if signal.signal == SignalType.LONG:
            stop_loss = entry_price * (1 - stop_distance_pct)
        else:
            stop_loss = entry_price * (1 + stop_distance_pct)

        # Position size
        pos_size = self.position_sizer.calculate(
            balance=self.balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            confidence=signal.confidence,
        )

        if not pos_size:
            return

        # Apply slippage
        if signal.signal == SignalType.LONG:
            entry_price += self.slippage_pips * 0.1  # 1 pip = $0.10
        else:
            entry_price -= self.slippage_pips * 0.1

        self.position = Position(
            entry_time=row['timestamp'],
            direction=signal.signal.value,
            entry_price=entry_price,
            lots=pos_size.lots,
            stop_loss=stop_loss,
        )

        logger.debug(f"Opened {self.position.direction} at {entry_price:.2f}, SL={stop_loss:.2f}")

    def _update_position(self, row: pd.Series) -> None:
        """Update open position and check exits."""
        if not self.position:
            return

        high = row['high']
        low = row['low']
        close = row['close']

        # Check stop loss
        if self.position.direction == 'LONG':
            if low <= self.position.stop_loss:
                self._close_position(row, 'stop_loss', self.position.stop_loss)
                return
        else:
            if high >= self.position.stop_loss:
                self._close_position(row, 'stop_loss', self.position.stop_loss)
                return

        # Update unrealized P&L
        if self.position.direction == 'LONG':
            pnl = (close - self.position.entry_price) * self.position.lots * 100
        else:
            pnl = (self.position.entry_price - close) * self.position.lots * 100

        self.equity = self.balance + pnl

    def _close_position(
        self,
        row: pd.Series,
        reason: str,
        exit_price: Optional[float] = None,
    ) -> None:
        """Close position and record trade."""
        if not self.position:
            return

        if exit_price is None:
            exit_price = row['close']

        # Calculate P&L
        if self.position.direction == 'LONG':
            pnl_pips = (exit_price - self.position.entry_price) * 10
            pnl_gross = pnl_pips * 10 * self.position.lots
        else:
            pnl_pips = (self.position.entry_price - exit_price) * 10
            pnl_gross = pnl_pips * 10 * self.position.lots

        # Costs
        commission = self.commission_per_lot * self.position.lots
        slippage_cost = self.slippage_pips * 10 * self.position.lots

        pnl_net = pnl_gross - commission - slippage_cost

        trade = Trade(
            entry_time=self.position.entry_time,
            exit_time=row['timestamp'],
            direction=self.position.direction,
            entry_price=self.position.entry_price,
            exit_price=exit_price,
            lots=self.position.lots,
            pnl_pips=pnl_pips,
            pnl_gross=pnl_gross,
            pnl_net=pnl_net,
            commission=commission,
            slippage_cost=slippage_cost,
            stop_loss=self.position.stop_loss,
            exit_reason=reason,
        )

        self.trades.append(trade)
        self.balance += pnl_net
        self.equity = self.balance

        if self.balance > self.peak_balance:
            self.peak_balance = self.balance

        self.position = None

        logger.debug(f"Closed {trade.direction} at {exit_price:.2f}: {pnl_net:+.2f} ({reason})")

    def _compute_metrics(self) -> BacktestResult:
        """Compute backtest metrics."""
        if not self.trades:
            logger.warning("No trades executed")
            return BacktestResult(
                initial_balance=self.initial_balance,
                final_balance=self.balance,
            )

        # Basic metrics
        total_return = (self.balance - self.initial_balance) / self.initial_balance

        # Trade stats
        wins = [t for t in self.trades if t.pnl_net > 0]
        losses = [t for t in self.trades if t.pnl_net < 0]

        win_rate = len(wins) / len(self.trades) if self.trades else 0
        avg_win = sum(t.pnl_net for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl_net for t in losses) / len(losses) if losses else 0

        gross_profit = sum(t.pnl_net for t in wins)
        gross_loss = abs(sum(t.pnl_net for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Drawdown
        equity_series = pd.Series([e['balance'] for e in self.equity_curve])
        running_max = equity_series.expanding().max()
        drawdown = (equity_series - running_max) / running_max
        max_drawdown = abs(drawdown.min())

        # Sharpe ratio (daily returns)
        daily_returns = equity_series.pct_change().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std() * (252**0.5)) if len(daily_returns) > 1 else 0

        # Totals
        total_pips = sum(t.pnl_pips for t in self.trades)
        total_commission = sum(t.commission for t in self.trades)
        total_slippage = sum(t.slippage_cost for t in self.trades)

        return BacktestResult(
            trades=self.trades,
            initial_balance=self.initial_balance,
            final_balance=self.balance,
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            total_trades=len(self.trades),
            total_pips=total_pips,
            total_commission=total_commission,
            total_slippage=total_slippage,
        )
