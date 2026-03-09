"""
Trade Analyst - 매매 사후분석 + 패턴 학습 시스템
================================================
각 매매가 끝날 때마다:
  1. 진입 시 시장 상태를 분석 (추세/변동성/RSI/거래량/시간대)
  2. 손익 원인을 분류하고 설명문 생성
  3. 패턴 DB에 저장
  4. 유사 패턴 승률을 계산해 '교훈(Lesson)' 생성
  5. 다음 매매 전 신뢰도 점수로 포지션 크기 조정

모든 데이터는 logs/trade_analysis/ 에 JSON으로 저장됩니다.
"""
import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict


# ── 데이터 구조 ────────────────────────────────────────────────────────────────

@dataclass
class MarketContext:
    """진입 시점의 시장 상태"""
    # 추세
    trend: str          # "strong_up" | "up" | "neutral" | "down" | "strong_down"
    trend_strength: float   # 0~1

    # 모멘텀
    rsi: float          # 0~100
    rsi_zone: str       # "oversold"(<30) | "normal" | "overbought"(>70)
    macd_signal: str    # "bullish" | "neutral" | "bearish"
    momentum: float     # -1~1

    # 변동성
    volatility: str     # "low" | "normal" | "high" | "extreme"
    volatility_value: float

    # 거래량
    volume_ratio: float     # 현재 거래량 / 평균 거래량
    volume_signal: str      # "low" | "normal" | "high"

    # 볼린저 밴드
    bb_position: float      # 0=하단 0.5=중앙 1=상단
    bb_zone: str            # "lower" | "middle" | "upper"

    # 시간대
    hour: int
    session: str        # "asia" | "europe" | "us" | "off"

    # 가격
    price: float


@dataclass
class LossReason:
    """손실 원인 분석"""
    primary: str        # 주 원인
    secondary: str      # 부 원인
    description: str    # 설명문


@dataclass
class WinReason:
    """이익 원인 분석"""
    primary: str
    secondary: str
    description: str


@dataclass
class AnalyzedTrade:
    """분석이 완료된 매매 기록"""
    trade_id: str
    timestamp: str
    symbol: str
    side: str               # "long" | "short"
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_percent: float
    exit_reason: str        # "take_profit" | "stop_loss" | "time_limit" | "rl_signal"
    duration_seconds: float

    context: Dict           # MarketContext as dict
    outcome: str            # "win" | "loss" | "breakeven"

    win_reason: Optional[Dict] = None
    loss_reason: Optional[Dict] = None
    lesson: str = ""        # 이 매매에서 배운 것
    confidence_at_entry: float = 0.5   # 진입 시 신뢰도


@dataclass
class Lesson:
    """학습된 교훈 (패턴 → 결과)"""
    pattern_key: str        # 패턴 식별자 (예: "rsi_overbought+trend_down+long")
    description: str        # 교훈 설명
    win_rate: float         # 이 패턴의 승률
    sample_count: int       # 샘플 수
    avg_pnl_pct: float      # 평균 손익%
    last_updated: str
    confidence: float       # 0~1 (샘플이 많을수록 높음)


# ── 시장 상태 분석기 ──────────────────────────────────────────────────────────

