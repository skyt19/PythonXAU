"""Generate synthetic XAUUSD data for testing"""
import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def generate_realistic_gold_data(start_date, end_date, base_price=2000.0):
    """Generate synthetic but realistic XAUUSD M15 data."""
    timestamps = pd.date_range(start=start_date, end=end_date, freq='15min')
    timestamps = timestamps[timestamps.weekday < 5]  # Mon-Fri only

    n = len(timestamps)
    logger.info(f"Generating {n} M15 bars from {start_date} to {end_date}")

    # Random walk with realistic parameters
    np.random.seed(42)

    # Daily trend component
    daily_returns = np.random.normal(0, 0.008, size=len(timestamps)//96 + 1)
    daily_trend = np.repeat(daily_returns, 96)[:n]

    # Intraday noise
    intraday_returns = np.random.normal(0, 0.002, size=n)

    # Combine
    returns = daily_trend + intraday_returns
    price = base_price * np.exp(np.cumsum(returns))

    # Generate OHLC
    data = []
    for i, ts in enumerate(timestamps):
        open_price = price[i]
        high = open_price * (1 + abs(np.random.normal(0, 0.001)))
        low = open_price * (1 - abs(np.random.normal(0, 0.001)))
        close = np.random.uniform(low, high)
        volume = np.random.randint(50, 500)

        data.append({
            'timestamp': ts,
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'tick_volume': volume,
        })

    return pd.DataFrame(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=365, help='Days of data to generate')
    parser.add_argument('--output', type=str, default='data/xauusd.db', help='Output database')

    args = parser.parse_args()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)

    df = generate_realistic_gold_data(start_date, end_date)

    # Save to database
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(output_path)
    df.to_sql('ohlc', conn, if_exists='replace', index=False)
    conn.close()

    logger.info(f"Generated {len(df)} bars")
    logger.info(f"Saved to {output_path}")
    logger.info(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")


if __name__ == '__main__':
    main()
