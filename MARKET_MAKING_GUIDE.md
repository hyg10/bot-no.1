# 🎯 Pure Market Making Strategy Guide

Hummingbot 스타일의 **Pure Market Making** 전략을 추가했습니다!

---

## 📊 전략 개요

### Pure Market Making이란?

매수/매도 양쪽에 동시에 주문을 배치하여 **스프레드 차익**을 얻는 전략입니다.

```
현재 시장 가격: $95,000

┌─────────────────────────────────┐
│  매도 주문: $95,095 (+0.1%)     │ ← 이 가격에 팔고 싶은 사람
├─────────────────────────────────┤
│  중간 가격: $95,000             │
├─────────────────────────────────┤
│  매수 주문: $94,905 (-0.1%)     │ ← 이 가격에 사고 싶은 사람
└─────────────────────────────────┘

양쪽 주문이 모두 체결되면:
수익 = $95,095 - $94,905 = $190 per 1 BTC
```

---

## 🎯 핵심 기능

### 1. 양방향 주문 배치
```python
Mid Price: $95,000

Buy Order:  $94,905 (0.1% 아래)
Sell Order: $95,095 (0.1% 위)

→ 스프레드: 0.2% = $190 profit
```

### 2. 자동 주문 갱신
- 30초마다 주문 취소 후 재배치
- 시장 변화에 빠르게 대응

### 3. 인벤토리 관리
```python
매수가 많이 체결됨 → inventory +
  → 매수 스프레드 확대 (매수 억제)
  → 매도 스프레드 축소 (매도 촉진)

매도가 많이 체결됨 → inventory -
  → 매수 스프레드 축소 (매수 촉진)
  → 매도 스프레드 확대 (매도 억제)
```

### 4. 자동 수익 계산
```python
Buy filled at $94,905
Sell filled at $95,095

Profit = ($95,095 - $94,905) × 0.0001 BTC
       = $19.00
```

---

## 🚀 사용 방법

### 1. 기본 실행

```cmd
set PYTHONPATH=%CD% && python src/market_making_bot.py
```

### 2. 예상 로그

```
🚀 Starting Market Making Bot

=== MARKET MAKING BOT CONFIGURATION ===
Symbol: BTC_USDC
Trade Size: 0.0001
Bid Spread: 0.1%
Ask Spread: 0.1%

✅ Connected to Backpack Exchange (159 markets)
💰 Account Balances:
  BTC: 0.001
  USDC: 10.00

📝 Placing new orders
  Mid Price: $95,000.00
  Buy Price: $94,905.00
  Sell Price: $95,095.00
  Spread: 0.20%

✅ Buy order placed | order_id=123 | price=$94,905.00
✅ Sell order placed | order_id=124 | price=$95,095.00

[30초 후]
✅ Buy order filled! | price=$94,905.00 | inventory=0.0001

[1분 후]
✅ Sell order filled! | price=$95,095.00 | inventory=0.0000

💰 Profit realized!
  Buy Price: $94,905.00
  Sell Price: $95,095.00
  Quantity: 0.0001
  Profit: $19.00
  Total Profit: $19.00
```

---

## ⚙️ 설정 조정

### .env 파일 설정

```env
# Trading Configuration
TRADING_SYMBOL=BTC_USDC
INITIAL_CAPITAL=100.0

# Strategy Parameters
STRATEGY_TRADE_SIZE=0.0001  # 주문 크기
```

### 전략 파라미터 (코드 내)

`src/strategies/market_making_strategy.py` 수정:

```python
# Strategy parameters
self.bid_spread = 0.001  # 0.1% → 조정 가능
self.ask_spread = 0.001  # 0.1% → 조정 가능
self.order_refresh_time = 30  # 30초 → 조정 가능
self.max_inventory_ratio = 0.5  # 50% → 조정 가능
```

---

## 💡 스프레드 설정 가이드

### 보수적 (안전)
```python
self.bid_spread = 0.002  # 0.2%
self.ask_spread = 0.002  # 0.2%
# 스프레드: 0.4% = $380 profit per BTC
# 체결률: 중간
```

### 균형 (권장)
```python
self.bid_spread = 0.001  # 0.1%
self.ask_spread = 0.001  # 0.1%
# 스프레드: 0.2% = $190 profit per BTC
# 체결률: 높음
```

