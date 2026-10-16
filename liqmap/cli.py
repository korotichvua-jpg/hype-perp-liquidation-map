from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .data import (fetch_ohlcv_df, fetch_open_interest_usd, load_snapshot, make_exchange,
                   resolve_symbol, save_snapshot, synthetic_ohlcv)
from .model import ModelConfig, build_grids, build_positions
from .plots import heatmap_figure, histogram2d_figure, write_html


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Deterministic HYPE perp liquidation map")
    p.add_argument("--exchange", default="hyperliquid")
    p.add_argument("--symbol", default="HYPE/USDC:USDC")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--oi-usd", type=float, default=None, help="Override open interest (USD, one side)")
    p.add_argument("--max-leverage", type=float, default=10.0)
    p.add_argument("--tiers", type=float, nargs="+", default=[2, 3, 5, 10])
    p.add_argument("--tier-weights", type=float, nargs="+", default=[0.15, 0.25, 0.35, 0.25])
    p.add_argument("--half-life-hours", type=float, default=168.0, help="0 disables age decay")
    p.add_argument("--bins", type=int, default=160)
    p.add_argument("--range-pct", type=float, default=0.30)
    p.add_argument("--snapshot", type=Path, default=None, help="Load data/<folder> instead of fetching")
    p.add_argument("--save-snapshot", type=Path, default=Path("data/last"), help="Where to store fetched data")
    p.add_argument("--offline", action="store_true", help="Use synthetic seeded data (demo only)")
    p.add_argument("--out", type=Path, default=Path("output"))
    return p.parse_args(argv)


def main(argv=None) -> Path:
    a = parse_args(argv)
    cfg = ModelConfig(max_leverage=a.max_leverage, tiers=tuple(a.tiers),
                      tier_weights=tuple(a.tier_weights),
                      half_life_hours=(a.half_life_hours or None),
                      n_price_bins=a.bins, price_range_pct=a.range_pct)

    if a.offline:
        df = synthetic_ohlcv()
        symbol = "HYPE (SYNTHETIC DEMO DATA)"
        oi = a.oi_usd or 400e6
    elif a.snapshot:
        df, meta = load_snapshot(a.snapshot)
        symbol = meta["symbol"]
        oi = a.oi_usd or meta["oi_usd"]
    else:
        ex = make_exchange(a.exchange)
        symbol = resolve_symbol(ex, a.symbol)
        df = fetch_ohlcv_df(ex, symbol, a.timeframe, a.days)
        ref = float(df["close"].iloc[-1])
        oi = a.oi_usd or fetch_open_interest_usd(ex, symbol, ref)
        save_snapshot(a.save_snapshot, df, {"symbol": symbol, "oi_usd": oi,
                                            "timeframe": a.timeframe, "exchange": a.exchange})
        print(f"snapshot saved -> {a.save_snapshot}  (re-run with --snapshot for identical output)")

    ref_price = float(df["close"].iloc[-1])
    pos = build_positions(df, oi, cfg)
    grids = build_grids(pos, len(df), ref_price, cfg)

    a.out.mkdir(parents=True, exist_ok=True)
    html = a.out / "hype_liquidation_map.html"
    write_html(html, [heatmap_figure(df, grids, ref_price, symbol, oi),
                      histogram2d_figure(pos, grids, symbol)],
               symbol=symbol, oi_usd=oi, ref_price=ref_price)
    csv_file = a.out / "liquidation_profile.csv"
    pd.DataFrame({"price": grids["centres"], "long_usd": grids["profile_long"],
                  "short_usd": grids["profile_short"], "cum_long": grids["cum_long"],
                  "cum_short": grids["cum_short"]}).to_csv(csv_file, index=False)
    
    meta_file = a.save_snapshot / "meta.json" if hasattr(a, "save_snapshot") and a.save_snapshot else Path("data/last/meta.json")
    if not meta_file.exists():
        meta_file = Path("data/last/meta.json")
    if meta_file.exists():
        from .terminal import generate_terminal_html
        term_html = a.out / "terminal.html"
        generate_terminal_html(csv_file, meta_file, ref_price, term_html)
        print(f"wrote {term_html}")

    print(f"ref price {ref_price:.4f} | OI/side ${oi/1e6:,.1f}M | positions modelled {len(pos):,} "
          f"| surviving {int(pos['alive'].sum()):,}")
    print(f"wrote {html}")
    return html
