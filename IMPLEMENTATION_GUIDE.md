# XAUUSD AI Farming HQ - Complete Implementation Guide

**Project Scope**: 20-Phase, 60+ Module Trading System  
**Complexity**: High (ML + Trading + Safety-Critical)  
**Effort Level**: MAX  
**Status**: Foundation Complete, Core Implementation In Progress

---

## 🎯 What Has Been Accomplished

### ✅ Phase 1-5: Foundation (COMPLETE)

**Project Structure**:
- Complete directory hierarchy
- `.gitignore` with credential protection
- Git repository initialized
- Professional `README.md`
- Comprehensive `.env.example`
- Pinned `requirements.txt`

**Core Framework**:
- `app/config.py` - Full configuration with Pydantic validation
- `app/logging_config.py` - Structured logging with credential redaction
- `app/database.py` - Complete SQLAlchemy models (11 tables)

**Critical Safety**:
- `app/broker/account_guard.py` - Multi-layer demo account verification
- Account mode detection (DEMO/CONTEST/REAL/UNKNOWN)
- Server allowlist checking
- Execution safety gate with caching

**MT5 Integration**:
- `app/broker/mt5_client.py` - Connection and data retrieval
- `app/broker/symbol_specs.py` - Instrument specifications and volume calculation

**Data Pipeline**:
- `app/data/validator.py` - OHLC validation, gap detection, staleness checks

**Feature Engineering**:
- `app/features/indicators.py` - Technical indicators (EMA, ATR, ADX, RSI, etc.)

**Documentation**:
- `docs/ARCHITECTURE.md` - Complete system architecture
- `PROJECT_STATUS.md` - Implementation tracker
- `IMPLEMENTATION_GUIDE.md` - This document

### 📊 Statistics

- **Files Created**: 25+
- **Lines of Code**: ~3,500+
- **Safety Layers**: 6
- **Database Models**: 11
- **Configuration Parameters**: 40+

---

## 🚧 What Remains

### Critical Path to Working System

The following modules are **required** for a minimal working system:

#### 1. Data Collection (Priority: CRITICAL)
```
app/data/collector.py      - Fetch M15 bars from MT5
app/data/storage.py        - Persist to database
app/data/market_clock.py   - Detect completed bars
```

#### 2. LSTM Model (Priority: CRITICAL)
```
app/ml/dataset.py          - PyTorch sequence dataset
app/ml/labels.py           - Regime label generation
app/ml/lstm_model.py       - Model architecture
app/ml/inference.py        - Production inference
app/ml/training.py         - Training loop
app/ml/model_registry.py   - Version management
```

#### 3. Strategy & Risk (Priority: CRITICAL)
```
app/strategy/rules.py       - Rule-based strategy
app/strategy/regime_filter.py - AI signal filter
app/risk/position_sizing.py - Volume calculation
app/risk/limits.py          - Risk enforcement
app/risk/kill_switch.py     - Emergency controls
```

#### 4. Execution (Priority: CRITICAL)
```
app/broker/execution.py     - Order submission
app/broker/reconciliation.py - State synchronization
```

#### 5. Trading Service (Priority: CRITICAL)
```
app/services/trading_service.py - Main execution loop
app/services/scheduler.py       - Periodic tasks
app/services/health.py           - Health monitoring
```

#### 6. Dashboard (Priority: HIGH)
```
app/dashboard/api.py            - FastAPI backend
app/dashboard/schemas.py        - Pydantic models
app/dashboard/templates/*.html  - Frontend pages
app/dashboard/static/css/*.css  - Styles
app/dashboard/static/js/*.js    - Frontend logic
```

#### 7. Main Application (Priority: CRITICAL)
```
app/main.py                     - Application entry point
app/__init__.py                 - Package initialization
```

#### 8. Testing (Priority: CRITICAL)
```
tests/safety/test_account_guard.py        - MUST HAVE
tests/safety/test_live_account_reject.py  - MUST HAVE
tests/safety/test_risk_limits.py          - MUST HAVE
tests/safety/test_kill_switch.py          - MUST HAVE
tests/unit/test_config.py
tests/unit/test_features.py
tests/unit/test_position_sizing.py
tests/integration/test_mt5.py
tests/integration/test_api.py
tests/ml/test_training.py
```