class MarketContextAnalyzer:
    """
    가격 히스토리에서 시장 상태를 분석해 MarketContext 생성
    """

    def analyze(self, prices: List[float], volumes: List[float],
                current_price: float) -> MarketContext:
        """시장 상태 종합 분석"""
        if len(prices) < 20:
            return self._default_context(current_price)

        prices_arr = np.array(prices[-50:])
        vols_arr = np.array(volumes[-50:]) if len(volumes) >= 50 else np.array(volumes)

        # 추세
        trend, trend_strength = self._analyze_trend(prices_arr)

        # RSI
        rsi = self._calc_rsi(prices_arr)
        rsi_zone = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "normal"

        # MACD
        macd_sig = self._calc_macd_signal(prices_arr)
        macd_str = "bullish" if macd_sig > 0.001 else "bearish" if macd_sig < -0.001 else "neutral"

        # 모멘텀 (10봉 ROC)
        momentum = float((prices_arr[-1] - prices_arr[-10]) / prices_arr[-10]) if len(prices_arr) >= 10 else 0.0
        momentum = float(np.clip(momentum, -0.1, 0.1) / 0.1)

        # 변동성
        returns = np.diff(prices_arr) / prices_arr[:-1]
        vol_val = float(np.std(returns[-20:])) if len(returns) >= 20 else 0.0
        vol_str = ("extreme" if vol_val > 0.03
                   else "high" if vol_val > 0.015
                   else "low" if vol_val < 0.005
                   else "normal")

        # 거래량
        vol_ratio = 1.0
        if len(vols_arr) >= 20:
            avg_vol = np.mean(vols_arr[-20:-5]) if len(vols_arr) > 5 else np.mean(vols_arr)
            vol_ratio = float(vols_arr[-1] / (avg_vol + 1e-8))
        vol_sig = "high" if vol_ratio > 1.5 else "low" if vol_ratio < 0.5 else "normal"

        # 볼린저 밴드 위치
        bb_pos = self._calc_bb_position(prices_arr[-20:], current_price)
        bb_zone = "lower" if bb_pos < 0.3 else "upper" if bb_pos > 0.7 else "middle"

        # 시간대 (UTC 기준)
        hour = datetime.utcnow().hour
        session = self._get_session(hour)

        return MarketContext(
            trend=trend,
            trend_strength=round(trend_strength, 3),
            rsi=round(rsi, 1),
            rsi_zone=rsi_zone,
            macd_signal=macd_str,
            momentum=round(momentum, 3),
            volatility=vol_str,
            volatility_value=round(vol_val, 6),
            volume_ratio=round(vol_ratio, 2),
            volume_signal=vol_sig,
            bb_position=round(bb_pos, 3),
            bb_zone=bb_zone,
            hour=hour,
            session=session,
            price=current_price,
        )

    def _analyze_trend(self, prices: np.ndarray) -> Tuple[str, float]:
        if len(prices) < 20:
            return "neutral", 0.0
        ema5 = self._ema(prices, 5)
        ema20 = self._ema(prices, 20)
        ratio = (ema5 - ema20) / (ema20 + 1e-8)
        strength = min(abs(ratio) / 0.02, 1.0)
        if ratio > 0.01:
            trend = "strong_up" if ratio > 0.02 else "up"
        elif ratio < -0.01:
            trend = "strong_down" if ratio < -0.02 else "down"
        else:
            trend = "neutral"
        return trend, float(strength)

    def _calc_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.maximum(deltas, 0)
        losses = np.maximum(-deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100.0 - (100.0 / (1.0 + rs)))

    def _calc_macd_signal(self, prices: np.ndarray) -> float:
        if len(prices) < 26:
            return 0.0
        ema12 = self._ema(prices, 12)
        ema26 = self._ema(prices, 26)
        return float((ema12 - ema26) / (prices[-1] + 1e-8))

    def _calc_bb_position(self, prices: np.ndarray, current: float) -> float:
        if len(prices) < 2:
            return 0.5
        mean = np.mean(prices)
        std = np.std(prices)
        if std == 0:
            return 0.5
        pos = (current - (mean - 2 * std)) / (4 * std)
        return float(np.clip(pos, 0, 1))

    def _ema(self, prices: np.ndarray, period: int) -> float:
        if len(prices) == 0:
            return 0.0
        k = 2.0 / (period + 1)
        ema = prices[-min(period, len(prices))]
        for p in prices[-min(period, len(prices)) + 1:]:
            ema = p * k + ema * (1 - k)
        return float(ema)

    def _get_session(self, hour: int) -> str:
        if 0 <= hour < 8:
            return "asia"
        elif 8 <= hour < 13:
            return "europe"
        elif 13 <= hour < 21:
            return "us"
        else:
            return "off"

    def _default_context(self, price: float) -> MarketContext:
        hour = datetime.utcnow().hour
        return MarketContext(
            trend="neutral", trend_strength=0.0,
            rsi=50.0, rsi_zone="normal",
            macd_signal="neutral", momentum=0.0,
            volatility="normal", volatility_value=0.01,
            volume_ratio=1.0, volume_signal="normal",
            bb_position=0.5, bb_zone="middle",
            hour=hour, session=self._get_session(hour),
            price=price,
        )


# ── 손익 원인 분석기 ──────────────────────────────────────────────────────────

