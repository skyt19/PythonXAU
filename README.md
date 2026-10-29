# PythonXAU - XAUUSD ML Trading System

**Research-only automated trading system for XAUUSD (Gold) using regime-based machine learning.**

## Status: Core Implementation Complete

### ✅ Completed Features

#### Data Pipeline
- MT5 integration with safety controls (demo-only, credentials required)
- SQLite storage with duplicate prevention
- Synthetic data generator for testing
- Feature engineering (28+ technical indicators)
- Regime labeling (TREND / RANGE / HIGH_VOLATILITY)

#### Machine Learning
- Dataset builder with chronological train/val/test splits (70/15/15)
- Baseline models (Majority Class, Rule-Based)
- LSTM regime classifier (PyTorch)
- Training loop with early stopping
- Model evaluation metrics

#### Strategy & Risk
- Signal generation based on regime predictions
- Position sizing (2% max risk per trade)
- Risk management (daily loss limits, max drawdown)
- Realistic backtesting with commission ($7/lot) and slippage (1 pip)

#### Testing
- Unit tests for risk management
- Unit tests for signal generation
- All tests passing

### Training Results (Synthetic Data)

```
Dataset: 25,008 M15 bars (365 days synthetic)
Train: 18,016 sequences | Val: 3,140 | Test: 3,703

Baseline Performance (Test Set):
- Majority Class: F1=0.32
- Rule-Based: F1=0.24
- LSTM: F1=0.32, Accuracy=93%

Note: Class imbalance (69% TREND, 9% RANGE, 22% HIGH_VOL)
caused model to predict only TREND class. This is expected
with synthetic random-walk data.
```

### Backtest Results (Synthetic Data)

```
8 trades executed
-16.69% return (all losses - expected on random data)
Commission: $1.12 | Slippage: $1.60
Win Rate: 0%
```

**Important:** These results use synthetic data. Real MT5 data collection requires:
- Valid MT5 demo account
- Configure `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` in `.env`
- Run: `python scripts/collect_data.py --days 365`

### Project Structure

```
PythonXAU/
├── app/
│   ├── data/          # MT5 connector, data collection
│   ├── features/      # Feature engineering, indicators
│   ├── ml/            # LSTM model, training, dataset
│   ├── strategy/      # Signal generation
│   ├── risk/          # Position sizing, risk management
│   └── backtest/      # Backtesting engine
├── scripts/
│   ├── collect_data.py       # Collect real MT5 data
│   ├── generate_test_data.py # Generate synthetic data
│   ├── build_dataset.py      # Build ML dataset
│   ├── train_model.py        # Train models
│   └── run_backtest.py       # Run backtest
├── tests/             # Unit tests
└── data/              # SQLite DB, datasets, models

```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Generate Test Data (or collect real MT5 data)

```bash
# Synthetic data for testing
python scripts/generate_test_data.py --days 365

# OR real MT5 data (requires credentials in .env)
python scripts/collect_data.py --days 365
```

### 3. Build Dataset

```bash
python scripts/build_dataset.py
```

### 4. Train Models

```bash
# Train all models (baselines + LSTM)
python scripts/train_model.py --data data/dataset.pkl --model all --epochs 100

# Or just LSTM
python scripts/train_model.py --data data/dataset.pkl --model lstm
```

### 5. Run Backtest

```bash
python scripts/run_backtest.py \
    --model artifacts/models/best_model.pt \
    --confidence-threshold 0.5
```

## Safety Features

### MT5 Integration
- **Demo accounts only** - live trading not supported
- Credentials validation before connection
- Account type verification (rejects live accounts)
- Order execution disabled by default

### Risk Management
- Max 2% risk per trade (configurable)
- Max 5% daily loss limit
- Max 15% drawdown limit
- 1 concurrent position max
- Stop loss on every trade

### Backtesting
- Realistic costs: $7 commission per lot, 1 pip slippage
- No look-ahead bias (chronological splits)
- Proper time-series handling (sequences)

## Data Requirements

**For Production Use:**
- Minimum 1 year of M15 XAUUSD data (35,000+ bars)
- Real MT5 demo account
- Clean, gap-free data

**Current Status:**
- Synthetic data used for development
- MT5 connector tested but requires credentials
- Ready for real data collection

## Model Performance Notes

The current LSTM model shows class imbalance issues (predicts only TREND). This is expected with:
- Synthetic random-walk data
- Highly imbalanced classes (69% TREND)

**Recommended fixes for real deployment:**
1. Collect real MT5 data (not random walk)
2. Use class weights in loss function
3. Adjust labeling thresholds
4. Try ensemble methods

## Architecture Decisions

### Why LSTM?
- Captures temporal dependencies in M15 data
- Learns regime patterns across 48-bar sequences (12 hours)
- Handles variable-length market conditions

### Why Regime Classification?
- More robust than price prediction
- Allows strategy adaptation to market conditions
- Reduces overfitting vs. direct signal prediction

### Why 70/15/15 Split?
- Chronological to prevent look-ahead bias
- 70% train ensures enough data for LSTM
- 15% test maintains realistic evaluation

## Known Limitations

1. **Model Performance**: Class imbalance causes poor minority class recall
2. **Data**: Synthetic data not representative of real market dynamics
3. **Strategy**: Simple trend-following; no mean-reversion or vol strategies
4. **Features**: Missing order flow, sentiment, macro indicators

## Next Steps for Production

1. **Data Collection**
   - [ ] Configure MT5 credentials
   - [ ] Collect 1+ year real M15 data
   - [ ] Validate data quality

2. **Model Improvements**
   - [ ] Add class weights to handle imbalance
   - [ ] Experiment with attention mechanisms
   - [ ] Try ensemble (LSTM + XGBoost)

3. **Strategy Enhancement**
   - [ ] Add mean-reversion for RANGE regime
   - [ ] Add volatility-based sizing
   - [ ] Implement trailing stops

4. **Infrastructure**
   - [ ] Model registry and versioning
   - [ ] Shadow trading mode (no execution)
   - [ ] Performance dashboard
   - [ ] Alerting system

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test suite
pytest tests/test_risk.py -v
pytest tests/test_strategy.py -v
```

## Configuration

Key parameters in scripts:
- `--sequence-length`: LSTM lookback (default: 48 = 12h)
- `--hidden-size`: LSTM hidden units (default: 64)
- `--max-risk`: Max risk per trade (default: 0.02 = 2%)
- `--confidence-threshold`: Min prediction confidence (default: 0.6)

## License

Research and educational use only. Not financial advice.

## Disclaimer

⚠️ **RESEARCH ONLY** ⚠️

This system is for research and education purposes only. Trading financial instruments carries significant risk of loss. Never trade with capital you cannot afford to lose. Past performance does not guarantee future results. Always test thoroughly on demo accounts before considering any real trading.

The developers assume no responsibility for financial losses incurred through use of this software.
