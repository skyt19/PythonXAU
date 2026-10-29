# Forward Testing — Operator Guide

XAUUSD M15 DEMO forward testing on HFM MetaTrader 5.

---

## Launch command

From the project root (`C:\z`):

```powershell
python scripts/forward_test.py
```

That is the single command. It connects to MT5, verifies the DEMO account,
loads the trained model, and starts processing closed M15 candles.

### Useful variants

```powershell
# Safety check only: connect, verify account, report capacity, then exit
python scripts/forward_test.py --preflight

# Log signals but never send an order (recommended first run)
python scripts/forward_test.py --dry-run

# Poll more often (default 30s)
python scripts/forward_test.py --check-interval 15

# Tighter risk budget
python scripts/forward_test.py --max-risk 0.005 --max-spread 4

# Verbose logging
python scripts/forward_test.py --verbose
```

### Stopping

Press `Ctrl+C` in the console running the script. The shutdown handler stops
the loop, disconnects MT5 and closes the database cleanly.

To run it in the background instead:

```powershell
# Start detached
Start-Process python -ArgumentList "scripts/forward_test.py" -RedirectStandardOutput logs\forward_stdout.log

# Stop it later
Get-Process python | Where-Object {$_.Path -like "*python*"} | Stop-Process
```

---

## Configuration

All settings live in `C:\z\.env` (never committed). Required for trading:

| Variable | Meaning |
|----------|---------|
| `MT5_LOGIN` | Numeric HFM demo account number |
| `MT5_PASSWORD` | HFM demo account password |
| `MT5_SERVER` | Exact demo server name from MT5 terminal |
| `MT5_SYMBOL` | `XAUUSD` (default) |
| `TIMEFRAME` | `M15` (default) |
| `DEMO_ONLY` | Must remain `true` |
| `DATABASE_URL` | `sqlite:///data/farming_hq.db` (default) |

Risk-related values used by the runtime (defaults shown):

| Setting | CLI flag | Default |
|---------|----------|---------|
| Max risk per trade | `--max-risk` | 1.0% of balance |
| Max spread | `--max-spread` | 5.0 pips |
| Min confidence | `--confidence` | 0.60 |
| Max open positions | (config) | 1 |
| Max daily loss | (config) | 5% |
| Max drawdown | (config) | 15% |
| ATR period | (config) | 14 |
| ATR stop multiplier | (config) | 2.0 |
| Risk/reward | (config) | 2.0 |

---

## Startup banner

On start the runtime prints (credentials are never shown):

```
======================================================================
FORWARD TESTING INITIALIZATION
======================================================================
✓ Database: sqlite:///data/farming_hq.db
✓ Preprocessing loaded: 28 features
  Sequence length: 48
  Model architecture: input=28, hidden=64, layers=2, classes=3
✓ Model loaded: artifacts\models\best_model.pt
✓ MT5 connected: HF Markets (SV) Ltd., build 6230
✓ Symbol XAUUSD: spread=34 points, volume_min=0.01, volume_step=0.01
======================================================================
✓ DEMO ACCOUNT VERIFIED
======================================================================
Account Verification [PASS]
  Mode: DEMO
  Server: HFMarketsGlobal-Demo4
  Balance: $64.07
  Leverage: 1:2000
======================================================================
  Broker pip value: $10.00 per 1.00 lot
  Broker accepted filling mode 0
✓ FORWARD TESTER READY
======================================================================
Symbol: XAUUSD
Timeframe: M15
Model: artifacts\models\best_model.pt
Check interval: 30s
Confidence threshold: 0.6
Max spread: 5.0 pips
Max risk per trade: 1.0%
======================================================================
```

---

## Runtime log

`logs/forward_test.log` (rotating). Useful lines:

| Message | Meaning |
|---------|---------|
| `NEW CANDLE: <ts>` | A closed M15 candle was picked up |
| `Prediction: TREND (confidence=79.66%)` | Model regime output |
| `Signal: SHORT` / `Signal: HOLD` | Strategy decision |
| `TRADE SIGNAL: SELL` | Passed the confidence gate |
| `✓ DEMO account verified` | Re-verified immediately before sending |
| `Spread OK: 3.4 pips` | Spread gate passed |
| `Risk checks passed (open positions: 0)` | Position/daily-loss/drawdown gates passed |
| `Trade rejected: min lot 0.01 risks $14.17 but risk budget is only $0.51` | Account too small to trade at the configured risk |
| `TRADE CLOSED #<id>` | A position was closed by the broker |
| `HEARTBEAT` | Status every 5 minutes |

---

## Checking that it is running

```powershell
# Is the process alive?
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, StartTime

# Tail the log
Get-Content logs\forward_test.log -Tail 30 -Wait

# Current open demo positions (from the broker)
python scripts/show_status.py
```

The trade journal is in the same database the dashboard reads:

