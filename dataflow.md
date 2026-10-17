# HYPE Perp Liquidation Map & Terminal
## End-to-End Data Flow & State Lifecycle Specification

---

### Table of Contents
1. [Data Pipeline Architecture](#1-data-pipeline-architecture)
2. [Pipeline 1: Batch Historical Ingestion & Deterministic Model](#2-pipeline-1-batch-historical-ingestion--deterministic-model)
3. [Pipeline 2: Real-time Hyperliquid WebSocket Tick Processing](#3-pipeline-2-real-time-hyperliquid-websocket-tick-processing)
4. [Pipeline 3: L2 Orderbook Depth & Air Pocket Detection](#4-pipeline-3-l2-orderbook-depth--air-pocket-detection)
5. [Pipeline 4: Client-side Interactive Waterfall & Shock Simulation](#5-pipeline-4-client-side-interactive-waterfall--shock-simulation)
6. [Pipeline 5: Zero-Reload Map Recalculation Flow](#6-pipeline-5-zero-reload-map-recalculation-flow)
7. [State Lifecycle Machine](#7-state-lifecycle-machine)

---

### 1. Data Pipeline Architecture

The system coordinates three asynchronous data rhythms:
1. **Low-Frequency Macro Flow (Hourly/On-demand):** 30-day OHLCV ingestion, position modeling, and grid generation ($N=720$ candles).
2. **Medium-Frequency Telemetry Flow (Every 2–2.5 Seconds):** Orderbook L2 depth aggregation, liquidation absorption ratios, and air pocket classification.
3. **High-Frequency Microstructure Flow (>30 Ticks/Second):** Live Hyperliquid WebSocket execution tape, rolling 60s delta balance, and DOM-recycled trade cards.

```mermaid
flowchart TD
    subgraph DataSources ["External Market Feeds"]
        HL_REST["Hyperliquid REST (CCXT)"]
        HL_WS["Hyperliquid WebSocket Gateway"]
    end

    subgraph BatchFlow ["Batch Historical Pipeline (Pipeline 1)"]
        P1["fetch_ohlcv_ccxt()"] --> P2["build_positions()"]
        P2 --> P3["build_grids()"]
        P3 --> P4["Output Artifacts: HTML, CSV, JSON"]
    end

    subgraph TelemetryFlow ["Live Telemetry & Depth Pipeline (Pipeline 3)"]
        T1["fetch_l2_order_book()"] --> T2["Integrate 2% & 5% Liquidity"]
        T2 --> T3["Evaluate Air Pocket Invariants"]
        T3 --> T4["Publish /api/live State"]
    end

    subgraph TickFlow ["Real-time Microstructure Pipeline (Pipeline 2)"]
        W1["wss://api.hyperliquid.xyz/ws"] --> W2["DOM-Recycled Fire Tape HUD"]
        W2 --> W3["Rolling 60s Volume Delta Bar"]
        W3 --> W4["Order Flow Matrix Columns"]
    end

    HL_REST --> BatchFlow
    HL_REST --> TelemetryFlow
    HL_WS --> TickFlow
```

---

### 2. Pipeline 1: Batch Historical Ingestion & Deterministic Model

This pipeline transforms raw OHLCV market history into the deterministic liquidation ledger.

```mermaid
sequenceDiagram
    autonumber
    actor User as CLI / Server
    participant CCXT as CCXT Exchange API
    participant Model as liqmap/model.py
    participant Disk as Local File Storage
    participant UI as Browser Dashboards

    User->>CCXT: fetch_ohlcv("HYPE/USDC:USDC", "1h", limit=720)
    CCXT-->>User: OHLCV DataFrame (720 rows)
    User->>CCXT: fetch_open_interest("HYPE/USDC:USDC")
    CCXT-->>User: Open Interest USD ($1.56B)
    User->>Disk: save_snapshot(data/last, df, meta)

    User->>Model: build_positions(df, oi_usd, ModelConfig)
    Note over Model: 1. Compute HLC3 dollar volume<br/>2. Apply 168h half-life decay<br/>3. Split long/short share by candle close<br/>4. Spread across entry prices & leverage tiers<br/>5. Apply Hyperliquid liquidation formula with funding drift<br/>6. Filter liquidated survivors<br/>7. Normalize survivors to match live OI
    Model-->>User: Position Ledger (23,224 survivors)

    User->>Model: build_grids(pos, 720, ref_price, ModelConfig)
    Note over Model: Bin positions into 160 price bins<br/>Calculate heat_long, heat_short<br/>Accumulate cum_long, cum_short
    Model-->>User: Grids Dictionary (centres, edges, heat, cum)

    User->>Disk: write_html(terminal.html, hype_liquidation_map.html)
    User->>Disk: export liquidation_profile.csv & map_data.json
    Disk-->>UI: Serve dashboards
```

---

### 3. Pipeline 2: Real-time Hyperliquid WebSocket Tick Processing

Direct browser connection streaming live executions directly from Hyperliquid without server proxy overhead.

```mermaid
sequenceDiagram
    autonumber
    participant Browser as Client Browser (terminal.html / map.html)
    participant WSS as wss://api.hyperliquid.xyz/ws

    Browser->>WSS: Connect & Handshake
    WSS-->>Browser: Connection Established
    Browser->>WSS: {"method": "subscribe", "subscription": {"type": "trades", "coin": "HYPE"}}
    Browser->>WSS: {"method": "subscribe", "subscription": {"type": "allMids"}}

    loop Streaming Execution Prints (>30 msgs/sec)
        WSS-->>Browser: Trade message: {px, sz, side, time}
        Note over Browser: 1. Update live spot price header<br/>2. Classify trade: Standard, Whale (≥$10k), Megalodon (≥$100k), Liq<br/>3. Append to rollingTrades buffer (prune trades > 60s)<br/>4. Recalculate buy/sell percentage split<br/>5. Recycle DOM element: feed.lastElementChild -> feed.firstChild<br/>6. Push into slide-out Order Flow Matrix columns
    end
```

---

### 4. Pipeline 3: L2 Orderbook Depth & Air Pocket Detection

Background integration assessing market robustness and liquidation cascade vulnerability.

```mermaid
flowchart TD
    Start["Poll Timer (every 2.0s)"] --> FetchOB["CCXT fetch_l2_order_book('HYPE/USDC:USDC', limit=100)"]
    FetchOB --> CalcMids["Calculate Mid Price: (best_bid + best_ask) / 2"]
    
    CalcMids --> SumDepth["Integrate Cumulative Resting Liquidity:<br/>• bids_2pct & asks_2pct [±2% from mid]<br/>• bids_5pct & asks_5pct [±5% from mid]"]
    
    SumDepth --> CompareLiq["Compare Against Liquidation Concentrations:<br/>• long_liq_5pct (modeled long liquidations in -5% range)<br/>• short_liq_5pct (modeled short liquidations in +5% range)"]
    
    CompareLiq --> AbsorptionCheck{"Absorption Ratio:<br/>bids_5pct < long_liq_5pct OR<br/>asks_5pct < short_liq_5pct?"}
    
    AbsorptionCheck -- Yes --> FlagAirPocket["Set air_pocket_long / air_pocket_short = True<br/>Status: '⚠️ AIR POCKET VOID GAP DETECTED'"]
    AbsorptionCheck -- No --> FlagSound["Set air_pockets = False<br/>Status: '🛡️ HEALTHY DEPTH: Resting liquidity exceeds liquidations'"]
    
    FlagAirPocket --> CacheState["Acquire Thread Lock & Update LiveStateEngine Cache"]
    FlagSound --> CacheState
    CacheState --> ServeAPI["Serve instantaneous snapshot via GET /api/live"]
```

---

### 5. Pipeline 4: Client-side Interactive Waterfall & Shock Simulation

GPU-accelerated interactive cascade simulation on [`output/terminal.html`](file:///D:/projects/N1/output/terminal.html).

```mermaid
sequenceDiagram
    autonumber
    actor Trader as Trader
    participant Slider as HTML Range Slider (#priceSlider)
    participant RAF as requestAnimationFrame Scheduler
    participant Engine as updateSimulation() Engine
    participant Canvas as HTML5 Depth Canvas (#depthCanvas)
    participant DOM as Metric Badges (#wipedUsdDisplay, #riskBadge)

    Trader->>Slider: Drags slider (e.g. -12% shock)
    Slider->>RAF: Dispatch 'input' event (cancel previous RAF)
    RAF->>Engine: Execute on next display v-sync

    Note over Engine: 1. Quantize target price P_target<br/>2. If P_target < SPOT: Interpolate cum_long from grid<br/>3. If P_target > SPOT: Interpolate cum_short from grid<br/>4. Calculate total wiped USD notional<br/>5. Evaluate systemic risk category

    Engine->>DOM: Update targetPriceDisplay ($69.24)
    Engine->>DOM: Update wipedUsdDisplay ($124.5M)
    Engine->>DOM: Set riskBadge ('🔥 EXTREME SYSTEMIC CASCADE')
    Engine->>Canvas: drawDepthChart(P_target)
    Note over Canvas: Clear canvas -> Draw bid/ask depth curves -> Draw liquidation wall bars -> Highlight wipe zone fill
```

---

### 6. Pipeline 5: Zero-Reload Map Recalculation Flow

Reactive update cycle on [`output/hype_liquidation_map.html`](file:///D:/projects/N1/output/hype_liquidation_map.html).

```mermaid
sequenceDiagram
    autonumber
    actor Trader as Trader
    participant ShockSlider as Map Shock Slider
    participant Fetch as Browser Fetch API
    participant Server as /api/map-data Endpoint
    participant Plotly as Plotly.react Engine

    Trader->>ShockSlider: Adjusts Shock Multiplier (e.g. 1.25x)
    Note over ShockSlider: Multiplies modeled liquidation notional in memory
    ShockSlider->>Plotly: Plotly.react('heatmapPlot', updatedData, updatedLayout)
    Note over Plotly: Performs in-place WebGL canvas patch without destroying DOM or resetting user zoom

    Trader->>Fetch: Periodic Poll (every 10s)
    Fetch->>Server: GET /api/map-data
    Server-->>Fetch: Fresh 2D heat matrix & cumulative arrays
    Fetch->>Plotly: Plotly.react('heatmapPlot', serverData)
```

---

### 7. State Lifecycle Machine

The operational lifecycle of a position bucket within the quantitative model.

```mermaid
stateDiagram-v2
    [*] --> Inception: Candle Volume Created ($V_{USD}$)
    Inception --> Sliced: Discretized into S Entry Samples & K Leverage Tiers
    Sliced --> DecayApplied: Weight Adjusted by Age Decay ($0.5^{\Delta t / 168}$)
    DecayApplied --> DriftAdjusted: Liquidation Price Shifted by Funding Drift ($f_{cum}$)

    state MarketEvaluation {
        [*] --> Monitoring
        Monitoring --> Terminated: Market Trades Through $P_{liq}$ ($\min L \le P_{liq}$ or $\max H \ge P_{liq}$)
        Monitoring --> Surviving: Market Never Traded Through $P_{liq}$
    }

    DriftAdjusted --> MarketEvaluation
    Terminated --> [*]: Dropped from Live Profile
    Surviving --> ScaledToOI: Scaled by Total Contract Open Interest
    ScaledToOI --> BinnedToGrid: Aggregated into Time x Price Grid Cell
    BinnedToGrid --> Rendered: Visualized on Terminal & Heatmap
```

---

### 8. Pipeline 6: Caddy Edge Ingress & Reverse Proxy Routing Flow

The ingress path connecting external browser clients to internal application processes.

```mermaid
sequenceDiagram
    autonumber
    actor Client as Trader Browser
    participant Caddy as Caddy Reverse Proxy (:41345)
    participant Upstream as DualStackServer (:12312)
    participant Disk as Static Storage (/output)

    Client->>Caddy: GET /terminal (or /map, /api/live)
    Note over Caddy: Match host: localhost:41345<br/>Route via srv_41345 upstream 127.0.0.1:12312
    Caddy->>Upstream: Forward HTTP/1.1 Request
    Upstream->>Disk: Read HTML, CSV, or Query LiveStateEngine
    Disk-->>Upstream: Raw Payload
    Upstream-->>Caddy: HTTP 200 OK + Payload
    Note over Caddy: Apply Gzip / Zstandard Compression<br/>Add Security Headers
    Caddy-->>Client: Compressed HTTP 200 Response
```

---

### 9. End-to-End Pipeline Verification Matrix

Each pipeline is formally verified by automated tests in [`tests/test_e2e_dataflow.py`](file:///D:/projects/N1/tests/test_e2e_dataflow.py):

| Pipeline | Test Class & Method | Invariant Assertions |
|:---|:---|:---|
| **Pipeline 1** | `TestPipeline1HistoricalBatch.test_pipeline_1_deterministic_flow` | Bit-for-bit reproducibility, zero-lookahead survivor integrity, exact Open Interest conservation ($L_{\text{alive}} = \text{OI}$, $S_{\text{alive}} = \text{OI}$), cumulative monotonicity |
| **Pipeline 2** | `TestPipeline2WebSocketTickProcessing.test_hyperliquid_live_wss_stream`<br>`TestPipeline2WebSocketTickProcessing.test_trade_classification_and_rolling_delta_logic` | Live `wss://api.hyperliquid.xyz/ws` connection, `allMids` & `trades` frames, rolling 60s delta accumulation, standard/whale/megalodon classification |
| **Pipeline 3** | `TestPipeline3DepthAndAirPocket.test_live_depth_aggregation_and_air_pocket_contract` | Schema contract, $5\% \ge 2\%$ liquidity ordering, absorption ratio calculation, air pocket boolean flag consistency |
| **Pipeline 4** | `TestPipeline4WaterfallShockSimulation.test_waterfall_simulator_e2e_dataflow` | Interactive slider shock interaction, rAF debouncer, wiped USD tally, depth canvas redraw, risk badge state transition |
| **Pipeline 5** | `TestPipeline5ZeroReloadMapRecalculation.test_map_data_endpoint_contract`<br>`TestPipeline5ZeroReloadMapRecalculation.test_plotly_react_shock_tester_e2e` | `/api/map-data` schema validation, zero-reload `Plotly.react` WebGL canvas patch without document reload |
| **Pipeline 6** | `TestPipeline6CaddyIngressAndProxy.test_caddy_reverse_proxy_endpoints`<br>`TestPipeline6CaddyIngressAndProxy.test_deployment_memo_manifest_integrity` | Edge port `:41345` reverse proxy to `:12312`, gzip compression header verification, [`memo.md`](file:///D:/projects/N1/memo.md) manifest schema integrity |


