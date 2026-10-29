"""
AUDIT TEST: Verify account guard safety controls.
"""
import pytest
from unittest.mock import Mock, patch

from app.broker.account_guard import AccountGuard, AccountMode


class TestAccountGuardSafety:
    """Test critical safety controls."""

    def test_live_account_rejected(self):
        """CRITICAL: Live accounts must be rejected."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                # Simulate LIVE account (trade_mode=1)
                mock_info.return_value = Mock(
                    trade_mode=1,  # REAL
                    login=12345,
                    server="HFM-Real",
                    balance=10000.0,
                    equity=10000.0,
                    leverage=500,
                )

                verification = guard.verify_account()

                # Must be rejected
                assert not verification.is_safe, "Live account was NOT rejected"
                assert verification.account_mode == AccountMode.REAL
                assert any("REAL" in reason or "DEMO" in reason for reason in verification.failure_reasons)

    def test_unknown_account_rejected(self):
        """CRITICAL: Unknown accounts must be rejected."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                # Simulate unknown account (trade_mode=0)
                mock_info.return_value = Mock(
                    trade_mode=0,  # UNKNOWN
                    login=12345,
                    server="UnknownServer",
                    balance=10000.0,
                    equity=10000.0,
                    leverage=500,
                )

                verification = guard.verify_account()

                # Must be rejected
                assert not verification.is_safe, "Unknown account was NOT rejected"
                assert verification.account_mode == AccountMode.UNKNOWN

    def test_demo_account_accepted(self):
        """CRITICAL: Demo accounts must be accepted."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                # Simulate DEMO account (trade_mode=2)
                mock_info.return_value = Mock(
                    trade_mode=2,  # DEMO
                    login=12345,
                    server="HFM-Demo",
                    balance=100000.0,
                    equity=100000.0,
                    leverage=100,
                )

                verification = guard.verify_account()

                # Must be accepted
                assert verification.is_safe, f"Demo account was rejected: {verification.failure_reasons}"
                assert verification.account_mode == AccountMode.DEMO

    def test_execution_safety_blocks_live(self):
        """CRITICAL: Execution safety must block live accounts."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                # Simulate LIVE account
                mock_info.return_value = Mock(
                    trade_mode=1,
                    login=12345,
                    server="HFM-Real",
                    balance=10000.0,
                    equity=10000.0,
                    leverage=500,
                )

                is_safe, reason = guard.verify_execution_safety()

                # Must block execution
                assert not is_safe, "Execution NOT blocked for live account"
                assert reason, "No rejection reason provided"

    def test_server_allowlist_enforced(self):
        """Verify server allowlist is enforced."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                # Demo mode but suspicious server
                mock_info.return_value = Mock(
                    trade_mode=2,  # DEMO
                    login=12345,
                    server="SuspiciousServer-123",
                    balance=100000.0,
                    equity=100000.0,
                    leverage=100,
                )

                verification = guard.verify_account()

                # Should warn about server not in allowlist
                assert not verification.is_safe or any("allowlist" in reason.lower() for reason in verification.failure_reasons)

    def test_mt5_failure_blocks_execution(self):
        """CRITICAL: MT5 initialization failure must block execution."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=False):
            with patch('MetaTrader5.last_error', return_value=(1, "Connection failed")):
                verification = guard.verify_account()

                # Must fail safely
                assert not verification.is_safe, "MT5 failure did NOT block execution"
                assert verification.account_mode == AccountMode.UNKNOWN
