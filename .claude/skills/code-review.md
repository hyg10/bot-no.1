# 코드 검토 체크리스트

트레이딩 봇 코드 변경 시 반드시 확인해야 할 항목들.

## 사용 시점
코드 수정 후 봇 재시작 전에 이 체크리스트를 실행한다.

## 체크리스트

### 1. 수수료 일관성
- [ ] `risk_manager.py`의 `TAKER_FEE`, `ROUND_TRIP_FEE` 값이 거래소와 일치하는가 (Backpack taker=0.05%)
- [ ] `calculate_pnl()`에 수수료가 반영되어 있는가
- [ ] `self_improving_bot.py`의 FeeFilter `tp_multiplier`가 `risk_manager.py`의 `open_position()` TP와 동일한가
- [ ] 로그의 fee 표시가 정확한가

### 2. 임계값 정합성
- [ ] `ENTRY_THRESHOLD`, `FLIP_THRESHOLD` 값 확인
- [ ] `ER_RANGING`, `ER_TRENDING` 값이 `backpack_client.py`에서 일관적인가
- [ ] `COOLDOWN_SEC`, `MIN_HOLD_SEC` 값 확인
- [ ] TP multiplier: `risk_manager.py`와 `self_improving_bot.py` FeeFilter에서 동일한가
  - ranging: 0.5×ATR, trending: 1.0×ATR (현재 기준)

### 3. 포지션 사이징 안전
- [ ] `MIN_ORDER_SIZE`가 거래소 최소 주문량 이상인가 (BTC≥0.0001)
- [ ] `MAX_POSITION_CAP`이 자본 대비 안전한가 (최대 3x 레버리지 이내)
- [ ] `signal_boost` × `size_multiplier` × `wk_size_boost`가 캡을 초과하지 않는가
- [ ] `.env`의 `STRATEGY_TRADE_SIZE`와 코드 내 MIN_ORDER_SIZE가 논리적으로 맞는가

### 4. 청산 로직 완전성
- [ ] 모든 청산 경로에서 `risk_manager.close_position()` 호출하는가
- [ ] 모든 청산 경로에서 fee 로그가 출력되는가
- [ ] `hedge_manager.close_all()` 호출이 누락되지 않았는가
- [ ] `_last_trade_time`, `_position_open_time` 리셋이 되는가
- [ ] RL 학습 기록 (`engine.on_trade_completed`)이 호출되는가

### 5. 레짐/필터 체인
- [ ] Regime 감지 → Signal 점수 → BB 필터 → FeeFilter → 진입 순서가 맞는가
- [ ] RANGING일 때 진입이 완전히 차단되는가
- [ ] BB 필터 bypass 조건 (`BB_BYPASS_SCORE`)이 적절한가
- [ ] 각 필터에서 `return`으로 빠져나가는 경로가 정확한가

### 6. 동시 실행 방지
- [ ] `restart_bot.ps1`이 기존 프로세스를 완전히 종료하는가
- [ ] `start_bot.bat`의 루프가 중복 실행을 방지하는가
- [ ] 로그에 Trading loop이 1개만 시작되는가

### 7. 로그 확인
- [ ] 진입 로그에 notional, fee, est_tp가 표시되는가
- [ ] 청산 로그에 reason, PnL, fee, 누적fee가 표시되는가
- [ ] 에러 로그가 없는가 (특히 INVALID_QUANTITY, argument error)
