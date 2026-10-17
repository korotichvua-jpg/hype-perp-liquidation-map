"""Tests for multi-timeframe deterministic liquidation map engine and HTTP API."""
import json
import urllib.request
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

from liqmap.data import synthetic_ohlcv, load_snapshot
from liqmap.multi_tf import TIMEFRAME_SPECS, resample_or_slice_ohlcv, calculate_timeframe_payload


class TestMultiTimeframeMathEngine:
    """Verifies deterministic math, lookback horizons, and decay half-lives across all timeframes."""

    @pytest.fixture
    def base_df(self):
        snap_dir = Path("data/last")
        if snap_dir.exists() and (snap_dir / "ohlcv.parquet").exists():
            df, _ = load_snapshot(snap_dir)
            return df
        return synthetic_ohlcv(n=720, start_price=80.0, seed=42)

    def test_all_timeframe_specs_present(self):
        expected_tfs = ["1m", "5m", "15m", "30m", "1h", "4h"]
        for tf in expected_tfs:
            assert tf in TIMEFRAME_SPECS
            days, hl, desc = TIMEFRAME_SPECS[tf]
            assert days > 0
            assert hl > 0
            assert len(desc) > 5

    @pytest.mark.parametrize("tf", ["1m", "5m", "15m", "30m", "1h", "4h"])
    def test_timeframe_payload_invariants(self, base_df, tf):
        oi_usd = 1_550_000_000.0
        payload = calculate_timeframe_payload(base_df, tf, oi_usd=oi_usd, symbol="HYPE/USDC:USDC")

        assert payload["timeframe"] == tf
        assert payload["half_life_hours"] == TIMEFRAME_SPECS[tf][1]
        assert payload["candles_count"] > 0
        assert payload["positions_modeled"] > 0
        assert payload["surviving_positions"] > 0
        assert payload["spot"] > 0
        assert payload["oi_usd"] == oi_usd

        # Invariant: centres, cum_long, cum_short arrays
        centres = np.asarray(payload["centres"])
        cum_long = np.asarray(payload["cum_long"])
        cum_short = np.asarray(payload["cum_short"])
        assert len(centres) == len(cum_long) == len(cum_short)

        # Invariant: monotonic cumulative cascades
        spot = payload["spot"]
        above_spot = centres >= spot
        below_spot = centres <= spot
        assert np.all(np.diff(cum_short[above_spot]) >= 0.0)
        assert np.all(np.diff(cum_long[below_spot]) <= 0.0)

        # Invariant: valid Plotly figures
        assert "data" in payload["heatmap"]
        assert "layout" in payload["heatmap"]
        assert "data" in payload["histogram"]
        assert "layout" in payload["histogram"]


class TestMultiTimeframeHttpEndpoints:
    """Verifies server.py and Caddy proxy endpoints for multi-timeframe navigation."""

    def test_timeframe_map_html_page_direct(self):
        req = urllib.request.Request("http://127.0.0.1:12313/timeframe-map")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
            assert "timeframeSelector" in html
            assert "switchTimeframe" in html
            assert "1m" in html
            assert "5m" in html
            assert "15m" in html
            assert "30m" in html
            assert "1h" in html
            assert "4h" in html

    def test_timeframe_map_html_page_caddy_proxy(self):
        req = urllib.request.Request("http://localhost:41345/timeframe-map")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
            assert "timeframeSelector" in html

    @pytest.mark.parametrize("tf", ["1m", "5m", "15m", "30m", "1h", "4h"])
    def test_api_map_data_timeframes_caddy(self, tf):
        url = f"http://localhost:41345/api/map-data?timeframe={tf}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["timeframe"] == tf
            assert data["half_life_hours"] == TIMEFRAME_SPECS[tf][1]
            assert "heatmap" in data
            assert "histogram" in data
            assert len(data["centres"]) > 0
