"""
Pure Market Making Strategy - Fixed Version
"""
import time
from typing import Dict, Tuple
from datetime import datetime
from src.utils.logger import logger
from src.config.config import config


class PureMarketMakingStrategy:
    """Pure Market Making Strategy"""
    
    def __init__(self, client, symbol: str):
        self.client = client
        self.symbol = symbol
        self.bid_spread = 0.001
        self.ask_spread = 0.001
        self.order_amount = config.strategy.trade_size
        self.order_refresh_time = 30
        self.max_inventory_ratio = 0.5
        self.active_orders = {'buy': None, 'sell': None}
        self.inventory = 0.0
        self.last_order_time = 0
        self.total_profit = 0.0
        self.is_running = False
        
        logger.info("Pure Market Making Strategy initialized")
    
    def start(self):
        """Start market making"""
        self.is_running = True
        logger.info("Starting Pure Market Making Strategy")
        self._market_making_loop()
    
    def stop(self):
        """Stop market making"""
        logger.info("Stopping Market Making Strategy")
        self.is_running = False
    
    def _market_making_loop(self):
        """Main market making loop"""
        logger.info("Market making loop started")
        
        while self.is_running:
            try:
                mid_price = self._get_mid_price()
                
                if mid_price == 0:
                    time.sleep(5)
                    continue
                
                current_time = time.time()
                if current_time - self.last_order_time >= self.order_refresh_time:
                    self._refresh_orders(mid_price)
                    self.last_order_time = current_time
                
                time.sleep(5)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error("Error in loop", {"error": str(e)})
                time.sleep(10)
        
        self.stop()
    
    def _get_mid_price(self):
        """Get mid price"""
        try:
            ticker = self.client.get_ticker(self.symbol)
            return float(ticker.get('lastPrice', 0))
        except Exception as e:
            logger.error("Failed to get price", {"error": str(e)})
            return 0.0
    
    def _adjust_spreads_for_inventory(self):
        """Adjust spreads"""
        if self.order_amount == 0:
            return self.bid_spread, self.ask_spread
        
        inventory_ratio = self.inventory / (self.order_amount * 10)
        inventory_ratio = max(-0.5, min(0.5, inventory_ratio))
        
        bid_adjustment = inventory_ratio * 0.0005
        ask_adjustment = -inventory_ratio * 0.0005
        
        adjusted_bid = max(0.0001, self.bid_spread + bid_adjustment)
        adjusted_ask = max(0.0001, self.ask_spread + ask_adjustment)
        
        return adjusted_bid, adjusted_ask
    
    def _refresh_orders(self, mid_price):
        """Refresh orders"""
        adjusted_bid, adjusted_ask = self._adjust_spreads_for_inventory()
        
        buy_price = int(round(mid_price * (1 - adjusted_bid)))
        sell_price = int(round(mid_price * (1 + adjusted_ask)))
        
        logger.info("Placing orders", {
            "buy": buy_price,
            "sell": sell_price
        })
        
        try:
            buy_order = self.client.place_limit_order(
                symbol=self.symbol,
                side='Bid',
                price=str(buy_price),
                quantity=str(self.order_amount)
            )
            logger.info("Buy order placed")
        except Exception as e:
            logger.error("Buy order failed", {"error": str(e)})
        
        try:
            sell_order = self.client.place_limit_order(
                symbol=self.symbol,
                side='Ask',
                price=str(sell_price),
                quantity=str(self.order_amount)
            )
            logger.info("Sell order placed")
        except Exception as e:
            logger.error("Sell order failed", {"error": str(e)})