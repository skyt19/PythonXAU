"""Build ML dataset from collected OHLC data"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.features.feature_builder import FeatureBuilder
from app.ml.labels import RegimeLabeler
from app.ml.dataset import DatasetBuilder, save_datasets

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=str, default='data/xauusd.db', help='Database path')
    parser.add_argument('--output', type=str, default='data/dataset.pkl', help='Output dataset path')
    parser.add_argument('--sequence-length', type=int, default=48, help='Sequence length (default 48=12h)')
    parser.add_argument('--train-ratio', type=float, default=0.7)
    parser.add_argument('--val-ratio', type=float, default=0.15)

    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        logger.error("Run: python scripts/collect_data.py --days 365")
        sys.exit(1)

    # Load OHLC data
    logger.info(f"Loading data from {db_path}")
    import sqlite3
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM ohlc ORDER BY timestamp", conn)
    conn.close()

    if len(df) == 0:
        logger.error("No data in database")
        sys.exit(1)

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    logger.info(f"Loaded {len(df)} bars from {df['timestamp'].min()} to {df['timestamp'].max()}")

    # Build features
    logger.info("Building features...")
    feature_builder = FeatureBuilder()
    df_features = feature_builder.build_features(df)

    logger.info(f"Built {len(df_features.columns)-1} features")  # -1 for timestamp

    # Generate labels
    logger.info("Generating regime labels...")
    labeler = RegimeLabeler()
    df_labels = labeler.generate_labels(df_features)

    logger.info("Class distribution:")
    for label, count in df_labels['regime'].value_counts().items():
        logger.info(f"  {label}: {count} ({count/len(df_labels)*100:.1f}%)")

    # Build datasets
    logger.info("Creating train/val/test splits...")
    builder = DatasetBuilder(
        sequence_length=args.sequence_length,
        val_split=args.val_ratio,
        test_split=1.0 - args.train_ratio - args.val_ratio,
    )

    feature_cols = feature_builder.get_feature_columns()
    train_dataset, val_dataset, test_dataset, metadata = builder.build_datasets(
        df_labels, feature_cols
    )

    # Package everything
    datasets = {
        'train_dataset': train_dataset,
        'val_dataset': val_dataset,
        'test_dataset': test_dataset,
        'train': {
            'X': train_dataset.features,
            'y': train_dataset.labels,
            'feature_names': feature_cols,
        },
        'val': {
            'X': val_dataset.features,
            'y': val_dataset.labels,
            'feature_names': feature_cols,
        },
        'test': {
            'X': test_dataset.features,
            'y': test_dataset.labels,
            'feature_names': feature_cols,
        },
        'metadata': metadata,
        'scaler': builder.get_scaler(),
    }

    # Save
    output_path = Path(args.output)
    save_datasets(datasets, output_path)

    logger.info("\nDataset created successfully")
    logger.info(f"Saved to: {output_path}")
    logger.info(f"Train sequences: {len(train_dataset)}")
    logger.info(f"Val sequences: {len(val_dataset)}")
    logger.info(f"Test sequences: {len(test_dataset)}")


if __name__ == '__main__':
    main()
