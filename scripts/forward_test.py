"""
Forward Testing Script - Live DEMO Trading with Safety Guards

This script implements the forward-testing workflow:
1. Connects to HFM MT5 DEMO account
2. Verifies DEMO-only safety checks
3. Loads trained model and preprocessing
4. Processes M15 candles in real-time
5. Generates signals with AI model
6. Executes trades on DEMO account only
7. Monitors positions and manages exits
8. Logs all decisions and outcomes
"""
import argparse
import logging
import pickle
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import torch
import pandas_ta as ta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.broker.account_guard import AccountGuard, AccountVerification
from app.broker.mt5_client import MT5Client
from app.broker.symbol_specs import get_symbol_specs
from app.config import config
from app.data.collector import DataCollector
from app.database import (
    Base,
    Signal,
    SystemState,
    Trade,
    RegimePrediction,
    TradeDirection,
    OrderStatus,
    ExitReason,
    create_engine,
    sessionmaker,
)
from app.features.feature_builder import FeatureBuilder
from app.logging_config import setup_logging
from app.ml.lstm_model import RegimeLSTM
from app.risk.position_sizing import PositionSizer, RiskManager
from app.strategy.signals import SignalGenerator, SignalType

logger = logging.getLogger(__name__)




def _to_datetime(value):
    """Coerce a pandas Timestamp / numpy datetime to a plain datetime."""
    if value is None:
        return datetime.utcnow()
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    return value


def _json_safe(value):
    """
    Convert a feature mapping into JSON-serializable primitives.

    Feature frames carry pandas Timestamps and numpy scalars, which the
    JSON column cannot encode. Everything is coerced to plain Python types
    and any value that still cannot be represented is dropped.
    """
    safe = {}
    for key, val in dict(value).items():
        try:
            if hasattr(val, "item"):  # numpy scalar
                val = val.item()
            if hasattr(val, "isoformat"):  # datetime / Timestamp
                val = val.isoformat()
            elif hasattr(val, "timestamp"):  # pd.Timestamp
                val = str(val)
            if isinstance(val, (str, int, float, bool)) or val is None:
                safe[str(key)] = val
            else:
                safe[str(key)] = float(val)
        except Exception:
            continue
    return safe


