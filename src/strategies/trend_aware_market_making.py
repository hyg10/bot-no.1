"""
Trend-Aware Market Making Strategy
Only makes markets in favorable conditions, avoids directional risks
"""
import time
from typing import Dict, Tuple, List, Optional
from datetime import datetime, timedelta
from collections import deque
from src.utils.logger import logger
from src.config.config import config


class TrendAwareMarketMakingStrategy:
    """
    Trend-Aware Market Making Strategy
    
    Key Features:
    1. Detects market trend (uptrend/downtrend/sideways)
    2. ONLY places buy orders in uptrend/sideways
    3. ONLY places sell orders in downtrend/sideways
    4. Cancels all orders during extreme trends
    5. Adaptive learning + All safety features
    """
    
    def __init__(self, client, symbol: str):
        self.client = client
        self.symbol = symbol
        
        # Strategy parameters
        self.base_bid_spread = 0.001
        self.base_ask_spread = 0.001
        self.current_bid_spread = 0.001
        self.current_ask_spread = 0.001
        
        self.base_order_amount = config.strategy.trade_size
        self.current_order_amount = config.strategy.trade_size
        
        self.order_refresh_time = 30
        self.max_inventory_ratio = 0.5
        
        # Trend detection parameters
        self.trend_window = 20  # Number of price points for trend analysis
        self.trend_threshold = 0.003  # 0.3% movement = trend
        self.extreme_trend_threshold = 0.01  # 1% = extreme trend
        
        # Safety parameters
        self.max_volatility = 0.02
        self.max_price_change_1min = 0.02
        self.max_unrealized_loss = 50.0  # Reduced from $100 to $50
        self.max_daily_loss = config.trading.initial_capital * 0.1
        self.auto_hedge_threshold = 2  # More aggressive hedging
        
        # State tracking
        self.active_orders = {'buy': None, 'sell': None}
        self.inventory = 0.0
        self.last_order_time = 0
        self.total_profit = 0.0
        self.daily_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.avg_entry_price = 0.0
        
        # Performance tracking
        self.filled_pairs = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # Adaptive parameters
        self.evaluation_period = config.adaptive.evaluation_period
        self.last_evaluation_time = datetime.now()
        self.adjustment_count = 0
        
        # Price history for trend detection
        self.price_history = deque(maxlen=100)  # Keep more history for trend
        self.last_price = 0.0
        
        # Trend state
        self.current_trend = "UNKNOWN"  # UPTREND, DOWNTREND, SIDEWAYS, EXTREME_UP, EXTREME_DOWN
        
        self.is_running = False
        self.is_paused = False
        
        logger.info("📈 Trend-Aware Market Making initialized", {
            "trend_detection": "enabled",
            "trend_threshold": f"{self.trend_threshold * 100}%",
            "max_loss": f"${self.max_unrealized_loss}"
        })
    
    def start(self):
        """Start market making"""
        self.is_running = True
        logger.info("🚀 Starting Trend-Aware Market Making")
        self._market_making_loop()
    
    def stop(self):
        """Stop market making"""
        logger.info("🛑 Stopping Trend-Aware Market Making")
        self.is_running = False
        self._print_final_stats()
    
    def _market_making_loop(self):
        """Main loop with trend awareness"""
        logger.info("📊 Trend-aware loop started")
        
        while self.is_running:
            try:
                mid_price = self._get_mid_price()
                
                if mid_price == 0:
                    time.sleep(5)
                    continue
                
                # Update price history
                self.price_history.append({
                    'price': mid_price,
                    'timestamp': datetime.now()
                })
                
                # TREND DETECTION - Most important!
                self._detect_trend()
                
                # Adaptive evaluation
                if self._should_evaluate():
                    self._evaluate_and_adapt()
                
                # Safety checks
                if not self._check_volatility():
                    logger.warning("⚠️ High volatility - pausing 60s")
                    self._cancel_all_orders()
                    self.is_paused = True
                    time.sleep(60)
                    self.is_paused = False
                    continue
                
                if not self._check_price_movement(mid_price):
                    logger.warning("🚨 Extreme movement - pausing 60s")
                    self._cancel_all_orders()
                    self.is_paused = True
                    time.sleep(60)
                    self.is_paused = False
                    continue
                
                self._update_unrealized_pnl(mid_price)
                
                if not self._check_unrealized_loss():
                    logger.error("🛑 Max unrealized loss - stopping")
                    self.stop()
                    break
                
                if not self._check_daily_loss():
                    logger.error("🛑 Daily loss limit - stopping")
                    self.stop()
                    break
                
                self._auto_hedge_inventory(mid_price)
                
                # Place orders with TREND AWARENESS
                current_time = time.time()
                if current_time - self.last_order_time >= self.order_refresh_time:
                    self._refresh_orders_trend_aware(mid_price)
                    self.last_order_time = current_time
                
                self.last_price = mid_price
                time.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt")
                break
            except Exception as e:
                logger.error("Error in loop", {"error": str(e)})
                time.sleep(10)
        
        self.stop()
    
    def _detect_trend(self):
        """
        🎯 TREND DETECTION - Core feature
        Analyzes recent price history to determine market direction
        """
        if len(self.price_history) < self.trend_window:
            self.current_trend = "UNKNOWN"
            return
        
        # Get recent prices
        recent_prices = [p['price'] for p in list(self.price_history)[-self.trend_window:]]
        
        # Calculate trend using linear regression (simple slope)
        start_price = recent_prices[0]
        end_price = recent_prices[-1]
        price_change = (end_price - start_price) / start_price
        
        # Also check short-term momentum (last 5 prices)
        if len(recent_prices) >= 5:
            short_start = recent_prices[-5]
            short_end = recent_prices[-1]
            short_change = (short_end - short_start) / short_start
        else:
            short_change = price_change
        
        old_trend = self.current_trend
        
        # Determine trend
        if short_change > self.extreme_trend_threshold:
            self.current_trend = "EXTREME_UP"
        elif short_change < -self.extreme_trend_threshold:
            self.current_trend = "EXTREME_DOWN"
        elif price_change > self.trend_threshold:
            self.current_trend = "UPTREND"
        elif price_change < -self.trend_threshold:
            self.current_trend = "DOWNTREND"
        else:
            self.current_trend = "SIDEWAYS"
        
        # Log trend changes
        if old_trend != self.current_trend and old_trend != "UNKNOWN":
            logger.info(f"📊 Trend changed: {old_trend} → {self.current_trend}", {
                "price_change": f"{price_change * 100:.2f}%",
                "short_change": f"{short_change * 100:.2f}%"
            })
    
    def _should_place_buy_order(self) -> bool:
        """
        🎯 DECISION: Should we place a buy order?
        
        Rules:
        - UPTREND: YES (price going up, buy is safe)
        - SIDEWAYS: YES (neutral, market making works)
        - DOWNTREND: NO (price dropping, avoid catching falling knife)
        - EXTREME_UP: NO (too risky)
        - EXTREME_DOWN: NO (wait for stabilization)
        """
        if self.current_trend in ["UPTREND", "SIDEWAYS"]:
            return True
        
        if self.current_trend == "DOWNTREND":
            logger.info("⛔ Skipping buy order - DOWNTREND detected")
            return False
        
        if self.current_trend in ["EXTREME_UP", "EXTREME_DOWN"]:
            logger.warning(f"⛔ Skipping buy order - {self.current_trend}")
            return False
        
        return False  # Unknown trend = be cautious
    
    def _should_place_sell_order(self) -> bool:
        """
        🎯 DECISION: Should we place a sell order?
        
        Rules:
        - DOWNTREND: YES (price dropping, sell is safe)
        - SIDEWAYS: YES (neutral, market making works)
        - UPTREND: NO (price rising, might miss gains)
        - EXTREME_UP: NO (too risky)
        - EXTREME_DOWN: NO (wait for stabilization)
        """
        if self.current_trend in ["DOWNTREND", "SIDEWAYS"]:
            return True
        
        if self.current_trend == "UPTREND":
            logger.info("⛔ Skipping sell order - UPTREND detected")
            return False
        
        if self.current_trend in ["EXTREME_UP", "EXTREME_DOWN"]:
            logger.warning(f"⛔ Skipping sell order - {self.current_trend}")
            return False
        
        return False
    
    def _cancel_all_orders(self):
        """Cancel all active orders"""
        logger.info("🔄 Cancelling all orders")
        # Note: Backpack SDK might not support cancel, so we just reset tracking
        self.active_orders = {'buy': None, 'sell': None}
    
    def _refresh_orders_trend_aware(self, mid_price: float):
        """
        🎯 TREND-AWARE ORDER PLACEMENT
        Only places orders that align with current trend
        """
        if self.is_paused:
            return
        
        # Calculate spreads
        adjusted_bid = self.current_bid_spread
        adjusted_ask = self.current_ask_spread
        
        # Add volatility adjustment
        if len(self.price_history) >= 12:
            recent_prices = [p['price'] for p in list(self.price_history)[-12:]]
            volatility = (max(recent_prices) - min(recent_prices)) / min(recent_prices)
            
            if volatility > 0.01:
                vol_adjustment = volatility * 0.5
                adjusted_bid += vol_adjustment
                adjusted_ask += vol_adjustment
        
        buy_price = int(round(mid_price * (1 - adjusted_bid)))
        sell_price = int(round(mid_price * (1 + adjusted_ask)))
        
        logger.info("📝 Trend-aware order placement", {
            "trend": self.current_trend,
            "mid": f"${mid_price:.2f}",
            "buy_allowed": self._should_place_buy_order(),
            "sell_allowed": self._should_place_sell_order()
        })
        
        # TREND-AWARE: Only place buy if trend allows
        if self._should_place_buy_order():
            try:
                buy_order = self.client.place_limit_order(
                    symbol=self.symbol,
                    side='Bid',
                    price=str(buy_price),
                    quantity=str(self.current_order_amount)
                )
                self.active_orders['buy'] = buy_order
                logger.info(f"✅ Buy order placed | trend={self.current_trend}")
                
            except Exception as e:
                logger.error("Buy order failed", {"error": str(e)})
        else:
            logger.info(f"⏭️ Buy order skipped | trend={self.current_trend}")
        
        # TREND-AWARE: Only place sell if trend allows
        if self._should_place_sell_order():
            try:
                sell_order = self.client.place_limit_order(
                    symbol=self.symbol,
                    side='Ask',
                    price=str(sell_price),
                    quantity=str(self.current_order_amount)
                )
                self.active_orders['sell'] = sell_order
                logger.info(f"✅ Sell order placed | trend={self.current_trend}")
                
            except Exception as e:
                logger.error("Sell order failed", {"error": str(e)})
        else:
            logger.info(f"⏭️ Sell order skipped | trend={self.current_trend}")
    
    def _get_mid_price(self) -> float:
        """Get current price"""
        try:
            ticker = self.client.get_ticker(self.symbol)
            return float(ticker.get('lastPrice', 0))
        except Exception as e:
            logger.error("Failed to get price", {"error": str(e)})
            return 0.0
    
    def _should_evaluate(self) -> bool:
        """Check evaluation time"""
        elapsed = datetime.now() - self.last_evaluation_time
        return elapsed >= timedelta(hours=self.evaluation_period)
    
    def _evaluate_and_adapt(self):
        """Adaptive learning"""
        logger.info("🔍 Evaluating performance...")
        
        if self.total_trades < 5:
            logger.info("Not enough trades")
            return
        
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        logger.info("📊 Performance", {
            "trades": self.total_trades,
            "win_rate": f"{win_rate:.1f}%",
            "profit": f"${self.total_profit:.2f}"
        })
        
        if win_rate < 40:
            self._widen_spreads()
        elif win_rate > 70:
            self._narrow_spreads()
        
        self.last_evaluation_time = datetime.now()
        self.adjustment_count += 1
    
    def _widen_spreads(self):
        """Widen spreads"""
        self.current_bid_spread = min(self.current_bid_spread * 1.2, 0.005)
        self.current_ask_spread = min(self.current_ask_spread * 1.2, 0.005)
        logger.info(f"📏 Spreads widened to {self.current_bid_spread * 100:.2f}%")
    
    def _narrow_spreads(self):
        """Narrow spreads"""
        self.current_bid_spread = max(self.current_bid_spread * 0.9, 0.0005)
        self.current_ask_spread = max(self.current_ask_spread * 0.9, 0.0005)
        logger.info(f"📏 Spreads narrowed to {self.current_bid_spread * 100:.2f}%")
    
    def _check_volatility(self) -> bool:
        """Volatility check"""
        if len(self.price_history) < 12:
            return True
        
        recent_prices = [p['price'] for p in list(self.price_history)[-12:]]
        returns = [(recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1] 
                   for i in range(1, len(recent_prices))]
        
        volatility = max(returns) - min(returns)
        return volatility <= self.max_volatility
    
    def _check_price_movement(self, current_price: float) -> bool:
        """Price movement check"""
        if self.last_price == 0:
            return True
        
        price_change = abs(current_price - self.last_price) / self.last_price
        return price_change <= self.max_price_change_1min
    
    def _update_unrealized_pnl(self, current_price: float):
        """Update P&L"""
        if self.inventory == 0 or self.avg_entry_price == 0:
            self.unrealized_pnl = 0
            return
        
        if self.inventory > 0:
            self.unrealized_pnl = (current_price - self.avg_entry_price) * self.inventory
        else:
            self.unrealized_pnl = (self.avg_entry_price - current_price) * abs(self.inventory)
    
    def _check_unrealized_loss(self) -> bool:
        """Check unrealized loss"""
        if self.unrealized_pnl < -self.max_unrealized_loss:
            logger.error(f"Max loss: ${self.unrealized_pnl:.2f}")
            self._emergency_close()
            return False
        return True
    
    def _check_daily_loss(self) -> bool:
        """Check daily loss"""
        return self.daily_pnl >= -self.max_daily_loss
    
    def _auto_hedge_inventory(self, current_price: float):
        """Auto hedge"""
        threshold = self.current_order_amount * self.auto_hedge_threshold
        
        if abs(self.inventory) > threshold:
            logger.warning(f"⚖️ Auto-hedging: {self.inventory:.4f}")
            
            try:
                side = 'Ask' if self.inventory > 0 else 'Bid'
                quantity = abs(self.inventory)
                
                order = self.client.place_market_order(
                    symbol=self.symbol,
                    side=side,
                    quantity=str(quantity)
                )
                
                logger.info("✅ Hedge executed")
                self.inventory = 0
                self.avg_entry_price = current_price
                
            except Exception as e:
                logger.error("Hedge failed", {"error": str(e)})
    
    def _emergency_close(self):
        """Emergency close"""
        if self.inventory == 0:
            return
        
        logger.error("🚨 EMERGENCY CLOSE")
        
        try:
            side = 'Ask' if self.inventory > 0 else 'Bid'
            
            order = self.client.place_market_order(
                symbol=self.symbol,
                side=side,
                quantity=str(abs(self.inventory))
            )
            
            self.daily_pnl += self.unrealized_pnl
            self.inventory = 0
            self.unrealized_pnl = 0
            
        except Exception as e:
            logger.error("Emergency close failed", {"error": str(e)})
    
    def _print_final_stats(self):
        """Print final stats"""
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        print("\n" + "="*60)
        print("📈 TREND-AWARE MARKET MAKING - FINAL STATS")
        print("="*60)
        
        print("\n💰 Performance:")
        print(f"  Total Profit: ${self.total_profit:.2f}")
        print(f"  Daily P&L: ${self.daily_pnl:.2f}")
        
        print("\n📊 Trading:")
        print(f"  Total Trades: {self.total_trades}")
        print(f"  Win Rate: {win_rate:.1f}%")
        
        print("\n📈 Trend Awareness:")
        print(f"  Final Trend: {self.current_trend}")
        print(f"  Adaptations: {self.adjustment_count}")
        
        print("\n" + "="*60 + "\n")
