# 리팩토링 플레이북

트레이딩 봇의 주요 파라미터와 구조를 변경할 때 따라야 할 절차.

## 핵심 파일 맵

```
src/
├── self_improving_bot.py    # 메인 봇 루프, 진입/청산 로직, 필터 체인
├── risk_management/
│   └── risk_manager.py      # SL/TP, PnL 계산, 수수료, 포지션 관리
├── utils/
│   └── backpack_client.py   # 거래소 API, 레짐 감지 (ER, BB, ATR)
├── ml/
│   ├── trade_analyst.py     # 신뢰도 기반 사이징 (get_position_size_multiplier)
│   ├── particle_filter.py   # L3 PF 방향 예측
│   └── wyckoff_analyzer.py  # L2 Wyckoff 분석
└── config/
    └── config.py            # .env 로딩, 설정 구조체
.env                         # 런타임 설정값
```

## 파라미터 변경 시 연쇄 체크

### TP 변경 시
1. `risk_manager.py` → `open_position()` 의 `tp_dist` 수정
2. `self_improving_bot.py` → FeeFilter의 `tp_multiplier` 동일하게 수정
3. FeeFilter 비중 계산이 여전히 유효한지 확인

### SL 변경 시
1. `risk_manager.py` → `open_position()` 의 `sl_dist` 수정
2. Trailing Breakeven 로직의 ATR 배수 확인 (`_monitor_position`)
3. 최대 SL 손실 = sl_dist × MAX_POSITION_CAP ≤ 자본의 2%

### 포지션 사이즈 변경 시
1. `.env` → `STRATEGY_TRADE_SIZE` 수정
2. `self_improving_bot.py` → `MIN_ORDER_SIZE` 수정
3. `MAX_POSITION_CAP` (max_coins × 2.0) 자동 반영 확인
4. SL 최대 손실 재계산: ATR × MAX_POSITION_CAP ≤ 자본의 2%

### 레짐 임계값 변경 시
1. `backpack_client.py` → `ER_RANGING`, `ER_TRENDING`, BB 보조판단 수정
2. 최근 로그에서 ER 분포 확인 (grep으로)
3. RANGING/TRENDING 비율이 적절한지 검증 (목표: 30~50% TRENDING)

### 쿨다운/보유시간 변경 시
1. `self_improving_bot.py` → `COOLDOWN_SEC`, `MIN_HOLD_SEC` 수정
2. `_monitor_position()` → `max_hold` (time_limit) 수정
3. 하루 예상 거래 수 계산: 24h ÷ (쿨다운 + 평균보유시간)

## 리팩토링 원칙

1. **한 번에 하나만 변경** — 여러 변수를 동시에 바꾸면 효과 분석 불가
2. **변경 전 현재 성과 기록** — 변경 효과를 비교할 기준선 확보
3. **최소 24시간 관찰** — 단기 결과로 판단하지 않기
4. **수수료 비중 항상 확인** — 어떤 변경이든 수수료/수익 비율 재계산
5. **로그에 변경 이력 남기기** — 봇 시작 시 주요 파라미터 출력