class CauseAnalyzer:
    """
    매매 결과와 시장 상태를 보고 손익 원인을 분석
    """

    def analyze_win(self, trade: Dict, context: MarketContext) -> WinReason:
        """이익 원인 분석"""
        side = trade.get("side", "long")
        exit_reason = trade.get("exit_reason", "")
        pnl_pct = trade.get("pnl_percent", 0)

        # 주 원인 분류
        primary_reasons = []
        secondary_reasons = []

        # 추세 일치
        if side == "long" and context.trend in ("up", "strong_up"):
            primary_reasons.append("추세 방향 일치 (상승추세 + 매수)")
        elif side == "short" and context.trend in ("down", "strong_down"):
            primary_reasons.append("추세 방향 일치 (하락추세 + 매도)")

        # RSI 역발상
        if side == "long" and context.rsi_zone == "oversold":
            primary_reasons.append("RSI 과매도 구간 진입 (반등 포착)")
        elif side == "short" and context.rsi_zone == "overbought":
            primary_reasons.append("RSI 과매수 구간 진입 (조정 포착)")

        # 볼린저 밴드
        if side == "long" and context.bb_zone == "lower":
            primary_reasons.append("볼린저 밴드 하단 지지선 반등")
        elif side == "short" and context.bb_zone == "upper":
            primary_reasons.append("볼린저 밴드 상단 저항선 반락")

        # 거래량 확인
        if context.volume_signal == "high":
            secondary_reasons.append("거래량 급증으로 방향 신뢰도 높음")

        # MACD
        if context.macd_signal == "bullish" and side == "long":
            secondary_reasons.append("MACD 강세 신호")
        elif context.macd_signal == "bearish" and side == "short":
            secondary_reasons.append("MACD 약세 신호")

        # 변동성
        if context.volatility == "low":
            secondary_reasons.append("낮은 변동성 환경 (안정적 수익)")

        # 청산 방식
        if exit_reason == "take_profit":
            secondary_reasons.append(f"목표가 달성 (TP 청산, +{pnl_pct:.2f}%)")
        elif exit_reason == "rl_signal":
            secondary_reasons.append("RL 에이전트 최적 타이밍 청산")

        primary = primary_reasons[0] if primary_reasons else "우호적 가격 움직임"
        secondary = " / ".join(secondary_reasons[:2]) if secondary_reasons else "기술적 지표 우호"
        description = (
            f"[이익 원인] {primary}. "
            f"{secondary}. "
            f"진입 당시 RSI={context.rsi:.0f}, "
            f"추세={context.trend}, "
            f"변동성={context.volatility}"
        )

        return WinReason(primary=primary, secondary=secondary, description=description)

    def analyze_loss(self, trade: Dict, context: MarketContext) -> LossReason:
        """손실 원인 분석"""
        side = trade.get("side", "long")
        exit_reason = trade.get("exit_reason", "")
        pnl_pct = trade.get("pnl_percent", 0)

        primary_reasons = []
        secondary_reasons = []

        # 추세 역행
        if side == "long" and context.trend in ("down", "strong_down"):
            primary_reasons.append("추세 역행 진입 (하락추세에서 매수)")
        elif side == "short" and context.trend in ("up", "strong_up"):
            primary_reasons.append("추세 역행 진입 (상승추세에서 매도)")

        # RSI 위험 구간
        if side == "long" and context.rsi_zone == "overbought":
            primary_reasons.append("RSI 과매수 구간에서 매수 (고점 추격)")
        elif side == "short" and context.rsi_zone == "oversold":
            primary_reasons.append("RSI 과매도 구간에서 매도 (저점 공매도)")

        # 변동성
        if context.volatility in ("high", "extreme"):
            primary_reasons.append(f"고변동성 환경 진입 (변동성={context.volatility})")

        # 거래량 부재
        if context.volume_signal == "low":
            secondary_reasons.append("거래량 부족 (방향성 불확실)")

        # 청산 방식
        if exit_reason == "stop_loss":
            secondary_reasons.append(f"손절 청산 ({pnl_pct:.2f}%)")
        elif exit_reason == "time_limit":
            secondary_reasons.append("보유 시간 초과 (방향 미실현)")

        # 시간대
        if context.session == "off":
            secondary_reasons.append("비활성 시간대 거래 (유동성 부족)")

        primary = primary_reasons[0] if primary_reasons else "불리한 가격 움직임"
        secondary = " / ".join(secondary_reasons[:2]) if secondary_reasons else "시장 조건 불일치"
        description = (
            f"[손실 원인] {primary}. "
            f"{secondary}. "
            f"진입 당시 RSI={context.rsi:.0f}, "
            f"추세={context.trend}, "
            f"변동성={context.volatility}"
        )

        return LossReason(primary=primary, secondary=secondary, description=description)

    def generate_lesson(self, trade: Dict, context: MarketContext,
                        outcome: str) -> str:
        """이 매매에서 배울 교훈 문장 생성"""
        side = trade.get("side", "long")
        pnl_pct = trade.get("pnl_percent", 0)

        if outcome == "win":
            lessons = []
            if context.trend in ("up", "strong_up") and side == "long":
                lessons.append("[O] 상승추세 + 매수 조합은 유효 → 계속 활용")
            if context.rsi_zone == "oversold" and side == "long":
                lessons.append("[O] RSI 과매도 구간 매수는 효과적")
            if context.volatility == "low":
                lessons.append("[O] 저변동성 환경이 안정적 수익에 유리")
            if context.volume_signal == "high":
                lessons.append("[O] 거래량 급증 시 방향 신뢰도 높음")
            return " | ".join(lessons) if lessons else f"[O] +{pnl_pct:.2f}% 수익: 현재 패턴 유지"
        else:
            lessons = []
            if context.trend in ("down", "strong_down") and side == "long":
                lessons.append("[X] 하락추세에서 매수 금지 → 추세 확인 필수")
            if context.rsi_zone == "overbought" and side == "long":
                lessons.append("[X] RSI 과매수 구간 매수 위험 → 진입 자제")
            if context.volatility in ("high", "extreme"):
                lessons.append("[X] 고변동성 환경에서 포지션 크기 축소 필요")
            if context.session == "off":
                lessons.append("[X] 비활성 시간대 거래 자제")
            return " | ".join(lessons) if lessons else f"[X] {pnl_pct:.2f}% 손실: 진입 조건 재검토"