#### 9. Scripts (Priority: MEDIUM)
```
scripts/collect_data.py    - Collect historical data
scripts/train_model.py     - Train LSTM
scripts/run_backtest.py    - Evaluate strategies
scripts/verify_account.py  - Account verification
```

#### 10. Additional Docs (Priority: LOW)
```
docs/TRADING_RULES.md      - Strategy documentation
docs/MODEL_CARD.md         - LSTM model card
docs/RISK_POLICY.md        - Risk management
docs/TESTING.md            - Test strategy
docs/OPERATIONS.md         - Operational procedures
```

---

## 📝 Implementation Templates

### Template: Data Collector

```python
# app/data/collector.py
"""Data collection from MT5."""
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.broker.mt5_client import MT5Client
from app.config import config
from app.database import MarketData
from app.data.validator import DataValidator

logger = logging.getLogger(__name__)


class DataCollector:
    """Collect and store market data."""

    def __init__(self, mt5_client: MT5Client, validator: DataValidator):
        self.mt5_client = mt5_client
        self.validator = validator

    def collect_historical(
        self,
        symbol: str,
        days: int,
        session: Session,
    ) -> int:
        """
        Collect historical data.

        Args:
            symbol: Symbol to collect
            days: Number of days to collect
            session: Database session

        Returns:
            Number of bars collected
        """
        start = datetime.utcnow() - timedelta(days=days)
        timeframe = config.get_mt5_timeframe_code()

        df = self.mt5_client.get_ohlc(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            count=days * 24 * 60 // 15,  # Approx bars for M15
        )

        if df is None:
            logger.error("Failed to retrieve data")
            return 0

        # Validate
        is_valid, errors = self.validator.validate_ohlc(df)
        if not is_valid:
            logger.error(f"Validation failed: {errors}")
            return 0

        # Store
        count = 0
        for _, row in df.iterrows():
            market_data = MarketData(
                symbol=symbol,
                timeframe=config.timeframe,
                timestamp=row['timestamp'],
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                tick_volume=int(row['tick_volume']),
                spread=row.get('spread'),
                real_volume=row.get('real_volume'),
            )
            session.add(market_data)
            count += 1

        session.commit()
        logger.info(f"Collected {count} bars for {symbol}")
        return count
```

### Template: LSTM Model

```python
# app/ml/lstm_model.py
"""PyTorch LSTM for regime classification."""
import torch
import torch.nn as nn


class RegimeLSTM(nn.Module):
    """LSTM for market regime classification."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 128,
        num_layers: int = 2,
        num_classes: int = 3,
        dropout: float = 0.3,
    ):
        super(RegimeLSTM, self).__init__()

        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )

        self.fc = nn.Linear(hidden_size, num_classes)
        self.softmax = nn.Softmax(dim=1)

    def forward(self, x):
        """
        Forward pass.

        Args:
            x: Input tensor [batch, seq_len, features]

        Returns:
            Logits [batch, num_classes]
        """
        # LSTM forward
        lstm_out, _ = self.lstm(x)

        # Take last output
        last_output = lstm_out[:, -1, :]

        # Fully connected
        logits = self.fc(last_output)

        return logits

    def predict_proba(self, x):
        """Predict probabilities."""
        logits = self.forward(x)
        probs = self.softmax(logits)
        return probs
```

### Template: Risk Manager

