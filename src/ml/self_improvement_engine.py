"""
Self-Improvement Engine
=======================
Orchestrates the full self-improvement cycle:

  1. Performance Monitor  → detects degradation triggers
  2. Auto Re-optimizer    → runs GA on recent data
  3. RL Agent Trainer     → continuous online learning
  4. Parameter Updater    → applies best params safely
  5. A/B Tester           → validates new vs old params
  6. History Logger       → tracks improvement over time

Trigger modes:
  - Scheduled  : every N hours (daily by default)
  - Emergency  : win_rate < threshold OR drawdown > threshold
"""
import json
import os
import time
import threading
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import deque


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class PerformanceSnapshot:
    """Snapshot of bot performance at a point in time"""
    timestamp: str
    win_rate: float
    sharpe_ratio: float
    total_pnl: float
    max_drawdown: float
    profit_factor: float
    total_trades: int
    params: Dict
    trigger_reason: str = "scheduled"


@dataclass
class ImprovementRecord:
    """Record of a self-improvement cycle"""
    timestamp: str
    trigger: str
    old_params: Dict
    new_params: Dict
    old_fitness: float
    new_fitness: float
    improvement_pct: float
    accepted: bool
    reason: str


@dataclass
class SelfImprovementConfig:
    # Scheduled optimization
    scheduled_interval_hours: float = 24.0

    # Emergency triggers
    emergency_win_rate_threshold: float = 38.0    # % - below triggers emergency
    emergency_drawdown_threshold: float = 8.0     # % - above triggers emergency
    emergency_sharpe_threshold: float = 0.3       # below triggers emergency
    emergency_consecutive_losses: int = 5

    # GA optimization settings
    ga_population_size: int = 15
    ga_generations: int = 30
    ga_data_lookback_days: int = 7

    # A/B test settings
    ab_test_min_trades: int = 20          # min trades before accepting new params
    ab_test_improvement_threshold: float = 5.0  # % improvement required

    # RL training settings
    rl_train_every_n_trades: int = 5      # train RL after every N trades
    rl_save_every_n_steps: int = 500

    # Safety guardrails
    max_trade_size_multiplier: float = 2.0   # new params can't exceed 2x original
    min_trade_size_multiplier: float = 0.1   # new params can't be below 0.1x original


# ── Performance Monitor ───────────────────────────────────────────────────────

class PerformanceMonitor:
    """Monitors live trading performance and detects degradation"""

    def __init__(self, config: SelfImprovementConfig):
        self.config = config
        self.trades: deque = deque(maxlen=500)
        self.snapshots: List[PerformanceSnapshot] = []
        self.last_scheduled_check = datetime.now()
        self.consecutive_losses = 0

    def record_trade(self, trade: Dict):
        """Record a completed trade"""
        self.trades.append({
            "timestamp": datetime.now().isoformat(),
            "pnl": trade.get("pnl", 0),
            "pnl_percent": trade.get("pnl_percent", 0),
            "side": trade.get("side", "unknown"),
        })

        if trade.get("pnl", 0) < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def compute_metrics(self, lookback_hours: float = 24.0) -> Optional[Dict]:
        """Compute performance metrics for the lookback window"""
        if len(self.trades) < 5:
            return None

        cutoff = datetime.now() - timedelta(hours=lookback_hours)
        recent = [t for t in self.trades
                  if datetime.fromisoformat(t["timestamp"]) >= cutoff]

        if len(recent) < 5:
            recent = list(self.trades)[-20:]  # fallback: last 20 trades

        if not recent:
            return None

        pnls = [t["pnl"] for t in recent]
        pnl_pcts = [t["pnl_percent"] for t in recent]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        win_rate = len(wins) / len(recent) * 100

        # Sharpe
        arr = np.array(pnl_pcts)
        sharpe = float(np.mean(arr) / np.std(arr)) if np.std(arr) > 0 else 0.0

        # Drawdown
        cumulative = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative)
        dd = running_max - cumulative
        max_drawdown_abs = float(np.max(dd))

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss

        return {
            "win_rate": round(win_rate, 2),
            "sharpe_ratio": round(sharpe, 4),
            "total_pnl": round(sum(pnls), 4),
            "max_drawdown": round(max_drawdown_abs, 4),
            "profit_factor": round(profit_factor, 4),
            "total_trades": len(recent),
        }

    def should_trigger(self) -> Tuple[bool, str]:
        """
        Check if self-improvement should be triggered.
        Returns (should_trigger, reason).
        """
        metrics = self.compute_metrics()
        if not metrics:
            return False, ""

        # Emergency triggers (high priority)
        if metrics["win_rate"] < self.config.emergency_win_rate_threshold:
            return True, f"emergency:win_rate={metrics['win_rate']:.1f}%"

        if metrics["max_drawdown"] > self.config.emergency_drawdown_threshold:
            return True, f"emergency:drawdown={metrics['max_drawdown']:.2f}"

        if metrics["sharpe_ratio"] < self.config.emergency_sharpe_threshold and metrics["total_trades"] > 10:
            return True, f"emergency:sharpe={metrics['sharpe_ratio']:.3f}"

        if self.consecutive_losses >= self.config.emergency_consecutive_losses:
            return True, f"emergency:consecutive_losses={self.consecutive_losses}"

        # Scheduled trigger
        elapsed = datetime.now() - self.last_scheduled_check
        if elapsed >= timedelta(hours=self.config.scheduled_interval_hours):
            self.last_scheduled_check = datetime.now()
            return True, "scheduled"

        return False, ""


