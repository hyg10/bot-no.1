"""Quick status check — exchange positions + equity"""
from src.utils.backpack_client import BackpackClient

c = BackpackClient()
positions = c.get_open_positions()
print("=== Open Positions ===")
found = False
for p in positions:
    nq = float(p.get("netQuantity", 0))
    if abs(nq) > 0:
        found = True
        sym = p.get("symbol", "?")
        ep = p.get("entryPrice", "?")
        mp = p.get("markPrice", "?")
        pu = p.get("pnlUnrealized", "?")
        side = "LONG" if nq > 0 else "SHORT"
        print(f"  {sym} | {side} {abs(nq)} | entry={ep} mark={mp} pnl_u={pu}")
if not found:
    print("  No open positions")

eq = c.get_available_equity()
print(f"\nEquity: ${eq:.2f}")
