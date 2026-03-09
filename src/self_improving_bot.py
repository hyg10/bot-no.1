"""
Self-Improving Trading Bot
==========================
Combines:
  - Live trading (Backpack Exchange)
  - RL Agent (DQN) for trade decisions
  - Self-Improvement Engine (GA + A/B Test)
  - Performance monitoring with dual triggers (scheduled + emergency)
  - Risk management

Run:
  python run_self_improving_bot.py
"""
import time
import random
import signal
import sys
import numpy as np
from datetime import datetime
from typing import Optional

from src.config.config import config
from src.utils.logger import logger
from src.utils.backpack_client import BackpackClient
from src.risk_management.risk_manager import RiskManager
from src.risk_management.hedge_manager import HedgeManager
from src.backtesting.backtester import Backtester
from src.ml.self_improvement_engine import (
    SelfImprovementEngine,
    SelfImprovementConfig,
)
from src.ml.trade_analyst import TradeAnalyst
from src.ml.particle_filter import TrendParticleFilter
from src.ml.wyckoff_analyzer import WyckoffAnalyzer


# ── Fitness Function ───────────────────────────────────────────────────────────

def build_fitness_function(initial_capital: float):
    """
    Returns a fitness function that evaluates strategy params using backtesting.
    Uses synthetic data if no live data is available yet.
    Fitness = 0.4*return + 0.3*win_rate + 0.3*sharpe - 0.5*max_drawdown_pct
    """
    def fitness_fn(params: Dict) -> float:
        try:
            import pandas as pd
            # Generate synthetic market data for backtesting
            # 로컬 RandomState 사용 — 글로벌 np.random 오염 방지 (BUG #3)
            rng = np.random.RandomState(42)
            n = 500
            timestamps = pd.date_range(start="2024-01-01", periods=n, freq="1min")
            base_price = 100.0
            returns = rng.normal(0, 0.002, n)
            prices = base_price * np.cumprod(1 + returns)

            df = pd.DataFrame({
                "timestamp": timestamps,
                "open": prices * (1 - rng.uniform(0, 0.001, n)),
                "high": prices * (1 + rng.uniform(0, 0.003, n)),
                "low": prices * (1 - rng.uniform(0, 0.003, n)),
                "close": prices,
                "volume": rng.uniform(100, 1000, n),
            })

            backtester = Backtester(initial_capital=initial_capital)
            df = backtester.load_data(df)

            trade_size = params.get("trade_size", 0.05)
            stop_loss_pct = params.get("stop_loss", 2.0)
            take_profit_pct = params.get("take_profit", 4.0)
            freq = max(1, int(params.get("min_interval", 60) / 2))  # convert seconds to bars

            i = 0
            sides = ["long", "short"]
            side_idx = 0

            while i < len(df) - freq:
                row = df.iloc[i]
                entry_price = float(row["close"])
                side = sides[side_idx % 2]
                side_idx += 1

                size = (initial_capital * trade_size) / entry_price

                if side == "long":
                    stop_loss = entry_price * (1 - stop_loss_pct / 100)
                    take_profit = entry_price * (1 + take_profit_pct / 100)
                else:
                    stop_loss = entry_price * (1 + stop_loss_pct / 100)
                    take_profit = entry_price * (1 - take_profit_pct / 100)

                trade, exit_idx = backtester.simulate_trade(
                    entry_time=row["timestamp"],
                    entry_price=entry_price,
                    size=size,
                    side=side,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    df=df,
                    start_idx=i + 1,
                )

                backtester.trades.append(trade)
                backtester.capital += trade.pnl
                backtester.equity_curve.append(backtester.capital)
                i = max(exit_idx + 1, i + freq)

                if backtester.capital <= initial_capital * 0.5:
                    break  # blown up

            if len(backtester.trades) < 3:
                return -100.0

            result = backtester.calculate_metrics()

            fitness = (
                result.total_return * 0.4 +
                result.win_rate * 0.3 +
                result.sharpe_ratio * 10 -
                result.max_drawdown_percent * 0.5
            )
            return float(fitness)

        except Exception as e:
            return -100.0

    return fitness_fn


from typing import Dict  # needed for fitness_fn type hint


# ── Main Bot Class ─────────────────────────────────────────────────────────────

