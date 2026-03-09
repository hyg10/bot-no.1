"""Deep analysis of trading performance and BB filter effectiveness"""
import re
from datetime import datetime

log_file = 'logs/trading_bot.log'
with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# ── Phase 3 trades detail ──
print('=' * 60)
print('Phase 3 거래 상세 (BB필터+TP축소 적용 후)')
print('=' * 60)
for line in lines:
    s = line.strip()
    if 'Position closed' not in s:
        continue
    ts_m = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', s)
    if not ts_m or ts_m.group(1) < '2026-03-03 22:50':
        continue
    reason_m = re.search(r'Position closed \[(\w+)\]', s)
    pnl_m = re.search(r'PnL=\$([-]?[0-9.]+)', s)
    pct_m = re.search(r'\(([-+]?[0-9.]+)%\)', s)
    reason = reason_m.group(1) if reason_m else '?'
    pnl = pnl_m.group(1) if pnl_m else '?'
    pct = pct_m.group(1) if pct_m else '?'
    print(f'  {ts_m.group(1)} | {reason:15s} | ${pnl:>9s} ({pct:>6s}%)')

# ── BB filter analysis ──
print()
print('=' * 60)
print('BB필터 차단 분석 (3/4~현재)')
print('=' * 60)

bb_positions_blocked = []
bb_positions_allowed = []
for line in lines:
    s = line.strip()
    ts_m = re.match(r'\[(\d{4}-\d{2}-\d{2})', s)
    if not ts_m or ts_m.group(1) < '2026-03-04':
        continue
    bb_m = re.search(r'BB.*?=([0-9.]+)', s)
    if not bb_m:
        continue
    bb_val = float(bb_m.group(1))
    if '거부' in s:
        bb_positions_blocked.append(bb_val)
    elif '허가' in s:
        bb_positions_allowed.append(bb_val)

if bb_positions_blocked:
    print(f'차단된 BB위치 범위: {min(bb_positions_blocked):.2f} ~ {max(bb_positions_blocked):.2f}')
    print(f'차단된 BB위치 평균: {sum(bb_positions_blocked)/len(bb_positions_blocked):.2f}')
    print(f'차단 횟수: {len(bb_positions_blocked)}')
if bb_positions_allowed:
    print(f'허가된 BB위치 범위: {min(bb_positions_allowed):.2f} ~ {max(bb_positions_allowed):.2f}')
    print(f'허가된 BB위치 평균: {sum(bb_positions_allowed)/len(bb_positions_allowed):.2f}')
    print(f'허가 횟수: {len(bb_positions_allowed)}')

total = len(bb_positions_blocked) + len(bb_positions_allowed)
if total > 0:
    print(f'차단율: {len(bb_positions_blocked)/total*100:.0f}%')

# ── Idle analysis ──
print()
print('=' * 60)
print('포지션 유무 분석 (3/4~현재)')
print('=' * 60)
no_pos_cycles = 0
has_pos_cycles = 0
hold_count = 0
bb_block_when_idle = 0

for line in lines:
    s = line.strip()
    ts_m = re.match(r'\[(\d{4}-\d{2}-\d{2})', s)
    if not ts_m or ts_m.group(1) < '2026-03-04':
        continue
    if 'Hold - skipping' in s and '없음' in s:
        no_pos_cycles += 1
    if 'ExSync' in s and ('SHORT' in s or 'LONG' in s):
        has_pos_cycles += 1
    if 'RL says Hold' in s:
        hold_count += 1

total_cycles = no_pos_cycles + has_pos_cycles
if total_cycles > 0:
    print(f'포지션 보유 사이클: {has_pos_cycles}')
    print(f'포지션 미보유 사이클: {no_pos_cycles}')
    print(f'RL Hold(스킵): {hold_count}')
    print(f'유휴 비율: {no_pos_cycles/(total_cycles)*100:.0f}%')

# ── What if BB filter was looser? ──
print()
print('=' * 60)
print('BB필터 완화 시뮬레이션')
print('=' * 60)
for threshold in [0.45, 0.50, 0.55, 0.60]:
    would_allow = 0
    still_block = 0
    for line in lines:
        s = line.strip()
        ts_m = re.match(r'\[(\d{4}-\d{2}-\d{2})', s)
        if not ts_m or ts_m.group(1) < '2026-03-04':
            continue
        if '거부' not in s or 'BB' not in s:
            continue
        bb_m = re.search(r'BB.*?=([0-9.]+)', s)
        if not bb_m:
            continue
        bb_val = float(bb_m.group(1))
        if 'LONG' in s:
            if bb_val <= threshold:
                would_allow += 1
            else:
                still_block += 1
        elif 'SHORT' in s:
            if bb_val >= (1 - threshold):
                would_allow += 1
            else:
                still_block += 1
    print(f'  BB < {threshold} (LONG) / > {1-threshold:.2f} (SHORT): '
          f'추가 허용 {would_allow}건, 여전히 차단 {still_block}건')

# ── time_limit exit profit distribution ──
print()
print('=' * 60)
print('time_limit 청산 수익 분포 (Phase 3)')
print('=' * 60)
tl_profits = []
for line in lines:
    s = line.strip()
    if 'Position closed [time_limit]' not in s:
        continue
    ts_m = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', s)
    if not ts_m or ts_m.group(1) < '2026-03-03 22:50':
        continue
    pnl_m = re.search(r'PnL=\$([-]?[0-9.]+)', s)
    pct_m = re.search(r'\(([-+]?[0-9.]+)%\)', s)
    if pnl_m:
        pnl = float(pnl_m.group(1))
        pct = float(pct_m.group(1)) if pct_m else 0
        tl_profits.append((pnl, pct))

if tl_profits:
    wins = [p for p, _ in tl_profits if p > 0]
    losses = [p for p, _ in tl_profits if p <= 0]
    print(f'총 {len(tl_profits)}건: 승{len(wins)} / 패{len(losses)}')
    print(f'총 PnL: ${sum(p for p, _ in tl_profits):.4f}')
    for pnl, pct in tl_profits:
        sign = '+' if pnl >= 0 else ''
        print(f'  ${sign}{pnl:.4f} ({sign}{pct:.2f}%)')
