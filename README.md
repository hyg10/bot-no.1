# 🚀 Advanced Backpack Trading Bot

Backpack 거래소를 위한 **전문가급 자동매매 봇** with:
- ✅ **백테스팅 시스템**: 과거 데이터로 전략 검증
- ✅ **리스크 관리**: 손절/익절/트레일링 스톱
- ✅ **유전 알고리즘 최적화**: 최적 파라미터 자동 탐색
- ✅ **적응형 전략**: 수익률에 따라 자동 조정
- ✅ **성과 분석**: 샤프 비율, 승률, 최대 낙폭 등

---

## 📋 목차

1. [주요 기능](#주요-기능)
2. [설치](#설치)
3. [사용법](#사용법)
4. [백테스팅](#백테스팅)
5. [최적화](#최적화)
6. [리스크 관리](#리스크-관리)
7. [적응형 전략](#적응형-전략)

---

## 🎯 주요 기능

### 1. 백테스팅 시스템
```python
# 과거 데이터로 전략 검증
python run_backtest.py

# 결과:
# - 총 수익률
# - 샤프 비율
# - 승률
# - 최대 낙폭 (MDD)
# - 평균 승/패 거래
```

### 2. 리스크 관리
- **손절 (Stop Loss)**: 설정한 % 손실 시 자동 청산
- **익절 (Take Profit)**: 설정한 % 수익 시 자동 청산
- **트레일링 스톱**: 수익 보호를 위한 동적 손절
- **일일 손실 제한**: 하루 최대 손실 도달 시 거래 중지
- **포지션 크기 관리**: 자본 대비 안전한 포지션 크기 계산

### 3. 유전 알고리즘 최적화
```python
# 최적 파라미터 자동 탐색
python run_optimization.py

# 탐색 파라미터:
# - 거래 크기
# - 손절 %
# - 익절 %
# - 거래 빈도
```

### 4. 적응형 전략
- **자동 성과 평가**: 24시간마다 성과 분석
- **파라미터 자동 조정**:
  - 승률 낮음 → 포지션 크기 축소
  - 승률 높음 → 포지션 크기 확대
  - 샤프 비율 낮음 → 거래 빈도 감소
  - 연속 손실 → 거래 일시 중지

### 5. Pure Market Making (NEW! 🎉)
Hummingbot 스타일의 **마켓 메이킹** 전략!
```python
# 양쪽 호가에 주문 배치
python src/market_making_bot.py

# 특징:
# - 스프레드 차익 획득
# - 자동 인벤토리 관리
# - 주문 자동 갱신
# - 수익 자동 계산
```

**상세 가이드**: [MARKET_MAKING_GUIDE.md](./MARKET_MAKING_GUIDE.md)

---

## 🔧 설치

### 1. Python 환경
```bash
# Python 3.8 이상 필요
python --version

# 가상환경 생성 (권장)
python -m venv venv

# 활성화
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정
```bash
cp .env.example .env
nano .env
```

**필수 설정**:
```env
# API 키
BACKPACK_API_KEY=your_api_key
BACKPACK_SECRET_KEY=your_secret_key

# 전략 파라미터
STRATEGY_TRADE_SIZE=0.1
STOP_LOSS_PERCENT=2.0
TAKE_PROFIT_PERCENT=5.0

# 최적화 (선택)
AUTO_OPTIMIZATION_ENABLED=true
ADAPTIVE_STRATEGY_ENABLED=true
```

---

## 📊 사용법

### 기본 실행
```bash
python src/advanced_bot.py
```

### 실행 흐름
1. **연결 확인**: Backpack API 연결
2. **잔고 확인**: 계좌 잔고 조회
3. **거래 시작**: 설정된 파라미터로 거래
4. **리스크 관리**: 각 거래에 손절/익절 자동 설정
5. **포지션 모니터링**: 실시간으로 손절/익절 체크
6. **성과 평가**: 주기적으로 성과 분석 및 파라미터 조정

---

## 🧪 백테스팅

### 실행
```bash
python run_backtest.py
```

### 출력 예시
```
=============================================================
BACKTEST RESULTS
=============================================================

📊 Trading Statistics:
  Total Trades: 50
  Winning Trades: 32
  Losing Trades: 18
  Win Rate: 64.00%

💰 Performance:
  Total P&L: $1,250.50
  Total Return: 12.51%
  Initial Capital: $10,000.00
  Final Capital: $11,250.50

📈 Trade Analysis:
  Average Win: $65.30
  Average Loss: $-28.40
  Average Trade: $25.01
  Max Win: $150.00
  Max Loss: $-75.00
  Profit Factor: 2.30

⚠️ Risk Metrics:
  Max Drawdown: $320.00 (3.20%)
  Sharpe Ratio: 1.85
  Sortino Ratio: 2.45

⏱️ Time Analysis:
  Average Trade Duration: 2:15:00
=============================================================
```

### 결과 해석
- **승률 > 50%**: 좋은 신호
- **샤프 비율 > 1.0**: 좋은 위험 조정 수익
- **샤프 비율 > 2.0**: 매우 우수
- **최대 낙폭 < 10%**: 안전한 전략
- **Profit Factor > 2.0**: 우수한 수익성

---

## 🧬 최적화

### 유전 알고리즘 최적화
```bash
python run_optimization.py
```

### 그리드 서치 (완전 탐색)
```bash
python run_optimization.py grid
```

### 최적화 프로세스
1. **초기 모집단 생성**: 랜덤 파라미터 조합 20개
2. **적합도 평가**: 각 조합을 백테스팅
3. **선택**: 상위 성과자 선택
4. **교배**: 우수 파라미터 조합
5. **돌연변이**: 다양성 유지
6. **반복**: 50세대 진화

### 결과 활용
```bash
# 최적화 완료 후 출력:
# Optimized Strategy Parameters
STRATEGY_TRADE_SIZE=0.0850
STOP_LOSS_PERCENT=1.50
TAKE_PROFIT_PERCENT=4.50
```

이 값을 `.env` 파일에 복사하세요!

---

## 🛡️ 리스크 관리

### 손절 (Stop Loss)
```env
STOP_LOSS_PERCENT=2.0  # 2% 손실 시 자동 청산
```

**동작**:
- 롱 포지션: 진입가 - 2%
- 숏 포지션: 진입가 + 2%

### 익절 (Take Profit)
```env
TAKE_PROFIT_PERCENT=5.0  # 5% 수익 시 자동 청산
```

### 트레일링 스톱
```env
TRAILING_STOP_PERCENT=1.5  # 최고가 대비 1.5% 하락 시 청산
```

**동작**:
- 가격이 상승하면 손절가도 함께 상승
- 최고가 갱신 시 자동으로 손절가 업데이트
- 수익 보호 메커니즘

### 포지션 크기 관리
```env
MAX_POSITION_SIZE_PERCENT=20.0  # 자본의 최대 20%
```

### 일일 손실 제한
```env
MAX_DAILY_LOSS_PERCENT=10.0  # 하루 10% 손실 시 중지
```

---

## 🔄 적응형 전략

### 활성화
```env
ADAPTIVE_STRATEGY_ENABLED=true
EVALUATION_PERIOD=24  # 24시간마다 평가
MIN_WIN_RATE=40.0  # 최소 승률 40%
```

### 조정 규칙

#### 규칙 1: 승률 기반
```
승률 < 40% → 포지션 크기 10% 감소 + 손절 강화
승률 > 60% → 포지션 크기 5% 증가
```

#### 규칙 2: 샤프 비율 기반
```
샤프 < 0.5 → 거래 빈도 50% 감소
샤프 > 2.0 → 거래 빈도 20% 증가
```

#### 규칙 3: 낙폭 기반
```
낙폭 > 5% → 포지션 크기 50% 감소
```

#### 규칙 4: 연속 손실
```
연속 3회 이상 손실 → 1시간 거래 중지
최근 5회 중 4회 손실 → 1시간 거래 중지
```

### 실시간 로그 예시
```
[INFO] 🔍 Evaluating performance...
[INFO] 📊 Performance Metrics | win_rate=58.5% | sharpe_ratio=1.45 | total_pnl=$350.20
[INFO] ✅ High win rate (58.5%) - Increasing position size
[INFO]   Adjusted trade_size: 0.1 → 0.105
```

---

## 📈 성과 지표

### 기본 지표
- **승률 (Win Rate)**: 이긴 거래 / 전체 거래
- **총 수익률 (Total Return)**: (최종 자본 - 초기 자본) / 초기 자본
- **평균 승 (Average Win)**: 이긴 거래의 평균 수익
- **평균 패 (Average Loss)**: 진 거래의 평균 손실

### 고급 지표
- **Profit Factor**: 총 수익 / 총 손실
  - > 2.0: 우수
  - 1.0-2.0: 양호
  - < 1.0: 부진

- **샤프 비율 (Sharpe Ratio)**: 위험 조정 수익률
  - > 2.0: 매우 우수
  - 1.0-2.0: 우수
  - < 1.0: 부진

- **소르티노 비율 (Sortino Ratio)**: 하방 위험 조정 수익률
  - 샤프 비율과 유사하지만 하방 변동성만 고려

- **최대 낙폭 (Max Drawdown)**: 최고점 대비 최대 하락폭
  - < 5%: 매우 안전
  - 5-10%: 양호
  - > 20%: 위험

---

## 🎮 실전 사용 팁

### 1. 단계별 접근
```bash
# Step 1: 백테스팅으로 전략 검증
python run_backtest.py

# Step 2: 최적화로 파라미터 튜닝
python run_optimization.py

# Step 3: 최적 파라미터를 .env에 적용

# Step 4: Devnet에서 실전 테스트
BACKPACK_ENVIRONMENT=devnet python src/advanced_bot.py

# Step 5: 성과 확인 후 Mainnet
BACKPACK_ENVIRONMENT=mainnet python src/advanced_bot.py
```

### 2. 보수적 설정 (초보자)
```env
STRATEGY_TRADE_SIZE=0.05
STOP_LOSS_PERCENT=1.5
TAKE_PROFIT_PERCENT=4.0
MAX_POSITION_SIZE_PERCENT=10.0
ADAPTIVE_STRATEGY_ENABLED=true
```

### 3. 공격적 설정 (경험자)
```env
STRATEGY_TRADE_SIZE=0.2
STOP_LOSS_PERCENT=3.0
TAKE_PROFIT_PERCENT=8.0
MAX_POSITION_SIZE_PERCENT=30.0
AUTO_OPTIMIZATION_ENABLED=true
```

---

## 📂 프로젝트 구조

```
backpack-advanced-bot/
├── src/
│   ├── config/
│   │   └── config.py                  # 설정 관리
│   ├── backtesting/
│   │   └── backtester.py              # 백테스팅 엔진
│   ├── risk_management/
│   │   └── risk_manager.py            # 리스크 관리
│   ├── optimization/
│   │   └── genetic_optimizer.py       # 유전 알고리즘
│   ├── strategies/
│   │   └── adaptive_strategy.py       # 적응형 전략
│   ├── utils/
│   │   ├── backpack_client.py         # API 래퍼
│   │   └── logger.py                  # 로깅
│   └── advanced_bot.py                # 메인 봇
├── run_backtest.py                    # 백테스팅 실행
├── run_optimization.py                # 최적화 실행
├── requirements.txt
├── .env.example
└── README.md
```

---

## ⚠️ 주의사항

1. **백테스팅은 과거 성과입니다**
   - 미래 수익을 보장하지 않습니다
   - 항상 devnet에서 먼저 테스트하세요

2. **리스크 관리는 필수입니다**
   - 절대 손실 감당 불가능한 금액으로 거래하지 마세요
   - 일일 손실 제한을 설정하세요

3. **과최적화 주의**
   - 너무 과거 데이터에 맞춘 파라미터는 실전에서 작동하지 않을 수 있습니다
   - Out-of-sample 테스트를 수행하세요

4. **모니터링**
   - 봇을 실행한 후에도 정기적으로 확인하세요
   - 시장 상황이 급변하면 수동 개입이 필요할 수 있습니다

---

## 📚 참고 자료

- [Backpack Exchange](https://backpack.exchange)
- [Backpack API 문서](https://docs.backpack.exchange/)
- [백테스팅 베스트 프랙티스](https://www.investopedia.com/terms/b/backtesting.asp)
- [리스크 관리 전략](https://www.investopedia.com/terms/r/riskmanagement.asp)

---

## 📄 라이선스

MIT License

---

## 🙏 Credits

- Backpack Exchange SDK by [solomeowl](https://github.com/solomeowl/backpack_exchange_sdk)
- DEAP (Genetic Algorithm Library)

---

**Happy Trading! May the profits be with you!** 🚀📈💰
