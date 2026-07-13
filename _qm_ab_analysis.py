"""
QM A/B Analysis - 1-Month Forward Checkpoint
Compares BASE (standard QM) vs Fix D (-0.5R fast loss cut) paper variants.

Run: venv\Scripts\python.exe _qm_ab_analysis.py

Expected JSONL files:
  logs/qm_paper_trades.jsonl      (BASE variant)
  logs/qm_fixd_paper_trades.jsonl (Fix D variant)

Supported JSONL formats:

  Event-based (multiple lines per position):
    {"type":"entry","pos_id":"xxx","bar_t":"2026-01-01T09:30:00","direction":"long",
     "entry_px":50000.0,"sl_px":49500.0,"risk_usd":5.0,"shared_entry_gate":true}
    {"type":"exit","pos_id":"xxx","exit_px":51000.0,"exit_reason":"ma20","frac":1.0,
     "net_usd":4.8,"mfe_r":2.1,"mae_r":-0.2,"hold_days":2.5}

  Flat single-line (one trade per line, already closed):
    {"pos_id":"xxx","bar_t":"2026-01-01T09:30:00","direction":"long",
     "entry_px":50000.0,"sl_px":49500.0,"exit_px":51000.0,"exit_reason":"ma20",
     "realized_r":1.0,"mfe_r":2.1,"mae_r":-0.2,"hold_days":2.5,
     "net_usd":4.8,"shared_entry_gate":true}

Output: QM_AB_REPORT_1MO.md
"""

import json
import os
import sys
from collections import defaultdict

BASE_JSONL  = os.path.join("logs", "qm_paper_trades.jsonl")
FIXD_JSONL  = os.path.join("logs", "qm_fixd_paper_trades.jsonl")
REPORT_PATH = "QM_AB_REPORT_1MO.md"

CAT_ORDER = ["WIN_RUNNER", "GAVE_BACK", "WIN_SMALL", "SHOOT_LOSS", "SL_FAST", "CHOP_LOSS"]


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_jsonl(path):
    """Load JSONL. Returns list of dicts, or None if file missing."""
    if not os.path.exists(path):
        print(f"[MISSING] {path}")
        return None
    events = []
    bad = 0
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                bad += 1
                print(f"[WARN] {path}:{lineno} bad JSON ({exc}), skipped")
    label = os.path.basename(path)
    print(f"[INFO] {label}: {len(events)} events, {bad} bad lines")
    return events


# ---------------------------------------------------------------------------
# Trade reconstruction
# ---------------------------------------------------------------------------

def _is_flat(events):
    """True if every record is a complete trade (no 'type' field needed)."""
    if not events:
        return True
    first = events[0]
    return "realized_r" in first or (
        "entry_px" in first and "exit_px" in first and "type" not in first
    )


def _fv(ev, *keys, default=0.0):
    """Get first matching key as float."""
    for k in keys:
        if k in ev:
            try:
                return float(ev[k])
            except (TypeError, ValueError):
                pass
    return default


def _sv(ev, *keys, default=""):
    """Get first matching key as str."""
    for k in keys:
        if k in ev:
            return str(ev[k])
    return default


def _bv(ev, *keys, default=True):
    """Get first matching key as bool."""
    for k in keys:
        if k in ev:
            return bool(ev[k])
    return default


def _make_trade_from_flat(ev):
    return {
        "pos_id":            _sv(ev, "pos_id", "position_id"),
        "bar_t":             _sv(ev, "bar_t", "entry_bar_t"),
        "direction":         _sv(ev, "direction", "side"),
        "entry_px":          _fv(ev, "entry_px", "entry_price"),
        "sl_px":             _fv(ev, "sl_px", "sl_price", "sl"),
        "risk_usd":          _fv(ev, "risk_usd", default=1.0),
        "realized_r":        _fv(ev, "realized_r", "r"),
        "mfe_r":             _fv(ev, "mfe_r", "mfe"),
        "mae_r":             _fv(ev, "mae_r", "mae"),
        "hold_days":         _fv(ev, "hold_days"),
        "net_usd":           _fv(ev, "net_usd", "pnl_usd"),
        "exit_reason":       _sv(ev, "exit_reason", "reason", default="unknown"),
        "shared_entry_gate": _bv(ev, "shared_entry_gate"),
    }


