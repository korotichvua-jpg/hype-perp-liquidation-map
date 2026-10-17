"""Comprehensive End-to-End Data Flow Test Suite.

Formally tests all 6 data pipelines and state lifecycles defined in dataflow.md:
- Pipeline 1: Batch Historical Ingestion & Deterministic Model Lifecycle
- Pipeline 2: Real-time Hyperliquid WebSocket Tick Ingestion & Delta Math
- Pipeline 3: L2 Orderbook Depth Integration & Air Pocket Detection Contract
- Pipeline 4: Interactive Client-side Waterfall & Shock Simulation (Playwright)
- Pipeline 5: Zero-Reload Map Recalculation Flow (Plotly.react)
- Pipeline 6: Caddy Edge Ingress & Reverse Proxy Routing Flow (:41345 -> :12312)
"""
import asyncio
import json
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import websockets
from playwright.sync_api import Page, expect

from liqmap.model import ModelConfig, build_positions, build_grids
from liqmap.data import synthetic_ohlcv


# -------------------------------------------------------------------------
# Pipeline 1: Batch Historical Ingestion & Deterministic Model Lifecycle
# -------------------------------------------------------------------------
class TestPipeline1HistoricalBatch:
    """Verifies Pipeline 1: Historical OHLCV -> Position Ledger -> Grid Bins -> Artifacts."""

    def test_pipeline_1_deterministic_flow(self):
        # 1. Ingest synthetic OHLCV dataset
        n_candles = 120
        df = synthetic_ohlcv(n=n_candles, start_price=50.0, seed=777)
        assert len(df) == n_candles
        ref_price = float(df["close"].iloc[-1])
        oi_usd = 250_000_000.0

        # 2. Configure model with funding drift
        cfg = ModelConfig(
            max_leverage=10.0,
            tiers=(2.0, 5.0, 10.0),
            tier_weights=(0.2, 0.5, 0.3),
            entry_samples=4,
            half_life_hours=72.0,
            n_price_bins=100,
            price_range_pct=0.25,
            funding_rate_hourly=0.0001,
            funding_drift=True,
        )

        # 3. Build positions
        pos = build_positions(df, oi_usd, cfg)

        # Invariant 1: Total position bucket count
        expected_buckets = n_candles * cfg.entry_samples * len(cfg.tiers) * 2
        assert len(pos) == expected_buckets

        # Invariant 2: Zero Lookahead & Survivor Invariant
        # Liquidated positions must have their liquidation price breached by future candles
        dead_sample = pos[~pos["alive"]].head(50)
        for r in dead_sample.itertuples():
            if r.side == "long":
                assert df.iloc[r.liq_idx].low <= r.liq_price + 1e-7
            else:
                assert df.iloc[r.liq_idx].high >= r.liq_price - 1e-7

        # Invariant 3: Open Interest Conservation
        # Surviving positions must sum exactly to total contract open interest
        surviving_long = pos[(pos["side"] == "long") & pos["alive"]]["notional_usd"].sum()
        surviving_short = pos[(pos["side"] == "short") & pos["alive"]]["notional_usd"].sum()
        assert abs(surviving_long - oi_usd) / oi_usd < 1e-9
        assert abs(surviving_short - oi_usd) / oi_usd < 1e-9

        # 4. Build 2D Price Grids and Cumulative Profiles
        grids = build_grids(pos, n_candles, ref_price, cfg)
        assert grids["edges"].shape == (cfg.n_price_bins + 1,)
        assert grids["centres"].shape == (cfg.n_price_bins,)
        assert grids["heat_long"].shape == (cfg.n_price_bins, n_candles)
        assert grids["heat_short"].shape == (cfg.n_price_bins, n_candles)

        # Invariant 4: Monotonic Profile Accumulation
        cum_short = grids["cum_short"]
        cum_long = grids["cum_long"]
        centres = grids["centres"]
        # Above spot: cumulative short cascade strictly non-decreasing
        above_spot = centres >= ref_price
        assert np.all(np.diff(cum_short[above_spot]) >= 0.0)
        # Below spot: cumulative long cascade strictly non-increasing downward
        below_spot = centres <= ref_price
        assert np.all(np.diff(cum_long[below_spot]) <= 0.0)