# ── 패턴 분석기 ───────────────────────────────────────────────────────────────

class PatternAnalyzer:
    """
    누적된 매매 기록에서 통계적 패턴을 찾아 교훈을 도출
    """

    def extract_pattern_key(self, context: MarketContext, side: str) -> str:
        """패턴 식별 키 생성"""
        return (
            f"{side}|"
            f"trend:{context.trend}|"
            f"rsi:{context.rsi_zone}|"
            f"vol:{context.volatility}|"
            f"session:{context.session}|"
            f"bb:{context.bb_zone}"
        )

    def extract_sub_keys(self, context: MarketContext, side: str) -> List[str]:
        """서브 패턴 키들 (부분 조합)"""
        return [
            f"{side}|trend:{context.trend}",
            f"{side}|rsi:{context.rsi_zone}",
            f"{side}|vol:{context.volatility}",
            f"{side}|session:{context.session}",
            f"{side}|trend:{context.trend}|rsi:{context.rsi_zone}",
            f"{side}|trend:{context.trend}|vol:{context.volatility}",
            f"{side}|rsi:{context.rsi_zone}|vol:{context.volatility}",
        ]

    def compute_lessons(self, trades: List[AnalyzedTrade]) -> Dict[str, Lesson]:
        """전체 매매 기록에서 교훈 계산"""
        # 패턴별 집계
        pattern_stats: Dict[str, Dict] = defaultdict(lambda: {
            "wins": 0, "total": 0, "pnl_sum": 0.0
        })

        for t in trades:
            ctx = MarketContext(**t.context)
            all_keys = [self.extract_pattern_key(ctx, t.side)]
            all_keys += self.extract_sub_keys(ctx, t.side)

            is_win = t.outcome == "win"
            for key in all_keys:
                pattern_stats[key]["total"] += 1
                pattern_stats[key]["pnl_sum"] += t.pnl_percent
                if is_win:
                    pattern_stats[key]["wins"] += 1

        # 교훈 생성 (샘플 3개 이상인 패턴만)
        lessons = {}
        for key, stats in pattern_stats.items():
            n = stats["total"]
            if n < 3:
                continue
            win_rate = stats["wins"] / n
            avg_pnl = stats["pnl_sum"] / n
            confidence = min(n / 20.0, 1.0)  # 20개 샘플이면 최대 신뢰도

            desc = self._describe_lesson(key, win_rate, avg_pnl, n)
            lessons[key] = Lesson(
                pattern_key=key,
                description=desc,
                win_rate=round(win_rate, 3),
                sample_count=n,
                avg_pnl_pct=round(avg_pnl, 3),
                last_updated=datetime.now().isoformat(),
                confidence=round(confidence, 3),
            )

        return lessons

    def _describe_lesson(self, key: str, win_rate: float, avg_pnl: float, n: int) -> str:
        """교훈 설명문 생성"""
        parts = key.split("|")
        cond_str = " + ".join(p for p in parts[1:] if p)
        if win_rate >= 0.6:
            qual = "유리한"
            emoji = "[O]"
        elif win_rate <= 0.4:
            qual = "불리한"
            emoji = "[X]"
        else:
            qual = "중립적인"
            emoji = "[!]"
        return (
            f"{emoji} [{cond_str}] 조건은 {qual} 패턴 "
            f"(승률={win_rate*100:.0f}%, 평균손익={avg_pnl:+.2f}%, 샘플={n})"
        )


