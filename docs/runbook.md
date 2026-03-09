# 운영 런북

트레이딩 봇 일상 운영, 장애 대응, 성과 분석 절차.

---

## 1. 일상 운영

### 1.1 봇 시작
```powershell
# 깨끗한 시작 (기존 프로세스 종료 후 시작)
powershell -ExecutionPolicy Bypass -File restart_bot.ps1
```

### 1.2 봇 상태 확인
```bash
# 프로세스 확인
powershell -Command "Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, StartTime"

# 최근 로그
tail -20 logs/trading_bot.log

# 현재 포지션
tail -100 logs/trading_bot.log | grep "\[Sync\]\|\[ExSync\]\|\[Entry\]\|\[Close\]" | tail -5
```

### 1.3 봇 중지
```powershell
Stop-Process -Name python -Force
```

### 1.4 Windows 자동 시작
- 시작 프로그램 폴더에 바로가기 등록됨
- `start_bot.bat` 실행 → 크래시 시 10초 후 자동 재시작

---

## 2. 일일 성과 분석

### 2.1 오늘의 거래 요약
```bash
DATE=$(date +%Y-%m-%d)

echo "=== 오늘의 거래 ==="
grep "$DATE" logs/trading_bot.log | grep "\[Close\]"

echo "=== 거래 수 ==="
grep "$DATE" logs/trading_bot.log | grep -c "\[Close\]"

echo "=== 승/패 ==="
echo -n "WIN: "; grep "$DATE" logs/trading_bot.log | grep "\[Close\]" | grep "PnL=\$[0-9]" | grep -cv "PnL=\$-"
echo -n "LOSS: "; grep "$DATE" logs/trading_bot.log | grep "\[Close\]" | grep -c "PnL=\$-"

echo "=== 청산 사유 ==="
grep "$DATE" logs/trading_bot.log | grep "\[Close\]" | grep -o "reason=[a-z_]*" | sort | uniq -c | sort -rn

echo "=== 레짐 분포 ==="
echo -n "RANGING 차단: "; grep "$DATE" logs/trading_bot.log | grep -c "진입 보류"
echo -n "TRENDING: "; grep "$DATE" logs/trading_bot.log | grep -c "TRENDING"
```

### 2.2 주간 성과 비교
```bash
echo "=== 일별 거래 수 ==="
for i in $(seq 0 6); do
  D=$(date -d "-${i} days" +%Y-%m-%d 2>/dev/null || date -v-${i}d +%Y-%m-%d)
  COUNT=$(grep "$D" logs/trading_bot.log | grep -c "\[Close\]")
  echo "$D: $COUNT 건"
done
```

### 2.3 확인해야 할 지표
| 지표 | 목표 | 위험 신호 |
|---|---|---|
| 일 거래 수 | 3~8건 | > 15건 (과다거래), 0건 (필터 과다) |
| 승률 | > 45% | < 35% |
| TP 도달 | > 10% | 0% (TP 너무 높음) |
| SL 도달 | < 20% | > 30% (SL 너무 좁음) |
| 수수료 비중 | < 30% | > 50% (사이즈 너무 작음) |
| RANGING 비율 | 20~40% | > 70% (ER 임계값 너무 높음) |

---

## 3. 장애 대응

### 3.1 봇 응답 없음
```bash
# 1. 프로세스 확인
powershell -Command "Get-Process python"

# 2. 로그 마지막 시간 확인
tail -1 logs/trading_bot.log

# 3. 재시작
powershell -ExecutionPolicy Bypass -File restart_bot.ps1

# 4. 포지션 확인 (거래소에 남아있을 수 있음)
tail -20 logs/trading_bot.log | grep "\[Sync\]"
```

### 3.2 거래소 API 오류
```bash
grep -i "error\|timeout\|connection" logs/trading_bot.log | tail -10
```
- `ConnectionError`: 인터넷 확인
- `INVALID_QUANTITY`: 수량 포맷 오류 → `_fmt_qty()` 확인
- `RATE_LIMIT`: API 호출 빈도 초과 → STRATEGY_MIN_INTERVAL 증가

