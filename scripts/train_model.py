"""Train regime classification model"""
import argparse
import logging
from pathlib import Path
import sys

import torch
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ml.lstm_model import RegimeLSTM
from app.ml.baselines import MajorityClassBaseline, SimpleRuleBaseline, BaselineEvaluator
from app.ml.training import Trainer
from app.ml.evaluation import evaluate_model
from app.ml.dataset import load_datasets

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def train_baselines(train_data, val_data, test_data):
    """Train and evaluate baseline models."""
    logger.info("="*60)
    logger.info("Training Baseline Models")
    logger.info("="*60)

    X_train, y_train = train_data['X'], train_data['y']
    X_val, y_val = val_data['X'], val_data['y']
    X_test, y_test = test_data['X'], test_data['y']
    feature_names = train_data['feature_names']

    evaluator = BaselineEvaluator()
    results = {}

    # Majority class baseline
    logger.info("\n1. Majority Class Baseline")
    majority = MajorityClassBaseline()
    majority.fit(y_train)

    y_pred_val = majority.predict(X_val)
    val_metrics = evaluator.evaluate(y_val, y_pred_val, "Majority (Validation)")

    y_pred_test = majority.predict(X_test)
    test_metrics = evaluator.evaluate(y_test, y_pred_test, "Majority (Test)")
    results['majority'] = {'val': val_metrics, 'test': test_metrics}

    # Rule-based baseline
    logger.info("\n2. Rule-Based Baseline")
    rule = SimpleRuleBaseline()
    rule.fit(X_train, feature_names)

    y_pred_val = rule.predict(X_val)
    val_metrics = evaluator.evaluate(y_val, y_pred_val, "Rule-Based (Validation)")

    y_pred_test = rule.predict(X_test)
    test_metrics = evaluator.evaluate(y_test, y_pred_test, "Rule-Based (Test)")
    results['rule'] = {'val': val_metrics, 'test': test_metrics}

    return results


def train_lstm(train_dataset, val_dataset, test_dataset, args):
    """Train LSTM model."""
    logger.info("="*60)
    logger.info("Training LSTM Model")
    logger.info("="*60)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f"Using device: {device}")

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size)

    input_size = train_dataset[0][0].shape[1]

    model = RegimeLSTM(
        input_size=input_size,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
    )

    logger.info(f"Model: {sum(p.numel() for p in model.parameters())} parameters")

    save_path = Path(args.model_dir) / "best_model.pt"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    trainer = Trainer(model, device=device, learning_rate=args.lr)

    history = trainer.fit(
        train_loader,
        val_loader,
        epochs=args.epochs,
        patience=args.patience,
        save_path=save_path,
    )

    # Load best model
    checkpoint = torch.load(save_path, weights_only=True)
    model.load_state_dict(checkpoint['model_state'])

    # Evaluate
    logger.info("\n" + "="*60)
    logger.info("LSTM Validation Performance")
    logger.info("="*60)
    val_metrics = evaluate_model(model, val_loader, device)

    logger.info("\n" + "="*60)
    logger.info("LSTM Test Performance")
    logger.info("="*60)
    test_metrics = evaluate_model(model, test_loader, device)

    return {
        'val': val_metrics,
        'test': test_metrics,
        'history': history,
        'save_path': str(save_path),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str, required=True, help='Dataset pickle path')
    parser.add_argument('--model', type=str, default='lstm', choices=['baseline', 'lstm', 'all'])
    parser.add_argument('--model-dir', type=str, default='artifacts/models')
    parser.add_argument('--epochs', type=int, default=200)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--hidden-size', type=int, default=64)
    parser.add_argument('--num-layers', type=int, default=2)
    parser.add_argument('--dropout', type=float, default=0.3)
    parser.add_argument('--lr', type=float, default=0.001)
    parser.add_argument('--patience', type=int, default=20)

    args = parser.parse_args()

    logger.info(f"Loading datasets from {args.data}")
    datasets = load_datasets(args.data)

    train_data = datasets['train']
    val_data = datasets['val']
    test_data = datasets['test']
    train_dataset = datasets['train_dataset']
    val_dataset = datasets['val_dataset']
    test_dataset = datasets['test_dataset']

    logger.info(f"Train: {len(train_dataset)}, Val: {len(val_dataset)}, Test: {len(test_dataset)}")

    results = {}

    if args.model in ['baseline', 'all']:
        baseline_results = train_baselines(train_data, val_data, test_data)
        results['baselines'] = baseline_results

    if args.model in ['lstm', 'all']:
        lstm_results = train_lstm(train_dataset, val_dataset, test_dataset, args)
        results['lstm'] = lstm_results

    logger.info("\n" + "="*60)
    logger.info("Training Complete")
    logger.info("="*60)

    if 'baselines' in results and 'lstm' in results:
        logger.info("\nComparison (Test Set):")
        logger.info(f"  Majority: F1={results['baselines']['majority']['test']['f1_macro']:.4f}")
        logger.info(f"  Rule-Based: F1={results['baselines']['rule']['test']['f1_macro']:.4f}")
        logger.info(f"  LSTM: F1={results['lstm']['test']['f1']:.4f}")


if __name__ == '__main__':
    main()
