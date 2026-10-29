"""
Tests for forward testing components.
"""
import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pandas as pd
import torch

from scripts.forward_test import ForwardTester


class TestForwardTesterSetup(unittest.TestCase):
    """Test forward tester initialization."""

    @patch("scripts.forward_test.get_symbol_specs")
    @patch("scripts.forward_test.MT5Client")
    @patch("scripts.forward_test.AccountGuard")
    @patch("scripts.forward_test.torch.load")
    @patch("scripts.forward_test.pickle.load")
    def test_setup_with_valid_artifacts(
        self, mock_pickle, mock_torch_load, mock_guard, mock_mt5, mock_specs
    ):
        """Test setup with valid model and dataset."""
        # Mock dataset
        mock_scaler = Mock()
        mock_scaler.transform = Mock(return_value=np.random.randn(50, 28))

        mock_pickle.return_value = {
            "metadata": {
                "feature_columns": ["f0"] * 28,
                "sequence_length": 48,
            },
            "scaler": mock_scaler,
        }

        # Mock model checkpoint - real format uses "model_state" key.
        # PyTorch LSTM stores weights as (4*hidden_size, input_size);
        # hidden_size=64 => weight_ih_l0 is (256, 28).
        mock_state = {
            "lstm.weight_ih_l0": torch.zeros(256, 28),
            "lstm.weight_hh_l0": torch.zeros(256, 64),
            "lstm.bias_ih_l0": torch.zeros(256),
            "lstm.bias_hh_l0": torch.zeros(256),
            "lstm.weight_ih_l1": torch.zeros(256, 64),
            "lstm.weight_hh_l1": torch.zeros(256, 64),
            "lstm.bias_ih_l1": torch.zeros(256),
            "lstm.bias_hh_l1": torch.zeros(256),
            "fc.weight": torch.zeros(3, 64),
            "fc.bias": torch.zeros(3),
        }
        mock_torch_load.return_value = {"model_state": mock_state}

        # Mock MT5 client
        mock_mt5_instance = Mock()
        mock_mt5_instance.connect.return_value = True
        mock_mt5_instance.get_symbol_info.return_value = Mock(
            spread=5, volume_min=0.01, volume_step=0.01
        )
        mock_mt5.return_value = mock_mt5_instance

        # Mock broker symbol specs (real HFM XAUUSD values)
        mock_specs.return_value = Mock(
            symbol="XAUUSD",
            digits=2,
            point=0.01,
            trade_contract_size=100.0,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_stops_level=0,
            trade_freeze_level=8,
            filling_mode=1,
        )

        # Mock account guard
        mock_guard_instance = Mock()
        mock_verification = Mock()
        mock_verification.is_safe = True
        mock_verification.account_mode = Mock(name="DEMO")
        mock_verification.account_login = 123456
        mock_verification.account_server = "HFM-Demo"
        mock_verification.account_balance = 10000.0
        mock_verification.account_equity = 10000.0
        mock_verification.account_leverage = 500
        mock_verification.verification_time = datetime.utcnow()
        mock_verification.failure_reasons = []
        mock_guard_instance.verify_account.return_value = mock_verification
        mock_guard.return_value = mock_guard_instance

        tester = ForwardTester()

        # Should not raise
        with patch("scripts.forward_test.create_engine"):
            with patch("scripts.forward_test.Base"):
                result = tester.setup()

        self.assertTrue(result)
        self.assertIsNotNone(tester.scaler)
        self.assertIsNotNone(tester.feature_columns)
        self.assertEqual(tester.sequence_length, 48)
        self.assertIsNotNone(tester.model)

    def test_setup_without_model_fails(self):
        """Test that setup fails when model is missing."""
        tester = ForwardTester(model_path="nonexistent_model.pt")

        with patch("scripts.forward_test.create_engine"):
            with patch("scripts.forward_test.Base"):
                result = tester.setup()

        self.assertFalse(result)

    def test_setup_without_dataset_fails(self):
        """Test that setup fails when dataset is missing."""
        tester = ForwardTester(dataset_path="nonexistent_dataset.pkl")

        with patch("scripts.forward_test.create_engine"):
            with patch("scripts.forward_test.Base"):
                result = tester.setup()

        self.assertFalse(result)


