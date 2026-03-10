# CLAUDE.md - Backpack Advanced Trading Bot Knowledge Base

> This file preserves all accumulated knowledge from development sessions.
> Read this before making any changes to the codebase.

---

## Project Overview

- **Name**: Self-Improving Trading Bot (Backpack Exchange)
- **Exchange**: Backpack Exchange (devnet)
- **Symbol**: `BTC_USDC_PERP` (perpetual futures)
- **Language**: Python 3.x
- **Entry Point**: `python run_self_improving_bot.py`
- **Repository**: https://github.com/hyg10/bot-no.1.git

---

## Architecture

```
src/
  self_improving_bot.py        # Main bot - trading loop, entry/exit logic (CORE FILE)
  config/config.py             # Environment-based configuration (.env)
  utils/
    backpack_client.py         # Exchange SDK wrapper (REST API)
    logger.py                  # UTF-8 safe logger (Windows cp949 compatible)
  risk_management/
    risk_manager.py            # Position, SL/TP, PnL, fee calculation
    hedge_manager.py           # SOL hedging (secondary)
  ml/
    self_improvement_engine.py # GA optimizer + RL agent orchestrator
    rl_agent.py                # DQN reinforcement learning (logging only)
    trade_analyst.py           # Entry confidence + post-trade analysis
    particle_filter.py         # Short-term trend probability (Layer 3)
    wyckoff_analyzer.py        # Volume/supply-demand analysis (Layer 2)
  strategies/                  # Legacy strategy files (not used by main bot)
  backtesting/backtester.py    # Backtesting engine for GA fitness
```

---

## Current Parameters (as of 2025-03)

### Entry/Exit Thresholds
| Parameter | Value | Rationale |
|---|---|---|
| `ENTRY_THRESHOLD` | 2.5 | Min score for new entry (was 2.0) |
| `FLIP_THRESHOLD` | 3.5 | Min score for direction reversal (was 2.5) |
| `COOLDOWN_SEC` | 900 | 15min wait after each trade |
| `MIN_HOLD_SEC` | 600 | 10min minimum position hold |

### SL/TP (ATR-based, dynamic)
| Parameter | Value | Rationale |
|---|---|---|
| SL distance | 0.5 x ATR | Was 1.0. Tighter = less loss per trade |
| TP (ranging) | 0.3 x ATR | MFE analysis: avg favorable move = 0.33 x ATR |
| TP (trending) | 0.5 x ATR | Was 1.0. Trending allows more room |

### Trailing Break-Even (TrailBE)
| Condition | Action |
|---|---|
| Profit > 0.2 x ATR | Move SL to entry price (breakeven) |
| Profit > 0.4 x ATR | Move SL to entry +/- 0.15 x ATR (lock profit) |

### Time Limits
| Parameter | Value | Rationale |
|---|---|---|
| Smart Exit | 600s (10min) + PnL < 0 | Early exit for losing positions |
| Max hold (ranging) | 1800s (30min) | Ranging = fast rotation |
| Max hold (trending) | 2400s (40min) | Trending = longer hold |

### Fee Structure
| Parameter | Value | Usage |
|---|---|---|
| `MAKER_FEE` | 0.0002 (0.02%) | Limit order entry (postOnly) |
| `TAKER_FEE` | 0.0005 (0.05%) | Market order exit |
| `MIXED_ROUND_TRIP_FEE` | 0.0007 (0.07%) | Entry + exit combined |
| `ROUND_TRIP_FEE` | 0.0010 (0.10%) | Legacy (both taker) |

### SMA Trend Bias
| Parameter | Value |
|---|---|
| SMA period | 7 candles (1h each) |
| Threshold | 0.5% (was 0.2%) |

### Position Sizing
| Parameter | Value |
|---|---|
| BTC min order | 0.0005 |
| ETH min order | 0.005 |
| Default min | 0.01 |
| Max position cap | `max_coins` (from config trade_size) |
| Signal boost x2 | abs(score) >= 4.0 |
| Signal boost x1.5 | abs(score) >= 3.0 |
| Wyckoff volume confirm | +30% |

### Fee Filter
- Rejects entry if estimated fee > 50% of estimated TP profit
- Uses `MIXED_ROUND_TRIP_FEE` for estimation

---

## 3-Layer Direction Decision System

