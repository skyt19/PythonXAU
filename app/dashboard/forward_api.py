"""
Forward-test status endpoint.

Surfaces the state the operator needs: what the runtime last did, what it
decided and why, and whether it is currently permitted to trade.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import config
from app.database import Signal, SystemState, Trade, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/forward", tags=["forward-testing"])

# Written by the forward tester so the dashboard can show live state.
STATUS_FILE = Path("artifacts/forward_status.json")


@router.get("/status")
async def forward_status(db: Session = Depends(get_db)):
    """
    Forward-testing runtime status.

    Combines the persisted runtime status file (written by
    scripts/forward_test.py) with the trade journal so the dashboard shows
    what the system is actually doing.
    """
    status = {
        "running": False,
        "mode": "IDLE",
        "last_candle": None,
        "last_signal": None,
        "last_error": None,
        "daily_pnl": None,
        "open_positions": 0,
        "demo_only": config.demo_only,
        "notes": [],
    }

    # Runtime status file
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE) as f:
                status.update(json.load(f))
        except Exception as e:
            logger.error(f"Failed to read forward status file: {e}")
            status["notes"].append(f"status file unreadable: {e}")

    # Journal-derived state
    try:
        last_signal = (
            db.query(Signal).order_by(Signal.id.desc()).first()
        )
        if last_signal:
            status["last_signal"] = {
                "timestamp": last_signal.timestamp.isoformat(),
                "direction": last_signal.direction.value,
                "entry_price": last_signal.entry_price,
                "stop_loss": last_signal.stop_loss,
                "take_profit": last_signal.take_profit,
                "approved": last_signal.ai_approved,
                "reason": last_signal.rejection_reason,
                "strategy_reason": last_signal.strategy_reason,
            }

        open_trades = db.query(Trade).filter(Trade.exit_timestamp == None).count()
        status["open_positions"] = open_trades

        closed = (
            db.query(Trade).filter(Trade.exit_timestamp != None).all()
        )
        realized = sum(t.realized_pnl or 0.0 for t in closed)
        status["realized_pnl"] = realized

        state = db.query(SystemState).first()
        if state:
            status["daily_pnl"] = state.daily_realized_pnl
            status["execution_enabled"] = state.execution_enabled
            status["session_start_equity"] = state.session_start_equity
            status["high_water_mark"] = state.high_water_mark
            status["emergency_stop_reason"] = state.emergency_stop_reason
            if state.last_account_verification:
                status["last_account_verification"] = (
                    state.last_account_verification.isoformat()
                )

    except Exception as e:
        logger.error(f"Failed to build forward status: {e}", exc_info=True)
        status["notes"].append(f"journal query failed: {e}")

    return status


@router.get("/signals")
async def recent_signals(limit: int = 50, db: Session = Depends(get_db)):
    """Recent signals with their decision reasons."""
    try:
        signals = (
            db.query(Signal).order_by(Signal.id.desc()).limit(min(limit, 500)).all()
        )
        return {
            "count": len(signals),
            "signals": [
                {
                    "id": s.id,
                    "timestamp": s.timestamp.isoformat(),
                    "direction": s.direction.value,
                    "entry_price": s.entry_price,
                    "stop_loss": s.stop_loss,
                    "take_profit": s.take_profit,
                    "volume": s.volume,
                    "approved": s.ai_approved,
                    "reason": s.rejection_reason,
                    "strategy_reason": s.strategy_reason,
                }
                for s in signals
            ],
        }
    except Exception as e:
        logger.error(f"Failed to list signals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades")
async def trade_journal(limit: int = 100, db: Session = Depends(get_db)):
    """Trade journal for forward testing."""
    try:
        trades = (
            db.query(Trade).order_by(Trade.id.desc()).limit(min(limit, 500)).all()
        )
        return {
            "count": len(trades),
            "trades": [
                {
                    "id": t.id,
                    "broker_order_id": t.broker_order_id,
                    "entry_timestamp": t.entry_timestamp.isoformat(),
                    "exit_timestamp": t.exit_timestamp.isoformat()
                    if t.exit_timestamp
                    else None,
                    "direction": t.direction.value,
                    "entry_price": t.entry_price_actual or t.entry_price_expected,
                    "exit_price": t.exit_price_actual,
                    "volume": t.volume,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                    "realized_pnl": t.realized_pnl,
                    "exit_reason": t.exit_reason.value if t.exit_reason else None,
                    "status": t.status.value,
                    "commission": t.total_commission,
                    "swap": t.total_swap,
                }
                for t in trades
            ],
        }
    except Exception as e:
        logger.error(f"Failed to list trades: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
