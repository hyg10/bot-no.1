"""
Pure Market Making Strategy
Inspired by Hummingbot's market making strategy
"""
import time
import random
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from src.utils.logger import logger
from src.config.config import config


class PureMarketMakingStrategy:
    """
    Pure Market Making Strategy
    
    Places buy and sell orders on both sides of the order book
    to capture the spread profit.
    
    How it works:
    1. Get mid price (between best bid and ask)
    2. Place buy order at: mid_price * (1 - bid_spread)
    3. Place sell order at: mid_price * (1 + ask_spread)
    4. When both filled, profit = spread
    5. Manage inventory to stay balanced
    """
    
    def __init__(self, client, symbol: str):
        self.client = client
        self.symbol = symbol
        
        # Strategy parameters
        self.bid_spread = 0.001  # 0.1% below mid price
        self.ask_spread = 0.001  # 0.1% above mid price
        self.order_amount = config.strategy.trade_size
        self.order_refresh_time = 30  # Refresh orders every 30 seconds
        self.max_inventory_ratio = 0.5  # Max 50% imbalance
        
        # State tracking
        self.active_orders = {
            'buy': None,
            'sell': None
        }
        self.filled_buys = []
        self.filled_sells = []
        self.inventory = 0.0  # Current inventory imbalance
        self.last_order_time = 0
        self.total_profit = 0.0
        
        self.is_running = False
        
        logger.info("Pure Market Making Strategy initialized", {
            "symbol": symbol,
            "bid_spread": f"{self.bid_spread * 100}%",
            "ask_spread": f"{self.ask_spread * 100}%",
            "order_amount": self.order_amount
        })
    
    def start(self):
        """Start market making"""
        self.is_running = True
        logger.info("🎯 Starting Pure Market Making Strategy")
        
        # Check initial balance
        self._check_balance()
        
        # Start main loop
        self._market_making_loop()
    
    def stop(self):
        """Stop market making"""
        logger.info("🛑 Stopping Market Making Strategy")
        self.is_running = False
        
        # Cancel all active orders
        self._cancel_all_orders()
        
        # Final statistics
        self._print_statistics()
    
    def _check_balance(self):
        """Check account balance"""
        try:
            balances = self.client.get_balances()
            logger.info("💰 Account Balances:")
            for balance in balances:
                if float(balance.get('available', 0)) > 0:
                    logger.info(f"  {balance.get('symbol')}: {balance.get('available')}")
        except Exception as e:
            logger.error("Failed to check balance", {"error": str(e)})
    
    def _market_making_loop(self):
        """Main market making loop"""
        logger.info("📊 Market making loop started")
        
        while self.is_running:
            try:
                # Get current mid price
                mid_price = self._get_mid_price()
                
                if mid_price == 0:
                    logger.warning("Invalid mid price, skipping cycle")
                    time.sleep(5)
                    continue
                
                # Check and refresh orders
                current_time = time.time()
                if current_time - self.last_order_time >= self.order_refresh_time:
                    self._refresh_orders(mid_price)
                    self.last_order_time = current_time
                
                # Check filled orders
                self._check_filled_orders()
                
                # Manage inventory
                self._manage_inventory()
                
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
        """Get mid price from order book"""
        try:
            depth = self.client.get_depth(self.symbol)
            
            if not depth or 'bids' not in depth or 'asks' not in depth:
                logger.error("Invalid order book data")
                return 0.0
            
            bids = depth['bids']
            asks = depth['asks']
            
            if not bids or not asks:
                logger.error("Empty order book")
                return 0.0
            
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            
            mid_price = (best_bid + best_ask) / 2
            
            logger.debug(f"Mid price: ${mid_price:.2f}", {
                "best_bid": best_bid,
                "best_ask": best_ask
            })
            
            return mid_price
            
        except Exception as e:
            logger.error("Failed to get mid price", {"error": str(e)})
            return 0.0