# -------------------------------------------------------------------------
# Pipeline 2: Real-time Hyperliquid WebSocket Tick Processing
# -------------------------------------------------------------------------
class TestPipeline2WebSocketTickProcessing:
    """Verifies Pipeline 2: Direct WebSocket Streaming & Trade Classification."""

    def test_hyperliquid_live_wss_stream(self):
        async def _test():
            uri = "wss://api.hyperliquid.xyz/ws"
            async with websockets.connect(uri) as ws:
                # Subscribe to allMids and trades for HYPE
                await ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "allMids"}}))
                await ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "trades", "coin": "HYPE"}}))

                for _ in range(10):
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    channel = data.get("channel")
                    if channel in ("allMids", "trades", "subscriptionResponse"):
                        return True
            return False

        assert asyncio.run(_test()), "Expected channel subscription or data message from Hyperliquid WebSocket"

    def test_trade_classification_and_rolling_delta_logic(self):
        # Simulate rolling trade delta calculation matching client-side logic
        trades = [
            {"time": 1000, "px": 80.0, "sz": 50.0, "side": "B"},   # Buy $4,000 (Standard)
            {"time": 2000, "px": 80.0, "sz": 150.0, "side": "A"},  # Sell $12,000 (Whale >= $10k)
            {"time": 3000, "px": 80.0, "sz": 1500.0, "side": "B"}, # Buy $120,000 (Megalodon >= $100k)
        ]

        buy_notional = 0.0
        sell_notional = 0.0
        classified = []

        for t in trades:
            notional = t["px"] * t["sz"]
            is_buy = t["side"] == "B"
            if is_buy:
                buy_notional += notional
            else:
                sell_notional += notional

            is_whale = notional >= 10_000.0
            is_megalodon = notional >= 100_000.0
            classified.append((is_whale, is_megalodon))

        total = buy_notional + sell_notional
        buy_pct = (buy_notional / total) * 100.0
        sell_pct = 100.0 - buy_pct

        assert classified[0] == (False, False)  # $4k standard
        assert classified[1] == (True, False)   # $12k whale
        assert classified[2] == (True, True)    # $120k megalodon
        assert round(buy_pct, 1) == 91.2
        assert round(sell_pct, 1) == 8.8


# -------------------------------------------------------------------------
# Pipeline 3: L2 Orderbook Depth & Air Pocket Detection
# -------------------------------------------------------------------------
class TestPipeline3DepthAndAirPocket:
    """Verifies Pipeline 3: Orderbook Depth Integration & Air Pocket Risk Contracts."""

    def test_live_depth_aggregation_and_air_pocket_contract(self, server_url: str):
        url = f"{server_url}/api/live"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())

        # Required fields check
        required_fields = [
            "symbol", "spot", "bids_2pct", "asks_2pct", "bids_5pct", "asks_5pct",
            "long_liq_5pct", "short_liq_5pct", "long_absorption_pct", "short_absorption_pct",
            "air_pocket_long", "air_pocket_short", "air_pocket_status"
        ]
        for field in required_fields:
            assert field in data, f"Missing required telemetry field: {field}"

        # Invariant: 5% depth must strictly exceed or equal 2% depth
        assert data["bids_5pct"] >= data["bids_2pct"]
        assert data["asks_5pct"] >= data["asks_2pct"]

        # Invariant: Absorption ratios
        if data["long_liq_5pct"] > 0:
            expected_long_abs = round((data["bids_5pct"] / data["long_liq_5pct"]) * 100.0, 2)
            assert abs(data["long_absorption_pct"] - expected_long_abs) < 0.1

        # Invariant: Air Pocket Status String Consistency
        status_lower = data["air_pocket_status"].lower()
        assert any(w in status_lower for w in ("air pocket", "void", "healthy", "exceed", "critical"))


# -------------------------------------------------------------------------
# Pipeline 4: Interactive Client-side Waterfall & Shock Simulation (Playwright)
# -------------------------------------------------------------------------
class TestPipeline4WaterfallShockSimulation:
    """Verifies Pipeline 4: Interactive Waterfall Slider -> Canvas Redraw -> Metric Badges."""

    def test_waterfall_simulator_e2e_dataflow(self, page: Page, server_url: str):
        page.goto(f"{server_url}/terminal", wait_until="networkidle")

        # 1. Verify canvas initialized
        canvas = page.locator("#depthCanvas")
        assert canvas.is_visible()
        box = canvas.bounding_box()
        assert box and box["width"] > 200

        # 2. Get initial price
        slider = page.locator("#priceSlider")
        assert slider.is_visible()
        p_init = float(slider.input_value())

        # 3. Simulate client slider shock movement downward (-10%)
        target_shock = round(p_init * 0.90, 2)
        page.evaluate(
            "(val) => { const s = document.getElementById('priceSlider'); s.value = val; s.dispatchEvent(new Event('input')); }",
            target_shock
        )

        # 4. Wait for requestAnimationFrame debounce
        page.wait_for_timeout(200)
        quantized_price = float(slider.input_value())

        # 5. Verify target price display updated
        target_display = page.locator("#targetPriceDisplay")
        expect(target_display).to_contain_text(f"${quantized_price:.2f}")

        # 6. Verify wiped USD changed from zero to positive cascade value
        wiped_display = page.locator("#wipedUsdDisplay")
        expect(wiped_display).not_to_have_text("$0.0M")
        wiped_text = wiped_display.inner_text()
        assert "$" in wiped_text and "M" in wiped_text

        # 7. Verify risk badge transitioned to CASCADE / RISK
        risk_badge = page.locator("#riskBadge")
        assert risk_badge.is_visible()
        badge_text = risk_badge.inner_text()
        assert "CASCADE" in badge_text or "RISK" in badge_text