### 3.3 비정상 손실 발생
```bash
# 최근 큰 손실 확인
grep "\[Close\]" logs/trading_bot.log | grep "PnL=\$-" | sort -t= -k3 -n | head -5

# SL 연속 발동 확인
grep "stop_loss" logs/trading_bot.log | tail -10
```
대응:
1. 즉시 봇 중지: `Stop-Process -Name python -Force`
2. 거래소에서 열린 포지션 수동 확인
3. 원인 분석 후 재시작

### 3.4 중복 실행
```bash
powershell -Command "Get-Process python | Select-Object Id, StartTime"
```
프로세스가 2개 이상이면:
```powershell
# 전부 종료 후 깨끗하게 재시작
Stop-Process -Name python -Force
Start-Sleep 3
powershell -ExecutionPolicy Bypass -File restart_bot.ps1
```

---

## 4. 파라미터 변경 절차

### 4.1 빈도 조절 (거래가 너무 많거나 적을 때)

**거래가 너무 많으면 (> 15건/일):**
- `COOLDOWN_SEC` 증가 (현재 900 → 1200)
- `ENTRY_THRESHOLD` 증가 (현재 2.0 → 2.5)

**거래가 너무 적으면 (< 2건/일):**
- `ER_RANGING` 감소 (현재 0.18 → 0.15)
- `ENTRY_THRESHOLD` 감소 (현재 2.0 → 1.5)
- `BB_BYPASS_SCORE` 감소 (현재 3.0 → 2.5)

### 4.2 수익성 조절

**TP가 안 맞으면:**
- Ranging TP 배수 감소 (현재 0.5 → 0.4)
- Trending TP 배수 감소 (현재 1.0 → 0.8)
- ⚠️ 수정 위치 2곳: `risk_manager.py` + `self_improving_bot.py` FeeFilter

**SL이 너무 자주 맞으면:**
- SL 배수 증가 (현재 1.0 → 1.2 ATR)
- Trailing BE 활성화 임계값 확인

**수수료가 너무 크면:**
- `STRATEGY_TRADE_SIZE` 증가
- Limit Order 전환 고려 (maker 0.02%)
- 거래 빈도 줄이기

### 4.3 변경 후 체크
1. `.claude/skills/code-review.md` 체크리스트 실행
2. 봇 재시작: `restart_bot.ps1`
3. 15초 후 로그 확인
4. 24시간 후 성과 비교

---

## 5. 로그 관리

### 5.1 로그 파일 위치
```
logs/trading_bot.log     # 메인 로그 (무제한 증가)
```

### 5.2 로그 크기 확인
```bash
wc -l logs/trading_bot.log           # 줄 수
ls -lh logs/trading_bot.log          # 파일 크기
```

### 5.3 로그 백업/정리
```bash
# 백업
cp logs/trading_bot.log logs/trading_bot_$(date +%Y%m%d).log

# 정리 (최근 5000줄만 유지)
tail -5000 logs/trading_bot.log > logs/trading_bot.tmp
mv logs/trading_bot.tmp logs/trading_bot.log
```

---

## 6. 현재 운영 파라미터

**2026-03-08 기준:**

| 카테고리 | 파라미터 | 값 |
|---|---|---|
| **거래소** | 환경 | devnet |
| | 심볼 | BTC_USDC_PERP |
| | 레버리지 | 5x |
| | 수수료 | Taker 0.05% |
| **사이징** | 기본 사이즈 | 0.001 BTC |
| | 최소 | 0.0005 BTC |
| | 최대 캡 | 0.002 BTC |
| **진입** | ENTRY_THRESHOLD | 2.0 |
| | COOLDOWN | 900s (15분) |
| | MIN_HOLD | 600s (10분) |
| **레짐** | ER_RANGING | 0.18 |
| | ER_TRENDING | 0.35 |
| | BB 보조 | < 1.5% → ranging |
| **SL/TP** | SL | 1.0 × ATR |
| | TP (ranging) | 0.5 × ATR |
| | TP (trending) | 1.0 × ATR |
| | Time Limit | 30분 / 40분 |
| **필터** | BB_BYPASS_SCORE | 3.0 |
| | FeeFilter 비중 | > 50% 차단 |
| | Flip | 비활성 (signal_exit) |
