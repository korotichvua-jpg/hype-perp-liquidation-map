"""Terminal dashboard generator for HYPE perp liquidation map.

Builds an ultra-fast, modern Pro Liquidation Terminal with:
- Interactive Liquidation Shock Simulator ('What-if' price shock slider)
- Magnetic Liquidation Sweep Zones & Gravity Score
- Net Liquidation Skew (Delta Liq Index)
- High-Performance HTML5 Canvas Cumulative & Profile Depth Chart
- High-value Liquidation Clusters Breakdown
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd


def generate_terminal_html(csv_path: Path, meta_path: Path, spot_price: float, out_path: Path) -> Path:
    df = pd.read_csv(csv_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Precompute metrics
    short_df = df[df["short_usd"] > 0].copy()
    long_df = df[df["long_usd"] > 0].copy()

    # Bins within 5% and 10%
    spot = float(spot_price)
    long_5pct = float(long_df[long_df["price"] >= spot * 0.95]["long_usd"].sum())
    short_5pct = float(short_df[short_df["price"] <= spot * 1.05]["short_usd"].sum())
    long_10pct = float(long_df[long_df["price"] >= spot * 0.90]["long_usd"].sum())
    short_10pct = float(short_df[short_df["price"] <= spot * 1.10]["short_usd"].sum())

    total_pool_10 = long_10pct + short_10pct
    skew_10 = ((short_10pct - long_10pct) / total_pool_10 * 100) if total_pool_10 > 0 else 0.0

    # Top clusters
    top_shorts = short_df.sort_values("short_usd", ascending=False).head(5)
    top_longs = long_df.sort_values("long_usd", ascending=False).head(5)

    nearest_short = short_df[short_df["short_usd"] >= 1e6].sort_values("price").head(1)
    nearest_long = long_df[long_df["long_usd"] >= 1e6].sort_values("price", ascending=False).head(1)

    near_short_p = float(nearest_short["price"].iloc[0]) if len(nearest_short) else spot * 1.05
    near_short_v = float(nearest_short["short_usd"].iloc[0]) if len(nearest_short) else 0.0
    near_long_p = float(nearest_long["price"].iloc[0]) if len(nearest_long) else spot * 0.95
    near_long_v = float(nearest_long["long_usd"].iloc[0]) if len(nearest_long) else 0.0

    # Gravity score calculation (scale 0-100, >50 means downside gravitational pull)
    gravity_score = int(round(50 + (long_5pct - short_5pct) / (max(long_5pct, short_5pct, 1e6)) * 40))
    gravity_score = max(5, min(95, gravity_score))

    bins_json = df[["price", "long_usd", "short_usd", "cum_long", "cum_short"]].to_dict(orient="records")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>{meta.get('symbol', 'HYPE')} - Pro Liquidation Terminal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-base: #080b11;
      --bg-card: rgba(14, 20, 34, 0.75);
      --bg-card-hover: rgba(22, 30, 48, 0.85);
      --border-subtle: rgba(255, 255, 255, 0.08);
      --border-accent: rgba(56, 189, 248, 0.3);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent-cyan: #38bdf8;
      --accent-green: #10b981;
      --accent-green-bg: rgba(16, 185, 129, 0.12);
      --accent-red: #ef4444;
      --accent-red-bg: rgba(239, 68, 68, 0.12);
      --accent-amber: #f59e0b;
      --accent-amber-bg: rgba(245, 158, 11, 0.12);
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 16px;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background-color: var(--bg-base);
      color: var(--text-main);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      line-height: 1.5;
      padding: 1.25rem;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }}

    .mono {{
      font-family: 'JetBrains Mono', monospace;
    }}

    /* Header Nav */
    header {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      padding: 1rem 1.5rem;
      backdrop-filter: blur(16px);
      gap: 1rem;
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}

    .badge-live {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.25rem 0.65rem;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.35);
      color: var(--accent-green);
      font-size: 0.75rem;
      font-weight: 700;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .pulse-dot {{
      width: 7px;
      height: 7px;
      background: var(--accent-green);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--accent-green);
      animation: pulse 1.8s infinite;
    }}

    @keyframes pulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: 0.4; transform: scale(0.85); }}
    }}

    .ticker-title {{
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}

    .nav-links {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}

    .nav-btn {{
      padding: 0.45rem 0.9rem;
      border-radius: var(--radius-sm);
      font-size: 0.85rem;
      font-weight: 600;
      text-decoration: none;
      color: var(--text-muted);
      border: 1px solid transparent;
      transition: all 0.2s ease;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }}

    .nav-btn:hover {{
      color: var(--text-main);
      background: rgba(255, 255, 255, 0.05);
      border-color: var(--border-subtle);
    }}

    .nav-btn.active {{
      color: var(--accent-cyan);
      background: rgba(56, 189, 248, 0.1);
      border-color: var(--border-accent);
    }}

    /* Main Grid */
    .dashboard-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.25rem;
    }}

    .card {{
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      padding: 1.25rem;
      backdrop-filter: blur(12px);
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      transition: border-color 0.2s ease;
    }}

    .card:hover {{
      border-color: rgba(255, 255, 255, 0.15);
    }}

    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 0.65rem;
    }}

    .card-title {{
      font-size: 0.85rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 0.4rem;
    }}

    .card-metric-huge {{
      font-size: 2.1rem;
      font-weight: 700;
      line-height: 1.1;
      letter-spacing: -0.03em;
    }}

    .metric-sub {{
      font-size: 0.8rem;
      color: var(--text-muted);
    }}

    /* Visual Skew Bar */
    .skew-bar-wrapper {{
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
      margin-top: 0.25rem;
    }}

    .skew-bar-track {{
      display: flex;
      height: 12px;
      border-radius: 9999px;
      overflow: hidden;
      background: rgba(255, 255, 255, 0.05);
    }}

    .skew-fill-long {{
      background: linear-gradient(90deg, #dc2626, #ef4444);
      height: 100%;
      transition: width 0.3s ease;
    }}

    .skew-fill-short {{
      background: linear-gradient(90deg, #10b981, #059669);
      height: 100%;
      transition: width 0.3s ease;
    }}

    .skew-labels {{
      display: flex;
      justify-content: space-between;
      font-size: 0.75rem;
      font-weight: 600;
    }}

    /* Simulator Panel */
    .simulator-panel {{
      grid-column: 1 / -1;
      background: linear-gradient(180deg, rgba(14, 20, 34, 0.95), rgba(10, 15, 26, 0.95));
      border: 1px solid rgba(56, 189, 248, 0.25);
      border-radius: var(--radius-lg);
      padding: 1.5rem;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }}

    .slider-container {{
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}

    .slider-labels {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.9rem;
    }}

    .target-price-display {{
      font-size: 1.75rem;
      font-weight: 700;
      color: var(--accent-cyan);
    }}

    .pct-badge {{
      display: inline-block;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-sm);
      font-size: 0.85rem;
      font-weight: 700;
    }}

    .pct-up {{
      background: var(--accent-green-bg);
      color: var(--accent-green);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}

    .pct-down {{
      background: var(--accent-red-bg);
      color: var(--accent-red);
      border: 1px solid rgba(239, 68, 68, 0.3);
    }}

    input[type=range] {{
      -webkit-appearance: none;
      width: 100%;
      height: 10px;
      border-radius: 5px;
      background: rgba(255, 255, 255, 0.1);
      outline: none;
      transition: background 0.2s;
    }}

    input[type=range]::-webkit-slider-thumb {{
      -webkit-appearance: none;
      appearance: none;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      background: var(--accent-cyan);
      cursor: pointer;
      box-shadow: 0 0 12px var(--accent-cyan);
      border: 2px solid #ffffff;
      transition: transform 0.1s ease;
    }}

    input[type=range]::-webkit-slider-thumb:hover {{
      transform: scale(1.15);
    }}

    .quick-presets {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
    }}

    .preset-btn {{
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      padding: 0.35rem 0.75rem;
      border-radius: var(--radius-sm);
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }}

    .preset-btn:hover {{
      background: rgba(255, 255, 255, 0.12);
      color: var(--text-main);
      border-color: rgba(255, 255, 255, 0.25);
    }}

    /* Shock Results Box */
    .shock-results {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 1.25rem;
    }}

    .shock-item {{
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
    }}

    .shock-item-label {{
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-dim);
    }}

    .shock-item-val {{
      font-size: 1.5rem;
      font-weight: 700;
    }}

    .risk-badge {{
      display: inline-block;
      padding: 0.25rem 0.65rem;
      border-radius: var(--radius-sm);
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      width: fit-content;
    }}

    .risk-low {{ background: rgba(16, 185, 129, 0.2); color: var(--accent-green); border: 1px solid var(--accent-green); }}
    .risk-mod {{ background: rgba(245, 158, 11, 0.2); color: var(--accent-amber); border: 1px solid var(--accent-amber); }}
    .risk-high {{ background: rgba(239, 68, 68, 0.2); color: var(--accent-red); border: 1px solid var(--accent-red); }}
    .risk-extreme {{ background: #dc2626; color: #ffffff; animation: pulse 1s infinite; }}

    /* Canvas Chart Container */
    .chart-container {{
      grid-column: 1 / -1;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}

    #depthCanvas {{
      width: 100%;
      height: 340px;
      display: block;
      border-radius: var(--radius-sm);
      background: #06090e;
    }}

    /* Table Container */
    .tables-grid {{
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 1.25rem;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }}

    th {{
      text-align: left;
      padding: 0.6rem 0.75rem;
      color: var(--text-dim);
      font-weight: 600;
      border-bottom: 1px solid var(--border-subtle);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}

    td {{
      padding: 0.65rem 0.75rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }}

    tr:hover td {{
      background: rgba(255, 255, 255, 0.03);
    }}

    .val-green {{ color: var(--accent-green); font-weight: 600; }}
    .val-red {{ color: var(--accent-red); font-weight: 600; }}

    footer {{
      text-align: center;
      font-size: 0.78rem;
      color: var(--text-dim);
      padding: 1rem 0;
    }}

    @keyframes livePulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: 0.35; transform: scale(0.85); }}
    }}
    @keyframes slideUp {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes tapeFade {{
      from {{ opacity: 0; transform: translateY(4px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .tape-filter-btn {{
      background: transparent;
      border: none;
      color: #94a3b8;
      font-family: inherit;
      font-size: 0.68rem;
      font-weight: 600;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .tape-filter-btn:hover {{
      color: #fff;
      background: rgba(255,255,255,0.08);
    }}
    .tape-filter-btn.active {{
      color: #38bdf8;
      background: rgba(56,189,248,0.15);
      font-weight: 700;
    }}
    .card-standard {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.2rem 0.55rem;
      border-radius: 6px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      font-size: 0.73rem;
      flex-shrink: 0;
      animation: tapeFade 0.25s ease-out;
      transition: transform 0.15s ease;
    }}
    .card-standard:hover {{
      transform: translateY(-1px);
      border-color: rgba(255,255,255,0.2);
    }}
    .card-whale {{
      background: rgba(245,158,11,0.12) !important;
      border: 1px solid rgba(245,158,11,0.45) !important;
      box-shadow: 0 0 10px rgba(245,158,11,0.2);
    }}
    .card-megalodon {{
      background: linear-gradient(135deg, rgba(168,85,247,0.22), rgba(245,158,11,0.18)) !important;
      border: 1px solid #a855f7 !important;
      box-shadow: 0 0 14px rgba(168,85,247,0.35);
    }}
    .card-liq {{
      background: rgba(239,68,68,0.2) !important;
      border: 1px solid #ef4444 !important;
      box-shadow: 0 0 12px rgba(239,68,68,0.3);
    }}
  </style>
</head>
<body>

  <!-- Top Header Navigation -->
  <header>
    <div class="brand">
      <span id="wsStatusBadge" class="badge-live" style="transition:all 0.3s;"><span class="pulse-dot"></span> <span id="wsStatusText">LIVE WS CONNECTED</span></span>
      <div>
        <h1 class="ticker-title">{meta.get('symbol', 'HYPE/USDC:USDC')}</h1>
        <p class="metric-sub">{meta.get('exchange', 'Hyperliquid').upper()} PERPETUAL &bull; SPOT: <span id="spotBadge" class="mono" style="color:var(--accent-cyan);font-weight:700;padding:0.15rem 0.45rem;border-radius:4px;transition:all 0.3s;">${spot:,.4f}</span> &bull; TOTAL OI: <span id="termOiBadge" class="mono">${meta.get('oi_usd', 0)/1e6:,.1f}M</span></p>
      </div>
    </div>
    <nav class="nav-links">
      <button id="audioToggleBtn" onclick="toggleAudio()" class="nav-btn" style="cursor:pointer;">🔊 Audio: ON</button>
      <button id="syncBtn" onclick="refreshLive()" class="nav-btn" style="color:var(--accent-cyan);background:rgba(56,189,248,0.1);border-color:var(--border-accent);cursor:pointer;">🔄 Sync CCXT</button>
      <a href="/terminal" class="nav-btn active">⚡ Terminal Pro</a>
      <a href="/hype_liquidation_map.html" class="nav-btn">📊 Full 2D Heatmap</a>
      <a href="/liquidation_profile.csv" download class="nav-btn">📥 CSV Export</a>
    </nav>
  </header>

  <!-- Key Metrics Row (4 Cards) -->
  <div class="dashboard-grid">
    <!-- Card 1: Net Liquidation Skew -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">Net Liquidation Skew (&Delta; Liq Index)</span>
        <span class="mono" style="font-size:0.8rem;color:var(--text-muted);">&plusmn;10% of Spot</span>
      </div>
      <div class="card-metric-huge mono" style="color:{'var(--accent-red)' if skew_10 < 0 else 'var(--accent-green)'};">
        {skew_10:+.1f}%
      </div>
      <p class="metric-sub">
        {'Downside Flush Asymmetry (More Longs At Risk)' if skew_10 < 0 else 'Upside Squeeze Asymmetry (More Shorts At Risk)'}
      </p>
      <div class="skew-bar-wrapper">
        <div class="skew-bar-track">
          <div class="skew-fill-long" style="width: {long_10pct / max(total_pool_10, 1) * 100:.1f}%;"></div>
          <div class="skew-fill-short" style="width: {short_10pct / max(total_pool_10, 1) * 100:.1f}%;"></div>
        </div>
        <div class="skew-labels mono">
          <span style="color:var(--accent-red)">Long Liq: ${long_10pct/1e6:,.1f}M</span>
          <span style="color:var(--accent-green)">Short Liq: ${short_10pct/1e6:,.1f}M</span>
        </div>
      </div>
    </div>

    <!-- Card 2: Magnetic Gravity Zones -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">Magnetic Liquidity Gravity</span>
        <span class="mono" style="font-size:0.8rem;color:var(--text-muted);">{gravity_score}/100</span>
      </div>
      <div class="card-metric-huge mono" style="color:var(--accent-cyan);">
        {gravity_score}<span style="font-size:1.1rem;color:var(--text-dim);"> / 100</span>
      </div>
      <p class="metric-sub">
        Pull Bias: <strong style="color:{'var(--accent-red)' if gravity_score >= 50 else 'var(--accent-green)'};">
          {'Downside Gravity Pull' if gravity_score >= 50 else 'Upside Vacuum Pull'}
        </strong>
      </p>
      <div style="display:flex;flex-direction:column;gap:0.35rem;font-size:0.82rem;margin-top:0.4rem;" class="mono">
        <div style="display:flex;justify-content:space-between;">
          <span style="color:var(--text-muted)">Nearest Long:</span>
          <span id="nearLongDist" style="color:var(--accent-red);font-weight:600;">${near_long_p:.2f} (${near_long_v/1e6:.1f}M, {((near_long_p - spot)/spot)*100:+.1f}%)</span>
        </div>
        <div style="display:flex;justify-content:space-between;">
          <span style="color:var(--text-muted)">Nearest Short:</span>
          <span id="nearShortDist" style="color:var(--accent-green);font-weight:600;">${near_short_p:.2f} (${near_short_v/1e6:.1f}M, {((near_short_p - spot)/spot)*100:+.1f}%)</span>
        </div>
      </div>
    </div>

    <!-- Card 3: Live Orderbook & Air Pocket Radar -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">Orderbook & Air Pocket Radar</span>
        <span id="airPocketCardBadge" class="risk-badge risk-low" style="font-size:0.7rem;padding:0.15rem 0.5rem;">🛡️ SOUND</span>
      </div>
      <div class="card-metric-huge mono" id="termAirPocketMain" style="color:var(--accent-green);font-size:1.7rem;">
        HEALTHY
      </div>
      <p class="metric-sub" id="termAirPocketDesc">Resting orderbook provides buffer against liquidation cascade</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;font-size:0.75rem;margin-top:0.25rem;" class="mono">
        <div style="background:rgba(255,255,255,0.03);padding:0.3rem 0.5rem;border-radius:4px;">
          <div style="color:var(--text-dim)">BIDS (2% DEPTH)</div>
          <div id="termBids2" style="color:var(--accent-green);font-weight:600;">$1.25M</div>
        </div>
        <div style="background:rgba(255,255,255,0.03);padding:0.3rem 0.5rem;border-radius:4px;">
          <div style="color:var(--text-dim)">ASKS (2% DEPTH)</div>
          <div id="termAsks2" style="color:var(--accent-red);font-weight:600;">$1.18M</div>
        </div>
      </div>
    </div>

    <!-- Card 4: Model Health & Parameters -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">Model Specifications</span>
        <span class="mono" style="font-size:0.8rem;color:var(--text-muted);">Hyperliquid Perp</span>
      </div>
      <div class="card-metric-huge mono" style="color:var(--text-main);font-size:1.7rem;">
        23,003 <span style="font-size:0.95rem;color:var(--text-dim);font-weight:400;">Surviving</span>
      </div>
      <p class="metric-sub">79.9% of 28,800 modeled positions unliquidated</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;font-size:0.75rem;margin-top:0.25rem;" class="mono">
        <div style="background:rgba(255,255,255,0.03);padding:0.3rem 0.5rem;border-radius:4px;">
          <div style="color:var(--text-dim)">HALF-LIFE</div>
          <div style="color:var(--text-main);font-weight:600;">168h (7d)</div>
        </div>
        <div style="background:rgba(255,255,255,0.03);padding:0.3rem 0.5rem;border-radius:4px;">
          <div style="color:var(--text-dim)">MAX LEV</div>
          <div style="color:var(--text-main);font-weight:600;">10x Tiered</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Interactive Liquidation Shock Simulator -->
  <section class="simulator-panel">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;">
      <div>
        <h2 style="font-size:1.25rem;font-weight:700;display:flex;align-items:center;gap:0.5rem;">
          🎯 Interactive Liquidation Shock Simulator
        </h2>
        <p class="metric-sub">Drag price to simulate cascade liquidations and wipeout volumes across leverage tiers</p>
      </div>
      <div class="quick-presets">
        <span style="font-size:0.75rem;color:var(--text-dim);text-transform:uppercase;font-weight:600;margin-right:0.25rem;">PRESETS:</span>
        <button class="preset-btn" onclick="setPreset(-0.15)">-15% Dump</button>
        <button class="preset-btn" onclick="setPreset(-0.08)">-8% Flush</button>
        <button class="preset-btn" onclick="setPreset(0.00)">Spot ($80.99)</button>
        <button class="preset-btn" onclick="setPreset(0.08)">+8% Pump</button>
        <button class="preset-btn" onclick="setPreset(0.15)">+15% Squeeze</button>
        <button class="preset-btn" onclick="setPreset(0.25)">+25% Mega Squeeze</button>
      </div>
    </div>

    <!-- Slider Control -->
    <div class="slider-container">
      <div class="slider-labels">
        <span class="mono" style="color:var(--accent-red)">MIN: $56.84 (-30%)</span>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span style="font-size:0.8rem;color:var(--text-muted);text-transform:uppercase;">SIMULATED TARGET:</span>
          <span id="targetPriceDisplay" class="target-price-display mono">${spot:.2f}</span>
          <span id="pctBadge" class="pct-badge pct-up mono">0.0%</span>
        </div>
        <span class="mono" style="color:var(--accent-green)">MAX: $105.13 (+30%)</span>
      </div>
      <input type="range" id="priceSlider" min="56.84" max="105.13" step="0.10" value="{spot:.2f}">
    </div>

    <!-- Shock Results Metrics -->
    <div class="shock-results">
      <div class="shock-item">
        <span class="shock-item-label">Estimated Liquidated USD</span>
        <div id="wipedUsdDisplay" class="shock-item-val mono" style="color:var(--accent-cyan);">$0.0M</div>
        <span id="sideDisplay" class="metric-sub">At current spot price</span>
      </div>

      <div class="shock-item">
        <span class="shock-item-label">Cascade Severity Risk</span>
        <div style="margin-top:0.25rem;">
          <span id="riskBadge" class="risk-badge risk-low">NEUTRAL (AT SPOT)</span>
        </div>
        <span id="riskDescription" class="metric-sub" style="margin-top:0.25rem;">No immediate cascade threshold</span>
      </div>

      <div class="shock-item">
        <span class="shock-item-label">10x Tier Liquidations</span>
        <div id="tier10Display" class="shock-item-val mono" style="color:var(--text-main);font-size:1.25rem;">$0.0M</div>
        <span class="metric-sub">Highest risk leverage bracket</span>
      </div>

      <div class="shock-item">
        <span class="shock-item-label">5x / 3x / 2x Tiers Wiped</span>
        <div id="tierOtherDisplay" class="shock-item-val mono" style="color:var(--text-main);font-size:1.25rem;">$0.0M</div>
        <span class="metric-sub">Medium & conservative collateral</span>
      </div>
    </div>
  </section>

  <!-- Modern Floating Fire Tape & Order Flow Command HUD -->
  <div id="fireTapeContainer" style="grid-column: 1 / -1; display:flex; flex-direction:column; gap:0.4rem;">
    <!-- Floating Island HUD -->
    <div id="tapeIsland" style="background:rgba(10,15,29,0.88);border:1px solid rgba(255,255,255,0.12);border-radius:14px;padding:0.5rem 1.1rem;display:flex;align-items:center;justify-content:space-between;gap:0.85rem;backdrop-filter:blur(24px);box-shadow:0 12px 36px rgba(0,0,0,0.55);transition:all 0.3s cubic-bezier(0.16,1,0.3,1);">
      <!-- Left: HUD Brand & Rolling 60s Net Delta Spark-Bar -->
      <div style="display:flex;align-items:center;gap:0.75rem;flex-shrink:0;">
        <div style="display:flex;align-items:center;gap:0.45rem;">
          <span style="width:8px;height:8px;background:#f59e0b;border-radius:50%;box-shadow:0 0 8px #f59e0b;animation:livePulse 1.8s infinite;"></span>
          <span style="font-weight:700;font-size:0.78rem;color:#f59e0b;letter-spacing:0.05em;">FLOW HUD</span>
        </div>
        <!-- 60s Delta Spark-Bar -->
        <div style="display:flex;flex-direction:column;gap:0.2rem;width:150px;background:rgba(255,255,255,0.03);padding:0.25rem 0.45rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);" title="60s Taker Volume Imbalance">
          <div style="display:flex;justify-content:space-between;font-size:0.62rem;font-weight:600;">
            <span id="deltaBuyText" style="color:var(--accent-green);">B: 50%</span>
            <span id="deltaSellText" style="color:var(--accent-red);">S: 50%</span>
          </div>
          <div style="height:4px;background:rgba(255,255,255,0.08);border-radius:999px;overflow:hidden;display:flex;">
            <div id="deltaBuyBar" style="width:50%;background:var(--accent-green);transition:width 0.3s ease;"></div>
            <div id="deltaSellBar" style="width:50%;background:var(--accent-red);transition:width 0.3s ease;"></div>
          </div>
        </div>
      </div>

      <!-- Center: Sliding Trade Micro-Cards Feed -->
      <div id="tapeStreamWrapper" onmouseenter="pauseTape()" onmouseleave="resumeTape()" style="display:flex;align-items:center;gap:0.5rem;overflow-x:auto;white-space:nowrap;scrollbar-width:none;flex-grow:1;position:relative;padding:0.1rem 0;">
        <div id="tapePausedBadge" style="display:none;position:absolute;left:50%;transform:translateX(-50%);background:rgba(245,158,11,0.9);color:#0a0f1d;font-size:0.68rem;font-weight:700;padding:0.15rem 0.5rem;border-radius:4px;z-index:10;box-shadow:0 2px 8px rgba(0,0,0,0.4);">
          ⏸ PAUSED (HOVER)
        </div>
        <div id="termTapeFeed" style="display:flex;align-items:center;gap:0.5rem;transition:opacity 0.2s;">
          <span style="color:#64748b;font-size:0.75rem;">Connecting live Hyperliquid stream...</span>
        </div>
      </div>

      <!-- Right: Filter Pills & Drawer Toggle Button -->
      <div style="display:flex;align-items:center;gap:0.45rem;flex-shrink:0;">
        <div style="display:flex;gap:0.25rem;background:rgba(255,255,255,0.04);padding:0.15rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
          <button id="filterAll" onclick="setTapeFilter('all')" class="tape-filter-btn active">All</button>
          <button id="filterWhales" onclick="setTapeFilter('whales')" class="tape-filter-btn">🐋 ≥$10k</button>
          <button id="filterLiqs" onclick="setTapeFilter('liqs')" class="tape-filter-btn">🔥 Liqs</button>
        </div>
        <button id="drawerToggleBtn" onclick="toggleTapeDrawer()" style="padding:0.3rem 0.55rem;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);color:var(--text-muted);border-radius:6px;cursor:pointer;font-size:0.75rem;font-weight:600;display:inline-flex;align-items:center;gap:0.3rem;transition:all 0.2s;" title="Toggle 3-Column Order Flow Matrix">
          <span id="drawerIcon">⛶</span> <span style="font-size:0.7rem;">Drawer</span>
        </button>
      </div>
    </div>

    <!-- Expandable 3-Column Order Flow Drawer -->
    <div id="tapeDrawer" style="display:none;background:rgba(10,15,29,0.95);border:1px solid rgba(255,255,255,0.14);border-radius:14px;padding:0.85rem 1rem;backdrop-filter:blur(24px);box-shadow:0 16px 40px rgba(0,0,0,0.6);animation:slideUp 0.25s cubic-bezier(0.16,1,0.3,1);">
      <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.5rem;margin-bottom:0.6rem;font-size:0.75rem;">
        <span style="font-weight:700;color:#f1f5f9;letter-spacing:0.04em;">⚡ ORDER FLOW COMMAND MATRIX (REAL-TIME HYPERLIQUID WS)</span>
        <div style="display:flex;gap:1rem;font-size:0.7rem;color:var(--text-muted);">
          <span>60s Taker Vol: <b id="drawerVol60s" style="color:var(--accent-cyan);">$0.0M</b></span>
          <span>Latency: <b id="drawerSpeed" style="color:var(--accent-green);">&lt;35ms</b></span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));gap:0.75rem;max-height:220px;">
        <!-- Col 1: All Taker Prints -->
        <div style="background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.5rem;display:flex;flex-direction:column;gap:0.35rem;">
          <div style="font-size:0.68rem;font-weight:700;color:var(--text-muted);display:flex;justify-content:space-between;">
            <span>ALL TAKER PRINTS</span>
            <span id="countAllPrints" style="color:var(--text-dim);">0 PRINTS</span>
          </div>
          <div id="drawerListAll" style="overflow-y:auto;max-height:180px;display:flex;flex-direction:column;gap:0.25rem;font-size:0.7rem;"></div>
        </div>
        <!-- Col 2: Whale Radar -->
        <div style="background:rgba(0,0,0,0.25);border:1px solid rgba(245,158,11,0.2);border-radius:8px;padding:0.5rem;display:flex;flex-direction:column;gap:0.35rem;">
          <div style="font-size:0.68rem;font-weight:700;color:var(--accent-amber);display:flex;justify-content:space-between;">
            <span>🐋 WHALE RADAR (≥$10,000)</span>
            <span id="countWhalePrints" style="color:var(--accent-amber);">0 WHALES</span>
          </div>
          <div id="drawerListWhales" style="overflow-y:auto;max-height:180px;display:flex;flex-direction:column;gap:0.25rem;font-size:0.7rem;"></div>
        </div>
        <!-- Col 3: Liquidation Sweeps -->
        <div style="background:rgba(0,0,0,0.25);border:1px solid rgba(239,68,68,0.25);border-radius:8px;padding:0.5rem;display:flex;flex-direction:column;gap:0.35rem;">
          <div style="font-size:0.68rem;font-weight:700;color:var(--accent-red);display:flex;justify-content:space-between;">
            <span>🚨 FORCED LIQUIDATIONS & SWEEPS</span>
            <span id="countLiqPrints" style="color:var(--accent-red);">0 DETECTED</span>
          </div>
          <div id="drawerListLiqs" style="overflow-y:auto;max-height:180px;display:flex;flex-direction:column;gap:0.25rem;font-size:0.7rem;"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- Interactive Depth & Cumulative Liquidation Canvas -->
  <section class="chart-container">
    <div class="card-header">
      <span class="card-title">Cumulative Liquidation Curves & High-Density Zones</span>
      <span class="mono" style="font-size:0.8rem;color:var(--text-muted);">Red = Long Liq Below Spot &bull; Green = Short Liq Above Spot</span>
    </div>
    <canvas id="depthCanvas" width="1200" height="340"></canvas>
  </section>

  <!-- Top Liquidation Clusters Breakdown -->
  <section class="tables-grid">
    <!-- Long Clusters Table -->
    <div class="card">
      <div class="card-header">
        <span class="card-title" style="color:var(--accent-red);">🔻 Top Long Liquidation Clusters (Below Spot)</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Liq Price</th>
            <th>Volume ($)</th>
            <th>Cumulative</th>
            <th>Distance</th>
            <th>Severity</th>
          </tr>
        </thead>
        <tbody class="mono">
          {"".join([f'''<tr>
            <td style="color:var(--accent-red);font-weight:700;">${r.price:.2f}</td>
            <td>${r.long_usd/1e6:,.2f}M</td>
            <td>${r.cum_long/1e6:,.1f}M</td>
            <td>{((r.price - spot)/spot)*100:+.2f}%</td>
            <td><span class="risk-badge risk-{"high" if r.long_usd > 20e6 else "mod"}">{"HIGH" if r.long_usd > 20e6 else "MOD"}</span></td>
          </tr>''' for _, r in top_longs.iterrows()])}
        </tbody>
      </table>
    </div>

    <!-- Short Clusters Table -->
    <div class="card">
      <div class="card-header">
        <span class="card-title" style="color:var(--accent-green);">🔺 Top Short Liquidation Clusters (Above Spot)</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Liq Price</th>
            <th>Volume ($)</th>
            <th>Cumulative</th>
            <th>Distance</th>
            <th>Severity</th>
          </tr>
        </thead>
        <tbody class="mono">
          {"".join([f'''<tr>
            <td style="color:var(--accent-green);font-weight:700;">${r.price:.2f}</td>
            <td>${r.short_usd/1e6:,.2f}M</td>
            <td>${r.cum_short/1e6:,.1f}M</td>
            <td>{((r.price - spot)/spot)*100:+.2f}%</td>
            <td><span class="risk-badge risk-{"high" if r.short_usd > 20e6 else "mod"}">{"HIGH" if r.short_usd > 20e6 else "MOD"}</span></td>
          </tr>''' for _, r in top_shorts.iterrows()])}
        </tbody>
      </table>
    </div>
  </section>

  <!-- Detailed System & Telemetry Footer -->
  <footer style="margin-top:auto;padding:1.25rem 1.5rem;margin-bottom:1rem;border-top:1px solid rgba(255,255,255,0.08);background:rgba(10,15,29,0.75);backdrop-filter:blur(16px);border-radius:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.85rem;font-family:'JetBrains Mono',monospace;font-size:0.75rem;color:#94a3b8;">
    <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
      <span style="display:inline-flex;align-items:center;gap:0.4rem;color:#38bdf8;font-weight:600;">
        📁 <span>D:\\projects\\N1</span>
      </span>
      <span style="color:rgba(255,255,255,0.15);">|</span>
      <span>INTERNAL IP: <b id="footerInternalIp" style="color:#10b981;">192.168.1.12</b></span>
      <span style="color:rgba(255,255,255,0.15);">|</span>
      <span>EXTERNAL IP: <b id="footerExternalIp" style="color:#f59e0b;">83.5.208.192</b></span>
    </div>
    <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
      <span style="color:#64748b;">AI ARCHITECTURE:</span>
      <span style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.25rem 0.6rem;background:rgba(168,85,247,0.15);border:1px solid rgba(168,85,247,0.35);color:#c084fc;font-weight:700;border-radius:6px;font-size:0.72rem;">
        🤖 Antigravity 2.0 (Google DeepMind) &bull; Gemini 2.5 Pro
      </span>
    </div>
  </footer>

  <script>
    // Embedded Liquidation Data
    let SPOT = {spot};
    const NEAR_LONG_P = {near_long_p};
    const NEAR_LONG_V = {near_long_v};
    const NEAR_SHORT_P = {near_short_p};
    const NEAR_SHORT_V = {near_short_v};
    const BINS = {json.dumps(bins_json)};

    const slider = document.getElementById('priceSlider');
    const targetPriceDisplay = document.getElementById('targetPriceDisplay');
    const pctBadge = document.getElementById('pctBadge');
    const wipedUsdDisplay = document.getElementById('wipedUsdDisplay');
    const sideDisplay = document.getElementById('sideDisplay');
    const riskBadge = document.getElementById('riskBadge');
    const riskDescription = document.getElementById('riskDescription');
    const tier10Display = document.getElementById('tier10Display');
    const tierOtherDisplay = document.getElementById('tierOtherDisplay');
    const canvas = document.getElementById('depthCanvas');
    const ctx = canvas.getContext('2d');

    function updateSimulation(targetPrice) {{
      const pct = ((targetPrice - SPOT) / SPOT) * 100;
      targetPriceDisplay.textContent = '$' + targetPrice.toFixed(2);
      
      pctBadge.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
      if (pct > 0.05) {{
        pctBadge.className = 'pct-badge pct-up mono';
      }} else if (pct < -0.05) {{
        pctBadge.className = 'pct-badge pct-down mono';
      }} else {{
        pctBadge.className = 'pct-badge mono';
        pctBadge.style.background = 'rgba(255,255,255,0.1)';
        pctBadge.style.color = '#fff';
      }}

      let wipedUsd = 0;
      let isShort = false;

      if (targetPrice > SPOT) {{
        // Shorts liquidated between SPOT and targetPrice
        isShort = true;
        for (const b of BINS) {{
          if (b.price > SPOT && b.price <= targetPrice) {{
            wipedUsd += b.short_usd;
          }}
        }}
        sideDisplay.textContent = 'Short positions liquidated (Short Squeeze)';
        wipedUsdDisplay.style.color = 'var(--accent-green)';
      }} else if (targetPrice < SPOT) {{
        // Longs liquidated between targetPrice and SPOT
        isShort = false;
        for (const b of BINS) {{
          if (b.price < SPOT && b.price >= targetPrice) {{
            wipedUsd += b.long_usd;
          }}
        }}
        sideDisplay.textContent = 'Long positions liquidated (Long Flush / Cascade)';
        wipedUsdDisplay.style.color = 'var(--accent-red)';
      }} else {{
        sideDisplay.textContent = 'At current spot price ($' + SPOT.toFixed(2) + ')';
        wipedUsdDisplay.style.color = 'var(--accent-cyan)';
      }}

      wipedUsdDisplay.textContent = '$' + (wipedUsd / 1e6).toFixed(1) + 'M';

      // Tier estimate (Tier 10x is ~25%, 5x is 35%, 3x is 25%, 2x is 15%)
      const t10 = wipedUsd * 0.25;
      const tOther = wipedUsd * 0.75;
      tier10Display.textContent = '$' + (t10 / 1e6).toFixed(1) + 'M';
      tierOtherDisplay.textContent = '$' + (tOther / 1e6).toFixed(1) + 'M';

      // Severity Badge
      const wipedM = wipedUsd / 1e6;
      if (wipedM === 0) {{
        riskBadge.className = 'risk-badge risk-low';
        riskBadge.textContent = 'NEUTRAL (AT SPOT)';
        riskDescription.textContent = 'No liquidation cascading';
      }} else if (wipedM < 25) {{
        riskBadge.className = 'risk-badge risk-low';
        riskBadge.textContent = 'LOW CASCADE RISK';
        riskDescription.textContent = 'Absorption likely via normal orderbook depth';
      }} else if (wipedM < 90) {{
        riskBadge.className = 'risk-badge risk-mod';
        riskBadge.textContent = 'MODERATE CASCADE RISK';
        riskDescription.textContent = 'Moderate slippage, local stop runs likely';
      }} else if (wipedM < 220) {{
        riskBadge.className = 'risk-badge risk-high';
        riskBadge.textContent = 'HIGH SQUEEZE/CASCADE RISK';
        riskDescription.textContent = 'Significant flash slippage and forced market closes';
      }} else {{
        riskBadge.className = 'risk-badge risk-extreme';
        riskBadge.textContent = '🔥 EXTREME SYSTEMIC CASCADE';
        riskDescription.textContent = 'Heavy multi-tier liquidation domino sweep';
      }}

      drawDepthChart(targetPrice);
    }}

    function setPreset(pct) {{
      const p = SPOT * (1 + pct);
      slider.value = p.toFixed(2);
      updateSimulation(p);
    }}

    let simRafId = null;
    slider.addEventListener('input', (e) => {{
      const val = parseFloat(e.target.value);
      if (simRafId) cancelAnimationFrame(simRafId);
      simRafId = requestAnimationFrame(() => {{
        updateSimulation(val);
        simRafId = null;
      }});
    }});

    // High performance HTML5 Canvas chart renderer
    function drawDepthChart(targetPrice) {{
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);

      const w = rect.width;
      const h = rect.height;
      const padL = 60, padR = 60, padT = 30, padB = 40;
      const chartW = w - padL - padR;
      const chartH = h - padT - padB;

      ctx.clearRect(0, 0, w, h);

      // Min/Max price
      const minP = BINS[0].price;
      const maxP = BINS[BINS.length - 1].price;
      const maxCum = Math.max(...BINS.map(b => Math.max(b.cum_long, b.cum_short))) || 1e9;

      function pToX(p) {{
        return padL + ((p - minP) / (maxP - minP)) * chartW;
      }}

      function cumToY(c) {{
        return padT + chartH - (c / maxCum) * chartH;
      }}

      // Background grid
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
      ctx.lineWidth = 1;
      for (let i = 0; i <= 5; i++) {{
        const y = padT + (chartH / 5) * i;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();

        const val = ((5 - i) / 5) * (maxCum / 1e6);
        ctx.fillStyle = '#64748b';
        ctx.font = '10px "JetBrains Mono"';
        ctx.textAlign = 'right';
        ctx.fillText('$' + val.toFixed(0) + 'M', padL - 8, y + 3);
      }}

      // Long Cumulative Area (Red)
      ctx.beginPath();
      ctx.moveTo(pToX(minP), padT + chartH);
      for (const b of BINS) {{
        if (b.price <= SPOT) {{
          ctx.lineTo(pToX(b.price), cumToY(b.cum_long));
        }}
      }}
      ctx.lineTo(pToX(SPOT), padT + chartH);
      ctx.closePath();
      const gradLong = ctx.createLinearGradient(0, padT, 0, padT + chartH);
      gradLong.addColorStop(0, 'rgba(239, 68, 68, 0.35)');
      gradLong.addColorStop(1, 'rgba(239, 68, 68, 0.02)');
      ctx.fillStyle = gradLong;
      ctx.fill();

      // Long Cumulative Line
      ctx.beginPath();
      let started = false;
      for (const b of BINS) {{
        if (b.price <= SPOT) {{
          const x = pToX(b.price);
          const y = cumToY(b.cum_long);
          if (!started) {{ ctx.moveTo(x, y); started = true; }} else {{ ctx.lineTo(x, y); }}
        }}
      }}
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Short Cumulative Area (Green)
      ctx.beginPath();
      ctx.moveTo(pToX(SPOT), padT + chartH);
      for (const b of BINS) {{
        if (b.price >= SPOT) {{
          ctx.lineTo(pToX(b.price), cumToY(b.cum_short));
        }}
      }}
      ctx.lineTo(pToX(maxP), padT + chartH);
      ctx.closePath();
      const gradShort = ctx.createLinearGradient(0, padT, 0, padT + chartH);
      gradShort.addColorStop(0, 'rgba(16, 185, 129, 0.35)');
      gradShort.addColorStop(1, 'rgba(16, 185, 129, 0.02)');
      ctx.fillStyle = gradShort;
      ctx.fill();

      // Short Cumulative Line
      ctx.beginPath();
      started = false;
      for (const b of BINS) {{
        if (b.price >= SPOT) {{
          const x = pToX(b.price);
          const y = cumToY(b.cum_short);
          if (!started) {{ ctx.moveTo(x, y); started = true; }} else {{ ctx.lineTo(x, y); }}
        }}
      }}
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Spot Line (Cyan)
      const spotX = pToX(SPOT);
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.moveTo(spotX, padT);
      ctx.lineTo(spotX, padT + chartH);
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = '#38bdf8';
      ctx.font = 'bold 11px "JetBrains Mono"';
      ctx.textAlign = 'center';
      ctx.fillText('SPOT $' + SPOT.toFixed(2), spotX, padT - 8);

      // Target simulated price line
      if (Math.abs(targetPrice - SPOT) > 0.05) {{
        const targetX = pToX(targetPrice);
        ctx.beginPath();
        ctx.setLineDash([2, 2]);
        ctx.moveTo(targetX, padT);
        ctx.lineTo(targetX, padT + chartH);
        ctx.strokeStyle = targetPrice > SPOT ? '#10b981' : '#ef4444';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = targetPrice > SPOT ? '#10b981' : '#ef4444';
        ctx.font = 'bold 11px "JetBrains Mono"';
        ctx.textAlign = 'center';
        ctx.fillText('TARGET $' + targetPrice.toFixed(2), targetX, padT + chartH + 20);
      }}

      // X-Axis Price Markers
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px "JetBrains Mono"';
      ctx.textAlign = 'center';
      const steps = 8;
      for (let i = 0; i <= steps; i++) {{
        const p = minP + (i / steps) * (maxP - minP);
        ctx.fillText('$' + p.toFixed(1), pToX(p), padT + chartH + 16);
      }}
    }}

    // Initial render
    window.addEventListener('resize', () => drawDepthChart(parseFloat(slider.value)));
    updateSimulation(SPOT);

    // Audio Synthesizer
    let audioEnabled = true;
    let audioCtx = null;

    function initAudio() {{
      if (!audioCtx) {{
        try {{
          audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }} catch(e) {{}}
      }}
    }}

    function playTickSound(isBuy, isWhale) {{
      if (!audioEnabled) return;
      try {{
        initAudio();
        if (!audioCtx) return;
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = isWhale ? 'sine' : 'triangle';
        osc.frequency.setValueAtTime(isWhale ? 880 : (isBuy ? 580 : 420), audioCtx.currentTime);
        gain.gain.setValueAtTime(isWhale ? 0.08 : 0.02, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + (isWhale ? 0.18 : 0.05));
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + (isWhale ? 0.18 : 0.05));
      }} catch(e) {{}}
    }}

    function toggleAudio() {{
      audioEnabled = !audioEnabled;
      const btn = document.getElementById('audioToggleBtn');
      btn.textContent = audioEnabled ? '🔊 Audio: ON' : '🔇 Audio: OFF';
      btn.style.color = audioEnabled ? 'var(--text-main)' : 'var(--text-dim)';
    }}

    function onLivePriceUpdate(newPrice) {{
      const diff = newPrice - SPOT;
      if (Math.abs(diff) > 0.0001) {{
        const badge = document.getElementById('spotBadge');
        if (badge) {{
          badge.textContent = '$' + newPrice.toFixed(4) + (diff > 0 ? ' ▲' : ' ▼');
          badge.style.background = diff > 0 ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)';
          badge.style.color = diff > 0 ? '#10b981' : '#ef4444';
          setTimeout(() => {{
            badge.style.background = 'transparent';
            badge.style.color = 'var(--accent-cyan)';
          }}, 500);
        }}
        SPOT = newPrice;

        // Recalculate cluster distances
        const longPct = ((NEAR_LONG_P - SPOT) / SPOT) * 100;
        const shortPct = ((NEAR_SHORT_P - SPOT) / SPOT) * 100;
        const nL = document.getElementById('nearLongDist');
        const nS = document.getElementById('nearShortDist');
        if (nL) nL.textContent = '$' + NEAR_LONG_P.toFixed(2) + ' (' + (NEAR_LONG_V / 1e6).toFixed(1) + 'M, ' + (longPct > 0 ? '+' : '') + longPct.toFixed(1) + '%)';
        if (nS) nS.textContent = '$' + NEAR_SHORT_P.toFixed(2) + ' (' + (NEAR_SHORT_V / 1e6).toFixed(1) + 'M, ' + (shortPct > 0 ? '+' : '') + shortPct.toFixed(1) + '%)';

        // Redraw depth chart with updated SPOT needle
        drawDepthChart(parseFloat(slider.value));
      }}
    }}

    let currentTapeFilter = 'all';
    let isTapePaused = false;
    let isDrawerOpen = false;
    const rollingTrades = [];
    let totalAllCount = 0, totalWhaleCount = 0, totalLiqCount = 0;

    function pauseTape() {{
      isTapePaused = true;
      const b = document.getElementById('tapePausedBadge');
      if (b) b.style.display = 'block';
    }}

    function resumeTape() {{
      isTapePaused = false;
      const b = document.getElementById('tapePausedBadge');
      if (b) b.style.display = 'none';
    }}

    function setTapeFilter(f) {{
      currentTapeFilter = f;
      ['filterAll', 'filterWhales', 'filterLiqs'].forEach(id => {{
        const b = document.getElementById(id);
        if (b) b.classList.remove('active');
      }});
      if (f === 'all') document.getElementById('filterAll').classList.add('active');
      if (f === 'whales') document.getElementById('filterWhales').classList.add('active');
      if (f === 'liqs') document.getElementById('filterLiqs').classList.add('active');

      const feed = document.getElementById('termTapeFeed');
      if (!feed) return;
      Array.from(feed.children).forEach(child => {{
        if (!child.dataset) return;
        if (f === 'all') child.style.display = 'inline-flex';
        else if (f === 'whales') child.style.display = child.dataset.whale === 'true' ? 'inline-flex' : 'none';
        else if (f === 'liqs') child.style.display = child.dataset.liq === 'true' ? 'inline-flex' : 'none';
      }});
    }}

    function toggleTapeDrawer() {{
      isDrawerOpen = !isDrawerOpen;
      const drawer = document.getElementById('tapeDrawer');
      const icon = document.getElementById('drawerIcon');
      if (drawer) drawer.style.display = isDrawerOpen ? 'block' : 'none';
      if (icon) icon.textContent = isDrawerOpen ? '✕' : '⛶';
    }}

    function updateDeltaBar(trade) {{
      const now = Date.now();
      const px = parseFloat(trade.px);
      const sz = parseFloat(trade.sz);
      const isBuy = trade.side === 'B' || trade.side === 'buy';
      const notional = px * sz;

      rollingTrades.push({{ time: trade.time || now, isBuy, notional }});
      while (rollingTrades.length && (now - rollingTrades[0].time > 60000)) {{
        rollingTrades.shift();
      }}

      let buyVal = 0, sellVal = 0;
      rollingTrades.forEach(t => {{
        if (t.isBuy) buyVal += t.notional; else sellVal += t.notional;
      }});
      const total = buyVal + sellVal;
      const buyPct = total > 0 ? (buyVal / total * 100) : 50;
      const sellPct = 100 - buyPct;

      const bBar = document.getElementById('deltaBuyBar');
      const sBar = document.getElementById('deltaSellBar');
      const bTxt = document.getElementById('deltaBuyText');
      const sTxt = document.getElementById('deltaSellText');
      const dVol = document.getElementById('drawerVol60s');

      if (bBar) bBar.style.width = buyPct.toFixed(1) + '%';
      if (sBar) sBar.style.width = sellPct.toFixed(1) + '%';
      if (bTxt) bTxt.textContent = 'B: ' + buyPct.toFixed(0) + '% ($' + (buyVal/1e3).toFixed(0) + 'k)';
      if (sTxt) sTxt.textContent = 'S: ' + sellPct.toFixed(0) + '% ($' + (sellVal/1e3).toFixed(0) + 'k)';
      if (dVol) dVol.textContent = '$' + (total / 1e6).toFixed(2) + 'M';
    }}

    function addTradeToTape(t) {{
      const feed = document.getElementById('termTapeFeed');
      if (!feed) return;
      const isBuy = t.side === 'B' || t.side === 'buy';
      const px = parseFloat(t.px);
      const sz = parseFloat(t.sz);
      const notional = px * sz;
      const isWhale = notional >= 10000;
      const isMegalodon = notional >= 50000;
      const isLiq = t.liquidation === true || t.side === 'LIQ';
      const timeStr = new Date(t.time || Date.now()).toLocaleTimeString([], {{hour:'2-digit', minute:'2-digit', second:'2-digit'}});

      playTickSound(isBuy, isWhale);
      updateDeltaBar(t);

      totalAllCount++;
      if (isWhale) totalWhaleCount++;
      if (isLiq) totalLiqCount++;

      const cAll = document.getElementById('countAllPrints');
      const cWhale = document.getElementById('countWhalePrints');
      const cLiq = document.getElementById('countLiqPrints');
      if (cAll) cAll.textContent = totalAllCount + ' PRINTS';
      if (cWhale) cWhale.textContent = totalWhaleCount + ' WHALES';
      if (cLiq) cLiq.textContent = totalLiqCount + ' DETECTED';

      const drawerItemHtml = `<div style="display:flex;justify-content:space-between;align-items:center;padding:0.2rem 0.35rem;border-radius:4px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04);">
        <span style="color:var(--text-dim);">${{timeStr}}</span>
        <b style="color:${{isBuy ? 'var(--accent-green)' : 'var(--accent-red)'}};">${{isBuy ? 'BUY' : 'SELL'}}</b>
        <span>${{sz.toFixed(2)}} @ $${{px.toFixed(2)}}</span>
        <span style="color:var(--text-main);font-weight:600;">$${{Math.round(notional).toLocaleString()}}</span>
      </div>`;

      const listAll = document.getElementById('drawerListAll');
      if (listAll) {{
        listAll.insertAdjacentHTML('afterbegin', drawerItemHtml);
        if (listAll.children.length > 40) listAll.removeChild(listAll.lastChild);
      }}
      if (isWhale) {{
        const listWhales = document.getElementById('drawerListWhales');
        if (listWhales) {{
          listWhales.insertAdjacentHTML('afterbegin', drawerItemHtml);
          if (listWhales.children.length > 40) listWhales.removeChild(listWhales.lastChild);
        }}
      }}
      if (isLiq) {{
        const listLiqs = document.getElementById('drawerListLiqs');
        if (listLiqs) {{
          listLiqs.insertAdjacentHTML('afterbegin', drawerItemHtml);
          if (listLiqs.children.length > 40) listLiqs.removeChild(listLiqs.lastChild);
        }}
      }}

      if (isTapePaused) return;

      let cardClass = 'card-standard';
      if (isMegalodon) cardClass += ' card-megalodon';
      else if (isWhale) cardClass += ' card-whale';
      else if (isLiq) cardClass += ' card-liq';

      // DOM element recycling: Reuse feed.lastElementChild once pool capacity (20) is met
      const item = (feed.children.length >= 20) ? feed.lastElementChild : document.createElement('div');
      item.className = cardClass;
      item.dataset.whale = isWhale ? 'true' : 'false';
      item.dataset.liq = isLiq ? 'true' : 'false';
      item.style.display = ((currentTapeFilter === 'whales' && !isWhale) || (currentTapeFilter === 'liqs' && !isLiq)) ? 'none' : '';

      item.innerHTML = `<span style="color:var(--text-dim);font-size:0.68rem;">${{timeStr}}</span> ` +
                       `<b style="color:${{isBuy ? 'var(--accent-green)' : 'var(--accent-red)'}};font-size:0.75rem;">${{isBuy ? 'BUY ▲' : 'SELL ▼'}}</b> ` +
                       `<span>${{sz.toFixed(2)}} @ $${{px.toFixed(2)}}</span> ` +
                       `<span style="color:var(--text-main);font-weight:600;">($${{Math.round(notional).toLocaleString()}})</span>` +
                       (isMegalodon ? ` <span style="background:#a855f7;color:#fff;padding:0.1rem 0.35rem;border-radius:3px;font-size:0.62rem;font-weight:700;">🚨 MEGALODON</span>` :
                        (isWhale ? ` <span style="background:rgba(245,158,11,0.25);color:#f59e0b;padding:0.1rem 0.35rem;border-radius:3px;font-size:0.62rem;font-weight:700;">🐋 WHALE</span>` : '')) +
                       (isLiq ? ` <span style="background:#ef4444;color:#fff;padding:0.1rem 0.35rem;border-radius:3px;font-size:0.62rem;font-weight:700;">🔥 LIQ</span>` : '');

      feed.insertBefore(item, feed.firstChild);
      while (feed.children.length > 20) {{
        feed.removeChild(feed.lastChild);
      }}
    }}

    // Direct Hyperliquid WebSocket client
    let termWs = null;
    function connectTerminalWS() {{
      try {{
        termWs = new WebSocket('wss://api.hyperliquid.xyz/ws');
        termWs.onopen = () => {{
          const b = document.getElementById('wsStatusBadge');
          const t = document.getElementById('wsStatusText');
          if (b && t) {{
            b.style.background = 'rgba(16,185,129,0.15)';
            b.style.borderColor = 'rgba(16,185,129,0.35)';
            b.style.color = 'var(--accent-green)';
            t.textContent = 'LIVE WS CONNECTED';
          }}
          termWs.send(JSON.stringify({{method: "subscribe", subscription: {{type: "trades", coin: "HYPE"}}}}));
          termWs.send(JSON.stringify({{method: "subscribe", subscription: {{type: "allMids"}}}}));
        }};

        termWs.onmessage = (e) => {{
          try {{
            const msg = JSON.parse(e.data);
            if (msg.channel === 'trades' && msg.data) {{
              const trades = Array.isArray(msg.data) ? msg.data : [msg.data];
              trades.forEach(t => {{
                if (t.coin === 'HYPE') {{
                  onLivePriceUpdate(parseFloat(t.px));
                  addTradeToTape(t);
                }}
              }});
            }} else if (msg.channel === 'allMids' && msg.data && msg.data.mids && msg.data.mids.HYPE) {{
              onLivePriceUpdate(parseFloat(msg.data.mids.HYPE));
            }}
          }} catch(err) {{}}
        }};

        termWs.onclose = () => {{
          setTimeout(connectTerminalWS, 3000);
        }};
      }} catch(e) {{}}
    }}

    // Polling server /api/live for Air Pocket and Depth calculations
    async function pollLiveTelemetry() {{
      try {{
        const res = await fetch('/api/live');
        if (res.ok) {{
          const data = await res.json();
          if (data.spot) onLivePriceUpdate(data.spot);
          if (data.bids_2pct && document.getElementById('termBids2')) {{
            document.getElementById('termBids2').textContent = '$' + (data.bids_2pct / 1e6).toFixed(2) + 'M';
          }}
          if (data.asks_2pct && document.getElementById('termAsks2')) {{
            document.getElementById('termAsks2').textContent = '$' + (data.asks_2pct / 1e6).toFixed(2) + 'M';
          }}
          if (data.oi_usd && document.getElementById('termOiBadge')) {{
            document.getElementById('termOiBadge').textContent = '$' + (data.oi_usd / 1e6).toFixed(1) + 'M';
          }}

          const badge = document.getElementById('airPocketCardBadge');
          const main = document.getElementById('termAirPocketMain');
          const desc = document.getElementById('termAirPocketDesc');
          if (badge && main && desc && data.air_pocket_status) {{
            if (data.air_pocket_long || data.air_pocket_short) {{
              badge.className = 'risk-badge risk-high';
              badge.textContent = '⚠️ AIR POCKET';
              main.textContent = 'VOID GAP';
              main.style.color = 'var(--accent-red)';
              desc.textContent = data.air_pocket_status;
            }} else {{
              badge.className = 'risk-badge risk-low';
              badge.textContent = '🛡️ SOUND';
              main.textContent = 'HEALTHY';
              main.style.color = 'var(--accent-green)';
              desc.textContent = data.air_pocket_status;
            }}
          }}
          if (data.internal_ip && document.getElementById('footerInternalIp')) {{
            document.getElementById('footerInternalIp').textContent = data.internal_ip;
          }}
          if (data.external_ip && document.getElementById('footerExternalIp')) {{
            document.getElementById('footerExternalIp').textContent = data.external_ip;
          }}
        }}
      }} catch(e) {{}}
    }}

    async function refreshLive() {{
      const btn = document.getElementById('syncBtn');
      btn.disabled = true;
      btn.style.opacity = '0.6';
      btn.textContent = '⏳ Syncing...';
      try {{
        const res = await fetch('/api/refresh', {{ method: 'POST' }});
        if (res.ok) {{
          btn.textContent = 'Reloading...';
          setTimeout(() => window.location.reload(), 800);
        }} else {{
          btn.textContent = 'Sync Failed';
          btn.disabled = false;
          btn.style.opacity = '1';
        }}
      }} catch (e) {{
        btn.textContent = 'Sync Error';
        btn.disabled = false;
        btn.style.opacity = '1';
      }}
    }}

    connectTerminalWS();
    setInterval(pollLiveTelemetry, 2500);
    pollLiveTelemetry();
  </script>
</body>
</html>
"""
    out_path.write_text(html_content, encoding="utf-8")
    return out_path