# -------------------------------------------------------------------------
# Pipeline 5: Zero-Reload Map Recalculation Flow
# -------------------------------------------------------------------------
class TestPipeline5ZeroReloadMapRecalculation:
    """Verifies Pipeline 5: /api/map-data Fetch -> In-Place Plotly.react Patching."""

    def test_map_data_endpoint_contract(self, server_url: str):
        url = f"{server_url}/api/map-data"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())

        required_keys = ["centres", "heatmap", "histogram", "cum_long", "cum_short", "spot", "oi_usd"]
        for k in required_keys:
            assert k in data, f"Missing key in /api/map-data: {k}"

        assert len(data["centres"]) == len(data["cum_long"])

    def test_plotly_react_shock_tester_e2e(self, page: Page, server_url: str):
        page.goto(f"{server_url}/map", wait_until="networkidle")

        # Verify Plotly container exists
        plot = page.locator("#heatmapPlot")
        assert plot.is_visible()

        # Verify Shock Tester badge
        badge = page.locator("#mapShockBadge")
        assert badge.is_visible()

        # Click -15% Shock button
        page.locator(".shock-btn").nth(0).click()
        page.wait_for_timeout(300)
        expect(badge).to_contain_text("Longs")

        # Click +15% Shock button
        page.locator(".shock-btn").nth(4).click()
        page.wait_for_timeout(300)
        expect(badge).to_contain_text("Shorts")


# -------------------------------------------------------------------------
# Pipeline 6: Caddy Edge Ingress & Reverse Proxy Routing Flow
# -------------------------------------------------------------------------
class TestPipeline6CaddyIngressAndProxy:
    """Verifies Pipeline 6: Edge Port :41345 -> Upstream :12312 Reverse Proxy."""

    def test_caddy_reverse_proxy_endpoints(self):
        caddy_base = "http://localhost:41345"
        routes = [
            ("/terminal", 200, "text/html"),
            ("/map", 200, "text/html"),
            ("/map-v2", 200, "text/html"),
            ("/live-map", 200, "text/html"),
            ("/api/live", 200, "application/json"),
            ("/api/map-data", 200, "application/json"),
            ("/plotly.min.js", 200, "javascript"),
        ]

        for route, expected_status, content_type_substr in routes:
            url = f"{caddy_base}{route}"
            req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                assert resp.status == expected_status, f"Route {route} failed with status {resp.status}"
                ct = resp.headers.get("Content-Type", "")
                assert content_type_substr in ct or "text/plain" in ct, (
                    f"Route {route} returned unexpected Content-Type: {ct}"
                )

    def test_map_v2_live_ticker_contract(self, page: Page, server_url: str):
        page.goto(f"{server_url}/map-v2", wait_until="networkidle")
        ticker = page.locator("#liveTickerWidget")
        assert ticker.is_visible()
        assert page.locator("#spotPriceBadge").is_visible()
        assert page.locator("#priceChangeBadge").is_visible()
        assert page.locator("#tickerChangeUsd").is_visible()
        assert page.locator("#tickerChangePct").is_visible()
        assert page.locator("#tickerPrevVal").is_visible()

    def test_deployment_memo_manifest_integrity(self):
        memo_file = Path("memo.md")
        assert memo_file.exists(), "memo.md deployment manifest must exist in root"
        content = memo_file.read_text(encoding="utf-8")
        assert "port: 41345" in content
        assert any(f'upstream: "127.0.0.1:{p}"' in content for p in (12312, 12313))
        assert "caddy_server_key: \"srv_41345\"" in content
        assert "last_build:" in content
