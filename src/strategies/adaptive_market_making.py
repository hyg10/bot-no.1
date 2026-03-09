"""
Adaptive Market Making Strategy
With learning, performance tracking, and automatic parameter adjustment
"""
import time
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
from collections import deque
from src.utils.logger import logger
from src.config.config import config


class AdaptiveMarketMakingStrategy:
    """
    Adaptive Market Making Strategy
    
    Features:
    1. Performance tracking (win rate, profit, spread effectiveness)
    2. Automatic spread adjustment based on performance
    3. Dynamic position sizing based on success
    4. Learning from filled orders
    5. All safety features from safe version
    """
    
    def __init__(self, client, symbol: str):
        self.client = client
        self.symbol = symbol
        
        # Base strategy parameters (will adapt)
        self.base_bid_spread = 0.001
        self.base_ask_spread = 0.001
        self.current_bid_spread = 0.001
        self.current_ask_spread = 0.001
        
        self.base_order_amount = config.strategy.trade_size
        self.current_order_amount = config.strategy.trade_size
        
        self.order_refresh_time = 30
        self.max_inventory_ratio = 0.5
        
        # Safety parameters
        self.max_volatility = 0.02
        self.max_price_change_1min = 0.02
        self.max_unrealized_loss = 100.0
        self.max_daily_loss = config.trading.initial_capital * 0.1
        self.auto_hedge_threshold = 3
        
        # State tracking
        self.active_orders = {'buy': None, 'sell': None}
        self.inventory = 0.0
        self.last_order_time = 0
        self.total_profit = 0.0
        self.daily_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.avg_entry_price = 0.0
        
        # Performance tracking for adaptive learning
        self.filled_pairs = []  # List of completed buy-sell pairs
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.avg_spread_captured = 0.0
        
        # Evaluation periods
        self.evaluation_period = config.adaptive.evaluation_period  # hours
        self.last_evaluation_time = datetime.now()
        self.adjustment_count = 0
        
        # Price history
        self.price_history = deque(maxlen=60)
        self.last_price = 0.0
        
        self.is_running = False
        self.is_paused = False
        
        logger.info("🧠 Adaptive Market Making Strategy initialized", {
            "base_spread": f"{self.base_bid_spread * 100}%",
            "evaluation_period": f"{self.evaluation_period}h",
            "learning": "enabled"
        })
    
    def start(self):
        """Start market making"""
        self.is_running = True
        logger.info("🚀 Starting Adaptive Market Making Strategy")
        self._market_making_loop()
    
    def stop(self):
        """Stop market making"""
        logger.info("🛑 Stopping Adaptive Market Making Strategy")
        self.is_running = False
        self._print_final_stats()
    
    def _market_making_loop(self):
        """Main market making loop with adaptive learning"""
        logger.info("📊 Adaptive market making loop started")
        
        while self.is_running:
            try:
                mid_price = self._get_mid_price()
                
                if mid_price == 0:
                    time.sleep(5)
                    continue
                
                self.price_history.append({
                    'price': mid_price,
                    'timestamp': datetime.now()
                })
                
                # ADAPTIVE FEATURE: Evaluate and adjust parameters
                if self._should_evaluate():
                    self._evaluate_and_adapt()
                
                # Safety checks
                if not self._check_volatility():
                    logger.warning("⚠️ High volatility - pausing 60s")
                    self.is_paused = True
                    time.sleep(60)
                    self.is_paused = False
                    continue
                
                if not self._check_price_movement(mid_price):
                    logger.warning("🚨 Extreme movement - pausing 60s")
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
                
                # Place/refresh orders with ADAPTIVE parameters
                current_time = time.time()
                if current_time - self.last_order_time >= self.order_refresh_time:
                    self._refresh_orders(mid_price)
                    self.last_order_time = current_time
                
                self.last_price = mid_price
                time.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                break
            except Exception as e:
                logger.error("Error in loop", {"error": str(e)})
                time.sleep(10)
        
        self.stop()
    
    def _should_evaluate(self) -> bool:
        """Check if it's time to evaluate performance"""
        elapsed = datetime.now() - self.last_evaluation_time
        return elapsed >= timedelta(hours=self.evaluation_period)
    
    def _evaluate_and_adapt(self):
        """
        🧠 ADAPTIVE LEARNING: Evaluate performance and adjust parameters
        """
        logger.info("🔍 Evaluating performance and adapting strategy...")
        
        if self.total_trades < 5:
            logger.info("Not enough trades for evaluation (need 5+)")
            return
        
        # Calculate metrics
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        profit_per_trade = self.total_profit / self.total_trades if self.total_trades > 0 else 0
        
        logger.info("📊 Performance Metrics", {
            "total_trades": self.total_trades,
            "win_rate": f"{win_rate:.1f}%",
            "profit_per_trade": f"${profit_per_trade:.2f}",
            "total_profit": f"${self.total_profit:.2f}",
            "current_spread": f"{self.current_bid_spread * 100:.2f}%"
        })
        
        # ADAPTATION RULE 1: Win rate based adjustment
        if win_rate < 40:
            # Poor performance - widen spreads for better fills
            self._widen_spreads()
            logger.warning(f"⚠️ Low win rate ({win_rate:.1f}%) - Widening spreads")
        
        elif win_rate > 70:
            # Excellent performance - can narrow spreads
            self._narrow_spreads()
            logger.info(f"✅ High win rate ({win_rate:.1f}%) - Narrowing spreads")
        
        # ADAPTATION RULE 2: Profit per trade
        if profit_per_trade < 1.0 and self.total_trades > 10:
            # Low profit - increase spread
            self._widen_spreads()
            logger.warning(f"⚠️ Low profit per trade (${profit_per_trade:.2f}) - Widening spreads")
        
        elif profit_per_trade > 5.0:
            # High profit - can be more aggressive
            self._increase_position_size()
            logger.info(f"✅ High profit per trade (${profit_per_trade:.2f}) - Increasing size")
        
        # ADAPTATION RULE 3: Spread effectiveness
        if len(self.filled_pairs) > 0:
            avg_spread_captured = sum(p['spread_captured'] for p in self.filled_pairs) / len(self.filled_pairs)
            
            if avg_spread_captured < 0.0005:  # Less than 0.05%
                self._widen_spreads()
                logger.warning("⚠️ Low spread capture - Widening spreads")
        
        # ADAPTATION RULE 4: Consecutive losses
        if self.losing_trades >= 3 and self.winning_trades == 0:
            self._reduce_position_size()
            self._widen_spreads()
            logger.error("🛑 Consecutive losses - Reducing risk")
        
        self.last_evaluation_time = datetime.now()
        self.adjustment_count += 1
        
        logger.info(f"🔄 Adaptation #{self.adjustment_count} complete")
    
    def _widen_spreads(self):
        """Widen spreads for better fill rate"""
        self.current_bid_spread = min(self.current_bid_spread * 1.2, 0.005)  # Max 0.5%
        self.current_ask_spread = min(self.current_ask_spread * 1.2, 0.005)
        
        logger.info(f"📏 Spreads widened to {self.current_bid_spread * 100:.2f}%")
    
    def _narrow_spreads(self):
        """Narrow spreads for more profit"""
        self.current_bid_spread = max(self.current_bid_spread * 0.9, 0.0005)  # Min 0.05%
        self.current_ask_spread = max(self.current_ask_spread * 0.9, 0.0005)
        
        logger.info(f"📏 Spreads narrowed to {self.current_bid_spread * 100:.2f}%")
    
    def _increase_position_size(self):
        """Increase position size"""
        max_size = self.base_order_amount * 1.5
        self.current_order_amount = min(self.current_order_amount * 1.1, max_size)
        
        logger.info(f"📈 Position size increased to {self.current_order_amount:.4f}")
    
    def _reduce_position_size(self):
        """Reduce position size"""
        min_size = self.base_order_amount * 0.5
        self.current_order_amount = max(self.current_order_amount * 0.8, min_size)
        
        logger.info(f"📉 Position size reduced to {self.current_order_amount:.4f}")
    
    def _record_trade(self, buy_price: float, sell_price: float, quantity: float):
        """Record a completed trade for learning"""
        spread_captured = (sell_price - buy_price) / buy_price
        profit = (sell_price - buy_price) * quantity
        
        self.filled_pairs.append({
            'buy_price': buy_price,
            'sell_price': sell_price,
            'quantity': quantity,
            'spread_captured': spread_captured,
            'profit': profit,
            'timestamp': datetime.now()
        })
        
        self.total_trades += 1
        
        if profit > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        self.total_profit += profit
        
        logger.info(f"💰 Trade recorded | profit=${profit:.2f} | spread={spread_captured*100:.2f}%")
    
    def _get_mid_price(self) -> float:
        """Get current market price"""
        try:
            ticker = self.client.get_ticker(self.symbol)
            return float(ticker.get('lastPrice', 0))
        except Exception as e:
            logger.error("Failed to get price", {"error": str(e)})
            return 0.0
    
    def _check_volatility(self) -> bool:
        """Volatility check"""
        if len(self.price_history) < 12:
            return True
        
        recent_prices = [p['price'] for p in list(self.price_history)[-12:]]
        returns = [(recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1] 
                   for i in range(1, len(recent_prices))]
        
        volatility = max(returns) - min(returns)
        
        if volatility > self.max_volatility:
            logger.warning(f"High volatility: {volatility*100:.2f}%")
            return False
        
        return True
    
    def _check_price_movement(self, current_price: float) -> bool:
        """Extreme price movement check"""
        if self.last_price == 0:
            return True
        
        price_change = abs(current_price - self.last_price) / self.last_price
        
        if price_change > self.max_price_change_1min:
            logger.warning(f"Extreme movement: {price_change*100:.2f}%")
            return False
        
        return True
    
    def _update_unrealized_pnl(self, current_price: float):
        """Update unrealized P&L"""
        if self.inventory == 0 or self.avg_entry_price == 0:
            self.unrealized_pnl = 0
            return
        
        if self.inventory > 0:
            self.unrealized_pnl = (current_price - self.avg_entry_price) * self.inventory
        else:
            self.unrealized_pnl = (self.avg_entry_price - current_price) * abs(self.inventory)
    
    def _check_unrealized_loss(self) -> bool:
        """Check max unrealized loss"""
        if self.unrealized_pnl < -self.max_unrealized_loss:
            logger.error(f"Max unrealized loss: ${self.unrealized_pnl:.2f}")
            self._emergency_close()
            return False
        return True
    
    def _check_daily_loss(self) -> bool:
        """Check daily loss limit"""
        if self.daily_pnl < -self.max_daily_loss:
            logger.error(f"Daily loss limit: ${self.daily_pnl:.2f}")
            return False
        return True
    
    def _auto_hedge_inventory(self, current_price: float):
        """Auto-hedge inventory"""
        threshold = self.current_order_amount * self.auto_hedge_threshold
        
        if abs(self.inventory) > threshold:
            logger.warning(f"⚖️ Auto-hedging: {self.inventory:.4f}")
            
            try:
                if self.inventory > 0:
                    side = 'Ask'
                else:
                    side = 'Bid'
                
                quantity = abs(self.inventory)
                
                order = self.client.place_market_order(
                    symbol=self.symbol,
                    side=side,
                    quantity=str(quantity)
                )
                
                logger.info(f"✅ Hedge executed | side={side}")
                
                if self.inventory > 0:
                    self.inventory -= quantity
                else:
                    self.inventory += quantity
                
                self.avg_entry_price = current_price
                
            except Exception as e:
                logger.error("Failed to hedge", {"error": str(e)})
    
    def _emergency_close(self):
        """Emergency close all positions"""
        if self.inventory == 0:
            return
        
        logger.error("🚨 EMERGENCY CLOSE")
        
        try:
            if self.inventory > 0:
                side = 'Ask'
            else:
                side = 'Bid'
            
            order = self.client.place_market_order(
                symbol=self.symbol,
                side=side,
                quantity=str(abs(self.inventory))
            )
            
            logger.info("Emergency close executed")
            
            self.daily_pnl += self.unrealized_pnl
            self.inventory = 0
            self.unrealized_pnl = 0
            self.avg_entry_price = 0
            
        except Exception as e:
            logger.error("Failed to emergency close", {"error": str(e)})
    
    def _refresh_orders(self, mid_price: float):
        """Refresh orders with ADAPTIVE parameters"""
        if self.is_paused:
            return
        
        # Use CURRENT (adaptive) spreads, not base spreads
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
        
        # Calculate prices
        buy_price = int(round(mid_price * (1 - adjusted_bid)))
        sell_price = int(round(mid_price * (1 + adjusted_ask)))
        
        logger.info("📝 Placing adaptive orders", {
            "mid": f"${mid_price:.2f}",
            "buy": f"${buy_price}",
            "sell": f"${sell_price}",
            "spread": f"{(adjusted_bid + adjusted_ask)*100:.2f}%",
            "size": f"{self.current_order_amount:.4f}"
        })
        
        # Place orders with CURRENT (adaptive) size
        try:
            buy_order = self.client.place_limit_order(
                symbol=self.symbol,
                side='Bid',
                price=str(buy_price),
                quantity=str(self.current_order_amount)
            )
            self.active_orders['buy'] = buy_order
            logger.info("✅ Buy order placed")
            
        except Exception as e:
            logger.error("Buy order failed", {"error": str(e)})
        
        try:
            sell_order = self.client.place_limit_order(
                symbol=self.symbol,
                side='Ask',
                price=str(sell_price),
                quantity=str(self.current_order_amount)
            )
            self.active_orders['sell'] = sell_order
            logger.info("✅ Sell order placed")
            
        except Exception as e:
            logger.error("Sell order failed", {"error": str(e)})
    
    def _print_final_stats(self):
        """Print final statistics"""
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        print("\n" + "="*60)
        print("🧠 ADAPTIVE MARKET MAKING - FINAL STATISTICS")
        print("="*60)
        
        print("\n💰 Performance:")
        print(f"  Total Profit: ${self.total_profit:.2f}")
        print(f"  Daily P&L: ${self.daily_pnl:.2f}")
        print(f"  Unrealized P&L: ${self.unrealized_pnl:.2f}")
        
        print("\n📊 Trading Stats:")
        print(f"  Total Trades: {self.total_trades}")
        print(f"  Winning Trades: {self.winning_trades}")
        print(f"  Losing Trades: {self.losing_trades}")
        print(f"  Win Rate: {win_rate:.1f}%")
        
        print("\n🔄 Adaptive Learning:")
        print(f"  Evaluations: {self.adjustment_count}")
        print(f"  Base Spread: {self.base_bid_spread * 100:.2f}%")
        print(f"  Final Spread: {self.current_bid_spread * 100:.2f}%")
        print(f"  Base Size: {self.base_order_amount:.4f}")
        print(f"  Final Size: {self.current_order_amount:.4f}")
        
        print("\n⚖️ Inventory:")
        print(f"  Current: {self.inventory:.4f}")
        
        print("\n" + "="*60 + "\n")
