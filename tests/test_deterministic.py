"""Deterministic tests for the liquidation model and price grid algorithms.

Verifies:
1. Zero-RNG bit-for-bit reproducibility across consecutive runs.
2. Invariance to Open Interest scaling.
3. Leverage monotonicity (higher leverage -> strictly closer liquidation price).
4. Exact Hyperliquid isolated-margin formula compliance.
5. Cumulative liquidation waterfall curve monotonicity.
6. Notional conservation (surviving positions sum exactly to OI).
"""
import numpy as np
import pandas as pd
import pytest

from liqmap.model import ModelConfig, build_grids, build_positions, liquidation_price
from liqmap.data import synthetic_ohlcv


def test_zero_rng_bit_for_bit_reproducibility():
    """Identical input OHLCV and ModelConfig must yield bit-for-bit identical positions across runs."""
    df = synthetic_ohlcv(n=200, seed=123)
    cfg = ModelConfig(max_leverage=10.0, tiers=(2.0, 3.0, 5.0, 10.0))
    oi = 350e6

    run_a = build_positions(df, oi, cfg)
    run_b = build_positions(df, oi, cfg)
    run_c = build_positions(df, oi, cfg)

    pd.testing.assert_frame_equal(run_a, run_b, check_exact=True)
    pd.testing.assert_frame_equal(run_b, run_c, check_exact=True)


def test_deterministic_grid_matrices():
    """Grid profiles and heat matrices must match identically between separate executions."""
    df = synthetic_ohlcv(n=150, seed=777)
    cfg = ModelConfig()
    oi = 400e6
    ref_price = float(df["close"].iloc[-1])

    pos_1 = build_positions(df, oi, cfg)
    grid_1 = build_grids(pos_1, len(df), ref_price, cfg)

    pos_2 = build_positions(df, oi, cfg)
    grid_2 = build_grids(pos_2, len(df), ref_price, cfg)

    np.testing.assert_array_equal(grid_1["edges"], grid_2["edges"])
    np.testing.assert_array_equal(grid_1["centres"], grid_2["centres"])
    np.testing.assert_array_equal(grid_1["profile_long"], grid_2["profile_long"])
    np.testing.assert_array_equal(grid_1["profile_short"], grid_2["profile_short"])
    np.testing.assert_array_equal(grid_1["cum_long"], grid_2["cum_long"])
    np.testing.assert_array_equal(grid_1["cum_short"], grid_2["cum_short"])


def test_leverage_monotonicity_long_and_short():
    """
    Higher leverage must strictly place liquidation prices closer to entry price.
    For longs: liq(L_low) < liq(L_high) < entry
    For shorts: entry < liq(L_high) < liq(L_low)
    """
    entry = 100.0
    max_lev = 10.0
    leverages = [2.0, 3.0, 5.0, 10.0]

    long_liqs = [liquidation_price(entry, lev, 1, max_lev) for lev in leverages]
    short_liqs = [liquidation_price(entry, lev, -1, max_lev) for lev in leverages]

    # Longs: strictly increasing towards entry
    for i in range(len(leverages) - 1):
        assert long_liqs[i] < long_liqs[i + 1] < entry

    # Shorts: strictly decreasing towards entry
    for i in range(len(leverages) - 1):
        assert entry < short_liqs[i + 1] < short_liqs[i]


def test_hyperliquid_isolated_margin_formula_exactness():
    """
    Formula:
        l = 1 / (2 * max_leverage)
        liq = entry - side * entry * (1/L - l) / (1 - l * side)
    """
    entry = 80.0
    max_lev = 10.0
    l = 1.0 / (2.0 * max_lev)  # 0.05

    # 10x long: L=10 -> 1/L = 0.10. (0.10 - 0.05) / (1 - 0.05) = 0.05 / 0.95
    expected_10x_long = entry * (1.0 - 0.05 / 0.95)
    actual_10x_long = liquidation_price(entry, 10.0, 1, max_lev)
    assert abs(actual_10x_long - expected_10x_long) < 1e-12

    # 10x short: L=10 -> 1/L = 0.10. (0.10 - 0.05) / (1 + 0.05) = 0.05 / 1.05
    expected_10x_short = entry * (1.0 + 0.05 / 1.05)
    actual_10x_short = liquidation_price(entry, 10.0, -1, max_lev)
    assert abs(actual_10x_short - expected_10x_short) < 1e-12

    # 5x long: L=5 -> 1/L = 0.20. (0.20 - 0.05) / 0.95 = 0.15 / 0.95
    expected_5x_long = entry * (1.0 - 0.15 / 0.95)
    actual_5x_long = liquidation_price(entry, 5.0, 1, max_lev)
    assert abs(actual_5x_long - expected_5x_long) < 1e-12