def _adjust_spreads_for_inventory(self) -> Tuple[float, float]:
        """
        Adjust spreads based on inventory imbalance
        
        If inventory is positive (more buys than sells):
        - Widen bid spread (discourage buying)
        - Narrow ask spread (encourage selling)
        
        If inventory is negative (more sells than buys):
        - Narrow bid spread (encourage buying)
        - Widen ask spread (discourage selling)
        """
        inventory_ratio = self.inventory / (self.order_amount * 10)  # Normalize
        inventory_ratio = max(-self.max_inventory_ratio, min(self.max_inventory_ratio, inventory_ratio))
        
        # Adjust spreads
        bid_adjustment = inventory_ratio * 0.0005  # Max 0.05% adjustment
        ask_adjustment = -inventory_ratio * 0.0005
        
        adjusted_bid_spread = self.bid_spread + bid_adjustment
        adjusted_ask_spread = self.ask_spread + ask_adjustment
        
        # Ensure positive spreads
        adjusted_bid_spread = max(0.0001, adjusted_bid_spread)
        adjusted_ask_spread = max(0.0001, adjusted_ask_spread)
        
        if abs(inventory_ratio) > 0.1:
            logger.info("Inventory imbalance detected", {
                "inventory": f"{self.inventory:.4f}",
                "ratio": f"{inventory_ratio:.2%}",
                "bid_spread": f"{adjusted_bid_spread * 100:.3f}%",
                "ask_spread": f"{adjusted_ask_spread * 100:.3f}%"
            })
        
        return adjusted_bid_spread, adjusted_ask_spread    


    def _refresh_orders(self, mid_price: float):
        """Refresh buy and sell orders"""
        # Cancel existing orders
        # self._cancel_all_orders()
        
        # Adjust spreads based on inventory
        adjusted_bid_spread, adjusted_ask_spread = self._adjust_spreads_for_inventory()
        
        # Calculate order prices
        buy_price = int(round(mid_price * (1 - adjusted_bid_spread)))
        sell_price = int(round(mid_price * (1 + adjusted_ask_spread)))
        
        logger.info("📝 Placing new orders", {
            "mid_price": f"${mid_price:.2f}",
            "buy_price": f"${buy_price:.2f}",
            "sell_price": f"${sell_price:.2f}",
            "spread": f"{(adjusted_bid_spread + adjusted_ask_spread) * 100:.2f}%"
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
    logger.info("Buy order placed", {
        "order_id": buy_order.get('id'),
        "price": f"${buy_price}",
        "quantity": self.order_amount
    })
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
    logger.info("Sell order placed", {
        "order_id": sell_order.get('id'),
        "price": f"${sell_price}",
        "quantity": self.order_amount
    })
except Exception as e:
    logger.error("Failed to place sell order", {"error": str(e)})
    
    def _adjust_spreads_for_inventory(self) -> Tuple[float, float]:
        """
        Adjust spreads based on inventory imbalance
        
        If inventory is positive (more buys than sells):
        - Widen bid spread (discourage buying)
        - Narrow ask spread (encourage selling)
        
        If inventory is negative (more sells than buys):
        - Narrow bid spread (encourage buying)
        - Widen ask spread (discourage selling)
        """
        inventory_ratio = self.inventory / (self.order_amount * 10)  # Normalize
        inventory_ratio = max(-self.max_inventory_ratio, min(self.max_inventory_ratio, inventory_ratio))
        
        # Adjust spreads
        bid_adjustment = inventory_ratio * 0.0005  # Max 0.05% adjustment
        ask_adjustment = -inventory_ratio * 0.0005
        
        adjusted_bid_spread = self.bid_spread + bid_adjustment
        adjusted_ask_spread = self.ask_spread + ask_adjustment
        
        # Ensure positive spreads
        adjusted_bid_spread = max(0.0001, adjusted_bid_spread)
        adjusted_ask_spread = max(0.0001, adjusted_ask_spread)
        
        if abs(inventory_ratio) > 0.1:
            logger.info("⚖️ Inventory imbalance detected", {
                "inventory": f"{self.inventory:.4f}",
                "ratio": f"{inventory_ratio:.2%}",
                "bid_spread": f"{adjusted_bid_spread * 100:.3f}%",
                "ask_spread": f"{adjusted_ask_spread * 100:.3f}%"
            })
        
        return adjusted_bid_spread, adjusted_ask_spread
    
    def _check_filled_orders(self):
        """Check if any orders were filled"""
        try:
            # Get recent order history
            order_history = self.client.get_order_history(self.symbol)
            
            # Check buy order
            if self.active_orders['buy']:
                buy_order_id = self.active_orders['buy'].get('id')
                for order in order_history:
                    if order.get('id') == buy_order_id and order.get('status') == 'Filled':
                        filled_price = float(order.get('price', 0))
                        filled_qty = float(order.get('quantity', 0))
                        
                        self.filled_buys.append({
                            'price': filled_price,
                            'quantity': filled_qty,
                            'timestamp': datetime.now()
                        })
                        
                        self.inventory += filled_qty
                        
                        logger.info("✅ Buy order filled!", {
                            "price": f"${filled_price:.2f}",
                            "quantity": filled_qty,
                            "inventory": f"{self.inventory:.4f}"
                        })
                        
                        self.active_orders['buy'] = None
                        break
            
            # Check sell order
            if self.active_orders['sell']:
                sell_order_id = self.active_orders['sell'].get('id')
                for order in order_history:
                    if order.get('id') == sell_order_id and order.get('status') == 'Filled':
                        filled_price = float(order.get('price', 0))
                        filled_qty = float(order.get('quantity', 0))
                        
                        self.filled_sells.append({
                            'price': filled_price,
                            'quantity': filled_qty,
                            'timestamp': datetime.now()
                        })
                        
                        self.inventory -= filled_qty
                        
                        logger.info("✅ Sell order filled!", {
                            "price": f"${filled_price:.2f}",
                            "quantity": filled_qty,
                            "inventory": f"{self.inventory:.4f}"
                        })
                        
                        self.active_orders['sell'] = None
                        break
            
            # Calculate profit from matched pairs
            self._calculate_profit()
            
        except Exception as e:
            logger.error("Failed to check filled orders", {"error": str(e)})
    
    def _calculate_profit(self):
        """Calculate profit from matched buy/sell pairs"""
        if not self.filled_buys or not self.filled_sells:
            return
        
        # Match oldest buy with oldest sell
        while self.filled_buys and self.filled_sells:
            buy = self.filled_buys[0]
            sell = self.filled_sells[0]
            
            # Calculate profit
            quantity = min(buy['quantity'], sell['quantity'])
            profit = (sell['price'] - buy['price']) * quantity
            
            self.total_profit += profit
            
            logger.info("💰 Profit realized!", {
                "buy_price": f"${buy['price']:.2f}",
                "sell_price": f"${sell['price']:.2f}",
                "quantity": quantity,
                "profit": f"${profit:.2f}",
                "total_profit": f"${self.total_profit:.2f}"
            })
            
            # Update quantities
            buy['quantity'] -= quantity
            sell['quantity'] -= quantity
            
            # Remove if fully matched
            if buy['quantity'] <= 0:
                self.filled_buys.pop(0)
            if sell['quantity'] <= 0:
                self.filled_sells.pop(0)
    
    def _manage_inventory(self):
        """Manage inventory to prevent excessive imbalance"""
        max_inventory = self.order_amount * 5  # Max 5x order amount
        
        if abs(self.inventory) > max_inventory:
            logger.warning("⚠️ Inventory limit reached, pausing strategy", {
                "inventory": f"{self.inventory:.4f}",
                "limit": max_inventory
            })
            
            # Cancel orders and wait
            self._cancel_all_orders()
            time.sleep(60)  # Wait 1 minute
    
    def _cancel_all_orders(self):
        """Cancel all active orders"""
        try:
            logger.info("Skipping order cancellation (not supported)")
            self.active_orders['buy'] = None
            self.active_orders['sell'] = None

        except Exception as e:
            logger.error("Failed to cancel orders", {"error": str(e)})
    
    def _print_statistics(self):
        """Print final statistics"""
        print("\n" + "="*60)
        print("MARKET MAKING STATISTICS")
        print("="*60)
        
        print("\n📊 Trading Summary:")
        print(f"  Total Buys: {len(self.filled_buys)}")
        print(f"  Total Sells: {len(self.filled_sells)}")
        print(f"  Total Profit: ${self.total_profit:.2f}")
        
        print("\n⚖️ Inventory:")
        print(f"  Current Inventory: {self.inventory:.4f} {self.symbol.split('_')[0]}")
        
        if len(self.filled_buys) > 0 and len(self.filled_sells) > 0:
            avg_buy = sum(b['price'] for b in self.filled_buys) / len(self.filled_buys)
            avg_sell = sum(s['price'] for s in self.filled_sells) / len(self.filled_sells)
            avg_spread = ((avg_sell - avg_buy) / avg_buy) * 100
            
            print("\n💹 Performance:")
            print(f"  Average Buy Price: ${avg_buy:.2f}")
            print(f"  Average Sell Price: ${avg_sell:.2f}")
            print(f"  Average Spread: {avg_spread:.2f}%")
        
        print("\n" + "="*60 + "\n")
    
    def get_status(self) -> Dict:
        """Get current strategy status"""
        return {
            'is_running': self.is_running,
            'active_orders': {
                'buy': self.active_orders['buy'] is not None,
                'sell': self.active_orders['sell'] is not None
            },
            'filled_buys': len(self.filled_buys),
            'filled_sells': len(self.filled_sells),
            'inventory': self.inventory,
            'total_profit': self.total_profit
        }
