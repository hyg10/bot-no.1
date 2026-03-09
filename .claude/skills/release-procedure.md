# 릴리스 절차

봇 코드 수정 후 프로덕션 반영까지의 표준 절차.

## 릴리스 단계

### 1단계: 코드 변경
- 변경 파일 목록 작성
- 각 변경의 의도와 예상 효과 명시
- 코드 검토 체크리스트 (`code-review.md`) 실행

### 2단계: 사전 검증
```bash
# 문법 오류 확인
cd C:/Users/rlask/Downloads/backpack-advanced-bot-v2
python -c "from src.self_improving_bot import SelfImprovingBot; print('OK')"

# 주요 모듈 임포트 확인
python -c "from src.risk_management.risk_manager import RiskManager; print('OK')"
python -c "from src.utils.backpack_client import BackpackClient; print('OK')"
```

### 3단계: 봇 재시작
```powershell
# PowerShell에서 실행
powershell -ExecutionPolicy Bypass -File "C:/Users/rlask/Downloads/backpack-advanced-bot-v2/restart_bot.ps1"
```

### 4단계: 시작 후 즉시 확인 (15초 대기)
```bash
sleep 15 && tail -20 logs/trading_bot.log
```
확인 항목:
- [ ] "Trading loop started" 출력 (1개만)
- [ ] "State builder warmed up" 정상
- [ ] 에러/Exception 없음
- [ ] 기존 포지션 동기화 정상 ([Sync])
- [ ] 레짐 감지 정상 (ER, BB 값 출력)

### 5단계: 5분 후 확인
```bash
tail -50 logs/trading_bot.log | grep -E "\[Signal\]|\[Regime\]|\[Entry\]|\[Close\]|ERROR"
```
확인 항목:
- [ ] Signal 점수가 계산되고 있는가
- [ ] 레짐이 적절하게 TRENDING/RANGING 구분되는가
- [ ] 필터가 정상 작동하는가 (BB, FeeFilter)
- [ ] 중복 실행 없는가

### 6단계: 24시간 후 성과 확인
```bash
# 거래 기록 확인
grep "\[Close\]" logs/trading_bot.log | tail -20

# 승률 확인
grep "\[Close\]" logs/trading_bot.log | grep -c "PnL=\$-"   # 손실 건수
grep "\[Close\]" logs/trading_bot.log | grep -c "PnL=\$[0-9]" # 수익 건수

# 에러 확인
grep -i "error\|exception\|traceback" logs/trading_bot.log | tail -10

# 레짐 분포 확인
grep "RANGING" logs/trading_bot.log | wc -l
grep "TRENDING" logs/trading_bot.log | wc -l
```

## 롤백 절차

문제 발생 시:
1. 봇 즉시 중지: `powershell -Command "Stop-Process -Name python -Force"`
2. `git diff`로 변경 내역 확인
3. `git checkout -- <file>` 로 문제 파일 복원
4. 재시작: `restart_bot.ps1`

## 현재 프로덕션 파라미터 (2026-03-08 기준)

| 파라미터 | 값 | 위치 |
|---|---|---|
| STRATEGY_TRADE_SIZE | 0.001 BTC | .env |
| MIN_ORDER_SIZE (BTC) | 0.0005 | self_improving_bot.py |
| MAX_POSITION_CAP | max_coins × 2.0 | self_improving_bot.py |
| ENTRY_THRESHOLD | 2.0 | self_improving_bot.py |
| FLIP_THRESHOLD | 3.5 | self_improving_bot.py |
| COOLDOWN_SEC | 900 (15분) | self_improving_bot.py |
| MIN_HOLD_SEC | 600 (10분) | self_improving_bot.py |
| ER_RANGING | 0.18 | backpack_client.py |
| ER_TRENDING | 0.35 | backpack_client.py |
| BB 보조판단 | < 1.5 → ranging | backpack_client.py |
| SL | 1.0 × ATR | risk_manager.py |
| TP (ranging) | 0.5 × ATR | risk_manager.py |
| TP (trending) | 1.0 × ATR | risk_manager.py |
| TAKER_FEE | 0.05% | risk_manager.py |
| Flip 거래 | 비활성 (signal_exit) | self_improving_bot.py |