```python
# app/risk/position_sizing.py
"""Non-Martingale position sizing."""
import logging
from typing import Optional

from app.broker.symbol_specs import SymbolSpecs
from app.config import config

logger = logging.getLogger(__name__)


class PositionSizer:
    """Calculate position size from risk budget."""

    def __init__(self, symbol_specs: SymbolSpecs):
        self.symbol_specs = symbol_specs

    def calculate_volume(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
        direction: str,
    ) -> Optional[float]:
        """
        Calculate position volume.

        Args:
            equity: Current account equity
            entry_price: Planned entry price
            stop_loss: Stop loss price
            direction: "LONG" or "SHORT"

        Returns:
            Volume in lots or None if invalid
        """
        # Calculate risk in dollars
        risk_dollars = equity * config.max_risk_per_trade

        # Calculate stop distance in points
        stop_distance = abs(entry_price - stop_loss)
        stop_distance_points = stop_distance / self.symbol_specs.point

        logger.debug(
            f"Risk: ${risk_dollars:.2f}, "
            f"Stop distance: {stop_distance_points:.1f} points"
        )

        # Calculate volume
        volume = self.symbol_specs.calculate_volume(
            risk_dollars=risk_dollars,
            stop_distance_points=stop_distance_points,
        )

        # Verify minimum risk is met
        if volume < self.symbol_specs.volume_min:
            logger.warning(
                f"Calculated volume {volume} below minimum "
                f"{self.symbol_specs.volume_min}. Trade rejected."
            )
            return None

        logger.info(
            f"Position size: {volume:.2f} lots "
            f"(risk: ${risk_dollars:.2f}, "
            f"stop: {stop_distance_points:.1f} pts)"
        )

        return volume
```

### Template: Main Application

```python
# app/main.py
"""Main application entry point."""
import logging
import signal
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import config
from app.database import DatabaseManager, db_manager
from app.logging_config import setup_logging

# Setup logging
setup_logging(log_level=config.log_level, log_file=config.log_file)
logger = logging.getLogger(__name__)


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    logger.info("=" * 70)
    logger.info("XAUUSD AI Farming HQ - Starting")
    logger.info("=" * 70)

    # Initialize database
    global db_manager
    db_manager = DatabaseManager(config.database_url)
    db_manager.create_tables()
    logger.info("✓ Database initialized")

    # Create directories
    config.create_directories()
    logger.info("✓ Directories created")

    # Log configuration (masked)
    logger.info("Configuration loaded:")
    for key, value in config.mask_credentials().items():
        logger.info(f"  {key}: {value}")

    logger.info("=" * 70)
    logger.info("✓ Farming HQ ready")
    logger.info(f"✓ Dashboard: http://{config.dashboard_host}:{config.dashboard_port}")
    logger.info("=" * 70)

    yield

    # Shutdown
    logger.info("Shutting down...")
    if db_manager:
        db_manager.close()
    logger.info("✓ Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="XAUUSD AI Farming HQ",
    description="HFM MT5 Demo Forward Testing System",
    version="1.0.0",
    lifespan=lifespan,
)


# Health endpoint
@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "service": "farming_hq",
        "demo_only": config.demo_only,
    }


def main():
    """Run the application."""
    try:
        uvicorn.run(
            "app.main:app",
            host=config.dashboard_host,
            port=config.dashboard_port,
            log_level="info",
            access_log=False,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## 🧪 Essential Safety Tests

```python
# tests/safety/test_account_guard.py
"""CRITICAL: Test account guard prevents live trading."""
import pytest
from unittest.mock import Mock, patch
from app.broker.account_guard import AccountGuard, AccountMode


def test_live_account_rejected():
    """MUST PASS: Live accounts are rejected."""
    guard = AccountGuard(required_demo_only=True)

    with patch('MetaTrader5.initialize', return_value=True):
        with patch('MetaTrader5.account_info') as mock_info:
            # Simulate LIVE account
            mock_info.return_value = Mock(
                trade_mode=1,  # REAL
                login=12345,
                server="HFM-Real",
                balance=10000.0,
                equity=10000.0,
                leverage=500,
            )

            verification = guard.verify_account()

            assert not verification.is_safe
            assert verification.account_mode == AccountMode.REAL
            assert "Account mode is REAL" in str(verification.failure_reasons)


def test_unknown_account_rejected():
    """MUST PASS: Unknown accounts are rejected."""
    guard = AccountGuard(required_demo_only=True)

    with patch('MetaTrader5.initialize', return_value=True):
        with patch('MetaTrader5.account_info') as mock_info:
            # Simulate unknown account
            mock_info.return_value = Mock(
                trade_mode=0,  # UNKNOWN
                login=12345,
                server="UnknownServer",
                balance=10000.0,
                equity=10000.0,
                leverage=500,
            )

            verification = guard.verify_account()

            assert not verification.is_safe


