"""
Account Guard - Multi-layer demo account verification.

This module implements the CRITICAL safety requirement that live trading
must be impossible. Every order passes through this guard.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Set

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


class AccountMode(Enum):
    """MT5 account trading mode."""

    UNKNOWN = 0
    DEMO = 1
    CONTEST = 2
    REAL = 3


@dataclass
class AccountVerification:
    """Result of account verification."""

    is_safe: bool
    account_mode: AccountMode
    account_login: Optional[int]
    account_server: Optional[str]
    account_balance: Optional[float]
    account_equity: Optional[float]
    account_leverage: Optional[int]
    verification_time: datetime
    failure_reasons: list[str]

    def __str__(self) -> str:
        """Human-readable verification result."""
        status = "PASS" if self.is_safe else "FAIL"
        return (
            f"Account Verification [{status}]\n"
            f"  Mode: {self.account_mode.name}\n"
            f"  Login: {self.account_login}\n"
            f"  Server: {self.account_server}\n"
            f"  Balance: ${self.account_balance:,.2f}\n"
            f"  Equity: ${self.account_equity:,.2f}\n"
            f"  Leverage: 1:{self.account_leverage}\n"
            f"  Verified: {self.verification_time.isoformat()}\n"
            + (
                f"  Failures: {', '.join(self.failure_reasons)}\n"
                if self.failure_reasons
                else ""
            )
        )


class AccountGuard:
    """
    Multi-layer account verification ensuring demo-only execution.

    This is the PRIMARY safety mechanism. Every order must pass through
    verify_execution_safety() before being sent to the broker.
    """

    # Known demo server patterns (HFM-specific, extend as needed)
    DEMO_SERVER_PATTERNS: Set[str] = {
        "HFM-Demo",
        "HotForex-Demo",
        "HF-Demo",
    }

    # Cache verification for this duration
    VERIFICATION_CACHE_DURATION = timedelta(minutes=5)

    def __init__(self, required_demo_only: bool = True):
        """
        Initialize account guard.

        Args:
            required_demo_only: If True, only demo accounts are allowed
        """
        self.required_demo_only = required_demo_only
        self._last_verification: Optional[AccountVerification] = None
        self._last_verification_time: Optional[datetime] = None

        logger.info(
            f"AccountGuard initialized: required_demo_only={required_demo_only}"
        )

    def verify_account(
        self,
        expected_login: Optional[int] = None,
        expected_server: Optional[str] = None,
        force_refresh: bool = False,
    ) -> AccountVerification:
        """
        Perform comprehensive account verification.

        This method implements ALL required safety checks:
        1. MT5 terminal connection
        2. Account information retrieval
        3. Account mode verification (DEMO required)
        4. Server name validation against allowlist
        5. Login matching if provided
        6. Balance sanity checks

        Args:
            expected_login: Expected account login (if known)
            expected_server: Expected server name (if known)
            force_refresh: Force fresh verification, ignore cache

        Returns:
            AccountVerification with detailed results
        """
        now = datetime.utcnow()

        # Check cache
        if (
            not force_refresh
            and self._last_verification is not None
            and self._last_verification_time is not None
            and (now - self._last_verification_time) < self.VERIFICATION_CACHE_DURATION
        ):
            logger.debug("Returning cached account verification")
            return self._last_verification

        failure_reasons = []

        # 1. Check MT5 initialization
        if not mt5.initialize():
            error = mt5.last_error()
            failure_reasons.append(f"MT5 initialization failed: {error}")
            logger.error(f"MT5 initialization failed: {error}")

            return AccountVerification(
                is_safe=False,
                account_mode=AccountMode.UNKNOWN,
                account_login=None,
                account_server=None,
                account_balance=None,
                account_equity=None,
                account_leverage=None,
                verification_time=now,
                failure_reasons=failure_reasons,
            )

        # 2. Retrieve account info
        account_info = mt5.account_info()
        if account_info is None:
            error = mt5.last_error()
            failure_reasons.append(f"Could not retrieve account info: {error}")
            logger.error(f"Could not retrieve account info: {error}")

            return AccountVerification(
                is_safe=False,
                account_mode=AccountMode.UNKNOWN,
                account_login=None,
                account_server=None,
                account_balance=None,
                account_equity=None,
                account_leverage=None,
                verification_time=now,
                failure_reasons=failure_reasons,
            )

        # Extract account details
        account_login = account_info.login
        account_server = account_info.server
        account_balance = account_info.balance
        account_equity = account_info.equity
        account_leverage = account_info.leverage

        # Determine account mode from trade_mode
        # MT5 trade_mode: 0=disabled, 1=real, 2=demo, 3=contest
        trade_mode = account_info.trade_mode
        if trade_mode == 2:
            account_mode = AccountMode.DEMO
        elif trade_mode == 3:
            account_mode = AccountMode.CONTEST  # Treat contest as demo-equivalent
        elif trade_mode == 1:
            account_mode = AccountMode.REAL
        else:
            account_mode = AccountMode.UNKNOWN

        logger.info(
            f"Account retrieved: login={account_login}, server={account_server}, "
            f"mode={account_mode.name}, balance=${account_balance:,.2f}"
        )

        # 3. Verify account mode
        if self.required_demo_only and account_mode not in (
            AccountMode.DEMO,
            AccountMode.CONTEST,
        ):
            failure_reasons.append(
                f"Account mode is {account_mode.name}, but DEMO is required"
            )
            logger.error(
                f"SAFETY VIOLATION: Account mode is {account_mode.name}, expected DEMO"
            )

        # 4. Verify server against allowlist
        if not self._is_demo_server(account_server):
            failure_reasons.append(
                f"Server '{account_server}' not in demo server allowlist"
            )
            logger.warning(
                f"Server '{account_server}' not recognized as demo server"
            )

        # 5. Verify login matches expected
        if expected_login is not None and account_login != expected_login:
            failure_reasons.append(
                f"Account login {account_login} does not match expected {expected_login}"
            )
            logger.error(
                f"Account login mismatch: got {account_login}, expected {expected_login}"
            )

        # 6. Verify server matches expected
        if expected_server is not None and account_server != expected_server:
            failure_reasons.append(
                f"Server '{account_server}' does not match expected '{expected_server}'"
            )
            logger.error(
                f"Server mismatch: got '{account_server}', expected '{expected_server}'"
            )

        # 7. Sanity check balance (demo accounts typically start with standard amounts)
        # This is a soft check - log warning but don't fail
        if account_balance < 100:
            logger.warning(
                f"Account balance unusually low for demo: ${account_balance}"
            )

        # Determine if safe
        is_safe = len(failure_reasons) == 0

        # Create verification result
        verification = AccountVerification(
            is_safe=is_safe,
            account_mode=account_mode,
            account_login=account_login,
            account_server=account_server,
            account_balance=account_balance,
            account_equity=account_equity,
            account_leverage=account_leverage,
            verification_time=now,
            failure_reasons=failure_reasons,
        )

        # Cache result
        self._last_verification = verification
        self._last_verification_time = now

        if is_safe:
            logger.info("✓ Account verification PASSED")
        else:
            logger.error(f"✗ Account verification FAILED: {failure_reasons}")

        return verification

    def verify_execution_safety(
        self,
        expected_login: Optional[int] = None,
        expected_server: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Verify that it is safe to execute orders.

        This method MUST be called before EVERY order submission.

        Args:
            expected_login: Expected account login
            expected_server: Expected server name

        Returns:
            Tuple of (is_safe, reason_if_not_safe)
        """
        verification = self.verify_account(
            expected_login=expected_login,
            expected_server=expected_server,
            force_refresh=True,  # Always fresh check for execution
        )

        if not verification.is_safe:
            reason = "; ".join(verification.failure_reasons)
            logger.error(f"EXECUTION BLOCKED: {reason}")
            return False, reason

        return True, "Execution safety verified"

    def _is_demo_server(self, server: str) -> bool:
        """
        Check if server name matches demo patterns.

        Args:
            server: Server name from MT5

        Returns:
            True if server is in demo allowlist
        """
        # Exact match
        if server in self.DEMO_SERVER_PATTERNS:
            return True

        # Pattern match (e.g., "Demo" in name)
        server_lower = server.lower()
        demo_keywords = ["demo", "test", "contest"]
        if any(keyword in server_lower for keyword in demo_keywords):
            logger.info(
                f"Server '{server}' matches demo keyword pattern"
            )
            return True

        return False

    def invalidate_cache(self) -> None:
        """Invalidate cached verification, forcing fresh check."""
        self._last_verification = None
        self._last_verification_time = None
        logger.debug("Account verification cache invalidated")

    def get_last_verification(self) -> Optional[AccountVerification]:
        """Get the last verification result (may be stale)."""
        return self._last_verification
