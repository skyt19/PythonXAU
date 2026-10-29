"""Run backtest with trained model"""
import argparse
import json
import logging
import pickle
import sys
from pathlib import Path

import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ml.lstm_model import RegimeLSTM
from app.strategy.signals import SignalGenerator
from app.backtest.engine import BacktestEngine
from app.risk.position_sizing import PositionSizer, RiskManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_model_and_data(model_path, dataset_path):
    """Load trained model and test data."""
    # Load model
    checkpoint = torch.load(model_path, weights_only=True)

    # Load dataset
    with open(dataset_path, 'rb') as f:
        datasets = pickle.load(f)

    test_dataset = datasets['test_dataset']
    scaler = datasets['scaler']
    feature_names = datasets['test']['feature_names']

    # Reconstruct model
    input_size = test_dataset[0][0].shape[1]
    model = RegimeLSTM(input_size=input_size, hidden_size=64, num_layers=2)
    model.load_state_dict(checkpoint['model_state'])
    model.eval()

    return model, test_dataset, scaler, feature_names


def generate_predictions(model, test_dataset, feature_names):
    """Generate regime predictions."""
    predictions = []

    for i in range(len(test_dataset)):
        X, y_true = test_dataset[i]
        X_batch = X.unsqueeze(0)

        with torch.no_grad():
            probs = model.predict_proba(X_batch)[0]
            pred = torch.argmax(probs).item()

        regime_names = ['TREND', 'RANGE', 'HIGH_VOLATILITY']

        # Extract features from last time step
        last_features = X[-1].numpy()
        feature_dict = {name: float(val) for name, val in zip(feature_names, last_features)}

        predictions.append({
            'idx': i,
            'regime': regime_names[pred],
            'probs': {regime_names[j]: float(probs[j]) for j in range(3)},
            'features': feature_dict,
        })

    return predictions


def run_backtest(df_test, predictions, args):
    """Run backtest with predictions."""
    signal_gen = SignalGenerator(confidence_threshold=args.confidence_threshold)

    signals = []
    for i, pred in enumerate(predictions):
        if i < len(df_test):
            timestamp = df_test.iloc[i]['timestamp']
            signal = signal_gen.generate(
                regime_pred=pred['regime'],
                regime_probs=pred['probs'],
                features=pred['features'],
                timestamp=timestamp,
            )
            signals.append(signal)

    # Run backtest
    engine = BacktestEngine(
        initial_balance=args.initial_balance,
        commission_per_lot=args.commission,
        slippage_pips=args.slippage,
        position_sizer=PositionSizer(max_risk_per_trade=args.max_risk),
        risk_manager=RiskManager(max_daily_loss=args.max_daily_loss),
    )

    result = engine.run(df_test, signals)

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=str, default='artifacts/models/best_model.pt')
    parser.add_argument('--data', type=str, default='data/dataset.pkl')
    parser.add_argument('--db', type=str, default='data/xauusd.db')
    parser.add_argument('--output', type=str, default='artifacts/backtest_results.json')
    parser.add_argument('--initial-balance', type=float, default=10000)
    parser.add_argument('--max-risk', type=float, default=0.02)
    parser.add_argument('--max-daily-loss', type=float, default=0.05)
    parser.add_argument('--commission', type=float, default=7.0)
    parser.add_argument('--slippage', type=float, default=1.0)
    parser.add_argument('--confidence-threshold', type=float, default=0.6)

    args = parser.parse_args()

    logger.info("="*60)
    logger.info("Backtest with LSTM Model")
    logger.info("="*60)

    # Load model and data
    logger.info(f"Loading model from {args.model}")
    logger.info(f"Loading dataset from {args.data}")
    model, test_dataset, scaler, feature_names = load_model_and_data(args.model, args.data)

    # Load test OHLC data
    import sqlite3
    conn = sqlite3.connect(args.db)
    df = pd.read_sql("SELECT * FROM ohlc ORDER BY timestamp", conn)
    conn.close()
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Get test portion (last 15%)
    test_size = int(len(df) * 0.15)
    df_test = df.iloc[-test_size:].reset_index(drop=True)
    logger.info(f"Test data: {len(df_test)} bars")

    # Generate predictions
    logger.info("Generating predictions...")
    predictions = generate_predictions(model, test_dataset, feature_names)
    logger.info(f"Generated {len(predictions)} predictions")

    # Run backtest
    logger.info("\nRunning backtest...")
    result = run_backtest(df_test, predictions, args)

    # Print results
    logger.info("\n" + "="*60)
    logger.info("BACKTEST RESULTS")
    logger.info("="*60)
    logger.info(f"Initial Balance: ${result.initial_balance:,.2f}")
    logger.info(f"Final Balance: ${result.final_balance:,.2f}")
    logger.info(f"Total Return: {result.total_return:.2%}")
    logger.info(f"Max Drawdown: {result.max_drawdown:.2%}")
    logger.info(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
    logger.info(f"Win Rate: {result.win_rate:.2%}")
    logger.info(f"Profit Factor: {result.profit_factor:.2f}")
    logger.info(f"Total Trades: {result.total_trades}")
    logger.info(f"Total Pips: {result.total_pips:+.1f}")
    logger.info(f"Avg Win: ${result.avg_win:.2f}")
    logger.info(f"Avg Loss: ${result.avg_loss:.2f}")
    logger.info(f"Total Commission: ${result.total_commission:.2f}")
    logger.info(f"Total Slippage: ${result.total_slippage:.2f}")

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(result.to_dict(), f, indent=2)
    logger.info(f"\nResults saved to {output_path}")


if __name__ == '__main__':
    main()