# ── 신뢰도 평가기 ────────────────────────────────────────────────────────────

class ConfidenceEvaluator:
    """
    현재 시장 상태와 학습된 교훈을 비교해 진입 신뢰도 계산
    """

    def evaluate(self, context: MarketContext, side: str,
                 lessons: Dict[str, Lesson]) -> Tuple[float, str]:
        """
        신뢰도 점수(0~1)와 이유 반환.
        0.5 = 중립 / 0.7+ = 유리 / 0.3- = 불리
        """
        if not lessons:
            return 0.5, "학습 데이터 부족 (기본 신뢰도)"

        analyzer = PatternAnalyzer()
        full_key = analyzer.extract_pattern_key(context, side)
        sub_keys = analyzer.extract_sub_keys(context, side)

        scores = []
        matched_lessons = []

        # 전체 패턴 매칭 (가중치 2배)
        if full_key in lessons:
            lesson = lessons[full_key]
            score = lesson.win_rate * lesson.confidence
            scores.append((score * 2, lesson.confidence * 2))
            matched_lessons.append(lesson.description)

        # 서브 패턴 매칭
        for key in sub_keys:
            if key in lessons:
                lesson = lessons[key]
                score = lesson.win_rate * lesson.confidence
                scores.append((score, lesson.confidence))
                if len(matched_lessons) < 3:
                    matched_lessons.append(lesson.description)

        if not scores:
            return 0.5, "매칭된 패턴 없음 (기본 신뢰도)"

        # 가중 평균
        total_weight = sum(w for _, w in scores)
        weighted_score = sum(s * w for s, w in scores) / total_weight

        # 기본 규칙 보정
        bonus = 0.0
        if side == "long" and context.trend in ("up", "strong_up"):
            bonus += 0.05
        if side == "short" and context.trend in ("down", "strong_down"):
            bonus += 0.05
        if context.rsi_zone == "oversold" and side == "long":
            bonus += 0.05
        if context.rsi_zone == "overbought" and side == "short":
            bonus += 0.05
        if context.volatility == "extreme":
            bonus -= 0.1
        if context.session == "off":
            bonus -= 0.05

        final_score = float(np.clip(weighted_score + bonus, 0.0, 1.0))
        reason = " | ".join(matched_lessons[:2]) if matched_lessons else "패턴 매칭 완료"

        return final_score, reason


# ── 메인 TradeAnalyst ────────────────────────────────────────────────────────