```powershell
python -c "import sys; sys.path.insert(0,'.'); from app.database import DatabaseManager, Signal, Trade; db=DatabaseManager('sqlite:///data/farming_hq.db'); s=db.get_session(); print('signals',s.query(Signal).count(),'trades',s.query(Trade).count())"
```

---

## How a candle becomes an order

1. **Completed candle detection** — the second-to-last M15 bar from the broker
   (the last one is still forming). Keyed by its timestamp, so the same candle
   is never processed twice, including across restarts.
2. **Feature build** — 400 M15 bars fetched; indicators computed with the
   same pipeline used at training time. The final feature row is the target
   candle (verified by timestamp, not positional index).
3. **Model inference** — last 48 scaled bars fed to the LSTM; probabilities
   for TREND / RANGE / HIGH_VOLATILITY.
4. **Strategy** — regime plus confidence plus EMA trend produces BUY, SELL
   or HOLD.
5. **Gates** — HOLD or low confidence stops here and is logged with a reason.
6. **Execution gates**, re-checked for every candidate order:
   - DEMO account re-verified (mode + server + login)
   - spread within limit
   - open-position count, daily loss, drawdown
   - position size within the risk budget
   - broker minimum/maximum volume and volume step
7. **Order** — `order_check` first, then `order_send`. The result, deal
   ticket and fill price are recorded.

---

## Account capacity

The broker minimum lot is a hard floor. On XAUUSD, 0.01 lot moving 142 pips
(2x ATR(14)) risks about **$14.17**. At the default 1% risk budget that
requires roughly **$1,417** of demo balance.

`--preflight` reports this directly:

```
  Balance: $64.07
  Min-lot risk at ATR stop: $14.17
  Required balance at 1.0% risk: $1,417
  Can trade: False
  Reason: Balance $64.07 at 1.0% risk ($0.64) cannot cover the broker
          minimum lot (0.01 lots, $14.17 at a 142 pip ATR stop).
```

If the demo account is underfunded the system still runs, still logs every
signal and rejection, and simply never sends an order. That is the intended
behaviour — a trade that breaches the risk budget is not taken.

---

## Restart and reconciliation

State that survives a restart:

- session equity baseline and high-water mark (`system_state` table)
- last processed candle (derived from the newest recorded signal)
- open positions are reconciled against the broker before any new entry

On startup the runtime compares broker positions with the local journal. A
position it does not recognise is recorded as a manual entry rather than
being ignored, so a restart cannot silently double a position.

---

## Safety properties

- `DEMO_ONLY=true` is enforced by the configuration validator; the process
  refuses to start if it is false.
- Account mode comes from `mt5.ACCOUNT_TRADE_MODE_*`, so a live account
  (mode `REAL`) is rejected and a demo account (mode `DEMO`) is accepted.
- The server name must be on the demo allowlist.
- The account is re-verified immediately before every order.
- Volume is never rounded up to the broker minimum; a trade that cannot fit
  the risk budget is rejected.
- Fills are recorded with the broker's own deal ticket and price.
- Stops and targets are attached to every entry.

---

## Troubleshooting

**"MT5 initialization failed"**
MT5 terminal is not running, or the Python package cannot find it. Open the
terminal and log in to the demo account first.

**"MT5 login failed: Invalid 1st unnamed argument"**
`MT5_LOGIN` must be numeric. The runtime converts it to an integer; a
non-numeric value is reported explicitly.

**"DEMO ACCOUNT VERIFICATION FAILED"**
The connected account is not a demo account, the server is not on the
allowlist, or the login does not match `MT5_LOGIN`. Execution stays blocked.

**"Unsupported filling mode"**
The broker rejected the filling mode. The runtime probes the modes with
`order_check` and uses the first one the server accepts (HFM demo accepts
FOK). If this appears anyway, the symbol metadata may have changed.

**"Trade rejected: min lot ... risks $X but risk budget is only $Y"**
Expected when the demo balance is too small for the broker minimum lot.
Fund the demo account, or lower `--max-risk` so the budget covers the
minimum lot.

**"Feature computation failed or insufficient"**
Not enough M15 history returned by the broker. This happens right after the
terminal starts; it resolves once history is available.

**"No closing deal found in broker history"**
The trade was closed but the closing deal is not in the 7-day history
window. The trade is flagged for review rather than assigned an invented
outcome.

---

## What is verified and what is not

**Verified against the live HFM DEMO terminal:**
- MT5 connection and login
- account classified as DEMO (mode from MT5 constants, server on allowlist)
- XAUUSD symbol present, specs read from the broker (contract size, tick
  size/value, volume limits and step, stops level)
- real M15 candle received and processed
- trained model loaded and producing probabilities on live data
- strategy producing a SELL signal and running every execution gate
- order request shape accepted by the broker (`order_check`, margin $8.04
  against $56.03 free margin)
- signal persisted to the database with a rejection reason

**Not verified:**
- An actual filled order. The demo account balance ($64.07) is below the
  broker minimum lot risk at the configured risk budget, so every candidate
  trade is correctly rejected before submission. No order has been placed.
