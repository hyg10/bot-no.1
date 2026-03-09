"""
Configuration management for Advanced Backpack Bot
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BackpackConfig:
    """Backpack API configuration"""
    api_key: str
    secret_key: str
    environment: str


@dataclass
class TradingConfig:
    """Trading configuration"""
    symbol: str
    initial_capital: float


@dataclass
class StrategyConfig:
    """Strategy parameters"""
    trade_size: float
    min_interval: int
    max_interval: int


@dataclass
class RiskManagementConfig:
    """Risk management configuration"""
    stop_loss_percent: float
    take_profit_percent: float
    trailing_stop_percent: float
    max_position_size_percent: float
    max_daily_loss_percent: float


@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    start_date: str
    end_date: str
    data_path: str


@dataclass
class OptimizationConfig:
    """Optimization configuration"""
    enabled: bool
    interval: int
    population_size: int
    generations: int
    mutation_rate: float


@dataclass
class AdaptiveConfig:
    """Adaptive strategy configuration"""
    enabled: bool
    evaluation_period: int
    min_win_rate: float
    adjustment_factor: float


class Config:
    """Main configuration class"""
    
    def __init__(self):
        self.backpack = BackpackConfig(
            api_key=os.getenv('BACKPACK_API_KEY', ''),
            secret_key=os.getenv('BACKPACK_SECRET_KEY', ''),
            environment=os.getenv('BACKPACK_ENVIRONMENT', 'devnet')
        )
        
        self.trading = TradingConfig(
            symbol=os.getenv('TRADING_SYMBOL', 'SOL_USDC'),
            initial_capital=float(os.getenv('INITIAL_CAPITAL', '10000.0'))
        )
        
        self.strategy = StrategyConfig(
            trade_size=float(os.getenv('STRATEGY_TRADE_SIZE', '0.1')),
            min_interval=int(os.getenv('STRATEGY_MIN_INTERVAL', '30')),
            max_interval=int(os.getenv('STRATEGY_MAX_INTERVAL', '120'))
        )
        
        self.risk_management = RiskManagementConfig(
            stop_loss_percent=float(os.getenv('STOP_LOSS_PERCENT', '2.0')),
            take_profit_percent=float(os.getenv('TAKE_PROFIT_PERCENT', '5.0')),
            trailing_stop_percent=float(os.getenv('TRAILING_STOP_PERCENT', '1.5')),
            max_position_size_percent=float(os.getenv('MAX_POSITION_SIZE_PERCENT', '20.0')),
            max_daily_loss_percent=float(os.getenv('MAX_DAILY_LOSS_PERCENT', '10.0'))
        )
        
        self.backtest = BacktestConfig(
            start_date=os.getenv('BACKTEST_START_DATE', '2024-01-01'),
            end_date=os.getenv('BACKTEST_END_DATE', '2024-12-31'),
            data_path=os.getenv('BACKTEST_DATA_PATH', './data/historical')
        )
        
        self.optimization = OptimizationConfig(
            enabled=os.getenv('AUTO_OPTIMIZATION_ENABLED', 'false').lower() == 'true',
            interval=int(os.getenv('OPTIMIZATION_INTERVAL', '24')),
            population_size=int(os.getenv('GA_POPULATION_SIZE', '20')),
            generations=int(os.getenv('GA_GENERATIONS', '50')),
            mutation_rate=float(os.getenv('GA_MUTATION_RATE', '0.2'))
        )
        
        self.adaptive = AdaptiveConfig(
            enabled=os.getenv('ADAPTIVE_STRATEGY_ENABLED', 'false').lower() == 'true',
            evaluation_period=int(os.getenv('EVALUATION_PERIOD', '24')),
            min_win_rate=float(os.getenv('MIN_WIN_RATE', '40.0')),
            adjustment_factor=float(os.getenv('PERFORMANCE_ADJUSTMENT_FACTOR', '0.1'))
        )
        
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        
        self._validate()
    
    def _validate(self):
        """Validate configuration"""
        errors = []
        
        if not self.backpack.api_key:
            errors.append('BACKPACK_API_KEY is required')
        if not self.backpack.secret_key:
            errors.append('BACKPACK_SECRET_KEY is required')
        
        if self.trading.initial_capital <= 0:
            errors.append('INITIAL_CAPITAL must be greater than 0')
        
        if self.strategy.trade_size <= 0:
            errors.append('STRATEGY_TRADE_SIZE must be greater than 0')
        
        if self.risk_management.stop_loss_percent <= 0:
            errors.append('STOP_LOSS_PERCENT must be greater than 0')
        
        if errors:
            raise ValueError(f"Configuration validation failed:\n" + "\n".join(errors))
    
    def print_config(self):
        """Print configuration"""
        print("\n" + "="*60)
        print("ADVANCED BACKPACK BOT CONFIGURATION")
        print("="*60)

        print("\n[Trading Config]")
        print(f"  Symbol: {self.trading.symbol}")
        print(f"  Initial Capital: ${self.trading.initial_capital:,.2f}")

        print("\n[Strategy]")
        print(f"  Trade Size: {self.strategy.trade_size}")
        print(f"  Interval: {self.strategy.min_interval}s - {self.strategy.max_interval}s")

        print("\n[Risk Management]")
        print(f"  Stop Loss: {self.risk_management.stop_loss_percent}%")
        print(f"  Take Profit: {self.risk_management.take_profit_percent}%")
        print(f"  Trailing Stop: {self.risk_management.trailing_stop_percent}%")
        print(f"  Max Position Size: {self.risk_management.max_position_size_percent}%")
        print(f"  Max Daily Loss: {self.risk_management.max_daily_loss_percent}%")

        print("\n[Optimization]")
        print(f"  Enabled: {self.optimization.enabled}")
        if self.optimization.enabled:
            print(f"  Interval: {self.optimization.interval}h")
            print(f"  Population: {self.optimization.population_size}")
            print(f"  Generations: {self.optimization.generations}")

        print("\n[Adaptive Strategy]")
        print(f"  Enabled: {self.adaptive.enabled}")
        if self.adaptive.enabled:
            print(f"  Evaluation Period: {self.adaptive.evaluation_period}h")
            print(f"  Min Win Rate: {self.adaptive.min_win_rate}%")

        print("\n" + "="*60 + "\n")


# Global config instance
config = Config()
