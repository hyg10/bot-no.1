"""
Optimization Script
Find optimal strategy parameters using Genetic Algorithm
"""
import pandas as pd
import numpy as np
from datetime import datetime

from src.config.config import config
from src.backtesting.backtester import Backtester
from src.optimization.genetic_optimizer import (
    GeneticOptimizer,
    ParameterRange,
    GridSearchOptimizer
)
from src.utils.logger import logger


def generate_sample_data(days: int = 30) -> pd.DataFrame:
    """Generate sample data"""
    dates = pd.date_range(end=datetime.now(), periods=days*24*12, freq='5min')
    
    initial_price = 100.0
    returns = np.random.normal(0, 0.02, len(dates))
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
    
    return pd.DataFrame(data)


# Global data for optimization
BACKTEST_DATA = None


def fitness_function(params: dict) -> float:
    """
    Fitness function for optimization
    Returns a score based on backtest performance
    """
    global BACKTEST_DATA
    
    try:
        # Run backtest with these parameters
        backtester = Backtester(initial_capital=config.trading.initial_capital)
        df = backtester.load_data(BACKTEST_DATA)
        
        trade_size = params['trade_size']
        stop_loss_pct = params['stop_loss_percent']
        take_profit_pct = params['take_profit_percent']
        trade_frequency = int(params['trade_frequency'])
        
        # Execute strategy
        i = 0
        while i < len(df) - trade_frequency:
            row = df.iloc[i]
            entry_price = row['close']
            
            side = 'long' if len(backtester.trades) % 2 == 0 else 'short'
            
            if side == 'long':
                stop_loss = entry_price * (1 - stop_loss_pct / 100)
                take_profit = entry_price * (1 + take_profit_pct / 100)
            else:
                stop_loss = entry_price * (1 + stop_loss_pct / 100)
                take_profit = entry_price * (1 - take_profit_pct / 100)
            
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
            
            i = exit_idx + trade_frequency
        
        # Calculate metrics
        if len(backtester.trades) < 10:
            return -1000.0  # Penalty for too few trades
        
        result = backtester.calculate_metrics()
        
        # Fitness score: weighted combination of metrics
        # Prioritize: Return, Sharpe, Win Rate, minimize Drawdown
        fitness = (
            result.total_return * 0.4 +  # 40% weight on returns
            result.sharpe_ratio * 20 +    # Sharpe ratio scaled
            result.win_rate * 0.3 -       # 30% weight on win rate
            result.max_drawdown_percent * 0.5  # Penalty for drawdown
        )
        
        return fitness
        
    except Exception as e:
        logger.error(f"Error in fitness function: {e}")
        return -1000.0  # Penalty for errors


def run_genetic_optimization():
    """Run genetic algorithm optimization"""
    global BACKTEST_DATA
    
    logger.info("🧬 GENETIC ALGORITHM OPTIMIZATION")
    logger.info("="*60)
    
    # Generate data
    logger.info("Generating data for optimization...")
    BACKTEST_DATA = generate_sample_data(days=30)
    
    # Define parameter ranges to optimize
    parameter_ranges = [
        ParameterRange(
            name='trade_size',
            min_value=0.01,
            max_value=0.5,
            step=0.01
        ),
        ParameterRange(
            name='stop_loss_percent',
            min_value=0.5,
            max_value=5.0,
            step=0.5
        ),
        ParameterRange(
            name='take_profit_percent',
            min_value=1.0,
            max_value=10.0,
            step=0.5
        ),
        ParameterRange(
            name='trade_frequency',
            min_value=20,
            max_value=100,
            step=10,
            is_integer=True
        )
    ]
    
    # Initialize optimizer
    optimizer = GeneticOptimizer(
        parameter_ranges=parameter_ranges,
        fitness_function=fitness_function,
        population_size=config.optimization.population_size,
        generations=config.optimization.generations,
        crossover_prob=0.7,
        mutation_prob=config.optimization.mutation_rate
    )
    
    # Run optimization
    result = optimizer.optimize(verbose=True)
    
    # Test best parameters
    logger.info("\n" + "="*60)
    logger.info("TESTING BEST PARAMETERS")
    logger.info("="*60)
    
    best_fitness = fitness_function(result.best_params)
    logger.info(f"\nBest Fitness Score: {best_fitness:.2f}")
    
    # Run final backtest with best parameters
    logger.info("\nRunning full backtest with optimized parameters...")
    
    return result


def run_grid_search():
    """Run grid search optimization (exhaustive)"""
    global BACKTEST_DATA
    
    logger.info("🔍 GRID SEARCH OPTIMIZATION")
    logger.info("="*60)
    logger.info("⚠️ Warning: Grid search can be slow for many parameters")
    
    # Generate data
    BACKTEST_DATA = generate_sample_data(days=15)  # Less data for speed
    
    # Define smaller parameter ranges for grid search
    parameter_ranges = [
        ParameterRange(
            name='trade_size',
            min_value=0.05,
            max_value=0.2,
            step=0.05
        ),
        ParameterRange(
            name='stop_loss_percent',
            min_value=1.0,
            max_value=3.0,
            step=1.0
        ),
        ParameterRange(
            name='take_profit_percent',
            min_value=3.0,
            max_value=7.0,
            step=2.0
        ),
        ParameterRange(
            name='trade_frequency',
            min_value=30,
            max_value=60,
            step=30,
            is_integer=True
        )
    ]
    
    optimizer = GridSearchOptimizer(
        parameter_ranges=parameter_ranges,
        fitness_function=fitness_function
    )
    
    result = optimizer.optimize(verbose=True)
    
    return result


def main():
    """Main optimization execution"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'grid':
        result = run_grid_search()
    else:
        result = run_genetic_optimization()
    
    # Save results
    logger.info("\n✅ Optimization complete!")
    logger.info("\nRecommended parameters for .env file:")
    print("\n# Optimized Strategy Parameters")
    for param_name, param_value in result.best_params.items():
        if param_name == 'trade_size':
            print(f"STRATEGY_TRADE_SIZE={param_value:.4f}")
        elif param_name == 'stop_loss_percent':
            print(f"STOP_LOSS_PERCENT={param_value:.2f}")
        elif param_name == 'take_profit_percent':
            print(f"TAKE_PROFIT_PERCENT={param_value:.2f}")
        elif param_name == 'trade_frequency':
            print(f"# Trade frequency: {param_value} bars")


if __name__ == "__main__":
    main()
