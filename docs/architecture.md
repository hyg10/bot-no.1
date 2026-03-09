# 아키텍처 개요

## 시스템 구성도

```
┌─────────────────────────────────────────────────────────┐
│                   Self-Improving Bot                     │
│                 (self_improving_bot.py)                   │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ RL Agent │  │ Signal   │  │ Filter   │  │ Risk   │  │
│  │  (DQN)   │→ │ Pipeline │→ │ Chain    │→ │ Mgmt   │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘  │
│       ↑              ↑                          │        │
│       │         ┌────┴────┐                     ↓        │
│       │         │ Market  │              ┌──────────┐   │
│       │         │ Data    │              │ Backpack │   │
│       │         └────┬────┘              │ Exchange │   │
│       │              │                   └──────────┘   │
│  ┌────┴─────┐   ┌────┴────┐                             │
│  │ Self-Imp │   │ Hedge   │                             │
│  │ Engine   │   │ Manager │                             │
│  └──────────┘   └─────────┘                             │
└─────────────────────────────────────────────────────────┘
```

## 핵심 모듈

### 1. 메인 봇 루프 (`self_improving_bot.py`)
- 1분~2분 간격 사이클 실행
- 각 사이클: 데이터 수집 → 신호 생성 → 필터링 → 진입/청산 판단
- 포지션 모니터링 (별도 스레드)

### 2. 신호 파이프라인 (4-Layer Direction System)

```
Layer 0: Regime Detection (ER + BB)
    ↓ RANGING → 진입 보류 / TRENDING → 계속
Layer 1: SMA Direction (±2)
    10-period 1h SMA 기울기 → LONG/SHORT bias
Layer 2: Wyckoff Analysis (±1~2)
    거래량 + 호가 + 국면 분석 → 방향 확인
Layer 3: Particle Filter (±1)
    Bootstrap PF 확률 → 단기 방향 보조

합산 점수: max ±5
```

### 3. 필터 체인 (진입 전 5단계)

```
① Regime Filter   — ER < 0.18 → 횡보장 차단
② Score Threshold  — |score| < ENTRY(2.0) → HOLD
③ Min Hold Time    — 보유 < 600s → 전환 보류
④ BB Position      — LONG: BB > 0.5 차단 / SHORT: BB < 0.5 차단
                     (|score| ≥ 3.0 → BB 무시)
⑤ Fee Filter       — 수수료 > 예상수익 50% → 진입 거부
```

### 4. 리스크 관리 (`risk_manager.py`)

| 항목 | 방식 |
|---|---|
| SL | 1.0 × ATR (동적) |
| TP | Ranging: 0.5×ATR / Trending: 1.0×ATR |
| Trailing BE | 수익 > 0.5×ATR → SL을 진입가로 이동 |
| Time Limit | Ranging: 30분 / Trending: 40분 |
| 수수료 | Taker 0.05% × 2 = 왕복 0.10% |
| PnL 계산 | raw PnL - (진입 notional + 청산 notional) × 0.05% |

### 5. 포지션 사이징

```
base_size = STRATEGY_TRADE_SIZE (0.001 BTC)

size = base_size
     × confidence_multiplier (0.3 ~ 1.5)
     × signal_boost          (1.0 / 1.5 / 2.0)
     × wyckoff_boost          (1.0 / 1.3)

floor = MIN_ORDER_SIZE (0.0005 BTC)
cap   = base_size × 2.0 (0.002 BTC)
```

### 6. 거래소 연동 (`backpack_client.py`)
- Backpack Exchange devnet
- BTC_USDC_PERP (주 거래), ETH_USDC_PERP (헤지)
- Market Order (taker), 5x 레버리지
- 1h 캔들스틱으로 ATR, BB, SMA 계산
- Efficiency Ratio 기반 레짐 감지

### 7. 자기개선 엔진 (`self_improvement_engine.py`)
- Genetic Algorithm으로 전략 파라미터 최적화
- A/B 테스트: 현재 vs 후보 파라미터
- 24시간 주기 자동 최적화

### 8. 헤지 매니저 (`hedge_manager.py`)
- PAXG→ETH 헤지 (달러 노출 관리)
- 메인 포지션 청산 시 헤지도 정리

## 데이터 흐름

```
Backpack API
    │
    ├─ 1h 캔들 (50개) → ATR, BB, SMA, ER 계산
    │                    → Regime 판정
    │
    ├─ 호가창 (orderbook) → Wyckoff OB 분석
    │
    ├─ 최근 체결 (trades) → Wyckoff EVR 분석
    │
    └─ 계좌 잔고/포지션 → 동기화, 사이징 기준
```

## 파일 구조

```
backpack-advanced-bot-v2/
├── .claude/
│   ├── hooks/              # 자동화 훅 (포맷, 테스트, 차단)
│   ├── skills/             # 스킬 (코드검토, 리팩토링, 릴리스, 디버깅)
│   └── settings.local.json # 프로젝트 설정
├── docs/
│   ├── architecture.md     # 이 문서
│   ├── adr.md              # 엔지니어링 결정 기록
│   └── runbook.md          # 운영 런북
├── logs/
│   └── trading_bot.log     # 실시간 로그
├── src/
│   ├── config/
│   │   └── config.py       # 설정 로딩 (.env)
│   ├── ml/
│   │   ├── self_improvement_engine.py  # GA + A/B 테스트
│   │   ├── trade_analyst.py            # 신뢰도 분석, 사이징
│   │   ├── particle_filter.py          # L3 PF 방향 예측
│   │   └── wyckoff_analyzer.py         # L2 Wyckoff 분석
│   ├── risk_management/
│   │   ├── risk_manager.py    # SL/TP/PnL/수수료
│   │   └── hedge_manager.py   # 헤지 포지션 관리
│   ├── utils/
│   │   ├── backpack_client.py # 거래소 API + 레짐 감지
│   │   └── logger.py          # 로깅 설정
│   └── self_improving_bot.py  # 메인 봇
├── .env                       # 런타임 설정
├── run_self_improving_bot.py  # 엔트리포인트
├── start_bot.bat              # 자동 재시작 루프
└── restart_bot.ps1            # 깨끗한 재시작 스크립트
```
