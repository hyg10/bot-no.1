"""
Bootstrap Particle Filter — Real-Time Trend Estimator
======================================================
PDF 참고: "How to Simulate Like a Quant Desk, Every Model, Every Formula"
Part IV: Sequential Monte Carlo for Real-Time Updating

Model
-----
  Hidden state  x_t = x_{t-1} + ε_t,   ε_t ~ N(0, σ_p²)   (random walk)
  Observation   y_t ~ N(tanh(x_t), σ_o²)                    (price return)

  P(up) = sigmoid(Σ w_i · x_i)   ← particle estimate

관측 수익률
-----------
  단일 틱(5초) 수익률은 ±0.01~0.05% → SIGMA_O=0.50 대비 너무 작아 노이즈만 됨.
  → WINDOW_TICKS=20개 슬라이딩 윈도우 누적 수익률 사용 (≈100초 변화량)
  → SIGMA_O=0.08로 낮춰 실제 가격 움직임에 민감하게 반응.

Interpretation
--------------
  x_t >> 0  →  P(up) → 1.0  →  강한 상승장
  x_t ≈  0  →  P(up) ≈ 0.5  →  중립 / 횡보
  x_t << 0  →  P(up) → 0.0  →  강한 하락장
"""
import numpy as np
from collections import deque
from typing import Tuple


class TrendParticleFilter:
    """
    Bootstrap Particle Filter for real-time BTC trend probability estimation.

    Usage
    -----
        pf = TrendParticleFilter()
        p_up, regime = pf.update(price)
        # regime: 'bull' | 'bear' | 'neutral'

    Thresholds (self_improving_bot.py에서 사용)
    ----------
        bull   : P(up) >= 0.53  →  LONG 진입
        bear   : P(up) <= 0.47  →  SHORT 진입
        neutral: 0.47 < P(up) < 0.53  →  HOLD (불확실)
    """

    # ── Hyperparameters ────────────────────────────────────────────────────────
    N            = 500   # 파티클 수
    SIGMA_P      = 0.08  # process noise — 추세 변화 속도 (작을수록 추세 지속)
    SIGMA_O      = 0.08  # observation noise — 실제 수익률 ±0.08% 수준에 맞춤
    BULL_THRESH  = 0.55  # 상승장 임계값
    BEAR_THRESH  = 0.45  # 하락장 임계값
    ESS_RATIO    = 0.50  # resampling trigger: ESS < N * ESS_RATIO
    WINDOW_TICKS = 20    # 누적 수익률 윈도우 (20 ticks × 5s = 100초)

    def __init__(self):
        # 파티클 초기화: x ~ N(0, 0.5) → P(up) ≈ 0.5 (neutral)
        self.particles = np.random.normal(0.0, 0.5, self.N)
        self.weights   = np.ones(self.N) / self.N
        self._price_buf: deque = deque(maxlen=self.WINDOW_TICKS + 1)
        self._p_up: float = 0.5
        self._regime: str = "neutral"
        self._tick_count: int = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def update(self, price: float) -> Tuple[float, str]:
        """
        새 가격 틱을 받아 hidden state를 업데이트하고 (P(up), regime)을 반환.

        Parameters
        ----------
        price : float  현재 가격

        Returns
        -------
        p_up   : float  0~1, 상승 확률
        regime : str    'bull' | 'bear' | 'neutral'
        """
        self._tick_count += 1
        self._price_buf.append(price)

        # 누적 수익률 계산: 윈도우 시작 가격 대비 현재 가격
        if len(self._price_buf) < 2:
            return self._p_up, self._regime

        base_price = self._price_buf[0]   # WINDOW_TICKS 전 가격 (또는 시작 가격)
        if base_price <= 0:
            return self._p_up, self._regime

        # 단위: % (예: BTC가 100초간 0.3% 상승 → ret_pct = 0.3)
        ret_pct = (price - base_price) / base_price * 100.0

        # ── Step 1: Predict (상태 전이) ───────────────────────────────────
        noise = np.random.normal(0.0, self.SIGMA_P, self.N)
        self.particles = self.particles + noise

        # ── Step 2: Update weights (관측 likelihood) ──────────────────────
        # 각 파티클의 예측 수익률: tanh(x) ∈ (-1, 1) %
        predicted = np.tanh(self.particles)
        log_like  = -0.5 * ((ret_pct - predicted) / self.SIGMA_O) ** 2
        log_like -= log_like.max()   # 수치 안정성
        self.weights = self.weights * np.exp(log_like)
        self.weights /= self.weights.sum()

        # ── Step 3: Resample (ESS가 낮으면 resampling) ────────────────────
        ess = 1.0 / (self.weights ** 2).sum()
        if ess < self.N * self.ESS_RATIO:
            idx = np.random.choice(self.N, size=self.N, p=self.weights)
            self.particles = self.particles[idx].copy()
            self.weights   = np.ones(self.N) / self.N

        # ── Step 4: Estimate P(up) = sigmoid(weighted mean) ───────────────
        x_mean     = float(np.dot(self.weights, self.particles))
        self._p_up = float(1.0 / (1.0 + np.exp(-x_mean)))   # sigmoid

        # ── Step 5: Classify regime ───────────────────────────────────────
        if self._p_up >= self.BULL_THRESH:
            self._regime = "bull"
        elif self._p_up <= self.BEAR_THRESH:
            self._regime = "bear"
        else:
            self._regime = "neutral"

        return self._p_up, self._regime

    def get_p_up(self) -> float:
        """현재 P(up) 추정값 반환 (update 없이)."""
        return self._p_up

    def get_regime(self) -> str:
        """현재 regime 반환 (update 없이)."""
        return self._regime

    def is_ready(self) -> bool:
        """WINDOW_TICKS만큼 쌓인 후 신뢰할 수 있는 추정 가능."""
        return self._tick_count >= self.WINDOW_TICKS

    def get_uncertainty(self) -> float:
        """파티클 분산 — 클수록 추세 불확실 (0~1 범위로 정규화)."""
        x_mean = float(np.dot(self.weights, self.particles))
        x_var  = float(np.dot(self.weights, (self.particles - x_mean) ** 2))
        return min(1.0, x_var / 4.0)

    def summary(self) -> str:
        return (
            f"P(up)={self._p_up:.1%} | regime={self._regime} | "
            f"uncertainty={self.get_uncertainty():.2f} | ticks={self._tick_count}"
        )