class SelfImprovingTradingBot:
    """
    Trading bot that improves itself over time using:
    1. DQN reinforcement learning for action selection
    2. Genetic algorithm for parameter optimization
    3. A/B testing to validate improvements
    4. Dual triggers: scheduled (daily) + emergency (performance drops)
    """

    def __init__(self):
        self.client = BackpackClient()
        self.risk_manager = RiskManager(config)
        self.is_running = False
        self.trade_count = 0

        # Base parameters
        self.base_params = {
            "trade_size": config.strategy.trade_size,
            "min_interval": config.strategy.min_interval,
            "max_interval": config.strategy.max_interval,
            "stop_loss": config.risk_management.stop_loss_percent,
            "take_profit": config.risk_management.take_profit_percent,
        }

        # Self-improvement config
        si_config = SelfImprovementConfig(
            scheduled_interval_hours=24.0,
            emergency_win_rate_threshold=38.0,
            emergency_drawdown_threshold=8.0,
            emergency_consecutive_losses=5,
            ga_population_size=15,
            ga_generations=30,
            ab_test_min_trades=20,
            rl_train_every_n_trades=5,
        )

        # Build fitness function
        fitness_fn = build_fitness_function(config.trading.initial_capital)

        # Initialize self-improvement engine
        self.engine = SelfImprovementEngine(
            si_config=si_config,
            base_params=self.base_params,
            fitness_function=fitness_fn,
            initial_capital=config.trading.initial_capital,
        )

        # 매매 분석 + 패턴 학습 시스템
        self.analyst = TradeAnalyst(log_dir="logs/trade_analysis")

        # 크로스-심볼 헷지 매니저 (ETH_USDC_PERP / PAXG_USDC_PERP)
        self.hedge_manager = HedgeManager(self.client)

        # Bootstrap Particle Filter — 실시간 추세 확률 추정기
        self.pf = TrendParticleFilter()

        # 와이코프 수요·공급 분석기
        self.wyckoff = WyckoffAnalyzer()

        # 진입 시점 컨텍스트 임시 저장
        self._entry_context = None
        self._entry_confidence = 0.5
        self._entry_time = None
        self._last_trade_time = None  # Safety: 거래 쿨다운

        # ── 플립플롭 방지 + 수수료 최적화 설정 ────────────────────────
        self.COOLDOWN_SEC       = 900    # 거래 후 15분 대기 (was 5분)
        self.MIN_HOLD_SEC       = 600    # 포지션 최소 10분 보유 (was 5분)
        self.ENTRY_THRESHOLD    = 2.5    # 신규 진입 점수 기준 상향 (was 2.0→2.5)
        self.FLIP_THRESHOLD     = 3.5    # 방향 전환 점수 기준 상향 (was 2.5)
        self._position_open_time = None  # 현재 포지션 오픈 시각

    def start(self):
        """Start the self-improving bot"""
        logger.info("=" * 60)
        logger.info("Self-Improving Trading Bot")
        logger.info("=" * 60)
        config.print_config()

        try:
            markets = self.client.get_markets()
            logger.info(f"Connected to Backpack ({len(markets)} markets)")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            sys.exit(1)

        self._check_balances()
        self._cancel_stale_orders()  # 잔존 리밋 주문 정리
        self._sync_positions()       # 거래소 실제 포지션 동기화

        # Start background improvement engine
        self.engine.start_background()
        logger.info("Self-improvement engine started in background")

        self._warmup_state_builder()

        self.is_running = True
        self._trading_loop()

    def stop(self):
        """Graceful shutdown"""
        logger.info("Stopping bot...")
        self.is_running = False
        self.engine.stop()
        self._close_all_positions()
        self._print_final_stats()
        logger.info("Bot stopped.")

    def _warmup_state_builder(self):
        """
        Pre-populate RL state builder with 22 recent price ticks so the agent
        can make decisions from the very first trade cycle.
        Without this, it needs 20+ organic ticks (20-40 min wait) before acting.
        """
        logger.info("Warming up RL state builder (collecting 22 ticks, ~11s)...")
        symbol = config.trading.symbol
        collected = 0
        for _ in range(25):
            try:
                ticker = self.client.get_ticker(symbol)
                price = float(ticker.get("lastPrice", 0))
                vol   = float(ticker.get("volume", 1.0))
                if price > 0:
                    self.engine.state_builder.update(price, vol)
                    self.pf.update(price)   # particle filter pre-warm
                    collected += 1
            except Exception:
                pass
            time.sleep(0.5)
        ready = self.engine.state_builder.ready()
        logger.info(f"State builder warmed up | ticks={collected} | ready={ready}")

    def _cancel_stale_orders(self):
        """재시작 시 미체결 리밋 주문 전량 취소.

        이전 세션에서 리밋 주문이 남아있으면 봇 모르게 체결 →
        추적 불가 유령 포지션 생성. 시작 전 전부 정리.
        """
        symbol = config.trading.symbol
        try:
            open_orders = self.client.get_open_orders(symbol)
            if not open_orders:
                logger.info("[Startup] 미체결 주문 없음")
                return
            for o in open_orders:
                oid = o.get("id", "?")
                try:
                    self.client.cancel_order(symbol, oid)
                    logger.info(f"[Startup] 잔존 주문 취소: {oid}")
                except Exception as ce:
                    logger.warning(f"[Startup] 주문 취소 실패 {oid}: {ce}")
        except Exception as e:
            logger.error(f"[Startup] 미체결 주문 조회 실패: {e}")

    def _sync_positions(self):
        """
        시작 시 거래소 실제 포지션 조회 → 내부 risk_manager와 동기화.
        봇 재시작 후에도 오픈 포지션을 잃지 않도록 함.
        """
        try:
            real_positions = self.client.get_open_positions()
        except Exception as e:
            logger.error(f"[Sync] 포지션 조회 실패: {e}")
            return

        if not real_positions:
            logger.info("[Sync] 거래소 오픈 포지션 없음")
            return

        logger.info(f"[Sync] 거래소 포지션 {len(real_positions)}개 발견:")
        for pd in real_positions:
            symbol      = pd.get("symbol", "?")
            net_qty     = float(pd.get("netQuantity", 0))
            entry_price = float(pd.get("entryPrice", 0))
            mark_price  = float(pd.get("markPrice", 0))
            pnl_r       = float(pd.get("pnlRealized", 0))
            pnl_u       = float(pd.get("pnlUnrealized", 0))

            if net_qty == 0:
                continue

            side = "long" if net_qty > 0 else "short"
            size = abs(net_qty)
            direction = "▲" if side == "long" else "▼"

            logger.info(
                f"  {direction} {symbol} | {side.upper()} {size} "
                f"@ ${entry_price:.2f} → mark=${mark_price:.2f} | "
                f"실현={pnl_r:+.4f} 미실현={pnl_u:+.4f}"
            )

            # 내부 트래커에 없으면 복원
            if symbol not in self.risk_manager.positions:
                # ATR 조회하여 동적 SL/TP + 트레일링 BE 활성화
                try:
                    ri = self.client.get_market_regime(symbol)
                    sync_atr = ri.get("atr", 0)
                except Exception:
                    sync_atr = 0
                # fill_history에서 최근 체결 시각 조회 → entry_time으로 사용
                sync_entry_time = None
                try:
                    fills = self.client.auth_client.get_fill_history(
                        symbol=symbol, limit=5
                    )
                    if fills:
                        ts_str = fills[0].get("timestamp", "")
                        if ts_str:
                            sync_entry_time = datetime.fromisoformat(
                                ts_str.replace("Z", "+00:00").split("+")[0]
                            )
                except Exception:
                    pass
                restored = self.risk_manager.open_position(
                    symbol=symbol,
                    entry_price=entry_price,
                    size=size,
                    side=side,
                    atr=sync_atr,
                    entry_time=sync_entry_time,
                )
                # BTC 포지션이면 _position_open_time도 복원
                if config.trading.symbol.upper() in symbol.upper():
                    self._position_open_time = sync_entry_time or datetime.now()
                logger.info(
                    f"  → 내부 트래커 복원 완료 | "
                    f"SL=${restored.stop_loss:.2f} TP=${restored.take_profit:.2f}"
                )
            else:
                logger.info(f"  → 이미 내부 트래커에 존재")

    def _check_balances(self):
        # ── 실제 사용 가능 자산 (autoLend=True 대응) ───────────────────────────
        try:
            equity = self.client.get_available_equity()
            logger.info(f"Available Equity (netEquityAvailable): ${equity:.2f}")
        except Exception as e:
            logger.warning(f"Failed to get equity: {e}")

        # ── 원시 잔고 표시 (참고용, autoLend 시 0 가능) ────────────────────────
        try:
            balances = self.client.get_balances()
            logger.info("Raw Account Balances (autoLend=True → USDC may show 0):")
            # Format 1: list of dicts
            if isinstance(balances, list):
                for b in balances:
                    if isinstance(b, dict):
                        avail = float(b.get("available", 0))
                        locked = float(b.get("locked", 0))
                        if avail > 0 or locked > 0:
                            logger.info(f"  {b.get('symbol')}: available={avail}, locked={locked}")
            # Format 2: dict of dicts  {"USDC": {"available": "500"}, ...}
            elif isinstance(balances, dict):
                for sym, val in balances.items():
                    if isinstance(val, dict):
                        avail = float(val.get("available", 0))
                        locked = float(val.get("locked", 0))
                    else:
                        avail = float(val)
                        locked = 0.0
                    if avail > 0 or locked > 0:
                        logger.info(f"  {sym}: available={avail}, locked={locked}")
        except Exception as e:
            logger.error(f"Failed to check balances: {e}")

    def _trading_loop(self):
        """Main trading loop"""
        logger.info("Trading loop started")

        while self.is_running:
            try:
                # Safety: check daily loss limit
                if self.risk_manager.check_daily_loss_limit():
                    logger.warning("Daily loss limit reached - pausing 1 hour")
                    time.sleep(3600)
                    continue

                # Execute trade
                self._execute_trade()

                # Wait using current params
                params = self.engine.get_current_params()
                min_int = int(params.get("min_interval", 30))
                max_int = int(params.get("max_interval", 120))
                wait = random.randint(min_int, max(max_int, min_int + 1))

                logger.debug(f"Waiting {wait}s | "
                             f"RL eps={self.engine.rl_agent.epsilon:.3f} | "
                             f"trades={self.trade_count}")
                time.sleep(wait)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                time.sleep(60)

        self.stop()

    def _get_exchange_position(self, symbol: str) -> dict:
        """
        거래소 실제 포지션 조회 — 내부 트래커 대신 거래소가 진실의 원천.

        Returns:
            {"side": "long"|"short"|None, "size": float, "entry": float}
        """
        try:
            positions = self.client.get_open_positions(symbol)
            for p in positions:
                net_qty = float(p.get("netQuantity", 0))
                if abs(net_qty) < 1e-10:
                    continue
                return {
                    "side": "long" if net_qty > 0 else "short",
                    "size": abs(net_qty),
                    "entry": float(p.get("entryPrice", 0)),
                }
        except Exception as e:
            logger.warning(f"[ExSync] 거래소 포지션 조회 실패: {e}")
        return {"side": None, "size": 0, "entry": 0}

    @staticmethod
    def _fmt_qty(size: float, symbol: str = "") -> str:
        """Format quantity as plain decimal within Backpack's allowed precision.

        Backpack Exchange max decimal places per asset:
          BTC perp/spot : 4  (e.g. 0.0001)
          ETH perp/spot : 3  (e.g. 0.001)
          SOL and others: 2  (e.g. 0.01)

        Also rounds DOWN to the nearest step to avoid 'too long' errors.
        """
        sym = symbol.upper()
        if "BTC" in sym:
            decimals = 4
        elif "ETH" in sym:
            decimals = 3
        else:
            decimals = 2

        # Round DOWN (floor) to avoid sending more than available
        import math
        step = 10 ** (-decimals)
        floored = math.floor(size / step) * step
        return f"{floored:.{decimals}f}"

    def _execute_trade(self):
        """Execute a single trade using RL + current params"""
        try:
            symbol = config.trading.symbol
            ticker = self.client.get_ticker(symbol)
            current_price = float(ticker.get("lastPrice", 0))

            if current_price <= 0:
                logger.error("Invalid price")
                return

            # ══════════════════════════════════════════════════════════════
            # Safety 1: 거래소 실제 포지션 동기화 (매 사이클)
            # 내부 트래커가 아닌 거래소 실제 상태를 기준으로 판단
            # ══════════════════════════════════════════════════════════════
            exchange_pos = self._get_exchange_position(symbol)
            ex_side = exchange_pos.get("side")     # "long" | "short" | None
            ex_size = exchange_pos.get("size", 0)  # 절대값
            ex_entry = exchange_pos.get("entry", 0)

            if ex_side:
                logger.info(
                    f"[ExSync] 거래소 실제: {ex_side.upper()} {ex_size} @ ${ex_entry:.2f}"
                )
                # 내부 트래커와 거래소가 다르면 거래소를 따름
                internal = self.risk_manager.positions.get(symbol)
                if not internal or (internal and internal.side != ex_side):
                    # 내부 트래커 리셋 후 거래소 기준 복원
                    if internal:
                        self.risk_manager.close_position(symbol, current_price)
                    # ATR 조회하여 동적 SL/TP 활성화
                    try:
                        _ri = self.client.get_market_regime(symbol)
                        _sync_atr = _ri.get("atr", 0)
                    except Exception:
                        _sync_atr = 0
                    self.risk_manager.open_position(
                        symbol=symbol, entry_price=ex_entry,
                        size=ex_size, side=ex_side,
                        atr=_sync_atr,
                    )
                    logger.info(f"[ExSync] 내부 트래커 → 거래소 기준 복원 (ATR=${_sync_atr:.0f})")
            else:
                # 거래소에 포지션 없는데 내부 트래커에 있으면 제거
                internal = self.risk_manager.positions.get(symbol)
                if internal:
                    self.risk_manager.close_position(symbol, current_price)
                    logger.info(f"[ExSync] 거래소 포지션 없음 → 내부 트래커 정리")

            # ══════════════════════════════════════════════════════════════
            # Safety 1.5: 기존 포지션의 SL/TP 체크 + 트레일링 손익분기
            # _monitor_position()은 신규 포지션에만 실행되므로,
            # 거래소에서 싱크된 기존 포지션의 SL/TP를 여기서 체크
            # ══════════════════════════════════════════════════════════════
            if ex_side:
                position_check = self.risk_manager.positions.get(symbol)
                if position_check:
                    # ── 트레일링 손익분기 SL ──────────────────────────
                    #   TP=0.3~0.5×ATR에 맞춘 비율 (_monitor_position과 동일):
                    #   수익 > 0.2×ATR → SL을 진입가(breakeven)로 이동
                    #   수익 > 0.4×ATR → SL을 진입가±0.15×ATR로 이동 (이익 확정)
                    if hasattr(position_check, '_atr') and position_check._atr > 0:
                        _atr = position_check._atr
                    else:
                        try:
                            _ri = self.client.get_market_regime(symbol)
                            _atr = _ri.get("atr", 0)
                        except Exception:
                            _atr = 0
                    if _atr > 0:
                        entry_p = position_check.entry_price
                        if position_check.side == "long":
                            profit_dist = current_price - entry_p
                            if profit_dist > 0.4 * _atr:
                                new_sl = entry_p + 0.15 * _atr
                                if position_check.stop_loss is None or new_sl > position_check.stop_loss:
                                    old_sl = position_check.stop_loss
                                    position_check.stop_loss = new_sl
                                    logger.info(
                                        f"[TrailBE] LONG 이익확정 SL "
                                        f"${old_sl:.2f}->${new_sl:.2f} (진입+0.15ATR)"
                                    )
                            elif profit_dist > 0.2 * _atr:
                                new_sl = entry_p
                                if position_check.stop_loss is None or new_sl > position_check.stop_loss:
                                    old_sl = position_check.stop_loss
                                    position_check.stop_loss = new_sl
                                    logger.info(
                                        f"[TrailBE] LONG 손익분기 SL "
                                        f"${old_sl:.2f}->${new_sl:.2f} (진입가)"
                                    )
                        else:  # short
                            profit_dist = entry_p - current_price
                            if profit_dist > 0.4 * _atr:
                                new_sl = entry_p - 0.15 * _atr
                                if position_check.stop_loss is None or new_sl < position_check.stop_loss:
                                    old_sl = position_check.stop_loss
                                    position_check.stop_loss = new_sl
                                    logger.info(
                                        f"[TrailBE] SHORT 이익확정 SL "
                                        f"${old_sl:.2f}->${new_sl:.2f} (진입-0.15ATR)"
                                    )
                            elif profit_dist > 0.2 * _atr:
                                new_sl = entry_p
                                if position_check.stop_loss is None or new_sl < position_check.stop_loss:
                                    old_sl = position_check.stop_loss
                                    position_check.stop_loss = new_sl
                                    logger.info(
                                        f"[TrailBE] SHORT 손익분기 SL "
                                        f"${old_sl:.2f}->${new_sl:.2f} (진입가)"
                                    )

                    # ── SL/TP 체크 ──────────────────────────────────
                    if self.risk_manager.check_stop_loss(position_check, current_price):
                        logger.info(
                            f"[SL/TP] [SL] SL 도달! {ex_side.upper()} @ ${current_price:.2f} "
                            f"SL=${position_check.stop_loss:.2f}"
                        )
                        self._close_position(position_check, current_price, "stop_loss")
                        self._last_trade_time = datetime.now()
                        return
                    if self.risk_manager.check_take_profit(position_check, current_price):
                        logger.info(
                            f"[SL/TP] [TP] TP 도달! {ex_side.upper()} @ ${current_price:.2f} "
                            f"TP=${position_check.take_profit:.2f}"
                        )
                        self._close_position(position_check, current_price, "take_profit")
                        self._last_trade_time = datetime.now()
                        return

                    # ── Smart time_limit: 10분 경과 + PnL < 0 → 조기 청산 ──
                    SMART_EXIT_SEC = 600  # 10분
                    hold_secs = (datetime.now() - position_check.entry_time).total_seconds()
                    if hold_secs >= SMART_EXIT_SEC:
                        cur_pnl = self.risk_manager.calculate_pnl(position_check, current_price)
                        if cur_pnl < 0:
                            logger.info(
                                f"[SmartExit] {hold_secs:.0f}s 경과 & PnL=${cur_pnl:.4f}<0 "
                                f"-> 조기 청산 (손실 확대 방지)"
                            )
                            self._close_position(position_check, current_price, "smart_time_limit")
                            self._last_trade_time = datetime.now()
                            return

                    # ── 시간제한 청산 (싱크된 포지션 포함) ──────────────
                    SYNC_MAX_HOLD = 2400  # 40분
                    if hold_secs >= SYNC_MAX_HOLD:
                        pnl = self.risk_manager.calculate_pnl(position_check, current_price)
                        pnl_pct = self.risk_manager.calculate_pnl_percent(position_check, current_price)
                        logger.info(
                            f"[TimeLimit] [TIME] 보유 {hold_secs:.0f}s >= {SYNC_MAX_HOLD}s → 청산 "
                            f"{ex_side.upper()} PnL=${pnl:.4f} ({pnl_pct:+.2f}%)"
                        )
                        self._close_position(position_check, current_price, "time_limit")
                        self._last_trade_time = datetime.now()
                        return

            # ══════════════════════════════════════════════════════════════
            # Safety 2: 쿨다운 — 마지막 거래 후 COOLDOWN_SEC 대기
            # ══════════════════════════════════════════════════════════════
            if hasattr(self, '_last_trade_time') and self._last_trade_time:
                elapsed_since_trade = (datetime.now() - self._last_trade_time).total_seconds()
                if elapsed_since_trade < self.COOLDOWN_SEC:
                    logger.info(
                        f"[Cooldown] 마지막 거래 후 {elapsed_since_trade:.0f}s → "
                        f"{self.COOLDOWN_SEC}s 대기 (남은 {self.COOLDOWN_SEC - elapsed_since_trade:.0f}s)"
                    )
                    return

            # Get available equity
            try:
                cash = self.client.get_available_equity()
                if cash <= 0:
                    logger.info(f"Available equity $0 → using initial capital ${config.trading.initial_capital:.2f}")
                    cash = config.trading.initial_capital
                else:
                    logger.info(f"Available equity: ${cash:.2f}")
            except Exception as e:
                logger.warning(f"Equity check failed ({e}), using initial capital")
                cash = config.trading.initial_capital

            # Update RL state — 거래소 실제 포지션 기준
            position = self.risk_manager.positions.get(symbol)
            entry_price = position.entry_price if position else 0.0
            pos_size = position.size if position else 0.0
            pos_value = pos_size * current_price

            self.engine.on_price_update(
                price=current_price,
                cash=cash,
                position_value=pos_value,
                entry_price=entry_price,
                position_size=pos_size,
            )

            # Get RL action recommendation (참고용 — 진입 결정은 3층 합의가 담당)
            action_id, action_name = self.engine.get_rl_action(training=True)
            logger.info(f"RL recommends: {action_name} (action={action_id}) [참고만]")

            params = self.engine.get_current_params()
            # RL/GA 비활성화: RL의 Hold 판정이 진입을 차단하지 않음
            # 방향 결정은 SMA + Wyckoff + PF 3층 합의가 전적으로 담당
            # RL은 로깅용으로만 유지 (학습 데이터 수집 목적)

            # ── 매매 분석 시스템: 진입 전 신뢰도 평가 ──────────────────────
            price_hist = list(self.engine.state_builder.price_history)
            vol_hist   = list(self.engine.state_builder.volume_history)
            pos_side = position.side if position else None
            # 방향은 아래 3층 합의에서 결정 — 여기서는 잠정적으로 "long" 전달
            prelim_side = "long"

            # ── Analyst: confidence check ────────────────────────────────────
            confidence, conf_reason = self.analyst.get_entry_confidence(
                price_hist, vol_hist, current_price, prelim_side
            )
            size_multiplier = self.analyst.get_position_size_multiplier(confidence)
            logger.info(f"[Confidence] {confidence:.0%} x{size_multiplier} | {conf_reason[:60]}")

            if confidence < 0.20:
                logger.warning(f"Confidence too low ({confidence:.0%}) - skipping")
                return

            # ══════════════════════════════════════════════════════════════
            # Layer 0: 시장 레짐 감지 (횡보 필터)
            # ATR + 볼린저밴드 → 횡보장이면 거래 안 함
            # ══════════════════════════════════════════════════════════════
            regime_info = self.client.get_market_regime(symbol)
            regime = regime_info["regime"]
            atr_pct = regime_info["atr_pct"]
            bb_width = regime_info["bb_width_pct"]
            bb_pos = regime_info["bb_position"]
            atr_val = regime_info["atr"]
            vol_label = regime_info["volatility"]

            eff_ratio = regime_info.get("efficiency_ratio", 0.5)
            logger.info(
                f"[L0·Regime] {regime.upper()} | ATR={atr_pct:.2f}% "
                f"BB폭={bb_width:.2f}% BB위치={bb_pos:.2f} | "
                f"ER={eff_ratio:.2f} vol={vol_label}"
            )

            # 횡보장이면 신규 진입 금지 (기존 포지션은 유지)
            if regime == "ranging" and not ex_side:
                logger.info(
                    f"[Regime] 횡보장 감지 (ER={eff_ratio:.2f}, BB={bb_width:.2f}%) "
                    f"→ 신규 진입 보류"
                )
                return

            # ══════════════════════════════════════════════════════════════
            # Multi-Layer Direction Decision (다층 방향 결정 시스템)
            # Layer 1: SMA 추세 (매크로)     — 1시간 캔들 10기간 이평선
            # Layer 2: 와이코프 수급 분석     — 거래량·호가창·국면
            # Layer 3: Particle Filter (PF)  — 단기 확률 추정
            # 최종: 3층 합의 → 방향 결정
            # ══════════════════════════════════════════════════════════════

            # ── Layer 1: 1h SMA 추세 (매크로 방향) ────────────────────────
            sma_bias = self.client.get_trend_bias(symbol, sma_period=7)
            logger.info(f"[L1·SMA] 1h×7 SMA bias: {sma_bias.upper()}")

            # ── Layer 2: 와이코프 수급 분석 ──────────────────────────────
            try:
                wk_klines = self.client.get_klines(symbol, "1h", hours=14)
                wk_depth  = self.client.get_depth(symbol)
                wk_signal = self.wyckoff.analyze(wk_klines, wk_depth)
                patterns = []
                if wk_signal.churning:  patterns.append("CHURNING!")
                if wk_signal.spring:    patterns.append("SPRING!")
                if wk_signal.upthrust:  patterns.append("UPTHRUST!")
                pat_str = " ".join(patterns) if patterns else "-"
                logger.info(
                    f"[L2-Wyckoff] bias={wk_signal.bias.upper()} "
                    f"str={wk_signal.strength:.0%} phase={wk_signal.phase} "
                    f"consol={wk_signal.consolidation_bars}bar | "
                    f"EVR={wk_signal.effort_result} "
                    f"OB={wk_signal.orderbook_bias}({wk_signal.orderbook_ratio:.2f}) | "
                    f"patterns=[{pat_str}] | {wk_signal.detail}"
                )
            except Exception as we:
                logger.warning(f"[L2·Wyckoff] 분석 실패: {we}")
                wk_signal = None

            # ── Layer 3: Particle Filter (단기) ──────────────────────────
            p_up, pf_regime = self.pf.update(current_price)
            logger.info(f"[L3·PF] {self.pf.summary()}")

            # ── 3층 합의 방향 결정 ───────────────────────────────────────
            # 점수 체계: SMA(±2) + Wyckoff(±1~2) + PF(±1) = max ±5
            dir_score = 0.0
            dir_reasons = []

            # SMA (가중치 2 — 매크로 추세가 가장 중요)
            if sma_bias == "long":
                dir_score += 2.0
                dir_reasons.append("SMA:LONG(+2)")
            elif sma_bias == "short":
                dir_score -= 2.0
                dir_reasons.append("SMA:SHORT(-2)")
            else:
                dir_reasons.append("SMA:중립(0)")

            # Wyckoff (가중치 1~2 — 수급 확인)
            if wk_signal:
                wk_weight = 1.0 + wk_signal.strength  # 1.0~2.0
                if wk_signal.bias == "long":
                    dir_score += wk_weight
                    dir_reasons.append(f"WK:LONG(+{wk_weight:.1f})")
                elif wk_signal.bias == "short":
                    dir_score -= wk_weight
                    dir_reasons.append(f"WK:SHORT(-{wk_weight:.1f})")
                else:
                    dir_reasons.append("WK:중립(0)")

                # 와이코프 분배 국면이면 LONG 점수 차감
                if wk_signal.phase == "distribution" and dir_score > 0:
                    dir_score -= 0.5
                    dir_reasons.append("분배경고(-0.5)")
                elif wk_signal.phase == "accumulation" and dir_score < 0:
                    dir_score += 0.5
                    dir_reasons.append("매집신호(+0.5)")

            # PF (가중치 1 — 단기 확인)
            if self.pf.is_ready():
                if p_up >= 0.55:
                    dir_score += 1.0
                    dir_reasons.append(f"PF:{p_up:.0%}(+1)")
                elif p_up <= 0.45:
                    dir_score -= 1.0
                    dir_reasons.append(f"PF:{p_up:.0%}(-1)")
                else:
                    dir_reasons.append(f"PF:{p_up:.0%}(0)")

            # ══════════════════════════════════════════════════════════════
            # 히스테리시스 방향 결정 (플립플롭 방지)
            #   신규 진입:  |score| ≥ ENTRY_THRESHOLD (1.0)
            #   방향 전환:  |score| ≥ FLIP_THRESHOLD  (2.5) — 더 강한 신호 필요
            #   최소 보유:  MIN_HOLD_SEC (300s) 이내 전환 금지
            # ══════════════════════════════════════════════════════════════

            # 현재 포지션 보유시간 계산
            hold_sec = 0
            if self._position_open_time:
                hold_sec = (datetime.now() - self._position_open_time).total_seconds()

            # 기준 결정: 포지션 있으면 FLIP_THRESHOLD, 없으면 ENTRY_THRESHOLD
            if ex_side:
                threshold = self.FLIP_THRESHOLD
                threshold_label = f"FLIP({threshold})"
            else:
                threshold = self.ENTRY_THRESHOLD
                threshold_label = f"ENTRY({threshold})"

            logger.info(
                f"[Signal] 합산점수={dir_score:+.1f} | 기준={threshold_label} | "
                f"보유={hold_sec:.0f}s | "
                + " ".join(dir_reasons)
            )

            # 방향 판정
            if dir_score >= threshold:
                final_direction = "long"
            elif dir_score <= -threshold:
                final_direction = "short"
            else:
                if ex_side:
                    logger.info(
                        f"[Signal] 점수={dir_score:+.1f} < FLIP기준(±{threshold}) "
                        f"→ {ex_side.upper()} 유지"
                    )
                else:
                    logger.info(
                        f"[Signal] 점수={dir_score:+.1f} 불충분 → HOLD"
                    )
                return

            # ── Neutral trend 차단: SMA 중립이면 신규 진입 금지 ─────
            if not ex_side and sma_bias == "neutral":
                logger.info(
                    f"[TrendFilter] SMA=neutral → 추세 없음, "
                    f"{final_direction.upper()} 신규 진입 거부"
                )
                return

            # ── SMA 방향 불일치 차단 (신규 진입 시) ──────────────────
            if not ex_side and sma_bias != "neutral":
                if (final_direction == "long" and sma_bias == "short") or \
                   (final_direction == "short" and sma_bias == "long"):
                    logger.info(
                        f"[TrendFilter] SMA={sma_bias.upper()} vs "
                        f"진입={final_direction.upper()} → 역추세 진입 거부"
                    )
                    return

            # ── 최소 보유시간 체크 (포지션 전환 시에만) ─────────────────
            if ex_side and ex_side != final_direction:
                if hold_sec < self.MIN_HOLD_SEC:
                    logger.info(
                        f"[MinHold] {ex_side.upper()} 보유 {hold_sec:.0f}s "
                        f"< {self.MIN_HOLD_SEC}s → 전환 보류 (유지)"
                    )
                    return

            # ── BB 포지션 필터 (신규 진입 타이밍 최적화) ──────────────
            #   LONG:  BB위치 < 0.5 (밴드 중심 이하 = 저평가 영역)
            #   SHORT: BB위치 > 0.5 (밴드 중심 이상 = 고평가 영역)
            #   강한 신호(|score| ≥ 3.0)면 BB 무시 (추세 우선)
            #   기존 같은 방향 포지션 유지 시에는 필터 미적용
            BB_LONG_MAX  = 0.5
            BB_SHORT_MIN = 0.5
            BB_BYPASS_SCORE = 3.0  # 이 이상이면 BB 필터 무시
            if not (ex_side and ex_side == final_direction):
                strong_signal = abs(dir_score) >= BB_BYPASS_SCORE
                if strong_signal:
                    logger.info(
                        f"[BB필터] 강한신호({dir_score:+.1f}) → BB무시, "
                        f"{final_direction.upper()} 진입 허가"
                    )
                elif final_direction == "long" and bb_pos > BB_LONG_MAX:
                    logger.info(
                        f"[BB필터] LONG 진입 거부 — BB위치={bb_pos:.2f} > {BB_LONG_MAX} "
                        f"(밴드 중심 이상 → 진입 불리)"
                    )
                    return
                elif final_direction == "short" and bb_pos < BB_SHORT_MIN:
                    logger.info(
                        f"[BB필터] SHORT 진입 거부 — BB위치={bb_pos:.2f} < {BB_SHORT_MIN} "
                        f"(밴드 중심 이하 → 진입 불리)"
                    )
                    return
                else:
                    logger.info(
                        f"[BB필터] {final_direction.upper()} 진입 허가 — BB위치={bb_pos:.2f}"
                    )
            # ══════════════════════════════════════════════════════════════

            # 최종 방향 확정 (3층 합의 결과 그대로 사용)
            logger.info(f"[Direction] FINAL={final_direction.upper()} (RL참고: {action_name})")

            # ── 신호 강도 기반 포지션 사이징 ─────────────────────────
            # |score| ≥ 4.0 → 2배, |score| ≥ 3.0 → 1.5배, 기본 1배
            # 와이코프 거래량 확인 시 +30%
            signal_boost = 1.0
            abs_score = abs(dir_score)
            if abs_score >= 4.0:
                signal_boost = 2.0
                logger.info(f"[Sizing] 매우 강한 신호({dir_score:+.1f}) → 포지션 2배")
            elif abs_score >= 3.0:
                signal_boost = 1.5
                logger.info(f"[Sizing] 강한 신호({dir_score:+.1f}) → 포지션 1.5배")

            wk_size_boost = 1.0
            if wk_signal and wk_signal.volume_confirm and wk_signal.bias == final_direction:
                wk_size_boost = 1.3  # 거래량 확인 시 30% 더 진입
                logger.info(f"[Wyckoff] 거래량 확인 → 포지션 +30%")

            # (RL 사이징 제거 — 포지션 크기는 max_coins 기반으로 결정)
            # ─────────────────────────────────────────────────────────────

            self._entry_context = self.analyst.capture_context(
                price_hist, vol_hist, current_price
            )
            self._entry_confidence = confidence
            self._entry_time = datetime.now()

            # ── Min order size by asset ──────────────────────────────────────
            sym_upper = symbol.upper()
            if "BTC" in sym_upper:   MIN_ORDER_SIZE = 0.0005   # 최소 0.0005 (was 0.0002) — 수수료 비중↓
            elif "ETH" in sym_upper: MIN_ORDER_SIZE = 0.005    # ETH도 상향
            else:                    MIN_ORDER_SIZE = 0.01
            max_coins = float(params.get("trade_size", config.strategy.trade_size))

            # ── Position size: 기본 × 신호강도 × 와이코프 ────────────
            position_size = max_coins * size_multiplier * signal_boost * wk_size_boost
            if position_size < MIN_ORDER_SIZE:
                position_size = MIN_ORDER_SIZE   # floor to exchange minimum

            # ── 수수료 필터: 예상 수익 < 왕복 수수료면 진입 금지 ──────
            est_fee = self.risk_manager.estimate_round_trip_fee(current_price, position_size)
            # 예상 수익 = TP까지의 수익 (수수료 제외 기준)
            if atr_val > 0:
                tp_multiplier = 0.3 if regime == "ranging" else 0.5
                est_profit = tp_multiplier * atr_val * position_size
            else:
                est_profit = current_price * position_size * 0.01  # fallback 1%
            fee_ratio = est_fee / est_profit if est_profit > 0 else 999

            if fee_ratio > 0.5:  # 수수료가 예상수익의 50% 이상이면
                logger.info(
                    f"[FeeFilter] 진입 거부 - 수수료=${est_fee:.4f} vs "
                    f"예상수익=${est_profit:.4f} (수수료비중={fee_ratio:.0%})"
                )
                return
            else:
                logger.info(
                    f"[FeeFilter] 통과 - 수수료=${est_fee:.4f} / "
                    f"예상수익=${est_profit:.4f} (비중={fee_ratio:.0%})"
                )

            # ══════════════════════════════════════════════════════════════
            # Safety 3: 거래소 실제 포지션 기준 진입/청산 (부분청산 제거)
            # 한 번에 전환: LONG→청산→SHORT (다음 사이클에서 신규 진입)
            # Safety 4: 포지션 크기 상한 = max_coins
            # ══════════════════════════════════════════════════════════════

            # 거래소 기준 포지션 확인 (Safety 1에서 동기화한 값)
            ex_side_now = ex_side     # "long" | "short" | None
            ex_size_now = ex_size     # 절대값

            # ── 이미 같은 방향 포지션 보유 → 스킵 ────────────────
            if ex_side_now == final_direction:
                logger.info(
                    f"Already {final_direction.upper()} {ex_size_now} "
                    f"- skipping (거래소 확인)"
                )
                return

            # ── 반대 방향 포지션 보유 → 청산만 (반대 진입 안 함) ──
            # flip 거래는 승률 23%로 최대 손실 원인 → 청산 후 쿨다운 강제
            if ex_side_now and ex_side_now != final_direction:
                close_side = "Ask" if ex_side_now == "long" else "Bid"
                qty_str = self._fmt_qty(ex_size_now, symbol)
                logger.info(
                    f"[Signal Exit] {ex_side_now.upper()} {qty_str} 반대신호 청산 "
                    f"(flip 진입 금지 → 쿨다운 후 신규 진입)"
                )
                self.client.place_market_order(
                    symbol=symbol, side=close_side, quantity=qty_str
                )
                # 내부 트래커 정리
                if position:
                    pnl = self.risk_manager.calculate_pnl(position, current_price)
                    pnl_pct = self.risk_manager.calculate_pnl_percent(position, current_price)
                    # fee 표시 (혼합: maker 진입 + taker 청산)
                    fee_entry = position.entry_price * position.size * self.risk_manager.MAKER_FEE
                    fee_exit = current_price * position.size * self.risk_manager.TAKER_FEE
                    fee = fee_entry + fee_exit
                    logger.info(
                        f"[Close] {position.side.upper()} {qty_str} {symbol} "
                        f"@ ${current_price:.2f} | reason=signal_exit | "
                        f"PnL=${pnl:.4f} ({pnl_pct:+.2f}%) | fee=${fee:.4f} "
                        f"| 누적fee=${self.risk_manager.total_fees + fee:.2f}"
                    )
                    self.risk_manager.close_position(symbol, current_price)
                    # 헷지 정리
                    try:
                        self.hedge_manager.close_all("signal_exit")
                    except Exception:
                        pass
                    # RL 학습 기록
                    trade_record = {
                        "pnl": pnl, "pnl_percent": pnl_pct,
                        "exit_reason": "signal_exit",
                    }
                    self.engine.on_trade_completed(trade=trade_record, next_price=current_price)
                self._last_trade_time = datetime.now()
                self._position_open_time = None
                return   # 청산만 — 쿨다운(900s) 후 신규 진입 가능

            # ── 포지션 없음 → 신규 진입 ──────────────────────────
            # Safety 4: 포지션 상한 = max_coins (기본 사이즈)
            # 0.002 BTC 시 SL 1회에 -$1.02 (자본 2.2%) → 과도한 리스크
            # signal_boost 효과는 base_size 내에서만 작용하도록 제한
            MAX_POSITION_CAP = max_coins
            if position_size > MAX_POSITION_CAP:
                position_size = MAX_POSITION_CAP
                logger.info(f"[Safety] 포지션 크기 → {MAX_POSITION_CAP}으로 제한")

            order_side = "Bid" if final_direction == "long" else "Ask"
            qty_str = self._fmt_qty(position_size, symbol)
            notional_est = current_price * position_size

            # ── 리밋 오더 진입 (maker 수수료 0.02%) ────────────────────
            # 1) 오더북에서 최우선 호가 조회
            try:
                book = self.client.get_best_bid_ask(symbol)
            except Exception as e:
                logger.warning(f"[Entry] 오더북 조회 실패: {e} → 스킵")
                return

            # LONG: best_bid에 매수, SHORT: best_ask에 매도
            if final_direction == "long":
                limit_price = book["best_bid"]
            else:
                limit_price = book["best_ask"]

            logger.info(
                f"[Entry] {final_direction.upper()} {qty_str} {symbol} "
                f"limit@${limit_price:.2f} (last=${current_price:.2f} "
                f"spread=${book['spread']:.2f}) "
                f"| notional=${notional_est:.2f} | conf={size_multiplier} "
                f"sig={signal_boost} | est_fee=${est_fee:.4f} est_tp=${est_profit:.4f}"
            )

            # 2) Post-only 리밋 주문 (스프레드 교차 시 거부 → maker 보장)
            try:
                order_resp = self.client.place_post_only_limit_order(
                    symbol=symbol,
                    side=order_side,
                    price=str(limit_price),
                    quantity=qty_str,
                )
                order_id = order_resp.get("id")
            except Exception as e:
                logger.warning(f"[Entry] Post-only 거부/실패: {e} → 스킵")
                return

            if not order_id:
                logger.warning("[Entry] 주문 ID 없음 → 스킵")
                return

            # 3) Fill 대기 (최대 30초, 2초 간격 폴링)
            FILL_TIMEOUT = 30
            FILL_POLL = 2
            fill_elapsed = 0
            fill_info = {"filled": False, "fill_price": 0.0, "fill_size": 0.0}

            while fill_elapsed < FILL_TIMEOUT:
                time.sleep(FILL_POLL)
                fill_elapsed += FILL_POLL

                # 주문이 아직 오더북에 있는지 확인
                open_orders = self.client.get_open_orders(symbol)
                order_still_open = any(
                    o.get("id") == order_id for o in open_orders
                )

                if not order_still_open:
                    # 주문 사라짐 → 체결 확인 (API 전파 지연 대비 재시도)
                    for _retry in range(3):
                        fill_info = self.client.get_order_fill_price(symbol, order_id)
                        if fill_info["filled"]:
                            break
                        time.sleep(1)  # 전파 대기
                    break

            # 4) 타임아웃 → 취소 후 재확인
            if not fill_info["filled"]:
                if fill_elapsed >= FILL_TIMEOUT:
                    try:
                        self.client.cancel_order(symbol, order_id)
                        logger.info(
                            f"[Entry] 리밋 {FILL_TIMEOUT}초 미체결 → 취소"
                        )
                    except Exception:
                        pass  # 이미 체결/취소됨

                    # 취소 후 부분 체결 재확인
                    fill_info = self.client.get_order_fill_price(symbol, order_id)

                # 최종 안전장치: 거래소 실제 포지션 확인
                if not fill_info["filled"]:
                    try:
                        ex_positions = self.client.get_open_positions(symbol)
                        for ep in ex_positions:
                            nq = float(ep.get("netQuantity", 0))
                            if abs(nq) > 0:
                                logger.warning(
                                    f"[Entry] fill_history 비었지만 거래소에 포지션 존재! "
                                    f"qty={nq} → 동기화 진행"
                                )
                                fill_info = {
                                    "filled": True,
                                    "fill_price": float(ep.get("entryPrice", limit_price)),
                                    "fill_size": abs(nq),
                                }
                                break
                    except Exception as sync_e:
                        logger.error(f"[Entry] 포지션 확인 실패: {sync_e}")

                if not fill_info["filled"]:
                    logger.info(f"[Entry] 미체결 → 이번 진입 스킵")
                    return

            # 5) 실제 체결 데이터로 포지션 기록
            actual_price = fill_info["fill_price"]
            actual_size = fill_info["fill_size"]

            # Dust filter: 의도량의 10% 미만이면 무시
            intended_size = float(qty_str)
            if actual_size < intended_size * 0.1:
                logger.info(
                    f"[Entry] Dust 체결 {actual_size} < {intended_size * 0.1:.6f} → 스킵"
                )
                return

            pos = self.risk_manager.open_position(
                symbol=symbol, entry_price=actual_price,
                size=actual_size, side=final_direction,
                atr=atr_val, regime=regime,
            )
            sl_dist_pct = abs(actual_price - pos.stop_loss) / actual_price * 100
            tp_dist_pct = abs(pos.take_profit - actual_price) / actual_price * 100
            logger.info(
                f"{final_direction.upper()} filled @ ${actual_price:.2f} "
                f"(limit=${limit_price:.2f}) qty={actual_size} "
                f"| wait={fill_elapsed}s | "
                f"SL=${pos.stop_loss:.2f}({sl_dist_pct:.2f}%) "
                f"TP=${pos.take_profit:.2f}({tp_dist_pct:.2f}%) "
                f"| ATR=${atr_val:.0f}"
            )
            self._last_trade_time = datetime.now()
            self._position_open_time = datetime.now()
            self._monitor_position(pos, regime=regime)

            self.trade_count += 1

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")

    def _monitor_position(self, position, regime: str = "trending"):
        """Monitor position until SL/TP or time limit"""
        symbol = position.symbol
        check_interval = 5
        # 레짐별 시간제한: 횡보장 30분 / 추세장 40분
        if regime == "ranging":
            max_hold = 1800   # 30분 — 횡보장은 빠른 회전
        else:
            max_hold = 2400   # 40분 — 추세장은 더 오래 보유
        elapsed = 0
        LOG_INTERVAL = 60  # 60초마다 상태 로그

        logger.info(
            f"[Monitor] 시작 | {position.side.upper()} {position.size} {symbol} "
            f"@ ${position.entry_price:.2f} | SL=${position.stop_loss:.2f} "
            f"TP=${position.take_profit:.2f} | max_hold={max_hold}s"
        )

        while elapsed < max_hold:
            try:
                ticker = self.client.get_ticker(symbol)
                price = float(ticker.get("lastPrice", 0))
                self._monitor_errors = 0  # 정상 조회 → 에러 카운터 리셋

                self.pf.update(price)   # 포지션 보유 중에도 필터 업데이트

                new_stop = self.risk_manager.update_trailing_stop(position, price)
                if new_stop:
                    position.stop_loss = new_stop
                    logger.info(f"[Monitor] 트레일링 SL 갱신 → ${new_stop:.2f}")

                # ── 트레일링 손익분기 SL (ATR 기반) ──────────────
                #   TP=0.3~0.5×ATR에 맞춘 비율:
                #   수익 > 0.2×ATR → SL을 진입가(breakeven)로 이동
                #   수익 > 0.4×ATR → SL을 진입가±0.15×ATR로 이동 (이익 확정)
                _atr = getattr(position, '_atr', 0)
                if _atr > 0:
                    entry_p = position.entry_price
                    if position.side == "long":
                        profit_dist = price - entry_p
                        if profit_dist > 0.4 * _atr:
                            new_be = entry_p + 0.15 * _atr
                            if position.stop_loss is None or new_be > position.stop_loss:
                                logger.info(
                                    f"[TrailBE] LONG 이익확정 SL↑ "
                                    f"${position.stop_loss:.2f}→${new_be:.2f}"
                                )
                                position.stop_loss = new_be
                        elif profit_dist > 0.2 * _atr:
                            new_be = entry_p
                            if position.stop_loss is None or new_be > position.stop_loss:
                                logger.info(
                                    f"[TrailBE] LONG 손익분기 SL↑ "
                                    f"${position.stop_loss:.2f}→${new_be:.2f}"
                                )
                                position.stop_loss = new_be
                    else:  # short
                        profit_dist = entry_p - price
                        if profit_dist > 0.4 * _atr:
                            new_be = entry_p - 0.15 * _atr
                            if position.stop_loss is None or new_be < position.stop_loss:
                                logger.info(
                                    f"[TrailBE] SHORT 이익확정 SL↓ "
                                    f"${position.stop_loss:.2f}→${new_be:.2f}"
                                )
                                position.stop_loss = new_be
                        elif profit_dist > 0.2 * _atr:
                            new_be = entry_p
                            if position.stop_loss is None or new_be < position.stop_loss:
                                logger.info(
                                    f"[TrailBE] SHORT 손익분기 SL↓ "
                                    f"${position.stop_loss:.2f}→${new_be:.2f}"
                                )
                                position.stop_loss = new_be

                if self.risk_manager.check_stop_loss(position, price):
                    logger.info(f"[Monitor] [SL] SL 도달! price=${price:.2f} SL=${position.stop_loss:.2f}")
                    self._close_position(position, price, "stop_loss")
                    return

                if self.risk_manager.check_take_profit(position, price):
                    logger.info(f"[Monitor] [TP] TP 도달! price=${price:.2f} TP=${position.take_profit:.2f}")
                    self._close_position(position, price, "take_profit")
                    return

                # ── 주기적 상태 로그 (60초마다) ────────────────────────────
                if elapsed > 0 and elapsed % LOG_INTERVAL == 0:
                    pnl = self.risk_manager.calculate_pnl(position, price)
                    pnl_pct = self.risk_manager.calculate_pnl_percent(position, price)
                    sl_dist = abs(price - position.stop_loss) / price * 100
                    tp_dist = abs(position.take_profit - price) / price * 100
                    remaining = max_hold - elapsed
                    logger.info(
                        f"[Monitor] {elapsed}s/{max_hold}s | "
                        f"${price:.2f} | PnL=${pnl:.4f}({pnl_pct:+.2f}%) | "
                        f"SL까지 {sl_dist:.2f}% TP까지 {tp_dist:.2f}% | "
                        f"남은 {remaining}s"
                    )

                # ── 헷지 체크 (30초마다) ─────────────────────────────────
                if elapsed > 0 and elapsed % 30 == 0:
                    try:
                        self.hedge_manager.check_and_hedge(position, price)
                        hs = self.hedge_manager.get_status()
                        if hs.get("active"):
                            logger.info(
                                f"[Hedge] {hs['symbol']} {hs['side'].upper()} "
                                f"{hs['size']} @ ${hs['entry_price']:.2f}"
                            )
                    except Exception as he:
                        logger.error(f"[Hedge] check error: {he}")

                # ── Smart time_limit: 10분 경과 + PnL < 0 → 조기 청산 ──
                SMART_EXIT_SEC = 600  # 10분
                if elapsed >= SMART_EXIT_SEC:
                    cur_pnl = self.risk_manager.calculate_pnl(position, price)
                    if cur_pnl < 0:
                        logger.info(
                            f"[SmartExit] {elapsed}s 경과 & PnL=${cur_pnl:.4f}<0 "
                            f"→ 조기 청산 (손실 확대 방지)"
                        )
                        self._close_position(position, price, "smart_time_limit")
                        return
                # ─────────────────────────────────────────────────────────

                time.sleep(check_interval)
                elapsed += check_interval

            except Exception as e:
                # BUG #4 FIX: 네트워크 에러 시 즉시 break → 재시도
                if not hasattr(self, '_monitor_errors'):
                    self._monitor_errors = 0
                self._monitor_errors += 1
                logger.error(f"[Monitor] 에러 ({self._monitor_errors}/5): {e}")
                if self._monitor_errors >= 5:
                    logger.error("[Monitor] 연속 5회 에러 → 루프 종료")
                    self._monitor_errors = 0
                    break
                time.sleep(check_interval)
                elapsed += check_interval
                continue
        self._monitor_errors = 0  # 정상 종료 시 카운터 리셋

        # Time limit reached
        logger.info(f"[Monitor] [TIME] 시간 초과 ({max_hold}s) → 포지션 청산")
        try:
            ticker = self.client.get_ticker(symbol)
            price = float(ticker.get("lastPrice", 0))
            self._close_position(position, price, "time_limit")
        except Exception as e:
            logger.error(f"Failed to close at time limit: {e}")

    def _close_position(self, position, exit_price: float, reason: str) -> float:
        """Close position, record trade, notify engine"""
        symbol = position.symbol
        pnl = self.risk_manager.calculate_pnl(position, exit_price)
        pnl_percent = self.risk_manager.calculate_pnl_percent(position, exit_price)

        # ── 헷지 먼저 종료 (메인 포지션 청산 전) ────────────────────────
        try:
            self.hedge_manager.close_all(reason)
        except Exception as he:
            logger.error(f"[Hedge] close_all error on {reason}: {he}")
        # ─────────────────────────────────────────────────────────────────

        try:
            close_side = "Ask" if position.side == "long" else "Bid"
            qty_str = self._fmt_qty(position.size, symbol)
            fee_entry = position.entry_price * position.size * self.risk_manager.MAKER_FEE
            fee_exit = exit_price * position.size * self.risk_manager.TAKER_FEE
            fee = fee_entry + fee_exit
            logger.info(
                f"[Close] {position.side.upper()} {qty_str} {symbol} "
                f"@ ${exit_price:.2f} | reason={reason} | "
                f"PnL=${pnl:.4f} ({pnl_percent:+.2f}%) | fee=${fee:.4f} "
                f"| 누적fee=${self.risk_manager.total_fees + fee:.2f}"
            )
            self.client.place_market_order(
                symbol=symbol,
                side=close_side,
                quantity=qty_str
            )
            # 주문 성공 후에만 내부 트래커 정리
            self.risk_manager.close_position(symbol, exit_price)
        except Exception as e:
            logger.error(f"Order placement failed: {e} - 내부 포지션 유지 (다음 사이클 재시도)")

        # 보유 시간 계산
        duration_sec = 0.0
        if self._entry_time:
            duration_sec = (datetime.now() - self._entry_time).total_seconds()

        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "size": position.size,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "exit_reason": reason,
            "duration_seconds": duration_sec,
        }

        # ── 매매 분석 시스템: 청산 후 사후 분석 ──────────────────────────
        if self._entry_context is not None:
            try:
                analyzed = self.analyst.record_exit(
                    trade=trade_record,
                    entry_context=self._entry_context,
                    confidence_at_entry=self._entry_confidence,
                )
                self.analyst.print_analysis(analyzed)
            except Exception as e:
                logger.error(f"매매 분석 실패: {e}")
            finally:
                self._entry_context = None
                self._entry_confidence = 0.5
                self._entry_time = None
        # ─────────────────────────────────────────────────────────────────

        # Notify self-improvement engine
        self.engine.on_trade_completed(
            trade=trade_record,
            next_price=exit_price,
        )

        logger.info(f"Position closed [{reason}] PnL=${pnl:.4f} ({pnl_percent:.2f}%)")
        return pnl

    def _close_position_partial(self, position, exit_price, ratio, reason):
        """Partial close (for RL sell signals)"""
        pnl = self.risk_manager.calculate_pnl(position, exit_price) * ratio
        pnl_percent = self.risk_manager.calculate_pnl_percent(position, exit_price)

        trade_record = {
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "exit_reason": reason,
        }
        self.engine.on_trade_completed(trade=trade_record, next_price=exit_price)
        return pnl

    def _close_all_positions(self):
        for symbol, position in list(self.risk_manager.positions.items()):
            try:
                ticker = self.client.get_ticker(symbol)
                price = float(ticker.get("lastPrice", 0))
                self._close_position(position, price, "shutdown")
            except Exception as e:
                logger.error(f"Failed to close {symbol}: {e}")

    def _print_final_stats(self):
        status = self.engine.get_status()
        print("\n" + "=" * 60)
        print("FINAL STATISTICS - Self-Improving Bot")
        print("=" * 60)
        print(f"\nTotal Trades: {self.trade_count}")

        perf = status.get("performance", {})
        if perf:
            print(f"\nPerformance:")
            print(f"  Win Rate:      {perf.get('win_rate', 0):.1f}%")
            print(f"  Sharpe Ratio:  {perf.get('sharpe_ratio', 0):.3f}")
            print(f"  Total PnL:     ${perf.get('total_pnl', 0):.2f}")
            print(f"  Max Drawdown:  ${perf.get('max_drawdown', 0):.2f}")

        rl = status.get("rl_agent", {})
        print(f"\nRL Agent:")
        print(f"  Steps trained: {rl.get('steps', 0)}")
        print(f"  Final epsilon: {rl.get('epsilon', 1.0):.4f}")
        print(f"  Avg loss:      {rl.get('avg_loss', 0):.6f}")
        print(f"  Actions: {rl.get('action_distribution', {})}")

        imp = status.get("improvement_history", {})
        print(f"\nSelf-Improvement:")
        print(f"  Total cycles:       {imp.get('total_cycles', 0)}")
        print(f"  Accepted:           {imp.get('accepted', 0)}")
        print(f"  Rejected:           {imp.get('rejected', 0)}")
        print(f"  Avg improvement:    {imp.get('avg_improvement_pct', 0):.1f}%")

        print(f"\nFinal Params:")
        for k, v in status.get("current_params", {}).items():
            print(f"  {k}: {v}")

        # 매매 분석 요약
        self.analyst.print_summary()

        print("=" * 60 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

_bot_instance: Optional[SelfImprovingTradingBot] = None


def signal_handler(sig, frame):
    global _bot_instance
    logger.info("Shutdown signal received")
    if _bot_instance:
        _bot_instance.stop()
    sys.exit(0)


def main():
    global _bot_instance
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    _bot_instance = SelfImprovingTradingBot()
    _bot_instance.start()


if __name__ == "__main__":
    main()
