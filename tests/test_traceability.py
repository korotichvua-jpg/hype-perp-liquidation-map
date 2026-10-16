"""Traceability test suite verifying end-to-end data lineage.

Traces data through the full pipeline:
Raw Snapshot (data/last)
  -> OHLCV DataFrame
  -> Position Ledger (build_positions)
  -> Grid Bins & Profile CSV (build_grids)
  -> HTML Dashboards (output/terminal.html & output/hype_liquidation_map.html)
  -> Telemetry State Contract
"""
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from liqmap.model import ModelConfig, build_positions, build_grids
from liqmap.data import load_snapshot


@pytest.fixture(scope="module")
def snapshot_data():
    snapshot_dir = Path("data/last")
    if not (snapshot_dir / "meta.json").exists() or not (snapshot_dir / "ohlcv.csv").exists():
        pytest.skip("data/last snapshot missing for traceability tests")
    df, meta = load_snapshot(snapshot_dir)
    return df, meta


class TestDataPipelineTraceability:
    """Traces numerical integrity from raw snapshot files through the calculation pipeline."""

    def test_trace_raw_data_to_position_ledger(self, snapshot_data):
        df, meta = snapshot_data
        oi_usd = meta["oi_usd"]
        cfg = ModelConfig()

        pos = build_positions(df, oi_usd, cfg)

        # 1. Trace position count: n_candles * entry_samples * len(tiers) * 2 sides
        expected_rows = len(df) * cfg.entry_samples * len(cfg.tiers) * 2
        assert len(pos) == expected_rows, f"Position count mismatch: expected {expected_rows}, got {len(pos)}"

        # 2. Trace entry price bounds: every entry price must be within the respective candle's [low, high]
        for row in pos.sample(100, random_state=42).itertuples():
            candle = df.iloc[row.entry_idx]
            assert candle.low <= row.entry_price <= candle.high + 1e-8, (
                f"Entry price {row.entry_price} out of bounds for candle {row.entry_idx} [{candle.low}, {candle.high}]"
            )

        # 3. Trace total surviving open interest back to meta.json
        surviving_longs = pos[(pos["side"] == "long") & pos["alive"]]["notional_usd"].sum()
        surviving_shorts = pos[(pos["side"] == "short") & pos["alive"]]["notional_usd"].sum()
        assert abs(surviving_longs - oi_usd) / oi_usd < 1e-9
        assert abs(surviving_shorts - oi_usd) / oi_usd < 1e-9

    def test_trace_positions_to_grid_profile_csv(self, snapshot_data):
        df, meta = snapshot_data
        oi_usd = meta["oi_usd"]
        cfg = ModelConfig()
        ref_price = float(df["close"].iloc[-1])

        pos = build_positions(df, oi_usd, cfg)
        grids = build_grids(pos, len(df), ref_price, cfg)

        # Trace bins in CSV against grid profile calculations
        csv_path = Path("output/liquidation_profile.csv")
        assert csv_path.exists(), "liquidation_profile.csv must exist in output/"
        df_csv = pd.read_csv(csv_path)

        assert len(df_csv) == cfg.n_price_bins
        np.testing.assert_allclose(df_csv["price"], grids["centres"], rtol=1e-5)
        np.testing.assert_allclose(df_csv["long_usd"], grids["profile_long"], rtol=1e-5)
        np.testing.assert_allclose(df_csv["short_usd"], grids["profile_short"], rtol=1e-5)
        np.testing.assert_allclose(df_csv["cum_long"], grids["cum_long"], rtol=1e-5)
        np.testing.assert_allclose(df_csv["cum_short"], grids["cum_short"], rtol=1e-5)

    def test_trace_snapshot_to_rendered_terminal_html(self, snapshot_data):
        df, meta = snapshot_data
        ref_price = float(df["close"].iloc[-1])
        oi_usd = meta["oi_usd"]

        term_path = Path("output/terminal.html")
        assert term_path.exists(), "output/terminal.html must exist"
        html = term_path.read_text(encoding="utf-8")

        # 1. Spot price trace
        assert f"{ref_price:,.4f}" in html or f"{ref_price:.2f}" in html, (
            f"Reference price {ref_price} must trace into terminal HTML"
        )

        # 2. Open interest trace
        oi_str = f"{oi_usd / 1e6:,.1f}M"
        assert oi_str in html, f"Open Interest {oi_str} must trace into terminal HTML"

        # 3. Symbol trace
        assert meta["symbol"] in html, f"Symbol {meta['symbol']} must trace into terminal HTML"


class TestTelemetryTraceability:
    """Traces telemetry configuration parameters directly into rendered HTML files."""

    EXPECTED_TELEMETRY = {
        "folder": r"D:\projects\N1",
        "internal_ip": "192.168.1.12",
        "external_ip": "83.5.208.192",
        "model_brand": "Antigravity 2.0 (Google DeepMind)",
        "model_version": "Gemini 2.5 Pro",
    }

    def test_trace_telemetry_to_terminal_html(self):
        term_path = Path("output/terminal.html")
        assert term_path.exists()
        content = term_path.read_text(encoding="utf-8")

        assert self.EXPECTED_TELEMETRY["folder"] in content
        assert self.EXPECTED_TELEMETRY["internal_ip"] in content
        assert self.EXPECTED_TELEMETRY["external_ip"] in content
        assert self.EXPECTED_TELEMETRY["model_brand"] in content
        assert self.EXPECTED_TELEMETRY["model_version"] in content

    def test_trace_telemetry_to_liquidation_map_html(self):
        map_path = Path("output/hype_liquidation_map.html")
        assert map_path.exists()
        content = map_path.read_text(encoding="utf-8")

        assert self.EXPECTED_TELEMETRY["folder"] in content
        assert self.EXPECTED_TELEMETRY["internal_ip"] in content
        assert self.EXPECTED_TELEMETRY["external_ip"] in content
        assert self.EXPECTED_TELEMETRY["model_brand"] in content
        assert self.EXPECTED_TELEMETRY["model_version"] in content