def test_open_interest_linear_scaling():
    """Scaling OI by scalar k must scale all survivor notional USD values and profile bars by exactly k."""
    df = synthetic_ohlcv(n=100, seed=42)
    cfg = ModelConfig()
    ref_price = float(df["close"].iloc[-1])

    base_oi = 100e6
    pos_base = build_positions(df, base_oi, cfg)
    grid_base = build_grids(pos_base, len(df), ref_price, cfg)

    for k in (0.25, 2.0, 5.0):
        scaled_oi = base_oi * k
        pos_scaled = build_positions(df, scaled_oi, cfg)
        grid_scaled = build_grids(pos_scaled, len(df), ref_price, cfg)

        np.testing.assert_allclose(pos_scaled["notional_usd"], pos_base["notional_usd"] * k, rtol=1e-8, atol=1e-6)
        np.testing.assert_allclose(grid_scaled["profile_long"], grid_base["profile_long"] * k, rtol=1e-8, atol=1e-6)
        np.testing.assert_allclose(grid_scaled["profile_short"], grid_base["profile_short"] * k, rtol=1e-8, atol=1e-6)
        np.testing.assert_allclose(grid_scaled["cum_long"], grid_base["cum_long"] * k, rtol=1e-8, atol=1e-6)
        np.testing.assert_allclose(grid_scaled["cum_short"], grid_base["cum_short"] * k, rtol=1e-8, atol=1e-6)


def test_cumulative_waterfall_profile_monotonicity():
    """
    Cumulative liquidation curves must be monotonically non-decreasing away from spot price:
    - Long liquidations accumulate downwards (as target price drops).
    - Short liquidations accumulate upwards (as target price rises).
    """
    df = synthetic_ohlcv(n=250, seed=99)
    cfg = ModelConfig(n_price_bins=100)
    ref_price = float(df["close"].iloc[-1])
    pos = build_positions(df, 500e6, cfg)
    grid = build_grids(pos, len(df), ref_price, cfg)

    centres = grid["centres"]
    cum_short = grid["cum_short"]
    cum_long = grid["cum_long"]

    # For prices >= ref_price, cum_short must be non-decreasing with increasing price
    above = centres >= ref_price
    cum_short_above = cum_short[above]
    diff_short = np.diff(cum_short_above)
    assert np.all(diff_short >= -1e-9), "Short cumulative liquidations must not decrease as price rises"

    # For prices <= ref_price, cum_long must be non-decreasing as price drops (i.e. moving left from spot)
    below_indices = np.where(centres < ref_price)[0]
    if len(below_indices) > 1:
        # cum_long accumulates from ref_price down to 0:
        cum_long_below = cum_long[below_indices]
        # moving towards lower price indices (leftwards): cum_long_below[i] >= cum_long_below[i+1]
        diff_long = np.diff(cum_long_below)
        assert np.all(diff_long <= 1e-9), "Long cumulative liquidations must not decrease as price drops"


def test_survivor_notional_exact_conservation():
    """Sum of all surviving longs and shorts must strictly equal target open interest."""
    df = synthetic_ohlcv(n=350, seed=55)
    target_oi = 850_000_000.0
    cfg = ModelConfig()

    pos = build_positions(df, target_oi, cfg)

    long_alive = pos[(pos["side"] == "long") & pos["alive"]]["notional_usd"].sum()
    short_alive = pos[(pos["side"] == "short") & pos["alive"]]["notional_usd"].sum()

    assert abs(long_alive - target_oi) / target_oi < 1e-12
    assert abs(short_alive - target_oi) / target_oi < 1e-12
