"""
Backpack Exchange client wrapper
"""
from typing import Dict, List, Optional
from backpack_exchange_sdk import AuthenticationClient, PublicClient
from backpack_exchange_sdk.enums import OrderType
from src.config.config import config
from src.utils.logger import logger


class BackpackClient:
    """Wrapper for Backpack Exchange SDK"""
    
    def __init__(self):
        self.public_client = PublicClient()
        self.auth_client = AuthenticationClient(
            config.backpack.api_key,
            config.backpack.secret_key
        )
        logger.info("Backpack client initialized", {
            "environment": config.backpack.environment,
            "symbol": config.trading.symbol
        })
    
    def get_ticker(self, symbol: str = None) -> Dict:
        """Get ticker data"""
        symbol = symbol or config.trading.symbol
        try:
            return self.public_client.get_ticker(symbol)
        except Exception as e:
            logger.error(f"Failed to get ticker", {"error": str(e)})
            raise
    
    def get_markets(self) -> List[Dict]:
        """Get all available markets"""
        try:
            return self.public_client.get_markets()
        except Exception as e:
            logger.error("Failed to get markets", {"error": str(e)})
            raise
    
    def get_balances(self) -> List[Dict]:
        """Get account balances"""
        try:
            return self.auth_client.get_balances()
        except Exception as e:
            logger.error("Failed to get balances", {"error": str(e)})
            raise

    def get_available_equity(self) -> float:
        """
        실제 사용 가능한 자산 조회.
        autoLend=True 환경에서는 get_balances()가 0을 반환하므로
        get_collateral()의 netEquityAvailable을 사용해야 함.
        """
        try:
            col = self.auth_client.get_collateral()
            return float(col.get("netEquityAvailable", 0))
        except Exception as e:
            logger.error("Failed to get collateral equity", {"error": str(e)})
            return 0.0
    
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: str
    ) -> Dict:
        """Place a market order"""
        try:
            order = self.auth_client.execute_order(
                orderType=OrderType.MARKET.value,
                side=side,
                symbol=symbol,
                quantity=quantity
            )
            
            logger.info("Market order placed", {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_id": order.get('id')
            })
            
            return order
        except Exception as e:
            logger.error("Failed to place market order", {"error": str(e)})
            raise
    
    def place_limit_order(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        time_in_force: str = "GTC"
    ) -> Dict:
        """Place a limit order"""
        try:
            logger.debug(f"Placing limit order", {
                "symbol": symbol,
                "side": side,
                "price": price,
                "quantity": quantity
            })
            
            order = self.auth_client.execute_order(
                orderType=OrderType.LIMIT.value,
                side=side,
                symbol=symbol,
                price=price,
                quantity=quantity,
                timeInForce=time_in_force
            )
            
            logger.info("Limit order placed", {
                "symbol": symbol,
                "side": side,
                "price": price,
                "quantity": quantity,
                "order_id": order.get('id')
            })
            
            return order
        except Exception as e:
            logger.error("Failed to place limit order", {
                "symbol": symbol,
                "side": side,
                "price": price,
                "quantity": quantity,
                "error": str(e)
            })
            raise
    
    def place_post_only_limit_order(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
    ) -> Dict:
        """Post-only 리밋 주문 (maker 수수료 보장).

        스프레드를 교차하면 거래소가 거부 (taker 수수료 방지).
        SDK 주의: timeInForce와 postOnly는 상호배타 → timeInForce 생략.
        """
        try:
            order = self.auth_client.execute_order(
                orderType=OrderType.LIMIT.value,
                side=side,
                symbol=symbol,
                price=price,
                quantity=quantity,
                postOnly=True,
            )
            logger.info(f"[LimitOrder] Post-only placed", {
                "symbol": symbol, "side": side,
                "price": price, "qty": quantity,
                "order_id": order.get("id"),
            })
            return order
        except Exception as e:
            logger.error(f"[LimitOrder] Post-only failed", {
                "symbol": symbol, "side": side,
                "price": price, "qty": quantity,
                "error": str(e),
            })
            raise

    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """Cancel an order"""
        try:
            result = self.auth_client.cancel_open_order(
                symbol=symbol,
                orderId=order_id
            )
            logger.info("Order cancelled", {
                "symbol": symbol,
                "order_id": order_id
            })
            return result
        except Exception as e:
            logger.error("Failed to cancel order", {
                "symbol": symbol,
                "order_id": order_id,
                "error": str(e)
            })
            raise
    
    def get_depth(self, symbol: str = None) -> Dict:
        """Get order book depth"""
        symbol = symbol or config.trading.symbol
        try:
            return self.public_client.get_depth(symbol)
        except Exception as e:
            logger.error(f"Failed to get depth for {symbol}", {"error": str(e)})
            raise

    def get_best_bid_ask(self, symbol: str = None) -> Dict:
        """오더북에서 최우선 호가 추출.

        Returns:
            {"best_bid": float, "best_ask": float, "spread": float}
        """
        symbol = symbol or config.trading.symbol
        try:
            depth = self.get_depth(symbol)
            bids = depth.get("bids", [])
            asks = depth.get("asks", [])
            if not bids or not asks:
                raise ValueError(f"Empty order book for {symbol}")
            # Backpack: bids 오름차순 (마지막=최고가), asks 오름차순 (첫번째=최저가)
            best_bid = float(bids[-1][0])
            best_ask = float(asks[0][0])
            return {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": best_ask - best_bid,
            }
        except Exception as e:
            logger.error(f"Failed to get best bid/ask for {symbol}", {"error": str(e)})
            raise
    
    def get_order_history(self, symbol: str = None) -> List[Dict]:
        """Get order history"""
        symbol = symbol or config.trading.symbol
        try:
            return self.auth_client.get_order_history(symbol=symbol)
        except Exception as e:
            logger.error("Failed to get order history", {"error": str(e)})
            raise

    def get_open_positions(self, symbol: str = None) -> List[Dict]:
        """Get real open positions from exchange"""
        try:
            result = self.auth_client.get_open_positions()
            if symbol and isinstance(result, list):
                result = [p for p in result if p.get("symbol") == symbol]
            return result if result else []
        except Exception as e:
            logger.error("Failed to get open positions", {"error": str(e)})
            return []

    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """Get open orders from exchange"""
        try:
            kwargs = {"symbol": symbol} if symbol else {}
            result = self.auth_client.get_open_orders(**kwargs)
            return result if result else []
        except Exception as e:
            logger.error("Failed to get open orders", {"error": str(e)})
            return []

    def get_klines(self, symbol: str, interval: str = "1h", hours: int = 24) -> List[Dict]:
        """
        1시간 캔들 데이터 조회.
        Returns list of dicts with keys: open, high, low, close, volume, start, end
        """
        import time
        try:
            now = int(time.time())
            start_time = now - hours * 3600
            raw = self.public_client.get_klines(symbol, interval, start_time=start_time)
            return raw if raw else []
        except Exception as e:
            logger.error(f"Failed to get klines for {symbol}", {"error": str(e)})
            return []

    def get_trend_bias(self, symbol: str, sma_period: int = 7) -> str:
        """
        1h 캔들 기반 SMA 추세 방향 반환.
        Returns: 'long' | 'short' | 'neutral'

        - 현재가 > SMA(sma_period) 이상 +0.5% → 'long'
        - 현재가 < SMA(sma_period) 이하 -0.5% → 'short'
        - 나머지 → 'neutral'

        NOTE: threshold 0.2%→0.5% 확대. 0.2% 기준에서 264거래 중 99.2%가
        neutral → SMA가 사실상 방향 결정에 기여 못함. 0.5%로 올리면
        long/short 판정이 실제 추세에만 발동하여 노이즈 감소.
        """
        try:
            klines = self.get_klines(symbol, "1h", hours=sma_period + 4)
            if len(klines) < sma_period:
                return "neutral"
            closes = [float(k["close"]) for k in klines]
            sma = sum(closes[-sma_period:]) / sma_period
            current = closes[-1]
            diff_pct = (current - sma) / sma * 100.0
            if diff_pct >= 0.5:
                return "long"
            elif diff_pct <= -0.5:
                return "short"
            else:
                return "neutral"
        except Exception as e:
            logger.error(f"Failed to get trend bias", {"error": str(e)})
            return "neutral"

    def get_market_regime(self, symbol: str, period: int = 14) -> Dict:
        """
        ATR + 볼린저밴드 기반 시장 레짐 감지.

        Returns:
            {
                "regime": "trending" | "ranging" | "unknown",
                "atr_pct": float,          # ATR as % of price
                "bb_width_pct": float,     # BB width as % of middle band
                "bb_position": float,      # 0.0=하단, 0.5=중앙, 1.0=상단
                "volatility": "high" | "medium" | "low",
                "atr": float,              # raw ATR value
            }
        """
        try:
            klines = self.get_klines(symbol, "1h", hours=period + 10)
            if len(klines) < period + 1:
                return {"regime": "unknown", "atr_pct": 0, "bb_width_pct": 0,
                        "bb_position": 0.5, "volatility": "low", "atr": 0}

            highs  = [float(k["high"]) for k in klines]
            lows   = [float(k["low"]) for k in klines]
            closes = [float(k["close"]) for k in klines]
            current = closes[-1]

            # ── ATR (Average True Range) ──────────────────────────────
            trs = []
            for i in range(1, len(closes)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
                trs.append(tr)
            atr = sum(trs[-period:]) / period
            atr_pct = atr / current * 100.0

            # ── 볼린저밴드 (20기간, 2σ) ──────────────────────────────
            bb_period = min(20, len(closes))
            bb_closes = closes[-bb_period:]
            bb_sma = sum(bb_closes) / bb_period
            variance = sum((c - bb_sma) ** 2 for c in bb_closes) / bb_period
            bb_std = variance ** 0.5
            bb_upper = bb_sma + 2 * bb_std
            bb_lower = bb_sma - 2 * bb_std
            bb_width = bb_upper - bb_lower
            bb_width_pct = bb_width / bb_sma * 100.0

            # BB 내 현재가 위치 (0.0 = 하단, 1.0 = 상단)
            if bb_width > 0:
                bb_position = (current - bb_lower) / bb_width
                bb_position = max(0.0, min(1.0, bb_position))
            else:
                bb_position = 0.5

            # ── Efficiency Ratio (방향성 효율) ───────────────────────
            # ER = |방향 이동| / 총 이동거리  (0=완전 횡보, 1=완전 추세)
            # 크립토는 ATR이 항상 높으므로 절대값 대신 상대적 방향성으로 판단
            er_period = min(10, len(closes) - 1)
            if er_period >= 2:
                direction_move = abs(closes[-1] - closes[-1 - er_period])
                total_move = sum(
                    abs(closes[i] - closes[i - 1])
                    for i in range(len(closes) - er_period, len(closes))
                )
                efficiency_ratio = direction_move / total_move if total_move > 0 else 0.5
            else:
                efficiency_ratio = 0.5

            # ── 레짐 판정 ─────────────────────────────────────────────
            # Efficiency Ratio 기반 (크립토 친화적)
            #   ER < 0.18 → 확실한 횡보 (차단)
            #   ER > 0.35 → 확실한 추세 (진입 허용)
            #   중간(0.18~0.35) → BB 폭으로 보조 판단
            ER_RANGING  = 0.18   # was 0.25 — 너무 엄격해서 진입 기회 부족
            ER_TRENDING = 0.35   # was 0.40
            if efficiency_ratio < ER_RANGING:
                regime = "ranging"
                volatility = "low"
            elif efficiency_ratio > ER_TRENDING:
                regime = "trending"
                volatility = "high"
            elif bb_width_pct < 1.5:
                regime = "ranging"   # ER 중간 + BB 매우 좁음 → 횡보
                volatility = "medium"
            else:
                regime = "trending"  # ER 중간 + BB 어느 정도 → 추세
                volatility = "medium"

            return {
                "regime": regime,
                "atr_pct": round(atr_pct, 4),
                "bb_width_pct": round(bb_width_pct, 4),
                "bb_position": round(bb_position, 3),
                "volatility": volatility,
                "atr": round(atr, 2),
                "efficiency_ratio": round(efficiency_ratio, 3),
            }
        except Exception as e:
            logger.error(f"Failed to get market regime: {e}")
            return {"regime": "unknown", "atr_pct": 0, "bb_width_pct": 0,
                    "bb_position": 0.5, "volatility": "low", "atr": 0}

    def get_fill_history(self, symbol: str = None, limit: int = 20) -> List[Dict]:
        """Get recent fill history"""
        try:
            kwargs = {"limit": limit}
            if symbol:
                kwargs["symbol"] = symbol
            result = self.auth_client.get_fill_history(**kwargs)
            return result if result else []
        except Exception as e:
            logger.error("Failed to get fill history", {"error": str(e)})
            return []

    def get_order_fill_price(self, symbol: str, order_id: str) -> Dict:
        """특정 주문의 체결 정보 조회.

        Returns:
            {"filled": bool, "fill_price": float, "fill_size": float}
        """
        try:
            fills = self.auth_client.get_fill_history(
                orderId=order_id, symbol=symbol, limit=50
            )
            if not fills:
                return {"filled": False, "fill_price": 0.0, "fill_size": 0.0}

            total_qty = 0.0
            total_value = 0.0
            for f in fills:
                qty = float(f.get("quantity", 0))
                price = float(f.get("price", 0))
                total_qty += qty
                total_value += qty * price

            avg_price = total_value / total_qty if total_qty > 0 else 0.0
            return {
                "filled": total_qty > 0,
                "fill_price": avg_price,
                "fill_size": total_qty,
            }
        except Exception as e:
            logger.error(f"[FillCheck] Failed for order {order_id}", {"error": str(e)})
            return {"filled": False, "fill_price": 0.0, "fill_size": 0.0}
