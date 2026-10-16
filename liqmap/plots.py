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
        <span id="spotPriceBadge" style="font-size:1.05rem;color:#38bdf8;font-family:'JetBrains Mono',monospace;font-weight:700;background:rgba(56,189,248,0.1);padding:0.2rem 0.6rem;border-radius:6px;border:1px solid rgba(56,189,248,0.25);transition:background 0.3s, color 0.3s;">
          ${init_price:,.3f}
        </span>
        <span id="oiBadge" style="font-size:0.82rem;color:#94a3b8;font-family:'JetBrains Mono',monospace;background:rgba(255,255,255,0.04);padding:0.2rem 0.5rem;border-radius:4px;">
          OI: ${init_oi/1e6:,.1f}M
        </span>
        <span id="airPocketPill" style="display:inline-flex;align-items:center;gap:0.35rem;font-size:0.75rem;font-weight:600;font-family:'JetBrains Mono',monospace;padding:0.2rem 0.6rem;border-radius:6px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);color:#10b981;transition:all 0.3s;">
          🛡️ LIQUIDITY SOUND
        </span>
      </div>
      <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
        <div id="depthStats" style="display:inline-flex;align-items:center;gap:0.5rem;font-size:0.75rem;color:#94a3b8;font-family:'JetBrains Mono',monospace;background:rgba(255,255,255,0.03);padding:0.25rem 0.6rem;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
          <span>Bids(2%): <b id="statBids" style="color:#10b981;">$1.2M</b></span>
          <span style="color:rgba(255,255,255,0.2);">|</span>
          <span>Asks(2%): <b id="statAsks" style="color:#ef4444;">$1.1M</b></span>
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

    <!-- Live Trade & Liquidation Fire Tape (Bottom Docked) -->
    <div id="fireTapeDock" style="position:fixed;bottom:0;left:0;right:0;background:rgba(10,14,24,0.92);border-top:1px solid rgba(255,255,255,0.1);padding:0.4rem 1.25rem;display:flex;align-items:center;justify-content:space-between;gap:1rem;z-index:9998;backdrop-filter:blur(16px);font-family:'JetBrains Mono',monospace;font-size:0.75rem;">
      <div style="display:flex;align-items:center;gap:0.6rem;flex-shrink:0;">
        <span style="display:inline-block;width:8px;height:8px;background:#f59e0b;border-radius:50%;box-shadow:0 0 6px #f59e0b;"></span>
        <b style="color:#f59e0b;letter-spacing:0.05em;">FIRE TAPE:</b>
      </div>
      <div id="tapeFeed" style="display:flex;align-items:center;gap:1.5rem;overflow-x:auto;white-space:nowrap;scrollbar-width:none;flex-grow:1;">
        <span style="color:#64748b;">Awaiting sub-second Hyperliquid trade prints...</span>
      </div>
      <div style="flex-shrink:0;color:#64748b;font-size:0.7rem;">
        <span id="tickLatency">Latency: &lt;40ms</span>
      </div>
    </div>

    <style>
      @keyframes livePulse {{
        0%, 100% {{ opacity: 1; transform: scale(1); }}
        50% {{ opacity: 0.35; transform: scale(0.85); }}
      }}
      .tape-item {{
        display:inline-flex;align-items:center;gap:0.35rem;padding:0.15rem 0.45rem;border-radius:4px;background:rgba(255,255,255,0.03);animation:tapeFade 0.3s ease-out;
      }}
      @keyframes tapeFade {{
        from {{ opacity: 0; transform: translateY(4px); }}
        to {{ opacity: 1; transform: translateY(0); }}
      }}
    </style>

    <script>
      let currentSpot = {init_price};
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
        btn.style.borderColor = audioEnabled ? 'rgba(56,189,248,0.4)' : 'rgba(255,255,255,0.1)';
        btn.style.color = audioEnabled ? '#38bdf8' : '#94a3b8';
      }}

      // Dynamic Plotly reference line update
      function updatePlotlySpot(newPrice) {{
        const gd = document.querySelector('.plotly-graph-div');
        if (gd && gd._fullLayout && gd._fullLayout.shapes) {{
          try {{
            Plotly.relayout(gd, {{
              'shapes[0].y0': newPrice,
              'shapes[0].y1': newPrice,
              'annotations[0].y': newPrice,
              'annotations[0].text': '$' + newPrice.toFixed(3)
            }});
          }} catch(e) {{}}
        }}
      }}

      function updatePriceDisplay(newPrice) {{
        const badge = document.getElementById('spotPriceBadge');
        if (!badge) return;
        const diff = newPrice - currentSpot;
        if (Math.abs(diff) > 0.0001) {{
          badge.textContent = '$' + newPrice.toFixed(3) + (diff > 0 ? ' ▲' : ' ▼');
          badge.style.background = diff > 0 ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)';
          badge.style.color = diff > 0 ? '#10b981' : '#ef4444';
          badge.style.borderColor = diff > 0 ? '#10b981' : '#ef4444';
          setTimeout(() => {{
            badge.style.background = 'rgba(56,189,248,0.1)';
            badge.style.color = '#38bdf8';
            badge.style.borderColor = 'rgba(56,189,248,0.25)';
          }}, 600);
          updatePlotlySpot(newPrice);
        }}
        currentSpot = newPrice;
      }}

      // Fire Tape streaming
      const recentTrades = [];
      function addTradeToTape(trade) {{
        const feed = document.getElementById('tapeFeed');
        if (!feed) return;
        const isBuy = trade.side === 'B' || trade.side === 'buy';
        const px = parseFloat(trade.px);
        const sz = parseFloat(trade.sz);
        const notional = px * sz;
        const isWhale = notional >= 15000;
        const timeStr = new Date(trade.time || Date.now()).toLocaleTimeString([], {{hour:'2-digit', minute:'2-digit', second:'2-digit'}});

        playTickSound(isBuy, isWhale);

        const item = document.createElement('span');
        item.className = 'tape-item';
        item.innerHTML = `<span style="color:#64748b;">${{timeStr}}</span> ` +
                         `<b style="color:${{isBuy ? '#10b981' : '#ef4444'}};">${{isBuy ? 'BUY' : 'SELL'}}</b> ` +
                         `<span>${{sz.toFixed(2)}} HYPE @ $${{px.toFixed(2)}}</span> ` +
                         `<span style="color:#94a3b8;">($${{Math.round(notional).toLocaleString()}})</span>` +
                         (isWhale ? ` <span style="background:rgba(245,158,11,0.2);color:#f59e0b;padding:0.1rem 0.35rem;border-radius:3px;font-size:0.65rem;font-weight:700;">🐋 WHALE</span>` : '');

        feed.insertBefore(item, feed.firstChild);
        while (feed.children.length > 15) {{
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
            // Subscribe to trades, l2Book, and allMids
            ws.send(JSON.stringify({{method: "subscribe", subscription: {{type: "trades", coin: "HYPE"}}}}));
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
            if (data.spot) updatePriceDisplay(data.spot);
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
          }}
        }} catch(e) {{}}
      }}

      function fallbackPoll() {{
        const text = document.getElementById('wsStatusText');
        if (text) text.textContent = 'POLLING /api/live';
      }}

      async function refreshLive() {{
        const btn = document.getElementById('refreshBtn');
        const icon = document.getElementById('btnIcon');
        const text = document.getElementById('btnText');
        btn.disabled = true;
        btn.style.opacity = '0.6';
        icon.textContent = '⏳';
        text.textContent = 'Syncing...';
        try {{
          const res = await fetch('/api/refresh', {{ method: 'POST' }});
          if (res.ok) {{
            text.textContent = 'Success! Reloading...';
            setTimeout(() => window.location.reload(), 800);
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
    </script>
    """
    html = ("<html><head><meta charset='utf-8'><title>HYPE Perp - Live Liquidation Map (CCXT)</title>"
            "<link rel='preconnect' href='https://fonts.googleapis.com'>"
            "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@500;700&family=JetBrains+Mono:wght@500;700&display=swap' rel='stylesheet'>"
            "</head><body style='background:#080b11;margin:0;padding-bottom:2.5rem;'>" + header_html + "".join(parts) + "</body></html>")
    path.write_text(html, encoding="utf-8")