### 공격적 (위험)
```python
self.bid_spread = 0.0005  # 0.05%
self.ask_spread = 0.0005  # 0.05%
# 스프레드: 0.1% = $95 profit per BTC
# 체결률: 매우 높음
# 위험: 인벤토리 불균형
```

---

## 📊 수익성 계산

### 예시 1: 작은 거래
```
거래 크기: 0.0001 BTC
스프레드: 0.2%
시간당 체결: 10회 (양쪽)

시간당 수익 = 0.0001 × $95,000 × 0.002 × 10
            = $19 × 10
            = $190/시간

일일 수익 = $190 × 24 = $4,560
월간 수익 = $4,560 × 30 = $136,800
```

### 예시 2: 중간 거래
```
거래 크기: 0.001 BTC
스프레드: 0.1%
시간당 체결: 5회

시간당 수익 = 0.001 × $95,000 × 0.001 × 5
            = $95 × 5
            = $475/시간

일일 수익 = $11,400
```

**주의**: 실제 수익은 시장 상황에 따라 크게 달라집니다!

---

## ⚠️ 리스크 관리

### 1. 인벤토리 리스크
```python
# 최대 불균형 설정
self.max_inventory_ratio = 0.5  # 50%

# 한계 도달 시:
# → 주문 중지
# → 균형 회복 대기
```

### 2. 가격 급변 리스크
```python
# 30초마다 주문 갱신
# → 오래된 주문 방지
# → 불리한 가격 체결 방지
```

### 3. 최대 손실 제한
```env
# .env 파일
MAX_DAILY_LOSS_PERCENT=10.0
```

---

## 🎯 최적의 시장 조건

### ✅ 좋은 조건
- **횡보장**: 가격이 일정 범위 내에서 움직임
- **높은 거래량**: 주문이 빠르게 체결됨
- **낮은 변동성**: 안정적인 스프레드 유지

### ❌ 나쁜 조건
- **강한 추세**: 한쪽 방향으로만 체결됨
- **낮은 거래량**: 주문이 체결 안 됨
- **높은 변동성**: 큰 손실 위험

---

## 🔄 Volume Farming과 비교

| 항목 | Volume Farming | Market Making |
|------|----------------|---------------|
| **목적** | 거래량 생성 | 스프레드 수익 |
| **주문 타입** | 시장가 | 지정가 |
| **수익원** | 포지션 수익 | 스프레드 차익 |
| **리스크** | 방향성 리스크 | 인벤토리 리스크 |
| **체결 속도** | 즉시 | 대기 필요 |
| **변동성** | 높음 | 낮음 |

---

## 💻 고급 설정

### 동적 스프레드 조정

```python
# 변동성 기반 스프레드
volatility = self._calculate_volatility()
self.bid_spread = 0.001 + (volatility * 0.01)
self.ask_spread = 0.001 + (volatility * 0.01)
```

### 거래량 기반 주문 크기

```python
# 거래량이 많으면 큰 주문
volume_24h = self._get_24h_volume()
self.order_amount = base_amount * (volume_24h / 1000000)
```

---

## 🆘 문제 해결

### 주문이 체결 안 됨
→ 스프레드 줄이기 (0.2% → 0.1%)

### 인벤토리 불균형
→ 최대 비율 줄이기 (0.5 → 0.3)

### 수익이 안 남
→ 스프레드 늘리기 (0.1% → 0.2%)

### 변동성이 너무 높음
→ 주문 갱신 시간 줄이기 (30초 → 15초)

---

## 🚀 실행 예시

```cmd
# 1. .env 설정
TRADING_SYMBOL=BTC_USDC
STRATEGY_TRADE_SIZE=0.0001

# 2. 실행
set PYTHONPATH=%CD% && python src/market_making_bot.py

# 3. 모니터링
# - 30초마다 주문 갱신
# - 체결 시 자동 수익 계산
# - Ctrl+C로 종료

# 4. 결과 확인
=== MARKET MAKING STATISTICS ===
Total Buys: 25
Total Sells: 23
Total Profit: $475.00
Current Inventory: 0.0002 BTC
Average Spread: 0.18%
```

---

## 📚 더 알아보기

- [Hummingbot 공식 문서](https://docs.hummingbot.org/)
- [Market Making 전략 가이드](https://hummingbot.org/strategies/pure-market-making/)

---

**Happy Market Making!** 💰📈🎯
