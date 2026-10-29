"""
Safety tests for the forward-testing execution path.

These cover the gates that must block an order from reaching the broker.
All MT5 interactions are mocked; no broker order is ever sent.
"""
import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import MetaTrader5 as mt5

from app.risk.position_sizing import PositionSizer
from scripts.forward_test import ForwardTester, _json_safe


class TestPositionSizerNoRoundUp(unittest.TestCase):
    """The risk budget must never be exceeded by rounding up to broker min."""

    def test_min_lot_above_budget_is_rejected(self):
        """A minimum lot that exceeds the risk budget must be rejected."""
        sizer = PositionSizer(
            max_risk_per_trade=0.01,
            min_lots=0.01,
            pip_value_per_lot=10.0,
            volume_step=0.01,
        )

        # $64.07 balance, 1% risk = $0.64 budget.
        # 0.01 lot over an 803 pip stop risks $80.30 -> must be rejected.
        result = sizer.calculate(
            balance=64.07,
            entry_price=4010.18,
            stop_loss_price=3930.0,
            confidence=1.0,
        )

        self.assertIsNone(result, "Trade must be rejected, not rounded up")

    def test_sufficient_balance_allows_trade(self):
        """A funded account can size a trade within budget."""
        sizer = PositionSizer(
            max_risk_per_trade=0.01,
            min_lots=0.01,
            pip_value_per_lot=10.0,
            volume_step=0.01,
        )

        # $100,000 balance, 1% = $1,000 budget, 803 pip stop.
        # 1000 / (803 * 10) = 0.124 lots -> 0.12 lots after step rounding.
        result = sizer.calculate(
            balance=100000.0,
            entry_price=4010.18,
            stop_loss_price=3930.0,
            confidence=1.0,
        )

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.lots, 0.12, places=4)
        # Actual risk must not exceed the budget.
        actual_risk = result.lots * result.stop_distance_pips * 10.0
        self.assertLessEqual(actual_risk, result.risk_amount + 1e-6)

    def test_volume_never_rounds_up_past_budget(self):
        """Across a range of balances the sized volume stays in budget."""
        sizer = PositionSizer(
            max_risk_per_trade=0.02,
            min_lots=0.01,
            pip_value_per_lot=10.0,
            volume_step=0.01,
        )

        for balance in [100.0, 500.0, 1000.0, 5000.0, 25000.0, 100000.0]:
            result = sizer.calculate(
                balance=balance,
                entry_price=4010.18,
                stop_loss_price=3930.0,
                confidence=1.0,
            )
            if result is None:
                continue  # rejected is a valid outcome
            actual_risk = result.lots * result.stop_distance_pips * 10.0
            self.assertLessEqual(
                actual_risk,
                balance * 0.02 + 1e-6,
                f"Risk breached at balance {balance}",
            )


class TestFillingModeResolution(unittest.TestCase):
    """Filling mode must come from broker metadata."""

    def test_respects_fok_support(self):
        tester = ForwardTester()
        info = Mock(filling_mode=mt5.ORDER_FILLING_FOK)
        self.assertEqual(tester._resolve_filling_mode(info), mt5.ORDER_FILLING_FOK)

    def test_respects_ioc_support(self):
        tester = ForwardTester()
        info = Mock(filling_mode=mt5.ORDER_FILLING_IOC)
        self.assertEqual(tester._resolve_filling_mode(info), mt5.ORDER_FILLING_IOC)

    def test_respects_return_support(self):
        tester = ForwardTester()
        info = Mock(filling_mode=mt5.ORDER_FILLING_RETURN)
        self.assertEqual(tester._resolve_filling_mode(info), mt5.ORDER_FILLING_RETURN)


class TestJsonSafety(unittest.TestCase):
    """Feature snapshots must be JSON serializable."""

    def test_numpy_and_timestamp_values_converted(self):
        import numpy as np
        import pandas as pd

        snapshot = {
            "returns": np.float64(0.0012),
            "rsi": np.int64(55),
            "timestamp": pd.Timestamp("2024-01-01 12:00:00"),
            "label": "TREND",
            "flag": True,
        }

        safe = _json_safe(snapshot)

        for value in safe.values():
            self.assertIsInstance(value, (str, int, float, bool, type(None)))

    def test_unserializable_values_are_dropped(self):
        class Weird:
            def item(self):
                raise ValueError("nope")

        safe = _json_safe({"ok": 1, "bad": Weird()})
        self.assertIn("ok", safe)
        self.assertNotIn("bad", safe)