def test_demo_account_accepted():
    """MUST PASS: Demo accounts are accepted."""
    guard = AccountGuard(required_demo_only=True)

    with patch('MetaTrader5.initialize', return_value=True):
        with patch('MetaTrader5.account_info') as mock_info:
            # Simulate DEMO account
            mock_info.return_value = Mock(
                trade_mode=2,  # DEMO
                login=12345,
                server="HFM-Demo",
                balance=100000.0,
                equity=100000.0,
                leverage=100,
            )

            verification = guard.verify_account()

            assert verification.is_safe
            assert verification.account_mode == AccountMode.DEMO


def test_execution_safety_blocks_live():
    """MUST PASS: Execution safety check blocks live accounts."""
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

            assert not is_safe
            assert "REAL" in reason or "live" in reason.lower()
```

---

## 🚀 Quick Start After Completion

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your HFM DEMO credentials

# 3. Run tests (MUST PASS SAFETY TESTS)
pytest tests/safety/ -v

# 4. Collect historical data
python scripts/collect_data.py --days 365

# 5. Train initial model
python scripts/train_model.py

# 6. Run backtest
python scripts/run_backtest.py

# 7. Start dashboard
python -m app.main

# 8. Open browser
# http://localhost:3831

# 9. Verify account (must be DEMO)
# Check Overview page for account status

# 10. Enable execution (if ready)
# Risk & Health page → Kill Switch → Enable
```

---

## ⚠️ Acceptance Criteria

Before declaring this system complete, **ALL** must be verified:

- [ ] Application starts without errors
- [ ] Dashboard loads at localhost:3831
- [ ] `/health` endpoint returns 200
- [ ] Database tables created
- [ ] MT5 connection works (or gracefully handles absence)
- [ ] Account guard REJECTS live accounts (test proves)
- [ ] Account guard REJECTS unknown accounts (test proves)
- [ ] Account guard ACCEPTS demo accounts (test proves)
- [ ] Data collection stores bars to database
- [ ] Features calculated without NaN/Inf
- [ ] LSTM model trains without errors
- [ ] Model predictions return probabilities
- [ ] Strategy rules generate signals
- [ ] Position sizing respects volume constraints
- [ ] Risk manager blocks trades exceeding limits
- [ ] Kill switch persists state
- [ ] Trade journal records outcomes
- [ ] Dashboard shows real data (not fabricated)
- [ ] No credentials in git history
- [ ] README instructions work

---

## 📚 Estimated Remaining Effort

**By Component**:
- Data pipeline: 3-4 hours
- LSTM complete implementation: 6-8 hours
- Strategy & risk: 4-6 hours
- Execution & reconciliation: 4-6 hours
- Trading service: 3-4 hours
- Dashboard (minimal): 6-8 hours
- Dashboard (complete): 12-16 hours
- Testing: 8-12 hours
- Scripts: 2-4 hours
- Documentation: 4-6 hours

**Total Remaining**: 50-80 hours of focused development

**Critical Path (Minimal Working System)**: 25-35 hours

---

## 🎯 Recommended Next Actions

### Option A: Continue Systematic Build (Recommended)
1. Complete data collection pipeline
2. Build LSTM training pipeline
3. Implement strategy and risk modules
4. Create minimal dashboard
5. Run safety tests
6. Document and deliver

### Option B: Prioritize Safety Verification
1. Write and run ALL safety tests first
2. Verify account guard with mocked scenarios
3. Then proceed with feature implementation

### Option C: Prototype-First Approach
1. Build simplest possible version (no ML, just rule-based)
2. Verify safety and execution
3. Add LSTM incrementally
4. Expand features

---

## 📞 Support

For questions or issues:
1. Check `docs/ARCHITECTURE.md`
2. Review `PROJECT_STATUS.md`
3. Read module docstrings
4. Check function signatures
5. Review test expectations

---

**Document Version**: 1.0  
**Last Updated**: 2026-10-29  
**Status**: Foundation Complete, Implementation In Progress
