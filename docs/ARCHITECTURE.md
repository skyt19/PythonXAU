# XAUUSD AI Farming HQ - System Architecture

## Overview

Farming HQ is a research platform for automated XAUUSD trading combining deep learning regime classification, rule-based strategy logic, and continuous post-trade learning. The architecture prioritizes safety, auditability, and scientific rigor.

## Design Principles

1. **Safety First**: Multiple independent layers prevent live trading
2. **Explicit Over Implicit**: No silent fallbacks or assumed configurations
3. **Fail Closed**: Unknown states block execution
4. **Immutable Audit Trail**: Every decision and outcome is logged
5. **Reproducibility**: Training, evaluation, and execution are deterministic
6. **Separation of Concerns**: Each module has a single, clear responsibility

## System Components

### 1. Broker Layer (`app/broker/`)

**Responsibility**: Interface with MetaTrader 5 and enforce demo-only execution.

**Key Modules**:
- `account_guard.py`: Multi-layer demo account verification
- `mt5_client.py`: MT5 connection, terminal health, reconnection
- `symbol_specs.py`: Instrument specifications from broker
- `execution.py`: Order submission with idempotency
- `reconciliation.py`: Broker state synchronization

**Safety Requirements**:
- ALL orders pass through `AccountGuard.verify_execution_safety()`
- Account mode, server, and login must match approved demo config
- No execution without successful preflight
- Order outcomes reconciled against broker deal history

**Inputs**:
- MT5 credentials from environment
- Demo server allowlist
- Execution requests from risk manager

**Outputs**:
- Verified account status
- Market data (OHLC, tick, spread)
- Symbol specifications
- Order confirmations
- Position and deal history

---

### 2. Data Layer (`app/data/`)

**Responsibility**: Collect, validate, store, and serve market data.

**Key Modules**:
- `collector.py`: Fetch M15 OHLC from MT5
- `validator.py`: OHLC consistency, gap detection, staleness
- `storage.py`: Persist to database
- `market_clock.py`: Trading hours, completed bar detection

**Data Flow**:
```
MT5 Terminal → Collector → Validator → Storage → Feature Engine
                                     ↓
                                 Alert on anomaly
```

**Quality Gates**:
- OHLC invariants (high ≥ close ≥ low, etc.)
- No duplicate timestamps
- Gap detection and logging
- Spread sanity checks
- Timestamp in UTC

---

### 3. Feature Engineering (`app/features/`)

**Responsibility**: Transform raw OHLC into model-ready features.

**Key Modules**:
- `indicators.py`: Technical indicators (EMA, ATR, ADX, RSI)
- `feature_builder.py`: Feature vector construction
- `feature_schema.py`: Schema versioning and validation

**Feature Requirements**:
- Causal validity: features available at decision time
- No look-ahead bias
- Preprocessing fit on training data only
- Feature versioning tied to model version

**Feature Categories**:
- Price-based: returns, log returns, normalized prices
- Trend: EMA cross, slope, alignment
- Volatility: ATR, realized vol, Bollinger bands
- Momentum: RSI, rate of change
- Market structure: highs/lows, support/resistance
- Time: hour, session, day-of-week
- Spread: current spread, percentile

---

### 4. Machine Learning (`app/ml/`)

**Responsibility**: Train, evaluate, and deploy LSTM regime classifier.

**Key Modules**:
- `dataset.py`: Sequence dataset with proper splitting
- `labels.py`: Regime label generation
- `lstm_model.py`: PyTorch model architecture
- `inference.py`: Production inference service
- `training.py`: Training loop with early stopping
- `evaluation.py`: Metrics and diagnostics
- `model_registry.py`: Versioned model storage
- `calibration.py`: Probability calibration
- `drift_detection.py`: Input distribution monitoring

**Training Pipeline**:
```
Raw Data → Features → Labels → Chronological Split → Train/Val/Test
                                                    ↓
                                              Model Training
                                                    ↓
                                         Evaluation vs Baselines
                                                    ↓
                                         Acceptance / Rejection
                                                    ↓
                                          Deployment (if approved)
```