class TestOrderPreflightValidation(unittest.TestCase):
    """order_check must gate the actual order_send."""

    def test_failed_order_check_blocks_send(self):
        tester = ForwardTester()

        with patch("scripts.forward_test.mt5.symbol_info") as mock_info:
            mock_info.return_value = Mock(
                name="XAUUSD",
                filling_mode=mt5.ORDER_FILLING_IOC,
            )
            with patch("scripts.forward_test.mt5.symbol_info_tick") as mock_tick:
                mock_tick.return_value = Mock(ask=4011.0, bid=4010.5)
                with patch("scripts.forward_test.mt5.order_check") as mock_check:
                    mock_check.return_value = Mock(
                        retcode=mt5.TRADE_RETCODE_ERROR,
                        comment="Not enough money",
                    )
                    with patch("scripts.forward_test.mt5.order_send") as mock_send:
                        result = tester._submit_order(
                            action="BUY",
                            volume=0.01,
                            stop_loss=3990.0,
                            take_profit=4050.0,
                        )

        self.assertIsNone(result)
        mock_send.assert_not_called()

    def test_successful_order_check_allows_send(self):
        tester = ForwardTester()

        with patch("scripts.forward_test.mt5.symbol_info") as mock_info:
            mock_info.return_value = Mock(
                name="XAUUSD",
                filling_mode=mt5.ORDER_FILLING_IOC,
            )
            with patch("scripts.forward_test.mt5.symbol_info_tick") as mock_tick:
                mock_tick.return_value = Mock(ask=4011.0, bid=4010.5)
                with patch("scripts.forward_test.mt5.order_check") as mock_check:
                    mock_check.return_value = Mock(
                        retcode=mt5.TRADE_RETCODE_DONE,
                        margin=10.0,
                        margin_free=100.0,
                    )
                    with patch("scripts.forward_test.mt5.order_send") as mock_send:
                        mock_send.return_value = Mock(
                            retcode=mt5.TRADE_RETCODE_DONE,
                            order=12345,
                            deal=67890,
                            price=4011.0,
                            volume=0.01,
                        )
                        result = tester._submit_order(
                            action="BUY",
                            volume=0.01,
                            stop_loss=3990.0,
                            take_profit=4050.0,
                        )

        self.assertIsNotNone(result)
        self.assertEqual(result["order"], 12345)
        self.assertEqual(result["deal"], 67890)


class TestSignalPersistence(unittest.TestCase):
    """Signals must be persisted with timestamps and rejection reasons."""

    def test_hold_signal_persisted_with_reason(self):
        tester = ForwardTester()
        tester.Session = MagicMock()
        session = tester.Session.return_value
        session.query.return_value.first.return_value = None

        mock_signal = Mock()
        mock_signal.timestamp = datetime(2024, 1, 1, 12, 0)
        mock_signal.signal = Mock(value="NEUTRAL")
        mock_signal.regime = "RANGE"
        mock_signal.confidence = 0.7
        mock_signal.features = {"returns": 0.001}

        tester._save_signal_to_db(
            mock_signal,
            {"close": 2000.0},
            ai_approved=False,
            rejection_reason="HOLD signal",
        )

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        self.assertFalse(added.ai_approved)
        self.assertEqual(added.rejection_reason, "HOLD signal")
        self.assertIsNotNone(added.timestamp)


class TestDuplicateProtection(unittest.TestCase):
    """The same candle must never be processed twice."""

    def test_candle_processed_only_once(self):
        tester = ForwardTester()
        candle_time = datetime(2024, 1, 1, 12, 0)
        candle = {
            "timestamp": candle_time,
            "open": 2000.0,
            "high": 2010.0,
            "low": 1995.0,
            "close": 2005.0,
        }

        with patch.object(
            tester, "_get_latest_completed_candle", return_value=candle
        ):
            with patch.object(
                tester, "_fetch_feature_history", return_value=None
            ) as mock_fetch:
                tester._process_cycle()
                tester._process_cycle()
                tester._process_cycle()

                # History fetched exactly once for the candle
                self.assertEqual(mock_fetch.call_count, 1)


if __name__ == "__main__":
    unittest.main()
