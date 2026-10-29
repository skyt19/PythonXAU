"""
Dashboard API Schemas

Pydantic models for request/response validation.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    demo_only: bool


class SystemInfoResponse(BaseModel):
    """System information response."""
    name: str
    version: str
    description: str
    demo_only: bool
    symbol: str
    timeframe: str


class RiskConfig(BaseModel):
    """Risk configuration."""
    max_risk_per_trade: float
    max_daily_loss: float
    max_drawdown: float
    max_open_positions: int
    max_spread_points: float


class TradingConfig(BaseModel):
    """Trading configuration."""
    symbol: str
    timeframe: str
    server: str


class ModelConfig(BaseModel):
    """Model configuration."""
    lookback: int
    min_confidence: float


class ExecutionConfig(BaseModel):
    """Execution configuration."""
    enabled: bool
    reason: str


class ConfigurationResponse(BaseModel):
    """Configuration response."""
    trading: TradingConfig
    risk: RiskConfig
    model: ModelConfig
    execution: ExecutionConfig


class SystemStateResponse(BaseModel):
    """System state response."""
    execution_enabled: bool
    last_account_verification: Optional[str]
    verified_account_login: Optional[str]
    verified_account_server: Optional[str]
    session_start_time: Optional[str]
    session_start_equity: Optional[float]
    daily_realized_pnl: float
    high_water_mark: Optional[float]
    emergency_stop_reason: Optional[str]
    last_updated: Optional[str]


class AccountStatusResponse(BaseModel):
    """Account status response."""
    connected: bool
    reason: Optional[str]
    account_verified: bool
    account_mode: str
    demo_only_enforced: bool
    note: Optional[str]


class MarketStatusResponse(BaseModel):
    """Market status response."""
    symbol: str
    timeframe: str
    data_available: bool
    latest_bar: Optional[str]
    current_regime: Optional[str]
    note: Optional[str]


class DataStats(BaseModel):
    """Data statistics."""
    bars_collected: int
    oldest_bar: Optional[str]
    newest_bar: Optional[str]


class PredictionStats(BaseModel):
    """Prediction statistics."""
    total: int


class SignalStats(BaseModel):
    """Signal statistics."""
    total: int
    approved: int
    rejected: int


class TradeStats(BaseModel):
    """Trade statistics."""
    total: int
    open: int
    closed: int


class ModelStats(BaseModel):
    """Model statistics."""
    total: int
    active: int


class StatisticsResponse(BaseModel):
    """Statistics response."""
    data: DataStats
    predictions: PredictionStats
    signals: SignalStats
    trades: TradeStats
    models: ModelStats