```
Layer 1: SMA (Macro)        weight: +/-2     1h x 7 candle SMA
Layer 2: Wyckoff (Supply)   weight: +/-1~2   Volume, orderbook, phase analysis
Layer 3: Particle Filter    weight: +/-1     Short-term probability

Total score range: -5 to +5

Score >= ENTRY_THRESHOLD (2.5) -> LONG
Score <= -ENTRY_THRESHOLD       -> SHORT
Otherwise                       -> HOLD (no trade)
```

### Additional Filters (in order)
1. **Regime filter**: Ranging market = no new entry
2. **SMA neutral ban**: SMA=neutral = no new entry
3. **Counter-trend ban**: SMA direction opposes entry direction = reject
4. **Min hold check**: < 600s since open = no flip
5. **BB position filter**: LONG only if BB < 0.5, SHORT only if BB > 0.5 (bypass if score >= 3.0)
6. **Fee filter**: Fee > 50% of expected profit = reject

---

## Entry Flow (Limit Order)

```
1. get_best_bid_ask() -> limit_price
   - LONG: best_bid (top of bid book)
   - SHORT: best_ask (top of ask book)
2. place_post_only_limit_order() -> order_id
   - postOnly=True guarantees maker fee
   - Rejection on spread cross = normal, skip cycle
3. Fill wait loop (max 30s, poll every 2s)
   - Check get_open_orders() for order existence
   - Order gone -> get_order_fill_price() for fill data
   - 3 retries for API propagation delay
4. Timeout -> cancel_order() + recheck partial fill
5. Dust filter: filled < 10% of intended = skip
6. open_position(actual_price, actual_size) -> SL/TP from real fill price
7. _monitor_position() -> SL/TP/trail/hedge/smart_exit loop
```

### Exit Flow (Market Order - always)
- SL hit, TP hit, time_limit, smart_time_limit, signal_exit
- All exits use `place_market_order()` (taker fee 0.05%)

---

## Backpack SDK Quirks

### CRITICAL SDK NOTES
1. **`cancel_open_order()`** not `cancel_order()` - SDK method name difference
2. **`postOnly=True`** and `timeInForce` are MUTUALLY EXCLUSIVE - never set both
3. **Order book format**: Bids ascending (last = best bid), Asks ascending (first = best ask)
4. **`get_best_bid_ask()`** extracts: `bids[-1][0]` = best_bid, `asks[0][0]` = best_ask
5. **fill_history**: `auth_client.get_fill_history(orderId=order_id)` - weighted avg for partial fills
6. **Position netQuantity**: positive = long, negative = short

### API Wrapper Methods (backpack_client.py)
- `get_best_bid_ask(symbol)` -> `{best_bid, best_ask, spread}`
- `place_post_only_limit_order(symbol, side, price, quantity)` -> order response
- `get_order_fill_price(symbol, order_id)` -> `{filled, fill_price, fill_size}`
- `get_trend_bias(symbol, sma_period=7)` -> "long" | "short" | "neutral"
- `get_market_regime(symbol)` -> `{regime, atr, atr_pct, bb_width_pct, ...}`

---

## Bugs Fixed (History)

### BUG #1: fill_history empty after limit order
- **Symptom**: Limit order fills but `get_fill_history()` returns empty
- **Fix**: Safety net checks `get_open_positions()` for exchange-level position confirmation
- **Location**: `self_improving_bot.py` entry flow, step 4

### BUG #2: Fee calculation completely missing
- **Symptom**: PnL showed as positive but account balance kept dropping
- **Fix**: Added `TAKER_FEE`, `MAKER_FEE`, fee calculation in `calculate_pnl()`, `FeeFilter`
- **Location**: `risk_manager.py`

### BUG #3: np.random.seed(42) global pollution
- **Symptom**: GA thread sets global numpy seed -> all randomness becomes deterministic
- **Fix**: `rng = np.random.RandomState(42)` local instance, all calls use `rng.*`
- **Location**: `self_improving_bot.py` line ~49 (fitness function)

### BUG #4: _monitor_position network error = immediate exit
- **Symptom**: Single network timeout breaks the monitor loop -> position unmonitored
- **Fix**: `continue` with 5-retry counter instead of `break`. `self._monitor_errors` resets on success
- **Location**: `self_improving_bot.py` _monitor_position exception handler

### BUG #5: GA thread concurrency (double execution)
- **Symptom**: Emergency trigger spawns new GA thread while one is running -> race condition
- **Fix**: `_improvement_running` flag with try/finally wrapper
- **Location**: `self_improvement_engine.py`

