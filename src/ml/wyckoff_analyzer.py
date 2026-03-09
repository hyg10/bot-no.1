"""
Wyckoff Method Analyzer — 수요·공급 기반 추세 분석
===================================================
@sasuketrading 와이코프 3대 법칙 + 세부 패턴 기반:

◆ 3대 법칙:
  1. 수요·공급의 법칙 → 호가창 bid/ask 불균형 측정
  2. 원인과 결과 → 횡보(원인) 기간이 길수록 돌파(결과) 강도 강함
  3. 노력 vs 결과 → 거래량(노력) 대비 가격(결과) Divergence 추적

◆ 핵심 패턴 감지:
  - Churning (물량 정체): 거래량↑ + 가격 고점 갱신 실패 → 분배 경고
  - Spring (스프링): 지지선 깨뜨린 후 빠르게 회복 → 매집 완료 = LONG
  - Upthrust (업스러스트): 저항선 돌파 후 빠르게 되돌림 → 분배 시작 = SHORT
  - SOS/SOW: 강도/약세 신호

◆ 4대 국면:
  1.매집(Accumulation) → 2.마크업(Markup) → 3.분배(Distribution) → 4.마크다운(Markdown)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import math


@dataclass
class WyckoffSignal:
    """와이코프 분석 결과"""
    bias: str               # 'long' | 'short' | 'neutral'
    strength: float          # 0.0 ~ 1.0 (신호 강도)
    phase: str               # 'accumulation' | 'markup' | 'distribution' | 'markdown'
    volume_confirm: bool     # 거래량이 가격 방향을 확인하는가
    orderbook_bias: str      # 'bid_heavy' | 'ask_heavy' | 'balanced'
    orderbook_ratio: float   # bid_vol / ask_vol (1.0 = 균형)
    effort_result: str       # 'confirmed' | 'divergence' | 'weak'
    # ── 새로 추가된 패턴 필드 ──
    churning: bool = False       # 물량 정체 감지
    spring: bool = False         # 스프링 감지 (매집 완료)
    upthrust: bool = False       # 업스러스트 감지 (분배 시작)
    consolidation_bars: int = 0  # 횡보 기간 (캔들 수)
    detail: str = ""             # 상세 설명


class WyckoffAnalyzer:
    """
    와이코프 수요·공급 분석기 (3대 법칙 + 세부 패턴)
    """

    def __init__(
        self,
        ob_imbalance_threshold: float = 1.3,
        volume_lookback: int = 10,
        range_threshold_pct: float = 0.5,
    ):
        self.ob_threshold = ob_imbalance_threshold
        self.vol_lookback = volume_lookback
        self.range_threshold = range_threshold_pct

    def analyze(
        self,
        klines: List[Dict],
        depth: Optional[Dict] = None,
    ) -> WyckoffSignal:
        """
        와이코프 종합 분석 실행.
        """
        # ── 법칙 1: 수요·공급 (호가창) ──────────────────────────────
        ob_bias, ob_label, ob_ratio = self._orderbook_imbalance(depth)

        # ── 법칙 2: 원인과 결과 (횡보 기간 측정) ───────────────────
        consol_bars = self._measure_consolidation(klines)

        # ── 법칙 3: 노력 vs 결과 ───────────────────────────────────
        evr_bias, evr_label, vol_confirm = self._effort_vs_result(klines)

        # ── 패턴: Churning / Spring / Upthrust ─────────────────────
        is_churning = self._detect_churning(klines)
        is_spring   = self._detect_spring(klines)
        is_upthrust = self._detect_upthrust(klines)

        # ── 국면 판단 ─────────────────────────────────────────────
        phase = self._detect_phase(klines, is_churning, is_spring, is_upthrust)

        # ── 종합 점수 ─────────────────────────────────────────────
        bias, strength, detail = self._combine_signals(
            evr_bias, ob_bias, phase, vol_confirm, ob_ratio,
            is_churning, is_spring, is_upthrust, consol_bars,
        )

        return WyckoffSignal(
            bias=bias,
            strength=strength,
            phase=phase,
            volume_confirm=vol_confirm,
            orderbook_bias=ob_label,
            orderbook_ratio=ob_ratio,
            effort_result=evr_label,
            churning=is_churning,
            spring=is_spring,
            upthrust=is_upthrust,
            consolidation_bars=consol_bars,
            detail=detail,
        )

    # ══════════════════════════════════════════════════════════════════
    # 법칙 3: 노력 vs 결과 (Effort vs Result)
    # ══════════════════════════════════════════════════════════════════

    def _effort_vs_result(self, klines: List[Dict]):
        """
        거래량(노력) vs 가격변화(결과) — Divergence 추적이 핵심!
        """
        if len(klines) < 3:
            return "neutral", "weak", False

        lookback = min(self.vol_lookback, len(klines) - 1)
        recent = klines[-lookback:]

        volumes = [float(k.get("volume", 0)) for k in recent]
        avg_vol = sum(volumes) / len(volumes) if volumes else 1.0

        last_3 = klines[-3:]
        price_change = float(last_3[-1]["close"]) - float(last_3[0]["open"])
        price_change_pct = price_change / float(last_3[0]["open"]) * 100.0

        recent_vol = sum(float(k.get("volume", 0)) for k in last_3) / 3.0
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

        if abs(price_change_pct) < 0.05:
            return "neutral", "weak", False

        if price_change_pct > 0:
            if vol_ratio >= 1.0:
                return "long", "confirmed", True
            else:
                return "long", "divergence", False
        else:
            if vol_ratio >= 1.0:
                return "short", "confirmed", True
            else:
                return "short", "divergence", False

    # ══════════════════════════════════════════════════════════════════
    # 법칙 1: 수요·공급 (호가창 불균형)
    # ══════════════════════════════════════════════════════════════════

    def _orderbook_imbalance(self, depth: Optional[Dict]):
        if not depth:
            return "neutral", "balanced", 1.0

        bids = depth.get("bids", [])
        asks = depth.get("asks", [])

        if not bids or not asks:
            return "neutral", "balanced", 1.0

        # Backpack: bids 오름차순 → 마지막 10개 = 최고 매수호가
        top_bids = bids[-10:] if len(bids) >= 10 else bids
        top_asks = asks[:10] if len(asks) >= 10 else asks
        bid_vol = sum(float(b[1]) for b in top_bids)
        ask_vol = sum(float(a[1]) for a in top_asks)

        if ask_vol == 0:
            return "long", "bid_heavy", 999.0
        if bid_vol == 0:
            return "short", "ask_heavy", 0.0

        ratio = bid_vol / ask_vol

        if ratio >= self.ob_threshold:
            return "long", "bid_heavy", ratio
        elif ratio <= 1.0 / self.ob_threshold:
            return "short", "ask_heavy", ratio
        else:
            return "neutral", "balanced", ratio

    # ══════════════════════════════════════════════════════════════════
    # 법칙 2: 원인과 결과 — 횡보 기간 측정
    # ══════════════════════════════════════════════════════════════════

    def _measure_consolidation(self, klines: List[Dict]) -> int:
        """
        현재 횡보(박스권) 기간을 캔들 수로 측정.
        "횡보 기간이 길수록, 이후 나타나는 추세의 강도는 더욱 강력해집니다."

        방법: 최근 캔들부터 거슬러 올라가며 가격이 일정 범위(±0.5%) 안에
        머문 캔들 수를 셈.
        """
        if len(klines) < 3:
            return 0

        current = float(klines[-1]["close"])
        threshold = current * 0.005  # ±0.5% 범위

        count = 0
        for k in reversed(klines[:-1]):
            close = float(k["close"])
            if abs(close - current) <= threshold:
                count += 1
            else:
                break
        return count

    # ══════════════════════════════════════════════════════════════════
    # 패턴 감지: Churning / Spring / Upthrust
    # ══════════════════════════════════════════════════════════════════

    def _detect_churning(self, klines: List[Dict]) -> bool:
        """
        Churning (물량 정체) 감지.
        "거래량은 폭증하는데 주가가 더 이상 고점을 높이지 못한다면 위험 신호"

        조건:
          1. 최근 3캔들 평균 거래량 > 전체 평균 × 1.5 (거래량 폭증)
          2. 최근 3캔들의 고점이 이전 3캔들 고점보다 높지 않음 (고점 갱신 실패)
          3. 최근 3캔들의 레인지 축소 (가격 정체)
        """
        if len(klines) < 8:
            return False

        lookback = min(self.vol_lookback, len(klines))
        all_vols = [float(k.get("volume", 0)) for k in klines[-lookback:]]
        avg_vol = sum(all_vols) / len(all_vols) if all_vols else 1.0

        recent_3 = klines[-3:]
        prev_3   = klines[-6:-3]

        recent_vol = sum(float(k.get("volume", 0)) for k in recent_3) / 3.0
        vol_surge = recent_vol > avg_vol * 1.5

        recent_high = max(float(k["high"]) for k in recent_3)
        prev_high   = max(float(k["high"]) for k in prev_3)
        no_new_high = recent_high <= prev_high * 1.001  # 0.1% 이내면 갱신 실패

        # 레인지 축소 확인
        recent_range = sum(
            (float(k["high"]) - float(k["low"])) / float(k["low"]) * 100.0
            for k in recent_3
        ) / 3.0
        prev_range = sum(
            (float(k["high"]) - float(k["low"])) / float(k["low"]) * 100.0
            for k in prev_3
        ) / 3.0
        range_shrinking = recent_range < prev_range * 0.8

        return vol_surge and no_new_high and range_shrinking

    def _detect_spring(self, klines: List[Dict]) -> bool:
        """
        Spring (스프링) 감지.
        "지지선을 깨뜨려 개미의 투매를 유도하는 마지막 함정"
        → 저점 이탈 후 빠르게 회복 = 매집 완료 신호 → LONG

        조건:
          1. 최근 캔들의 저가 < 이전 N캔들 저가 (저점 이탈)
          2. 최근 캔들의 종가 > 이전 저점 (빠르게 회복)
          3. 최근 캔들의 거래량 낮음 (함정 = 약한 매도)
        """
        if len(klines) < 6:
            return False

        lookback = min(8, len(klines) - 1)
        prev_candles = klines[-lookback:-1]
        last = klines[-1]

        prev_low = min(float(k["low"]) for k in prev_candles)
        last_low   = float(last["low"])
        last_close = float(last["close"])

        # 저점 이탈 후 회복
        broke_support = last_low < prev_low * 0.999  # 0.1% 이탈
        recovered = last_close > prev_low             # 종가는 다시 위

        # 거래량 확인: 이탈 캔들의 거래량이 낮아야 함 (함정)
        all_vols = [float(k.get("volume", 0)) for k in prev_candles]
        avg_vol = sum(all_vols) / len(all_vols) if all_vols else 1.0
        last_vol = float(last.get("volume", 0))
        low_volume = last_vol < avg_vol * 1.2  # 평균 이하~약간 위

        return broke_support and recovered and low_volume

    def _detect_upthrust(self, klines: List[Dict]) -> bool:
        """
        Upthrust (업스러스트) 감지.
        "돌파하는 척 유인한 뒤 급락시키는 속임수 현상"
        → 고점 돌파 후 빠르게 되돌림 = 분배 시작 → SHORT

        조건:
          1. 최근 캔들의 고가 > 이전 N캔들 고가 (고점 돌파)
          2. 최근 캔들의 종가 < 이전 고점 (빠르게 되돌림)
          3. 윗꼬리가 긴 캔들 (세력이 위에서 판 흔적)
        """
        if len(klines) < 6:
            return False

        lookback = min(8, len(klines) - 1)
        prev_candles = klines[-lookback:-1]
        last = klines[-1]

        prev_high = max(float(k["high"]) for k in prev_candles)
        last_high  = float(last["high"])
        last_close = float(last["close"])
        last_open  = float(last["open"])
        last_low   = float(last["low"])

        # 고점 돌파 후 되돌림
        broke_resistance = last_high > prev_high * 1.001  # 0.1% 돌파
        fell_back = last_close < prev_high                 # 종가는 다시 아래

        # 윗꼬리 확인 (세력의 매도 흔적)
        body = abs(last_close - last_open)
        upper_wick = last_high - max(last_close, last_open)
        total_range = last_high - last_low
        long_upper_wick = (
            total_range > 0 and upper_wick > body and upper_wick > total_range * 0.4
        )

        return broke_resistance and fell_back and long_upper_wick

    # ══════════════════════════════════════════════════════════════════
    # 국면 판단 (개선)
    # ══════════════════════════════════════════════════════════════════

    def _detect_phase(
        self, klines: List[Dict],
        is_churning: bool = False,
        is_spring: bool = False,
        is_upthrust: bool = False,
    ) -> str:
        """
        와이코프 4대 국면 + 패턴 기반 정밀 감지:

        Phase A: 상승 모멘텀 둔화 (과열)
        Phase B: 본격 물량 정리 + 고점 횡보 (탐욕)
        Phase C: 가짜 고점 돌파로 불나방 유도 (유혹)
        Phase D/E: 지선 붕괴 + 본격 하락 (공포)
        """
        if len(klines) < 6:
            return "markup"

        # 패턴이 국면을 직접 지시하는 경우
        if is_spring:
            return "accumulation"   # 매집 완료 → 마크업 직전
        if is_upthrust:
            return "distribution"   # 분배 시작 → 마크다운 직전
        if is_churning:
            return "distribution"   # 물량 정체 = 분배 진행 중

        lookback = min(self.vol_lookback, len(klines))
        recent = klines[-lookback:]

        ranges = [
            (float(k["high"]) - float(k["low"])) / float(k["low"]) * 100.0
            for k in recent
        ]
        avg_range = sum(ranges) / len(ranges) if ranges else 0.5
        recent_3_range = sum(ranges[-3:]) / 3.0

        first_close = float(recent[0]["close"])
        last_close = float(recent[-1]["close"])
        trend_pct = (last_close - first_close) / first_close * 100.0

        volumes = [float(k.get("volume", 0)) for k in recent]
        avg_vol = sum(volumes) / len(volumes) if volumes else 1.0
        recent_vol = sum(volumes[-3:]) / 3.0
        vol_rising = recent_vol > avg_vol

        range_contracting = recent_3_range < avg_range * self.range_threshold

        if range_contracting and vol_rising:
            if trend_pct < -0.5:
                return "accumulation"
            elif trend_pct > 0.5:
                return "distribution"
            else:
                return "accumulation"
        elif trend_pct > 0.3:
            return "markup"
        elif trend_pct < -0.3:
            return "markdown"
        else:
            return "accumulation"

    # ══════════════════════════════════════════════════════════════════
    # 종합 점수 산출
    # ══════════════════════════════════════════════════════════════════

    def _combine_signals(
        self,
        evr_bias: str,
        ob_bias: str,
        phase: str,
        vol_confirm: bool,
        ob_ratio: float,
        is_churning: bool,
        is_spring: bool,
        is_upthrust: bool,
        consol_bars: int,
    ):
        """
        종합 점수 체계 (max ±5.0):
          EVR confirmed:       ±1.0
          EVR divergence:      ±0.3
          Orderbook:           ±1.0
          Phase:               ±1.0
          Spring:              +1.5  (매집 완료 = 강한 LONG)
          Upthrust:            -1.5  (분배 시작 = 강한 SHORT)
          Churning:            -0.5  (분배 경고)
          Consolidation 보너스: 횡보 ≥5바 시 돌파 방향 ±0.3
        """
        score = 0.0
        reasons = []

        # ── EVR ────────────────────────────────────────────────
        if evr_bias == "long":
            score += 1.0 if vol_confirm else 0.3
            reasons.append(f"EVR:상승{'확인' if vol_confirm else '약함'}")
        elif evr_bias == "short":
            score -= 1.0 if vol_confirm else 0.3
            reasons.append(f"EVR:하락{'확인' if vol_confirm else '약함'}")

        # ── 호가창 ─────────────────────────────────────────────
        if ob_bias == "long":
            score += 1.0
            reasons.append(f"호가:수요우위({ob_ratio:.1f}x)")
        elif ob_bias == "short":
            score -= 1.0
            reasons.append(f"호가:공급우위({ob_ratio:.1f}x)")

        # ── 국면 ──────────────────────────────────────────────
        if phase in ("markup", "accumulation"):
            score += 1.0
            reasons.append(f"국면:{phase}")
        elif phase in ("markdown", "distribution"):
            score -= 1.0
            reasons.append(f"국면:{phase}")

        # ── 패턴 보너스 ───────────────────────────────────────
        if is_spring:
            score += 1.5
            reasons.append("Spring(매집완료+1.5)")
        if is_upthrust:
            score -= 1.5
            reasons.append("Upthrust(분배시작-1.5)")
        if is_churning:
            score -= 0.5
            reasons.append("Churning(물량정체-0.5)")

        # ── 횡보 기간 보너스 (원인→결과) ──────────────────────
        if consol_bars >= 5:
            # 횡보 후 돌파 방향이 현재 score 방향과 같으면 보너스
            if score > 0:
                score += 0.3
                reasons.append(f"횡보{consol_bars}bar→돌파보너스(+0.3)")
            elif score < 0:
                score -= 0.3
                reasons.append(f"횡보{consol_bars}bar→돌파보너스(-0.3)")

        # ── 최종 ──────────────────────────────────────────────
        strength = min(1.0, abs(score) / 5.0)  # 0~1 정규화 (max ±5)
        detail = " + ".join(reasons) if reasons else "신호없음"

        if score >= 1.0:
            return "long", strength, detail
        elif score <= -1.0:
            return "short", strength, detail
        else:
            return "neutral", strength, detail
