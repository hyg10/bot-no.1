"""
Hedge Manager
=============
Backpack Exchange does not support hedge mode (simultaneous long + short
on the same symbol), so we hedge using ETH_USDC_PERP (BTC-ETH ~85% correlation):

  BTC LONG  at risk (-0.5%) -> Short ETH_USDC_PERP
            BTC 하락 → ETH도 하락 → ETH 숏 수익으로 손실 상쇄 ✅

  BTC SHORT at risk (+0.5%) -> Long  ETH_USDC_PERP
            BTC 상승 → ETH도 상승 → ETH 롱 수익으로 손실 상쇄 ✅

Hedge closes automatically when:
  - Main position closes
  - Main position recovers past the close threshold
"""
import math
from typing import Optional, Dict
from dataclasses import dataclass
from datetime import datetime

from src.utils.logger import logger


# ── Config ────────────────────────────────────────────────────────────────────
HEDGE_OPEN_PCT  = 0.5   # open hedge when drawdown exceeds this %
HEDGE_CLOSE_PCT = 0.2   # close hedge when position recovers to this % drawdown
HEDGE_RATIO_ETH = 0.50  # hedge 50% of BTC position value with ETH


@dataclass
class HedgePosition:
    symbol: str
    side: str            # 'long' or 'short'
    entry_price: float
    size: float
    opened_at: datetime
    hedge_for: str       # main symbol being hedged