class TradeAnalyst:
    """
    매매 분석 시스템 메인 클래스.

    사용법:
        analyst = TradeAnalyst()

        # 진입 전 - 신뢰도 확인
        confidence, reason = analyst.get_entry_confidence(
            prices, volumes, current_price, side
        )

        # 진입 후 - 시장 상태 저장
        context = analyst.record_entry(prices, volumes, current_price)

        # 청산 후 - 분석 실행
        analyzed = analyst.record_exit(trade_dict, context)
        analyst.print_analysis(analyzed)
    """

    def __init__(self, log_dir: str = "logs/trade_analysis"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

        self.context_analyzer = MarketContextAnalyzer()
        self.cause_analyzer = CauseAnalyzer()
        self.pattern_analyzer = PatternAnalyzer()
        self.confidence_evaluator = ConfidenceEvaluator()

        self.trades: List[AnalyzedTrade] = []
        self.lessons: Dict[str, Lesson] = {}
        self._trade_counter = 0

        self._load()
        print(f"[TradeAnalyst] 초기화 완료: {len(self.trades)}개 기록, "
              f"{len(self.lessons)}개 교훈 로드")

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def get_entry_confidence(self, prices: List[float], volumes: List[float],
                             current_price: float, side: str) -> Tuple[float, str]:
        """
        진입 전 신뢰도 평가.
        Returns: (confidence 0~1, 이유 설명)
        """
        context = self.context_analyzer.analyze(prices, volumes, current_price)
        confidence, reason = self.confidence_evaluator.evaluate(context, side, self.lessons)
        return confidence, reason

    def capture_context(self, prices: List[float], volumes: List[float],
                        current_price: float) -> MarketContext:
        """진입 시점 시장 상태 캡처 (진입 직후 호출)"""
        return self.context_analyzer.analyze(prices, volumes, current_price)

    def record_exit(self, trade: Dict, entry_context: MarketContext,
                    confidence_at_entry: float = 0.5) -> AnalyzedTrade:
        """
        청산 후 매매 분석 실행.
        trade dict 필수 키: side, entry_price, exit_price, size, pnl,
                            pnl_percent, exit_reason
        """
        self._trade_counter += 1
        pnl = trade.get("pnl", 0)
        pnl_pct = trade.get("pnl_percent", 0)
        outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "breakeven"

        # 원인 분석
        if outcome == "win":
            win_reason = self.cause_analyzer.analyze_win(trade, entry_context)
            loss_reason = None
        else:
            win_reason = None
            loss_reason = self.cause_analyzer.analyze_loss(trade, entry_context)

        lesson_text = self.cause_analyzer.generate_lesson(trade, entry_context, outcome)

        analyzed = AnalyzedTrade(
            trade_id=f"T{self._trade_counter:04d}_{datetime.now().strftime('%H%M%S')}",
            timestamp=datetime.now().isoformat(),
            symbol=trade.get("symbol", ""),
            side=trade.get("side", "long"),
            entry_price=trade.get("entry_price", 0),
            exit_price=trade.get("exit_price", 0),
            size=trade.get("size", 0),
            pnl=round(pnl, 4),
            pnl_percent=round(pnl_pct, 4),
            exit_reason=trade.get("exit_reason", ""),
            duration_seconds=trade.get("duration_seconds", 0),
            context=asdict(entry_context),
            outcome=outcome,
            win_reason=asdict(win_reason) if win_reason else None,
            loss_reason=asdict(loss_reason) if loss_reason else None,
            lesson=lesson_text,
            confidence_at_entry=round(confidence_at_entry, 3),
        )

        self.trades.append(analyzed)

        # 교훈 업데이트 (10거래마다 + 항상 저장)
        if len(self.trades) % 10 == 0:
            self._update_lessons()

        self._save()
        return analyzed

    def get_position_size_multiplier(self, confidence: float) -> float:
        """
        신뢰도 기반 포지션 크기 배수 반환.
        confidence 0.0~1.0 → multiplier 0.3~1.5
        """
        if confidence >= 0.75:
            return 1.5   # 고신뢰: 150%
        elif confidence >= 0.65:
            return 1.2   # 중상: 120%
        elif confidence >= 0.55:
            return 1.0   # 중립: 100%
        elif confidence >= 0.45:
            return 0.7   # 중하: 70%
        elif confidence >= 0.35:
            return 0.5   # 저신뢰: 50%
        else:
            return 0.3   # 매우 저신뢰: 30%

    def print_analysis(self, analyzed: AnalyzedTrade):
        """분석 결과를 콘솔에 출력"""
        emoji = "[WIN]" if analyzed.outcome == "win" else "[LOSS]" if analyzed.outcome == "loss" else "[BE]"
        print(f"\n{'─'*60}")
        print(f"{emoji} 매매 분석 [{analyzed.trade_id}]")
        print(f"{'─'*60}")
        print(f"  결과: {analyzed.outcome.upper()} | "
              f"손익: {analyzed.pnl_percent:+.2f}% (${analyzed.pnl:+.4f})")
        print(f"  진입가: ${analyzed.entry_price:.2f} → 청산가: ${analyzed.exit_price:.2f}")
        print(f"  청산 사유: {analyzed.exit_reason} | 진입 신뢰도: {analyzed.confidence_at_entry:.0%}")
        print(f"\n  [MARKET] 진입 시 시장 상태:")
        ctx = analyzed.context
        print(f"    추세: {ctx['trend']} (강도 {ctx['trend_strength']:.0%})")
        print(f"    RSI: {ctx['rsi']:.0f} ({ctx['rsi_zone']})")
        print(f"    변동성: {ctx['volatility']} | 거래량: {ctx['volume_signal']} ({ctx['volume_ratio']:.1f}x)")
        print(f"    BB 위치: {ctx['bb_zone']} ({ctx['bb_position']:.0%})")
        print(f"    세션: {ctx['session']} ({ctx['hour']}시 UTC)")

        if analyzed.win_reason:
            print(f"\n  [CAUSE] 이익 원인:")
            print(f"    {analyzed.win_reason['description']}")
        elif analyzed.loss_reason:
            print(f"\n  [CAUSE] 손실 원인:")
            print(f"    {analyzed.loss_reason['description']}")

        print(f"\n  [LESSON] 교훈:")
        print(f"    {analyzed.lesson}")

        # 관련 교훈 표시
        if self.lessons:
            ctx_obj = MarketContext(**analyzed.context)
            key = self.pattern_analyzer.extract_pattern_key(ctx_obj, analyzed.side)
            if key in self.lessons:
                l = self.lessons[key]
                print(f"\n  [STATS] 누적 패턴 통계 ({l.sample_count}회):")
                print(f"    승률: {l.win_rate*100:.0f}% | 평균손익: {l.avg_pnl_pct:+.2f}%")

        print(f"{'─'*60}\n")

    def print_summary(self):
        """전체 학습 요약 출력"""
        if not self.trades:
            print("[TradeAnalyst] 분석된 매매 없음")
            return

        wins = [t for t in self.trades if t.outcome == "win"]
        losses = [t for t in self.trades if t.outcome == "loss"]
        total = len(self.trades)

        print(f"\n{'='*60}")
        print(f"[SUMMARY] 매매 분석 요약 ({total}회)")
        print(f"{'='*60}")
        print(f"  승률: {len(wins)/total*100:.1f}% ({len(wins)}승 {len(losses)}패)")
        print(f"  평균 수익: {np.mean([t.pnl_percent for t in wins]):.2f}%" if wins else "  평균 수익: -")
        print(f"  평균 손실: {np.mean([t.pnl_percent for t in losses]):.2f}%" if losses else "  평균 손실: -")

        print(f"\n[LESSONS] 학습된 교훈 TOP 5:")
        sorted_lessons = sorted(
            self.lessons.values(),
            key=lambda l: abs(l.win_rate - 0.5) * l.confidence,
            reverse=True
        )
        for i, lesson in enumerate(sorted_lessons[:5], 1):
            print(f"  {i}. {lesson.description}")

        print(f"{'='*60}\n")

    # ── 내부 메서드 ───────────────────────────────────────────────────────────

    def _update_lessons(self):
        """교훈 재계산"""
        self.lessons = self.pattern_analyzer.compute_lessons(self.trades)
        print(f"[TradeAnalyst] 교훈 업데이트: {len(self.lessons)}개 패턴 학습됨")

    def _save(self):
        """데이터 저장"""
        trades_path = os.path.join(self.log_dir, "analyzed_trades.json")
        lessons_path = os.path.join(self.log_dir, "lessons.json")
        try:
            with open(trades_path, "w", encoding="utf-8") as f:
                json.dump([asdict(t) for t in self.trades], f,
                          ensure_ascii=False, indent=2)
            with open(lessons_path, "w", encoding="utf-8") as f:
                json.dump({k: asdict(v) for k, v in self.lessons.items()},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TradeAnalyst] 저장 실패: {e}")

    def _load(self):
        """저장된 데이터 로드"""
        trades_path = os.path.join(self.log_dir, "analyzed_trades.json")
        lessons_path = os.path.join(self.log_dir, "lessons.json")
        try:
            if os.path.exists(trades_path):
                with open(trades_path, encoding="utf-8") as f:
                    data = json.load(f)
                self.trades = [AnalyzedTrade(**d) for d in data]
                self._trade_counter = len(self.trades)
        except Exception as e:
            print(f"[TradeAnalyst] 매매 기록 로드 실패: {e}")
        try:
            if os.path.exists(lessons_path):
                with open(lessons_path, encoding="utf-8") as f:
                    data = json.load(f)
                self.lessons = {k: Lesson(**v) for k, v in data.items()}
        except Exception as e:
            print(f"[TradeAnalyst] 교훈 로드 실패: {e}")
