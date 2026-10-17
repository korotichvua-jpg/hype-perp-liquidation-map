"""Multi-timeframe deterministic liquidation map calculation engine.

Supports dynamic lookback horizons, adaptive half-life decay, and fast
zero-reload Plotly serialization for:
['1m', '5m', '15m', '30m', '1h', '4h']
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd

from .model import ModelConfig, build_positions, build_grids
from .plots import heatmap_figure, histogram2d_figure

# Timeframe specification matrix: (lookback_days, default_half_life_hours, description)
TIMEFRAME_SPECS: Dict[str, Tuple[float, float, str]] = {
    "1m":  (0.5, 4.0,   "12h Microstructure & Scalper Stops"),
    "5m":  (2.0, 18.0,  "48h Intraday Momentum Sweeps"),
    "15m": (7.0, 48.0,  "7d Tactical Swing Zones"),
    "30m": (15.0, 96.0, "15d Intermediate Trend Liquidation"),
    "1h":  (30.0, 168.0,"30d Structural Liquidation Map (Core)"),
    "4h":  (90.0, 504.0,"90d Macro Cycle & Institutional Collateral"),
}


def resample_or_slice_ohlcv(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """Resample or filter baseline OHLCV candles to the desired timeframe."""
    df = df.copy()
    if "datetime" not in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("datetime").reset_index(drop=True)

    tf_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
    }
    freq = tf_map.get(target_tf, "1h")

    # If already hourly, resample up to 4h
    if freq == "4h":
        resampled = (
            df.set_index("datetime")
            .resample("4h")
            .agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "timestamp": "first",
            })
            .dropna()
            .reset_index()
        )
        return resampled

    # If target is lower timeframe (1m, 5m, 15m, 30m) but input is 1h, synthetic micro-bars
    if target_tf in ("1m", "5m", "15m", "30m"):
        days, _, _ = TIMEFRAME_SPECS[target_tf]
        cutoff_ms = df["timestamp"].iloc[-1] - int(days * 86_400_000)
        sub_df = df[df["timestamp"] >= cutoff_ms].copy()
        if len(sub_df) < 5:
            sub_df = df.tail(30).copy()
        
        # Micro-candle deterministic subdivision
        sub_divs = {"1m": 60, "5m": 12, "15m": 4, "30m": 2}[target_tf]
        rows = []
        for _, row in sub_df.iterrows():
            o, h, l, c, v = row["open"], row["high"], row["low"], row["close"], row["volume"]
            t0 = row["timestamp"]
            step_ms = 3_600_000 // sub_divs
            v_step = v / sub_divs
            
            # Deterministic linear intraday path: Open -> Low -> High -> Close
            for k in range(sub_divs):
                frac = (k + 0.5) / sub_divs
                if frac < 0.33:
                    inter_px = o + (l - o) * (frac / 0.33)
                elif frac < 0.66:
                    inter_px = l + (h - l) * ((frac - 0.33) / 0.33)
                else:
                    inter_px = h + (c - h) * ((frac - 0.66) / 0.34)
                
                bar_o = o if k == 0 else rows[-1]["close"]
                bar_c = inter_px
                bar_h = max(bar_o, bar_c) * 1.0005
                bar_l = min(bar_o, bar_c) * 0.9995
                rows.append({
                    "timestamp": t0 + k * step_ms,
                    "open": bar_o,
                    "high": bar_h,
                    "low": bar_l,
                    "close": bar_c,
                    "volume": v_step,
                })
        return pd.DataFrame(rows).reset_index(drop=True)

    return df


def calculate_timeframe_payload(
    base_df: pd.DataFrame,
    timeframe: str,
    oi_usd: float,
    symbol: str = "HYPE/USDC:USDC",
    max_leverage: float = 10.0,
) -> Dict[str, Any]:
    """Calculate deterministic liquidation map payload for a given timeframe."""
    spec = TIMEFRAME_SPECS.get(timeframe, TIMEFRAME_SPECS["1h"])
    _, half_life, desc = spec

    df = resample_or_slice_ohlcv(base_df, timeframe)
    ref_price = float(df["close"].iloc[-1])

    cfg = ModelConfig(
        max_leverage=max_leverage,
        tiers=(2.0, 3.0, 5.0, 10.0),
        tier_weights=(0.15, 0.25, 0.35, 0.25),
        entry_samples=5,
        half_life_hours=half_life,
        n_price_bins=160,
        price_range_pct=0.30,
    )

    pos = build_positions(df, oi_usd, cfg)
    grids = build_grids(pos, len(df), ref_price, cfg)

    fig_heat = heatmap_figure(df, grids, ref_price, symbol, oi_usd)
    fig_hist = histogram2d_figure(pos, grids, symbol)

    return {
        "timeframe": timeframe,
        "description": desc,
        "half_life_hours": half_life,
        "candles_count": len(df),
        "positions_modeled": len(pos),
        "surviving_positions": int(pos["alive"].sum()),
        "spot": round(ref_price, 4),
        "oi_usd": oi_usd,
        "symbol": symbol,
        "centres": np.round(grids["centres"], 3).tolist(),
        "cum_long": np.round(grids["cum_long"]).astype(int).tolist(),
        "cum_short": np.round(grids["cum_short"]).astype(int).tolist(),
        "heatmap": json.loads(fig_heat.to_json()),
        "histogram": json.loads(fig_hist.to_json()),
    }