**Model Outputs**:
- Regime class (TREND, RANGE, HIGH_VOLATILITY)
- Class probabilities
- Confidence score
- Uncertainty estimate

**Governance**:
- Immutable version IDs
- Training provenance recorded
- Candidate vs production separation
- Explicit promotion approval
- Rollback capability

---

### 5. Strategy Layer (`app/strategy/`)

**Responsibility**: Generate and filter trading signals.

**Key Modules**:
- `rules.py`: Rule-based entry/exit logic
- `regime_filter.py`: Regime-specific policies
- `signal_engine.py`: Signal generation orchestration

**Signal Flow**:
```
Market Data + Indicators → Rule Engine → Candidate Signal
                                             ↓
                           Regime Prediction → AI Filter → Approved Signal
                                             ↓
                                        Risk Manager → Execution
```

**Rules** (configurable):
- Trend detection (EMA alignment, ADX > threshold)
- Entry triggers (pullback, breakout)
- Stop-loss calculation (ATR-based)
- Take-profit calculation (risk-reward ratio)

**AI Filter**:
- TREND regime: approve trend-following signals
- RANGE regime: block trend signals (or use range strategy if implemented)
- HIGH_VOLATILITY: block or apply conservative rules
- Low confidence: block

---

### 6. Risk Management (`app/risk/`)

**Responsibility**: Enforce position sizing and risk limits.

**Key Modules**:
- `position_sizing.py`: Volume calculation from risk budget
- `limits.py`: Daily loss, drawdown, exposure checks
- `kill_switch.py`: Emergency stop and recovery

**Risk Checks** (independent of ML model):
- Max risk per trade (% of equity)
- Max daily realized + unrealized loss
- Max drawdown from high-water mark
- Max open positions
- Max spread
- Max slippage
- Minimum time between trades
- Trading hours restriction

**Position Sizing Algorithm**:
```
risk_dollars = equity * max_risk_per_trade
stop_distance_dollars = stop_distance_points * point_value * volume
volume = risk_dollars / (stop_distance_dollars / volume)
volume = round to broker volume_step, clamp to [min, max]
```

**Non-Martingale Enforcement**:
- Position size NEVER increases after losses
- No averaging down
- No grid expansion
- After daily loss breach: stop new entries

---

### 7. Learning System (`app/learning/`)

**Responsibility**: Analyze trade outcomes and trigger model improvement.

**Key Modules**:
- `trade_review.py`: Post-trade outcome analysis
- `error_analysis.py`: Classify prediction errors
- `experiment_manager.py`: Control training experiments

**Post-Trade Analysis**:
```
Trade Close → Reconcile with Broker → Extract Actual Outcome
                                             ↓
                           Compare with Prediction → Categorize Error
                                             ↓
                                    Store in Trade Journal
                                             ↓
                               Update Aggregate Metrics
```

**Error Categories**:
- Correct prediction
- Incorrect regime classification
- False positive entry
- Trend reversal
- Volatility expansion
- Execution cost (spread/slippage)
- Stop too tight/wide
- Data quality issue

**Learning Triggers** (NOT after every trade):
- Minimum observation threshold
- Scheduled evaluation period
- Significant drift detected
- Manual trigger

**Candidate Evaluation**:
- Train on new data
- Compare vs current model on holdout
- Require improvement on acceptance criteria
- Approve or reject with reason

---

### 8. Backtesting (`app/backtest/`)

**Responsibility**: Evaluate strategies on historical data.

**Key Modules**:
- `engine.py`: Walk-forward backtest orchestration
- `fill_simulator.py`: Realistic fill simulation
- `costs.py`: Spread, commission, swap, slippage
- `metrics.py`: Performance and risk metrics

**Backtest Requirements**:
- Chronological train/test splits
- Realistic bid/ask fills
- Actual spread from historical data
- Commission and swap from broker specs
- Slippage estimate
- No lookahead in features or labels
- Bootstrap uncertainty estimates

