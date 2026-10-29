"""
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
