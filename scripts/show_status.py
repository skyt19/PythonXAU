"""Display project status and results"""
import json
import sqlite3
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent))


def check_data():
    """Check data availability."""
    db_path = Path("data/xauusd.db")
    if not db_path.exists():
        print("❌ No data collected")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM ohlc")
    count, start, end = cursor.fetchone()
    conn.close()

    print(f"✅ Data: {count:,} bars ({start} to {end})")
    return True


def check_dataset():
    """Check if dataset is built."""
    dataset_path = Path("data/dataset.pkl")
    if not dataset_path.exists():
        print("❌ Dataset not built")
        return False

    import pickle
    with open(dataset_path, 'rb') as f:
        datasets = pickle.load(f)

    train_size = len(datasets['train_dataset'])
    val_size = len(datasets['val_dataset'])
    test_size = len(datasets['test_dataset'])
    n_features = len(datasets['train']['feature_names'])

    print(f"✅ Dataset: {train_size} train / {val_size} val / {test_size} test ({n_features} features)")
    return True


def check_model():
    """Check if model is trained."""
    model_path = Path("artifacts/models/best_model.pt")
    if not model_path.exists():
        print("❌ Model not trained")
        return False

    size_mb = model_path.stat().st_size / 1024 / 1024
    print(f"✅ Model trained: {model_path} ({size_mb:.1f} MB)")
    return True


def check_backtest():
    """Check backtest results."""
    results_path = Path("artifacts/backtest_results.json")
    if not results_path.exists():
        print("❌ No backtest results")
        return False

    with open(results_path) as f:
        results = json.load(f)

    print(f"✅ Backtest Results:")
    print(f"   Return: {results['total_return']:.2%}")
    print(f"   Sharpe: {results['sharpe_ratio']:.2f}")
    print(f"   Max DD: {results['max_drawdown']:.2%}")
    print(f"   Win Rate: {results['win_rate']:.2%}")
    print(f"   Trades: {results['total_trades']}")
    print(f"   Pips: {results['total_pips']:+.1f}")
    return True


def check_tests():
    """Check if tests pass."""
    import subprocess
    result = subprocess.run(
        ['python', '-m', 'pytest', 'tests/', '-v', '--tb=no'],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        # Count passed tests
        lines = result.stdout.split('\n')
        for line in lines:
            if 'passed' in line:
                print(f"✅ Tests: {line.strip()}")
                return True

    print(f"❌ Tests failed")
    return False


def main():
    print("=" * 60)
    print("PythonXAU Project Status")
    print("=" * 60)
    print()

    check_data()
    check_dataset()
    check_model()
    check_backtest()
    check_tests()

    print()
    print("=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. Configure MT5 credentials in .env")
    print("2. Collect real data: python scripts/collect_data.py --days 365")
    print("3. Rebuild dataset: python scripts/build_dataset.py")
    print("4. Retrain model: python scripts/train_model.py --data data/dataset.pkl --model all")
    print("5. Run backtest: python scripts/run_backtest.py")


if __name__ == '__main__':
    main()
