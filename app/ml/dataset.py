"""
Dataset Builder - Chronological Train/Val/Test Splits

Creates PyTorch datasets with proper time-series handling.
No look-ahead bias, no future leakage.
"""
import logging
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class TimeSeriesDataset(Dataset):
    """PyTorch dataset for time series with sequences."""

    def __init__(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        sequence_length: int,
    ):
        """
        Initialize dataset.

        Args:
            features: Feature array [samples, features]
            labels: Label array [samples]
            sequence_length: Length of input sequences
        """
        self.features = torch.FloatTensor(features)
        self.labels = torch.LongTensor(labels)
        self.sequence_length = sequence_length

        # Validate
        if len(self.features) != len(self.labels):
            raise ValueError(
                f"Features ({len(self.features)}) and labels ({len(self.labels)}) length mismatch"
            )

    def __len__(self) -> int:
        """Dataset length."""
        # Subtract sequence length to ensure we can form complete sequences
        return max(0, len(self.features) - self.sequence_length + 1)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get item by index.

        Returns:
            Tuple of (sequence, label) where sequence is [seq_len, features]
        """
        # Get sequence
        sequence = self.features[idx : idx + self.sequence_length]

        # Get label (for the last time step)
        label = self.labels[idx + self.sequence_length - 1]

        return sequence, label


class DatasetBuilder:
    """Build train/val/test datasets with chronological splits."""

    def __init__(
        self,
        sequence_length: int = 64,
        val_split: float = 0.15,
        test_split: float = 0.15,
    ):
        """
        Initialize dataset builder.

        Args:
            sequence_length: Length of input sequences
            val_split: Fraction for validation (from end of train)
            test_split: Fraction for test (from end of data)
        """
        self.sequence_length = sequence_length
        self.val_split = val_split
        self.test_split = test_split

        self.scaler: Optional[StandardScaler] = None
        self.feature_names: Optional[list] = None

        logger.info(
            f"DatasetBuilder: seq_len={sequence_length}, "
            f"val={val_split:.1%}, test={test_split:.1%}"
        )

    def build_datasets(
        self,
        df: pd.DataFrame,
        feature_columns: list,
        label_column: str = 'regime',
    ) -> Tuple[TimeSeriesDataset, TimeSeriesDataset, TimeSeriesDataset, dict]:
        """
        Build train, validation, and test datasets.

        Uses chronological splits:
        - Test: Last test_split fraction
        - Val: Last val_split fraction of remaining
        - Train: Rest

        Args:
            df: DataFrame with features and labels
            feature_columns: List of feature column names
            label_column: Name of label column

        Returns:
            Tuple of (train_dataset, val_dataset, test_dataset, metadata)
        """
        if df.empty:
            raise ValueError("Empty DataFrame")

        # Check columns exist
        missing = [col for col in feature_columns if col not in df.columns]
        if missing:
            raise ValueError(f"Missing feature columns: {missing}")

        if label_column not in df.columns:
            raise ValueError(f"Missing label column: {label_column}")

        logger.info(f"Building datasets from {len(df)} samples")

        # Sort by timestamp if available
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp').reset_index(drop=True)

        # Extract features and labels
        features = df[feature_columns].values
        labels = df[label_column].values

        # Calculate split indices
        total_samples = len(features)
        test_size = int(total_samples * self.test_split)
        val_size = int((total_samples - test_size) * self.val_split)
        train_size = total_samples - test_size - val_size

        # Chronological splits
        train_features = features[:train_size]
        train_labels = labels[:train_size]

        val_features = features[train_size : train_size + val_size]
        val_labels = labels[train_size : train_size + val_size]

        test_features = features[train_size + val_size :]
        test_labels = labels[train_size + val_size :]

        logger.info(
            f"Split sizes: train={train_size}, val={val_size}, test={test_size}"
        )

        # Fit scaler on training data ONLY
        self.scaler = StandardScaler()
        self.scaler.fit(train_features)

        # Transform all splits
        train_features_scaled = self.scaler.transform(train_features)
        val_features_scaled = self.scaler.transform(val_features)
        test_features_scaled = self.scaler.transform(test_features)

        # Create datasets
        train_dataset = TimeSeriesDataset(
            train_features_scaled,
            train_labels,
            self.sequence_length,
        )

        val_dataset = TimeSeriesDataset(
            val_features_scaled,
            val_labels,
            self.sequence_length,
        )

        test_dataset = TimeSeriesDataset(
            test_features_scaled,
            test_labels,
            self.sequence_length,
        )

        # Metadata
        metadata = {
            'total_samples': total_samples,
            'train_size': train_size,
            'val_size': val_size,
            'test_size': test_size,
            'sequence_length': self.sequence_length,
            'feature_columns': feature_columns,
            'label_column': label_column,
            'scaler_mean': self.scaler.mean_.tolist(),
            'scaler_std': self.scaler.scale_.tolist(),
        }

        # Add date ranges if available
        if 'timestamp' in df.columns:
            metadata['train_start'] = df.iloc[0]['timestamp'].isoformat()
            metadata['train_end'] = df.iloc[train_size - 1]['timestamp'].isoformat()
            metadata['val_start'] = df.iloc[train_size]['timestamp'].isoformat()
            metadata['val_end'] = df.iloc[train_size + val_size - 1]['timestamp'].isoformat()
            metadata['test_start'] = df.iloc[train_size + val_size]['timestamp'].isoformat()
            metadata['test_end'] = df.iloc[-1]['timestamp'].isoformat()

        logger.info("Datasets created successfully")
        logger.info(f"Train sequences: {len(train_dataset)}")
        logger.info(f"Val sequences: {len(val_dataset)}")
        logger.info(f"Test sequences: {len(test_dataset)}")

        return train_dataset, val_dataset, test_dataset, metadata

    def get_scaler(self) -> Optional[StandardScaler]:
        """Get the fitted scaler."""
        return self.scaler