**Baselines**:
- B0: No-trade (zero P&L, zero cost)
- B1: Rule-only strategy (no AI)
- B2: Fixed regime rules (no ML)
- B3: Full system (LSTM filter)

---

### 9. Trading Service (`app/services/`)

**Responsibility**: Orchestrate execution loop and health monitoring.

**Key Modules**:
- `trading_service.py`: Main execution loop
- `scheduler.py`: Periodic tasks (data collection, evaluation)
- `health.py`: System health checks

**Execution Loop**:
```
Wait for completed M15 bar
  ↓
Collect market data
  ↓
Validate data quality
  ↓
Generate features
  ↓
LSTM inference → Regime prediction
  ↓
Strategy rules → Candidate signal
  ↓
AI filter → Approved signal (or NO TRADE)
  ↓
Risk manager → Position sizing
  ↓
Account guard → Execution safety check
  ↓
Submit order (if ALL checks pass)
  ↓
Reconcile broker state
```

**Health Checks**:
- MT5 connection alive
- Data freshness < threshold
- Model loaded and version current
- Disk space available
- Kill switch state
- Last successful reconciliation

---

### 10. Dashboard (`app/dashboard/`)

**Responsibility**: Operational monitoring and control interface.

**Components**:
- `api.py`: FastAPI backend with typed schemas
- `schemas.py`: Pydantic request/response models
- `templates/`: HTML pages
- `static/`: CSS and JavaScript

**Pages**:
- **Overview**: Account, market, positions, P&L, health
- **Live Market**: Chart with indicators and regime overlay
- **Learning Center**: Model versions, experiments, metrics
- **Trade Journal**: Complete order history with analysis
- **Strategy Lab**: Configuration, backtests
- **Risk & Health**: Limits, kill switch, alerts

**API Endpoints**:
- `GET /health`: System health
- `GET /account/status`: Account verification and execution state
- `GET /market/current`: Current XAUUSD state and prediction
- `GET /models/current`: Active model info
- `GET /trades`: Trade journal with filters
- `GET /metrics`: Performance metrics
- `POST /execution/enable`: Enable execution (requires preflight)
- `POST /execution/disable`: Kill switch
- `POST /training/trigger`: Start model training

**Security**:
- Bind to 127.0.0.1 only
- No credential exposure
- State-changing endpoints require confirmation
- Kill switch persisted to database

---

## Data Flow Diagram

```
MT5 Terminal
    ↓
Broker Adapter (account guard, symbol specs)
    ↓
Data Collector → Validator → Database
    ↓
Feature Engineer
    ↓
LSTM Model → Regime Prediction
    ↓
Rule Strategy → Candidate Signal
    ↓
AI Filter → Approved Signal
    ↓
Risk Manager → Position Size
    ↓
Execution (if safe)
    ↓
Trade Journal
    ↓
Learning System → Experiment Manager → Model Registry
    ↓
Dashboard
```

---

## State Management

**Persistent State** (SQLite database):
- Market data (OHLC)
- Regime predictions
- Signals (approved and rejected)
- Trades (entry, exit, analysis)
- Model versions and experiments
- System events
- Kill switch state

**In-Memory State**:
- Current feature vectors
- Model inference cache
- Health check status
- Active MT5 connection

**Configuration State** (environment + files):
- Risk limits
- Strategy parameters
- Model hyperparameters
- Broker credentials

---

## Safety Architecture

**Layer 1: Configuration**
- `DEMO_ONLY=true` required in environment

**Layer 2: Account Verification**
- MT5 account mode must be DEMO or CONTEST
- Server must match demo allowlist
- Login and server must match expected values

**Layer 3: Preflight Checks**
- Account verified
- Symbol available
- Data fresh
- Model loaded
- Risk limits configured

**Layer 4: Kill Switch**
- Persisted enabled/disabled state
- Manual enable required
- Automatic disable on breach