class HedgeManager:
    """
    Cross-symbol hedge manager for Backpack Exchange.

    Both hedge directions use ETH_USDC_PERP (high BTC correlation):
      - BTC LONG  손실 시 → ETH SHORT  (같이 떨어지는 ETH 숏으로 손실 상쇄)
      - BTC SHORT 손실 시 → ETH LONG   (같이 오르는 ETH 롱으로 손실 상쇄)

    Usage:
        hm = HedgeManager(client)

        # Inside position monitor loop:
        hm.check_and_hedge(main_position, current_btc_price)

        # When main position closes:
        hm.close_all("main_closed")
    """

    ETH_SYMBOL = "ETH_USDC_PERP"
    DECIMALS   = 4   # minQuantity=0.0001, stepSize=0.0001
    MIN_QTY    = 0.0001

    def __init__(self, client):
        self.client = client
        self.hedge_position: Optional[HedgePosition] = None
        self._active = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def check_and_hedge(self, main_position, current_btc_price: float):
        """
        Called every monitor tick. Decides whether to open or close the hedge.
        main_position : Position from RiskManager (or None if no position)
        """
        if main_position is None:
            if self._active:
                self._close_hedge("main_closed")
            return

        entry = main_position.entry_price
        side  = main_position.side

        if side == "long":
            # BTC 롱 → 하락할수록 손실 → ETH 숏으로 헷지
            drawdown_pct = (current_btc_price - entry) / entry * 100
            if drawdown_pct <= -HEDGE_OPEN_PCT and not self._active:
                logger.info(
                    f"[Hedge] BTC LONG drawdown {drawdown_pct:.2f}% "
                    f"-> opening ETH SHORT hedge"
                )
                self._open_eth_position("short", main_position, current_btc_price)
            elif drawdown_pct >= -HEDGE_CLOSE_PCT and self._active:
                logger.info(
                    f"[Hedge] BTC LONG recovered to {drawdown_pct:.2f}% "
                    f"-> closing ETH hedge"
                )
                self._close_hedge("recovered")

        elif side == "short":
            # BTC 숏 → 상승할수록 손실 → ETH 롱으로 헷지
            adverse_pct = (current_btc_price - entry) / entry * 100
            if adverse_pct >= HEDGE_OPEN_PCT and not self._active:
                logger.info(
                    f"[Hedge] BTC SHORT adverse {adverse_pct:.2f}% "
                    f"-> opening ETH LONG hedge"
                )
                self._open_eth_position("long", main_position, current_btc_price)
            elif adverse_pct <= HEDGE_CLOSE_PCT and self._active:
                logger.info(
                    f"[Hedge] BTC SHORT recovered to {adverse_pct:.2f}% "
                    f"-> closing ETH hedge"
                )
                self._close_hedge("recovered")

    def close_all(self, reason: str = "main_closed"):
        """Force-close hedge position (call when main position is closed)."""
        if self._active:
            self._close_hedge(reason)

    def get_status(self) -> Dict:
        if not self._active or self.hedge_position is None:
            return {"active": False}
        hp = self.hedge_position
        return {
            "active":      True,
            "symbol":      hp.symbol,
            "side":        hp.side,
            "entry_price": hp.entry_price,
            "size":        hp.size,
            "opened_at":   hp.opened_at.isoformat(),
            "hedge_for":   hp.hedge_for,
        }

    def is_active(self) -> bool:
        return self._active

    # ── Internal ───────────────────────────────────────────────────────────────

    def _open_eth_position(self, hedge_side: str, main_position, btc_price: float):
        """
        Open ETH hedge position.
        hedge_side = 'short'  →  BTC 롱 포지션 헷지 (BTC 하락 시 ETH도 하락)
        hedge_side = 'long'   →  BTC 숏 포지션 헷지 (BTC 상승 시 ETH도 상승)
        """
        try:
            ticker    = self.client.get_ticker(self.ETH_SYMBOL)
            eth_price = float(ticker.get("lastPrice", 0))
            if eth_price <= 0:
                logger.warning("[Hedge] Invalid ETH price, skip")
                return

            main_usd   = main_position.size * btc_price
            hedge_usd  = main_usd * HEDGE_RATIO_ETH
            hedge_size = hedge_usd / eth_price
            qty_str    = self._fmt(hedge_size)

            if float(qty_str) < self.MIN_QTY:
                logger.warning(
                    f"[Hedge] ETH {hedge_side} size {qty_str} < min {self.MIN_QTY} "
                    f"(hedge_usd=${hedge_usd:.2f}, eth=${eth_price:.2f})"
                )
                return

            order_side = "Ask" if hedge_side == "short" else "Bid"
            self.client.place_market_order(
                symbol=self.ETH_SYMBOL, side=order_side, quantity=qty_str
            )
            self.hedge_position = HedgePosition(
                symbol=self.ETH_SYMBOL, side=hedge_side,
                entry_price=eth_price, size=float(qty_str),
                opened_at=datetime.now(), hedge_for="BTC_USDC_PERP",
            )
            self._active = True
            logger.info(
                f"[Hedge] ETH {hedge_side.upper()} {qty_str} @ ${eth_price:.2f} "
                f"(hedge_usd=${hedge_usd:.2f})"
            )

        except Exception as e:
            logger.error(f"[Hedge] Open ETH {hedge_side} failed: {e}")

    def _close_hedge(self, reason: str):
        """Close the active hedge position at market price."""
        if not self._active or self.hedge_position is None:
            return

        hp = self.hedge_position
        try:
            close_side = "Bid" if hp.side == "short" else "Ask"
            qty_str    = self._fmt(hp.size)

            self.client.place_market_order(
                symbol=hp.symbol, side=close_side, quantity=qty_str
            )

            ticker     = self.client.get_ticker(hp.symbol)
            exit_price = float(ticker.get("lastPrice", hp.entry_price))

            pnl = (
                (hp.entry_price - exit_price) * hp.size if hp.side == "short"
                else (exit_price - hp.entry_price) * hp.size
            )
            logger.info(
                f"[Hedge] ETH {hp.side.upper()} closed [{reason}] PnL=${pnl:.4f}"
            )

        except Exception as e:
            logger.error(f"[Hedge] Close hedge failed: {e}")
        finally:
            self.hedge_position = None
            self._active = False

    def _fmt(self, size: float) -> str:
        """Floor-round to 4 decimal places (ETH perp step size)."""
        step    = 10 ** (-self.DECIMALS)
        floored = math.floor(size / step) * step
        return f"{floored:.{self.DECIMALS}f}"
