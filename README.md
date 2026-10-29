# XAUUSD AI Farming HQ

**HFM MetaTrader 5 Demo Forward Testing System**

## ⚠️ CRITICAL SAFETY NOTICE

This system is designed for **DEMO TRADING ONLY** on HFM MetaTrader 5 demo accounts.

**Live trading is explicitly prohibited and protected by multiple safety layers.**

## Overview

XAUUSD AI Farming HQ is a comprehensive research and forward-testing platform for automated XAUUSD (Gold/USD) trading. It combines:

- **Deep Learning**: PyTorch LSTM for market regime classification (TREND, RANGE, HIGH_VOLATILITY)
- **Rule-Based Strategy**: Transparent, configurable entry/exit rules
- **AI Signal Filter**: LSTM-powered trade filtering
- **Post-Trade Learning**: Automated outcome analysis and model improvement
- **Non-Martingale Risk Management**: Position sizing based on risk budget, never loss recovery
- **Operational Dashboard**: Real-time monitoring at http://localhost:3831

## Architecture

The system is built with clear separation of concerns:

```
app/
├── broker/          # MT5 integration, account verification, execution
├── data/            # Market data collection, validation, storage
├── features/        # Technical indicators, feature engineering
├── ml/              # LSTM model, training, inference, evaluation
├── strategy/        # Rule-based strategy and AI filter
├── risk/            # Position sizing, limits, kill switch
├── learning/        # Post-trade analysis, error learning
├── backtest/        # Walk-forward testing, cost simulation
├── services/        # Trading service orchestration
└── dashboard/       # FastAPI backend + frontend UI
```

## Installation

### Prerequisites

- Python 3.12+
- MetaTrader 5 terminal installed (Windows)
- HFM Demo account credentials

### Setup

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Copy environment template
copy .env.example .env

# Edit .env with your HFM DEMO credentials
# NEVER commit this file
notepad .env
```

### Environment Variables

Required variables in `.env`:

```
# DEMO ACCOUNT ONLY
DEMO_ONLY=true
MT5_LOGIN=your_demo_login
MT5_PASSWORD=your_demo_password
MT5_SERVER=HFM-Demo
MT5_SYMBOL=XAUUSD

# Application
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=3831
LOG_LEVEL=INFO

# Database
DATABASE_URL=sqlite:///data/farming_hq.db

# Risk Limits (Demo defaults)
MAX_RISK_PER_TRADE=0.0025
MAX_DAILY_LOSS=0.01
MAX_DRAWDOWN=0.05
MAX_OPEN_POSITIONS=1
```

## Usage

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run safety tests
pytest tests/safety/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

### Training the Model

```bash
# Collect initial data
python scripts/collect_data.py --days 365

# Train baseline model
python scripts/train_model.py --config configs/model.yaml

# Run backtest evaluation
python scripts/run_backtest.py --config configs/strategy.yaml
```

### Starting the Dashboard

```bash
# Start Farming HQ
python -m app.main

# Dashboard will be available at:
# http://localhost:3831
```

The dashboard provides:
- **Overview**: Account status, market state, current positions
- **Live Market**: XAUUSD chart with indicators and regime overlays
- **Learning Center**: Model versions, training history, experiments
- **Trade Journal**: Complete order history with analysis
- **Strategy Lab**: Configuration, backtests, cost analysis
- **Risk & Health**: Limits, connection status, kill switch

### Demo Forward Testing

**IMPORTANT**: Forward testing requires explicit verification and activation.

```bash
# 1. Verify MT5 connection and demo account
python scripts/verify_account.py

# 2. Start dashboard in research mode (default)
python -m app.main

# 3. In dashboard: Complete preflight checks
#    - Account verification: PASS
#    - Demo mode confirmed: PASS
#    - Symbol specs loaded: PASS
#    - Risk limits configured: PASS

