# HYPE Perp Deterministic Liquidation Map & Pro Terminal
## Comprehensive System Documentation & Technical Reference

---

### Table of Contents
1. [Project Overview](#1-project-overview)
2. [Key Architectural Features](#2-key-architectural-features)
3. [Installation & Requirements](#3-installation--requirements)
4. [CLI Command-Line Interface](#4-cli-command-line-interface)
5. [Web Server & Live REST API](#5-web-server--live-rest-api)
6. [Mathematical Liquidation Model](#6-mathematical-liquidation-model)
   - [Volume Weighting & Age Decay](#volume-weighting--age-decay)
   - [Long/Short Directional Allocation](#longshort-directional-allocation)
   - [Hyperliquid Isolated Margin Formula](#hyperliquid-isolated-margin-formula)
   - [Cost-of-Carry Funding Rate Drift](#cost-of-carry-funding-rate-drift)
   - [Survivor Filtering & Open Interest Scaling](#survivor-filtering--open-interest-scaling)
7. [Frontend Dashboards](#7-frontend-dashboards)
   - [Pro Liquidation Terminal (`/terminal`)](#pro-liquidation-terminal-terminal)
   - [Interactive 2D Liquidation Map (`/map`)](#interactive-2d-liquidation-map-map)
8. [Performance Optimizations](#8-performance-optimizations)
9. [Automated Test Suite & Verification](#9-automated-test-suite--verification)

---

### 1. Project Overview

The **HYPE Perp Deterministic Liquidation Map & Pro Terminal** is an institutional-grade crypto derivatives intelligence tool engineered specifically for the Hyperliquid `HYPE/USDC:USDC` perpetual contract.

Because cryptocurrency derivative exchanges do not publish private trader position books, traditional public liquidation maps rely on opaque heuristics or stochastic simulations. This project implements a **100% deterministic, zero-RNG quantitative model**:
$$\text{Output} = f(\text{OHLCV Snapshot}, \text{Open Interest}, \text{ModelConfig})$$

Given identical input data and configuration parameters, the system generates bit-for-bit identical liquidation ledgers, cumulative cascade curves, and 2D heat profiles across any operating system or run environment.

---

### 2. Key Architectural Features

- **Deterministic Liquidation Modeling:** Calculates discrete position clusters across customizable leverage tiers ($2\times, 3\times, 5\times, 10\times$) with strict adherence to Hyperliquid's isolated-margin maintenance specifications.
- **Funding Rate Collateral Drift:** Dynamically shifts liquidation prices over holding periods based on continuous cost-of-carry funding rate margin erosion.
- **Zero-Reload Live Map (`Plotly.react`):** Dynamically updates heatmap layers and histogram distributions without triggering full page reloads, preserving browser canvas state and zoom levels.
- **Modern Fire Tape HUD:** Real-time trade streaming directly connected to `wss://api.hyperliquid.xyz/ws` with rolling 60-second buy/sell delta volume bars, whale order alerts ($\ge\$10\text{k}$), megalodon alerts ($\ge\$100\text{k}$), and liquidation print badges.
- **DOM Element Recycling:** Employs circular object pooling (20 elements) in live tape feeds to prevent browser garbage collection micro-stutter at $>30\text{ trades/sec}$.
- **Interactive Waterfall Simulator:** HTML5 high-DPI canvas simulator with `requestAnimationFrame` debouncing and real-time cascading liquidation depth estimates.
- **Air Pocket Void Gap Detector:** Real-time L2 orderbook evaluation detecting catastrophic liquidity deficits within 2% and 5% depth brackets.
- **Dual-Stack Server:** IPv4/IPv6 multi-threaded HTTP server with built-in Caddy reverse proxy support.

---

### 3. Installation & Requirements

#### Prerequisites
- Python 3.10+ (tested on Python 3.12.10)
- Operating Systems: Windows 10/11, Linux (Ubuntu/Debian), macOS, or WSL2.
- (Optional) Podman or Docker for containerized deployment.

#### Quick Setup
```bash
# Clone the repository
git clone https://github.com/korotichvua-jpg/hype-perp-liquidation-map.git
cd hype-perp-liquidation-map

# Create virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# (Optional) Install Playwright browser binaries for UI testing
playwright install chromium
```

---

### 4. CLI Command-Line Interface

The primary CLI entry point is [`run.py`](file:///D:/projects/N1/run.py) (which executes [`liqmap/cli.py`](file:///D:/projects/N1/liqmap/cli.py)):

```bash
# 1. Fetch live Hyperliquid data and compile complete dashboard suite
python run.py

# 2. Re-run deterministically on a saved snapshot (offline, bit-for-bit reproducible)
python run.py --snapshot data/last

# 3. Offline demonstration mode with synthetic geometric Brownian motion candles
python run.py --offline

# 4. Custom leverage configuration & timeframe tuning
python run.py --timeframe 15m --days 14 --max-leverage 10 --tiers 2 3 5 10 --tier-weights 0.15 0.25 0.35 0.25 --half-life-hours 72 --bins 200
```

#### CLI Parameters
| Parameter | Default | Description |
|:---|:---:|:---|
| `--symbol` | `HYPE/USDC:USDC` | CCXT perp unified market symbol |
| `--timeframe` | `1h` | OHLCV aggregation candle timeframe |
| `--days` | `30` | Historical lookback window in calendar days |
| `--oi-usd` | `None` (auto) | Override total contract open interest in USD |
| `--snapshot` | `None` | Path to load/save offline snapshot directory (`ohlcv.csv` + `meta.json`) |
| `--offline` | `False` | Run with synthetic deterministic random walk without network |
| `--max-leverage`| `10.0` | Maximum leverage bracket permitted for the instrument |
| `--tiers` | `2 3 5 10` | Discretized leverage tiers for position distribution |
| `--tier-weights`| `.15 .25 .35 .25` | Notional proportion assigned to each tier |
| `--entry-samples`| `5` | Evenly spaced entry price samples per candle $[L, H]$ |
| `--half-life-hours`| `168.0` | Age decay half-life in hours (`0` = disable decay) |
| `--bins` | `160` | Number of discrete liquidation price buckets |
| `--range-pct` | `0.30` | Price grid span $(\text{spot} \times [1 - r, 1 + r])$ |
| `--out` | `output` | Target directory for generated assets |

---

### 5. Web Server & Live REST API

The interactive application server is managed by [`server.py`](file:///D:/projects/N1/server.py).

```bash
# Launch server on dual-stack IPv4/IPv6 localhost
python server.py --host :: --port 12312

# Launch with pre-existing snapshot without fetching live CCXT on startup
python server.py --host 0.0.0.0 --port 12312 --skip-fetch
```

#### REST API Endpoints

- **`GET /api/live`**
  Returns real-time telemetry, resting L2 depth, liquidation absorption ratios, air pocket metrics, and host network configuration.
  ```json
  {
    "symbol": "HYPE/USDC:USDC",
    "spot": 78.68,
    "oracle_px": 78.65,
    "funding": 0.0001,
    "oi_usd": 1566500000.0,
    "vlm_24h": 412500000.0,
    "bids_2pct": 14250000.0,
    "asks_2pct": 18120000.0,
    "bids_5pct": 38200000.0,
    "asks_5pct": 42100000.0,
    "long_liq_5pct": 42500000.0,
    "short_liq_5pct": 39100000.0,
    "long_absorption_pct": 89.88,
    "short_absorption_pct": 107.67,
    "air_pocket_long": false,
    "air_pocket_short": false,
    "air_pocket_status": "Healthy depth: bids and asks exceed liquidation cascade thresholds within 5%",
    "local_folder": "D:\\projects\\N1",
    "internal_ip": "192.168.1.12",
    "external_ip": "83.5.208.192",
    "ai_model": "Antigravity 2.0 (Google DeepMind) / Gemini 2.5 Pro",
    "bids": [[78.65, 12000], [78.60, 45000]],
    "asks": [[78.70, 15000], [78.75, 38000]],
    "last_updated": 1729170000000
  }
  ```

- **`GET /api/map-data`**
  Returns structured Plotly-compatible JSON containing heatmap matrices (`heat_long`, `heat_short`), cumulative profiles (`cum_long`, `cum_short`), price grid centres, and latest spot reference price for zero-reload canvas recalculation.

- **`POST /api/refresh`**
  Triggers a background execution of [`liqmap/cli.py`](file:///D:/projects/N1/liqmap/cli.py) to fetch fresh 30-day CCXT candles, rebuild the model, and refresh disk artifacts.

- **`GET /plotly.min.js`**
  High-speed cached delivery of the unbundled Plotly graphics engine.

---

### 6. Mathematical Liquidation Model

The core calculation kernel resides in [`liqmap/model.py`](file:///D:/projects/N1/liqmap/model.py).

#### Volume Weighting & Age Decay
Each candle $i \in [0, N-1]$ represents opening volume. Dollar volume is calculated using the typical price (HLC3):
$$V_{\text{USD}, i} = \text{volume}_i \cdot \frac{\text{high}_i + \text{low}_i + \text{close}_i}{3}$$

To account for position churn, old positions undergo continuous exponential half-life decay:
$$w_i = V_{\text{USD}, i} \cdot 0.5^{\frac{\Delta t_i}{t_{\text{half-life}}}}$$
where $\Delta t_i$ is the elapsed duration in hours from candle timestamp $t_i$ to the most recent snapshot candle.

#### Long/Short Directional Allocation
The intra-candle market balance determines position directionality based on the location of the close within the range:
$$\text{share}_{\text{long}} = \frac{\text{close}_i - \text{low}_i}{\text{high}_i - \text{low}_i}, \quad \text{share}_{\text{short}} = 1 - \text{share}_{\text{long}}$$
*(If $\text{high}_i = \text{low}_i$, an unbiased $0.50 / 0.50$ split is assigned).*

#### Hyperliquid Isolated Margin Formula
Hyperliquid defines the maintenance margin rate $l$ as:
$$l = \frac{1}{2 \cdot L_{\text{max}}}$$
For $L_{\text{max}} = 10$, $l = 0.05$ (5.0% maintenance margin).

The isolated-margin liquidation price $P_{\text{liq}}$ for entry price $P_{\text{entry}}$, leverage $L$, and directional side $s \in \{+1 \text{ (long)}, -1 \text{ (short)}\}$ is:
$$P_{\text{liq}} = P_{\text{entry}} - s \cdot P_{\text{entry}} \cdot \frac{\frac{1}{L} - l}{1 - s \cdot l}$$

#### Cost-of-Carry Funding Rate Drift
Holding a perpetual position over time incurs funding fees. Longs pay positive funding rates; shorts receive positive funding.
The cumulative funding rate percentage is:
$$f_{\text{cum}} = f_{\text{hourly}} \cdot \Delta t_i$$
Effective initial margin ratio $\mu_{\text{eff}}$ erodes or builds over time:
$$\mu_{\text{eff}} = \max\left(\frac{1}{L} - s \cdot f_{\text{cum}}, \; l + 10^{-5}\right)$$
Substituting $\mu_{\text{eff}}$ into the liquidation price formula yields:
$$P_{\text{liq}}^{\text{drift}} = P_{\text{entry}} - s \cdot P_{\text{entry}} \cdot \frac{\mu_{\text{eff}} - l}{1 - s \cdot l}$$

- For **Longs** ($s = +1$) paying positive funding: $\mu_{\text{eff}}$ shrinks, causing $P_{\text{liq}}$ to migrate upward (closer to market price, increasing risk).
- For **Shorts** ($s = -1$) receiving positive funding: $\mu_{\text{eff}}$ increases, causing $P_{\text{liq}}$ to migrate upward (further from market price, increasing margin buffer).

#### Survivor Filtering & Open Interest Scaling
A position bucket is marked terminated if market prices subsequent to its entry candle ever traded through its liquidation barrier:
$$\text{Long Liquidated}: \min_{k > i} (\text{low}_k) \le P_{\text{liq}}$$
$$\text{Short Liquidated}: \max_{k > i} (\text{high}_k) \ge P_{\text{liq}}$$

All remaining active positions are scaled so that surviving long and short notional values sum exactly to the live contract Open Interest:
$$\sum_{\text{alive long}} \text{Notional}_j = \text{OI}_{\text{USD}}, \quad \sum_{\text{alive short}} \text{Notional}_j = \text{OI}_{\text{USD}}$$

---

### 7. Frontend Dashboards

#### Pro Liquidation Terminal (`/terminal`)
Generated by [`liqmap/terminal.py`](file:///D:/projects/N1/liqmap/terminal.py) and rendered to [`output/terminal.html`](file:///D:/projects/N1/output/terminal.html).
- **Header Telemetry:** Live WebSocket status badge, contract spot price, total open interest ($M), and manual pipeline sync button.
- **Interactive Waterfall Simulator:** Range slider with preset delta jumps ($\pm5\%, \pm10\%, \pm15\%$), real-time cascade notional tally, and severity risk badge.
- **HTML5 Depth Canvas:** High-DPI rendered depth charts comparing long/short liquidation concentrations against resting orderbook walls.
- **Fire Tape HUD Island:** Rolling 60s buy/sell volume bar, whale filters, play/pause toggle, and slide-out 3-column Order Flow Matrix drawer.
- **Air Pocket Void Card:** Instant alert card flagging orderbook gaps susceptible to flash domino liquidations.
- **System Telemetry Footer:** Fully populated diagnostic footer documenting repository path, host IPs, and AI model signature.

#### Interactive 2D Liquidation Map (`/map`)
Generated by [`liqmap/plots.py`](file:///D:/projects/N1/liqmap/plots.py) and rendered to [`output/hype_liquidation_map.html`](file:///D:/projects/N1/output/hype_liquidation_map.html).
- **Main Heatmap (`go.Heatmap`):** Visualizes the historical evolution of liquidation density across time and price coordinates with overlaid OHLCV candlesticks.
- **Cumulative Profile Curves:** Monotonic right-side profile showing cumulative shorts building upward and cumulative longs building downward.
- **Position Distribution (`go.Histogram2d`):** 2D bivariate density mapping entry date against liquidation price.
- **Zero-Reload Shock Tester:** Range slider on `/map` executing in-memory recalculation and `Plotly.react` updates without reloading.

---

### 8. Performance Optimizations

1. **Plotly Engine Decoupling:**
   Separated the 4.8MB Plotly runtime into a standalone cached asset `/plotly.min.js`. The HTML document size dropped from 6.75MB to ~1.93MB (~71% payload reduction).
2. **DOM Element Recycling:**
   The Fire Tape HUD maintains a fixed pool of 20 elements. New ticks reuse `feed.lastElementChild` via `insertBefore()`, eliminating heap allocations and garbage collection stutter.
3. **`requestAnimationFrame` Debounce:**
   Slider events are debounced using `requestAnimationFrame`, aligning canvas redraws with the monitor's native refresh rate (60Hz/120Hz/144Hz).

---

### 9. Automated Test Suite & Verification

The project includes 47 automated tests maintaining 100% pass status:

```powershell
python -m pytest
```

| Test File | Count | Focus Areas |
|:---|:---:|:---|
| [`tests/test_deterministic.py`](file:///D:/projects/N1/tests/test_deterministic.py) | 7 | Bit-for-bit reproducibility, leverage monotonicity, Hyperliquid formula exactness, OI conservation |
| [`tests/test_model.py`](file:///D:/projects/N1/tests/test_model.py) | 8 | Core model behavior, survivor verification, funding drift erosion checks |
| [`tests/test_tdd_contracts.py`](file:///D:/projects/N1/tests/test_tdd_contracts.py) | 6 | `/api/live` REST schema contracts, flat candle zero-division resilience, crash behavior |
| [`tests/test_traceability.py`](file:///D:/projects/N1/tests/test_traceability.py) | 5 | End-to-end data pipeline traceability from raw snapshot to rendered HTML/CSV |
| [`tests/test_unit.py`](file:///D:/projects/N1/tests/test_unit.py) | 11 | `ModelConfig` validation, synthetic OHLCV generators, `LiveStateEngine` thread safety |
| [`tests/test_e2e_playwright.py`](file:///D:/projects/N1/tests/test_e2e_playwright.py) | 10 | Headless Chromium browser validation of DOM, slider interaction, tape HUD, and Plotly rendering |

---

### 10. Caddy Web Server Deployment & Dashboard Memo

The application is engineered for production-grade local hosting via the **Caddy Web Server** and Antigravity's **caddy-manager** ecosystem.

#### Reverse Proxy Routing
Caddy serves as the hardened edge ingress:
- **Public Port:** `41345`
- **Upstream Daemon:** `127.0.0.1:12312` (Python `DualStackServer` / Podman `n1-liqmap-container`)
- **Proxy Key:** `srv_41345`

All requests to `http://localhost:41345/terminal`, `http://localhost:41345/map`, and `/api/*` are reverse-proxied transparently with HTTP gzip compression and zero-copy static asset streaming.

#### Deployment Manifest (`memo.md`)
The repository includes a standardized [`memo.md`](file:///D:/projects/N1/memo.md) file recognized by `caddy-manager` and the visual dashboard on port `62225`:

```yaml
---
project_name: "hype-perp-liquidation-map"
display_name: "HYPE Perp Liquidation Map & Pro Terminal"
port: 41345
type: "Quantitative Trading Dashboard & Web Server"
route_path: "D:\\projects\\N1\\output"
last_build: "2026-10-17 18:41:59"
upstream: "127.0.0.1:12312"
caddy_server_key: "srv_41345"
description: "Deterministic liquidation map, real-time WebSocket fire tape HUD, waterfall shock simulator, and L2 depth air pocket detector for Hyperliquid HYPE perp."
---
```

#### Caddy Management Commands
```powershell
# Verify Caddy Admin API health
caddy-manager status

# Add reverse proxy route
caddy-manager proxy --host localhost --port 41345 --to 127.0.0.1:12312

# Inspect all active hosted sites
caddy-manager list
```

