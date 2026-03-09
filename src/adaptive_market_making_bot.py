"""
Adaptive Market Making Bot
Market making with learning and automatic parameter adjustment
"""
import sys
import signal
from src.utils.backpack_client import BackpackClient
from src.strategies.adaptive_market_making import AdaptiveMarketMakingStrategy
from src.utils.logger import logger
from src.config.config import config


class AdaptiveMarketMakingBot:
    """Adaptive Market Making Bot"""
    
    def __init__(self):
        self.client = BackpackClient()
        self.strategy = AdaptiveMarketMakingStrategy(self.client, config.trading.symbol)
    
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
        print("🧠 ADAPTIVE MARKET MAKING BOT")
        print("="*60)
        
        print("\n📊 Trading Config:")
        print(f"  Symbol: {config.trading.symbol}")
        print(f"  Capital: ${config.trading.initial_capital:,.2f}")
        print(f"  Base Trade Size: {config.strategy.trade_size}")
        
        print("\n🎯 Base Strategy:")
        print(f"  Initial Spread: 0.1% / 0.1%")
        print(f"  Order Refresh: 30s")
        
        print("\n🧠 Adaptive Learning:")
        print(f"  ✅ Performance Tracking")
        print(f"  ✅ Win Rate Analysis")
        print(f"  ✅ Automatic Spread Adjustment")
        print(f"  ✅ Dynamic Position Sizing")
        print(f"  ✅ Spread Effectiveness Learning")
        print(f"  Evaluation: Every {config.adaptive.evaluation_period}h")
        
        print("\n🛡️ Safety Features:")
        print(f"  ✅ Volatility Detection (2%)")
        print(f"  ✅ Extreme Movement Guard (2%/min)")
        print(f"  ✅ Max Unrealized Loss ($100)")
        print(f"  ✅ Daily Loss Limit (${config.trading.initial_capital * 0.1:.2f})")
        print(f"  ✅ Auto-Hedge (3x imbalance)")
        
        print("\n" + "="*60 + "\n")


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("\nReceived shutdown signal")
    sys.exit(0)


def main():
    """Main entry point"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot = AdaptiveMarketMakingBot()
    bot.start()


if __name__ == "__main__":
    main()
