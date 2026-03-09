"""
Backtesting Script
Run backtest on historical data
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.config.config import config
from src.backtesting.backtester import Backtester
from src.utils.logger import logger


def generate_sample_data(days: int = 30) -> pd.DataFrame:
    """
    Generate sample OHLCV data for backtesting
    In production, replace with actual historical data
    """
    logger.info(f"Generating {days} days of sample data...")
    
    dates = pd.date_range(end=datetime.now(), periods=days*24*12, freq='5min')  # 5-minute bars
    
    # Generate realistic price movement
    initial_price = 100.0
    returns = np.random.normal(0, 0.02, len(dates))  # 2% volatility
    prices = initial_price * np.exp(np.cumsum(returns))
    
    data = []
    for i, timestamp in enumerate(dates):
        close = prices[i]
        high = close * (1 + abs(np.random.normal(0, 0.01)))
        low = close * (1 - abs(np.random.normal(0, 0.01)))
        open_price = prices[i-1] if i > 0 else close
        volume = np.random.uniform(1000, 10000)
        
        data.append({
            'timestamp': timestamp,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    df = pd.DataFrame(data)
    logger.info(f"✅ Generated {len(df)} bars of data")
    return df


def run_simple_strategy_backtest(df: pd.DataFrame) -> None:
    """
    Run backtest with a simple trading strategy
    """
    logger.info("Starting backtest...")
    
    backtester = Backtester(initial_capital=config.trading.initial_capital)
    df = backtester.load_data(df)
    
    # Strategy parameters
    trade_size = config.strategy.trade_size
    stop_loss_pct = config.risk_management.stop_loss_percent
    take_profit_pct = config.risk_management.take_profit_percent
    
    # Simple strategy: Enter trade every N bars
    trade_frequency = 50  # Trade every 50 bars
    
    i = 0
    while i < len(df) - trade_frequency:
        row = df.iloc[i]
        entry_price = row['close']
        
        # Alternate between long and short
        side = 'long' if len(backtester.trades) % 2 == 0 else 'short'
        
        # Calculate stop loss and take profit
        if side == 'long':
            stop_loss = entry_price * (1 - stop_loss_pct / 100)
            take_profit = entry_price * (1 + take_profit_pct / 100)
        else:
            stop_loss = entry_price * (1 + stop_loss_pct / 100)
            take_profit = entry_price * (1 - take_profit_pct / 100)
        
        # Simulate trade
        trade, exit_idx = backtester.simulate_trade(
            entry_time=row['timestamp'],
            entry_price=entry_price,
            size=trade_size,
            side=side,
            stop_loss=stop_loss,
            take_profit=take_profit,
            df=df,
            start_idx=i
        )
        
        backtester.trades.append(trade)
        backtester.capital += trade.pnl
        backtester.equity_curve.append(backtester.capital)
        backtester.timestamps.append(trade.timestamp)
        
        # Move to next entry point
        i = exit_idx + trade_frequency
    
    # Calculate and print results
    result = backtester.calculate_metrics()
    backtester.print_results(result)
    
    # Export trades
    backtester.export_trades_to_csv('backtest_trades.csv')
    
    return result


def main():
    """Main backtest execution"""
    logger.info("🧪 BACKTESTING SYSTEM")
    logger.info("="*60)
    
    # Generate or load data
    df = generate_sample_data(days=30)
    
    # Run backtest
    result = run_simple_strategy_backtest(df)
    
    # Analysis
    if result.total_return > 0:
        logger.info(f"✅ Strategy is profitable: {result.total_return:.2f}%")
    else:
        logger.info(f"❌ Strategy is unprofitable: {result.total_return:.2f}%")
    
    if result.sharpe_ratio > 1.0:
        logger.info(f"✅ Good risk-adjusted returns (Sharpe: {result.sharpe_ratio:.2f})")
    else:
        logger.info(f"⚠️ Poor risk-adjusted returns (Sharpe: {result.sharpe_ratio:.2f})")


if __name__ == "__main__":
    main()
