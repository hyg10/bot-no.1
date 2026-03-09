# 디버깅 흐름

트레이딩 봇 문제 발생 시 원인을 빠르게 찾는 절차.

## 증상별 디버깅

### 증상 1: 봇이 거래를 안 함
```bash
# 1. 봇이 살아있는지 확인
powershell -Command "Get-Process python -ErrorAction SilentlyContinue"

# 2. 최근 로그 확인
tail -30 logs/trading_bot.log

# 3. 차단 원인 분석
# RANGING 차단?
grep "진입 보류" logs/trading_bot.log | tail -5

# 점수 불충분?
grep "불충분" logs/trading_bot.log | tail -5

# BB 필터 차단?
grep "진입 거부" logs/trading_bot.log | tail -5

# FeeFilter 차단?
grep "FeeFilter.*거부" logs/trading_bot.log | tail -5

# 쿨다운?
grep "cooldown" logs/trading_bot.log | tail -5
```

**해결 우선순위:**
1. ER 임계값 확인 → `ER_RANGING` 값이 너무 높은지
2. ENTRY_THRESHOLD 확인 → 점수 분포 대비 너무 높은지
3. BB 필터 확인 → BB_LONG_MAX, BB_SHORT_MIN 값
4. 쿨다운 확인 → COOLDOWN_SEC가 너무 긴지

### 증상 2: 계속 손실만 남
```bash
# 1. 최근 거래 PnL 확인
grep "\[Close\]" logs/trading_bot.log | tail -20

# 2. 청산 사유 분포
grep "\[Close\]" logs/trading_bot.log | grep -o "reason=[a-z_]*" | sort | uniq -c | sort -rn

# 3. 수수료 vs 수익
grep "fee=" logs/trading_bot.log | tail -10

# 4. SL 손실 확인
grep "stop_loss" logs/trading_bot.log | tail -5

# 5. TP 도달 확인
grep "take_profit" logs/trading_bot.log | tail -5
```

**해결 우선순위:**
1. flip/signal_exit 비중 높으면 → 임계값 상향 또는 flip 로직 확인
2. SL 손실 크면 → ATR × SL 배수 줄이기 또는 TrailBE 확인
3. TP 안 맞으면 → TP 배수 낮추기
4. 수수료 비중 높으면 → 포지션 사이즈 키우기 또는 Limit Order

### 증상 3: 봇이 크래시/재시작 반복
```bash
# 1. 에러 확인
grep -i "error\|exception\|traceback" logs/trading_bot.log | tail -20

# 2. 주요 에러 패턴
grep "INVALID_QUANTITY" logs/trading_bot.log | tail -5       # 수량 오류
grep "argument" logs/trading_bot.log | tail -5               # 함수 인자 오류
grep "ConnectionError\|Timeout" logs/trading_bot.log | tail -5 # 네트워크
grep "KeyError\|TypeError" logs/trading_bot.log | tail -5    # 코드 버그

# 3. 시작 시각 확인 (잦은 재시작?)
grep "Trading loop started" logs/trading_bot.log | tail -10
```

**해결 우선순위:**
1. INVALID_QUANTITY → 수량 포맷 확인 (`_fmt_qty`), 소수점 자릿수
2. 함수 인자 → 최근 코드 변경에서 함수 시그니처 변경 여부
3. 네트워크 → 인터넷 연결, API 상태 확인
4. 잦은 재시작 → start_bot.bat 루프가 10초마다 재시작

### 증상 4: 포지션 동기화 문제
```bash
# 거래소 vs 내부 트래커 불일치
grep "\[Sync\]" logs/trading_bot.log | tail -5
grep "\[ExSync\]" logs/trading_bot.log | tail -5
grep "Already" logs/trading_bot.log | tail -5
```

**해결 우선순위:**
1. 봇 재시작 시 기존 포지션 복원 확인 → [Sync] 로그
2. 내부 트래커에 없는 포지션 → SYNC_MAX_HOLD 시간 초과 시 자동 청산
3. 중복 포지션 → 같은 방향 "Already ... skipping" 확인

## 일일 점검 명령어

```bash
# 오늘 거래 수
grep "$(date +%Y-%m-%d)" logs/trading_bot.log | grep -c "\[Close\]"

# 오늘 PnL 합계 (수동 계산 필요)
grep "$(date +%Y-%m-%d)" logs/trading_bot.log | grep "\[Close\]"

# 오늘 레짐 분포
echo "RANGING:" && grep "$(date +%Y-%m-%d)" logs/trading_bot.log | grep -c "진입 보류"
echo "TRENDING:" && grep "$(date +%Y-%m-%d)" logs/trading_bot.log | grep -c "TRENDING"

# 에러 유무
grep "$(date +%Y-%m-%d)" logs/trading_bot.log | grep -ci "error\|exception"

# 현재 포지션
tail -100 logs/trading_bot.log | grep "\[Sync\]\|\[ExSync\]\|\[Entry\]\|\[Close\]" | tail -5
```

## 핵심 로그 태그 사전

| 태그 | 의미 |
|---|---|
| `[L0·Regime]` | 레짐 감지 결과 (ER, ATR, BB) |
| `[Regime]` | 횡보장 진입 보류 |
| `[Signal]` | 합산 점수 및 판정 |
| `[BB필터]` | 볼린저밴드 필터 결과 |
| `[FeeFilter]` | 수수료 필터 결과 |
| `[Entry]` | 신규 포지션 진입 |
| `[Close]` | 포지션 청산 (PnL, fee) |
| `[Signal Exit]` | 반대 신호 청산 (구 flip) |
| `[Sizing]` | 신호 강도 배수 |
| `[Wyckoff]` | 거래량 확인 배수 |
| `[Safety]` | 포지션 캡 제한 |
| `[MinHold]` | 최소 보유시간 미달 |
| `[Sync]` | 시작 시 포지션 동기화 |
| `[ExSync]` | 사이클 내 포지션 확인 |