class TestCandleProcessing(unittest.TestCase):
    """Test candle detection and duplicate prevention."""

    def test_duplicate_candle_not_processed(self):
        """Test that duplicate candles are not processed twice."""
        tester = ForwardTester()

        candle_time = datetime(2024, 1, 1, 12, 0)
        tester.processed_candles.add(candle_time)

        # Mock get_latest_completed_candle to return the same time
        with patch.object(
            tester, "_get_latest_completed_candle", return_value={"timestamp": candle_time}
        ):
            with patch.object(tester, "_fetch_feature_history") as mock_fetch:
                tester._process_cycle()
                # Should not fetch history since candle is duplicate
                mock_fetch.assert_not_called()

    def test_new_candle_triggers_processing(self):
        """Test that new candles trigger processing."""
        tester = ForwardTester()

        candle_time = datetime(2024, 1, 1, 12, 0)
        candle = {
            "timestamp": candle_time,
            "open": 2000.0,
            "high": 2010.0,
            "low": 1995.0,
            "close": 2005.0,
        }

        with patch.object(tester, "_get_latest_completed_candle", return_value=candle):
            with patch.object(
                tester, "_fetch_feature_history", return_value=None
            ) as mock_fetch:
                tester._process_cycle()
                # Should attempt to fetch history
                mock_fetch.assert_called_once_with(candle_time)


class TestSignalGeneration(unittest.TestCase):
    """Test signal generation logic."""

    def test_hold_signal_does_not_execute(self):
        """Test that HOLD signals don't trigger execution."""
        tester = ForwardTester()
        tester.signal_generator = Mock()

        mock_signal = Mock()
        mock_signal.signal = Mock(value="NEUTRAL")
        mock_signal.regime = "RANGE"
        mock_signal.confidence = 0.7
        mock_signal.timestamp = datetime.utcnow()
        mock_signal.features = {}

        tester.signal_generator.generate.return_value = mock_signal

        prediction = {
            "regime": "RANGE",
            "confidence": 0.7,
            "regime_probs": {"TREND": 0.2, "RANGE": 0.7, "HIGH_VOLATILITY": 0.1},
        }

        with patch.object(tester, "_save_signal_to_db"):
            result = tester._generate_signal(
                prediction,
                pd.Series({"returns": 0.001}),
                datetime.utcnow(),
                {"close": 2000.0},
            )

        self.assertIsNone(result)

    def test_low_confidence_rejected(self):
        """Test that low confidence signals are rejected."""
        tester = ForwardTester(confidence_threshold=0.7)
        tester.signal_generator = Mock()

        mock_signal = Mock()
        mock_signal.signal = Mock(value="LONG")
        mock_signal.regime = "TREND"
        mock_signal.confidence = 0.5  # Below threshold
        mock_signal.timestamp = datetime.utcnow()
        mock_signal.features = {}

        tester.signal_generator.generate.return_value = mock_signal

        prediction = {
            "regime": "TREND",
            "confidence": 0.5,
            "regime_probs": {"TREND": 0.5, "RANGE": 0.3, "HIGH_VOLATILITY": 0.2},
        }

        with patch.object(tester, "_save_signal_to_db"):
            result = tester._generate_signal(
                prediction,
                pd.Series({"returns": 0.001}),
                datetime.utcnow(),
                {"close": 2000.0},
            )

        self.assertIsNone(result)


