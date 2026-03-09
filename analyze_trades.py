"""Analyze overnight trading performance from log file"""
import re

log_path = "logs/trading_bot.log"

with open(log_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find all trade-related events
fills = []       # position opened
closes = []      # position closed
monitors = []    # monitor logs
errors = []      # errors
restarts = []    # bot restarts
equity_log = []  # equity changes

for line in lines:
    line = line.strip()

    # Position fills (entries)
    if "filled" in line and ("SHORT" in line or "LONG" in line):
        fills.append(line)

    # Position closes
    if "Position closed" in line:
        closes.append(line)

    # Close logs (new format with _fmt_qty fix)
    if "[Close]" in line:
        closes.append(line)

    # Monitor logs
    if "[Monitor]" in line:
        monitors.append(line)

    # Errors
    if "ERROR" in line:
        errors.append(line)

    # Bot restarts
    if "Self-Improving Trading Bot" in line:
        restarts.append(line)

    # Equity
    m = re.search(r"Available [Ee]quity.*?\$(\d+\.?\d*)", line)
    if m:
        equity_log.append((line[:25], float(m.group(1))))

    # Available Equity (netEquityAvailable)
    m2 = re.search(r"netEquityAvailable.*?\$(\d+\.?\d*)", line)
    if m2:
        equity_log.append((line[:25], float(m2.group(1))))

# PnL from closes
pnls = []
for c in closes:
    m = re.search(r"PnL=\$(-?\d+\.?\d*)", c)
    if m:
        pnls.append(float(m.group(1)))

print("=" * 60)
print("  OVERNIGHT TRADING ANALYSIS")
print("=" * 60)

print(f"\n--- Bot Restarts ({len(restarts)}) ---")
for r in restarts:
    print(f"  {r[:25]}")

print(f"\n--- Trade Entries ({len(fills)}) ---")
for f_line in fills:
    print(f"  {f_line}")

print(f"\n--- Trade Closes ({len(closes)}) ---")
for c in closes:
    print(f"  {c}")

print(f"\n--- PnL Summary ---")
if pnls:
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    print(f"  Total trades closed: {len(pnls)}")
    print(f"  Wins:   {len(wins)} ({len(wins)/len(pnls)*100:.0f}%)")
    print(f"  Losses: {len(losses)} ({len(losses)/len(pnls)*100:.0f}%)")
    print(f"  Total PnL: ${sum(pnls):.4f}")
    if wins:
        print(f"  Avg Win:  ${sum(wins)/len(wins):.4f}")
    if losses:
        print(f"  Avg Loss: ${sum(losses)/len(losses):.4f}")
else:
    print("  No closed trades with PnL data found")

print(f"\n--- Equity Timeline ---")
if equity_log:
    print(f"  First: {equity_log[0][0]} → ${equity_log[0][1]:.2f}")
    print(f"  Last:  {equity_log[-1][0]} → ${equity_log[-1][1]:.2f}")
    print(f"  Change: ${equity_log[-1][1] - equity_log[0][1]:+.2f}")

print(f"\n--- Errors ({len(errors)}) ---")
for e in errors[-10:]:  # last 10 errors
    print(f"  {e}")

print(f"\n--- Monitor Logs ({len(monitors)}) ---")
for m in monitors[-5:]:
    print(f"  {m}")

print("=" * 60)
