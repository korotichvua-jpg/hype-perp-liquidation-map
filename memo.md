---
project_name: "hype-perp-liquidation-map"
display_name: "HYPE Perp Liquidation Map & Pro Terminal"
port: 41345
type: "Quantitative Trading Dashboard & Web Server"
route_path: "D:\\projects\\N1\\output"
last_build: "2026-10-17 23:02:25"
upstream: "127.0.0.1:12313"
caddy_server_key: "srv_41345"
description: "Deterministic liquidation map, real-time WebSocket fire tape HUD, waterfall shock simulator, and L2 depth air pocket detector for Hyperliquid HYPE perp."
---

# Deployment Memo: HYPE Perp Liquidation Map & Pro Terminal

- **Target URL**: http://localhost:41345
- **Pro Terminal Dashboard**: http://localhost:41345/terminal
- **Interactive 2D Liquidation Map (V1)**: http://localhost:41345/map
- **Live V2 Liquidation Map (Direct DOM Ticker)**: http://localhost:41345/map-v2
- **Host Root**: `D:\projects\N1\output`
- **Upstream Backend**: `http://127.0.0.1:12313`
- **Pipeline Handlers**: `reverse_proxy`
- **Deployment Status**: Active & Monitored
- **Visual Dashboard**: http://localhost:62225
