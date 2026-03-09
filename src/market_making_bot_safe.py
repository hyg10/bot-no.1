"""
Market Making Bot - Safe Edition
With all safety features enabled
"""
import sys
import signal
from src.utils.backpack_client import BackpackClient
from src.strategies.market_making_strategy_safe import PureMarketMakingStrategy
from src.utils.logger import logger
from src.config.config import config


class SafeMarketMakingBot:
    """Market Making Bot with Complete Safety Features"""
    
    def __init__(self):
        self.client = BackpackClient()
        self.strategy = PureMarketMakingStrategy(self.client, config.trading.symbol)
    
    def start(self):
        """Start the bot"""
        try:
            self._print_banner()
            
            # Check connection
            logger.info("Checking connection...")
            markets = self.client.get_markets()
            logger.info(f"✅ Connected to Backpack ({len(markets)} markets)")
            
            # Start strategy
            self.strategy.start()
            
        except KeyboardInterrupt:
            logger.info("Received stop signal")
            self.stop()
        except Exception as e:
            logger.error("Failed to start bot", {"error": str(e)})
            sys.exit(1)
    
    def stop(self):
        """Stop the bot"""
        logger.info("🛑 Stopping bot...")
        self.strategy.stop()
        logger.info("✅ Bot stopped successfully")
    
    def _print_banner(self):
        """Print startup banner"""
        print("\n" + "="*60)
        print("🛡️  SAFE MARKET MAKING BOT")
        print("="*60)
        
        print("\n📊 Trading Config:")
        print(f"  Symbol: {config.trading.symbol}")
        print(f"  Capital: ${config.trading.initial_capital:,.2f}")
        print(f"  Trade Size: {config.strategy.trade_size}")
        
        print("\n🎯 Strategy:")
        print(f"  Base Spread: 0.1% bid / 0.1% ask")
        print(f"  Order Refresh: 30s")
        print(f"  Dynamic Adjustment: ON")
        
        print("\n🛡️ Safety Features:")
        print(f"  ✅ Volatility Detection (2% threshold)")
        print(f"  ✅ Extreme Movement Guard (2% per minute)")
        print(f"  ✅ Max Unrealized Loss ($100)")
        print(f"  ✅ Daily Loss Limit (${config.trading.initial_capital * 0.1:.2f})")
        print(f"  ✅ Auto-Hedge (3x imbalance)")
        print(f"  ✅ Emergency Close")
        
        print("\n" + "="*60 + "\n")


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("\nReceived shutdown signal")
    sys.exit(0)


def main():
    """Main entry point"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot = SafeMarketMakingBot()
    bot.start()


if __name__ == "__main__":
    main()
