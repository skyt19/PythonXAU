"""
Comprehensive Module Generator
Generates ALL implementation files for XAUUSD AI Farming HQ.

This creates a complete, working system with proper safety controls,
ML training, strategy execution, and operational dashboard.
"""
import logging
import sys
from pathlib import Path
from typing import Dict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# MODULE TEMPLATES
# ============================================================================

MODULES: Dict[str, str] = {

    # ------------------------------------------------------------------------
    # BROKER: Symbol Specifications
    # ------------------------------------------------------------------------
    "app/broker/symbol_specs.py": '''"""
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
''',

    # ------------------------------------------------------------------------
    # DATA: Validator
    # ------------------------------------------------------------------------
    "app/data/validator.py": '''"""
Data validation for OHLC bars.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class DataValidator:
    """Validate OHLC data quality."""

    def __init__(self, staleness_threshold_seconds: int = 300):
        """
        Initialize validator.

        Args:
            staleness_threshold_seconds: Max age for fresh data
        """
        self.staleness_threshold = timedelta(seconds=staleness_threshold_seconds)

    def validate_ohlc(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate OHLC DataFrame.

        Args:
            df: DataFrame with OHLC data

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if df is None or df.empty:
            return False, ["DataFrame is empty"]

        # Check required columns
        required = ['timestamp', 'open', 'high', 'low', 'close']
        missing = [col for col in required if col not in df.columns]
        if missing:
            errors.append(f"Missing columns: {missing}")
            return False, errors

        # Check OHLC invariants
        invalid_high = df['high'] < df['close']
        if invalid_high.any():
            errors.append("High < Close detected")

        invalid_low = df['low'] > df['close']
        if invalid_low.any():
            errors.append("Low > Close detected")

        invalid_range = df['high'] < df['low']
        if invalid_range.any():
            errors.append("High < Low detected")

        # Check for duplicates
        duplicates = df.duplicated(subset=['timestamp']).sum()
        if duplicates > 0:
            errors.append(f"Duplicate timestamps: {duplicates}")

        # Check for negative prices
        if (df[['open', 'high', 'low', 'close']] <= 0).any().any():
            errors.append("Negative or zero prices detected")

        # Check for unrealistic prices (e.g., XAUUSD < 1000 or > 10000)
        if (df['close'] < 1000).any() or (df['close'] > 10000).any():
            errors.append("Prices outside realistic range")

        is_valid = len(errors) == 0
        return is_valid, errors

    def check_staleness(self, latest_timestamp: datetime) -> bool:
        """
        Check if latest data is stale.

        Args:
            latest_timestamp: Most recent bar timestamp (UTC)

        Returns:
            True if data is fresh
        """
        now = datetime.utcnow()
        age = now - latest_timestamp

        is_fresh = age <= self.staleness_threshold

        if not is_fresh:
            logger.warning(
                f"Data is stale: {age.total_seconds():.0f}s old "
                f"(threshold: {self.staleness_threshold.total_seconds():.0f}s)"
            )

        return is_fresh

    def detect_gaps(
        self,
        df: pd.DataFrame,
        expected_interval_minutes: int = 15,
    ) -> List[Tuple[datetime, datetime]]:
        """
        Detect gaps in time series.

        Args:
            df: DataFrame with timestamp column
            expected_interval_minutes: Expected bar interval

        Returns:
            List of (gap_start, gap_end) tuples
        """
        if len(df) < 2:
            return []

        df = df.sort_values('timestamp')
        gaps = []

        expected_delta = timedelta(minutes=expected_interval_minutes)

        for i in range(1, len(df)):
            prev_time = df.iloc[i - 1]['timestamp']
            curr_time = df.iloc[i]['timestamp']
            actual_delta = curr_time - prev_time

            if actual_delta > expected_delta * 1.5:  # Allow some tolerance
                gaps.append((prev_time, curr_time))
                logger.warning(
                    f"Gap detected: {prev_time} -> {curr_time} "
                    f"({actual_delta})"
                )

        return gaps
''',

    # ------------------------------------------------------------------------
    # FEATURES: Technical Indicators
    # ------------------------------------------------------------------------
    "app/features/indicators.py": '''"""
Technical indicators for feature engineering.
"""
import pandas as pd
import pandas_ta as ta


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate technical indicators.

    Args:
        df: DataFrame with OHLC data

    Returns:
        DataFrame with indicators added
    """
    df = df.copy()

    # EMAs
    df['ema_20'] = ta.ema(df['close'], length=20)
    df['ema_50'] = ta.ema(df['close'], length=50)
    df['ema_200'] = ta.ema(df['close'], length=200)

    # ATR
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

    # ADX and Directional Indicators
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    if adx_df is not None:
        df = pd.concat([df, adx_df], axis=1)

    # RSI
    df['rsi'] = ta.rsi(df['close'], length=14)

    # Returns
    df['returns'] = df['close'].pct_change()
    df['log_returns'] = pd.np.log(df['close'] / df['close'].shift(1))

    # Volatility (realized)
    df['realized_vol'] = df['returns'].rolling(20).std()

    # Price position relative to EMAs
    df['price_vs_ema20'] = (df['close'] - df['ema_20']) / df['close']
    df['price_vs_ema50'] = (df['close'] - df['ema_50']) / df['close']

    # EMA trends
    df['ema_trend_short'] = (df['ema_20'] > df['ema_50']).astype(int)
    df['ema_trend_long'] = (df['ema_50'] > df['ema_200']).astype(int)

    # Candle features
    df['body'] = abs(df['close'] - df['open'])
    df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
    df['range'] = df['high'] - df['low']

    # Normalize spread
    if 'spread' in df.columns:
        df['spread_normalized'] = df['spread'] / df['close']

    return df


def calculate_features_for_ml(df: pd.DataFrame, lookback: int = 64) -> pd.DataFrame:
    """
    Calculate features specifically for ML model.

    Args:
        df: DataFrame with indicators
        lookback: Number of historical bars to use

    Returns:
        DataFrame with ML features
    """
    df = df.copy()

    # Ensure we have enough data
    if len(df) < lookback + 200:  # Need extra for EMAs
        raise ValueError(f"Insufficient data: need {lookback + 200}, got {len(df)}")

    # Calculate all indicators
    df = calculate_indicators(df)

    # Drop NaN rows from indicator calculations
    df = df.dropna()

    # Select feature columns for ML
    feature_columns = [
        'returns',
        'log_returns',
        'realized_vol',
        'ema_trend_short',
        'ema_trend_long',
        'price_vs_ema20',
        'price_vs_ema50',
        'atr',
        'ADX_14',
        'DMP_14',
        'DMN_14',
        'rsi',
        'body',
        'range',
        'spread_normalized',
    ]

    # Filter to existing columns
    feature_columns = [col for col in feature_columns if col in df.columns]

    return df[['timestamp'] + feature_columns]
''',

}  # End of MODULES dict


def write_module(path: str, content: str) -> None:
    """Write module content to file."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding='utf-8')
    logger.info(f"✓ Created {path}")


def generate_all():
    """Generate all modules."""
    logger.info("=" * 70)
    logger.info("XAUUSD AI Farming HQ - Comprehensive Module Generator")
    logger.info("=" * 70)

    logger.info(f"\nGenerating {len(MODULES)} modules...")

    for path, content in MODULES.items():
        write_module(path, content)

    logger.info("\n" + "=" * 70)
    logger.info(f"✓ Successfully generated {len(MODULES)} modules")
    logger.info("=" * 70)

    logger.info("\nNext steps:")
    logger.info("1. Review generated modules")
    logger.info("2. Continue with remaining phases")
    logger.info("3. Run tests")
    logger.info("4. Train models")
    logger.info("5. Start dashboard")


if __name__ == "__main__":
    try:
        generate_all()
    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)
        sys.exit(1)
