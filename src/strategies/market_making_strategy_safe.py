"""
Pure Market Making Strategy - Complete Safety Version
With volatility detection, auto-hedge, and loss limits
"""
import time
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
from collections import deque
from src.utils.logger import logger
from src.config.config import config


class PureMarketMakingStrategy:
    """
    Pure Market Making Strategy with Complete Safety Features:
    1. Volatility detection & auto-pause
    2. Inventory auto-hedge
    3. Maximum loss limits
    4. Dynamic spread adjustment
    """
    
    def __init__(self, client, symbol: str):
        self.client = client
        self.symbol = symbol
        
        # Strategy parameters
        self.bid_spread = 0.001  # 0.1% below mid price
        self.ask_spread = 0.001  # 0.1% above mid price
        self.order_amount = config.strategy.trade_size
        self.order_refresh_time = 30
        self.max_inventory_ratio = 0.5
        
        # Safety parameters
        self.max_volatility = 0.02  # 2% - pause if exceeded
        self.max_price_change_1min = 0.02  # 2% per minute
        self.max_unrealized_loss = 100.0  # $100 max unrealized loss
        self.max_daily_loss = config.trading.initial_capital * 0.1  # 10% of capital
        self.auto_hedge_threshold = 3  # Hedge when inventory > 3x order_amount
        
        # State tracking
        self.active_orders = {'buy': None, 'sell': None}
        self.inventory = 0.0
        self.last_order_time = 0
        self.total_profit = 0.0
        self.daily_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.avg_entry_price = 0.0
        
        # Price history for volatility calculation
        self.price_history = deque(maxlen=60)  # Last 60 prices (5 min at 5s interval)
        self.last_price = 0.0
        
        self.is_running = False
        self.is_paused = False
        
        logger.info("Pure Market Making Strategy initialized with full safety", {
            "max_volatility": f"{self.max_volatility * 100}%",
            "max_loss": f"${self.max_unrealized_loss}",
            "auto_hedge": f"{self.auto_hedge_threshold}x"
        })
    
    def start(self):
        """Start market making"""
        self.is_running = True
        logger.info("🚀 Starting Pure Market Making Strategy with Safety Features")
        self._market_making_loop()
    
    def stop(self):
        """Stop market making"""
        logger.info("🛑 Stopping Market Making Strategy")
        self.is_running = False
        self._print_final_stats()
    
    def _market_making_loop(self):
        """Main market making loop with safety checks"""
        logger.info("📊 Market making loop started")
        
        while self.is_running:
            try:
                # Get current price
                mid_price = self._get_mid_price()
                
                if mid_price == 0:
                    time.sleep(5)
                    continue
                
                # Update price history
                self.price_history.append({
                    'price': mid_price,
                    'timestamp': datetime.now()
                })
                
                # SAFETY CHECK 1: Volatility check
                if not self._check_volatility():
                    logger.warning("⚠️ High volatility detected - pausing for 60s")
                    self.is_paused = True
                    time.sleep(60)
                    self.is_paused = False
                    continue
                
                # SAFETY CHECK 2: Extreme price movement
                if not self._check_price_movement(mid_price):
                    logger.warning("🚨 Extreme price movement - pausing for 60s")
                    self.is_paused = True
                    time.sleep(60)
                    self.is_paused = False
                    continue
                
                # SAFETY CHECK 3: Maximum unrealized loss
                self._update_unrealized_pnl(mid_price)
                if not self._check_unrealized_loss():
                    logger.error("🛑 Maximum unrealized loss reached - stopping bot")
                    self.stop()
                    break
                
                # SAFETY CHECK 4: Daily loss limit
                if not self._check_daily_loss():
                    logger.error("🛑 Daily loss limit reached - stopping bot")
                    self.stop()
                    break
                
                # SAFETY CHECK 5: Auto-hedge if inventory imbalanced
                self._auto_hedge_inventory(mid_price)
                
                # Place/refresh orders
                current_time = time.time()
                if current_time - self.last_order_time >= self.order_refresh_time:
                    self._refresh_orders(mid_price)
                    self.last_order_time = current_time
                
                # Update last price
                self.last_price = mid_price
                
                # Wait before next cycle
                time.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                break
            except Exception as e:
                logger.error("Error in market making loop", {"error": str(e)})
                time.sleep(10)
        
        self.stop()
    
    def _get_mid_price(self) -> float:
        """Get current market price"""
        try:
            ticker = self.client.get_ticker(self.symbol)
            return float(ticker.get('lastPrice', 0))
        except Exception as e:
            logger.error("Failed to get price", {"error": str(e)})
            return 0.0
    
    def _check_volatility(self) -> bool:
        """
        SAFETY CHECK 1: Volatility Detection
        Returns False if volatility is too high
        """
        if len(self.price_history) < 12:  # Need at least 1 minute of data
            return True
        
        # Calculate volatility over last minute (12 samples at 5s interval)
        recent_prices = [p['price'] for p in list(self.price_history)[-12:]]
        returns = [(recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1] 
                   for i in range(1, len(recent_prices))]
        
        volatility = max(returns) - min(returns)  # Range
        
        if volatility > self.max_volatility:
            logger.warning(f"High volatility detected: {volatility*100:.2f}%")
            return False
        
        return True
    
    def _check_price_movement(self, current_price: float) -> bool:
        """
        SAFETY CHECK 2: Extreme Price Movement Detection
        Returns False if price moved too much too fast
        """
        if self.last_price == 0:
            return True
        
        price_change = abs(current_price - self.last_price) / self.last_price
        
        if price_change > self.max_price_change_1min:
            logger.warning(f"Extreme price movement: {price_change*100:.2f}%")
            return False
        
        return True
    
    def _update_unrealized_pnl(self, current_price: float):
        """Update unrealized P&L"""
        if self.inventory == 0 or self.avg_entry_price == 0:
            self.unrealized_pnl = 0
            return
        
        # Calculate unrealized P&L
        if self.inventory > 0:  # Long position
            self.unrealized_pnl = (current_price - self.avg_entry_price) * self.inventory
        else:  # Short position
            self.unrealized_pnl = (self.avg_entry_price - current_price) * abs(self.inventory)
    
    def _check_unrealized_loss(self) -> bool:
        """
        SAFETY CHECK 3: Maximum Unrealized Loss
        Returns False if unrealized loss exceeds limit
        """
        if self.unrealized_pnl < -self.max_unrealized_loss:
            logger.error(f"Max unrealized loss exceeded: ${self.unrealized_pnl:.2f}")
            
            # Emergency close - hedge all inventory
            self._emergency_close()
            return False
        
        return True
    
    def _check_daily_loss(self) -> bool:
        """
        SAFETY CHECK 4: Daily Loss Limit
        Returns False if daily loss exceeds limit
        """
        if self.daily_pnl < -self.max_daily_loss:
            logger.error(f"Daily loss limit exceeded: ${self.daily_pnl:.2f}")
            return False
        
        return True
    
    def _auto_hedge_inventory(self, current_price: float):
        """
        SAFETY CHECK 5: Auto-hedge Inventory
        Automatically hedge when inventory is too imbalanced
        """
        threshold = self.order_amount * self.auto_hedge_threshold
        
        if abs(self.inventory) > threshold:
            excess = self.inventory
            
            logger.warning(f"⚖️ Auto-hedging inventory: {excess:.4f}")
            
            try:
                if excess > 0:
                    # Too much bought - sell at market
                    side = 'Ask'
                    quantity = abs(excess)
                else:
                    # Too much sold - buy at market
                    side = 'Bid'
                    quantity = abs(excess)
                
                # Place market order to hedge
                order = self.client.place_market_order(
                    symbol=self.symbol,
                    side=side,
                    quantity=str(quantity)
                )
                
                logger.info(f"✅ Hedge order executed | side={side} | qty={quantity:.4f}")
                
                # Update inventory
                if excess > 0:
                    self.inventory -= quantity
                else:
                    self.inventory += quantity
                
                # Update average entry price
                self.avg_entry_price = current_price
                
            except Exception as e:
                logger.error("Failed to hedge inventory", {"error": str(e)})
    
    def _emergency_close(self):
        """Emergency close all positions"""
        if self.inventory == 0:
            return
        
        logger.error("🚨 EMERGENCY CLOSE - Hedging all inventory")
        
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
            
            # Record loss
            self.daily_pnl += self.unrealized_pnl
            
            # Reset
            self.inventory = 0
            self.unrealized_pnl = 0
            self.avg_entry_price = 0
            
        except Exception as e:
            logger.error("Failed to emergency close", {"error": str(e)})
    
    def _adjust_spreads_for_inventory(self) -> Tuple[float, float]:
        """Adjust spreads based on inventory and volatility"""
        if self.order_amount == 0:
            return self.bid_spread, self.ask_spread
        
        # Inventory-based adjustment
        inventory_ratio = self.inventory / (self.order_amount * 10)
        inventory_ratio = max(-0.5, min(0.5, inventory_ratio))
        
        bid_adjustment = inventory_ratio * 0.0005
        ask_adjustment = -inventory_ratio * 0.0005
        
        # Volatility-based adjustment
        if len(self.price_history) >= 12:
            recent_prices = [p['price'] for p in list(self.price_history)[-12:]]
            volatility = (max(recent_prices) - min(recent_prices)) / min(recent_prices)
            
            if volatility > 0.01:  # 1% volatility
                # Widen spreads in volatile markets
                volatility_adjustment = volatility * 0.5
                bid_adjustment += volatility_adjustment
                ask_adjustment += volatility_adjustment
                
                logger.info(f"📊 Widening spreads due to volatility: {volatility*100:.2f}%")
        
        adjusted_bid = max(0.0001, self.bid_spread + bid_adjustment)
        adjusted_ask = max(0.0001, self.ask_spread + ask_adjustment)
        
        return adjusted_bid, adjusted_ask
    
    def _refresh_orders(self, mid_price: float):
        """Refresh buy and sell orders"""
        if self.is_paused:
            logger.info("⏸️ Paused - skipping order placement")
            return
        
        # Adjust spreads
        adjusted_bid, adjusted_ask = self._adjust_spreads_for_inventory()
        
        # Calculate prices (integers for PERP)
        buy_price = int(round(mid_price * (1 - adjusted_bid)))
        sell_price = int(round(mid_price * (1 + adjusted_ask)))
        
        logger.info("📝 Placing orders", {
            "mid": f"${mid_price:.2f}",
            "buy": f"${buy_price}",
            "sell": f"${sell_price}",
            "spread": f"{(adjusted_bid + adjusted_ask)*100:.2f}%",
            "inventory": f"{self.inventory:.4f}"
        })
        
        # Place buy order
        try:
            buy_order = self.client.place_limit_order(
                symbol=self.symbol,
                side='Bid',
                price=str(buy_price),
                quantity=str(self.order_amount)
            )
            self.active_orders['buy'] = buy_order
            logger.info("✅ Buy order placed")
            
            # Update average entry price
            if self.inventory >= 0:
                total_value = self.avg_entry_price * self.inventory + buy_price * self.order_amount
                total_quantity = self.inventory + self.order_amount
                self.avg_entry_price = total_value / total_quantity if total_quantity > 0 else buy_price
            
        except Exception as e:
            logger.error("Failed to place buy order", {"error": str(e)})
        
        # Place sell order
        try:
            sell_order = self.client.place_limit_order(
                symbol=self.symbol,
                side='Ask',
                price=str(sell_price),
                quantity=str(self.order_amount)
            )
            self.active_orders['sell'] = sell_order
            logger.info("✅ Sell order placed")
            
        except Exception as e:
            logger.error("Failed to place sell order", {"error": str(e)})
    
    def _print_final_stats(self):
        """Print final statistics"""
        print("\n" + "="*60)
        print("MARKET MAKING FINAL STATISTICS")
        print("="*60)
        
        print("\n💰 Performance:")
        print(f"  Total Profit: ${self.total_profit:.2f}")
        print(f"  Daily P&L: ${self.daily_pnl:.2f}")
        print(f"  Unrealized P&L: ${self.unrealized_pnl:.2f}")
        
        print("\n⚖️ Inventory:")
        print(f"  Current Inventory: {self.inventory:.4f}")
        print(f"  Average Entry: ${self.avg_entry_price:.2f}")
        
        print("\n🛡️ Safety Stats:")
        print(f"  Max Unrealized Loss: ${self.max_unrealized_loss}")
        print(f"  Max Daily Loss: ${self.max_daily_loss:.2f}")
        
        print("\n" + "="*60 + "\n")
    
    def get_status(self) -> Dict:
        """Get current strategy status"""
        return {
            'is_running': self.is_running,
            'is_paused': self.is_paused,
            'inventory': self.inventory,
            'unrealized_pnl': self.unrealized_pnl,
            'daily_pnl': self.daily_pnl,
            'total_profit': self.total_profit
        }