**Layer 5: Risk Veto**
- Independent risk manager
- Model cannot override rejection

**Layer 6: Reconciliation**
- Continuous verification against broker
- Detect unknown orders
- Stop on mismatch

---

## Testing Strategy

**Unit Tests**:
- Feature calculations (exact outputs)
- Label generation (edge cases)
- Position sizing (volume constraints)
- Cost calculations (spread, commission)

**Integration Tests**:
- Mock MT5 connection
- Mock account info
- End-to-end signal generation
- API endpoints

**Safety Tests**:
- Live account rejection
- Unknown account rejection
- Missing credentials
- Daily loss breach
- Drawdown breach
- Kill switch behavior
- Duplicate order prevention

**ML Tests**:
- Chronological splits
- No future leakage
- Preprocessing on train only
- Reproducible training

---

## Deployment

**Prerequisites**:
1. Windows with MT5 terminal installed
2. HFM Demo account created
3. Python 3.12+ environment
4. Sufficient historical data collected

**Startup Sequence**:
1. Load configuration
2. Initialize logging
3. Connect to database, create tables
4. Initialize MT5 connection
5. Verify demo account
6. Load active model
7. Start dashboard server
8. Execution DISABLED by default

**Execution Enable Sequence**:
1. User visits dashboard
2. Preflight checks run and display
3. User manually enables kill switch
4. Trading service begins signal generation
5. Orders submitted (if approved)

**Shutdown Sequence**:
1. Disable execution
2. Close open positions (if configured)
3. Disconnect MT5
4. Stop dashboard
5. Close database connections

---

## Monitoring and Alerts

**Critical Alerts**:
- Live account detected
- Unknown account
- Daily loss breach
- Drawdown breach
- Execution error
- Data staleness
- Model load failure
- Disk space low

**Operational Alerts**:
- Trade opened
- Trade closed
- Signal rejected (with reason)
- Model training started/completed
- New model promoted
- Kill switch triggered

**Alert Channels**:
- Dashboard notifications
- Log files (structured)
- Database events table

---

## Extension Points

**Adding Strategies**:
1. Implement new rule set in `strategy/rules.py`
2. Add regime-specific policy in `regime_filter.py`
3. Backtest against baselines
4. Document in `TRADING_RULES.md`

**Adding Features**:
1. Implement calculator in `features/indicators.py`
2. Update `feature_builder.py` to include
3. Version feature schema
4. Retrain model on new features
5. Compare vs previous model

**Adding Models**:
1. Implement architecture in `ml/`
2. Register in model registry
3. Implement inference interface
4. Backtest and compare
5. Promote if accepted

**Adding Risk Checks**:
1. Implement check in `risk/limits.py`
2. Add configuration parameter
3. Document in `RISK_POLICY.md`
4. Add safety test

---

## Performance Considerations

**Inference Latency**:
- Target: < 100ms per prediction
- LSTM forward pass on CPU acceptable for M15
- Feature calculation pre-computed where possible

**Data Storage**:
- SQLite adequate for single-instrument, M15 data
- Expect ~35,000 bars/year
- Database size: < 1 GB for multi-year history

**Dashboard Updates**:
- Polling every 5 seconds (configurable)
- WebSocket optional future enhancement

**Training Duration**:
- Expect 5-20 minutes for full retrain on CPU
- Run as background task
- User receives notification on completion

---

## Limitations and Future Work

**Current Limitations**:
- Single instrument (XAUUSD)
- Single timeframe (M15 primary)
- Windows only (MT5 requirement)
- Single broker (HFM)
- CPU-only training

**Planned Enhancements**:
- Multi-instrument support
- Multi-timeframe features
- Advanced order types (trailing stop, partial close)
- Range-specific strategy rules
- Volatility-adjusted position sizing
- GPU training support
- Cloud deployment option (with continued demo-only enforcement)
- Webhook notifications
- Advanced analytics dashboard

---

**Document Version**: 1.0
**Last Updated**: 2026-10-29
