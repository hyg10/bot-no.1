"""Check leverage details"""
import json
from src.utils.backpack_client import BackpackClient

c = BackpackClient()
positions = c.get_open_positions()
for p in positions:
    nq = float(p.get("netQuantity", 0))
    if abs(nq) > 0:
        print(json.dumps(p, indent=2, default=str))

eq = c.get_available_equity()
print(f"\nEquity: ${eq:.2f}")

# Current BTC price
t = c.get_ticker("BTC_USDC_PERP")
price = float(t.get("lastPrice", 0))
print(f"BTC Price: ${price:.2f}")

# Position value calculation
pos_value = abs(nq) * price
print(f"\nPosition: {abs(nq)} BTC = ${pos_value:.2f}")
print(f"10x leverage margin needed: ${pos_value/10:.2f}")
print(f"20x leverage margin needed: ${pos_value/20:.2f}")
print(f"10x liquidation distance: ~{100/10:.1f}%")
print(f"20x liquidation distance: ~{100/20:.1f}%")
print(f"10x liq price (SHORT): ~${price * 1.10:.0f}")
print(f"20x liq price (SHORT): ~${price * 1.05:.0f}")
