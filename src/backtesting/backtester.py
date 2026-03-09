"""
Backtesting Engine
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict


@dataclass
class Trade:
    """Trade record"""
    timestamp: datetime
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_percent: float
    duration: timedelta
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exit_reason: str = 'manual'  # 'stop_loss', 'take_profit', 'trailing_stop', 'manual'


@dataclass
class BacktestResult:
    """Backtest result metrics"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    total_pnl: float
    total_return: float
    
    avg_win: float
    avg_loss: float
    avg_trade: float
    
    max_win: float
    max_loss: float
    
    profit_factor: float
    
    max_drawdown: float
    max_drawdown_percent: float
    
    sharpe_ratio: float
    sortino_ratio: float
    
    avg_trade_duration: timedelta
    
    initial_capital: float
    final_capital: float
    
    trades: List[Trade]


class Backtester:
    """
    Backtesting engine for trading strategies
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = [initial_capital]
        self.timestamps: List[datetime] = []
    
    def load_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Load and prepare historical data
        
        Expected columns: timestamp, open, high, low, close, volume
        """
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df
    
    def simulate_trade(
        self,
        entry_time: datetime,
        entry_price: float,
        size: float,
        side: str,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        df: pd.DataFrame,
        start_idx: int
    ) -> Tuple[Trade, int]:
        """
        Simulate a single trade through historical data
        
        Returns: (Trade object, exit index)
        """
        exit_idx = start_idx
        exit_price = None
        exit_reason = 'manual'
        highest_price = entry_price
        lowest_price = entry_price
        
        # Simulate price movement
        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            current_high = row['high']
            current_low = row['low']
            current_close = row['close']
            
            # Update highest/lowest for trailing stop
            if current_high > highest_price:
                highest_price = current_high
            if current_low < lowest_price:
                lowest_price = current_low
            
            # Check stop loss
            if stop_loss is not None:
                if side == 'long' and current_low <= stop_loss:
                    exit_price = stop_loss
                    exit_reason = 'stop_loss'
                    exit_idx = i
                    break
                elif side == 'short' and current_high >= stop_loss:
                    exit_price = stop_loss
                    exit_reason = 'stop_loss'
                    exit_idx = i
                    break
            
            # Check take profit
            if take_profit is not None:
                if side == 'long' and current_high >= take_profit:
                    exit_price = take_profit
                    exit_reason = 'take_profit'
                    exit_idx = i
                    break
                elif side == 'short' and current_low <= take_profit:
                    exit_price = take_profit
                    exit_reason = 'take_profit'
                    exit_idx = i
                    break
        
        # If no exit condition met, exit at last close
        if exit_price is None:
            exit_price = df.iloc[-1]['close']
            exit_idx = len(df) - 1
            exit_reason = 'manual'
        
        # Calculate P&L
        if side == 'long':
            pnl = (exit_price - entry_price) * size
        else:
            pnl = (entry_price - exit_price) * size
        
        pnl_percent = (pnl / (entry_price * size)) * 100
        
        exit_time = df.iloc[exit_idx]['timestamp']
        duration = exit_time - entry_time
        
        trade = Trade(
            timestamp=entry_time,
            symbol='BACKTEST',
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=pnl,
            pnl_percent=pnl_percent,
            duration=duration,
            stop_loss=stop_loss,
            take_profit=take_profit,
            exit_reason=exit_reason
        )
        
        return trade, exit_idx
    
    def calculate_metrics(self) -> BacktestResult:
        """Calculate comprehensive backtest metrics"""
        if not self.trades:
            raise ValueError("No trades to analyze")
        
        # Basic stats
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t.pnl > 0])
        losing_trades = len([t for t in self.trades if t.pnl < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # P&L stats
        total_pnl = sum(t.pnl for t in self.trades)
        total_return = (total_pnl / self.initial_capital) * 100
        
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        losses = [t.pnl for t in self.trades if t.pnl < 0]
        
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        avg_trade = np.mean([t.pnl for t in self.trades])
        
        max_win = max(wins) if wins else 0
        max_loss = min(losses) if losses else 0
        
        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Drawdown
        equity_curve = np.array(self.equity_curve)
        running_max = np.maximum.accumulate(equity_curve)
        drawdown = running_max - equity_curve
        max_drawdown = np.max(drawdown)
        max_drawdown_percent = (max_drawdown / self.initial_capital) * 100 if self.initial_capital > 0 else 0
        
        # Sharpe ratio
        returns = [t.pnl_percent for t in self.trades]
        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        
        # Sortino ratio
        sortino_ratio = self._calculate_sortino_ratio(returns)
        
        # Average trade duration
        avg_duration = np.mean([t.duration.total_seconds() for t in self.trades])
        avg_trade_duration = timedelta(seconds=avg_duration)
        
        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_return=total_return,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade=avg_trade,
            max_win=max_win,
            max_loss=max_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            max_drawdown_percent=max_drawdown_percent,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            avg_trade_duration=avg_trade_duration,
            initial_capital=self.initial_capital,
            final_capital=self.capital,
            trades=self.trades
        )
    
    def _calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio"""
        if not returns:
            return 0.0
        
        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate
        
        if len(excess_returns) < 2:
            return 0.0
        
        return (np.mean(excess_returns) / np.std(excess_returns)) if np.std(excess_returns) > 0 else 0.0
    
    def _calculate_sortino_ratio(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sortino ratio (uses downside deviation)"""
        if not returns:
            return 0.0
        
        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate
        
        # Calculate downside deviation
        negative_returns = excess_returns[excess_returns < 0]
        if len(negative_returns) < 2:
            return 0.0
        
        downside_deviation = np.std(negative_returns)
        
        if downside_deviation == 0:
            return 0.0
        
        return np.mean(excess_returns) / downside_deviation
    
    def print_results(self, result: BacktestResult):
        """Print backtest results"""
        print("\n" + "="*60)
        print("BACKTEST RESULTS")
        print("="*60)
        
        print("\n📊 Trading Statistics:")
        print(f"  Total Trades: {result.total_trades}")
        print(f"  Winning Trades: {result.winning_trades}")
        print(f"  Losing Trades: {result.losing_trades}")
        print(f"  Win Rate: {result.win_rate:.2f}%")
        
        print("\n💰 Performance:")
        print(f"  Total P&L: ${result.total_pnl:,.2f}")
        print(f"  Total Return: {result.total_return:.2f}%")
        print(f"  Initial Capital: ${result.initial_capital:,.2f}")
        print(f"  Final Capital: ${result.final_capital:,.2f}")
        
        print("\n📈 Trade Analysis:")
        print(f"  Average Win: ${result.avg_win:,.2f}")
        print(f"  Average Loss: ${result.avg_loss:,.2f}")
        print(f"  Average Trade: ${result.avg_trade:,.2f}")
        print(f"  Max Win: ${result.max_win:,.2f}")
        print(f"  Max Loss: ${result.max_loss:,.2f}")
        print(f"  Profit Factor: {result.profit_factor:.2f}")
        
        print("\n⚠️ Risk Metrics:")
        print(f"  Max Drawdown: ${result.max_drawdown:,.2f} ({result.max_drawdown_percent:.2f}%)")
        print(f"  Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"  Sortino Ratio: {result.sortino_ratio:.2f}")
        
        print("\n⏱️ Time Analysis:")
        print(f"  Average Trade Duration: {result.avg_trade_duration}")
        
        print("\n" + "="*60 + "\n")
    
    def export_trades_to_csv(self, filename: str):
        """Export trades to CSV"""
        trades_dict = [asdict(trade) for trade in self.trades]
        df = pd.DataFrame(trades_dict)
        df.to_csv(filename, index=False)
        print(f"✅ Trades exported to {filename}")