# ── Parameter Safety Guardrails ───────────────────────────────────────────────

class ParameterGuardrail:
    """Ensures new parameters stay within safe bounds relative to originals"""

    def __init__(self, base_params: Dict, config: SelfImprovementConfig):
        self.base_params = base_params.copy()
        self.config = config

    def validate_and_clip(self, new_params: Dict) -> Dict:
        """Clip new params to safe ranges"""
        safe = new_params.copy()

        if "trade_size" in safe and "trade_size" in self.base_params:
            base = self.base_params["trade_size"]
            safe["trade_size"] = np.clip(
                safe["trade_size"],
                base * self.config.min_trade_size_multiplier,
                base * self.config.max_trade_size_multiplier
            )

        if "stop_loss" in safe:
            safe["stop_loss"] = float(np.clip(safe["stop_loss"], 0.3, 15.0))

        if "take_profit" in safe:
            safe["take_profit"] = float(np.clip(safe["take_profit"], 0.5, 30.0))

        if "min_interval" in safe:
            safe["min_interval"] = int(np.clip(safe["min_interval"], 5, 600))

        if "max_interval" in safe:
            safe["max_interval"] = int(np.clip(safe["max_interval"], 10, 3600))

        # Ensure max_interval >= min_interval
        if "min_interval" in safe and "max_interval" in safe:
            safe["max_interval"] = max(safe["max_interval"], safe["min_interval"] + 5)

        return safe


# ── A/B Tester ────────────────────────────────────────────────────────────────

