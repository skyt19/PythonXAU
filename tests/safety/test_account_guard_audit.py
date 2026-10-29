"""
AUDIT TEST: Verify account guard safety controls.

IMPORTANT: These tests use the REAL MetaTrader5 constants
(ACCOUNT_TRADE_MODE_DEMO=0, CONTEST=1, REAL=2). An earlier version of
this file used incorrect literal values, which masked a swapped
demo/live mapping in AccountGuard. Always reference the library
constants so a mapping error cannot hide here.
"""
import pytest
from unittest.mock import Mock, patch

import MetaTrader5 as mt5

from app.broker.account_guard import AccountGuard, AccountMode


def make_account_info(trade_mode, server="HFM-Demo", login=12345):
    """Build a mock account_info with the given MT5 trade_mode."""
    return Mock(
        trade_mode=trade_mode,
        login=login,
        server=server,
        balance=100000.0,
        equity=100000.0,
        leverage=100,
    )


class TestAccountGuardSafety:
    """Test critical safety controls."""

    def test_live_account_rejected(self):
        """CRITICAL: Live accounts must be rejected."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                mock_info.return_value = make_account_info(
                    mt5.ACCOUNT_TRADE_MODE_REAL, server="HFM-Real"
                )

                verification = guard.verify_account()

                # Must be rejected
                assert not verification.is_safe, "Live account was NOT rejected"
                assert verification.account_mode == AccountMode.REAL
                assert any(
                    "REAL" in reason or "DEMO" in reason
                    for reason in verification.failure_reasons
                )

    def test_contest_account_rejected_or_accepted_by_policy(self):
        """Contest accounts are treated as demo-equivalent."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                mock_info.return_value = make_account_info(
                    mt5.ACCOUNT_TRADE_MODE_CONTEST, server="HFM-Demo"
                )

                verification = guard.verify_account()

                assert verification.account_mode == AccountMode.CONTEST
                # Contest is accepted as demo-equivalent
                assert verification.is_safe, verification.failure_reasons

    def test_unknown_account_rejected(self):
        """CRITICAL: Unknown accounts must be rejected."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                # trade_mode value that matches no known constant
                mock_info.return_value = make_account_info(
                    99, server="UnknownServer"
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
                mock_info.return_value = make_account_info(
                    mt5.ACCOUNT_TRADE_MODE_DEMO, server="HFM-Demo"
                )

                verification = guard.verify_account()

                # Must be accepted
                assert verification.is_safe, (
                    f"Demo account was rejected: {verification.failure_reasons}"
                )
                assert verification.account_mode == AccountMode.DEMO

    def test_execution_safety_blocks_live(self):
        """CRITICAL: Execution safety must block live accounts."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                mock_info.return_value = make_account_info(
                    mt5.ACCOUNT_TRADE_MODE_REAL, server="HFM-Real"
                )

                is_safe, reason = guard.verify_execution_safety()

                # Must block execution
                assert not is_safe, "Execution NOT blocked for live account"
                assert reason, "No rejection reason provided"

    def test_execution_safety_allows_demo(self):
        """Demo account passes the execution safety gate."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                mock_info.return_value = make_account_info(
                    mt5.ACCOUNT_TRADE_MODE_DEMO, server="HFM-Demo"
                )

                is_safe, reason = guard.verify_execution_safety()

                assert is_safe, f"Demo account blocked: {reason}"

    def test_server_allowlist_enforced(self):
        """Verify server allowlist is enforced."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                # Demo mode but non-demo server name
                mock_info.return_value = make_account_info(
                    mt5.ACCOUNT_TRADE_MODE_DEMO, server="SuspiciousServer-123"
                )

                verification = guard.verify_account()

                assert any(
                    "allowlist" in reason.lower()
                    for reason in verification.failure_reasons
                ), verification.failure_reasons

    def test_hfm_global_demo_server_accepted(self):
        """The real HFM demo server name is recognised."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                mock_info.return_value = make_account_info(
                    mt5.ACCOUNT_TRADE_MODE_DEMO, server="HFMarketsGlobal-Demo4"
                )

                verification = guard.verify_account()

                assert verification.is_safe, verification.failure_reasons

    def test_login_mismatch_rejected(self):
        """A different login than expected is rejected."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=True):
            with patch('MetaTrader5.account_info') as mock_info:
                mock_info.return_value = make_account_info(
                    mt5.ACCOUNT_TRADE_MODE_DEMO, server="HFM-Demo", login=999
                )

                verification = guard.verify_account(expected_login=12345)

                assert not verification.is_safe
                assert any("login" in r.lower() for r in verification.failure_reasons)

    def test_mt5_failure_blocks_execution(self):
        """CRITICAL: MT5 initialization failure must block execution."""
        guard = AccountGuard(required_demo_only=True)

        with patch('MetaTrader5.initialize', return_value=False):
            with patch('MetaTrader5.last_error', return_value=(1, "Connection failed")):
                verification = guard.verify_account()

                # Must fail safely
                assert not verification.is_safe, "MT5 failure did NOT block execution"
                assert verification.account_mode == AccountMode.UNKNOWN
