"""
Historical Data Collection Script

Collects XAUUSD M15 historical data from HFM MT5 Demo account.

Usage:
    python scripts/collect_data.py --days 365
    python scripts/collect_data.py --start 2024-01-01 --end 2024-12-31
    python scripts/collect_data.py --check

This script is READ-ONLY. It does not submit orders.
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.broker.mt5_client import MT5Client
from app.config import config
from app.data.collector import DataCollector
from app.data.validator import DataValidator
from app.database import DatabaseManager
from app.logging_config import setup_logging

# Setup logging
setup_logging(log_level="INFO", log_file=Path("logs/data_collection.log"))
logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> datetime:
    """Parse date string to datetime."""
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD or ISO format.")


def main():
    """Main collection routine."""
    parser = argparse.ArgumentParser(
        description="Collect historical XAUUSD M15 data from MT5"
    )
    parser.add_argument(
        "--days",
        type=int,
        help="Number of days to collect (from today backwards)"
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check MT5 availability and data coverage only"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Symbol to collect (default: from config)"
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("XAUUSD Historical Data Collection")
    logger.info("=" * 70)
    logger.info(f"Symbol: {args.symbol or config.mt5_symbol}")
    logger.info(f"Timeframe: {config.timeframe}")
    logger.info(f"Server: {config.mt5_server}")
    logger.info("=" * 70)

    # Initialize components
    logger.info("Initializing components...")

    # Database
    db_manager = DatabaseManager(config.database_url)
    db_manager.create_tables()
    session = db_manager.get_session()

    # MT5 Client
    mt5_client = MT5Client()

    # Check MT5 credentials
    if not config.mt5_login or not config.mt5_password:
        logger.warning("MT5 credentials not configured in .env")
        logger.info("Set MT5_LOGIN and MT5_PASSWORD in .env file")

        if args.check:
            logger.info("Running in check mode without MT5 connection")
        else:
            logger.error("Cannot collect data without MT5 credentials")
            return 1

    # Try to connect to MT5
    if config.mt5_login and config.mt5_password:
        logger.info("Connecting to MT5...")
        connected = mt5_client.connect(
            login=int(config.mt5_login) if config.mt5_login.isdigit() else None,
            password=config.mt5_password,
            server=config.mt5_server,
        )

        if not connected:
            logger.error("Failed to connect to MT5")
            if not args.check:
                logger.error("Collection aborted")
                return 1
    else:
        connected = False

    # Initialize collector
    validator = DataValidator(staleness_threshold_seconds=config.data_staleness_threshold)
    collector = DataCollector(
        mt5_client=mt5_client,
        validator=validator,
        symbol=args.symbol,
    )

    # Check mode
    if args.check:
        logger.info("\n" + "=" * 70)
        logger.info("MT5 AVAILABILITY CHECK")
        logger.info("=" * 70)

        if connected:
            is_available, message = collector.check_mt5_availability()
            logger.info(f"MT5 Status: {message}")

            if is_available:
                logger.info("✓ MT5 is available for data collection")
            else:
                logger.warning("✗ MT5 is not ready for data collection")
        else:
            logger.warning("✗ MT5 not connected")

        logger.info("\n" + "=" * 70)
        logger.info("DATA COVERAGE")
        logger.info("=" * 70)

        coverage = collector.get_coverage(session)
        logger.info(f"Symbol: {coverage['symbol']}")
        logger.info(f"Timeframe: {coverage['timeframe']}")
        logger.info(f"Total Bars: {coverage['total_bars']:,}")

        if coverage['total_bars'] > 0:
            logger.info(f"Oldest Bar: {coverage['oldest_bar']}")
            logger.info(f"Newest Bar: {coverage['newest_bar']}")
            logger.info(f"Date Range: {coverage['date_range_days']} days")
        else:
            logger.info("No data collected yet")

        logger.info("=" * 70)
        return 0

    # Collection mode
    if not connected:
        logger.error("MT5 not connected. Cannot collect data.")
        return 1

    # Validate arguments
    if args.days is None and (args.start is None or args.end is None):
        logger.error("Must specify either --days or both --start and --end")
        return 1

    logger.info("\n" + "=" * 70)
    logger.info("STARTING DATA COLLECTION")
    logger.info("=" * 70)

    try:
        # Collect data
        if args.days:
            logger.info(f"Collecting last {args.days} days...")
            result = collector.collect_historical(
                session=session,
                days=args.days,
            )
        else:
            start_date = parse_date(args.start)
            end_date = parse_date(args.end)
            logger.info(f"Collecting from {start_date} to {end_date}...")
            result = collector.collect_historical(
                session=session,
                start_date=start_date,
                end_date=end_date,
            )

        # Print results
        logger.info("\n" + "=" * 70)
        logger.info("COLLECTION RESULTS")
        logger.info("=" * 70)
        logger.info(str(result))

        if result.success:
            logger.info("\n✓ Data collection completed successfully")

            # Show updated coverage
            coverage = collector.get_coverage(session)
            logger.info(f"\nTotal bars in database: {coverage['total_bars']:,}")
            logger.info(f"Date range: {coverage['date_range_days']} days")

            return 0
        else:
            logger.error("\n✗ Data collection failed")
            return 1

    except KeyboardInterrupt:
        logger.warning("\nCollection interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"\nCollection error: {e}", exc_info=True)
        return 1
    finally:
        # Cleanup
        mt5_client.disconnect()
        session.close()
        db_manager.close()


if __name__ == "__main__":
    sys.exit(main())
