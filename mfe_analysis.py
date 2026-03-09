#!/usr/bin/env python3
"""MFE/MAE analysis of trades from trading_bot.log for 3/8 and 3/9."""
import re

logfile = 'logs/trading_bot.log'

with open(logfile, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# DEBUG: test matching on known line
test_line = lines[51075]  # line 51076 (0-indexed)
print(f"DEBUG test line: {test_line[:100]}")
m_test = re.search(r'\[Entry\]', test_line)
print(f"DEBUG [Entry] match: {m_test}")
m_test2 = re.search(r'\[Entry\] (SHORT|LONG)', test_line)
print(f"DEBUG direction match: {m_test2}")
if m_test2:
    print(f"DEBUG groups: {m_test2.groups()}")
# Test the dollar sign
dollar_pat = re.compile(r'\$ *([\d.]+)')
m_dollar = dollar_pat.search(test_line)
print(f"DEBUG dollar match: {m_dollar}")
if m_dollar:
    print(f"DEBUG dollar groups: {m_dollar.groups()}")
# Full pattern test
full_pat = re.compile(r'\[Entry\] (SHORT|LONG) ([\d.]+) \S+ @ \$([\d.]+)')
m_full = full_pat.search(test_line)
print(f"DEBUG full pattern match: {m_full}")
if m_full:
    print(f"DEBUG full groups: {m_full.groups()}")
# Check char by char around $
idx = test_line.find('$')
if idx >= 0:
    print(f"DEBUG chars around $: {repr(test_line[idx-2:idx+10])}")
print()

# Build trade pairs: each Entry matched with its Close
trades = []
current_entry = None
entry_count = 0
close_count = 0

for i, line in enumerate(lines):
    lineno = i + 1

    # Entry line
    m_entry = re.search(r'\[Entry\] (SHORT|LONG) ([\d.]+) \S+ @ \$([\d.]+)', line)
    if m_entry:
        entry_count += 1
        if entry_count <= 3:
            print(f"DEBUG found entry at line {lineno}: {m_entry.groups()}")
        dt_m = re.search(r'\[([\d-]+ [\d:]+)\]', line)
        current_entry = {
            'entry_lineno': lineno,
            'entry_time': dt_m.group(1) if dt_m else '',
            'direction': m_entry.group(1),
            'qty': float(m_entry.group(2)),
            'entry_price': float(m_entry.group(3)),
            'monitors': [],
            'sl_price': None,
            'tp_price': None,
            'atr': None,
            'trail_updates': [],
            'closes': [],
        }

    # Filled line with SL/TP/ATR (follows Entry)
    if current_entry and current_entry.get('atr') is None:
        m_filled = re.search(r'(SHORT|LONG) filled \| SL=\$([\d.]+)\(([\d.]+)%\) TP=\$([\d.]+)\(([\d.]+)%\) \| ATR=\$([\d]+)', line)
        if m_filled:
            current_entry['sl_price'] = float(m_filled.group(2))
            current_entry['sl_pct'] = float(m_filled.group(3))
            current_entry['tp_price'] = float(m_filled.group(4))
            current_entry['tp_pct'] = float(m_filled.group(5))
            current_entry['atr'] = float(m_filled.group(6))

    # Monitor lines with price data
    if current_entry:
        m_mon = re.search(
            r'\[Monitor\] (\d+)s/(\d+)s \| \$([\d.]+) \| '
            r'PnL=\$([-\d.]+)\(([-+\d.]+)%\) \| '
            r'SL까지 ([\d.]+)% TP까지 ([\d.]+)% \| 남은 (\d+)s',
            line
        )
        if m_mon:
            current_entry['monitors'].append({
                'elapsed': int(m_mon.group(1)),
                'price': float(m_mon.group(3)),
                'pnl_pct': float(m_mon.group(5)),
                'sl_dist_pct': float(m_mon.group(6)),
                'tp_dist_pct': float(m_mon.group(7)),
            })

        # Trailing SL updates
        m_trail = re.search(r'\[TrailBE\].*SL.*\$([\d.]+)', line)
        if m_trail:
            current_entry['trail_updates'].append(float(m_trail.group(1)))

    # Close line - note space between PnL amount and (pct%)
    m_close = re.search(
        r'\[Close\] (SHORT|LONG) ([\d.]+) \S+ @ \$([\d.]+) \| '
        r'reason=(\w+) \| PnL=\$([-\d.]+) ?\(([-+\d.]+)%\)',
        line
    )
    if m_close and current_entry:
        if m_close.group(1) == current_entry['direction']:
            dt_m = re.search(r'\[([\d-]+ [\d:]+)\]', line)
            close_info = {
                'close_lineno': lineno,
                'close_time': dt_m.group(1) if dt_m else '',
                'exit_price': float(m_close.group(3)),
                'reason': m_close.group(4),
                'pnl_dollar': float(m_close.group(5)),
                'pnl_pct': float(m_close.group(6)),
                'exit_qty': float(m_close.group(2)),
            }
            current_entry['closes'].append(close_info)

            # Check if all qty closed
            total_closed = sum(
                c['exit_qty'] for c in current_entry['closes']
            )
            close_count += 1
            if close_count <= 5:
                print(
                    f"DEBUG close at line {lineno}: "
                    f"qty_closed={total_closed:.4f} "
                    f"of {current_entry['qty']:.4f} "
                    f"reason={close_info['reason']}"
                )
            if total_closed >= current_entry['qty'] - 0.00005:
                # Store trade
                if close_count <= 5:
                    print(f"DEBUG -> trade completed, storing")
                trades.append(current_entry)
                current_entry = None

# Filter for 3/8 and 3/9 trades
trades_filtered = [t for t in trades
                   if t['entry_time'].startswith('2026-03-08')
                   or t['entry_time'].startswith('2026-03-09')]

print(f"Total trades with [Entry] tags: {len(trades)}")
print(f"Trades on 3/8 and 3/9: {len(trades_filtered)}")
print()

all_results = []

for idx, t in enumerate(trades_filtered):
    direction = t['direction']
    entry_p = t['entry_price']
    atr = t['atr']
    monitors = t['monitors']

    # Use last close for exit info
    last_close = t['closes'][-1]
    exit_p = last_close['exit_price']
    reason = last_close['reason']
    pnl_pct = last_close['pnl_pct']
    pnl_dollar = last_close['pnl_dollar']
    exit_qty = last_close['exit_qty']

    # Total qty closed
    total_qty = sum(c['exit_qty'] for c in t['closes'])

    print(f"{'='*80}")
    print(f"TRADE #{idx+1}: {direction} @ ${entry_p:.2f}")
    print(f"  Entry: {t['entry_time']} (line {t['entry_lineno']})")
    for ci, c in enumerate(t['closes']):
        print(f"  Close {ci+1}: {c['close_time']} (line {c['close_lineno']}) "
              f"@ ${c['exit_price']:.2f} | {c['reason']} | qty={c['exit_qty']} | PnL=${c['pnl_dollar']} ({c['pnl_pct']}%)")
    print(f"  Total qty closed: {total_qty} (of {t['qty']})")
    print(f"  SL: ${t['sl_price']} ({t.get('sl_pct','?')}%) | TP: ${t['tp_price']} ({t.get('tp_pct','?')}%)")
    print(f"  ATR: ${atr}")
    if t['trail_updates']:
        print(f"  Trailing BE updates: SL moved to {t['trail_updates']}")
    print(f"  Monitor data points: {len(monitors)}")

    if not monitors:
        print(f"  ** NO MONITOR DATA - SKIPPING MFE/MAE **")
        print()
        continue

    prices = [m['price'] for m in monitors]
    elapsed_times = [m['elapsed'] for m in monitors]

    if direction == 'LONG':
        max_price = max(prices)
        min_price = min(prices)
        mfe_dollar = max_price - entry_p
        mae_dollar = entry_p - min_price
        mfe_price = max_price
        mae_price = min_price
        mfe_time = elapsed_times[prices.index(max_price)]
        mae_time = elapsed_times[prices.index(min_price)]
    else:  # SHORT
        max_price = max(prices)
        min_price = min(prices)
        mfe_dollar = entry_p - min_price
        mae_dollar = max_price - entry_p
        mfe_price = min_price
        mae_price = max_price
        mfe_time = elapsed_times[prices.index(min_price)]
        mae_time = elapsed_times[prices.index(max_price)]

    mfe_pct = (mfe_dollar / entry_p) * 100
    mae_pct = (mae_dollar / entry_p) * 100

    mfe_atr = mfe_dollar / atr if atr else 0
    mae_atr = mae_dollar / atr if atr else 0

    print(f"  Price range in monitors: ${min_price:.2f} - ${max_price:.2f}")
    print(f"  MFE: ${mfe_dollar:.2f} ({mfe_pct:.3f}%) = {mfe_atr:.3f}x ATR "
          f"@ {mfe_time}s after entry (price=${mfe_price:.2f})")
    print(f"  MAE: ${mae_dollar:.2f} ({mae_pct:.3f}%) = {mae_atr:.3f}x ATR "
          f"@ {mae_time}s after entry (price=${mae_price:.2f})")

    # ATR threshold checks
    if atr and atr > 0:
        for th in [0.3, 0.5, 1.0, 1.5]:
            target_move = th * atr
            reached = mfe_dollar >= target_move
            # Find the time when it was first reached
            first_time = None
            for m in monitors:
                p = m['price']
                if direction == 'LONG':
                    move = p - entry_p
                else:
                    move = entry_p - p
                if move >= target_move:
                    first_time = m['elapsed']
                    break
            time_str = f" (first at {first_time}s)" if first_time else ""
            print(f"  {th}x ATR (${target_move:.2f}): "
                  f"{'YES' if reached else 'NO'}{time_str}")

    # What if we exited at MFE?
    notional = total_qty * entry_p
    fee_roundtrip = notional * 0.001  # 0.10% round-trip
    mfe_gross_pnl = mfe_dollar * total_qty
    mfe_net_pnl = mfe_gross_pnl - fee_roundtrip
    print(f"  If exited at MFE: gross=${mfe_gross_pnl:.4f}, "
          f"fee=${fee_roundtrip:.4f}, net=${mfe_net_pnl:.4f}")

    # Optimal TP level
    if atr and atr > 0:
        optimal_tp = mfe_dollar / atr
        print(f"  Optimal TP to capture MFE: {optimal_tp:.3f}x ATR")

    result = {
        'trade_num': idx + 1,
        'direction': direction,
        'entry_price': entry_p,
        'exit_price': exit_p,
        'reason': reason,
        'atr': atr,
        'mfe_dollar': mfe_dollar,
        'mfe_pct': mfe_pct,
        'mfe_atr': mfe_atr,
        'mfe_time': mfe_time,
        'mae_dollar': mae_dollar,
        'mae_atr': mae_atr,
        'total_qty': total_qty,
        'pnl_dollar': sum(c['pnl_dollar'] for c in t['closes']),
        'pnl_pct': pnl_pct,  # last close pct
        'has_monitors': True,
    }
    all_results.append(result)
    print()

# ============================================================
# SUMMARY
# ============================================================
print("=" * 80)
print("SUMMARY STATISTICS")
print("=" * 80)

results_with_data = [r for r in all_results if r['has_monitors']]
tl_trades = [r for r in results_with_data if r['reason'] == 'time_limit']
sl_trades = [r for r in results_with_data if r['reason'] == 'stop_loss']
tp_trades = [r for r in results_with_data if r['reason'] == 'take_profit']

print(f"\nTotal trades with monitor data: {len(results_with_data)}")
print(f"  time_limit: {len(tl_trades)}")
print(f"  stop_loss: {len(sl_trades)}")
print(f"  take_profit: {len(tp_trades)}")

print(f"\n--- TIME_LIMIT trades ({len(tl_trades)}) ---")
for th in [0.3, 0.5, 1.0, 1.5]:
    count = sum(1 for r in tl_trades if r['mfe_atr'] >= th)
    pct = (count / len(tl_trades) * 100) if tl_trades else 0
    print(f"  MFE >= {th}x ATR: {count}/{len(tl_trades)} ({pct:.1f}%)")

print(f"\n--- STOP_LOSS trades ({len(sl_trades)}) ---")
for th in [0.3, 0.5, 1.0, 1.5]:
    count = sum(1 for r in sl_trades if r['mfe_atr'] >= th)
    pct = (count / len(sl_trades) * 100) if sl_trades else 0
    print(f"  MFE >= {th}x ATR before SL: {count}/{len(sl_trades)} ({pct:.1f}%)")

print(f"\n--- ALL trades ({len(results_with_data)}) ---")
for th in [0.3, 0.5, 1.0, 1.5]:
    count = sum(1 for r in results_with_data if r['mfe_atr'] >= th)
    pct = (count / len(results_with_data) * 100) if results_with_data else 0
    print(f"  MFE >= {th}x ATR: {count}/{len(results_with_data)} ({pct:.1f}%)")

if results_with_data:
    avg_mfe_atr = sum(r['mfe_atr'] for r in results_with_data) / len(results_with_data)
    avg_mfe_dollar = sum(r['mfe_dollar'] for r in results_with_data) / len(results_with_data)
    avg_mae_atr = sum(r['mae_atr'] for r in results_with_data) / len(results_with_data)
    print(f"\n  Average MFE: {avg_mfe_atr:.3f}x ATR (${avg_mfe_dollar:.2f})")
    print(f"  Average MAE: {avg_mae_atr:.3f}x ATR")

# What % of trades profitable with different TP levels
print(f"\n--- Profitability simulation with different TP levels ---")
for tp_mult in [0.3, 0.5, 0.7, 1.0]:
    profitable = 0
    total = len(results_with_data)
    total_pnl = 0.0
    for r in results_with_data:
        atr_val = r['atr']
        tp_target = tp_mult * atr_val
        notional = r['total_qty'] * r['entry_price']
        fee = notional * 0.001  # 0.10% round trip
        if r['mfe_atr'] >= tp_mult:
            # Would have hit TP
            gross = tp_target * r['total_qty']
            net = gross - fee
            total_pnl += net
            if net > 0:
                profitable += 1
        else:
            # Would NOT have hit TP - use actual outcome
            total_pnl += r['pnl_dollar']
            if r['pnl_dollar'] > 0:
                profitable += 1

    pct = (profitable / total * 100) if total else 0
    print(f"  TP at {tp_mult}x ATR: {profitable}/{total} profitable ({pct:.1f}%), "
          f"total PnL=${total_pnl:.4f}")
