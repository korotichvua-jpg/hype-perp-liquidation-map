"""Unit test suite for the core modules: model, data, terminal, plots, and server."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from liqmap.model import ModelConfig, build_positions, build_grids, liquidation_price
from liqmap.data import synthetic_ohlcv, save_snapshot, load_snapshot
from liqmap.terminal import generate_terminal_html
from liqmap.plots import heatmap_figure, histogram2d_figure, write_html
from server import LiveStateEngine


class TestModelConfigUnit:
    """Unit tests for ModelConfig dataclass and validation logic."""

    def test_valid_default_config(self):
        cfg = ModelConfig()
        cfg.validate()
        assert cfg.max_leverage == 10.0
        assert len(cfg.tiers) == 4
        assert len(cfg.tier_weights) == 4

    def test_invalid_tiers_mismatch(self):
        cfg = ModelConfig(tiers=(2.0, 5.0), tier_weights=(0.5,))
        with pytest.raises(ValueError, match="same length"):
            cfg.validate()

    def test_tier_exceeding_max_leverage(self):
        cfg = ModelConfig(max_leverage=10.0, tiers=(2.0, 15.0), tier_weights=(0.5, 0.5))
        with pytest.raises(ValueError, match="max_leverage"):
            cfg.validate()

    def test_non_positive_tier(self):
        cfg = ModelConfig(max_leverage=10.0, tiers=(0.0, 5.0), tier_weights=(0.5, 0.5))
        with pytest.raises(ValueError, match="max_leverage"):
            cfg.validate()

    def test_non_positive_weights_sum(self):
        cfg = ModelConfig(tiers=(2.0, 5.0), tier_weights=(0.0, 0.0))
        with pytest.raises(ValueError, match="tier_weights must sum to > 0"):
            cfg.validate()


class TestDataUnit:
    """Unit tests for synthetic generation, snapshot save/load, and data framing."""

    def test_synthetic_ohlcv_structure(self):
        df = synthetic_ohlcv(n=50, start_price=50.0, seed=10)
        assert len(df) == 50
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        assert (df["volume"] > 0).all()
        assert (df["high"] >= df["low"]).all()
        assert (df["high"] >= df["open"]).all()
        assert (df["high"] >= df["close"]).all()
        assert (df["low"] <= df["open"]).all()
        assert (df["low"] <= df["close"]).all()
        assert df["timestamp"].is_monotonic_increasing

    def test_snapshot_save_and_load_roundtrip(self, tmp_path: Path):
        df = synthetic_ohlcv(n=24, seed=1)
        meta = {
            "symbol": "HYPE/USDC:USDC",
            "oi_usd": 120_000_000.0,
            "timeframe": "1h",
            "exchange": "hyperliquid"
        }
        snap_dir = tmp_path / "test_snapshot"
        save_snapshot(snap_dir, df, meta)

        loaded_df, loaded_meta = load_snapshot(snap_dir)
        pd.testing.assert_frame_equal(df, loaded_df)
        assert loaded_meta == meta


class TestTerminalAndPlotsUnit:
    """Unit tests for terminal HTML and Plotly figure generation."""

    def test_generate_terminal_html(self, tmp_path: Path):
        csv_file = tmp_path / "liquidation_profile.csv"
        df_csv = pd.DataFrame({
            "price": [70.0, 75.0, 80.0, 85.0, 90.0],
            "long_usd": [1e6, 2e6, 0.0, 0.0, 0.0],
            "short_usd": [0.0, 0.0, 0.0, 2e6, 1e6],
            "cum_long": [3e6, 2e6, 0.0, 0.0, 0.0],
            "cum_short": [0.0, 0.0, 0.0, 2e6, 3e6],
        })
        df_csv.to_csv(csv_file, index=False)

        meta_file = tmp_path / "meta.json"
        meta_file.write_text(json.dumps({
            "symbol": "HYPE/USDC:USDC",
            "oi_usd": 500e6,
            "exchange": "hyperliquid"
        }))

        out_html = tmp_path / "terminal.html"
        generated_path = generate_terminal_html(csv_file, meta_file, spot_price=80.0, out_path=out_html)

        assert generated_path.exists()
        content = generated_path.read_text(encoding="utf-8")
        assert "HYPE/USDC:USDC - Pro Liquidation Terminal" in content
        assert "Detailed System & Telemetry Footer" in content
        assert "D:\\projects\\N1" in content
        assert "192.168.1.12" in content
        assert "83.5.208.192" in content
        assert "Antigravity 2.0 (Google DeepMind)" in content
        assert "Gemini 2.5 Pro" in content

    def test_plots_figures_generation(self, tmp_path: Path):
        df = synthetic_ohlcv(n=30, seed=42)
        cfg = ModelConfig(n_price_bins=20)
        ref_price = float(df["close"].iloc[-1])
        pos = build_positions(df, 100e6, cfg)
        grids = build_grids(pos, len(df), ref_price, cfg)

        fig_heat = heatmap_figure(df, grids, ref_price, "HYPE", 100e6)
        fig_hist = histogram2d_figure(pos, grids, "HYPE")
        assert fig_heat is not None
        assert fig_hist is not None

        out_map = tmp_path / "map.html"
        write_html(out_map, [fig_heat, fig_hist], symbol="HYPE/USDC:USDC", oi_usd=100e6, ref_price=ref_price)
        assert out_map.exists()
        map_content = out_map.read_text(encoding="utf-8")
        assert "Detailed System & Telemetry Footer" in map_content
        assert "D:\\projects\\N1" in map_content


class TestLiveStateEngineUnit:
    """Unit tests for server.py LiveStateEngine logic and thread safety."""

    def test_initial_engine_state(self, tmp_path: Path):
        engine = LiveStateEngine(outdir=tmp_path, coin="HYPE")
        state = engine.get_state()
        try:
            assert state["symbol"] == "HYPE/USDC:USDC"
            assert state["local_folder"] == "D:\\projects\\N1"
            assert state["internal_ip"] == "192.168.1.12"
            assert state["external_ip"] == "83.5.208.192"
            assert "Antigravity 2.0" in state["ai_model"]
            assert state["spot"] > 0
            assert state["oi_usd"] > 0
        finally:
            engine.running = False

    def test_thread_safe_state_retrieval(self, tmp_path: Path):
        engine = LiveStateEngine(outdir=tmp_path, coin="HYPE")
        try:
            # get_state returns a copy, mutating returned dict does not mutate internal engine.state
            state_copy = engine.get_state()
            state_copy["spot"] = 9999.99
            assert engine.get_state()["spot"] != 9999.99
        finally:
            engine.running = False
