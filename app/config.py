"""
Application Configuration
Loads and validates all configuration from environment variables.
"""
import os
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Main application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ========================================================================
    # DEMO ENFORCEMENT
    # ========================================================================
    demo_only: bool = Field(
        default=True,
        description="MUST be True. Live trading is prohibited.",
    )

    # ========================================================================
    # MT5 BROKER CREDENTIALS
    # ========================================================================
    mt5_login: Optional[str] = Field(
        default=None,
        description="MT5 demo account login",
    )
    mt5_password: Optional[str] = Field(
        default=None,
        description="MT5 demo account password",
    )
    mt5_server: str = Field(
        default="HFM-Demo",
        description="MT5 broker server",
    )
    mt5_symbol: str = Field(
        default="XAUUSD",
        description="Primary trading symbol",
    )

    # ========================================================================
    # APPLICATION
    # ========================================================================
    dashboard_host: str = Field(
        default="127.0.0.1",
        description="Dashboard host (localhost only for security)",
    )
    dashboard_port: int = Field(
        default=3831,
        description="Dashboard port",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    log_file: Path = Field(
        default=Path("logs/farming_hq.log"),
        description="Log file path",
    )

    # ========================================================================
    # DATABASE
    # ========================================================================
    database_url: str = Field(
        default="sqlite:///data/farming_hq.db",
        description="Database connection URL",
    )

    # ========================================================================
    # RISK MANAGEMENT
    # ========================================================================
    max_risk_per_trade: float = Field(
        default=0.0025,
        ge=0.0,
        le=0.05,
        description="Maximum risk per trade as fraction of equity",
    )
    max_daily_loss: float = Field(
        default=0.01,
        ge=0.0,
        le=0.1,
        description="Maximum daily loss as fraction of session equity",
    )
    max_drawdown: float = Field(
        default=0.05,
        ge=0.0,
        le=0.2,
        description="Maximum drawdown from high-water mark",
    )
    max_open_positions: int = Field(
        default=1,
        ge=0,
        le=10,
        description="Maximum simultaneous open positions",
    )
    max_spread_points: float = Field(
        default=50.0,
        ge=0.0,
        description="Maximum spread in points (0 = disabled)",
    )
    max_slippage_points: float = Field(
        default=30.0,
        ge=0.0,
        description="Maximum allowed slippage in points",
    )

    # ========================================================================
    # TRADING STRATEGY
    # ========================================================================
    timeframe: str = Field(
        default="M15",
        description="Primary analysis timeframe",
    )
    lstm_lookback: int = Field(
        default=64,
        ge=10,
        le=200,
        description="LSTM lookback window in bars",
    )
    min_lstm_confidence: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Minimum LSTM confidence for trade approval",
    )
    atr_period: int = Field(
        default=14,
        ge=5,
        le=50,
        description="ATR period for volatility calculation",
    )
    atr_stop_multiplier: float = Field(
        default=2.0,
        ge=0.5,
        le=5.0,
        description="ATR multiplier for stop-loss distance",
    )
    risk_reward_ratio: float = Field(
        default=2.0,
        ge=1.0,
        le=10.0,
        description="Risk-reward ratio (TP/SL)",
    )

    # ========================================================================
    # MODEL TRAINING
    # ========================================================================
    model_dir: Path = Field(
        default=Path("artifacts/models"),
        description="Model artifacts directory",
    )
    data_dir: Path = Field(
        default=Path("data"),
        description="Training data directory",
    )
    random_seed: int = Field(
        default=42,
        description="Random seed for reproducibility",
    )
    batch_size: int = Field(
        default=64,
        ge=8,
        le=512,
        description="Training batch size",
    )
    max_epochs: int = Field(
        default=200,
        ge=10,
        le=1000,
        description="Maximum training epochs",
    )
    early_stopping_patience: int = Field(
        default=20,
        ge=5,
        le=100,
        description="Early stopping patience",
    )
    learning_rate: float = Field(
        default=0.001,
        ge=0.00001,
        le=0.1,
        description="Learning rate",
    )

    # ========================================================================
    # EXECUTION CONTROL
    # ========================================================================
    execution_enabled: bool = Field(
        default=False,
        description="Enable execution (overridden by kill switch in database)",
    )
    min_trade_interval: int = Field(
        default=300,
        ge=0,
        description="Minimum seconds between trades",
    )
    trading_hours: str = Field(
        default="",
        description="Trading hours in UTC (comma-separated, empty = always)",
    )

    # ========================================================================
    # MONITORING
    # ========================================================================
    dashboard_update_interval: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Dashboard update interval in seconds",
    )
    data_staleness_threshold: int = Field(
        default=300,
        ge=60,
        description="Data staleness threshold in seconds",
    )
    health_check_interval: int = Field(
        default=60,
        ge=10,
        description="Health check interval in seconds",
    )

    # ========================================================================
    # DEVELOPMENT
    # ========================================================================
    mock_mt5: bool = Field(
        default=False,
        description="Enable mock MT5 for testing",
    )
    debug_mode: bool = Field(
        default=False,
        description="Enable debug logging",
    )

    @field_validator("demo_only")
    @classmethod
    def validate_demo_only(cls, v: bool) -> bool:
        """Enforce that DEMO_ONLY must be True."""
        if not v:
            raise ValueError(
                "DEMO_ONLY must be True. Live trading is prohibited by design."
            )
        return v

    @field_validator("dashboard_host")
    @classmethod
    def validate_dashboard_host(cls, v: str) -> str:
        """Ensure dashboard is bound to localhost for security."""
        if v not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                f"Dashboard host must be localhost for security. Got: {v}"
            )
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(
                f"Invalid log level: {v}. Must be one of {valid_levels}"
            )
        return v_upper

    @property
    def trading_hours_list(self) -> Optional[List[int]]:
        """Parse trading hours string into list of hours."""
        if not self.trading_hours:
            return None
        try:
            hours = [int(h.strip()) for h in self.trading_hours.split(",")]
            if not all(0 <= h <= 23 for h in hours):
                raise ValueError("Hours must be between 0 and 23")
            return hours
        except ValueError as e:
            raise ValueError(f"Invalid trading hours format: {e}")

    def create_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        Path("artifacts").mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(parents=True, exist_ok=True)

    def get_mt5_timeframe_code(self) -> int:
        """Convert timeframe string to MT5 timeframe constant."""
        import MetaTrader5 as mt5

        timeframe_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        if self.timeframe not in timeframe_map:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")
        return timeframe_map[self.timeframe]

    def mask_credentials(self) -> dict:
        """Return config dict with masked credentials for logging."""
        config_dict = self.model_dump()
        if self.mt5_password:
            config_dict["mt5_password"] = "***REDACTED***"
        if self.mt5_login:
            config_dict["mt5_login"] = f"***{str(self.mt5_login)[-4:]}***"
        return config_dict


# Global configuration instance
config = Config()