def reconstruct_trades(events):
    """
    Assemble events into completed Trade dicts.
    Returns (completed_trades, open_count).
    """
    if not events:
        return [], 0

    if _is_flat(events):
        return [_make_trade_from_flat(ev) for ev in events], 0

    by_pos = defaultdict(list)
    for ev in events:
        pid = _sv(ev, "pos_id", "position_id", default="__unknown__")
        by_pos[pid].append(ev)

    completed = []
    open_count = 0

    for pid, evs in by_pos.items():
        entries = [e for e in evs if e.get("type") == "entry"]
        exits   = [e for e in evs if e.get("type") in ("exit", "partial_exit", "full_exit")]

        if not entries:
            entries = [e for e in evs if "entry_px" in e and "exit_px" not in e]
        if not entries:
            entries = [e for e in evs if "entry_px" in e]

        if not entries:
            continue

        entry = entries[0]

        if not exits:
            open_count += 1
            continue

        risk_usd  = _fv(entry, "risk_usd", default=1.0)
        total_net = sum(_fv(e, "net_usd", "pnl_usd") for e in exits)
        realized_r = total_net / risk_usd if risk_usd else 0.0

        mfe_r      = max((_fv(e, "mfe_r", "mfe") for e in exits), default=0.0)
        mae_r      = min((_fv(e, "mae_r", "mae") for e in exits), default=0.0)
        hold_days  = _fv(exits[-1], "hold_days")
        exit_reason = _sv(exits[-1], "exit_reason", "reason", default="unknown")

        completed.append({
            "pos_id":            pid,
            "bar_t":             _sv(entry, "bar_t", "entry_bar_t"),
            "direction":         _sv(entry, "direction", "side"),
            "entry_px":          _fv(entry, "entry_px", "entry_price"),
            "sl_px":             _fv(entry, "sl_px", "sl_price", "sl"),
            "risk_usd":          risk_usd,
            "realized_r":        realized_r,
            "mfe_r":             mfe_r,
            "mae_r":             mae_r,
            "hold_days":         hold_days,
            "net_usd":           total_net,
            "exit_reason":       exit_reason,
            "shared_entry_gate": _bv(entry, "shared_entry_gate"),
        })

    return completed, open_count


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_full(realized_r, mfe_r):
    """
    Priority: WIN_RUNNER > GAVE_BACK > WIN_SMALL > SHOOT_LOSS > SL_FAST > CHOP_LOSS
    Thresholds match _qm_loss_decomp.py::classify_full().
    """
    if realized_r >= 1.5:
        return "WIN_RUNNER"
    if mfe_r >= 1.5 and realized_r < 0.7:
        return "GAVE_BACK"
    if realized_r > 0:
        return "WIN_SMALL"
    if realized_r < -1.2:
        return "SHOOT_LOSS"
    if realized_r <= -0.8 and mfe_r < 0.5:
        return "SL_FAST"
    return "CHOP_LOSS"


def classify_all(trades):
    """Annotate trades in-place; return dict cat -> list of trades."""
    cats = defaultdict(list)
    for t in trades:
        cat = classify_full(t["realized_r"], t["mfe_r"])
        t["category"] = cat
        cats[cat].append(t)
    return cats


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def compute_stats(trades):
    if not trades:
        return dict(n=0, net=0.0, pf=0.0, wr_pct=0.0, top3_pct=0.0, mdd=0.0)

    n         = len(trades)
    net       = sum(t["net_usd"] for t in trades)
    gross_win = sum(t["net_usd"] for t in trades if t["net_usd"] > 0)
    gross_los = sum(abs(t["net_usd"]) for t in trades if t["net_usd"] < 0)
    pf        = gross_win / gross_los if gross_los > 0 else float("inf")
    wins      = [t for t in trades if t["net_usd"] > 0]
    wr_pct    = len(wins) / n * 100.0
    top3_sum  = sum(sorted([t["net_usd"] for t in wins], reverse=True)[:3])
    top3_pct  = top3_sum / gross_win * 100.0 if gross_win > 0 else 0.0

    # Equity-curve MDD
    equity = 0.0
    peak   = 0.0
    mdd    = 0.0
    for t in trades:
        equity += t["net_usd"]
        peak = max(peak, equity)
        mdd  = max(mdd, peak - equity)

    return dict(n=n, net=net, pf=pf, wr_pct=wr_pct, top3_pct=top3_pct, mdd=mdd)