class ABTester:
    """
    Compares old vs new parameters over live trades.
    Uses a shadow parameter set and tracks comparative performance.
    """

    def __init__(self, config: SelfImprovementConfig):
        self.config = config
        self.testing = False
        self.old_params: Optional[Dict] = None
        self.new_params: Optional[Dict] = None
        self.old_fitness: float = 0.0
        self.new_trades: List[Dict] = []
        self.start_time: Optional[datetime] = None

    def start_test(self, old_params: Dict, new_params: Dict, old_fitness: float):
        """Begin an A/B test"""
        self.testing = True
        self.old_params = old_params.copy()
        self.new_params = new_params.copy()
        self.old_fitness = old_fitness
        self.new_trades = []
        self.start_time = datetime.now()
        print(f"[A/B Test] Started. Need {self.config.ab_test_min_trades} trades to evaluate.")

    def record_trade(self, trade: Dict):
        """Record a trade during A/B test"""
        if self.testing:
            self.new_trades.append(trade)

    def evaluate(self) -> Tuple[bool, str]:
        """
        Evaluate whether new params are better.
        Returns (accept_new_params, reason).
        """
        if not self.testing:
            return False, "not_testing"

        if len(self.new_trades) < self.config.ab_test_min_trades:
            return False, f"need_more_trades ({len(self.new_trades)}/{self.config.ab_test_min_trades})"

        pnls = [t.get("pnl", 0) for t in self.new_trades]
        pnl_pcts = [t.get("pnl_percent", 0) for t in self.new_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        win_rate = len(wins) / len(self.new_trades) * 100
        arr = np.array(pnl_pcts)
        sharpe = float(np.mean(arr) / np.std(arr)) if np.std(arr) > 0 else 0.0
        profit_factor = sum(wins) / (abs(sum(losses)) + 1e-8)

        # New fitness score (same formula as GA)
        new_fitness = (
            win_rate * 0.3 +
            sharpe * 10 +
            profit_factor * 5 -
            max(0, -sum(pnls)) * 0.1  # drawdown penalty
        )

        improvement = (new_fitness - self.old_fitness) / (abs(self.old_fitness) + 1e-8) * 100

        self.testing = False
        print(f"[A/B Test] Old fitness: {self.old_fitness:.3f} | New fitness: {new_fitness:.3f} | Improvement: {improvement:.1f}%")

        if improvement >= self.config.ab_test_improvement_threshold:
            return True, f"improved_by_{improvement:.1f}pct"
        else:
            return False, f"insufficient_improvement_{improvement:.1f}pct"


# ── History Logger ─────────────────────────────────────────────────────────────

class ImprovementLogger:
    """Persists improvement history to disk"""

    def __init__(self, log_dir: str = "logs/improvement"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.records: List[ImprovementRecord] = []
        self._load()

    def log(self, record: ImprovementRecord):
        self.records.append(record)
        self._save()
        print(f"[Improvement Logger] Logged: {record.trigger} | accepted={record.accepted}")

    def _save(self):
        path = os.path.join(self.log_dir, "improvement_history.json")
        with open(path, "w") as f:
            json.dump([asdict(r) for r in self.records], f, indent=2)

    def _load(self):
        path = os.path.join(self.log_dir, "improvement_history.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                self.records = [ImprovementRecord(**d) for d in data]
            except Exception:
                self.records = []

    def summary(self) -> Dict:
        if not self.records:
            return {"total_cycles": 0, "accepted": 0, "rejected": 0}
        accepted = [r for r in self.records if r.accepted]
        avg_improvement = np.mean([r.improvement_pct for r in accepted]) if accepted else 0
        return {
            "total_cycles": len(self.records),
            "accepted": len(accepted),
            "rejected": len(self.records) - len(accepted),
            "avg_improvement_pct": round(float(avg_improvement), 2),
            "last_cycle": self.records[-1].timestamp if self.records else None
        }


# ── Main Self-Improvement Engine ──────────────────────────────────────────────

class SelfImprovementEngine:
    """
    Orchestrates the full self-improvement loop.

    Usage:
        engine = SelfImprovementEngine(config, base_params, fitness_fn)
        engine.start_background()  # runs in background thread

        # After each trade:
        engine.on_trade_completed(trade_dict)

        # Get current best params:
        params = engine.get_current_params()
    """

    def __init__(
        self,
        si_config: SelfImprovementConfig,
        base_params: Dict,
        fitness_function,          # fn(params: Dict) -> float  (uses backtesting internally)
        initial_capital: float = 10000.0,
        log_dir: str = "logs/improvement",
        model_dir: str = "models/rl"
    ):
        from src.ml.rl_agent import TradingRLAgent, MarketStateBuilder, RLConfig

        self.config = si_config
        self.base_params = base_params.copy()
        self.current_params = base_params.copy()
        self.fitness_function = fitness_function
        self.initial_capital = initial_capital

        # Sub-components
        self.monitor = PerformanceMonitor(si_config)
        self.guardrail = ParameterGuardrail(base_params, si_config)
        self.ab_tester = ABTester(si_config)
        self.logger = ImprovementLogger(log_dir)

        # RL Agent
        rl_config = RLConfig()
        self.rl_agent = TradingRLAgent(rl_config, model_dir)
        self.state_builder = MarketStateBuilder(lookback=20)
        self._loaded_rl = self.rl_agent.load()

        # State
        self.is_running = False
        self._lock = threading.Lock()
        self._improvement_running = False  # BUG #5: GA 동시 실행 방지 플래그
        self._bg_thread: Optional[threading.Thread] = None
        self.trade_count_since_rl_train = 0
        self._last_state: Optional[np.ndarray] = None
        self._last_action: int = 0
        self._portfolio_cash = initial_capital
        self._portfolio_position_value = 0.0

        # Current fitness estimate
        self._current_fitness = 0.0

        print("[SelfImprovementEngine] Initialized.")
        print(f"  Scheduled interval: every {si_config.scheduled_interval_hours}h")
        print(f"  Emergency win_rate threshold: <{si_config.emergency_win_rate_threshold}%")
        print(f"  Emergency drawdown threshold: >{si_config.emergency_drawdown_threshold}%")
        print(f"  RL agent loaded: {self._loaded_rl}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def start_background(self):
        """Start background monitoring thread"""
        self.is_running = True
        self._bg_thread = threading.Thread(target=self._background_loop, daemon=True)
        self._bg_thread.start()
        print("[SelfImprovementEngine] Background thread started.")

    def stop(self):
        """Stop the engine"""
        self.is_running = False
        self.rl_agent.save("_final")
        print("[SelfImprovementEngine] Stopped.")

    def get_current_params(self) -> Dict:
        """Thread-safe getter for current params"""
        with self._lock:
            return self.current_params.copy()

    def on_price_update(self, price: float, volume: float = 1.0,
                        cash: float = None, position_value: float = 0.0,
                        entry_price: float = 0.0, position_size: float = 0.0):
        """
        Called on every price tick.
        Updates RL state builder and optionally returns RL action recommendation.
        """
        if cash is not None:
            self._portfolio_cash = cash
        self._portfolio_position_value = position_value

        self.state_builder.update(price, volume)

        state = self.state_builder.build_state(
            self._portfolio_cash,
            position_value,
            position_size,
            entry_price
        )

        if state is not None:
            self._last_state = state

        return state

    def get_rl_action(self, training: bool = True) -> Tuple[int, str]:
        """
        Get RL agent's recommended action.
        Returns (action_id, action_name).
        """
        if self._last_state is None:
            return 0, "Hold"
        action = self.rl_agent.select_action(self._last_state, training=training)
        self._last_action = action
        return action, self.rl_agent.ACTION_NAMES[action]

    def on_trade_completed(self, trade: Dict, next_price: float = None,
                           next_volume: float = 1.0):
        """
        Called after each trade completes.
        1. Records trade for performance monitoring
        2. Computes RL reward and trains
        3. Records for A/B test if active
        4. Checks for improvement triggers
        """
        self.monitor.record_trade(trade)
        self.ab_tester.record_trade(trade)

        # RL training
        if self._last_state is not None and next_price is not None:
            # Compute reward: risk-adjusted PnL
            pnl_pct = trade.get("pnl_percent", 0)
            reward = self._compute_rl_reward(pnl_pct, trade.get("exit_reason", ""))

            # Build next state
            self.state_builder.update(next_price, next_volume)
            next_state = self.state_builder.build_state(
                self._portfolio_cash,
                self._portfolio_position_value,
                0, 0  # after close, no position
            )

            if next_state is not None:
                done = False  # trading never truly "done"
                self.rl_agent.store_experience(
                    self._last_state, self._last_action, reward, next_state, done
                )

                self.trade_count_since_rl_train += 1
                if self.trade_count_since_rl_train >= self.config.rl_train_every_n_trades:
                    self._train_rl()
                    self.trade_count_since_rl_train = 0

                if self.rl_agent.steps % self.config.rl_save_every_n_steps == 0:
                    self.rl_agent.save()

        # A/B test evaluation
        if self.ab_tester.testing:
            accept, reason = self.ab_tester.evaluate()
            if accept is not None and not self.ab_tester.testing:
                self._finalize_ab_test(accept, reason)

        # Trigger check (emergency only - scheduled runs in background)
        # BUG #5 FIX: 동시 GA 스레드 방지
        should, reason = self.monitor.should_trigger()
        if should and "emergency" in reason:
            if self._improvement_running:
                print("[SelfImprovementEngine] GA 이미 실행 중 → 스킵")
            else:
                print(f"[SelfImprovementEngine] Emergency trigger: {reason}")
                threading.Thread(target=self._run_improvement_cycle,
                                 args=(reason,), daemon=True).start()

    def get_status(self) -> Dict:
        """Full status report"""
        metrics = self.monitor.compute_metrics() or {}
        rl_stats = self.rl_agent.get_stats()
        improvement_summary = self.logger.summary()

        return {
            "current_params": self.current_params,
            "performance": metrics,
            "rl_agent": rl_stats,
            "improvement_history": improvement_summary,
            "ab_test_active": self.ab_tester.testing,
            "consecutive_losses": self.monitor.consecutive_losses,
            "engine_running": self.is_running,
        }

    # ── Internal Methods ───────────────────────────────────────────────────────

    def _background_loop(self):
        """Background thread: checks for scheduled triggers"""
        while self.is_running:
            try:
                should, reason = self.monitor.should_trigger()
                if should and reason == "scheduled":
                    print(f"[SelfImprovementEngine] Scheduled optimization triggered.")
                    self._run_improvement_cycle(reason)
            except Exception as e:
                print(f"[SelfImprovementEngine] Background loop error: {e}")
            time.sleep(300)  # Check every 5 minutes

    def _run_improvement_cycle(self, trigger_reason: str):
        """Full self-improvement cycle"""
        # BUG #5 FIX: 동시 실행 방지
        if self._improvement_running:
            print("[SelfImprovementEngine] 이미 실행 중 → 스킵")
            return
        self._improvement_running = True

        try:
            self._run_improvement_cycle_inner(trigger_reason)
        finally:
            self._improvement_running = False

    def _run_improvement_cycle_inner(self, trigger_reason: str):
        """실제 improvement cycle 로직 (BUG #5: finally로 플래그 보장)"""
        print(f"\n{'='*60}")
        print(f"[SelfImprovementEngine] Starting improvement cycle")
        print(f"  Trigger: {trigger_reason}")
        print(f"  Time: {datetime.now().isoformat()}")
        print(f"{'='*60}")

        with self._lock:
            old_params = self.current_params.copy()

        # Step 1: Run GA optimization
        print("[Step 1] Running genetic algorithm optimization...")
        try:
            new_params, new_fitness = self._run_ga_optimization()
        except Exception as e:
            print(f"[Step 1] GA optimization failed: {e}")
            return

        if new_params is None:
            print("[Step 1] GA returned no results. Skipping cycle.")
            return

        # Step 2: Safety guardrails
        new_params = self.guardrail.validate_and_clip(new_params)
        print(f"[Step 2] Params validated: {new_params}")

        # Step 3: Compute old fitness for comparison
        old_fitness = self._compute_fitness(old_params)
        improvement_pct = (new_fitness - old_fitness) / (abs(old_fitness) + 1e-8) * 100

        print(f"[Step 3] Fitness: old={old_fitness:.3f} | new={new_fitness:.3f} | delta={improvement_pct:.1f}%")

        # Step 4: If improvement is meaningful, start A/B test
        if improvement_pct > 0 and not self.ab_tester.testing:
            print("[Step 4] Starting A/B test...")
            self.ab_tester.start_test(old_params, new_params, old_fitness)
            self._current_fitness = old_fitness

            # For emergency triggers with clear improvement, apply immediately
            if "emergency" in trigger_reason and improvement_pct > 15:
                print("[Step 4] Emergency + large improvement: applying immediately.")
                self._apply_params(new_params, old_params, old_fitness, new_fitness,
                                   improvement_pct, trigger_reason, accepted=True,
                                   reason="emergency_immediate")
        elif improvement_pct <= 0:
            self._log_improvement(trigger_reason, old_params, new_params, old_fitness,
                                  new_fitness, improvement_pct, accepted=False,
                                  reason="no_improvement")

    def _run_ga_optimization(self) -> Tuple[Optional[Dict], float]:
        """Run genetic algorithm to find better parameters"""
        from src.optimization.genetic_optimizer import GeneticOptimizer, ParameterRange

        param_ranges = [
            ParameterRange("trade_size", 0.005, 0.5, is_integer=False),
            ParameterRange("stop_loss", 0.3, 8.0, is_integer=False),
            ParameterRange("take_profit", 0.5, 15.0, is_integer=False),
            ParameterRange("min_interval", 10, 300, is_integer=True),
        ]

        optimizer = GeneticOptimizer(
            parameter_ranges=param_ranges,
            fitness_function=self.fitness_function,
            population_size=self.config.ga_population_size,
            generations=self.config.ga_generations,
            crossover_prob=0.7,
            mutation_prob=0.2,
        )

        result = optimizer.optimize(verbose=False)
        return result.best_params, result.best_fitness

    def _compute_fitness(self, params: Dict) -> float:
        """Compute fitness for given params using the provided fitness function"""
        try:
            return float(self.fitness_function(params))
        except Exception:
            return 0.0

    def _finalize_ab_test(self, accept: bool, reason: str):
        """Finalize A/B test result"""
        new_params = self.ab_tester.new_params
        old_params = self.ab_tester.old_params
        old_fitness = self.ab_tester.old_fitness
        new_fitness = self._compute_fitness(new_params)
        improvement_pct = (new_fitness - old_fitness) / (abs(old_fitness) + 1e-8) * 100

        if accept:
            self._apply_params(new_params, old_params, old_fitness, new_fitness,
                               improvement_pct, "ab_test", accepted=True, reason=reason)
        else:
            self._log_improvement("ab_test", old_params, new_params, old_fitness,
                                  new_fitness, improvement_pct, accepted=False, reason=reason)
            print(f"[A/B Test] New params rejected: {reason}. Keeping original params.")

    def _apply_params(self, new_params, old_params, old_fitness, new_fitness,
                      improvement_pct, trigger, accepted, reason):
        """Apply new params and log the change"""
        with self._lock:
            self.current_params = new_params.copy()

        print(f"[SelfImprovementEngine] New params applied! improvement={improvement_pct:.1f}%")
        self._log_improvement(trigger, old_params, new_params, old_fitness,
                              new_fitness, improvement_pct, accepted=accepted, reason=reason)

    def _log_improvement(self, trigger, old_params, new_params, old_fitness,
                         new_fitness, improvement_pct, accepted, reason):
        record = ImprovementRecord(
            timestamp=datetime.now().isoformat(),
            trigger=trigger,
            old_params=old_params,
            new_params=new_params,
            old_fitness=round(old_fitness, 4),
            new_fitness=round(new_fitness, 4),
            improvement_pct=round(improvement_pct, 2),
            accepted=accepted,
            reason=reason
        )
        self.logger.log(record)

    def _train_rl(self):
        """Run RL training batch"""
        losses = []
        for _ in range(4):  # 4 gradient steps per train call
            loss = self.rl_agent.train_step()
            if loss is not None:
                losses.append(loss)
        if losses:
            avg_loss = np.mean(losses)
            if self.rl_agent.steps % 100 == 0:
                print(f"[RL] Step {self.rl_agent.steps} | "
                      f"eps={self.rl_agent.epsilon:.3f} | "
                      f"loss={avg_loss:.5f} | "
                      f"memory={len(self.rl_agent.memory)}")

    def _compute_rl_reward(self, pnl_pct: float, exit_reason: str) -> float:
        """
        Compute RL reward from trade outcome.
        Uses risk-adjusted return + bonus/penalty for exit type.
        """
        # Base reward: PnL percentage
        reward = pnl_pct

        # Bonus for clean take-profit exit
        if exit_reason == "take_profit":
            reward *= 1.2

        # Penalty for stop-loss hit (risk discipline)
        if exit_reason == "stop_loss":
            reward *= 1.1  # slightly less penalty since stop-loss is disciplined

        # Clip reward to prevent gradient explosion
        return float(np.clip(reward, -10.0, 10.0))
