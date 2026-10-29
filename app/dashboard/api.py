"""
Dashboard API Routes

Provides RESTful API endpoints for the Farming HQ dashboard.
Phase 1: Basic status and information endpoints only.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import config
from app.database import get_db, SystemState

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/info")
async def get_info():
    """Get system information."""
    return {
        "name": "XAUUSD AI Farming HQ",
        "version": "1.0.0",
        "description": "HFM MetaTrader 5 Demo Forward Testing System",
        "demo_only": config.demo_only,
        "symbol": config.mt5_symbol,
        "timeframe": config.timeframe,
    }


@router.get("/config")
async def get_configuration():
    """
    Get current configuration.

    Returns non-sensitive configuration parameters.
    """
    return {
        "trading": {
            "symbol": config.mt5_symbol,
            "timeframe": config.timeframe,
            "server": config.mt5_server,
        },
        "risk": {
            "max_risk_per_trade": config.max_risk_per_trade,
            "max_daily_loss": config.max_daily_loss,
            "max_drawdown": config.max_drawdown,
            "max_open_positions": config.max_open_positions,
            "max_spread_points": config.max_spread_points,
        },
        "model": {
            "lookback": config.lstm_lookback,
            "min_confidence": config.min_lstm_confidence,
        },
        "execution": {
            "enabled": False,
            "reason": "Phase 1 - No execution module",
        },
    }


@router.get("/system/state")
async def get_system_state(db: Session = Depends(get_db)):
    """
    Get current system state from database.

    Returns kill switch state, session info, and safety status.
    """
    try:
        # Try to get system state
        state = db.query(SystemState).first()

        if state is None:
            # Create initial state if it doesn't exist
            state = SystemState(
                execution_enabled=False,
                session_start_equity=None,
                session_start_time=None,
                daily_realized_pnl=0.0,
                high_water_mark=None,
                emergency_stop_reason=None,
            )
            db.add(state)
            db.commit()
            db.refresh(state)

        return {
            "execution_enabled": state.execution_enabled,
            "last_account_verification": state.last_account_verification.isoformat() if state.last_account_verification else None,
            "verified_account_login": state.verified_account_login,
            "verified_account_server": state.verified_account_server,
            "session_start_time": state.session_start_time.isoformat() if state.session_start_time else None,
            "session_start_equity": state.session_start_equity,
            "daily_realized_pnl": state.daily_realized_pnl,
            "high_water_mark": state.high_water_mark,
            "emergency_stop_reason": state.emergency_stop_reason,
            "last_updated": state.last_updated.isoformat() if state.last_updated else None,
        }
    except Exception as e:
        logger.error(f"Error retrieving system state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve system state: {str(e)}")


@router.get("/account/status")
async def get_account_status():
    """
    Get account connection and verification status.

    Phase 1: Returns placeholder data as MT5 connection is not active.
    """
    return {
        "connected": False,
        "reason": "MT5 integration not active in Phase 1",
        "account_verified": False,
        "account_mode": "unknown",
        "demo_only_enforced": config.demo_only,
        "note": "Account verification will be implemented in Phase 2",
    }


@router.get("/market/status")
async def get_market_status():
    """
    Get current market status.

    Phase 1: Returns placeholder as data collection is not active.
    """
    return {
        "symbol": config.mt5_symbol,
        "timeframe": config.timeframe,
        "data_available": False,
        "latest_bar": None,
        "current_regime": None,
        "note": "Market data collection will be implemented in Phase 3",
    }


@router.get("/statistics")
async def get_statistics(db: Session = Depends(get_db)):
    """
    Get system statistics.

    Returns counts of key database entities.
    """
    try:
        from app.database import MarketData, Trade, Signal, RegimePrediction, ModelVersion

        stats = {
            "data": {
                "bars_collected": db.query(MarketData).count(),
                "oldest_bar": None,
                "newest_bar": None,
            },
            "predictions": {
                "total": db.query(RegimePrediction).count(),
            },
            "signals": {
                "total": db.query(Signal).count(),
                "approved": db.query(Signal).filter(Signal.ai_approved == True).count(),
                "rejected": db.query(Signal).filter(Signal.ai_approved == False).count(),
            },
            "trades": {
                "total": db.query(Trade).count(),
                "open": db.query(Trade).filter(Trade.exit_timestamp == None).count(),
                "closed": db.query(Trade).filter(Trade.exit_timestamp != None).count(),
            },
            "models": {
                "total": db.query(ModelVersion).count(),
                "active": db.query(ModelVersion).filter(ModelVersion.is_active == True).count(),
            },
        }

        # Get oldest and newest bar if any exist
        oldest_bar = db.query(MarketData).order_by(MarketData.timestamp.asc()).first()
        newest_bar = db.query(MarketData).order_by(MarketData.timestamp.desc()).first()

        if oldest_bar:
            stats["data"]["oldest_bar"] = oldest_bar.timestamp.isoformat()
        if newest_bar:
            stats["data"]["newest_bar"] = newest_bar.timestamp.isoformat()

        return stats

    except Exception as e:
        logger.error(f"Error retrieving statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve statistics: {str(e)}")
