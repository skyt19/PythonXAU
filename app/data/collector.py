"""
Data Collector - Resumable Historical OHLC Collection

This module implements read-only MT5 data collection with:
- Resumable collection with explicit date ranges
- Timezone handling (UTC standardization)
- Duplicate detection
- Gap reporting
- Data provenance tracking
- No order submission (read-only)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

import pandas as pd
import pytz
from sqlalchemy.orm import Session

from app.broker.mt5_client import MT5Client
from app.config import config
from app.data.validator import DataValidator
from app.database import MarketData

logger = logging.getLogger(__name__)


class DataCollectionResult:
    """Result of data collection operation."""

    def __init__(self):
        self.success = False
        self.bars_collected = 0
        self.bars_duplicates = 0
        self.gaps_detected = 0
        self.start_date: Optional[datetime] = None
        self.end_date: Optional[datetime] = None
        self.errors: List[str] = []
        self.collection_time: Optional[datetime] = None

    def __str__(self) -> str:
        """Human-readable summary."""
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"Data Collection [{status}]\n"
            f"  Period: {self.start_date} to {self.end_date}\n"
            f"  Bars Collected: {self.bars_collected}\n"
            f"  Duplicates Skipped: {self.bars_duplicates}\n"
            f"  Gaps Detected: {self.gaps_detected}\n"
            f"  Collection Time: {self.collection_time}\n"
            + (f"  Errors: {', '.join(self.errors)}\n" if self.errors else "")
        )


class DataCollector:
    """
    Collects historical OHLC data from MT5.

    This is READ-ONLY. No order submission capability.
    """

    def __init__(
        self,
        mt5_client: MT5Client,
        validator: DataValidator,
        symbol: str = None,
    ):
        """
        Initialize data collector.

        Args:
            mt5_client: MT5 client instance
            validator: Data validator
            symbol: Trading symbol (default from config)
        """
        self.mt5_client = mt5_client
        self.validator = validator
        self.symbol = symbol or config.mt5_symbol

        logger.info(f"DataCollector initialized for {self.symbol}")

    def collect_historical(
        self,
        session: Session,
        days: int = None,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> DataCollectionResult:
        """
        Collect historical OHLC data.

        Args:
            session: Database session
            days: Number of days to collect (from today backwards)
            start_date: Explicit start date (UTC)
            end_date: Explicit end date (UTC)

        Returns:
            DataCollectionResult with collection summary
        """
        result = DataCollectionResult()
        result.collection_time = datetime.utcnow()

        try:
            # Determine date range
            if days is not None:
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days)
            elif start_date is None or end_date is None:
                raise ValueError("Must provide either 'days' or both start_date and end_date")

            # Ensure UTC
            if start_date.tzinfo is None:
                start_date = pytz.UTC.localize(start_date)
            if end_date.tzinfo is None:
                end_date = pytz.UTC.localize(end_date)

            # Convert to UTC if not already
            start_date = start_date.astimezone(pytz.UTC)
            end_date = end_date.astimezone(pytz.UTC)

            result.start_date = start_date
            result.end_date = end_date

            logger.info(
                f"Collecting {self.symbol} data from {start_date} to {end_date}"
            )

            # Get timeframe code
            timeframe = config.get_mt5_timeframe_code()

            # Calculate approximate bar count
            total_minutes = int((end_date - start_date).total_seconds() / 60)
            approx_bars = total_minutes // 15  # M15 timeframe

            logger.info(f"Approximate bars to collect: {approx_bars}")

            # Collect data from MT5
            df = self.mt5_client.get_ohlc(
                symbol=self.symbol,
                timeframe=timeframe,
                start=start_date,
                end=end_date,
            )

            if df is None or df.empty:
                result.errors.append("No data returned from MT5")
                logger.error("No data returned from MT5")
                return result

            logger.info(f"Retrieved {len(df)} bars from MT5")
            logger.info(f"Timestamp dtype: {df['timestamp'].dtype}")
            logger.info(f"Timestamp min: {df['timestamp'].min()}")
            logger.info(f"Timestamp max: {df['timestamp'].max()}")
            logger.info(f"Requested start: {start_date}")
            logger.info(f"Requested end: {end_date}")

            # Filter to requested date range
            df = df[
                (df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)
            ]

            logger.info(f"Filtered to {len(df)} bars in date range")

            # Validate data
            is_valid, errors = self.validator.validate_ohlc(df)
            if not is_valid:
                result.errors.extend(errors)
                logger.error(f"Validation failed: {errors}")
                return result

            # Detect gaps
            gaps = self.validator.detect_gaps(df, expected_interval_minutes=15)
            result.gaps_detected = len(gaps)

            if gaps:
                logger.warning(f"Detected {len(gaps)} gaps in data")
                for gap_start, gap_end in gaps[:5]:  # Log first 5
                    logger.warning(f"  Gap: {gap_start} to {gap_end}")

            # Store to database
            bars_added, bars_skipped = self._store_to_database(session, df)

            result.bars_collected = bars_added
            result.bars_duplicates = bars_skipped
            result.success = True

            logger.info(
                f"Collection complete: {bars_added} new bars, "
                f"{bars_skipped} duplicates"
            )

            return result

        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"Collection failed: {e}", exc_info=True)
            return result

    def _store_to_database(
        self,
        session: Session,
        df: pd.DataFrame,
    ) -> Tuple[int, int]:
        """
        Store OHLC data to database with duplicate detection.

        Args:
            session: Database session
            df: DataFrame with OHLC data

        Returns:
            Tuple of (bars_added, bars_skipped)
        """
        bars_added = 0
        bars_skipped = 0

        for _, row in df.iterrows():
            # Check if bar already exists
            existing = session.query(MarketData).filter(
                MarketData.symbol == self.symbol,
                MarketData.timeframe == config.timeframe,
                MarketData.timestamp == row['timestamp'],
            ).first()

            if existing:
                bars_skipped += 1
                continue

            # Create new market data entry
            market_data = MarketData(
                symbol=self.symbol,
                timeframe=config.timeframe,
                timestamp=row['timestamp'],
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                tick_volume=int(row['tick_volume']),
                spread=float(row['spread']) if pd.notna(row.get('spread')) else None,
                real_volume=float(row['real_volume']) if pd.notna(row.get('real_volume')) else None,
            )

            session.add(market_data)
            bars_added += 1

            # Commit in batches
            if bars_added % 1000 == 0:
                session.commit()
                logger.debug(f"Committed {bars_added} bars")

        # Final commit
        session.commit()

        return bars_added, bars_skipped

    def get_coverage(self, session: Session) -> dict:
        """
        Get data coverage statistics.

        Args:
            session: Database session

        Returns:
            Dictionary with coverage statistics
        """
        from sqlalchemy import func

        stats = {
            'symbol': self.symbol,
            'timeframe': config.timeframe,
            'total_bars': 0,
            'oldest_bar': None,
            'newest_bar': None,
            'date_range_days': 0,
        }

        # Get count
        count = session.query(MarketData).filter(
            MarketData.symbol == self.symbol,
            MarketData.timeframe == config.timeframe,
        ).count()

        stats['total_bars'] = count

        if count == 0:
            return stats

        # Get oldest and newest
        oldest = session.query(MarketData).filter(
            MarketData.symbol == self.symbol,
            MarketData.timeframe == config.timeframe,
        ).order_by(MarketData.timestamp.asc()).first()

        newest = session.query(MarketData).filter(
            MarketData.symbol == self.symbol,
            MarketData.timeframe == config.timeframe,
        ).order_by(MarketData.timestamp.desc()).first()

        if oldest and newest:
            stats['oldest_bar'] = oldest.timestamp.isoformat()
            stats['newest_bar'] = newest.timestamp.isoformat()
            date_range = newest.timestamp - oldest.timestamp
            stats['date_range_days'] = date_range.days

        return stats

    def check_mt5_availability(self) -> Tuple[bool, str]:
        """
        Check if MT5 is available and connected.

        Returns:
            Tuple of (is_available, message)
        """
        if not self.mt5_client.check_connection():
            return False, "MT5 not connected"

        # Try to get symbol info
        symbol_info = self.mt5_client.get_symbol_info(self.symbol)
        if symbol_info is None:
            return False, f"Symbol {self.symbol} not available"

        return True, f"MT5 connected, {self.symbol} available"
