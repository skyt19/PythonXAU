"""
Feature Builder - Reproducible Feature Engineering

Builds features from OHLC data using only information available at decision time.
No look-ahead bias.
"""
import logging
from typing import List, Optional

import pandas as pd
import numpy as np

from app.features.indicators import calculate_indicators

logger = logging.getLogger(__name__)


class FeatureSchema:
    """Feature schema versioning."""

    VERSION = "1.0.0"

    FEATURE_COLUMNS = [
        # Returns
        'returns',
        'log_returns',
        'returns_1h',  # 4-bar return (4 * 15min)
        'returns_4h',  # 16-bar return

        # Volatility
        'realized_vol',
        'atr',
        'atr_normalized',

        # Trend
        'ema_trend_short',
        'ema_trend_long',
        'price_vs_ema20',
        'price_vs_ema50',
        'ema20_slope',

        # Momentum
        'rsi',
        'rsi_change',

        # Directional
        'ADX_14',
        'DMP_14',
        'DMN_14',
        'di_diff',

        # Candle features
        'body_normalized',
        'range_normalized',
        'upper_wick_ratio',
        'lower_wick_ratio',

        # Spread (if available)
        'spread_normalized',

        # Time features
        'hour',
        'day_of_week',
        'is_asian_session',
        'is_london_session',
        'is_ny_session',
    ]


class FeatureBuilder:
    """Build features from OHLC data."""

    def __init__(self, lookback: int = 64):
        """
        Initialize feature builder.

        Args:
            lookback: Number of bars for sequence features
        """
        self.lookback = lookback
        self.schema_version = FeatureSchema.VERSION

        logger.info(f"FeatureBuilder initialized: lookback={lookback}, schema={self.schema_version}")

    def build_features(
        self,
        df: pd.DataFrame,
        include_future_labels: bool = False,
    ) -> pd.DataFrame:
        """
        Build features from OHLC data.

        Args:
            df: DataFrame with OHLC data (must have timestamp, open, high, low, close)
            include_future_labels: If True, generate labels using future data (training only)

        Returns:
            DataFrame with features
        """
        if df.empty:
            raise ValueError("Empty DataFrame")

        # Check required columns
        required = ['timestamp', 'open', 'high', 'low', 'close']
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        logger.info(f"Building features from {len(df)} bars")

        # Make a copy
        df = df.copy()

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        # Calculate technical indicators
        df = calculate_indicators(df)

        # Add multi-timeframe returns
        df['returns_1h'] = df['close'].pct_change(periods=4)  # 4 * 15min = 1h
        df['returns_4h'] = df['close'].pct_change(periods=16)  # 16 * 15min = 4h

        # Normalized ATR
        df['atr_normalized'] = df['atr'] / df['close']

        # EMA slope (rate of change)
        if 'ema_20' in df.columns:
            df['ema20_slope'] = df['ema_20'].pct_change(periods=4)

        # RSI change
        if 'rsi' in df.columns:
            df['rsi_change'] = df['rsi'].diff()

        # Directional difference
        if 'DMP_14' in df.columns and 'DMN_14' in df.columns:
            df['di_diff'] = df['DMP_14'] - df['DMN_14']

        # Normalized candle features
        df['body_normalized'] = df['body'] / df['close']
        df['range_normalized'] = df['range'] / df['close']
        df['upper_wick_ratio'] = df['upper_wick'] / df['range'].replace(0, np.nan)
        df['lower_wick_ratio'] = df['lower_wick'] / df['range'].replace(0, np.nan)

        # Fill NaN in ratios with 0
        df['upper_wick_ratio'] = df['upper_wick_ratio'].fillna(0)
        df['lower_wick_ratio'] = df['lower_wick_ratio'].fillna(0)

        # Time features
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek

        # Trading sessions (UTC times)
        # Asian: 00:00-09:00 UTC
        # London: 08:00-16:00 UTC
        # NY: 13:00-22:00 UTC
        df['is_asian_session'] = ((df['hour'] >= 0) & (df['hour'] < 9)).astype(int)
        df['is_london_session'] = ((df['hour'] >= 8) & (df['hour'] < 16)).astype(int)
        df['is_ny_session'] = ((df['hour'] >= 13) & (df['hour'] < 22)).astype(int)

        # Drop rows with NaN values from indicator calculations
        # (typically first 200 bars for EMA200)
        initial_count = len(df)
        df = df.dropna(subset=FeatureSchema.FEATURE_COLUMNS, how='any')
        dropped = initial_count - len(df)

        if dropped > 0:
            logger.info(f"Dropped {dropped} rows with NaN values")

        logger.info(f"Features built: {len(df)} valid bars")

        return df

    def get_feature_columns(self) -> List[str]:
        """Get list of feature column names."""
        return FeatureSchema.FEATURE_COLUMNS.copy()

    def validate_features(self, df: pd.DataFrame) -> tuple[bool, List[str]]:
        """
        Validate feature DataFrame.

        Args:
            df: DataFrame with features

        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []

        # Check all expected features exist
        missing = [col for col in FeatureSchema.FEATURE_COLUMNS if col not in df.columns]
        if missing:
            errors.append(f"Missing feature columns: {missing}")

        # Check for infinite values
        for col in FeatureSchema.FEATURE_COLUMNS:
            if col in df.columns:
                if df[col].isin([np.inf, -np.inf]).any():
                    errors.append(f"Infinite values in {col}")

        # Check for excessive NaN
        for col in FeatureSchema.FEATURE_COLUMNS:
            if col in df.columns:
                nan_pct = df[col].isna().sum() / len(df)
                if nan_pct > 0.05:  # More than 5% NaN
                    errors.append(f"Excessive NaN in {col}: {nan_pct:.1%}")

        is_valid = len(errors) == 0
        return is_valid, errors