class TestOrderExecution(unittest.TestCase):
    """Test order execution with safety checks."""

    def test_demo_verification_blocks_unsafe_account(self):
        """Test that unsafe account blocks execution."""
        tester = ForwardTester()
        tester.account_guard = Mock()

        # Mock unsafe verification
        tester.account_guard.verify_execution_safety.return_value = (
            False,
            "Live account detected",
        )

        signal_result = {
            "action": "BUY",
            "signal": Mock(timestamp=datetime.utcnow(), features={}),
        }

        with patch.object(tester, "_save_signal_to_db"):
            with patch.object(tester, "_submit_order") as mock_submit:
                tester._execute_trade(signal_result, {"close": 2000.0})
                # Should not submit order
                mock_submit.assert_not_called()

    def test_excessive_spread_blocks_execution(self):
        """Test that excessive spread blocks execution."""
        tester = ForwardTester(max_spread_pips=5.0)
        tester.account_guard = Mock()
        tester.account_guard.verify_execution_safety.return_value = (True, "OK")

        # Mock wide spread
        with patch("scripts.forward_test.mt5.symbol_info_tick") as mock_tick:
            mock_tick.return_value = Mock(ask=2010.0, bid=2000.0)

            with patch("scripts.forward_test.mt5.symbol_info") as mock_info:
                mock_info.return_value = Mock(
                    spread=60,  # 6 pips
                    point=0.01,
                    volume_min=0.01,
                    volume_step=0.01,
                )

                signal_result = {
                    "action": "BUY",
                    "signal": Mock(timestamp=datetime.utcnow(), features={}),
                }

                with patch.object(tester, "_save_signal_to_db"):
                    with patch.object(tester, "_submit_order") as mock_submit:
                        tester._execute_trade(signal_result, {"close": 2000.0})
                        # Should not submit order due to spread
                        mock_submit.assert_not_called()

    def test_risk_limit_blocks_execution(self):
        """Test that risk limits block execution."""
        tester = ForwardTester()
        tester.account_guard = Mock()
        tester.account_guard.verify_execution_safety.return_value = (True, "OK")
        tester.risk_manager = Mock()
        tester.risk_manager.can_open_trade.return_value = (False, "Max drawdown reached")

        with patch("scripts.forward_test.mt5.symbol_info_tick") as mock_tick:
            mock_tick.return_value = Mock(ask=2000.0, bid=2000.0)

            with patch("scripts.forward_test.mt5.symbol_info") as mock_info:
                mock_info.return_value = Mock(
                    spread=5,
                    point=0.01,
                    volume_min=0.01,
                    volume_step=0.01,
                )

                with patch("scripts.forward_test.mt5.account_info") as mock_account:
                    mock_account.return_value = Mock(balance=10000, equity=8500)

                    with patch("scripts.forward_test.mt5.positions_get") as mock_pos:
                        mock_pos.return_value = []

                        signal_result = {
                            "action": "BUY",
                            "signal": Mock(timestamp=datetime.utcnow(), features={}),
                        }

                        tester.session_start_equity = 10000
                        tester.session_high_water_mark = 10000

                        with patch.object(tester, "_save_signal_to_db"):
                            with patch.object(tester, "_submit_order") as mock_submit:
                                tester._execute_trade(signal_result, {"close": 2000.0})
                                # Should not submit order due to risk limit
                                mock_submit.assert_not_called()

    def test_dry_run_mode_prevents_execution(self):
        """Test that dry run mode prevents actual execution."""
        tester = ForwardTester(dry_run=True)
        tester.account_guard = Mock()
        tester.account_guard.verify_execution_safety.return_value = (True, "OK")
        tester.risk_manager = Mock()
        tester.risk_manager.can_open_trade.return_value = (True, "OK")
        tester.position_sizer = Mock()
        tester.position_sizer.calculate.return_value = Mock(
            lots=0.1,
            risk_amount=100.0,
            stop_distance_pips=20.0,
            position_value=20000.0,
        )

        with patch("scripts.forward_test.mt5.symbol_info_tick") as mock_tick:
            mock_tick.return_value = Mock(ask=2000.0, bid=2000.0)

            with patch("scripts.forward_test.mt5.symbol_info") as mock_info:
                mock_info.return_value = Mock(
                    spread=5,
                    point=0.01,
                    volume_min=0.01,
                    volume_max=10.0,
                    volume_step=0.01,
                )

                with patch("scripts.forward_test.mt5.account_info") as mock_account:
                    mock_account.return_value = Mock(balance=10000, equity=10000)

                    with patch("scripts.forward_test.mt5.positions_get") as mock_pos:
                        mock_pos.return_value = []

                        signal_result = {
                            "action": "BUY",
                            "signal": Mock(
                                timestamp=datetime.utcnow(),
                                confidence=0.8,
                                regime="TREND",
                                features={},
                            ),
                        }

                        tester.session_start_equity = 10000
                        tester.session_high_water_mark = 10000

                        with patch.object(tester, "_save_signal_to_db", return_value=1):
                            with patch.object(tester, "_submit_order") as mock_submit:
                                tester._execute_trade(signal_result, {"close": 2000.0, "timestamp": datetime.utcnow()})
                                # Should not submit order in dry run mode
                                mock_submit.assert_not_called()


class TestFeatureProcessing(unittest.TestCase):
    """Test feature computation and model input preparation."""

    def test_prepare_model_input_with_valid_features(self):
        """Test model input preparation with valid features."""
        tester = ForwardTester()
        tester.feature_columns = ["returns", "atr", "rsi"]
        tester.sequence_length = 10
        tester.scaler = Mock()
        tester.scaler.transform.return_value = np.random.randn(50, 3)

        # Create mock feature dataframe
        features_df = pd.DataFrame(
            np.random.randn(50, 3), columns=["returns", "atr", "rsi"]
        )

        result = tester._prepare_model_input(features_df)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, torch.Tensor)
        self.assertEqual(result.shape, (1, 10, 3))

    def test_prepare_model_input_insufficient_history(self):
        """Test that insufficient history returns None."""
        tester = ForwardTester()
        tester.feature_columns = ["returns", "atr", "rsi"]
        tester.sequence_length = 50
        tester.scaler = Mock()

        # Only 10 rows, but need 50
        features_df = pd.DataFrame(
            np.random.randn(10, 3), columns=["returns", "atr", "rsi"]
        )

        result = tester._prepare_model_input(features_df)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
