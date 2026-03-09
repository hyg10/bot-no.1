"""
Trend-Aware Market Making Bot
Intelligent market making that respects market direction
"""
import sys
import signal
from src.utils.backpack_client import BackpackClient
from src.strategies.trend_aware_market_making import TrendAwareMarketMakingStrategy
from src.utils.logger import logger
from src.config.config import config


class TrendAwareMarketMakingBot:
    """Trend-Aware Market Making Bot"""
    
    def __init__(self):
        self.client = BackpackClient()
        self.strategy = TrendAwareMarketMakingStrategy(self.client, config.trading.symbol)
    
    def start(self):
        """Start the bot"""
        try:
            self._print_banner()
            
            logger.info("Checking connection...")
            markets = self.client.get_markets()
            logger.info(f"✅ Connected to Backpack ({len(markets)} markets)")
            
            self.strategy.start()
            
        except KeyboardInterrupt:
            logger.info("Stop signal received")
            self.stop()
        except Exception as e:
            logger.error("Failed to start", {"error": str(e)})
            sys.exit(1)
    
    def stop(self):
        """Stop the bot"""
        logger.info("🛑 Stopping...")
        self.strategy.stop()
        logger.info("✅ Stopped")
    
    def _print_banner(self):
        """Print banner"""
        print("\n" + "="*60)
        print("📈 TREND-AWARE MARKET MAKING BOT")
        print("="*60)
        
        print("\n📊 Configuration:")
        print(f"  Symbol: {config.trading.symbol}")
        print(f"  Capital: ${config.trading.initial_capital:,.2f}")
        print(f"  Trade Size: {config.strategy.trade_size}")
        
        print("\n🎯 Trend Detection:")
        print("  ✅ Real-time trend analysis")
        print("  ✅ Uptrend: Buy orders only")
        print("  ✅ Downtrend: Sell orders only")
        print("  ✅ Sideways: Both orders")
        print("  ✅ Extreme trends: Pause all")
        
        print("\n🧠 Smart Features:")
        print("  ✅ Avoids buying in downtrends")
        print("  ✅ Avoids selling in uptrends")
        print("  ✅ Adaptive spread adjustment")
        print("  ✅ Automatic inventory hedge")
        
        print("\n🛡️ Safety:")
        print("  ✅ Max unrealized loss: $50")
        print(f"  ✅ Daily loss limit: ${config.trading.initial_capital * 0.1:.2f}")
        print("  ✅ Volatility detection")
        print("  ✅ Emergency close")
        
        print("\n" + "="*60 + "\n")


def signal_handler(sig, frame):
    """Handle signals"""
    logger.info("\nShutdown signal")
    sys.exit(0)


def main():
    """Main"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot = TrendAwareMarketMakingBot()
    bot.start()


if __name__ == "__main__":
    main()
