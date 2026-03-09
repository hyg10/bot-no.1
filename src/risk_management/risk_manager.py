"""
Risk Management System
"""
from typing import Optional, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Position:
    """Trading position"""
    symbol: str
    entry_price: float
    size: float
    side: str  # 'long' or 'short'
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    highest_price: Optional[float] = None  # For trailing stop
    lowest_price: Optional[float] = None
    _atr: float = 0.0  # ATR at entry (for trailing breakeven SL)


class RiskManager:
    """Risk management system"""

    # Backpack Exchange 선물 수수료
    TAKER_FEE = 0.0005    # 0.05% (마켓 주문 — 청산용)
    MAKER_FEE = 0.0002    # 0.02% (리밋 주문 — 진입용)
    # 혼합 왕복: maker 진입 + taker 청산 = 0.07%
    MIXED_ROUND_TRIP_FEE = MAKER_FEE + TAKER_FEE
    # 레거시: 양쪽 taker (하위 호환)
    ROUND_TRIP_FEE = TAKER_FEE * 2

    def __init__(self, config):
        self.config = config
        self.positions: Dict[str, Position] = {}
        self.daily_pnl = 0.0
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.total_capital = config.trading.initial_capital
        self.total_fees = 0.0  # 누적 수수료 추적
    
    def calculate_position_size(self, price: float, capital: float) -> float:
        """
        Calculate position size based on risk management rules
        """
        # Maximum position size based on capital
        max_position_value = capital * (self.config.risk_management.max_position_size_percent / 100)
        max_size = max_position_value / price
        
        # Use configured trade size or max, whichever is smaller
        position_size = min(self.config.strategy.trade_size, max_size)
        
        return round(position_size, 4)
    
    def set_stop_loss(self, position: Position, current_price: float) -> float:
        """Calculate stop loss price"""
        stop_loss_decimal = self.config.risk_management.stop_loss_percent / 100
        
        if position.side == 'long':
            stop_loss = position.entry_price * (1 - stop_loss_decimal)
        else:  # short
            stop_loss = position.entry_price * (1 + stop_loss_decimal)
        
        return stop_loss
    
    def set_take_profit(self, position: Position) -> float:
        """Calculate take profit price"""
        take_profit_decimal = self.config.risk_management.take_profit_percent / 100
        
        if position.side == 'long':
            take_profit = position.entry_price * (1 + take_profit_decimal)
        else:  # short
            take_profit = position.entry_price * (1 - take_profit_decimal)
        
        return take_profit
    
    def update_trailing_stop(self, position: Position, current_price: float) -> Optional[float]:
        """
        Update trailing stop based on current price
        Returns new stop loss if trailing stop is triggered
        """
        trailing_percent = self.config.risk_management.trailing_stop_percent / 100
        
        if position.side == 'long':
            # Update highest price
            if position.highest_price is None or current_price > position.highest_price:
                position.highest_price = current_price
            
            # Calculate trailing stop
            trailing_stop = position.highest_price * (1 - trailing_percent)
            
            # Update stop loss if trailing stop is higher
            if position.stop_loss is None or trailing_stop > position.stop_loss:
                position.trailing_stop = trailing_stop
                return trailing_stop
        
        else:  # short
            # Update lowest price
            if position.lowest_price is None or current_price < position.lowest_price:
                position.lowest_price = current_price
            
            # Calculate trailing stop
            trailing_stop = position.lowest_price * (1 + trailing_percent)
            
            # Update stop loss if trailing stop is lower
            if position.stop_loss is None or trailing_stop < position.stop_loss:
                position.trailing_stop = trailing_stop
                return trailing_stop
        
        return None
    
    def check_stop_loss(self, position: Position, current_price: float) -> bool:
        """Check if stop loss is hit"""
        if position.stop_loss is None:
            return False
        
        if position.side == 'long':
            return current_price <= position.stop_loss
        else:  # short
            return current_price >= position.stop_loss
    
    def check_take_profit(self, position: Position, current_price: float) -> bool:
        """Check if take profit is hit"""
        if position.take_profit is None:
            return False
        
        if position.side == 'long':
            return current_price >= position.take_profit
        else:  # short
            return current_price <= position.take_profit
    
    def calculate_pnl(self, position: Position, current_price: float) -> float:
        """Calculate P&L for a position (혼합 수수료: maker 진입 + taker 청산)"""
        if position.side == 'long':
            raw_pnl = (current_price - position.entry_price) * position.size
        else:  # short
            raw_pnl = (position.entry_price - current_price) * position.size

        # 혼합 수수료: 진입(maker) + 청산(taker)
        notional_entry = position.entry_price * position.size
        notional_exit  = current_price * position.size
        fee = notional_entry * self.MAKER_FEE + notional_exit * self.TAKER_FEE
        return raw_pnl - fee

    def calculate_pnl_raw(self, position: Position, current_price: float) -> float:
        """Calculate raw P&L without fees (SL/TP 체크용)"""
        if position.side == 'long':
            return (current_price - position.entry_price) * position.size
        else:
            return (position.entry_price - current_price) * position.size

    def calculate_pnl_percent(self, position: Position, current_price: float) -> float:
        """Calculate P&L percentage (수수료 포함)"""
        pnl = self.calculate_pnl(position, current_price)
        position_value = position.entry_price * position.size
        return (pnl / position_value) * 100

    def estimate_round_trip_fee(self, price: float, size: float) -> float:
        """진입 전 예상 왕복 수수료 (maker 진입 + taker 청산)"""
        notional = price * size
        return notional * self.MIXED_ROUND_TRIP_FEE
    
    def check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit is reached"""
        # Reset daily P&L at midnight
        now = datetime.now()
        if now >= self.daily_reset_time + timedelta(days=1):
            self.daily_pnl = 0.0
            self.daily_reset_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Check if daily loss exceeds limit
        max_daily_loss = self.total_capital * (self.config.risk_management.max_daily_loss_percent / 100)
        return self.daily_pnl <= -max_daily_loss
    
    def update_daily_pnl(self, pnl: float):
        """Update daily P&L"""
        self.daily_pnl += pnl
    
    def open_position(
        self,
        symbol: str,
        entry_price: float,
        size: float,
        side: str,
        atr: float = 0.0,
        regime: str = "trending",
        entry_time: datetime = None,
    ) -> Position:
        """Open a new position with risk management.

        Args:
            atr: ATR value (1h). If > 0, uses ATR-based dynamic SL/TP
            regime: "trending" | "ranging" — TP를 시장 상태에 맞게 조정
            entry_time: 진입 시각 (None이면 현재 시각 사용, 재시작 동기화 시 전달)
        """
        position = Position(
            symbol=symbol,
            entry_price=entry_price,
            size=size,
            side=side,
            entry_time=entry_time or datetime.now(),
            _atr=atr,
        )

        # Set stop loss and take profit
        if atr > 0:
            # ── 동적 SL/TP (ATR 기반 + 레짐 반영) ──────────────────
            # MFE 분석 결과: 평균 유리이동 0.33×ATR → TP 0.3×ATR가 최적
            # SL 0.5×ATR로 축소 → R:R 개선 + 손실 폭 감소
            sl_dist = 0.5 * atr    # SL = 0.5 ATR (was 1.0)
            if regime == "ranging":
                tp_dist = 0.3 * atr  # 횡보장: MFE 기반 최적 (was 0.5)
            else:
                tp_dist = 0.5 * atr  # 추세장: 약간 넉넉히 (was 1.0)
            if side == "long":
                position.stop_loss   = entry_price - sl_dist
                position.take_profit = entry_price + tp_dist
            else:
                position.stop_loss   = entry_price + sl_dist
                position.take_profit = entry_price - tp_dist
        else:
            # ── 기존 고정 % SL/TP ────────────────────────────────────
            position.stop_loss = self.set_stop_loss(position, entry_price)
            position.take_profit = self.set_take_profit(position)
        
        # Initialize for trailing stop
        if side == 'long':
            position.highest_price = entry_price
        else:
            position.lowest_price = entry_price
        
        self.positions[symbol] = position
        return position
    
    def close_position(self, symbol: str, exit_price: float) -> Optional[float]:
        """Close a position and return P&L (혼합 수수료 포함)"""
        if symbol not in self.positions:
            return None

        position = self.positions[symbol]
        pnl = self.calculate_pnl(position, exit_price)  # 이미 혼합 수수료 차감됨

        # 혼합 수수료 추적 (maker 진입 + taker 청산)
        notional_entry = position.entry_price * position.size
        notional_exit  = exit_price * position.size
        fee = notional_entry * self.MAKER_FEE + notional_exit * self.TAKER_FEE
        self.total_fees += fee

        # Update daily P&L
        self.update_daily_pnl(pnl)

        # Remove position
        del self.positions[symbol]

        return pnl
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position by symbol"""
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """Check if position exists"""
        return symbol in self.positions
    
    def get_risk_metrics(self) -> Dict:
        """Get current risk metrics"""
        return {
            'daily_pnl': self.daily_pnl,
            'daily_pnl_percent': (self.daily_pnl / self.total_capital) * 100,
            'open_positions': len(self.positions),
            'total_capital': self.total_capital,
            'daily_loss_limit_reached': self.check_daily_loss_limit()
        }
