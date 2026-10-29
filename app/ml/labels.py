"""
Regime Label Generation

Generates market regime labels from OHLC data.
Uses future data for labels (supervised learning target), but ensures no leakage into features.
"""
import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RegimeLabeler:
    """Generate regime labels from price data."""

    # Regime classes
    TREND = 0
    RANGE = 1
    HIGH_VOLATILITY = 2

    def __init__(
        self,
        lookforward: int = 8,  # 8 * 15min = 2 hours
        trend_threshold: float = 0.004,  # 0.4% move
        volatility_threshold: float = 0.006,  # 0.6% realized vol
    ):
        """
        Initialize regime labeler.

        Args:
            lookforward: Bars to look forward for regime classification
            trend_threshold: Minimum price move to classify as trend
            volatility_threshold: Minimum volatility to classify as high vol
        """
        self.lookforward = lookforward
        self.trend_threshold = trend_threshold
        self.volatility_threshold = volatility_threshold

        logger.info(
            f"RegimeLabeler: lookforward={lookforward}, "
            f"trend_threshold={trend_threshold:.1%}, "
            f"vol_threshold={volatility_threshold:.1%}"
        )

    def generate_labels(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Generate regime labels.

        This uses FUTURE data for label generation (which is appropriate for supervised learning).
        The labels represent what happened AFTER each bar.

        Args:
            df: DataFrame with OHLC data

        Returns:
            DataFrame with 'regime' column added
        """
        if df.empty:
            raise ValueError("Empty DataFrame")

        if 'close' not in df.columns:
            raise ValueError("DataFrame must have 'close' column")

        logger.info(f"Generating labels for {len(df)} bars")

        df = df.copy()

        # Calculate forward returns
        df['forward_return'] = df['close'].pct_change(periods=self.lookforward).shift(-self.lookforward)

        # Calculate forward realized volatility
        df['forward_vol'] = (
            df['close']
            .pct_change()
            .rolling(window=self.lookforward)
            .std()
            .shift(-self.lookforward)
        )

        # Calculate trend strength (ADX if available, otherwise use returns)
        if 'ADX_14' in df.columns:
            trend_strength = df['ADX_14']
        else:
            # Use absolute returns as proxy for trend strength
            trend_strength = df['forward_return'].abs()

        # Initialize labels
        labels = np.full(len(df), self.RANGE, dtype=int)

        # HIGH_VOLATILITY: High realized volatility
        high_vol_mask = df['forward_vol'] > self.volatility_threshold
        labels[high_vol_mask] = self.HIGH_VOLATILITY

        # TREND: Significant directional move and not high volatility
        trend_mask = (
            (df['forward_return'].abs() > self.trend_threshold)
            & ~high_vol_mask
        )
        labels[trend_mask] = self.TREND

        # RANGE: Default (low volatility, no clear trend)
        # Already initialized to RANGE

        df['regime'] = labels

        # Remove rows with NaN labels (at the end due to forward-looking)
        df = df.dropna(subset=['regime', 'forward_return', 'forward_vol'])

        # Log distribution
        regime_counts = df['regime'].value_counts().sort_index()
        logger.info("Regime distribution:")
        for regime, count in regime_counts.items():
            regime_name = ['TREND', 'RANGE', 'HIGH_VOLATILITY'][regime]
            logger.info(f"  {regime_name}: {count} ({count/len(df):.1%})")

        # Check for class imbalance
        min_class_count = regime_counts.min()
        max_class_count = regime_counts.max()
        imbalance_ratio = max_class_count / min_class_count

        if imbalance_ratio > 5.0:
            logger.warning(
                f"Significant class imbalance detected: {imbalance_ratio:.1f}x"
            )

        return df

    def validate_labels(self, df: pd.DataFrame) -> Tuple[bool, list]:
        """
        Validate generated labels.

        Args:
            df: DataFrame with regime labels

        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []

        if 'regime' not in df.columns:
            errors.append("Missing 'regime' column")
            return False, errors

        # Check for valid values
        valid_values = {self.TREND, self.RANGE, self.HIGH_VOLATILITY}
        invalid = df[~df['regime'].isin(valid_values)]
        if len(invalid) > 0:
            errors.append(f"Invalid regime values: {invalid['regime'].unique()}")

        # Check for NaN
        if df['regime'].isna().any():
            errors.append("NaN values in regime labels")

        # Check class distribution
        regime_counts = df['regime'].value_counts()
        if len(regime_counts) < 3:
            missing_classes = valid_values - set(regime_counts.index)
            errors.append(f"Missing regime classes: {missing_classes}")

        is_valid = len(errors) == 0
        return is_valid, errors