# ---------------------------------------------------------------------------
# Matching and decision
# ---------------------------------------------------------------------------

def match_by_bar_t(base_trades, fixd_trades):
    """Match trades by bar_t timestamp. Returns list of (base_t, fixd_t) pairs."""
    fixd_idx = {t["bar_t"]: t for t in fixd_trades if t["bar_t"]}
    return [(b, fixd_idx[b["bar_t"]]) for b in base_trades if b["bar_t"] in fixd_idx]


def make_decision(b_stats, f_stats, b_cats, f_cats):
    """
    Returns (decision_str, reasons_list).
    decision: ADOPT_FIXD | EXTEND_PAPER | KEEP_BASE_REJECT_FIXD
    """
    reasons = []
    b_n = b_stats["n"]
    f_n = f_stats["n"]

    # 1. Insufficient sample
    if b_n < 5 or f_n < 5:
        reasons.append(
            f"Insufficient sample: BASE n={b_n}, FixD n={f_n} (need >=5 each)"
        )
        return "EXTEND_PAPER", reasons

    net_diff  = f_stats["net"] - b_stats["net"]
    b_runners = len(b_cats.get("WIN_RUNNER", []))
    f_runners = len(f_cats.get("WIN_RUNNER", []))
    runner_damaged = (b_runners - f_runners) >= 2

    # 2. FixD net worse OR runner tail damaged
    if f_stats["net"] < b_stats["net"]:
        reasons.append(
            f"FixD net ${f_stats['net']:.2f} < BASE net ${b_stats['net']:.2f}"
        )
        return "KEEP_BASE_REJECT_FIXD", reasons

    if runner_damaged:
        reasons.append(
            f"Runner tail damaged: FixD WIN_RUNNER={f_runners} vs BASE WIN_RUNNER={b_runners}"
            f" (diff={b_runners - f_runners} >= 2)"
        )
        return "KEEP_BASE_REJECT_FIXD", reasons

    # 3. Results too close
    if abs(net_diff) < 5.0:
        reasons.append(
            f"Net difference ${net_diff:+.2f} < $5 threshold (too close to call)"
        )
        return "EXTEND_PAPER", reasons

    # 4. ADOPT: FixD net >$5 better AND PF better AND chop reduced AND runner intact
    b_chop = len(b_cats.get("CHOP_LOSS", []))
    f_chop = len(f_cats.get("CHOP_LOSS", []))
    chop_reduced = f_chop < b_chop

    if f_stats["net"] > b_stats["net"] + 5.0 and f_stats["pf"] > b_stats["pf"] and chop_reduced:
        reasons.append(
            f"FixD net +${net_diff:.2f} vs BASE"
        )
        reasons.append(
            f"PF improved: {b_stats['pf']:.2f} -> {f_stats['pf']:.2f}"
        )
        reasons.append(
            f"CHOP_LOSS reduced: {b_chop} -> {f_chop}"
        )
        reasons.append(
            f"WIN_RUNNER intact: {b_runners} -> {f_runners}"
        )
        return "ADOPT_FIXD", reasons

    reasons.append(
        f"net_diff=${net_diff:+.2f}, PF BASE={b_stats['pf']:.2f} FixD={f_stats['pf']:.2f},"
        f" chop_reduced={chop_reduced} -- not all ADOPT criteria met"
    )
    return "EXTEND_PAPER", reasons


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

NEXT_STEPS = {
    "ADOPT_FIXD": (
        "Phase 2: Enable micro real-money trading.\n"
        "1. Set ENABLE_QM_BTC_FIXD_TRADE=true in .env\n"
        "2. Set QM_FIXD_BTC_SIZE=0.0001 (micro position, approx 0.001 BTC)\n"
        "3. Run for 2 weeks, then re-evaluate\n"
        "4. If profitable at micro size, scale to 0.001 BTC standard"
    ),
    "EXTEND_PAPER": (
        "Continue both paper variants for 1-3 more months.\n"
        "1. Keep ENABLE_QM_BTC_BASE_PAPER=true in .env\n"
        "2. Keep ENABLE_QM_BTC_FIXD_PAPER=true in .env\n"
        "3. Next checkpoint auto-scheduled: +30 days"
    ),
    "KEEP_BASE_REJECT_FIXD": (
        "Reject Fix D. Keep BASE running.\n"
        "1. Set ENABLE_QM_BTC_FIXD_PAPER=false in .env\n"
        "2. Document failure: fast -0.5R loss cut not suitable for BTC QM\n"
        "3. Log to CLAUDE.md: Fix D 1mo forward test FAILED (runner tail damage)"
    ),
}


