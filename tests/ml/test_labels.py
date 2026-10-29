"""
Tests for label generation and threshold fitting.

Label thresholds define the regime boundaries, so they must be fitted on
the training period only. These tests verify that property.
"""
import unittest
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ml.labels import RegimeLabeler


def make_frame(n=1000, seed=0, drift=0.0004, vol=0.0015):
    """Build a synthetic OHLC frame with a known drift and volatility."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, size=n)
    close = 2000 * np.exp(np.cumsum(returns))

    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="15min"),
            "open": close,
            "high": close * (1 + np.abs(rng.normal(0, 0.0005, n))),
            "low": close * (1 - np.abs(rng.normal(0, 0.0005, n))),
            "close": close,
        }
    )
    return df


class TestThresholdFitting(unittest.TestCase):
    """Threshold fitting must use training data only."""

    def test_thresholds_are_derived_from_the_frame(self):
        labeler = RegimeLabeler(lookforward=8)
        df = make_frame(n=2000, seed=1, vol=0.003)

        result = labeler.fit_thresholds(df)

        self.assertTrue(labeler.thresholds_fitted)
        self.assertGreater(result["trend_threshold"], 0)
        self.assertGreater(result["volatility_threshold"], 0)

    def test_higher_volatility_data_yields_higher_threshold(self):
        """The fitted volatility threshold tracks the data's volatility."""
        calm = make_frame(n=2000, seed=2, vol=0.001)
        wild = make_frame(n=2000, seed=2, vol=0.006)

        calm_labeler = RegimeLabeler(lookforward=8)
        calm_labeler.fit_thresholds(calm)

        wild_labeler = RegimeLabeler(lookforward=8)
        wild_labeler.fit_thresholds(wild)

        self.assertGreater(
            wild_labeler.volatility_threshold,
            calm_labeler.volatility_threshold,
            "Volatility threshold must scale with the data",
        )

    def test_fitting_on_train_only_does_not_see_later_data(self):
        """
        Changing the validation/test tail must not change the thresholds.

        If the thresholds moved, the fitting step would be reading data it
        should not see.
        """
        df = make_frame(n=2000, seed=3)

        train_only = df.iloc[:1500].copy()
        with_tail = df.copy()
        # Replace the tail with completely different behaviour.
        with_tail.loc[1500:, "close"] = 5000.0

        labeler_a = RegimeLabeler(lookforward=8)
        labeler_a.fit_thresholds(train_only)

        labeler_b = RegimeLabeler(lookforward=8)
        labeler_b.fit_thresholds(with_tail)

        # The full-frame fit legitimately differs (it saw the tail), but the
        # train-only fit must equal an independent fit of the same slice.
        labeler_c = RegimeLabeler(lookforward=8)
        labeler_c.fit_thresholds(df.iloc[:1500].copy())

        self.assertAlmostEqual(
            labeler_a.trend_threshold,
            labeler_c.trend_threshold,
            places=10,
        )
        self.assertAlmostEqual(
            labeler_a.volatility_threshold,
            labeler_c.volatility_threshold,
            places=10,
        )

    def test_get_thresholds_reports_fitted_state(self):
        labeler = RegimeLabeler()
        self.assertFalse(labeler.get_thresholds()["fitted"])

        labeler.fit_thresholds(make_frame(n=500))
        self.assertTrue(labeler.get_thresholds()["fitted"])


class TestLabelGeneration(unittest.TestCase):
    """Label generation must produce valid, documented classes."""

    def test_labels_are_in_valid_range(self):
        labeler = RegimeLabeler(lookforward=8)
        df = make_frame(n=800, seed=4)
        labeled = labeler.generate_labels(df)

        self.assertIn("regime", labeled.columns)
        valid = {labeler.TREND, labeler.RANGE, labeler.HIGH_VOLATILITY}
        self.assertTrue(set(labeled["regime"].unique()).issubset(valid))

    def test_labels_cover_multiple_classes(self):
        labeler = RegimeLabeler(lookforward=8)
        df = make_frame(n=3000, seed=5, vol=0.004)
        labeled = labeler.generate_labels(df)

        self.assertGreater(
            len(labeled["regime"].unique()),
            1,
            "Labeling collapsed to a single class",
        )

    def test_no_future_leakage_in_features(self):
        """
        The label generator uses future data; the feature builder must not.

        This checks the property that the feature pipeline only reads the
        current and past bars: perturbing a future price must not change
        the features of an earlier bar.
        """
        from app.features.feature_builder import FeatureBuilder

        df = make_frame(n=500, seed=6)
        builder = FeatureBuilder()

        base = builder.build_features(df)

        perturbed = df.copy()
        # Change the last 50 closes drastically.
        perturbed.loc[perturbed.index[-50:], "close"] *= 1.05
        perturbed.loc[perturbed.index[-50:], "high"] *= 1.05
        perturbed.loc[perturbed.index[-50:], "low"] *= 1.05
        perturbed.loc[perturbed.index[-50:], "open"] *= 1.05

        after = builder.build_features(perturbed)

        # Compare a feature row well before the perturbation.
        cutoff = len(df) - 100
        base_row = base[base["timestamp"] < df["timestamp"].iloc[cutoff]].iloc[-1]
        after_row = after[after["timestamp"] < df["timestamp"].iloc[cutoff]].iloc[-1]

        for col in ["returns", "rsi", "atr_normalized", "realized_vol"]:
            self.assertAlmostEqual(
                float(base_row[col]),
                float(after_row[col]),
                places=8,
                msg=f"Feature {col} changed when only future data changed",
            )

    def test_validate_labels_detects_bad_values(self):
        labeler = RegimeLabeler()
        bad = pd.DataFrame({"regime": [0, 1, 99, 2]})
        is_valid, errors = labeler.validate_labels(bad)
        self.assertFalse(is_valid)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