### Additional Fixes
- **cancel_order -> cancel_open_order**: SDK method name was wrong
- **TrailBE inconsistency**: Safety 1.5 had old 0.5/1.0 values, unified to 0.2/0.4
- **entry_time reset**: Synced positions got `datetime.now()` instead of actual fill time
- **SmartExit missing from Safety 1.5**: Only in `_monitor_position`, added to main loop
- **Log duplication**: `logger.propagate = False`
- **Unicode/emoji errors on Windows cp949**: All emojis replaced with ASCII `[X]`, `[O]`, `[!]`, etc.

---

## Windows-Specific Notes

### Encoding
- Windows console uses cp949 (Korean) - no emoji support
- Logger uses `io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")`
- NEVER use emoji in log messages or data files
- Em dash (U+2014) also fails - use `-` instead

### Git
- `nul` is a Windows reserved filename - added to `.gitignore`
- Use `venv/` not `venv\` in paths

---

## RL Agent Status

**DISABLED for trading decisions** (logging/learning only)

The RL (DQN) agent's Hold/Buy/Sell recommendations are logged but NOT used for entry/exit decisions. The 3-layer consensus system (SMA + Wyckoff + PF) controls all trading.

Reason: RL Hold action was blocking valid entries with 63% win rate signals.

RL parameters `trade_size_ratio` and `sell_ratio` are also unused. Position sizing is based on `max_coins` x multipliers only.

---

## Self-Improvement Engine

- GA (Genetic Algorithm) optimizes strategy parameters periodically
- **Thread safety**: `_improvement_running` flag prevents concurrent execution
- **Triggers**: Scheduled (daily) + Emergency (win_rate < threshold or drawdown > threshold)
- **Fitness**: 0.4*return + 0.3*win_rate + 0.3*sharpe - 0.5*max_drawdown
- Uses local `np.random.RandomState(42)` to avoid global seed pollution

---

## Key Design Decisions

### Why Limit Order Entry + Market Order Exit?
- Maker fee (0.02%) vs Taker fee (0.05%) = 60% fee reduction on entry
- Round-trip: 0.07% vs 0.10% = 30% total savings
- Exit stays market for safety (guaranteed fill on SL/TP)

### Why SL 0.5 x ATR instead of 1.0?
- Old 1.0 x ATR SL lost $1.02 per SL hit (2.2% of capital)
- 0.5 x ATR cuts loss per trade in half
- MFE analysis showed avg favorable move = 0.33 x ATR, so TP at 0.3 is optimal

### Why ENTRY_THRESHOLD 2.5?
- At 2.0, too many weak signals entered and lost
- 2.5 requires stronger consensus (e.g., SMA+Wyckoff must agree)
- Reduces trade frequency but improves win rate

### Why no flip trades?
- Flip trades (close + reverse in one cycle) had 23% win rate
- Now: close only, then wait COOLDOWN_SEC (900s) before new entry

### Why Smart Exit at 10 min?
- Losing positions that don't recover in 10min rarely recover at all
- Early exit at 10min + PnL<0 prevents losses from growing to SL

### Why SMA neutral/counter-trend ban?
- Entering against the macro trend was the #1 loss source
- SMA neutral = no clear direction = high-risk entry = skip

---

## Configuration (.env)

```env
BACKPACK_API_KEY=your_key
BACKPACK_SECRET_KEY=your_secret
BACKPACK_ENVIRONMENT=devnet
TRADING_SYMBOL=BTC_USDC_PERP
INITIAL_CAPITAL=50
STRATEGY_TRADE_SIZE=0.001
STRATEGY_MIN_INTERVAL=30
STRATEGY_MAX_INTERVAL=120
STOP_LOSS_PERCENT=2.0
TAKE_PROFIT_PERCENT=5.0
TRAILING_STOP_PERCENT=1.5
MAX_POSITION_SIZE_PERCENT=20.0
MAX_DAILY_LOSS_PERCENT=10.0
LOG_LEVEL=INFO
```

---

## File-by-File Quick Reference

| File | Key Responsibility | Watch Out For |
|---|---|---|
| `self_improving_bot.py` | Main loop, all entry/exit logic | LARGEST file. Multiple safety layers interleave |
| `risk_manager.py` | Position tracking, PnL, fees | `MAKER_FEE` vs `TAKER_FEE` in calculations |
| `backpack_client.py` | All exchange API calls | SDK method names (cancel_open_order, not cancel_order) |
| `self_improvement_engine.py` | GA + RL orchestration | Thread safety with `_improvement_running` flag |
| `logger.py` | UTF-8 logging | `propagate=False`, UTF-8 wrapper for Windows |
| `trade_analyst.py` | Confidence scoring, lessons | No emojis in output (Windows cp949) |
| `particle_filter.py` | Short-term trend probability | Needs warmup (22 ticks) before `is_ready()` |
| `wyckoff_analyzer.py` | Volume/supply-demand analysis | Needs 14h of 1h candles for full analysis |

---

## Trading Loop Flow (Simplified)

```
_trading_loop() [30-120s interval]
  |
  +-- Safety 1.5: Sync exchange position
  |     +-- SL/TP check on synced position
  |     +-- SmartExit (10min + PnL<0)
  |     +-- Time limit check (30-40min)
  |
  +-- Safety 2: Cooldown check (900s)
  |
  +-- Get equity, update RL state
  +-- RL action (logging only)
  +-- Confidence check (skip if < 20%)
  |
  +-- Layer 0: Market regime (skip ranging)
  +-- Layer 1: SMA bias (7-period, 1h)
  +-- Layer 2: Wyckoff analysis
  +-- Layer 3: Particle Filter
  |
  +-- Score calculation (-5 to +5)
  +-- Hysteresis: ENTRY(2.5) / FLIP(3.5)
  +-- Neutral ban, counter-trend ban
  +-- Min hold check, BB filter
  +-- Fee filter (>50% = reject)
  |
  +-- Same direction? -> skip
  +-- Opposite direction? -> close only (no flip)
  +-- No position? -> limit order entry
  |     +-- get_best_bid_ask -> limit_price
  |     +-- place_post_only_limit_order
  |     +-- fill wait (30s max)
  |     +-- open_position(actual_fill_price)
  |     +-- _monitor_position()
  |           +-- SL/TP/trail check (5s interval)
  |           +-- TrailBE (0.2/0.4 x ATR)
  |           +-- SmartExit (600s + PnL<0)
  |           +-- Hedge check (30s interval)
  |           +-- Time limit exit
