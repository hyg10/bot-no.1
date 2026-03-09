"""
Market Making Bot V2
"""
import sys
import signal
from src.utils.backpack_client import BackpackClient
from src.strategies.market_making_strategy_v2 import PureMarketMakingStrategy
from src.utils.logger import logger
from src.config.config import config


class MarketMakingBotV2:
    def __init__(self):
        self.client = BackpackClient()
        self.strategy = PureMarketMakingStrategy(self.client, config.trading.symbol)
    
    def start(self):
        logger.info("Starting Market Making Bot V2")
        markets = self.client.get_markets()
        logger.info(f"Connected ({len(markets)} markets)")
        self.strategy.start()


def main():
    bot = MarketMakingBotV2()
    bot.start()


if __name__ == "__main__":
    main()