"""
MT5 Client - Connection and market data retrieval.
"""
import logging
from datetime import datetime
from typing import Optional, Tuple

import MetaTrader5 as mt5
import pandas as pd

logger = logging.getLogger(__name__)


class MT5Client:
    """MetaTrader 5 client for connection and data retrieval."""

    def __init__(self):
        """Initialize MT5 client."""
        self.is_connected = False
        self.terminal_info = None

    def connect(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
    ) -> bool:
        """
        Connect to MT5 terminal.

        Args:
            login: Account login
            password: Account password
            server: Broker server

        Returns:
            True if connected successfully
        """
        try:
            # Initialize MT5
            if not mt5.initialize():
                error = mt5.last_error()
                logger.error(f"MT5 initialization failed: {error}")
                return False

            # Login if credentials provided
            if login and password and server:
                if not mt5.login(login, password=password, server=server):
                    error = mt5.last_error()
                    logger.error(f"MT5 login failed: {error}")
                    mt5.shutdown()
                    return False

            self.terminal_info = mt5.terminal_info()
            self.is_connected = True

            logger.info(
                f"✓ MT5 connected: {self.terminal_info.company}, "
                f"build {self.terminal_info.build}"
            )
            return True

        except Exception as e:
            logger.error(f"MT5 connection error: {e}", exc_info=True)
            return False

    def disconnect(self) -> None:
        """Disconnect from MT5."""
        if self.is_connected:
            mt5.shutdown()
            self.is_connected = False
            logger.info("MT5 disconnected")

    def get_symbol_info(self, symbol: str):
        """
        Get symbol information.

        Args:
            symbol: Symbol name

        Returns:
            SymbolInfo or None
        """
        if not self.is_connected:
            logger.error("MT5 not connected")
            return None

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Symbol '{symbol}' not found")
            return None

        # Ensure symbol is visible
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                logger.error(f"Failed to select symbol '{symbol}'")
                return None

        return symbol_info

    def get_ohlc(
        self,
        symbol: str,
        timeframe: int,
        start: datetime,
        count: int,
    ) -> Optional[pd.DataFrame]:
        """
        Get OHLC data.

        Args:
            symbol: Symbol name
            timeframe: MT5 timeframe constant
            start: Start datetime (UTC)
            count: Number of bars

        Returns:
            DataFrame with OHLC data or None
        """
        if not self.is_connected:
            logger.error("MT5 not connected")
            return None

        # Get rates
        rates = mt5.copy_rates_from(symbol, timeframe, start, count)
        if rates is None or len(rates) == 0:
            logger.warning(f"No data returned for {symbol}")
            return None

        # Convert to DataFrame
        df = pd.DataFrame(rates)

        # Convert time to datetime (UTC)
        df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)

        # Rename columns
        df = df.rename(columns={
            'tick_volume': 'tick_volume',
            'real_volume': 'real_volume',
        })

        # Select and order columns
        df = df[[
            'timestamp', 'open', 'high', 'low', 'close',
            'tick_volume', 'spread', 'real_volume'
        ]]

        logger.debug(f"Retrieved {len(df)} bars for {symbol}")
        return df

    def get_tick(self, symbol: str) -> Optional[Tuple[float, float]]:
        """
        Get current bid/ask.

        Args:
            symbol: Symbol name

        Returns:
            Tuple of (bid, ask) or None
        """
        if not self.is_connected:
            logger.error("MT5 not connected")
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick for {symbol}")
            return None

        return tick.bid, tick.ask

    def check_connection(self) -> bool:
        """Check if connection is alive."""
        if not self.is_connected:
            return False

        try:
            # Test connection by getting terminal info
            info = mt5.terminal_info()
            return info is not None
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
