"""
Market Making Bot
Pure market making strategy implementation
"""
import sys
import signal
from src.utils.backpack_client import BackpackClient
from src.strategies.market_making_strategy import PureMarketMakingStrategy
from src.utils.logger import logger
from src.config.config import config


class MarketMakingBot:
    """Market Making Bot"""
    
    def __init__(self):
        self.client = BackpackClient()
        self.strategy = PureMarketMakingStrategy(
            self.client,
            config.trading.symbol
        )
    
    def start(self):
        """Start the bot"""
        try:
            logger.info("🚀 Starting Market Making Bot")
            
            # Print configuration
            self._print_config()
            
            # Check connection
            logger.info("Checking connection...")
            markets = self.client.get_markets()
            logger.info(f"✅ Connected to Backpack Exchange ({len(markets)} markets available)")
            
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
    
    def _print_config(self):
        """Print configuration"""
        print("\n" + "="*60)
        print("MARKET MAKING BOT CONFIGURATION")
        print("="*60)
        
        print("\n📊 Trading Config:")
        print(f"  Symbol: {config.trading.symbol}")
        print(f"  Initial Capital: ${config.trading.initial_capital:,.2f}")
        
        print("\n🎯 Strategy:")
        print(f"  Trade Size: {config.strategy.trade_size}")
        print(f"  Bid Spread: 0.1%")
        print(f"  Ask Spread: 0.1%")
        print(f"  Order Refresh: 30s")
        
        print("\n" + "="*60 + "\n")


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("\nReceived shutdown signal")
    sys.exit(0)


def main():
    """Main entry point"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot = MarketMakingBot()
    bot.start()


if __name__ == "__main__":
    main()
