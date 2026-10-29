"""
Symbol specifications from broker.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


@dataclass
class SymbolSpecs:
    """Symbol specifications."""

    symbol: str
    digits: int
    point: float
    trade_contract_size: float
    trade_tick_size: float
    trade_tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    trade_stops_level: int
    trade_freeze_level: int
    filling_mode: int

    @property
    def pip_value(self) -> float:
        """Value of 1 pip for 1 lot."""
        return self.trade_tick_value / self.trade_tick_size

    def calculate_volume(
        self,
        risk_dollars: float,
        stop_distance_points: float,
    ) -> float:
        """
        Calculate position volume from risk and stop distance.

        Args:
            risk_dollars: Dollar risk amount
            stop_distance_points: Stop distance in points

        Returns:
            Volume in lots, rounded to volume_step
        """
        if stop_distance_points <= 0:
            return 0.0

        # Calculate point value for one lot
        point_value = self.trade_tick_value

        # Calculate volume
        volume = risk_dollars / (stop_distance_points * point_value)

        # Round to volume_step
        volume = round(volume / self.volume_step) * self.volume_step

        # Clamp to min/max
        volume = max(self.volume_min, min(volume, self.volume_max))

        return volume


def get_symbol_specs(symbol: str) -> Optional[SymbolSpecs]:
    """
    Retrieve symbol specifications from MT5.

    Args:
        symbol: Symbol name

    Returns:
        SymbolSpecs or None
    """
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        logger.error(f"Could not retrieve info for {symbol}")
        return None

    specs = SymbolSpecs(
        symbol=symbol,
        digits=symbol_info.digits,
        point=symbol_info.point,
        trade_contract_size=symbol_info.trade_contract_size,
        trade_tick_size=symbol_info.trade_tick_size,
        trade_tick_value=symbol_info.trade_tick_value,
        volume_min=symbol_info.volume_min,
        volume_max=symbol_info.volume_max,
        volume_step=symbol_info.volume_step,
        trade_stops_level=symbol_info.trade_stops_level,
        trade_freeze_level=symbol_info.trade_freeze_level,
        filling_mode=symbol_info.filling_mode,
    )

    logger.info(
        f"Symbol specs: {symbol}, "
        f"contract_size={specs.trade_contract_size}, "
        f"volume=[{specs.volume_min}, {specs.volume_max}] "
        f"step={specs.volume_step}"
    )

    return specs
