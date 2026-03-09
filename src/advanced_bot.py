"""
Advanced Backpack Trading Bot
With Backtesting, Risk Management, and Auto-Optimization
"""
import time
import random
import signal
import sys
from datetime import datetime
from typing import Optional

from src.config.config import config
from src.utils.logger import logger
from src.utils.backpack_client import BackpackClient
from src.risk_management.risk_manager import RiskManager
from src.strategies.adaptive_strategy import AdaptiveStrategy


class AdvancedTradingBot:
    """
    Advanced trading bot with:
    - Risk management (stop loss, take profit, trailing stop)
    - Adaptive strategy (auto-adjusts parameters)
    - Performance tracking
    """
    
    def __init__(self):
        self.client = BackpackClient()
        self.risk_manager = RiskManager(config)
        
        # Initialize base strategy parameters
        base_params = {
            'trade_size': config.strategy.trade_size,
            'min_interval': config.strategy.min_interval,
            'max_interval': config.strategy.max_interval,
            'stop_loss': config.risk_management.stop_loss_percent,
            'take_profit': config.risk_management.take_profit_percent
        }
        
        self.adaptive_strategy = AdaptiveStrategy(config, base_params)
        self.is_running = False
        self.trade_count = 0
    
    def start(self):
        """Start the trading bot"""
        try:
            logger.info("🚀 Starting Advanced Backpack Trading Bot")
            config.print_config()
            
            # Check connection
            markets = self.client.get_markets()
            logger.info(f"✅ Connected to Backpack ({len(markets)} markets)")
            
            # Check balances
            self._check_balances()
            
            # Start trading loop
            self.is_running = True
            self._trading_loop()
            
        except KeyboardInterrupt:
            logger.info("Received stop signal")
            self.stop()
        except Exception as e:
            logger.error("Failed to start bot", {"error": str(e)})
            sys.exit(1)
    
    def stop(self):
        """Stop the trading bot"""
        logger.info("🛑 Stopping bot...")
        self.is_running = False
        
        # Close any open positions
        self._close_all_positions()
        
        # Print final statistics
        self._print_final_stats()
        
        logger.info("✅ Bot stopped successfully")
    
    def _check_balances(self):
        """Check account balances"""
        try:
            balances = self.client.get_balances()
            logger.info("💰 Account Balances:")
            for balance in balances:
                if float(balance.get('available', 0)) > 0:
                    logger.info(f"  {balance.get('symbol')}: {balance.get('available')}")
        except Exception as e:
            logger.error("Failed to check balances", {"error": str(e)})
    
    def _trading_loop(self):
        """Main trading loop with adaptive strategy"""
        logger.info("📊 Trading loop started")
        
        while self.is_running:
            try:
                # Check if daily loss limit reached
                if self.risk_manager.check_daily_loss_limit():
                    logger.warning("🛑 Daily loss limit reached - pausing until reset")
                    time.sleep(3600)  # Wait 1 hour
                    continue
                
                # Check if adaptive strategy suggests pause
                if self.adaptive_strategy.should_pause_trading():
                    logger.warning("⏸️ Adaptive strategy suggests pause - waiting")
                    time.sleep(3600)  # Wait 1 hour
                    continue
                
                # Evaluate performance periodically
                if self.adaptive_strategy.should_evaluate():
                    self._evaluate_and_adapt()
                
                # Execute trade with current parameters
                self._execute_trade()
                
                # Wait for next trade
                params = self.adaptive_strategy.get_current_params()
                wait_time = random.randint(
                    params['min_interval'],
                    params['max_interval']
                )
                logger.debug(f"Waiting {wait_time}s for next trade")
                time.sleep(wait_time)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                break
            except Exception as e:
                logger.error("Error in trading loop", {"error": str(e)})
                time.sleep(60)
        
        self.stop()
    
    def _execute_trade(self):
        """Execute a single trade with risk management"""
        try:
            symbol = config.trading.symbol
            
            # Get current price
            ticker = self.client.get_ticker(symbol)
            current_price = float(ticker.get('lastPrice', 0))
            
            if current_price == 0:
                logger.error("Invalid price received")
                return
            
            # Determine trade side (alternate)
            side = 'long' if self.trade_count % 2 == 0 else 'short'
            order_side = 'Bid' if side == 'long' else 'Ask'
            
            # Get current parameters
            params = self.adaptive_strategy.get_current_params()
            
            # Calculate position size with risk management
            position_size = self.risk_manager.calculate_position_size(
                current_price,
                self.risk_manager.total_capital
            )
            
            # Use parameter-adjusted size
            position_size = min(position_size, params['trade_size'])
            
            logger.info("🎯 Executing trade", {
                "side": side,
                "size": f"{position_size:.4f}",
                "price": f"${current_price:.2f}",
                "trade_count": self.trade_count
            })
            
            # Place order
            order = self.client.place_market_order(
                symbol=symbol,
                side=order_side,
                quantity=str(position_size)
            )
            
            # Open position with risk management
            position = self.risk_manager.open_position(
                symbol=symbol,
                entry_price=current_price,
                size=position_size,
                side=side
            )
            
            logger.info("✅ Trade executed", {
                "order_id": order.get('id'),
                "stop_loss": f"${position.stop_loss:.2f}",
                "take_profit": f"${position.take_profit:.2f}"
            })
            
            # Monitor position
            self._monitor_position(position)
            
            self.trade_count += 1
            
        except Exception as e:
            logger.error("Failed to execute trade", {"error": str(e)})
            raise
    
    def _monitor_position(self, position):
        """Monitor position for stop loss / take profit"""
        symbol = position.symbol
        check_interval = 5  # Check every 5 seconds
        max_hold_time = 300  # Max 5 minutes
        elapsed_time = 0
        
        while elapsed_time < max_hold_time:
            try:
                # Get current price
                ticker = self.client.get_ticker(symbol)
                current_price = float(ticker.get('lastPrice', 0))
                
                # Update trailing stop
                new_stop = self.risk_manager.update_trailing_stop(position, current_price)
                if new_stop:
                    logger.info(f"📈 Trailing stop updated: ${new_stop:.2f}")
                    position.stop_loss = new_stop
                
                # Check stop loss
                if self.risk_manager.check_stop_loss(position, current_price):
                    logger.warning("🛑 Stop loss hit!")
                    pnl = self._close_position(position, current_price, 'stop_loss')
                    return
                
                # Check take profit
                if self.risk_manager.check_take_profit(position, current_price):
                    logger.info("🎯 Take profit hit!")
                    pnl = self._close_position(position, current_price, 'take_profit')
                    return
                
                # Show current P&L
                pnl = self.risk_manager.calculate_pnl(position, current_price)
                pnl_percent = self.risk_manager.calculate_pnl_percent(position, current_price)
                
                if elapsed_time % 30 == 0:  # Log every 30 seconds
                    logger.debug(f"Position P&L: ${pnl:.2f} ({pnl_percent:.2f}%)")
                
                time.sleep(check_interval)
                elapsed_time += check_interval
                
            except Exception as e:
                logger.error("Error monitoring position", {"error": str(e)})
                break
        
        # Close at end of max hold time
        ticker = self.client.get_ticker(symbol)
        current_price = float(ticker.get('lastPrice', 0))
        self._close_position(position, current_price, 'time_limit')
    
    def _close_position(self, position, exit_price: float, reason: str) -> float:
        """Close position and record trade"""
        symbol = position.symbol
        
        # Calculate final P&L
        pnl = self.risk_manager.calculate_pnl(position, exit_price)
        pnl_percent = self.risk_manager.calculate_pnl_percent(position, exit_price)
        
        # Place closing order
        close_side = 'Ask' if position.side == 'long' else 'Bid'
        
        try:
            order = self.client.place_market_order(
                symbol=symbol,
                side=close_side,
                quantity=str(position.size)
            )
            
            logger.info(f"💼 Position closed ({reason})", {
                "pnl": f"${pnl:.2f}",
                "pnl_percent": f"{pnl_percent:.2f}%",
                "order_id": order.get('id')
            })
            
        except Exception as e:
            logger.error("Failed to close position", {"error": str(e)})
        
        # Record trade in adaptive strategy
        trade_record = {
            'timestamp': datetime.now(),
            'symbol': symbol,
            'side': position.side,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'size': position.size,
            'pnl': pnl,
            'pnl_percent': pnl_percent,
            'exit_reason': reason
        }
        
        self.adaptive_strategy.record_trade(trade_record)
        
        # Close in risk manager
        self.risk_manager.close_position(symbol, exit_price)
        
        return pnl
    
    def _close_all_positions(self):
        """Close all open positions"""
        for symbol, position in list(self.risk_manager.positions.items()):
            try:
                ticker = self.client.get_ticker(symbol)
                current_price = float(ticker.get('lastPrice', 0))
                self._close_position(position, current_price, 'shutdown')
            except Exception as e:
                logger.error(f"Failed to close position {symbol}", {"error": str(e)})
    
    def _evaluate_and_adapt(self):
        """Evaluate performance and adapt strategy"""
        logger.info("🔍 Evaluating performance...")
        
        metrics = self.adaptive_strategy.evaluate_performance()
        
        if metrics:
            logger.info("📊 Performance Metrics", {
                "win_rate": f"{metrics.win_rate:.1f}%",
                "sharpe_ratio": f"{metrics.sharpe_ratio:.2f}",
                "total_pnl": f"${metrics.total_pnl:.2f}",
                "trades": metrics.total_trades
            })
            
            # Adjust parameters based on performance
            adjustments = self.adaptive_strategy.adjust_parameters(metrics)
            
            if adjustments:
                logger.info("⚙️ Strategy adjusted based on performance")
    
    def _print_final_stats(self):
        """Print final statistics"""
        summary = self.adaptive_strategy.get_performance_summary()
        risk_metrics = self.risk_manager.get_risk_metrics()
        
        print("\n" + "="*60)
        print("FINAL STATISTICS")
        print("="*60)
        
        print("\n📊 Trading Summary:")
        print(f"  Total Trades: {self.trade_count}")
        print(f"  Evaluations: {summary['evaluations']}")
        print(f"  Parameter Adjustments: {summary['adjustments']}")
        
        if summary['evaluations'] > 0:
            print(f"  Final Win Rate: {summary.get('latest_win_rate', 0):.1f}%")
            print(f"  Final Sharpe Ratio: {summary.get('latest_sharpe', 0):.2f}")
            print(f"  Final P&L: ${summary.get('latest_pnl', 0):.2f}")
        
        print("\n💰 Risk Metrics:")
        print(f"  Daily P&L: ${risk_metrics['daily_pnl']:.2f} ({risk_metrics['daily_pnl_percent']:.2f}%)")
        print(f"  Total Capital: ${risk_metrics['total_capital']:,.2f}")
        
        print("\n" + "="*60 + "\n")


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("\nReceived shutdown signal")
    sys.exit(0)


def main():
    """Main entry point"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot = AdvancedTradingBot()
    bot.start()


if __name__ == "__main__":
    main()
