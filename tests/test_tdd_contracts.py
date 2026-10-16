"""TDD contract and specification tests.

Ensures strict adherence to schema contracts, telemetry invariants,
and graceful edge-case handling under extreme market conditions.
"""
import re
import json
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from liqmap.model import ModelConfig, build_positions, build_grids, liquidation_price
from liqmap.data import synthetic_ohlcv
from server import LiveStateEngine


class TestAPIStateContract:
    """Contract tests for the /api/live telemetry schema."""

    REQUIRED_SCHEMA = {
        "symbol": str,
        "spot": (int, float),
        "oracle_px": (int, float),
        "funding": (int, float),
        "oi_usd": (int, float),
        "vlm_24h": (int, float),
        "bids_2pct": (int, float),
        "asks_2pct": (int, float),
        "bids_5pct": (int, float),
        "asks_5pct": (int, float),
        "long_liq_5pct": (int, float),
        "short_liq_5pct": (int, float),
        "long_absorption_pct": (int, float),
        "short_absorption_pct": (int, float),
        "air_pocket_long": bool,
        "air_pocket_short": bool,
        "air_pocket_status": str,
        "local_folder": str,
        "internal_ip": str,
        "external_ip": str,
        "ai_model": str,
        "bids": list,
        "asks": list,
        "last_updated": (int, float),
    }

    def test_live_engine_state_matches_contract(self, tmp_path: Path):
        engine = LiveStateEngine(outdir=tmp_path, coin="HYPE")
        try:
            state = engine.get_state()
            for key, expected_type in self.REQUIRED_SCHEMA.items():
                assert key in state, f"Contract violation: missing key '{key}' in LiveStateEngine state"
                val = state[key]
                assert isinstance(val, expected_type), (
                    f"Contract violation for '{key}': expected {expected_type}, got {type(val)}: {val}"
                )
        finally:
            engine.running = False

    def test_live_server_api_response_contract(self, server_url: str):
        """Query live running server endpoint /api/live and validate schema."""
        req = urllib.request.Request(f"{server_url}/api/live")
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
        except Exception as e:
            pytest.skip(f"Live server at {server_url} not reachable: {e}")

        for key, expected_type in self.REQUIRED_SCHEMA.items():
            assert key in data, f"Live API missing required field '{key}'"
            assert isinstance(data[key], expected_type), (
                f"Field '{key}' has invalid type: expected {expected_type}, got {type(data[key])}"
            )


class TestTelemetryInvariantsContract:
    """Contract tests for exact telemetry data formats."""

    IPV4_REGEX = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

    def test_telemetry_values_contract(self, tmp_path: Path):
        engine = LiveStateEngine(outdir=tmp_path, coin="HYPE")
        try:
            state = engine.get_state()
            assert "N1" in state["local_folder"], "Local folder must reference project N1 directory"
            assert self.IPV4_REGEX.match(state["internal_ip"]), f"Invalid internal IPv4: {state['internal_ip']}"
            assert self.IPV4_REGEX.match(state["external_ip"]), f"Invalid external IPv4: {state['external_ip']}"
            assert "Antigravity 2.0" in state["ai_model"]
            assert "Gemini 2.5 Pro" in state["ai_model"]
        finally:
            engine.running = False


class TestEdgeCaseContracts:
    """TDD edge case handling contracts: zero range, empty books, extreme moves."""

    def test_flat_candle_zero_range_no_division_by_zero(self):
        """Candles where high == low must not trigger division by zero."""
        ts = [1760000000000, 1760003600000]
        df_flat = pd.DataFrame({
            "timestamp": ts,
            "open": [50.0, 50.0],
            "high": [50.0, 50.0],  # high == low
            "low": [50.0, 50.0],
            "close": [50.0, 50.0],
            "volume": [1000.0, 1000.0],
        })
        cfg = ModelConfig()
        # Must execute cleanly without ZeroDivisionError
        pos = build_positions(df_flat, oi_usd=10e6, cfg=cfg)
        assert len(pos) > 0
        assert not pos["notional_usd"].isna().any()

    def test_single_candle_minimal_dataset(self):
        """Model must function on a minimal dataset with a single candle."""
        df_single = pd.DataFrame({
            "timestamp": [1760000000000],
            "open": [100.0],
            "high": [105.0],
            "low": [95.0],
            "close": [102.0],
            "volume": [5000.0],
        })
        cfg = ModelConfig()
        pos = build_positions(df_single, oi_usd=1e6, cfg=cfg)
        assert len(pos) > 0
        grids = build_grids(pos, len(df_single), 102.0, cfg)
        assert len(grids["centres"]) == cfg.n_price_bins

    def test_extreme_market_crash_behavior(self):
        """In a massive 95% price collapse, all earlier longs should be liquidated (alive == False)."""
        n = 10
        ts = [1760000000000 + i * 3600000 for i in range(n)]
        # Price starts at 100, drops to 5 on the last candle
        prices = [100.0] * 8 + [50.0, 5.0]
        df_crash = pd.DataFrame({
            "timestamp": ts,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000.0] * n,
        })
        cfg = ModelConfig(max_leverage=10.0, tiers=(5.0, 10.0), tier_weights=(0.5, 0.5))
        pos = build_positions(df_crash, oi_usd=10e6, cfg=cfg)

        # Early long positions entered around $100 must be liquidated
        early_longs = pos[(pos["entry_idx"] == 0) & (pos["side"] == "long")]
        assert not early_longs["alive"].any(), "All 100-entry longs should be liquidated by drop to 5"
