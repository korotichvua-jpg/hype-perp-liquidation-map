import numpy as np
import pandas as pd

from liqmap import ModelConfig, build_grids, build_positions, liquidation_price
from liqmap.data import synthetic_ohlcv

CFG = ModelConfig()
OI = 500e6


def test_liq_price_sides():
    long = liquidation_price(100.0, 10, +1, 10)
    short = liquidation_price(100.0, 10, -1, 10)
    assert long < 100 < short
    assert abs(long - 100 * (1 - 0.05 / 0.95)) < 1e-9


def test_lower_leverage_liquidates_further_away():
    assert liquidation_price(100, 2, 1, 10) < liquidation_price(100, 10, 1, 10)


def test_deterministic():
    df = synthetic_ohlcv(300)
    a = build_positions(df, OI, CFG)
    b = build_positions(df, OI, CFG)
    pd.testing.assert_frame_equal(a, b)


def test_survivors_sum_to_oi():
    df = synthetic_ohlcv(300)
    pos = build_positions(df, OI, CFG)
    for side in ("long", "short"):
        s = pos[(pos.side == side) & pos.alive].notional_usd.sum()
        assert abs(s - OI) / OI < 1e-9


def test_liquidated_positions_were_really_hit():
    df = synthetic_ohlcv(300)
    pos = build_positions(df, OI, CFG)
    dead = pos[~pos.alive].sample(200, random_state=0) if (~pos.alive).sum() > 200 else pos[~pos.alive]
    for r in dead.itertuples():
        if r.side == "long":
            assert df.low.iloc[r.liq_idx] <= r.liq_price
        else:
            assert df.high.iloc[r.liq_idx] >= r.liq_price
    alive = pos[pos.alive & (pos.entry_idx < 299)]
    for r in alive.head(300).itertuples():
        fut = df.iloc[r.entry_idx + 1:]
        assert (fut.low.min() > r.liq_price) if r.side == "long" else (fut.high.max() < r.liq_price)


def test_grid_profile_matches_survivors_in_range():
    df = synthetic_ohlcv(300)
    ref = float(df.close.iloc[-1])
    pos = build_positions(df, OI, CFG)
    g = build_grids(pos, len(df), ref, CFG)
    e = g["edges"]
    inr = pos[pos.alive & (pos.liq_price >= e[0]) & (pos.liq_price < e[-1])]
    for side in ("long", "short"):
        assert abs(g[f"profile_{side}"].sum() - inr[inr.side == side].notional_usd.sum()) < 1.0


def test_funding_drift_erodes_long_margin():
    """Positive funding rate should erode long collateral, shifting liq price closer to entry."""
    entry = 100.0
    lev = 5.0
    max_lev = 10.0
    # Standard liq price without drift
    liq_no_drift = liquidation_price(entry, lev, +1, max_lev, cum_funding=0.0)
    # Long pays 1% cumulative funding -> margin drops -> liq price rises towards 100
    liq_with_drift = liquidation_price(entry, lev, +1, max_lev, cum_funding=0.01)
    assert liq_with_drift > liq_no_drift
    assert liq_with_drift < entry

    # Short receives 1% cumulative funding -> margin increases -> liq price rises away from entry
    short_no_drift = liquidation_price(entry, lev, -1, max_lev, cum_funding=0.0)
    short_with_drift = liquidation_price(entry, lev, -1, max_lev, cum_funding=0.01)
    assert short_with_drift > short_no_drift


def test_build_positions_with_funding_drift():
    df = synthetic_ohlcv(100, seed=42)
    cfg_base = ModelConfig(funding_drift=False)
    cfg_drift = ModelConfig(funding_drift=True, funding_rate_hourly=0.0001)

    pos_base = build_positions(df, OI, cfg_base)
    pos_drift = build_positions(df, OI, cfg_drift)

    assert len(pos_base) == len(pos_drift)
    # Positions should have shifted liquidation prices for older candles
    old_longs_base = pos_base[(pos_base["side"] == "long") & (pos_base["entry_idx"] < 50)]
    old_longs_drift = pos_drift[(pos_drift["side"] == "long") & (pos_drift["entry_idx"] < 50)]
    assert (old_longs_drift["liq_price"].to_numpy() >= old_longs_base["liq_price"].to_numpy()).all()