```

---

## Common Issues & Solutions

| Issue | Cause | Solution |
|---|---|---|
| UnicodeEncodeError cp949 | Emoji in log/print | Use ASCII: [X], [O], [!], [WIN], [LOSS] |
| `cancel_order` AttributeError | Wrong SDK method | Use `cancel_open_order()` |
| Position not tracked after restart | No sync on startup | `_sync_positions()` runs on start |
| Fill history empty | API propagation delay | 3 retries with 1s sleep + position fallback |
| Duplicate log lines | Logger propagation | `logger.propagate = False` |
| GA thread race condition | Double trigger | `_improvement_running` flag |
| Global RNG contamination | `np.random.seed()` in GA | Use local `np.random.RandomState()` |
| Entry time wrong after restart | `datetime.now()` used | Use fill_history timestamp |

---

## Performance History

| Date | Equity | Key Change |
|---|---|---|
| Initial | ~$50.00 | Bot started |
| Week 1-2 | $48.22 | No fee calculation, losing to fees |
| Week 3 | $44.88 | Fee fix deployed, still declining |
| Bug fix session | $42.67 | 5 critical bugs fixed, 6 profitability improvements |
| Post-fix | Monitoring | All fixes verified, SmartExit working |

---

## DO NOT Change Without Understanding

1. **`postOnly=True` without `timeInForce`** - They are mutually exclusive in Backpack SDK
2. **Fee calculation in `calculate_pnl()`** - Uses MAKER for entry, TAKER for exit
3. **`logger.propagate = False`** - Prevents duplicate log lines
4. **TrailBE values 0.2/0.4** - Must match in BOTH `_monitor_position()` AND Safety 1.5 block
5. **SmartExit in TWO places** - Both `_monitor_position()` AND main loop Safety 1.5
6. **`cancel_open_order`** not `cancel_order` - SDK method name
7. **Order book: `bids[-1]` = best bid** - Backpack returns bids ascending
8. **`rng = np.random.RandomState(42)`** - Local RNG in fitness function
9. **RL is logging only** - Do not reconnect RL decisions to entry/exit logic
10. **No emoji anywhere** - Windows cp949 will crash the logger