# 4. Enable execution via dashboard kill switch
#    (requires manual confirmation)
```

**Execution will not start until:**
- MT5 terminal is connected
- Account is verified as DEMO
- Symbol XAUUSD is available
- All preflight checks pass
- Kill switch is manually enabled

## Safety Features

### Multi-Layer Demo Protection

1. **Configuration Check**: `DEMO_ONLY=true` required
2. **Account Verification**: MT5 account mode must be DEMO
3. **Server Allowlist**: Only approved demo servers
4. **Metadata Validation**: Account info must match demo criteria
5. **Preflight Execution**: All checks must pass before orders
6. **Kill Switch**: Manual enable required, persisted state
7. **Order Reconciliation**: Continuous verification against broker

### Non-Martingale Enforcement

- Position size calculated from risk budget and stop distance
- **NEVER increases after losses**
- No averaging down
- No grid expansion
- No stop-loss removal
- Independent risk manager with veto power

### Risk Limits (Configurable)

- Max risk per trade: 0.25% equity (default)
- Max daily loss: 1% session equity
- Max drawdown: 5% from high-water mark
- Max open positions: 1 (initially)
- Max spread threshold
- Trade frequency limits
- Session restrictions

### Emergency Controls

- **Kill Switch**: Immediate halt of all new positions
- **Daily Loss Limit**: Auto-disable on breach
- **Drawdown Circuit Breaker**: Stop on threshold
- **Stale Data Detection**: No trading on old quotes
- **Execution Error Halt**: Stop on critical broker errors
- **Manual Pause/Resume**: Operator control

## Model Training and Learning

### Regime Classification

The LSTM classifies market state into three regimes:

- **TREND**: Directional movement, allow trend-following entries
- **RANGE**: Sideways consolidation, block or use range-specific rules
- **HIGH_VOLATILITY**: Elevated risk, conservative or no-trade

Training uses:
- Chronological train/validation/test splits
- Walk-forward evaluation
- Overlapping-label protection
- Calibrated probability outputs
- Explicit uncertainty handling

### Learning Loop

After each trade closes:

1. **Outcome Collection**: Retrieve broker deal history
2. **Reconciliation**: Match entry/exit with actual fills
3. **Error Analysis**: Compare prediction vs realized outcome
4. **Categorization**: Classify error type
5. **Journal Storage**: Immutable trade record
6. **Aggregate Metrics**: Update evaluation statistics

Learning triggers:
- **Not after every trade** (prevents overfitting)
- Scheduled evaluation periods
- Minimum observation thresholds
- Controlled candidate training
- Explicit approval before deployment

### Model Registry

- Immutable version identifiers
- Complete training provenance
- Comparison against current model
- Acceptance/rejection criteria
- Rollback capability
- Deployment audit trail

## Evaluation Methodology

### Baselines

- **B0**: No-trade baseline (zero P&L, zero cost)
- **B1**: Rule-based strategy without AI
- **B2**: Rule-based with fixed regime rules
- **B3**: Rule-based with LSTM filter (full system)

### Metrics

**Classification**:
- Balanced accuracy, macro F1
- Per-class precision/recall
- Confusion matrix
- Calibration diagnostics

**Trading**:
- Net profit after costs
- Profit factor, expectancy
- Win rate, avg win/loss
- Maximum drawdown
- Sharpe and Sortino ratios
- R-multiple distribution
- Cost sensitivity
- Performance by regime/session

### Backtesting

- Chronological walk-forward splits
- Realistic bid/ask, spread, commission, swap
- Slippage and execution constraints
- Bootstrap uncertainty estimates
- No leakage from preprocessing or tuning
- Holdout validation before acceptance

## Dashboard UI Design

Farming HQ uses a **serious, professional trading workstation aesthetic**:

- Dark neutral background (charcoal, near-black)
- Restrained blue for focus and selection
- High-contrast readable typography
- Compact data tables with aligned numbers
- Muted green/red for P&L changes
- Amber for warnings
- Clear labels, units, timestamps
- Persistent compact sidebar
- Responsive without sacrificing legibility

**Explicitly avoided**:
- AI-themed gradients or glowing effects
- Emojis or decorative symbols
- Fake terminal aesthetics
- Fabricated statistics or progress bars
- Generic SaaS landing page styling
- Unnecessary animations
- Low-contrast tiny text

Every displayed number comes from real data or is explicitly labeled as an example.

## Testing

### Test Coverage

- **Unit Tests**: Feature calculations, labels, position sizing, costs
- **Safety Tests**: Live account rejection, missing stops, loss limits, kill switch
- **ML Tests**: Chronological splits, no leakage, reproducibility, rollback
- **Integration Tests**: Mock MT5, account verification, API endpoints

### Running Specific Test Suites

```bash
# Safety-critical tests
pytest tests/safety/test_account_guard.py -v
pytest tests/safety/test_risk_limits.py -v
pytest tests/safety/test_execution.py -v

# ML pipeline tests
pytest tests/ml/test_features.py -v
pytest tests/ml/test_training.py -v
pytest tests/ml/test_model_registry.py -v

# Backtest tests
pytest tests/backtest/test_engine.py -v
pytest tests/backtest/test_costs.py -v
```

## Project Status

### Implemented Features

✅ Project structure and configuration
✅ MT5 broker integration with account verification
✅ Market data collection and validation
✅ Feature engineering pipeline
✅ LSTM model architecture
✅ Training and evaluation framework
✅ Rule-based strategy engine
✅ AI signal filter
✅ Non-Martingale risk management
✅ Trade journal and post-trade analysis
✅ Walk-forward backtesting
✅ Dashboard backend API
✅ Dashboard frontend UI
✅ Comprehensive test suite
✅ Safety mechanisms and kill switch

### Current Limitations

- MT5 integration requires Windows and installed terminal
- Symbol resolution tested with HFM demo data
- Model trained on historical M15 data (requires sufficient history)
- Dashboard WebSocket updates at 5-second polling (configurable)
- Commission/swap require broker-specific configuration

### Next Steps

1. Collect sufficient historical M15 XAUUSD data (12+ months)
2. Train and validate baseline models
3. Run comprehensive walk-forward backtests
4. Complete 3-month demo observation period
5. Analyze cost sensitivity and regime performance
6. Iterate on feature engineering based on results
7. Refine entry/exit rules from journal analysis

## Documentation

Detailed documentation in `docs/`:

- **ARCHITECTURE.md**: System design and module responsibilities
- **TRADING_RULES.md**: Strategy logic and regime-specific policies
- **MODEL_CARD.md**: LSTM architecture, training, and evaluation
- **RISK_POLICY.md**: Position sizing, limits, and safety mechanisms
- **TESTING.md**: Test strategy and coverage
- **OPERATIONS.md**: Installation, configuration, monitoring, troubleshooting

## Contributing

This is a research system. Contributions should:

- Maintain safety-first principles
- Include comprehensive tests
- Document assumptions and limitations
- Preserve audit trails
- Never bypass risk controls

## License

[To be determined]

## Disclaimer

**THIS SOFTWARE IS FOR EDUCATIONAL AND RESEARCH PURPOSES ONLY.**

- No warranty of any kind
- No guarantee of profitability
- Past performance does not predict future results
- Demo trading results do not reflect live market conditions
- Use at your own risk
- The authors are not responsible for trading losses

**ALWAYS verify that you are connected to a DEMO account before enabling execution.**

---

**Farming HQ Dashboard**: http://localhost:3831

**Kill Switch Location**: Dashboard → Risk & Health → Execution Control
