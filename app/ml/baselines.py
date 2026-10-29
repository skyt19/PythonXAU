"""
Baseline Models - Simple Non-Neural Classifiers

Establishes performance baselines that LSTM must exceed to be useful.
"""
import logging
from typing import Dict

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix

logger = logging.getLogger(__name__)


class MajorityClassBaseline:
    """Always predict the most common class."""

    def __init__(self):
        self.majority_class = None
        self.class_counts = None

    def fit(self, y_train: np.ndarray):
        """
        Fit by finding majority class.

        Args:
            y_train: Training labels
        """
        unique, counts = np.unique(y_train, return_counts=True)
        self.class_counts = dict(zip(unique, counts))
        self.majority_class = unique[np.argmax(counts)]

        logger.info(f"Majority class: {self.majority_class}")
        logger.info(f"Class distribution: {self.class_counts}")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict majority class for all samples.

        Args:
            X: Features (ignored)

        Returns:
            Predictions (all same class)
        """
        if self.majority_class is None:
            raise ValueError("Model not fitted")

        return np.full(len(X), self.majority_class)


class SimpleRuleBaseline:
    """
    Simple rule-based classifier using obvious signals.

    Rules:
    - HIGH_VOLATILITY if ATR > threshold
    - TREND if strong directional move
    - RANGE otherwise
    """

    # Regime classes (must match labels.py)
    TREND = 0
    RANGE = 1
    HIGH_VOLATILITY = 2

    def __init__(
        self,
        atr_threshold: float = 0.008,  # 0.8% ATR
        trend_threshold: float = 0.005,  # 0.5% return
    ):
        """
        Initialize rule-based classifier.

        Args:
            atr_threshold: ATR threshold for high volatility
            trend_threshold: Return threshold for trend
        """
        self.atr_threshold = atr_threshold
        self.trend_threshold = trend_threshold

        self.feature_indices = None
        self.fitted = False

    def fit(self, X_train: np.ndarray, feature_names: list):
        """
        Store feature indices.

        Args:
            X_train: Training features
            feature_names: List of feature names
        """
        # Find required feature indices
        try:
            self.atr_idx = feature_names.index('atr_normalized')
            self.returns_idx = feature_names.index('returns')
        except ValueError as e:
            raise ValueError(f"Required features not found: {e}")

        self.fitted = True
        logger.info("SimpleRuleBaseline fitted")
        logger.info(f"  ATR threshold: {self.atr_threshold:.1%}")
        logger.info(f"  Trend threshold: {self.trend_threshold:.1%}")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict using simple rules.

        Args:
            X: Features

        Returns:
            Predictions
        """
        if not self.fitted:
            raise ValueError("Model not fitted")

        predictions = np.full(len(X), self.RANGE, dtype=int)

        # Extract features
        atr = X[:, self.atr_idx]
        returns = X[:, self.returns_idx]

        # HIGH_VOLATILITY: High ATR
        high_vol_mask = atr > self.atr_threshold
        predictions[high_vol_mask] = self.HIGH_VOLATILITY

        # TREND: Strong directional move and not high volatility
        trend_mask = (np.abs(returns) > self.trend_threshold) & ~high_vol_mask
        predictions[trend_mask] = self.TREND

        # RANGE: Default (already set)

        return predictions


class BaselineEvaluator:
    """Evaluate baseline model performance."""

    def __init__(self):
        self.class_names = ['TREND', 'RANGE', 'HIGH_VOLATILITY']

    def evaluate(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        model_name: str = "Model",
    ) -> Dict:
        """
        Evaluate predictions.

        Args:
            y_true: True labels
            y_pred: Predicted labels
            model_name: Name for logging

        Returns:
            Dictionary of metrics
        """
        # Overall accuracy
        accuracy = accuracy_score(y_true, y_pred)

        # Per-class metrics
        precision, recall, f1, support = precision_recall_fscore_support(
            y_true,
            y_pred,
            average=None,
            zero_division=0,
        )

        # Macro averages
        precision_macro = np.mean(precision)
        recall_macro = np.mean(recall)
        f1_macro = np.mean(f1)

        # Confusion matrix
        cm = confusion_matrix(y_true, y_pred)

        # Log results
        logger.info(f"\n{'='*60}")
        logger.info(f"{model_name} Performance")
        logger.info(f"{'='*60}")
        logger.info(f"Overall Accuracy: {accuracy:.4f}")
        logger.info(f"Macro Precision:  {precision_macro:.4f}")
        logger.info(f"Macro Recall:     {recall_macro:.4f}")
        logger.info(f"Macro F1:         {f1_macro:.4f}")
        logger.info(f"\nPer-Class Metrics:")

        for i, class_name in enumerate(self.class_names):
            logger.info(
                f"  {class_name:15s} - "
                f"P: {precision[i]:.4f}, "
                f"R: {recall[i]:.4f}, "
                f"F1: {f1[i]:.4f}, "
                f"Support: {support[i]}"
            )

        logger.info(f"\nConfusion Matrix:")
        logger.info(f"{'':15s} " + " ".join([f"{c:>12s}" for c in self.class_names]))
        for i, row in enumerate(cm):
            logger.info(f"{self.class_names[i]:15s} " + " ".join([f"{v:12d}" for v in row]))

        logger.info(f"{'='*60}\n")

        # Return metrics
        metrics = {
            'accuracy': float(accuracy),
            'precision_macro': float(precision_macro),
            'recall_macro': float(recall_macro),
            'f1_macro': float(f1_macro),
            'precision_per_class': precision.tolist(),
            'recall_per_class': recall.tolist(),
            'f1_per_class': f1.tolist(),
            'support_per_class': support.tolist(),
            'confusion_matrix': cm.tolist(),
        }

        return metrics