def _ascii_table(headers, rows):
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    def fmt(cells):
        return "|" + "|".join(f" {str(c):<{w}} " for c, w in zip(cells, widths)) + "|"
    lines = [sep, fmt(headers), sep]
    for row in rows:
        lines.append(fmt(row))
    lines.append(sep)
    return "\n".join(lines)


def _avg_r(trades):
    if not trades:
        return 0.0
    return sum(t["realized_r"] for t in trades) / len(trades)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(b_stats, f_stats, b_cats, f_cats, pairs,
                 b_gated, f_gated, b_reasons_dist, f_reasons_dist,
                 b_open, f_open, decision, dec_reasons):

    net_diff = f_stats["net"] - b_stats["net"]
    b_run = b_cats.get("WIN_RUNNER", [])
    f_run = f_cats.get("WIN_RUNNER", [])
    b_chop = b_cats.get("CHOP_LOSS", [])
    f_chop = f_cats.get("CHOP_LOSS", [])

    lines = [
        "# QM A/B Report - 1-Month Forward Checkpoint",
        "",
        "Analysis date: 2026-07-13  |  Backtest ref: logs/260613_fixd.txt (2021-2026, n=76)",
        "",
        "## Summary Statistics",
        "",
        "| Metric | BASE | Fix D | Diff |",
        "|--------|------|-------|------|",
        f"| Trades (n) | {b_stats['n']} | {f_stats['n']} | {f_stats['n']-b_stats['n']:+d} |",
        f"| Open (excluded) | {b_open} | {f_open} | - |",
        f"| Net USD | ${b_stats['net']:.2f} | ${f_stats['net']:.2f} | ${net_diff:+.2f} |",
        f"| Profit Factor | {b_stats['pf']:.2f} | {f_stats['pf']:.2f} | {f_stats['pf']-b_stats['pf']:+.2f} |",
        f"| Win Rate | {b_stats['wr_pct']:.1f}% | {f_stats['wr_pct']:.1f}%"
        f" | {f_stats['wr_pct']-b_stats['wr_pct']:+.1f}% |",
        f"| Top-3 Contribution | {b_stats['top3_pct']:.1f}% | {f_stats['top3_pct']:.1f}% | - |",
        f"| Max Drawdown | ${b_stats['mdd']:.2f} | ${f_stats['mdd']:.2f} | - |",
        "",
        "## Classification Breakdown",
        "",
        "| Category | BASE n | BASE avg R | FixD n | FixD avg R |",
        "|----------|--------|-----------|--------|-----------|",
    ]
    for cat in CAT_ORDER:
        bt = b_cats.get(cat, [])
        ft = f_cats.get(cat, [])
        lines.append(
            f"| {cat} | {len(bt)} | {_avg_r(bt):+.3f} | {len(ft)} | {_avg_r(ft):+.3f} |"
        )

    # --- Diagnostics ---
    b_chop_avg = _avg_r(b_chop)
    f_chop_avg = _avg_r(f_chop)
    f_cut_r = [t for t in f_chop if "cut_r" in t.get("exit_reason", "")]
    b_run_net = sum(t["net_usd"] for t in b_run)
    f_run_net = sum(t["net_usd"] for t in f_run)
    b_run_max = max((t["realized_r"] for t in b_run), default=0.0)
    f_run_max = max((t["realized_r"] for t in f_run), default=0.0)

    lines += [
        "",
        "## Diagnostic Results",
        "",
        "### (a) CHOP_LOSS - Hypothesis: FixD count lower, avg R capped near -0.5R",
        f"- BASE CHOP_LOSS: n={len(b_chop)}, avg R={b_chop_avg:+.3f}",
        f"- FixD CHOP_LOSS: n={len(f_chop)}, avg R={f_chop_avg:+.3f}",
        f"- FixD CHOP with cut_r exit reason: {len(f_cut_r)}",
        f"- Hypothesis confirmed: {'YES' if len(f_chop) < len(b_chop) else 'NO'}",
        "",
        "### (b) WIN_RUNNER - Hypothesis: FixD >= BASE (slow MA20 was killing winners)",
        f"- BASE WIN_RUNNER: n={len(b_run)}, max R={b_run_max:+.2f}, total net=${b_run_net:.2f}",
        f"- FixD WIN_RUNNER: n={len(f_run)}, max R={f_run_max:+.2f}, total net=${f_run_net:.2f}",
        f"- Runner tail intact (FixD >= BASE - 1): {'YES' if len(f_run) >= len(b_run) - 1 else 'NO'}",
        "",
        "### (c) Common-Signal Pair Comparison",
        f"- Matched by bar_t: {len(pairs)} pairs",
    ]
    if pairs:
        pair_diff_total = sum(f["net_usd"] - b["net_usd"] for b, f in pairs)
        lines += [
            f"- Total USD edge of FixD over BASE on matched signals: ${pair_diff_total:+.2f}",
            "",
            "| bar_t | entry_px | sl_px | base_reason | fixd_reason | base_R | fixd_R | diff_USD |",
            "|-------|----------|-------|-------------|-------------|--------|--------|----------|",
        ]
        for b, f in pairs[:25]:
            diff = f["net_usd"] - b["net_usd"]
            lines.append(
                f"| {str(b['bar_t'])[:16]} | {b['entry_px']:.0f} | {b['sl_px']:.0f}"
                f" | {b.get('exit_reason','?')[:10]} | {f.get('exit_reason','?')[:10]}"
                f" | {b['realized_r']:+.3f} | {f['realized_r']:+.3f} | {diff:+.2f} |"
            )
        if len(pairs) > 25:
            lines.append(f"| ... | | | | | | | ({len(pairs)-25} more) |")
    else:
        lines.append("- No matching bar_t signals found (possible clock skew or mismatched logs)")

    lines += [
        "",
        "### (d) Entry Gate (shared_entry_gate=False = would have been blocked from live)",
        f"- BASE blocked: {b_gated} / {b_stats['n']}",
        f"- FixD blocked: {f_gated} / {f_stats['n']}",
        "",
        "### (e) Exit Reason Distribution",
        "",
        "| exit_reason | BASE | FixD |",
        "|-------------|------|------|",
    ]
    all_reasons = sorted(set(list(b_reasons_dist.keys()) + list(f_reasons_dist.keys())))
    for r in all_reasons:
        lines.append(f"| {r} | {b_reasons_dist.get(r, 0)} | {f_reasons_dist.get(r, 0)} |")

    lines += [
        "",
        "## Decision",
        "",
        f"**{decision}**",
        "",
    ]
    for r in dec_reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Next Steps",
        "",
    ]
    for step_line in NEXT_STEPS[decision].split("\n"):
        lines.append(step_line)

    lines += [
        "",
        "---",
        "",
        "## Backtest Reference (2021-2026, n=76)",
        "",
        "| Metric | BASE (backtest) | Fix D (backtest) |",
        "|--------|----------------|-----------------|",
        "| Net USD | +$44.27 | +$69.04 |",
        "| Profit Factor | 1.21 | 1.36 |",
        "| Top-3 Contribution | 213% | 136% |",
        "| MA20-exit trades | n=72 | n=52 |",
        "| MA20-exit net | +$60 | +$174 |",
        "",
        "Improvement mechanism: fast -0.5R cut converts CHOP losers from slow MA20 exits",
        "(avg -0.4R over many trades) to a hard -0.5R cap, while allowing real winners",
        "to stay in until MA20 -- net effect is concentrated runner gains.",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("QM A/B ANALYSIS - 1-Month Forward Checkpoint (2026-07-13)")
    print("BASE vs Fix D paper trade variants")
    print("=" * 60)
    print()

    base_events = load_jsonl(BASE_JSONL)
    fixd_events = load_jsonl(FIXD_JSONL)

    missing = []
    if base_events is None:
        missing.append(BASE_JSONL)
    if fixd_events is None:
        missing.append(FIXD_JSONL)

    if missing:
        print()
        print("[ERROR] Missing JSONL file(s):")
        for p in missing:
            print(f"  {p}")
        print()
        print("Ensure the paper trading loop has run since 2026-06-13 and")
        print("generated both files in the logs/ subdirectory.")
        print("Re-run this script once the files exist.")
        sys.exit(1)

    if not base_events and not fixd_events:
        print("[ERROR] Both JSONL files are empty -- no data to analyze.")
        sys.exit(1)

    base_trades, base_open = reconstruct_trades(base_events)
    fixd_trades, fixd_open = reconstruct_trades(fixd_events)

    print(f"\n[INFO] BASE  : {len(base_trades)} completed, {base_open} still open (excluded)")
    print(f"[INFO] Fix D : {len(fixd_trades)} completed, {fixd_open} still open (excluded)")

    b_stats = compute_stats(base_trades)
    f_stats = compute_stats(fixd_trades)

    b_cats = classify_all(base_trades)
    f_cats = classify_all(fixd_trades)

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)
    rows = [
        ["Trades (n)",       b_stats["n"],                          f_stats["n"]],
        ["Net USD",          f"${b_stats['net']:.2f}",              f"${f_stats['net']:.2f}"],
        ["Profit Factor",    f"{b_stats['pf']:.2f}",                f"{f_stats['pf']:.2f}"],
        ["Win Rate",         f"{b_stats['wr_pct']:.1f}%",           f"{f_stats['wr_pct']:.1f}%"],
        ["Top-3 Contrib",    f"{b_stats['top3_pct']:.1f}%",         f"{f_stats['top3_pct']:.1f}%"],
        ["Max Drawdown",     f"${b_stats['mdd']:.2f}",              f"${f_stats['mdd']:.2f}"],
    ]
    print(_ascii_table(["Metric", "BASE", "Fix D"], rows))

    # --- Classification ---
    print("\n" + "=" * 60)
    print("CLASSIFICATION BREAKDOWN")
    print("=" * 60)
    cat_rows = []
    for cat in CAT_ORDER:
        bt = b_cats.get(cat, [])
        ft = f_cats.get(cat, [])
        cat_rows.append([cat, len(bt), f"{_avg_r(bt):+.3f}", len(ft), f"{_avg_r(ft):+.3f}"])
    print(_ascii_table(["Category", "BASE n", "BASE avg R", "FixD n", "FixD avg R"], cat_rows))

    # --- Diagnostic (a): CHOP_LOSS ---
    print("\n" + "=" * 60)
    print("DIAGNOSTIC (a): CHOP_LOSS")
    print("Hypothesis: FixD count lower, avg R capped near -0.5R by cut_r exits")
    print("=" * 60)
    b_chop = b_cats.get("CHOP_LOSS", [])
    f_chop = f_cats.get("CHOP_LOSS", [])
    f_cut_r = [t for t in f_chop if "cut_r" in t.get("exit_reason", "")]
    print(f"  BASE CHOP_LOSS : n={len(b_chop)}, avg R={_avg_r(b_chop):+.3f}")
    print(f"  FixD CHOP_LOSS : n={len(f_chop)}, avg R={_avg_r(f_chop):+.3f}")
    print(f"  FixD CHOP with cut_r exit: {len(f_cut_r)}")
    f_chop_reasons = defaultdict(int)
    for t in f_chop:
        f_chop_reasons[t.get("exit_reason", "unknown")] += 1
    if f_chop_reasons:
        print(f"  FixD CHOP exit reason breakdown: {dict(f_chop_reasons)}")
    print(f"  Hypothesis confirmed: {'YES - count reduced' if len(f_chop) < len(b_chop) else 'NO'}")

    # --- Diagnostic (b): WIN_RUNNER ---
    print("\n" + "=" * 60)
    print("DIAGNOSTIC (b): WIN_RUNNER")
    print("Hypothesis: FixD runners >= BASE (slow MA20 was killing winners in BASE)")
    print("=" * 60)
    b_run = b_cats.get("WIN_RUNNER", [])
    f_run = f_cats.get("WIN_RUNNER", [])
    b_run_net = sum(t["net_usd"] for t in b_run)
    f_run_net = sum(t["net_usd"] for t in f_run)
    b_run_max = max((t["realized_r"] for t in b_run), default=0.0)
    f_run_max = max((t["realized_r"] for t in f_run), default=0.0)
    print(f"  BASE WIN_RUNNER: n={len(b_run)}, max R={b_run_max:+.2f}, total net=${b_run_net:.2f}")
    print(f"  FixD WIN_RUNNER: n={len(f_run)}, max R={f_run_max:+.2f}, total net=${f_run_net:.2f}")
    intact = len(f_run) >= len(b_run) - 1
    print(f"  Runner tail intact (FixD >= BASE-1): {'YES' if intact else 'NO - DAMAGED'}")

    # --- Diagnostic (c): Common signal pairs ---
    print("\n" + "=" * 60)
    print("DIAGNOSTIC (c): Common-Signal Pairs (matched by bar_t)")
    print("=" * 60)
    pairs = match_by_bar_t(base_trades, fixd_trades)
    print(f"  Matched signals: {len(pairs)}")
    if pairs:
        pair_diff_total = sum(f["net_usd"] - b["net_usd"] for b, f in pairs)
        print(f"  Total USD edge of FixD over BASE on matched signals: ${pair_diff_total:+.2f}")
        show = pairs[:15]
        pair_rows = []
        for b, f in show:
            diff = f["net_usd"] - b["net_usd"]
            pair_rows.append([
                str(b["bar_t"])[:16],
                f"{b['entry_px']:.0f}",
                f"{b['sl_px']:.0f}",
                b.get("exit_reason", "?")[:8],
                f.get("exit_reason", "?")[:8],
                f"{b['realized_r']:+.3f}",
                f"{f['realized_r']:+.3f}",
                f"{diff:+.2f}",
            ])
        print(_ascii_table(
            ["bar_t", "entry_px", "sl_px", "base_rsn", "fixd_rsn", "base_R", "fixd_R", "diff_USD"],
            pair_rows
        ))
        if len(pairs) > 15:
            print(f"  ... {len(pairs)-15} more pairs (see report)")
    else:
        print("  No common bar_t signals found")

    # --- Diagnostic (d): entry gate ---
    print("\n" + "=" * 60)
    print("DIAGNOSTIC (d): Entry Gate (shared_entry_gate=False)")
    print("=" * 60)
    b_gated_n = len([t for t in base_trades if not t.get("shared_entry_gate", True)])
    f_gated_n = len([t for t in fixd_trades if not t.get("shared_entry_gate", True)])
    print(f"  BASE blocked from live: {b_gated_n} / {len(base_trades)}")
    print(f"  FixD blocked from live: {f_gated_n} / {len(fixd_trades)}")

    # --- Diagnostic (e): Exit reason distribution ---
    print("\n" + "=" * 60)
    print("DIAGNOSTIC (e): Exit Reason Distribution")
    print("Expect BASE: mostly ma20 | FixD: mix of ma20 + cut_r")
    print("=" * 60)
    b_rdist = defaultdict(int)
    f_rdist = defaultdict(int)
    for t in base_trades:
        b_rdist[t.get("exit_reason", "unknown")] += 1
    for t in fixd_trades:
        f_rdist[t.get("exit_reason", "unknown")] += 1
    all_reasons = sorted(set(list(b_rdist.keys()) + list(f_rdist.keys())))
    reason_rows = [[r, b_rdist.get(r, 0), f_rdist.get(r, 0)] for r in all_reasons]
    print(_ascii_table(["exit_reason", "BASE", "FixD"], reason_rows))

    # --- Decision ---
    print("\n" + "=" * 60)
    print("DECISION")
    print("=" * 60)
    decision, dec_reasons = make_decision(b_stats, f_stats, b_cats, f_cats)
    print(f"\n  >>> {decision} <<<\n")
    for r in dec_reasons:
        print(f"  - {r}")
    print(f"\n  Next steps:")
    for line in NEXT_STEPS[decision].split("\n"):
        print(f"    {line}")

    # --- Write report ---
    report_text = build_report(
        b_stats, f_stats, b_cats, f_cats, pairs,
        b_gated_n, f_gated_n, b_rdist, f_rdist,
        base_open, fixd_open,
        decision, dec_reasons
    )
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(report_text)

    print(f"\n[OK] Report written to {REPORT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
