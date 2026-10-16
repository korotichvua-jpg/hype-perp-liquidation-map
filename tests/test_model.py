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
