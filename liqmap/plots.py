"""Plotly figures: Heatmap + candles + profile, and 2D histograms."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

TEMPLATE = "plotly_dark"
LONG_C, SHORT_C = "#ef4444", "#22c55e"


def _times(ohlcv: pd.DataFrame):
    return pd.to_datetime(ohlcv["timestamp"], unit="ms", utc=True)


def heatmap_figure(ohlcv, grids, ref_price, symbol, oi_usd) -> go.Figure:
    t = _times(ohlcv)
    y = grids["centres"]
    z = grids["heat_long"] + grids["heat_short"]
    zpos = z[z > 0]
    zmax = float(np.percentile(zpos, 99)) if zpos.size else 1.0
    zplot = np.where(z > 0, z, np.nan)
    bin_h = float(y[1] - y[0])

    fig = make_subplots(rows=1, cols=3, shared_yaxes=True, horizontal_spacing=0.01,
                        column_widths=[0.62, 0.19, 0.19],
                        subplot_titles=("Liquidation heatmap (live levels over time)",
                                        "Liquidation profile", "Cumulative"))
    fig.add_trace(go.Heatmap(x=t, y=y, z=zplot, zmin=0, zmax=zmax, colorscale="Plasma",
                             colorbar=dict(title="USD", x=1.04, len=0.8),
                             hovertemplate="%{x}<br>$%{y:.3f}<br>%{z:,.0f} USD<extra></extra>",
                             name="liq levels"), row=1, col=1)
    fig.add_trace(go.Candlestick(x=t, open=ohlcv["open"], high=ohlcv["high"],
                                 low=ohlcv["low"], close=ohlcv["close"],
                                 increasing_line_color="#e5e7eb", decreasing_line_color="#6b7280",
                                 name="price"), row=1, col=1)
    fig.add_trace(go.Bar(x=grids["profile_long"], y=y, orientation="h", width=bin_h,
                         marker_color=LONG_C, name="Long liq"), row=1, col=2)
    fig.add_trace(go.Bar(x=grids["profile_short"], y=y, orientation="h", width=bin_h,
                         marker_color=SHORT_C, name="Short liq"), row=1, col=2)
    fig.add_trace(go.Scatter(x=grids["cum_long"], y=y, mode="lines", fill="tozerox",
                             line=dict(color=LONG_C), name="Cum. longs",
                             hoverinfo="x+y"), row=1, col=3)
    fig.add_trace(go.Scatter(x=grids["cum_short"], y=y, mode="lines", fill="tozerox",
                             line=dict(color=SHORT_C), name="Cum. shorts",
                             hoverinfo="x+y"), row=1, col=3)
    fig.add_hline(y=ref_price, line=dict(color="#facc15", dash="dot", width=1),
                  annotation_text=f"{ref_price:.3f}", annotation_position="top left")
    fig.update_layout(template=TEMPLATE, barmode="overlay", height=760,
                      title=f"{symbol} - estimated liquidation map  |  OI per side: ${oi_usd/1e6:,.1f}M",
                      xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=-0.08))
    fig.update_yaxes(range=[y[0], y[-1]], title_text="Liquidation price", row=1, col=1)
    return fig


def histogram2d_figure(pos: pd.DataFrame, grids, symbol, n_time_bins: int = 60) -> go.Figure:
    """Plotly Histogram2d: entry time x liquidation price, weighted by notional (surviving only)."""
    e = grids["edges"]
    live = pos[pos["alive"] & (pos["liq_price"] >= e[0]) & (pos["liq_price"] < e[-1])]
    nby = max(20, len(grids["centres"]) // 2)
    ybins = dict(start=float(e[0]), end=float(e[-1]), size=float((e[-1] - e[0]) / nby))

    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.03,
                        subplot_titles=("Long liquidations (below price)",
                                        "Short liquidations (above price)"))
    for col, (side, scale) in enumerate((("long", "Reds"), ("short", "Greens")), start=1):
        s = live[live["side"] == side]
        fig.add_trace(go.Histogram2d(x=s["entry_time"], y=s["liq_price"], z=s["notional_usd"],
                                     histfunc="sum", nbinsx=n_time_bins, ybins=ybins,
                                     colorscale=scale, colorbar=dict(title="USD", x=0.46 if col == 1 else 1.02, len=0.8),
                                     hovertemplate="entry %{x}<br>liq $%{y:.3f}<br>%{z:,.0f} USD<extra></extra>"),
                      row=1, col=col)
    fig.update_layout(template=TEMPLATE, height=520,
                      title=f"{symbol} - Histogram2d: entry time vs liquidation price (surviving positions)")
    fig.update_yaxes(title_text="Liquidation price", row=1, col=1)
    fig.update_xaxes(title_text="Entry time")
    return fig


def write_html(path, figs: list[go.Figure], symbol: str = "HYPE/USDC:USDC",
               oi_usd: float | None = None, ref_price: float | None = None) -> None:
    parts = [f.to_html(full_html=False, include_plotlyjs=(True if i == 0 else False))
             for i, f in enumerate(figs)]
    header_html = f"""
    <div style="background:#0e1422;border-bottom:1px solid rgba(255,255,255,0.08);padding:0.75rem 1.5rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;font-family:'Inter',system-ui,sans-serif;color:#f1f5f9;position:sticky;top:0;z-index:9999;backdrop-filter:blur(16px);">
      <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
        <span style="display:inline-flex;align-items:center;gap:0.4rem;padding:0.25rem 0.65rem;background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.35);color:#10b981;font-size:0.75rem;font-weight:700;border-radius:9999px;">
          <span style="width:7px;height:7px;background:#10b981;border-radius:50%;box-shadow:0 0 8px #10b981;"></span> LIVE CCXT HYPERLIQUID PERP
        </span>
        <span style="font-size:1.15rem;font-weight:700;font-family:'JetBrains Mono',monospace;">{symbol}</span>
        {f'<span style="font-size:0.95rem;color:#38bdf8;font-family:\'JetBrains Mono\',monospace;font-weight:700;background:rgba(56,189,248,0.1);padding:0.15rem 0.5rem;border-radius:4px;">${ref_price:,.4f}</span>' if ref_price else ''}
        {f'<span style="font-size:0.82rem;color:#94a3b8;font-family:\'JetBrains Mono\',monospace;">OI: ${oi_usd/1e6:,.1f}M</span>' if oi_usd else ''}
      </div>
      <div style="display:flex;align-items:center;gap:0.5rem;">
        <button id="refreshBtn" onclick="refreshLive()" style="padding:0.45rem 0.9rem;background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.35);color:#38bdf8;font-size:0.82rem;font-weight:600;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center;gap:0.4rem;transition:all 0.2s;">
          <span id="btnIcon">🔄</span> <span id="btnText">Fetch Live CCXT Data</span>
        </button>
        <a href="/terminal" style="padding:0.45rem 0.9rem;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:#94a3b8;font-size:0.82rem;font-weight:600;border-radius:8px;text-decoration:none;transition:all 0.2s;">⚡ Pro Terminal</a>
        <a href="/liquidation_profile.csv" download style="padding:0.45rem 0.9rem;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:#94a3b8;font-size:0.82rem;font-weight:600;border-radius:8px;text-decoration:none;transition:all 0.2s;">📥 CSV</a>
      </div>
    </div>
    <script>
      async function refreshLive() {{
        const btn = document.getElementById('refreshBtn');
        const icon = document.getElementById('btnIcon');
        const text = document.getElementById('btnText');
        btn.disabled = true;
        btn.style.opacity = '0.6';
        icon.textContent = '⏳';
        text.textContent = 'Fetching CCXT Live Perp Data...';
        try {{
          const res = await fetch('/api/refresh', {{ method: 'POST' }});
          if (res.ok) {{
            text.textContent = 'Success! Reloading...';
            setTimeout(() => window.location.reload(), 800);
          }} else {{
            text.textContent = 'Fetch failed, retry';
            btn.disabled = false;
            btn.style.opacity = '1';
          }}
        }} catch (e) {{
          text.textContent = 'Error, retry';
          btn.disabled = false;
          btn.style.opacity = '1';
        }}
      }}
    </script>
    """
    html = ("<html><head><meta charset='utf-8'><title>HYPE Perp - Live Liquidation Map (CCXT)</title>"
            "<link rel='preconnect' href='https://fonts.googleapis.com'>"
            "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@500;700&family=JetBrains+Mono:wght@500;700&display=swap' rel='stylesheet'>"
            "</head><body style='background:#080b11;margin:0;'>" + header_html + "".join(parts) + "</body></html>")
    path.write_text(html, encoding="utf-8")
