"""Phase-by-phase trade analysis"""
import re

log_file = 'logs/trading_bot.log'
with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

trades = []
for line in lines:
    s = line.strip()
    if 'Position closed' not in s:
        continue
    ts_m = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', s)
    ts = ts_m.group(1) if ts_m else '?'
    reason_m = re.search(r'Position closed \[(\w+)\]', s)
    reason = reason_m.group(1) if reason_m else '?'
    pnl_m = re.search(r'PnL=\$([-]?[0-9.]+)', s)
    if not pnl_m:
        continue
    pnl = float(pnl_m.group(1))
    trades.append({'ts': ts, 'reason': reason, 'pnl': pnl})

# Phase splits
phase1, phase2, phase3 = [], [], []
for t in trades:
    if t['ts'] < '2026-03-02 22:00':
        phase1.append(t)
    elif t['ts'] < '2026-03-03 22:50':
        phase2.append(t)
    else:
        phase3.append(t)

def print_phase(name, tlist):
    if not tlist:
        print(f'{name}: 거래 없음')
        print()
        return
    wins = [t for t in tlist if t['pnl'] > 0]
    losses = [t for t in tlist if t['pnl'] <= 0]
    total_pnl = sum(t['pnl'] for t in tlist)
    wr = len(wins) / len(tlist) * 100
    print(f'{name}:')
    print(f'  거래 수: {len(tlist)} (승{len(wins)}/패{len(losses)})')
    print(f'  승률: {wr:.0f}%')
    print(f'  총 PnL: ${total_pnl:.4f}')
    if wins:
        print(f'  평균 수익: ${sum(t["pnl"] for t in wins)/len(wins):.4f}')
    if losses:
        print(f'  평균 손실: ${sum(t["pnl"] for t in losses)/len(losses):.4f}')
    reasons = {}
    for t in tlist:
        r = t['reason']
        if r not in reasons:
            reasons[r] = {'count': 0, 'pnl': 0}
        reasons[r]['count'] += 1
        reasons[r]['pnl'] += t['pnl']
    print(f'  청산사유:')
    for r, v in sorted(reasons.items(), key=lambda x: -x[1]['count']):
        print(f'    {r}: {v["count"]}건, PnL=${v["pnl"]:.4f}')
    print()

print('=' * 60)
print('전체 거래 분석 (3일간)')
print('=' * 60)
print()
print_phase('Phase 1: 플립플롭 시기 (3/1~3/2 22시)', phase1)
print_phase('Phase 2: 히스테리시스 적용 후 (3/2 22시~3/3 22:50)', phase2)
print_phase('Phase 3: BB필터+TP축소 적용 후 (3/3 22:50~현재)', phase3)

print('=' * 60)
all_pnl = sum(t['pnl'] for t in trades)
all_wins = [t for t in trades if t['pnl'] > 0]
print(f'전체 총합: {len(trades)}건, 승률 {len(all_wins)/len(trades)*100:.0f}%, PnL=${all_pnl:.4f}')
print()
print('최근 5건:')
for t in trades[-5:]:
    sign = '+' if t['pnl'] >= 0 else ''
    print(f'  {t["ts"]} | {t["reason"]:15s} | {sign}${t["pnl"]:.4f}')

# BB filter stats
bb_blocks = sum(1 for l in lines if 'BB필터' in l and '거부' in l)
regime_blocks = sum(1 for l in lines if '횡보장 감지' in l)
flip_holds = sum(1 for l in lines if '유지' in l and 'FLIP' in l)
print()
print('--- 필터 효과 ---')
print(f'BB필터 차단: {bb_blocks}회 (나쁜 타이밍 진입 방지)')
print(f'횡보장 차단: {regime_blocks}회')
print(f'FLIP 점수부족 유지: {flip_holds}회 (불필요한 방향전환 방지)')

# Equity
print()
print('--- 자산 추이 ---')
equity_lines = [(l.strip()) for l in lines if 'Available Equity' in l or 'Available equity' in l]
if equity_lines:
    first = equity_lines[0]
    last = equity_lines[-1]
    eq_first = re.search(r'\$([\d.]+)', first)
    eq_last = re.search(r'\$([\d.]+)', last)
    if eq_first and eq_last:
        e1 = float(eq_first.group(1))
        e2 = float(eq_last.group(1))
        print(f'  시작 자산: ${e1:.2f}')
        print(f'  현재 자산: ${e2:.2f}')
        print(f'  변동: ${e2-e1:+.2f} ({(e2-e1)/e1*100:+.2f}%)')
