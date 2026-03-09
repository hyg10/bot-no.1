"""
Adaptive Strategy System
Automatically adjusts strategy parameters based on performance
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np


@dataclass
class PerformanceMetrics:
    """Performance metrics for evaluation period"""
    timestamp: datetime
    win_rate: float
    total_trades: int
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    avg_trade_pnl: float


class AdaptiveStrategy:
    """
    Adaptive strategy that adjusts parameters based on performance
    """
    
    def __init__(self, config, base_params: Dict):
        self.config = config
        self.base_params = base_params.copy()
        self.current_params = base_params.copy()
        
        self.performance_history: List[PerformanceMetrics] = []
        self.trades_history: List = []
        
        self.last_evaluation_time = datetime.now()
        self.adjustment_count = 0
    
    def record_trade(self, trade: Dict):
        """Record a trade for performance tracking"""
        self.trades_history.append({
            'timestamp': datetime.now(),
            'pnl': trade.get('pnl', 0),
            'pnl_percent': trade.get('pnl_percent', 0),
            'side': trade.get('side'),
            'size': trade.get('size')
        })
    
    def should_evaluate(self) -> bool:
        """Check if it's time to evaluate performance"""
        if not self.config.adaptive.enabled:
            return False
        
        elapsed = datetime.now() - self.last_evaluation_time
        evaluation_hours = self.config.adaptive.evaluation_period
        
        return elapsed >= timedelta(hours=evaluation_hours)
    
    def evaluate_performance(self) -> Optional[PerformanceMetrics]:
        """Evaluate recent performance"""
        if len(self.trades_history) < 10:  # Need minimum trades
            return None
        
        # Get trades from evaluation period
        cutoff_time = datetime.now() - timedelta(hours=self.config.adaptive.evaluation_period)
        recent_trades = [t for t in self.trades_history if t['timestamp'] >= cutoff_time]
        
        if not recent_trades:
            return None
        
        # Calculate metrics
        total_trades = len(recent_trades)
        winning_trades = len([t for t in recent_trades if t['pnl'] > 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = sum(t['pnl'] for t in recent_trades)
        avg_trade_pnl = total_pnl / total_trades if total_trades > 0 else 0
        
        # Calculate Sharpe ratio
        returns = [t['pnl_percent'] for t in recent_trades]
        sharpe_ratio = self._calculate_sharpe(returns)
        
        # Calculate max drawdown
        cumulative_pnl = np.cumsum([t['pnl'] for t in recent_trades])
        running_max = np.maximum.accumulate(cumulative_pnl)
        drawdown = running_max - cumulative_pnl
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0
        
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            win_rate=win_rate,
            total_trades=total_trades,
            total_pnl=total_pnl,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            avg_trade_pnl=avg_trade_pnl
        )
        
        self.performance_history.append(metrics)
        self.last_evaluation_time = datetime.now()
        
        return metrics
    
    def adjust_parameters(self, metrics: PerformanceMetrics) -> Dict[str, float]:
        """
        Adjust strategy parameters based on performance
        
        Adjustment rules:
        - Low win rate → Reduce position size, tighten stops
        - High win rate → Increase position size, wider targets
        - High drawdown → Reduce risk
        - Low Sharpe → More conservative
        """
        adjustments = {}
        adjustment_factor = self.config.adaptive.adjustment_factor
        
        # Rule 1: Win rate adjustment
        if metrics.win_rate < self.config.adaptive.min_win_rate:
            # Poor performance - reduce risk
            adjustments['trade_size'] = self.current_params['trade_size'] * (1 - adjustment_factor)
            adjustments['stop_loss'] = self.current_params.get('stop_loss', 2.0) * 0.8  # Tighter stop
            print(f"⚠️ Low win rate ({metrics.win_rate:.1f}%) - Reducing risk")
        
        elif metrics.win_rate > 60.0:
            # Good performance - increase position
            adjustments['trade_size'] = self.current_params['trade_size'] * (1 + adjustment_factor * 0.5)
            print(f"✅ High win rate ({metrics.win_rate:.1f}%) - Increasing position size")
        
        # Rule 2: Sharpe ratio adjustment
        if metrics.sharpe_ratio < 0.5:
            # Poor risk-adjusted returns
            adjustments['min_interval'] = int(self.current_params['min_interval'] * 1.5)  # Slower trading
            print(f"⚠️ Low Sharpe ratio ({metrics.sharpe_ratio:.2f}) - Slowing down")
        
        elif metrics.sharpe_ratio > 2.0:
            # Excellent risk-adjusted returns
            adjustments['min_interval'] = int(self.current_params['min_interval'] * 0.8)  # Faster trading
            print(f"✅ High Sharpe ratio ({metrics.sharpe_ratio:.2f}) - Increasing frequency")
        
        # Rule 3: Drawdown adjustment
        if metrics.max_drawdown > self.config.trading.initial_capital * 0.05:  # 5% drawdown
            # High drawdown - pause or reduce drastically
            adjustments['trade_size'] = self.current_params['trade_size'] * 0.5
            print(f"🛑 High drawdown (${metrics.max_drawdown:.2f}) - Halving position size")
        
        # Rule 4: Consecutive losses
        recent_10_trades = self.trades_history[-10:]
        consecutive_losses = 0
        for trade in reversed(recent_10_trades):
            if trade['pnl'] < 0:
                consecutive_losses += 1
            else:
                break
        
        if consecutive_losses >= 3:
            adjustments['pause_trading'] = True
            print(f"⏸️ {consecutive_losses} consecutive losses - Pausing trading")
        
        # Apply adjustments
        if adjustments:
            self._apply_adjustments(adjustments)
            self.adjustment_count += 1
        
        return adjustments
    
    def _apply_adjustments(self, adjustments: Dict):
        """Apply parameter adjustments"""
        for param, value in adjustments.items():
            if param == 'pause_trading':
                continue
            
            # Apply bounds
            if param == 'trade_size':
                # Min: 10% of base, Max: 200% of base
                min_size = self.base_params['trade_size'] * 0.1
                max_size = self.base_params['trade_size'] * 2.0
                value = np.clip(value, min_size, max_size)
            
            elif param == 'min_interval':
                # Min: 10s, Max: 300s
                value = int(np.clip(value, 10, 300))
            
            elif param == 'stop_loss':
                # Min: 0.5%, Max: 10%
                value = np.clip(value, 0.5, 10.0)
            
            self.current_params[param] = value
            print(f"  Adjusted {param}: {self.base_params.get(param, 'N/A')} → {value}")
    
    def _calculate_sharpe(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate
        
        if np.std(excess_returns) == 0:
            return 0.0
        
        return np.mean(excess_returns) / np.std(excess_returns)
    
    def reset_to_base(self):
        """Reset parameters to base values"""
        self.current_params = self.base_params.copy()
        print("🔄 Parameters reset to base values")
    
    def get_current_params(self) -> Dict:
        """Get current parameter values"""
        return self.current_params.copy()
    
    def should_pause_trading(self) -> bool:
        """Check if trading should be paused"""
        # Check recent consecutive losses
        if len(self.trades_history) < 5:
            return False
        
        recent_trades = self.trades_history[-5:]
        consecutive_losses = sum(1 for t in recent_trades if t['pnl'] < 0)
        
        return consecutive_losses >= 4  # Pause after 4 out of 5 losses
    
    def get_performance_summary(self) -> Dict:
        """Get performance summary"""
        if not self.performance_history:
            return {
                'evaluations': 0,
                'adjustments': 0,
                'current_params': self.current_params
            }
        
        latest = self.performance_history[-1]
        
        return {
            'evaluations': len(self.performance_history),
            'adjustments': self.adjustment_count,
            'latest_win_rate': latest.win_rate,
            'latest_sharpe': latest.sharpe_ratio,
            'latest_pnl': latest.total_pnl,
            'current_params': self.current_params,
            'base_params': self.base_params
        }
