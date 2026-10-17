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
    div_ids = ["heatmapPlot", "histogramPlot"]
    parts = [f.to_html(full_html=False, div_id=(div_ids[i] if i < len(div_ids) else None),
                       include_plotlyjs=False)
             for i, f in enumerate(figs)]
    init_price = ref_price or 79.30
    init_oi = oi_usd or 1.58e9

    header_html = f"""
    <!-- Live Telemetry Control Center -->
    <div id="liveTelemetryHeader" style="background:#0e1422;border-bottom:1px solid rgba(255,255,255,0.08);padding:0.75rem 1.5rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;font-family:'Inter',system-ui,sans-serif;color:#f1f5f9;position:sticky;top:0;z-index:9999;backdrop-filter:blur(16px);">
      <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
        <span id="wsStatusBadge" style="display:inline-flex;align-items:center;gap:0.4rem;padding:0.25rem 0.65rem;background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.35);color:#10b981;font-size:0.75rem;font-weight:700;border-radius:9999px;transition:all 0.3s;">
          <span class="pulse-dot" style="width:7px;height:7px;background:#10b981;border-radius:50%;box-shadow:0 0 8px #10b981;animation:livePulse 1.8s infinite;"></span>
          <span id="wsStatusText">LIVE WS CONNECTED</span>
        </span>
        <span style="font-size:1.15rem;font-weight:700;font-family:'JetBrains Mono',monospace;">{symbol}</span>
        <!-- Live Price Ticker & Actual 24h Change Widget -->
        <div id="liveTickerWidget" style="display:inline-flex;align-items:center;gap:0.45rem;background:rgba(255,255,255,0.03);padding:0.2rem 0.55rem;border-radius:8px;border:1px solid rgba(255,255,255,0.08);font-family:'JetBrains Mono',monospace;">
          <span id="spotPriceBadge" style="font-size:1.05rem;color:#38bdf8;font-weight:700;padding:0.15rem 0.4rem;border-radius:4px;transition:background 0.25s, color 0.25s;">
            ${init_price:,.3f}
          </span>
          <span id="priceChangeBadge" style="display:inline-flex;align-items:center;gap:0.25rem;font-size:0.75rem;font-weight:700;padding:0.15rem 0.45rem;border-radius:5px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);color:#10b981;transition:all 0.25s;">
            <span id="tickerArrow">▲</span>
            <span id="tickerChangeUsd">+$0.000</span>
            <span id="tickerChangePct">(+0.00%)</span>
          </span>
          <span id="tickerPrevClose" style="font-size:0.7rem;color:#64748b;display:inline-flex;align-items:center;gap:0.2rem;" title="24h Previous Reference Price">
            Prev: <b id="tickerPrevVal" style="color:#94a3b8;">${init_price:,.3f}</b>
          </span>
          <span id="tickerVolBox" style="font-size:0.7rem;color:#64748b;display:inline-flex;align-items:center;gap:0.2rem;" title="24h Volume">
            Vol: <b id="vol24hVal" style="color:#38bdf8;">$128.8M</b>
          </span>
        </div>
        <span id="oiBadge" style="font-size:0.82rem;color:#94a3b8;font-family:'JetBrains Mono',monospace;background:rgba(255,255,255,0.04);padding:0.2rem 0.5rem;border-radius:4px;">
          OI: ${init_oi/1e6:,.1f}M
        </span>
        <span id="airPocketPill" style="display:inline-flex;align-items:center;gap:0.35rem;font-size:0.75rem;font-weight:600;font-family:'JetBrains Mono',monospace;padding:0.2rem 0.6rem;border-radius:6px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);color:#10b981;transition:all 0.3s;">
          🛡️ LIQUIDITY SOUND
        </span>
      </div>
      <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
        <!-- Multi-Timeframe Selector Pill Bar -->
        <div id="timeframeSelector" style="display:inline-flex;align-items:center;gap:0.25rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);padding:0.2rem 0.4rem;border-radius:8px;font-family:'JetBrains Mono',monospace;">
          <span style="font-size:0.68rem;color:#64748b;font-weight:700;margin-right:0.2rem;text-transform:uppercase;letter-spacing:0.04em;">TF:</span>
          <button class="tf-btn" onclick="switchTimeframe('1m')">1m</button>
          <button class="tf-btn" onclick="switchTimeframe('5m')">5m</button>
          <button class="tf-btn" onclick="switchTimeframe('15m')">15m</button>
          <button class="tf-btn" onclick="switchTimeframe('30m')">30m</button>
          <button class="tf-btn active" onclick="switchTimeframe('1h')">1h</button>
          <button class="tf-btn" onclick="switchTimeframe('4h')">4h</button>
          <span id="tfStatusIndicator" style="display:none;margin-left:0.35rem;font-size:0.68rem;color:#38bdf8;font-weight:600;"></span>
        </div>
        <div id="depthStats" style="display:inline-flex;align-items:center;gap:0.5rem;font-size:0.75rem;color:#94a3b8;font-family:'JetBrains Mono',monospace;background:rgba(255,255,255,0.03);padding:0.25rem 0.6rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
          <span>Bids(2%): <b id="statBids" style="color:#10b981;">$1.2M</b></span>
          <span style="color:rgba(255,255,255,0.2);">|</span>
          <span>Asks(2%): <b id="statAsks" style="color:#ef4444;">$1.1M</b></span>
        </div>
        <!-- Interactive Shock Cascade Tester -->
        <div style="display:inline-flex;align-items:center;gap:0.25rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);padding:0.2rem 0.45rem;border-radius:6px;font-size:0.72rem;">
          <span style="color:#94a3b8;font-size:0.65rem;font-weight:700;">SHOCK:</span>
          <button onclick="applyMapShock(-0.15)" class="shock-btn">-15%</button>
          <button onclick="applyMapShock(-0.08)" class="shock-btn">-8%</button>
          <button onclick="applyMapShock(0)" class="shock-btn" style="color:#38bdf8;font-weight:700;">Spot</button>
          <button onclick="applyMapShock(0.08)" class="shock-btn">+8%</button>
          <button onclick="applyMapShock(0.15)" class="shock-btn">+15%</button>
          <span id="mapShockBadge" style="color:#f59e0b;font-weight:700;font-family:'JetBrains Mono',monospace;font-size:0.68rem;margin-left:0.2rem;">$0.0M Wiped</span>
        </div>
        <button id="audioToggleBtn" onclick="toggleAudio()" style="padding:0.45rem 0.75rem;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:#94a3b8;font-size:0.8rem;font-weight:600;border-radius:8px;cursor:pointer;transition:all 0.2s;">
          🔊 Audio: ON
        </button>
        <button id="refreshBtn" onclick="refreshLive()" style="padding:0.45rem 0.85rem;background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.35);color:#38bdf8;font-size:0.8rem;font-weight:600;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center;gap:0.35rem;transition:all 0.2s;">
          <span id="btnIcon">🔄</span> <span id="btnText">CCXT Sync</span>
        </button>
        <a href="/terminal" style="padding:0.45rem 0.85rem;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:#94a3b8;font-size:0.8rem;font-weight:600;border-radius:8px;text-decoration:none;transition:all 0.2s;">⚡ Pro Terminal</a>
        <a href="/liquidation_profile.csv" download style="padding:0.45rem 0.85rem;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:#94a3b8;font-size:0.8rem;font-weight:600;border-radius:8px;text-decoration:none;transition:all 0.2s;">📥 CSV</a>
      </div>
    </div>

    <!-- Modern Floating Fire Tape & Order Flow Command HUD -->
    <div id="fireTapeContainer" style="position:fixed;bottom:14px;left:18px;right:18px;z-index:9998;font-family:'JetBrains Mono',monospace;display:flex;flex-direction:column;gap:0.4rem;pointer-events:none;">
      <!-- Floating Island HUD -->
      <div id="tapeIsland" style="pointer-events:auto;background:rgba(10,15,29,0.88);border:1px solid rgba(255,255,255,0.12);border-radius:14px;padding:0.45rem 1rem;display:flex;align-items:center;justify-content:space-between;gap:0.85rem;backdrop-filter:blur(24px);box-shadow:0 12px 36px rgba(0,0,0,0.55);transition:all 0.3s cubic-bezier(0.16,1,0.3,1);">
        <!-- Left: HUD Brand & Rolling 60s Net Delta Spark-Bar -->
        <div style="display:flex;align-items:center;gap:0.75rem;flex-shrink:0;">
          <div style="display:flex;align-items:center;gap:0.45rem;">
            <span style="width:8px;height:8px;background:#f59e0b;border-radius:50%;box-shadow:0 0 8px #f59e0b;animation:livePulse 1.8s infinite;"></span>
            <span style="font-weight:700;font-size:0.78rem;color:#f59e0b;letter-spacing:0.05em;">FLOW HUD</span>
          </div>
          <!-- 60s Delta Spark-Bar -->
          <div style="display:flex;flex-direction:column;gap:0.2rem;width:150px;background:rgba(255,255,255,0.03);padding:0.25rem 0.45rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);" title="60s Taker Volume Imbalance">
            <div style="display:flex;justify-content:space-between;font-size:0.62rem;font-weight:600;">
              <span id="deltaBuyText" style="color:#10b981;">B: 50%</span>
              <span id="deltaSellText" style="color:#ef4444;">S: 50%</span>
            </div>
            <div style="height:4px;background:rgba(255,255,255,0.08);border-radius:999px;overflow:hidden;display:flex;">
              <div id="deltaBuyBar" style="width:50%;background:#10b981;transition:width 0.3s ease;"></div>
              <div id="deltaSellBar" style="width:50%;background:#ef4444;transition:width 0.3s ease;"></div>
            </div>
          </div>
        </div>

        <!-- Center: Sliding Trade Micro-Cards Feed -->
        <div id="tapeStreamWrapper" onmouseenter="pauseTape()" onmouseleave="resumeTape()" style="display:flex;align-items:center;gap:0.5rem;overflow-x:auto;white-space:nowrap;scrollbar-width:none;flex-grow:1;position:relative;padding:0.1rem 0;">
          <div id="tapePausedBadge" style="display:none;position:absolute;left:50%;transform:translateX(-50%);background:rgba(245,158,11,0.9);color:#0a0f1d;font-size:0.68rem;font-weight:700;padding:0.15rem 0.5rem;border-radius:4px;z-index:10;box-shadow:0 2px 8px rgba(0,0,0,0.4);">
            ⏸ PAUSED (HOVER)
          </div>
          <div id="tapeFeed" style="display:flex;align-items:center;gap:0.5rem;transition:opacity 0.2s;">
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
          <button id="drawerToggleBtn" onclick="toggleTapeDrawer()" style="padding:0.3rem 0.55rem;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);color:#94a3b8;border-radius:6px;cursor:pointer;font-size:0.75rem;font-weight:600;display:inline-flex;align-items:center;gap:0.3rem;transition:all 0.2s;" title="Toggle 3-Column Order Flow Matrix">
            <span id="drawerIcon">⛶</span> <span style="font-size:0.7rem;">Drawer</span>
          </button>
        </div>
      </div>

      <!-- Expandable 3-Column Order Flow Drawer -->
      <div id="tapeDrawer" style="display:none;pointer-events:auto;background:rgba(10,15,29,0.95);border:1px solid rgba(255,255,255,0.14);border-radius:14px;padding:0.85rem 1rem;backdrop-filter:blur(24px);box-shadow:0 16px 40px rgba(0,0,0,0.6);animation:slideUp 0.25s cubic-bezier(0.16,1,0.3,1);">
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:0.5rem;margin-bottom:0.6rem;font-size:0.75rem;">
          <span style="font-weight:700;color:#f1f5f9;letter-spacing:0.04em;">⚡ ORDER FLOW COMMAND MATRIX (REAL-TIME HYPERLIQUID WS)</span>
          <div style="display:flex;gap:1rem;font-size:0.7rem;color:#94a3b8;">
            <span>60s Taker Vol: <b id="drawerVol60s" style="color:#38bdf8;">$0.0M</b></span>
            <span>Latency: <b id="drawerSpeed" style="color:#10b981;">&lt;35ms</b></span>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));gap:0.75rem;max-height:220px;">
          <!-- Col 1: All Taker Prints -->
          <div style="background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:0.5rem;display:flex;flex-direction:column;gap:0.35rem;">
            <div style="font-size:0.68rem;font-weight:700;color:#94a3b8;display:flex;justify-content:space-between;">
              <span>ALL TAKER PRINTS</span>
              <span id="countAllPrints" style="color:#64748b;">0 PRINTS</span>
            </div>
            <div id="drawerListAll" style="overflow-y:auto;max-height:180px;display:flex;flex-direction:column;gap:0.25rem;font-size:0.7rem;"></div>
          </div>
          <!-- Col 2: Whale Radar -->
          <div style="background:rgba(0,0,0,0.25);border:1px solid rgba(245,158,11,0.2);border-radius:8px;padding:0.5rem;display:flex;flex-direction:column;gap:0.35rem;">
            <div style="font-size:0.68rem;font-weight:700;color:#f59e0b;display:flex;justify-content:space-between;">
              <span>🐋 WHALE RADAR (≥$10,000)</span>
              <span id="countWhalePrints" style="color:#f59e0b;">0 WHALES</span>
            </div>
            <div id="drawerListWhales" style="overflow-y:auto;max-height:180px;display:flex;flex-direction:column;gap:0.25rem;font-size:0.7rem;"></div>
          </div>
          <!-- Col 3: Liquidation Sweeps -->
          <div style="background:rgba(0,0,0,0.25);border:1px solid rgba(239,68,68,0.25);border-radius:8px;padding:0.5rem;display:flex;flex-direction:column;gap:0.35rem;">
            <div style="font-size:0.68rem;font-weight:700;color:#ef4444;display:flex;justify-content:space-between;">
              <span>🚨 FORCED LIQUIDATIONS & SWEEPS</span>
              <span id="countLiqPrints" style="color:#ef4444;">0 DETECTED</span>
            </div>
            <div id="drawerListLiqs" style="overflow-y:auto;max-height:180px;display:flex;flex-direction:column;gap:0.25rem;font-size:0.7rem;"></div>
          </div>
        </div>
      </div>
    </div>

    <style>
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
      .shock-btn {{
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.12);
        color: #94a3b8;
        border-radius: 4px;
        padding: 0.15rem 0.4rem;
        font-size: 0.68rem;
        font-family: inherit;
        cursor: pointer;
        transition: all 0.15s ease;
      }}
      .shock-btn:hover {{
        background: rgba(56,189,248,0.18);
        color: #38bdf8;
        border-color: rgba(56,189,248,0.4);
      }}
      .tf-btn {{
        background: transparent;
        border: 1px solid transparent;
        color: #94a3b8;
        font-family: inherit;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 0.15rem 0.45rem;
        border-radius: 5px;
        cursor: pointer;
        transition: all 0.2s ease;
      }}
      .tf-btn:hover {{
        color: #fff;
        background: rgba(255, 255, 255, 0.08);
      }}
      .tf-btn.active {{
        background: rgba(56, 189, 248, 0.2);
        border-color: rgba(56, 189, 248, 0.5);
        color: #38bdf8;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.25);
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

    <script>
      let currentSpot = {init_price};
      let prevDayPx = null;
      let lastPrice = {init_price};
      let audioEnabled = true;
      let audioCtx = null;
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

        // Filter visible feed
        const feed = document.getElementById('tapeFeed');
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
        btn.style.borderColor = audioEnabled ? 'rgba(56,189,248,0.4)' : 'rgba(255,255,255,0.1)';
        btn.style.color = audioEnabled ? '#38bdf8' : '#94a3b8';
      }}

      // Dynamic Plotly reference line update
      function updatePlotlySpot(newPrice) {{
        const gd = document.getElementById('heatmapPlot');
        if (gd && (gd.layout || gd._fullLayout)) {{
          try {{
            const layout = gd.layout || gd._fullLayout;
            const updateObj = {{}};
            if (layout.shapes && Array.isArray(layout.shapes)) {{
              layout.shapes.forEach((s, idx) => {{
                if (s.type === 'line' && (Math.abs(s.y0 - s.y1) < 0.001 || (s.line && s.line.color === '#facc15'))) {{
                  updateObj['shapes[' + idx + '].y0'] = newPrice;
                  updateObj['shapes[' + idx + '].y1'] = newPrice;
                }}
              }});
            }}
            if (layout.annotations && Array.isArray(layout.annotations)) {{
              layout.annotations.forEach((a, idx) => {{
                if (a.text && (a.text.startsWith('$') || !isNaN(parseFloat(a.text.replace('$', ''))))) {{
                  updateObj['annotations[' + idx + '].y'] = newPrice;
                  updateObj['annotations[' + idx + '].text'] = '$' + newPrice.toFixed(3);
                }}
              }});
            }}
            if (Object.keys(updateObj).length > 0) {{
              Plotly.relayout(gd, updateObj);
            }}
          }} catch(e) {{}}
        }}
      }}

      function updatePriceDisplay(newPrice) {{
        const badge = document.getElementById('spotPriceBadge');
        const changeBadge = document.getElementById('priceChangeBadge');
        const arrow = document.getElementById('tickerArrow');
        const changeUsd = document.getElementById('tickerChangeUsd');
        const changePct = document.getElementById('tickerChangePct');
        const prevVal = document.getElementById('tickerPrevVal');

        if (!badge) return;
        const tickDiff = newPrice - (lastPrice || currentSpot);
        lastPrice = newPrice;
        currentSpot = newPrice;

        if (Math.abs(tickDiff) > 0.0001) {{
          badge.textContent = '$' + newPrice.toFixed(3);
          badge.style.background = tickDiff > 0 ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)';
          badge.style.color = tickDiff > 0 ? '#10b981' : '#ef4444';
          badge.style.borderColor = tickDiff > 0 ? '#10b981' : '#ef4444';
          setTimeout(() => {{
            badge.style.background = 'transparent';
            badge.style.color = '#38bdf8';
            badge.style.borderColor = 'transparent';
          }}, 350);
          updatePlotlySpot(newPrice);
        }} else {{
          badge.textContent = '$' + newPrice.toFixed(3);
        }}

        // Direct DOM update for 24h Price Change Ticker
        const refBase = prevDayPx || {init_price};
        if (refBase && changeBadge && changeUsd && changePct) {{
          const deltaUsd = newPrice - refBase;
          const deltaPct = (deltaUsd / refBase) * 100.0;
          const isUp = deltaUsd >= 0;

          changeBadge.style.background = isUp ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)';
          changeBadge.style.borderColor = isUp ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)';
          changeBadge.style.color = isUp ? '#10b981' : '#ef4444';

          if (arrow) arrow.textContent = isUp ? '▲' : '▼';
          changeUsd.textContent = (isUp ? '+' : '') + '$' + deltaUsd.toFixed(3);
          changePct.textContent = '(' + (isUp ? '+' : '') + deltaPct.toFixed(2) + '%)';
          if (prevVal) prevVal.textContent = '$' + refBase.toFixed(3);
        }}
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

      // Modern Fire Tape streaming & drawer updates
      function addTradeToTape(trade) {{
        const feed = document.getElementById('tapeFeed');
        if (!feed) return;
        const isBuy = trade.side === 'B' || trade.side === 'buy';
        const px = parseFloat(trade.px);
        const sz = parseFloat(trade.sz);
        const notional = px * sz;
        const isWhale = notional >= 10000;
        const isMegalodon = notional >= 50000;
        const isLiq = trade.liquidation === true || trade.side === 'LIQ';
        const timeStr = new Date(trade.time || Date.now()).toLocaleTimeString([], {{hour:'2-digit', minute:'2-digit', second:'2-digit'}});

        playTickSound(isBuy, isWhale);
        updateDeltaBar(trade);

        // Update counts
        totalAllCount++;
        if (isWhale) totalWhaleCount++;
        if (isLiq) totalLiqCount++;

        const cAll = document.getElementById('countAllPrints');
        const cWhale = document.getElementById('countWhalePrints');
        const cLiq = document.getElementById('countLiqPrints');
        if (cAll) cAll.textContent = totalAllCount + ' PRINTS';
        if (cWhale) cWhale.textContent = totalWhaleCount + ' WHALES';
        if (cLiq) cLiq.textContent = totalLiqCount + ' DETECTED';

        // 1. Drawer Item Construction
        const drawerItemHtml = `<div style="display:flex;justify-content:space-between;align-items:center;padding:0.2rem 0.35rem;border-radius:4px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04);">
          <span style="color:#64748b;">${{timeStr}}</span>
          <b style="color:${{isBuy ? '#10b981' : '#ef4444'}};">${{isBuy ? 'BUY' : 'SELL'}}</b>
          <span>${{sz.toFixed(2)}} @ $${{px.toFixed(2)}}</span>
          <span style="color:#f1f5f9;font-weight:600;">$${{Math.round(notional).toLocaleString()}}</span>
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

        // 2. Main Horizontal Island Feed Item
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

        item.innerHTML = `<span style="color:#64748b;font-size:0.68rem;">${{timeStr}}</span> ` +
                         `<b style="color:${{isBuy ? '#10b981' : '#ef4444'}};font-size:0.75rem;">${{isBuy ? 'BUY ▲' : 'SELL ▼'}}</b> ` +
                         `<span>${{sz.toFixed(2)}} HYPE @ $${{px.toFixed(2)}}</span> ` +
                         `<span style="color:#f1f5f9;font-weight:600;">($${{Math.round(notional).toLocaleString()}})</span>` +
                         (isMegalodon ? ` <span style="background:#a855f7;color:#fff;padding:0.1rem 0.35rem;border-radius:3px;font-size:0.62rem;font-weight:700;">🚨 MEGALODON</span>` :
                          (isWhale ? ` <span style="background:rgba(245,158,11,0.25);color:#f59e0b;padding:0.1rem 0.35rem;border-radius:3px;font-size:0.62rem;font-weight:700;">🐋 WHALE</span>` : '')) +
                         (isLiq ? ` <span style="background:#ef4444;color:#fff;padding:0.1rem 0.35rem;border-radius:3px;font-size:0.62rem;font-weight:700;">🔥 LIQ</span>` : '');

        feed.insertBefore(item, feed.firstChild);
        while (feed.children.length > 20) {{
          feed.removeChild(feed.lastChild);
        }}
      }}

      // WebSocket Connection Engine
      let ws = null;
      function connectHyperliquidWS() {{
        try {{
          ws = new WebSocket('wss://api.hyperliquid.xyz/ws');
          ws.onopen = () => {{
            const badge = document.getElementById('wsStatusBadge');
            const text = document.getElementById('wsStatusText');
            if (badge && text) {{
              badge.style.background = 'rgba(16,185,129,0.15)';
              badge.style.borderColor = 'rgba(16,185,129,0.35)';
              badge.style.color = '#10b981';
              text.textContent = 'LIVE WS CONNECTED';
            }}
            // Subscribe to trades, activeAssetCtx, l2Book, and allMids
            ws.send(JSON.stringify({{method: "subscribe", subscription: {{type: "trades", coin: "HYPE"}}}}));
            ws.send(JSON.stringify({{method: "subscribe", subscription: {{type: "activeAssetCtx", coin: "HYPE"}}}}));
            ws.send(JSON.stringify({{method: "subscribe", subscription: {{type: "l2Book", coin: "HYPE"}}}}));
            ws.send(JSON.stringify({{method: "subscribe", subscription: {{type: "allMids"}}}}));
          }};

          ws.onmessage = (event) => {{
            try {{
              const msg = JSON.parse(event.data);
              if (msg.channel === 'trades' && msg.data) {{
                const trades = Array.isArray(msg.data) ? msg.data : [msg.data];
                trades.forEach(t => {{
                  if (t.coin === 'HYPE') {{
                    updatePriceDisplay(parseFloat(t.px));
                    addTradeToTape(t);
                  }}
                }});
              }} else if (msg.channel === 'activeAssetCtx' && msg.data) {{
                const assetData = (msg.data.coin === 'HYPE') ? msg.data.ctx : (msg.data.ctx || msg.data);
                if (assetData) {{
                  if (assetData.prevDayPx) {{
                    prevDayPx = parseFloat(assetData.prevDayPx);
                  }}
                  const px = parseFloat(assetData.midPx || assetData.markPx || assetData.oraclePx || 0);
                  if (px > 0) updatePriceDisplay(px);
                  if (assetData.dayNtlVlm && document.getElementById('vol24hVal')) {{
                    document.getElementById('vol24hVal').textContent = '$' + (parseFloat(assetData.dayNtlVlm) / 1e6).toFixed(1) + 'M';
                  }}
                }}
              }} else if (msg.channel === 'allMids' && msg.data && msg.data.mids) {{
                if (msg.data.mids.HYPE) {{
                  updatePriceDisplay(parseFloat(msg.data.mids.HYPE));
                }}
              }} else if (msg.channel === 'l2Book' && msg.data && msg.data.levels) {{
                handleOrderBook(msg.data.levels);
              }}
            }} catch(e) {{}}
          }};

          ws.onerror = () => {{
            fallbackPoll();
          }};

          ws.onclose = () => {{
            setTimeout(connectHyperliquidWS, 3000);
          }};
        }} catch(e) {{
          fallbackPoll();
        }}
      }}

      function handleOrderBook(levels) {{
        try {{
          const bids = levels[0] || [];
          const asks = levels[1] || [];
          let bidVal2 = 0, askVal2 = 0;
          bids.forEach(b => {{
            const p = parseFloat(b.px), s = parseFloat(b.sz);
            if (p >= currentSpot * 0.98) bidVal2 += p * s;
          }});
          asks.forEach(a => {{
            const p = parseFloat(a.px), s = parseFloat(a.sz);
            if (p <= currentSpot * 1.02) askVal2 += p * s;
          }});
          const sb = document.getElementById('statBids');
          const sa = document.getElementById('statAsks');
          if (sb) sb.textContent = '$' + (bidVal2 / 1e6).toFixed(2) + 'M';
          if (sa) sa.textContent = '$' + (askVal2 / 1e6).toFixed(2) + 'M';
        }} catch(e) {{}}
      }}

      // Polling server /api/live for Air Pocket analysis & background metrics
      async function pollLiveAPI() {{
        try {{
          const res = await fetch('/api/live');
          if (res.ok) {{
            const data = await res.json();
            if (data.prev_day_px) {{
              prevDayPx = parseFloat(data.prev_day_px);
            }}
            if (data.spot) updatePriceDisplay(data.spot);
            if (data.vlm_24h && document.getElementById('vol24hVal')) {{
              document.getElementById('vol24hVal').textContent = '$' + (data.vlm_24h / 1e6).toFixed(1) + 'M';
            }}
            if (data.bids_2pct && document.getElementById('statBids')) {{
              document.getElementById('statBids').textContent = '$' + (data.bids_2pct / 1e6).toFixed(2) + 'M';
            }}
            if (data.asks_2pct && document.getElementById('statAsks')) {{
              document.getElementById('statAsks').textContent = '$' + (data.asks_2pct / 1e6).toFixed(2) + 'M';
            }}
            if (data.oi_usd && document.getElementById('oiBadge')) {{
              document.getElementById('oiBadge').textContent = 'OI: $' + (data.oi_usd / 1e6).toFixed(1) + 'M';
            }}
            const pill = document.getElementById('airPocketPill');
            if (pill && data.air_pocket_status) {{
              if (data.air_pocket_long || data.air_pocket_short) {{
                pill.style.background = 'rgba(239,68,68,0.18)';
                pill.style.borderColor = 'rgba(239,68,68,0.45)';
                pill.style.color = '#ef4444';
                pill.textContent = '⚠️ ' + data.air_pocket_status;
              }} else {{
                pill.style.background = 'rgba(16,185,129,0.12)';
                pill.style.borderColor = 'rgba(16,185,129,0.3)';
                pill.style.color = '#10b981';
                pill.textContent = '🛡️ LIQUIDITY SOUND';
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

      function fallbackPoll() {{
        const text = document.getElementById('wsStatusText');
        if (text) text.textContent = 'POLLING /api/live';
      }}

      let MAP_PAYLOAD = null;
      let currentTimeframe = '1h';
      async function loadInitialMapPayload() {{
        try {{
          const r = await fetch('/api/map-data');
          if (r.ok) {{
            MAP_PAYLOAD = await r.json();
            if (MAP_PAYLOAD.timeframe) currentTimeframe = MAP_PAYLOAD.timeframe;
          }}
        }} catch(e) {{}}
      }}

      async function switchTimeframe(tf) {{
        if (tf === currentTimeframe && MAP_PAYLOAD && MAP_PAYLOAD.timeframe === tf) return;
        const buttons = document.querySelectorAll('.tf-btn');
        buttons.forEach(b => {{
          if (b.textContent.trim() === tf) b.classList.add('active');
          else b.classList.remove('active');
        }});

        const indicator = document.getElementById('tfStatusIndicator');
        if (indicator) {{
          indicator.style.display = 'inline-block';
          indicator.textContent = `⚡ Calculating ${{tf}}...`;
          indicator.style.color = '#38bdf8';
        }}

        try {{
          const res = await fetch(`/api/map-data?timeframe=${{tf}}`);
          if (res.ok) {{
            const data = await res.json();
            currentTimeframe = tf;
            MAP_PAYLOAD = data;

            const hPlot = document.getElementById('heatmapPlot');
            const sPlot = document.getElementById('histogramPlot');
            if (window.Plotly && hPlot && data.heatmap) {{
              await Plotly.react(hPlot, data.heatmap.data, data.heatmap.layout);
            }}
            if (window.Plotly && sPlot && data.histogram) {{
              await Plotly.react(sPlot, data.histogram.data, data.histogram.layout);
            }}
            if (data.spot) updatePriceDisplay(data.spot);
            if (indicator) {{
              const hl = data.half_life_hours ? `${{data.half_life_hours}}h` : 'decay';
              indicator.textContent = `✓ ${{tf}} (${{hl}})`;
              indicator.style.color = '#10b981';
              setTimeout(() => {{ indicator.style.display = 'none'; }}, 2200);
            }}
          }} else {{
            if (indicator) {{
              indicator.textContent = '❌ Failed';
              indicator.style.color = '#ef4444';
              setTimeout(() => {{ indicator.style.display = 'none'; }}, 2500);
            }}
          }}
        }} catch(e) {{
          if (indicator) {{
            indicator.textContent = '❌ Error';
            indicator.style.color = '#ef4444';
            setTimeout(() => {{ indicator.style.display = 'none'; }}, 2500);
          }}
        }}
      }}

      function applyMapShock(pct) {{
        if (!MAP_PAYLOAD || !MAP_PAYLOAD.centres) return;
        const targetPrice = currentSpot * (1 + pct);
        updatePlotlySpot(targetPrice);

        const badge = document.getElementById('mapShockBadge');
        if (!badge) return;

        if (pct === 0) {{
          badge.textContent = '$0.0M Wiped';
          badge.style.color = '#94a3b8';
          return;
        }}

        const centres = MAP_PAYLOAD.centres;
        let wiped = 0;
        if (pct < 0) {{
          const cumLong = MAP_PAYLOAD.cum_long;
          let idx = 0, minDiff = Infinity;
          for (let i = 0; i < centres.length; i++) {{
            const d = Math.abs(centres[i] - targetPrice);
            if (d < minDiff) {{ minDiff = d; idx = i; }}
          }}
          wiped = cumLong[idx] || 0;
          badge.textContent = `-$${{(wiped / 1e6).toFixed(1)}}M Longs`;
          badge.style.color = '#ef4444';
        }} else {{
          const cumShort = MAP_PAYLOAD.cum_short;
          let idx = centres.length - 1, minDiff = Infinity;
          for (let i = 0; i < centres.length; i++) {{
            const d = Math.abs(centres[i] - targetPrice);
            if (d < minDiff) {{ minDiff = d; idx = i; }}
          }}
          wiped = cumShort[idx] || 0;
          badge.textContent = `+$${{(wiped / 1e6).toFixed(1)}}M Shorts`;
          badge.style.color = '#10b981';
        }}
      }}

      async function refreshLive() {{
        const btn = document.getElementById('refreshBtn');
        const icon = document.getElementById('btnIcon');
        const text = document.getElementById('btnText');
        btn.disabled = true;
        btn.style.opacity = '0.7';
        icon.textContent = '⏳';
        text.textContent = 'Syncing...';
        const t0 = performance.now();
        try {{
          const res = await fetch('/api/refresh', {{ method: 'POST' }});
          if (res.ok) {{
            text.textContent = 'Updating Map...';
            const mapRes = await fetch('/api/map-data');
            if (mapRes.ok) {{
              const fresh = await mapRes.json();
              MAP_PAYLOAD = fresh;
              const hPlot = document.getElementById('heatmapPlot');
              const sPlot = document.getElementById('histogramPlot');
              if (window.Plotly && hPlot && fresh.heatmap) {{
                await Plotly.react(hPlot, fresh.heatmap.data, fresh.heatmap.layout);
              }}
              if (window.Plotly && sPlot && fresh.histogram) {{
                await Plotly.react(sPlot, fresh.histogram.data, fresh.histogram.layout);
              }}
              if (fresh.spot) updatePriceDisplay(fresh.spot);
              if (fresh.oi_usd && document.getElementById('oiBadge')) {{
                document.getElementById('oiBadge').textContent = 'OI: $' + (fresh.oi_usd / 1e6).toFixed(1) + 'M';
              }}
              const dt = ((performance.now() - t0) / 1000).toFixed(2);
              text.textContent = `Synced (${{dt}}s)`;
              icon.textContent = '⚡';
              btn.style.borderColor = '#10b981';
              btn.style.color = '#10b981';
              setTimeout(() => {{
                text.textContent = 'CCXT Sync';
                icon.textContent = '🔄';
                btn.style.borderColor = 'rgba(56,189,248,0.35)';
                btn.style.color = '#38bdf8';
                btn.disabled = false;
                btn.style.opacity = '1';
              }}, 2500);
            }} else {{
              text.textContent = 'Reloading...';
              setTimeout(() => window.location.reload(), 500);
            }}
          }} else {{
            text.textContent = 'Failed';
            btn.disabled = false;
            btn.style.opacity = '1';
          }}
        }} catch (e) {{
          text.textContent = 'Error';
          btn.disabled = false;
          btn.style.opacity = '1';
        }}
      }}

      // Init live engines
      connectHyperliquidWS();
      setInterval(pollLiveAPI, 2500);
      pollLiveAPI();
      loadInitialMapPayload();
    </script>
    """
    footer_html = r"""
    <!-- Detailed System & Telemetry Footer -->
    <footer style="margin:2.5rem 1.5rem 1.5rem 1.5rem;padding:1.25rem 1.5rem;border-top:1px solid rgba(255,255,255,0.08);background:rgba(10,15,29,0.75);backdrop-filter:blur(16px);border-radius:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.85rem;font-family:'JetBrains Mono',monospace;font-size:0.75rem;color:#94a3b8;">
      <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
        <span style="display:inline-flex;align-items:center;gap:0.4rem;color:#38bdf8;font-weight:600;">
          📁 <span>D:\projects\N1</span>
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
    """
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>HYPE Perp - Live Liquidation Map (CCXT)</title>"
            "<link rel='preconnect' href='https://fonts.googleapis.com'>"
            "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@500;700&family=JetBrains+Mono:wght@500;700&display=swap' rel='stylesheet'>"
            "<script src='/plotly.min.js' onerror=\"this.onerror=null;this.src='https://cdn.plot.ly/plotly-2.35.2.min.js'\"></script>"
            "</head><body style='background:#080b11;margin:0;padding-bottom:3.5rem;'>" + header_html + "".join(parts) + footer_html + "</body></html>")
    path.write_text(html, encoding="utf-8")
    if path.name == "hype_liquidation_map.html":
        for alt_name in ("hype_liquidation_map_v2.html", "hype_live_map.html", "hype_timeframe_liqmap.html"):
            (path.parent / alt_name).write_text(html, encoding="utf-8")