class ForwardTester:
    """Forward testing orchestrator."""

    def __init__(
        self,
        symbol: str = "XAUUSD",
        timeframe: str = "M15",
        model_path: Path = Path("artifacts/models/best_model.pt"),
        dataset_path: Path = Path("data/dataset.pkl"),
        check_interval: int = 30,
        confidence_threshold: float = 0.6,
        max_risk_per_trade: float = 0.01,  # 1% risk
        max_spread_pips: float = 5.0,
        dry_run: bool = False,
    ):
        """
        Initialize forward tester.

        Args:
            symbol: Trading symbol
            timeframe: Trading timeframe
            model_path: Path to trained model
            dataset_path: Path to dataset with preprocessing
            check_interval: Seconds between checks
            confidence_threshold: Minimum confidence for trade
            max_risk_per_trade: Maximum risk per trade (fraction of balance)
            max_spread_pips: Maximum allowed spread in pips
            dry_run: If True, log signals but don't execute
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.model_path = model_path
        self.dataset_path = dataset_path
        self.check_interval = check_interval
        self.confidence_threshold = confidence_threshold
        self.max_risk_per_trade = max_risk_per_trade
        self.atr_period = config.atr_period
        self.max_spread_pips = max_spread_pips
        self.dry_run = dry_run

        # Components (initialized in setup)
        self.mt5_client: Optional[MT5Client] = None
        self.account_guard: Optional[AccountGuard] = None
        self.feature_builder: Optional[FeatureBuilder] = None
        self.model: Optional[RegimeLSTM] = None
        self.scaler = None
        self.feature_columns = None
        self.sequence_length = None
        self.signal_generator: Optional[SignalGenerator] = None
        self.position_sizer: Optional[PositionSizer] = None
        self.risk_manager: Optional[RiskManager] = None
        self.data_collector: Optional[DataCollector] = None

        # Database
        self.engine = None
        self.Session = None

        # State tracking
        self.processed_candles: Set[datetime] = set()
        self.running = False
        self.verified_account = None
        self._verified_login = None
        self._filling_mode = None
        self.last_heartbeat = None

        # Performance tracking
        self.session_start_equity = None
        self.session_high_water_mark = None

    def setup(self) -> bool:
        """Initialize all components."""
        try:
            logger.info("=" * 70)
            logger.info("FORWARD TESTING INITIALIZATION")
            logger.info("=" * 70)

            # 1. Setup database
            logger.info("Setting up database...")
            db_url = config.database_url
            self.engine = create_engine(db_url, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            logger.info(f"✓ Database: {db_url}")

            # 2. Load model and preprocessing
            logger.info("\nLoading model and preprocessing...")
            if not self._load_model_and_preprocessing():
                return False

            # 3. Initialize MT5 connection
            logger.info("\nConnecting to MT5...")
            self.mt5_client = MT5Client()
            # mt5.login() requires an integer account number; the config
            # value arrives from the environment as a string.
            login_value = None
            if config.mt5_login:
                try:
                    login_value = int(str(config.mt5_login).strip())
                except ValueError:
                    logger.error(
                        f"MT5_LOGIN must be numeric, got {config.mt5_login!r}"
                    )
                    return False

            if not self.mt5_client.connect(
                login=login_value,
                password=config.mt5_password,
                server=config.mt5_server,
            ):
                logger.error("Failed to connect to MT5")
                return False

            # 4. Verify symbol availability
            symbol_info = self.mt5_client.get_symbol_info(self.symbol)
            if symbol_info is None:
                logger.error(f"Symbol {self.symbol} not available")
                return False

            logger.info(
                f"✓ Symbol {self.symbol}: spread={symbol_info.spread} points, "
                f"volume_min={symbol_info.volume_min}, volume_step={symbol_info.volume_step}"
            )

            # 5. Initialize account guard
            logger.info("\nInitializing safety guard...")
            self.account_guard = AccountGuard(required_demo_only=True)

            # 6. Verify DEMO account
            verification = self.account_guard.verify_account(
                expected_login=login_value,
                expected_server=config.mt5_server,
            )

            if not verification.is_safe:
                logger.error("=" * 70)
                logger.error("DEMO ACCOUNT VERIFICATION FAILED")
                logger.error("=" * 70)
                logger.error(str(verification))
                logger.error("=" * 70)
                logger.error("EXECUTION BLOCKED FOR SAFETY")
                logger.error("=" * 70)
                return False

            self.verified_account = verification
            self._verified_login = login_value
            logger.info("\n" + "=" * 70)
            logger.info("✓ DEMO ACCOUNT VERIFIED")
            logger.info("=" * 70)
            logger.info(str(verification))
            logger.info("=" * 70)

            # Track session equity
            self.session_start_equity = verification.account_equity
            self.session_high_water_mark = verification.account_equity

            # 7. Initialize strategy components
            logger.info("\nInitializing strategy components...")
            self.signal_generator = SignalGenerator(
                confidence_threshold=self.confidence_threshold
            )
            # Build the sizer from REAL broker symbol metadata so the pip
            # value, volume limits and volume step come from the broker
            # rather than being assumed.
            broker_specs = get_symbol_specs(self.symbol)
            if broker_specs is None:
                logger.error("Could not read symbol specs from broker")
                return False

            # Value of one pip (0.10 price move) for 1.00 lot, in account
            # currency: ticks_per_pip * tick_value
            ticks_per_pip = 0.10 / broker_specs.trade_tick_size
            pip_value_per_lot = ticks_per_pip * broker_specs.trade_tick_value
            logger.info(
                f"  Broker pip value: ${pip_value_per_lot:.2f} per 1.00 lot "
                f"(tick_size={broker_specs.trade_tick_size}, "
                f"tick_value=${broker_specs.trade_tick_value})"
            )

            self.position_sizer = PositionSizer(
                max_risk_per_trade=self.max_risk_per_trade,
                max_lots=broker_specs.volume_max,
                min_lots=broker_specs.volume_min,
                pip_value_per_lot=pip_value_per_lot,
                volume_step=broker_specs.volume_step,
            )
            self.risk_manager = RiskManager(
                max_open_trades=1,
                max_daily_loss=0.05,  # 5%
                max_drawdown=0.15,  # 15%
            )
            logger.info("✓ Strategy components initialized")

            # 8. Initialize feature builder
            logger.info("\nInitializing feature builder...")
            self.feature_builder = FeatureBuilder()
            logger.info("✓ Feature builder initialized")

            # 9. Initialize data collector
            from app.data.validator import DataValidator

            self.data_collector = DataCollector(
                mt5_client=self.mt5_client,
                validator=DataValidator(
                    staleness_threshold_seconds=config.data_staleness_threshold
                ),
                symbol=self.symbol,
            )
            logger.info("✓ Data collector initialized")
            # 9b. Report whether this account can size a tradable position
            capacity = self._preflight_account_capacity()
            if capacity["can_trade"]:
                logger.info(f"  Account capacity: {capacity['reason']}")
            else:
                logger.warning(f"  Account capacity: {capacity['reason']}")
                logger.warning(
                    "  Orders will be rejected by the risk budget until the demo "
                    "account is funded. The system will keep running and logging."
                )

            # 10. Restore restart-safe state and reconcile broker positions
            logger.info("Restoring runtime state and reconciling positions...")
            self._load_runtime_state()
            self._reconcile_after_restart()
            self._persist_runtime_state()


            logger.info("\n" + "=" * 70)
            logger.info("✓ FORWARD TESTER READY")
            logger.info("=" * 70)
            logger.info(f"Symbol: {self.symbol}")
            logger.info(f"Timeframe: {self.timeframe}")
            logger.info(f"Model: {self.model_path}")
            logger.info(f"Features: {len(self.feature_columns)}")
            logger.info(f"Sequence length: {self.sequence_length}")
            logger.info(f"Check interval: {self.check_interval}s")
            logger.info(f"Confidence threshold: {self.confidence_threshold}")
            logger.info(f"Max spread: {self.max_spread_pips} pips")
            logger.info(f"Max risk per trade: {self.max_risk_per_trade:.1%}")
            logger.info(f"Dry run: {self.dry_run}")
            logger.info("=" * 70)

            return True

        except Exception as e:
            logger.error(f"Setup failed: {e}", exc_info=True)
            return False

    def _load_model_and_preprocessing(self) -> bool:
        """Load trained model and preprocessing artifacts."""
        try:
            # Load dataset metadata
            if not self.dataset_path.exists():
                logger.error(f"Dataset not found: {self.dataset_path}")
                logger.error("Run scripts/build_dataset.py first")
                return False

            with open(self.dataset_path, "rb") as f:
                dataset = pickle.load(f)

            metadata = dataset.get("metadata", {})
            self.scaler = dataset.get("scaler")
            self.feature_columns = metadata.get("feature_columns", [])
            self.sequence_length = metadata.get("sequence_length", 48)

            if not self.feature_columns:
                logger.error("No feature columns found in dataset")
                return False

            if self.scaler is None:
                logger.error("No scaler found in dataset")
                return False

            logger.info(f"✓ Preprocessing loaded: {len(self.feature_columns)} features")
            logger.info(f"  Feature columns: {self.feature_columns}")
            logger.info(f"  Sequence length: {self.sequence_length}")

            # Label thresholds used to train this model (provenance)
            thresholds = metadata.get("label_thresholds")
            if thresholds:
                logger.info(
                    f"  Label thresholds: trend={thresholds.get('trend_threshold'):.4%}, "
                    f"volatility={thresholds.get('volatility_threshold'):.4%}, "
                    f"lookforward={thresholds.get('lookforward')} bars"
                )
            else:
                logger.info("  Label thresholds: not recorded in dataset metadata")

            # Load model - infer architecture from checkpoint tensor shapes
            if not self.model_path.exists():
                logger.error(f"Model not found: {self.model_path}")
                logger.error("Run scripts/train_model.py first")
                return False

            checkpoint = torch.load(self.model_path, map_location="cpu", weights_only=True)

            # Checkpoint format from train_model.py: {"model_state": OrderedDict, ...}
            if "model_state" not in checkpoint:
                logger.error(
                    f"Invalid checkpoint format. Expected 'model_state' key, "
                    f"found: {list(checkpoint.keys())}"
                )
                return False

            state_dict = checkpoint["model_state"]

            # Infer architecture from weight shapes (do not hardcode).
            # PyTorch LSTM stores:
            #   weight_ih_lK = (4*hidden_size, input_size_of_layer_K)
            #   weight_hh_lK = (4*hidden_size, hidden_size)
            try:
                input_size = state_dict["lstm.weight_ih_l0"].shape[1]
                hidden_size = state_dict["lstm.weight_hh_l0"].shape[1]
                num_layers = 1 + max(
                    int(k.split("_l")[-1]) for k in state_dict if "weight_ih_l" in k
                )
                num_classes = state_dict["fc.weight"].shape[0]
            except KeyError as e:
                logger.error(f"Cannot infer model architecture from checkpoint: {e}")
                return False

            # Validate against the feature schema we loaded
            if input_size != len(self.feature_columns):
                logger.error(
                    f"Model input size mismatch: checkpoint expects {input_size} features, "
                    f"dataset provides {len(self.feature_columns)}"
                )
                logger.error("Rebuild dataset and retrain model to resolve this")
                return False

            logger.info(
                f"  Model architecture: input={input_size}, hidden={hidden_size}, "
                f"layers={num_layers}, classes={num_classes}"
            )

            self.model = RegimeLSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=0.3,
            )

            self.model.load_state_dict(state_dict)
            self.model.eval()

            logger.info(f"✓ Model loaded: {self.model_path}")
            logger.info(f"  Parameters: {sum(p.numel() for p in self.model.parameters())}")

            return True

        except Exception as e:
            logger.error(f"Failed to load model/preprocessing: {e}", exc_info=True)
            return False

    def run(self):
        """Main forward testing loop."""
        self.running = True
        self.last_heartbeat = datetime.utcnow()

        logger.info("\n" + "=" * 70)
        logger.info("STARTING FORWARD TESTING")
        logger.info("=" * 70)
        logger.info("Press Ctrl+C to stop gracefully")
        logger.info("=" * 70 + "\n")

        cycle_count = 0

        try:
            while self.running:
                cycle_count += 1
                cycle_start = time.time()

                # Heartbeat log every 5 minutes
                now = datetime.utcnow()
                if (now - self.last_heartbeat).total_seconds() >= 300:
                    self._log_heartbeat(cycle_count)
                    self.last_heartbeat = now

                # Process new candles
                try:
                    self._process_cycle()
                except Exception as e:
                    logger.error(f"Cycle {cycle_count} error: {e}", exc_info=True)
                    # Don't crash, continue running

                # Sleep until next check
                cycle_duration = time.time() - cycle_start
                sleep_time = max(0, self.check_interval - cycle_duration)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("\n" + "=" * 70)
            logger.info("SHUTDOWN REQUESTED")
            logger.info("=" * 70)
        finally:
            self.shutdown()

    def _process_cycle(self):
        """Process one cycle: reconcile positions, check for new candles, act."""
        # Always reconcile open positions first, regardless of candle state.
        self._monitor_open_positions()

        # Get latest completed candle
        candle = self._get_latest_completed_candle()
        if candle is None:
            return

        candle_time = candle["timestamp"]

        # Skip if already processed
        if candle_time in self.processed_candles:
            return

        logger.info("=" * 70)
        logger.info(f"NEW CANDLE: {candle_time} | O={candle['open']:.2f} H={candle['high']:.2f} "
                    f"L={candle['low']:.2f} C={candle['close']:.2f}")
        logger.info("=" * 70)

        # Mark as processed immediately to prevent duplicates
        self.processed_candles.add(candle_time)

        # Keep only last 1000 candle timestamps in memory
        if len(self.processed_candles) > 1000:
            oldest = sorted(self.processed_candles)[:-1000]
            for old_time in oldest:
                self.processed_candles.discard(old_time)

        # Fetch enough history to compute features
        history = self._fetch_feature_history(candle_time)
        if history is None or len(history) < self.sequence_length:
            logger.warning(
                f"Insufficient history: {len(history) if history is not None else 0} bars"
            )
            return

        # Build features
        features_df = self._build_features(history)
        if features_df is None or len(features_df) < self.sequence_length:
            logger.warning("Feature computation failed or insufficient")
            return

        # Get the latest feature row for the completed candle
        # Ensure we're using only information available at candle close
        latest_features = features_df.iloc[-1]

        # Prepare model input
        model_input = self._prepare_model_input(features_df)
        if model_input is None:
            return

        # Generate prediction
        prediction = self._generate_prediction(model_input, latest_features, candle_time)
        if prediction is None:
            return

        # Generate signal
        signal_result = self._generate_signal(prediction, latest_features, candle_time, candle)
        if signal_result is None:
            return

        # Execute trade if signal is valid
        if signal_result["action"] != "HOLD":
            self._execute_trade(signal_result, candle)

    def _get_latest_completed_candle(self) -> Optional[dict]:
        """Get the latest completed M15 candle."""
        try:
            # Fetch last 5 candles
            rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M15, 0, 5)
            if rates is None or len(rates) == 0:
                return None

            # The last candle might be incomplete, use second-to-last
            if len(rates) < 2:
                return None

            latest_complete = rates[-2]

            return {
                "timestamp": pd.to_datetime(latest_complete["time"], unit="s"),
                "open": latest_complete["open"],
                "high": latest_complete["high"],
                "low": latest_complete["low"],
                "close": latest_complete["close"],
                "tick_volume": latest_complete["tick_volume"],
                "spread": latest_complete["spread"],
                "real_volume": latest_complete["real_volume"],
            }

        except Exception as e:
            logger.error(f"Failed to get latest candle: {e}")
            return None

    def _fetch_feature_history(self, up_to_time: datetime) -> Optional[pd.DataFrame]:
        """Fetch historical data for feature computation."""
        try:
            # Fetch enough M15 bars for the full indicator warmup (EMA200)
            # plus the model sequence window, with headroom.
            bars_needed = max(400, self.sequence_length + 300)
            rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M15, 1, bars_needed)

            if rates is None or len(rates) == 0:
                logger.error("Failed to fetch history")
                return None

            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df["timestamp"] = pd.to_datetime(df["time"], unit="s")
            df = df.rename(
                columns={
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "tick_volume": "tick_volume",
                    "spread": "spread",
                    "real_volume": "real_volume",
                }
            )

            # Only use candles up to and including the target time
            df = df[df["timestamp"] <= up_to_time]

            return df

        except Exception as e:
            logger.error(f"Failed to fetch history: {e}", exc_info=True)
            return None

    def _build_features(self, history: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Build features from historical data."""
        try:
            # Use feature builder
            features_df = self.feature_builder.build_features(history)

            # Drop rows with NaN (from indicator warmup)
            features_df = features_df.dropna()

            if len(features_df) == 0:
                logger.warning("No valid features after dropping NaN")
                return None

            return features_df

        except Exception as e:
            logger.error(f"Feature building failed: {e}", exc_info=True)
            return None

    def _prepare_model_input(self, features_df: pd.DataFrame) -> Optional[torch.Tensor]:
        """Prepare scaled sequence for model input."""
        try:
            # Extract feature columns in correct order
            feature_values = features_df[self.feature_columns].values

            if len(feature_values) < self.sequence_length:
                logger.warning(
                    f"Not enough features: {len(feature_values)} < {self.sequence_length}"
                )
                return None

            # Scale features
            scaled_features = self.scaler.transform(feature_values)

            # Get last sequence
            sequence = scaled_features[-self.sequence_length :]

            # Convert to tensor [1, seq_len, features]
            tensor = torch.FloatTensor(sequence).unsqueeze(0)

            return tensor

        except Exception as e:
            logger.error(f"Failed to prepare model input: {e}", exc_info=True)
            return None

    def _generate_prediction(
        self, model_input: torch.Tensor, latest_features: pd.Series, timestamp: datetime
    ) -> Optional[dict]:
        """Generate model prediction."""
        try:
            with torch.no_grad():
                logits = self.model(model_input)
                probs = torch.softmax(logits, dim=1)[0]

            # Map to regime labels
            regime_map = {0: "TREND", 1: "RANGE", 2: "HIGH_VOLATILITY"}
            pred_idx = torch.argmax(probs).item()
            regime_pred = regime_map[pred_idx]

            regime_probs = {
                "TREND": probs[0].item(),
                "RANGE": probs[1].item(),
                "HIGH_VOLATILITY": probs[2].item(),
            }

            confidence = probs[pred_idx].item()

            logger.info(f"Prediction: {regime_pred} (confidence={confidence:.2%})")
            logger.info(
                f"  Probs: TREND={regime_probs['TREND']:.2%}, "
                f"RANGE={regime_probs['RANGE']:.2%}, "
                f"HIGH_VOL={regime_probs['HIGH_VOLATILITY']:.2%}"
            )

            return {
                "regime": regime_pred,
                "confidence": confidence,
                "regime_probs": regime_probs,
                "timestamp": timestamp,
            }

        except Exception as e:
            logger.error(f"Prediction failed: {e}", exc_info=True)
            return None

    def _generate_signal(
        self,
        prediction: dict,
        latest_features: pd.Series,
        timestamp: datetime,
        candle: dict,
    ) -> Optional[dict]:
        """Generate trading signal from prediction."""
        try:
            # Convert features to dict
            features_dict = latest_features.to_dict()

            # Generate signal
            trading_signal = self.signal_generator.generate(
                regime_pred=prediction["regime"],
                regime_probs=prediction["regime_probs"],
                features=features_dict,
                timestamp=timestamp,
            )

            logger.info(
                f"Signal: {trading_signal.signal.value} "
                f"(regime={trading_signal.regime}, confidence={trading_signal.confidence:.2%})"
            )

            # Map signal to action
            if trading_signal.signal == SignalType.LONG:
                action = "BUY"
            elif trading_signal.signal == SignalType.SHORT:
                action = "SELL"
            else:
                action = "HOLD"

            if action == "HOLD":
                logger.info("→ No trade signal")
                self._save_signal_to_db(
                    trading_signal, candle, ai_approved=False, rejection_reason="HOLD signal"
                )
                return None

            # Check confidence
            if trading_signal.confidence < self.confidence_threshold:
                logger.info(
                    f"→ Confidence too low: {trading_signal.confidence:.2%} < {self.confidence_threshold:.2%}"
                )
                self._save_signal_to_db(
                    trading_signal,
                    candle,
                    ai_approved=False,
                    rejection_reason="Confidence below threshold",
                )
                return None

            return {
                "action": action,
                "signal": trading_signal,
                "candle": candle,
            }

        except Exception as e:
            logger.error(f"Signal generation failed: {e}", exc_info=True)
            return None

    def _execute_trade(self, signal_result: dict, candle: dict):
        """Execute trade with full safety checks."""
        action = signal_result["action"]
        trading_signal = signal_result["signal"]

        logger.info("=" * 70)
        logger.info(f"TRADE SIGNAL: {action}")
        logger.info("=" * 70)

        try:
            # 1. Re-verify DEMO account before execution
            logger.info("1. Verifying DEMO account...")
            is_safe, reason = self.account_guard.verify_execution_safety(
                expected_login=self._verified_login,
                expected_server=config.mt5_server,
            )

            if not is_safe:
                logger.error(f"✗ EXECUTION BLOCKED: {reason}")
                self._save_signal_to_db(
                    trading_signal,
                    candle,
                    ai_approved=False,
                    rejection_reason=f"Safety check failed: {reason}",
                )
                return

            logger.info("✓ DEMO account verified")

            # 2. Check current market data
            logger.info("2. Checking market conditions...")
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                logger.error("✗ Could not get current tick")
                self._save_signal_to_db(
                    trading_signal,
                    candle,
                    ai_approved=False,
                    rejection_reason="Could not get current tick",
                )
                return

            # Check spread.
            # symbol_info.spread is in POINTS. 1 pip = 0.10 price move.
            # For XAUUSD (point=0.01): 34 points = 0.34 price = 3.4 pips.
            symbol_info = mt5.symbol_info(self.symbol)
            current_spread_pips = symbol_info.spread * symbol_info.point * 10

            if current_spread_pips > self.max_spread_pips:
                logger.warning(
                    f"✗ Spread too wide: {current_spread_pips:.1f} > {self.max_spread_pips:.1f} pips"
                )
                self._save_signal_to_db(
                    trading_signal,
                    candle,
                    ai_approved=False,
                    rejection_reason=f"Spread too wide: {current_spread_pips:.1f} pips",
                )
                return

            logger.info(f"✓ Spread OK: {current_spread_pips:.1f} pips")

            # 3. Get account info
            logger.info("3. Checking account status...")
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("✗ Could not get account info")
                return

            balance = account_info.balance
            equity = account_info.equity
            logger.info(f"  Balance: ${balance:,.2f}, Equity: ${equity:,.2f}")

            # 4. Check risk limits
            logger.info("4. Checking risk limits...")
            open_positions = len(mt5.positions_get(symbol=self.symbol))
            daily_pnl = equity - self.session_start_equity

            can_trade, risk_reason = self.risk_manager.can_open_trade(
                balance=balance,
                equity=equity,
                peak_balance=self.session_high_water_mark,
                daily_pnl=daily_pnl,
                open_positions=open_positions,
            )

            if not can_trade:
                logger.warning(f"✗ Risk limit: {risk_reason}")
                self._save_signal_to_db(
                    trading_signal,
                    candle,
                    ai_approved=False,
                    rejection_reason=f"Risk limit: {risk_reason}",
                )
                return

            logger.info(f"✓ Risk checks passed (open positions: {open_positions})")

            # 5. Calculate position size
            logger.info("5. Calculating position size...")
            entry_price = tick.ask if action == "BUY" else tick.bid

            # Stop loss distance from ATR (falls back to a percentage of price
            # when ATR is unavailable). ATR keeps stops proportional to current
            # volatility instead of using a fixed fraction of price.
            atr_value = self._latest_atr()
            if atr_value and atr_value > 0:
                stop_loss_distance = atr_value * config.atr_stop_multiplier
                stop_basis = f"ATR({self.atr_period}) x {config.atr_stop_multiplier}"
            else:
                stop_loss_distance = entry_price * 0.02
                stop_basis = "2% of price (ATR unavailable)"

            stop_loss_price = (
                entry_price - stop_loss_distance
                if action == "BUY"
                else entry_price + stop_loss_distance
            )
            take_profit_price = (
                entry_price + stop_loss_distance * config.risk_reward_ratio
                if action == "BUY"
                else entry_price - stop_loss_distance * config.risk_reward_ratio
            )
            logger.info(f"  Stop distance from {stop_basis}: {stop_loss_distance:.2f}")

            position_size = self.position_sizer.calculate(
                balance=balance,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                confidence=trading_signal.confidence,
            )

            if position_size is None:
                logger.error("✗ Could not calculate position size")
                self._save_signal_to_db(
                    trading_signal,
                    candle,
                    ai_approved=False,
                    rejection_reason="Position size calculation failed",
                )
                return

            # Validate volume against broker limits.
            # NOTE: the volume is NOT rounded up to the broker minimum here.
            # PositionSizer.calculate() already rejects the trade when the
            # smallest tradable lot would exceed the risk budget, so rounding
            # up here would re-introduce a risk breach.
            if position_size.lots < symbol_info.volume_min:
                logger.error(
                    f"✗ Volume {position_size.lots} below broker minimum "
                    f"{symbol_info.volume_min} - rejecting"
                )
                self._save_signal_to_db(
                    trading_signal,
                    candle,
                    ai_approved=False,
                    rejection_reason="Volume below broker minimum",
                )
                return

            if position_size.lots > symbol_info.volume_max:
                logger.error(
                    f"✗ Volume {position_size.lots} above broker maximum "
                    f"{symbol_info.volume_max} - rejecting"
                )
                self._save_signal_to_db(
                    trading_signal,
                    candle,
                    ai_approved=False,
                    rejection_reason="Volume above broker maximum",
                )
                return

            logger.info(f"  Volume: {position_size.lots} lots")
            logger.info(f"  Entry: {entry_price:.2f}")
            logger.info(f"  Stop Loss: {stop_loss_price:.2f} ({position_size.stop_distance_pips:.1f} pips)")
            logger.info(f"  Take Profit: {take_profit_price:.2f}")
            logger.info(f"  Risk: ${position_size.risk_amount:.2f}")

            # Save signal as approved
            signal_id = self._save_signal_to_db(
                trading_signal,
                candle,
                ai_approved=True,
                rejection_reason=None,
                entry_price=entry_price,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price,
                volume=position_size.lots,
                risk_amount=position_size.risk_amount,
            )

            # 6. Execute order
            if self.dry_run:
                logger.info("=" * 70)
                logger.info("DRY RUN MODE: Order would be submitted")
                logger.info("=" * 70)
                return

            logger.info("6. Submitting order...")
            order_result = self._submit_order(
                action=action,
                volume=position_size.lots,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price,
            )

            if order_result is None:
                logger.error("✗ Order submission failed")
                return

            logger.info("=" * 70)
            logger.info("✓ ORDER EXECUTED")
            logger.info("=" * 70)
            logger.info(f"  Order: {order_result['order']}")
            logger.info(f"  Deal: {order_result.get('deal', 'N/A')}")
            logger.info(f"  Price: {order_result['price']:.2f}")
            logger.info(f"  Volume: {order_result['volume']} lots")
            logger.info("=" * 70)

            # Save trade to database
            self._save_trade_to_db(order_result, signal_id, candle, action, position_size)

        except Exception as e:
            logger.error(f"Trade execution error: {e}", exc_info=True)

    def _resolve_filling_mode(self, symbol_info) -> int:
        """
        Choose a filling mode this broker actually accepts for this symbol.

        symbol_info.filling_mode is a mask whose meaning does not line up
        with the ORDER_FILLING_* request values (ORDER_FILLING_FOK is 0, so
        it contributes no bits). On the HFM demo server the advertised mask
        is 1 while the server only accepts FOK, so the mask cannot be
        trusted on its own.

        The mode is therefore probed with order_check, which validates a
        request without sending an order, and the first mode the server
        accepts is cached.
        """
        if self._filling_mode is not None:
            return self._filling_mode

        candidates = [
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_RETURN,
        ]

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            logger.warning("No tick available; defaulting to FOK")
            self._filling_mode = mt5.ORDER_FILLING_FOK
            return self._filling_mode

        price = tick.ask
        for mode in candidates:
            probe = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": 0.01,
                "type": mt5.ORDER_TYPE_BUY,
                "price": price,
                "deviation": 20,
                "magic": 234000,
                "comment": "probe",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mode,
            }
            try:
                check = mt5.order_check(probe)
            except Exception:
                continue

            if check is None:
                continue

            comment = str(getattr(check, "comment", "") or "").lower()
            if "unsupported filling mode" in comment:
                logger.debug(f"Filling mode {mode} rejected by broker: {comment}")
                continue

            # order_check reports retcode 0 with a populated margin when the
            # request is acceptable. A rejected request returns retcode 10030
            # (unsupported filling mode) with zeroed balance/margin.
            if check.retcode == 0 and getattr(check, "margin_free", 0) > 0:
                logger.info(
                    f"  Broker accepted filling mode {mode} "
                    f"(advertised mask {symbol_info.filling_mode})"
                )
                self._filling_mode = mode
                return mode

        logger.warning(
            "Could not determine a supported filling mode; defaulting to FOK"
        )
        self._filling_mode = mt5.ORDER_FILLING_FOK
        return self._filling_mode

    def _submit_order(
        self,
        action: str,
        volume: float,
        stop_loss: float,
        take_profit: float,
    ) -> Optional[dict]:
        """Submit order to MT5."""
        try:
            # Prepare request
            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info is None:
                logger.error("Symbol info not available")
                return None

            # Get current prices
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                logger.error("Tick info not available")
                return None

            order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
            price = tick.ask if action == "BUY" else tick.bid

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": stop_loss,
                "tp": take_profit,
                "deviation": 20,  # Max deviation in points
                "magic": 234000,
                "comment": "PythonXAU Forward Test",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": self._resolve_filling_mode(symbol_info),
            }

            # Validate the request against the broker before sending.
            # order_check does not place an order; it reports whether the
            # request would be accepted (margin, stops level, volume, etc).
            check = mt5.order_check(request)
            if check is None:
                logger.error("order_check returned None - cannot validate request")
                return None

            # order_check uses retcode 0 for an acceptable request and
            # retcode 10030 ("Unsupported filling mode") or a specific error
            # code otherwise. Balance/margin are only populated when the
            # request was actually evaluated.
            if check.retcode != 0:
                logger.error(
                    f"Order rejected by pre-check: retcode={check.retcode} "
                    f"comment={check.comment} "
                    f"balance={getattr(check, 'balance', None)} "
                    f"margin={getattr(check, 'margin', None)}"
                )
                return None

            logger.info(
                f"  Pre-check OK: margin=${getattr(check, 'margin', 0):.2f} "
                f"free=${getattr(check, 'margin_free', 0):.2f} "
                f"balance=${getattr(check, 'balance', 0):.2f}"
            )

            # Send order
            result = mt5.order_send(request)

            if result is None:
                logger.error("order_send returned None")
                return None

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Order failed: {result.retcode} - {result.comment}")
                return None

            return {
                "order": result.order,
                "deal": result.deal,
                "price": result.price,
                "volume": result.volume,
                "request": request,
                "result": result,
            }

        except Exception as e:
            logger.error(f"Order submission error: {e}", exc_info=True)
            return None

    def _save_signal_to_db(
        self,
        trading_signal,
        candle: dict,
        ai_approved: bool,
        rejection_reason: Optional[str],
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        volume: Optional[float] = None,
        risk_amount: Optional[float] = None,
    ) -> Optional[int]:
        """Save signal to database."""
        try:
            session = self.Session()

            direction = (
                TradeDirection.LONG
                if trading_signal.signal == SignalType.LONG
                else TradeDirection.SHORT
                if trading_signal.signal == SignalType.SHORT
                else None
            )

            # Use candle close as default entry if not provided
            if entry_price is None:
                entry_price = candle["close"]
            if stop_loss is None:
                stop_loss = entry_price * 0.98 if direction == TradeDirection.LONG else entry_price * 1.02
            if take_profit is None:
                take_profit = entry_price * 1.02 if direction == TradeDirection.LONG else entry_price * 0.98
            if volume is None:
                volume = 0.01
            if risk_amount is None:
                risk_amount = 0.0

            ts = trading_signal.timestamp
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()

            signal = Signal(
                timestamp=ts,
                direction=direction if direction else TradeDirection.LONG,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                volume=volume,
                risk_amount=risk_amount,
                ai_approved=ai_approved,
                rejection_reason=rejection_reason,
                strategy_reason=f"{trading_signal.regime} regime, confidence={trading_signal.confidence:.2%}",
                indicators_snapshot=_json_safe(trading_signal.features),
            )

            session.add(signal)
            session.commit()

            signal_id = signal.id
            session.close()

            return signal_id

        except Exception as e:
            logger.error(f"Failed to save signal: {e}", exc_info=True)
            return None

    def _save_trade_to_db(
        self,
        order_result: dict,
        signal_id: Optional[int],
        candle: dict,
        action: str,
        position_size,
    ):
        """Save executed trade to database."""
        try:
            session = self.Session()

            direction = TradeDirection.LONG if action == "BUY" else TradeDirection.SHORT

            trade = Trade(
                signal_id=signal_id,
                broker_order_id=str(order_result["order"]),
                entry_timestamp=_to_datetime(candle["timestamp"]),
                direction=direction,
                entry_price_expected=order_result["request"]["price"],
                entry_price_actual=order_result["price"],
                volume=order_result["volume"],
                stop_loss=order_result["request"]["sl"],
                take_profit=order_result["request"]["tp"],
                status=OrderStatus.FILLED,
            )

            session.add(trade)
            session.commit()
            session.close()

            logger.info(f"Trade saved to database: ID={trade.id}")

        except Exception as e:
            logger.error(f"Failed to save trade: {e}", exc_info=True)

    def _load_runtime_state(self):
        """
        Load restart-safe runtime state from the database.

        Prevents duplicate processing of candles that were already handled
        before a restart, and restores the session equity baseline.
        """
        try:
            session = self.Session()

            # Restore the last processed candle time from saved signals
            from app.database import Signal as SignalModel

            last_signal = (
                session.query(SignalModel)
                .order_by(SignalModel.timestamp.desc())
                .first()
            )
            if last_signal:
                logger.info(
                    f"  Last processed signal candle: {last_signal.timestamp}"
                )

            # Restore session equity baseline from SystemState
            state = session.query(SystemState).first()
            if state:
                if state.session_start_equity:
                    self.session_start_equity = state.session_start_equity
                    logger.info(
                        f"  Session start equity: ${state.session_start_equity:,.2f}"
                    )
                if state.high_water_mark:
                    self.session_high_water_mark = state.high_water_mark
                self.execution_enabled = state.execution_enabled

            session.close()

        except Exception as e:
            logger.error(f"Failed to load runtime state: {e}")

    def _persist_runtime_state(self):
        """Persist runtime state so a restart can resume safely."""
        try:
            session = self.Session()
            state = session.query(SystemState).first()

            if state is None:
                state = SystemState(execution_enabled=False)
                session.add(state)

            if self.session_start_equity is not None:
                state.session_start_equity = self.session_start_equity
            if self.session_high_water_mark is not None:
                state.high_water_mark = self.session_high_water_mark
            if self.verified_account is not None:
                state.verified_account_login = str(self.verified_account.account_login)
                state.verified_account_server = self.verified_account.account_server
                state.last_account_verification = self.verified_account.verification_time

            session.commit()
            session.close()

        except Exception as e:
            logger.error(f"Failed to persist runtime state: {e}")

    def _reconcile_after_restart(self):
        """
        Reconcile broker positions against local records after startup.

        Runs before any new entry is considered so that a restart cannot
        create a duplicate position.
        """
        try:
            logger.info("Reconciling broker positions with local records...")

            positions = mt5.positions_get(symbol=self.symbol)
            broker_tickets = set()
            if positions:
                for pos in positions:
                    broker_tickets.add(pos.ticket)
                    logger.info(
                        f"  Broker position: #{pos.ticket} {pos.type_str} "
                        f"{pos.volume} @ {pos.price_open:.2f}"
                    )

            # Record any broker position we do not know about locally
            session = self.Session()
            known = {
                t.broker_order_id
                for t in session.query(Trade)
                .filter(Trade.exit_timestamp == None)
                .all()
            }
            for ticket in broker_tickets:
                if str(ticket) not in known:
                    logger.warning(
                        f"  Untracked broker position #{ticket} - recording as manual"
                    )
                    pos = next(p for p in positions if p.ticket == ticket)
                    trade = Trade(
                        broker_order_id=str(ticket),
                        entry_timestamp=datetime.utcnow(),
                        direction=(
                            TradeDirection.LONG
                            if pos.type == 0
                            else TradeDirection.SHORT
                        ),
                        entry_price_expected=pos.price_open,
                        entry_price_actual=pos.price_open,
                        volume=pos.volume,
                        stop_loss=pos.sl,
                        take_profit=pos.tp,
                        status=OrderStatus.FILLED,
                        error_analysis="Position found at startup without local record",
                    )
                    session.add(trade)
            session.commit()
            session.close()

            # Close out local records whose positions are gone
            self._reconcile_closed_trades(broker_tickets)

            logger.info("  Reconciliation complete")

        except Exception as e:
            logger.error(f"Restart reconciliation error: {e}", exc_info=True)

    def _preflight_account_capacity(self) -> dict:
        """
        Report whether the demo account can actually trade this instrument.

        The broker minimum volume sets a hard floor on risk: if the smallest
        tradable lot costs more than the risk budget, no trade is possible
        regardless of strategy quality. This is reported explicitly rather
        than discovered trade by trade.
        """
        info = {
            "balance": None,
            "min_lot_risk_at_atr_stop": None,
            "required_balance_at_risk_pct": None,
            "can_trade": False,
            "reason": "",
        }

        try:
            account_info = mt5.account_info()
            if account_info is None:
                info["reason"] = "Account info unavailable"
                return info

            balance = account_info.balance
            info["balance"] = balance

            atr_value = self._latest_atr()
            if not atr_value:
                info["reason"] = "ATR unavailable; cannot size the stop"
                return info

            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                info["reason"] = "Tick unavailable"
                return info

            entry_price = tick.ask
            stop_distance = atr_value * config.atr_stop_multiplier
            stop_distance_pips = stop_distance * 10

            symbol_info = mt5.symbol_info(self.symbol)
            min_lot = symbol_info.volume_min if symbol_info else 0.01

            min_lot_risk = (
                min_lot * stop_distance_pips * self.position_sizer.pip_value_per_lot
            )
            info["min_lot_risk_at_atr_stop"] = min_lot_risk

            risk_budget = balance * self.max_risk_per_trade
            info["required_balance_at_risk_pct"] = (
                min_lot_risk / self.max_risk_per_trade
                if self.max_risk_per_trade > 0
                else None
            )

            if risk_budget >= min_lot_risk:
                info["can_trade"] = True
                info["reason"] = (
                    f"OK: risk budget ${risk_budget:.2f} >= min lot risk "
                    f"${min_lot_risk:.2f}"
                )
            else:
                info["can_trade"] = False
                info["reason"] = (
                    f"Balance ${balance:.2f} at {self.max_risk_per_trade:.1%} risk "
                    f"(${risk_budget:.2f}) cannot cover the broker minimum lot "
                    f"({min_lot} lots, ${min_lot_risk:.2f} at a {stop_distance_pips:.0f} "
                    f"pip ATR stop). Needs ~${info['required_balance_at_risk_pct']:,.0f}."
                )

            return info

        except Exception as e:
            info["reason"] = f"Preflight failed: {e}"
            return info

    def _latest_atr(self) -> Optional[float]:
        """
        Latest ATR from the most recent completed bars.

        Uses the same feature pipeline as training so the stop distance is
        derived from the same volatility measure the model was trained on.
        """
        try:
            rates = mt5.copy_rates_from_pos(
                self.symbol, mt5.TIMEFRAME_M15, 1, self.atr_period + 60
            )
            if rates is None or len(rates) < self.atr_period + 2:
                return None

            df = pd.DataFrame(rates)
            df["timestamp"] = pd.to_datetime(df["time"], unit="s")

            atr = ta.atr(df["high"], df["low"], df["close"], length=self.atr_period)
            if atr is None:
                return None

            last = atr.dropna()
            if last.empty:
                return None

            return float(last.iloc[-1])

        except Exception as e:
            logger.error(f"ATR calculation failed: {e}")
            return None

    def _monitor_open_positions(self):
        """
        Reconcile broker positions with local records and manage exits.

        Called every cycle. Detects:
        - Positions closed by the broker (SL/TP hit) -> record realized P&L
        - Positions still open -> update unrealized P&L
        - Orphaned local trades with no matching broker position -> mark closed
        """
        try:
            positions = mt5.positions_get(symbol=self.symbol)
            broker_tickets = set()

            if positions:
                for pos in positions:
                    broker_tickets.add(pos.ticket)

                    unrealized = pos.profit + (pos.swap if pos.swap else 0.0)

                    logger.info(
                        f"  OPEN #{pos.ticket} {pos.type_str} {pos.volume} "
                        f"@ {pos.price_open:.2f} | SL {pos.sl:.2f} TP {pos.tp:.2f} "
                        f"| unrealized ${unrealized:+.2f}"
                    )

                    # Update local trade record with unrealized P&L
                    self._update_trade_unrealized(pos)

            # Detect trades closed by the broker (SL/TP/manual)
            self._reconcile_closed_trades(broker_tickets)

            return len(positions) if positions else 0

        except Exception as e:
            logger.error(f"Position monitoring error: {e}", exc_info=True)
            return 0

    def _update_trade_unrealized(self, position):
        """Update a local trade row with live unrealized P&L."""
        try:
            session = self.Session()
            trade = (
                session.query(Trade)
                .filter(Trade.broker_order_id == str(position.ticket))
                .filter(Trade.exit_timestamp == None)
                .first()
            )
            if trade:
                unrealized = position.profit + (position.swap if position.swap else 0.0)
                trade.realized_pnl = unrealized
                trade.updated_at = datetime.utcnow()
                session.commit()
            session.close()
        except Exception as e:
            logger.error(f"Failed to update unrealized P&L: {e}")

    def _reconcile_closed_trades(self, broker_tickets: set):
        """
        Detect locally-tracked trades that the broker has closed.

        Uses MT5 history to find the closing deal and compute the actual
        realized P&L, including commission and swap.
        """
        try:
            session = self.Session()
            open_trades = (
                session.query(Trade)
                .filter(Trade.exit_timestamp == None)
                .all()
            )

            for trade in open_trades:
                if trade.broker_order_id and int(trade.broker_order_id) in broker_tickets:
                    continue  # Still open

                # Position no longer exists -> find the closing deal
                deal_info = self._find_closing_deal(trade.broker_order_id)

                if deal_info:
                    exit_price = deal_info.get("price")
                    realized = deal_info.get("profit")
                    commission = deal_info.get("commission", 0.0)
                    swap = deal_info.get("swap", 0.0)
                    exit_reason = self._classify_exit(trade, exit_price)

                    trade.exit_timestamp = datetime.utcnow()
                    trade.exit_price_actual = exit_price
                    trade.realized_pnl = realized
                    trade.total_commission = commission
                    trade.total_swap = swap
                    trade.exit_reason = exit_reason
                    trade.status = OrderStatus.FILLED

                    session.commit()

                    logger.info("=" * 70)
                    logger.info(f"TRADE CLOSED #{trade.id}")
                    logger.info(f"  Exit price: {exit_price}")
                    logger.info(f"  Realized P&L: ${realized:+.2f}")
                    logger.info(f"  Commission: ${commission:.2f}  Swap: ${swap:.2f}")
                    logger.info(f"  Reason: {exit_reason}")
                    logger.info("=" * 70)
                else:
                    # Broker state unknown: flag for review rather than
                    # inventing an outcome.
                    logger.warning(
                        f"Trade {trade.id} (order {trade.broker_order_id}) has no open "
                        f"position and no closing deal found - marked for review"
                    )
                    trade.error_category = "UNKNOWN"
                    trade.error_analysis = "No closing deal found in broker history"
                    trade.exit_timestamp = datetime.utcnow()
                    trade.status = OrderStatus.CANCELLED
                    session.commit()

            session.close()

        except Exception as e:
            logger.error(f"Trade reconciliation error: {e}", exc_info=True)

    def _find_closing_deal(self, order_id):
        """Find the closing deal for an order in MT5 history."""
        if not order_id:
            return None

        try:
            order_ticket = int(order_id)
        except (TypeError, ValueError):
            return None

        try:
            # Search recent history (last 7 days)
            from datetime import timedelta

            since = datetime.utcnow() - timedelta(days=7)

            deals = mt5.history_deals_get(position=order_ticket)
            if not deals:
                deals = mt5.history_deals_get(since, datetime.utcnow())

            if not deals:
                return None

            # Prefer an explicit OUT entry (entry == 1)
            for deal in reversed(deals):
                if getattr(deal, "entry", None) == 1:
                    return {
                        "deal": deal.ticket,
                        "price": deal.price,
                        "profit": deal.profit,
                        "commission": deal.commission,
                        "swap": deal.swap,
                    }

            # Fall back to the most recent deal for this position
            last = deals[-1]
            return {
                "deal": last.ticket,
                "price": last.price,
                "profit": last.profit,
                "commission": last.commission,
                "swap": last.swap,
            }

        except Exception as e:
            logger.error(f"Failed to find closing deal for order {order_id}: {e}")
            return None

    def _classify_exit(self, trade, exit_price) -> ExitReason:
        """Classify why a trade was closed."""
        try:
            if (
                exit_price is None
                or trade.stop_loss is None
                or trade.take_profit is None
            ):
                return ExitReason.MANUAL_CLOSE

            tolerance = 0.05
            if trade.direction == TradeDirection.LONG:
                if exit_price <= trade.stop_loss + tolerance:
                    return ExitReason.STOP_LOSS
                if exit_price >= trade.take_profit - tolerance:
                    return ExitReason.TAKE_PROFIT
            else:
                if exit_price >= trade.stop_loss - tolerance:
                    return ExitReason.STOP_LOSS
                if exit_price <= trade.take_profit + tolerance:
                    return ExitReason.TAKE_PROFIT

            return ExitReason.MANUAL_CLOSE

        except Exception:
            return ExitReason.MANUAL_CLOSE

    def _log_heartbeat(self, cycle_count: int):
        """Log periodic heartbeat."""
        try:
            account_info = mt5.account_info()
            if account_info:
                logger.info("=" * 70)
                logger.info(f"HEARTBEAT | Cycle {cycle_count} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
                logger.info(f"  Balance: ${account_info.balance:,.2f} | Equity: ${account_info.equity:,.2f}")

                # Open positions
                positions = mt5.positions_get(symbol=self.symbol)
                if positions and len(positions) > 0:
                    logger.info(f"  Open positions: {len(positions)}")
                    for pos in positions:
                        profit = pos.profit
                        logger.info(
                            f"    {pos.type_str} {pos.volume} @ {pos.price_open:.2f} | "
                            f"P&L: ${profit:,.2f}"
                        )
                else:
                    logger.info("  Open positions: 0")

                logger.info("=" * 70)

        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

    def shutdown(self):
        """Graceful shutdown."""
        logger.info("=" * 70)
        logger.info("SHUTTING DOWN")
        logger.info("=" * 70)

        self.running = False

        if self.mt5_client:
            self.mt5_client.disconnect()

        logger.info("✓ Shutdown complete")
        logger.info("=" * 70)

    def handle_shutdown(self, signum, frame):
        """Signal handler for graceful shutdown."""
        logger.info("\nShutdown signal received")
        self.running = False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="XAUUSD Forward Testing")
    parser.add_argument("--check-interval", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--confidence", type=float, default=0.6, help="Minimum confidence threshold")
    parser.add_argument("--max-risk", type=float, default=0.01, help="Max risk per trade (fraction)")
    parser.add_argument("--max-spread", type=float, default=5.0, help="Max spread in pips")
    parser.add_argument("--dry-run", action="store_true", help="Log signals but don't execute")
    parser.add_argument(
        "--model",
        type=str,
        default="artifacts/models/real/best_model.pt",
        help="Trained model checkpoint",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="data/dataset_real.pkl",
        help="Dataset pickle holding the scaler and feature schema",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Run setup and safety checks, report status, then exit",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level=log_level, log_file=Path("logs/forward_test.log"))

    # Create forward tester
    tester = ForwardTester(
        symbol="XAUUSD",
        timeframe="M15",
        model_path=Path(args.model),
        dataset_path=Path(args.dataset),
        check_interval=args.check_interval,
        confidence_threshold=args.confidence,
        max_risk_per_trade=args.max_risk,
        max_spread_pips=args.max_spread,
        dry_run=args.dry_run,
    )

    # Setup signal handlers
    signal.signal(signal.SIGINT, tester.handle_shutdown)
    signal.signal(signal.SIGTERM, tester.handle_shutdown)

    # Initialize
    if not tester.setup():
        logger.error("Initialization failed")
        sys.exit(1)

    if args.preflight:
        capacity = tester._preflight_account_capacity()
        logger.info("=" * 70)
        logger.info("PREFLIGHT RESULT")
        logger.info("=" * 70)
        logger.info(f"  Balance: ${capacity['balance']:,.2f}" if capacity["balance"] else "  Balance: unavailable")
        logger.info(f"  Min-lot risk at ATR stop: ${capacity['min_lot_risk_at_atr_stop']:,.2f}"
                    if capacity["min_lot_risk_at_atr_stop"] else "  Min-lot risk: unavailable")
        logger.info(f"  Required balance at {args.max_risk:.1%} risk: "
                    f"${capacity['required_balance_at_risk_pct']:,.0f}"
                    if capacity["required_balance_at_risk_pct"] else "  Required balance: unavailable")
        logger.info(f"  Can trade: {capacity['can_trade']}")
        logger.info(f"  Reason: {capacity['reason']}")
        logger.info("=" * 70)
        return

    # Run
    tester.run()


if __name__ == "__main__":
    main()
