"""
Deterministic liquidation-level model.

Exchanges do not publish individual positions, so every public "liquidation map"
is an *estimate*. This one is fully deterministic: no RNG anywhere. Same input
snapshot + same ModelConfig  ->  identical output.

Pipeline
--------
1. Every candle "creates" positions. Candle USD volume (volume * HLC3) is the
   weight, optionally decayed with age (old positions are likely closed).
2. Long/short split per candle comes from where the close sits in the range:
       buy_share = (close - low) / (high - low)
   Close near the high -> mostly longs opened; near the low -> mostly shorts.
3. Each candle's volume is spread over `entry_samples` evenly spaced entry prices
   between low and high, and over leverage tiers with fixed weights.
4. Liquidation price follows Hyperliquid's isolated-margin formula:
       l     = 1 / (2 * max_leverage)             (maintenance margin rate)
       liq   = entry - side * entry * (1/L - l) / (1 - l * side)
   side = +1 long, -1 short.
5. A position is dropped once price later trades through its liquidation price
   (long: low <= liq, short: high >= liq). Survivors are scaled per side so
   that they sum exactly to the current open interest (USD).
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ModelConfig:
    max_leverage: float = 10.0                       # HYPE max leverage on Hyperliquid (verify!)
    tiers: tuple = (2.0, 3.0, 5.0, 10.0)             # assumed leverage buckets
    tier_weights: tuple = (0.15, 0.25, 0.35, 0.25)   # share of notional per bucket
    entry_samples: int = 5                           # entry prices per candle
    half_life_hours: float | None = 168.0            # age decay; None = off
    n_price_bins: int = 160
    price_range_pct: float = 0.30                    # map spans price * (1 +/- x)
    funding_rate_hourly: float = 0.0                 # hourly funding rate (e.g. 0.0001 = 0.01%/hr)
    funding_drift: bool = False                      # enable cost-of-carry collateral erosion drift

    def validate(self) -> None:
        if len(self.tiers) != len(self.tier_weights):
            raise ValueError("tiers and tier_weights must have the same length")
        if any(t <= 0 or t > self.max_leverage for t in self.tiers):
            raise ValueError("every leverage tier must be in (0, max_leverage]")
        if sum(self.tier_weights) <= 0:
            raise ValueError("tier_weights must sum to > 0")
        if not (-0.05 <= self.funding_rate_hourly <= 0.05):
            raise ValueError("funding_rate_hourly must be between -5% and +5%")


def liquidation_price(entry, leverage, side, max_leverage, cum_funding=0.0):
    """Isolated-margin liquidation price (Hyperliquid style). side: +1 long, -1 short.
    cum_funding: cumulative funding rate paid (+) or received (-) over holding duration.
    """
    l = 1.0 / (2.0 * max_leverage)
    entry = np.asarray(entry, dtype=float)
    inv_l = 1.0 / np.asarray(leverage, dtype=float)
    if np.any(cum_funding != 0.0):
        # Long (side=+1) pays positive funding -> margin erodes (inv_l - cum_funding)
        # Short (side=-1) receives positive funding -> margin builds (inv_l + cum_funding)
        eff_margin = inv_l - side * cum_funding
        eff_margin = np.maximum(eff_margin, l + 1e-5)
    else:
        eff_margin = inv_l
    return entry - side * entry * (eff_margin - l) / (1.0 - l * side)


def build_positions(ohlcv: pd.DataFrame, oi_usd: float, cfg: ModelConfig) -> pd.DataFrame:
    """Return one row per estimated position bucket (entry candle x sample x tier x side)."""
    cfg.validate()
    df = ohlcv.reset_index(drop=True)
    n = len(df)
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    times = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

    hlc3 = (h + l + c) / 3.0
    usd = v * hlc3
    rng = h - l
    safe = np.where(rng > 0, rng, 1.0)
    buy = np.where(rng > 0, (c - l) / safe, 0.5)

    age_h = (df["timestamp"].iloc[-1] - df["timestamp"].to_numpy(float)) / 3_600_000.0
    if cfg.half_life_hours:
        usd = usd * 0.5 ** (age_h / cfg.half_life_hours)

    S = cfg.entry_samples
    frac = np.linspace(0.0, 1.0, S)
    tiers = np.asarray(cfg.tiers, float)
    tw = np.asarray(cfg.tier_weights, float)
    tw = tw / tw.sum()
    K = len(tiers)

    cols = {k: [] for k in ("entry_idx", "side", "leverage", "entry_price", "liq_price", "liq_idx", "raw")}
    for i in range(n):
        entries = l[i] + frac * rng[i]                     # (S,)
        cum_f = (cfg.funding_rate_hourly * age_h[i]) if (cfg.funding_drift and cfg.funding_rate_hourly != 0.0) else 0.0
        for side, share in ((1, buy[i]), (-1, 1.0 - buy[i])):
            liq = liquidation_price(entries[None, :], tiers[:, None], side, cfg.max_leverage, cum_funding=cum_f)  # (K,S)
            if i + 1 < n:
                if side == 1:
                    fut = np.minimum.accumulate(l[i + 1:])
                    j = np.searchsorted(-fut, -liq.ravel(), side="left")
                else:
                    fut = np.maximum.accumulate(h[i + 1:])
                    j = np.searchsorted(fut, liq.ravel(), side="left")
                j_abs = i + 1 + j
            else:
                j_abs = np.full(liq.size, n)
            j_abs = np.minimum(j_abs, n)                   # n == never liquidated
            raw = (usd[i] * share / S) * np.repeat(tw, S)
            cols["entry_idx"].append(np.full(liq.size, i))
            cols["side"].append(np.full(liq.size, side))
            cols["leverage"].append(np.repeat(tiers, S))
            cols["entry_price"].append(np.tile(entries, K))
            cols["liq_price"].append(liq.ravel())
            cols["liq_idx"].append(j_abs)
            cols["raw"].append(raw)

    pos = pd.DataFrame({k: np.concatenate(v_) for k, v_ in cols.items()})
    pos["entry_time"] = times.to_numpy()[pos["entry_idx"].to_numpy()]
    pos["alive"] = pos["liq_idx"] >= n

    # Scale each side so survivors sum to open interest.
    pos["notional_usd"] = 0.0
    for side in (1, -1):
        m = pos["side"] == side
        alive_sum = pos.loc[m & pos["alive"], "raw"].sum()
        scale = oi_usd / alive_sum if alive_sum > 0 else 0.0
        pos.loc[m, "notional_usd"] = pos.loc[m, "raw"] * scale
    pos["side"] = np.where(pos["side"] == 1, "long", "short")
    return pos.drop(columns="raw")


def build_grids(pos: pd.DataFrame, n_candles: int, ref_price: float, cfg: ModelConfig) -> dict:
    """Bin positions onto a price grid. Returns time x price heat matrices and the live profile."""
    r = cfg.price_range_pct
    edges = np.linspace(ref_price * (1 - r), ref_price * (1 + r), cfg.n_price_bins + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    nb = cfg.n_price_bins

    inside = pos[(pos["liq_price"] >= edges[0]) & (pos["liq_price"] < edges[-1])]
    out = {"edges": edges, "centres": centres}
    for side in ("long", "short"):
        s = inside[inside["side"] == side]
        pb = np.clip(np.digitize(s["liq_price"].to_numpy(), edges) - 1, 0, nb - 1)
        diff = np.zeros((nb, n_candles + 1))
        np.add.at(diff, (pb, s["entry_idx"].to_numpy()), s["notional_usd"].to_numpy())
        np.add.at(diff, (pb, s["liq_idx"].to_numpy()), -s["notional_usd"].to_numpy())
        heat = np.cumsum(diff, axis=1)[:, :n_candles]
        heat[heat < 1e-9] = 0.0
        out[f"heat_{side}"] = heat
        out[f"profile_{side}"] = heat[:, -1]
    # cumulative: shorts accumulate upward from price, longs downward from price
    up = centres >= ref_price
    cs = np.where(up, out["profile_short"], 0.0)
    cl = np.where(~up, out["profile_long"], 0.0)
    out["cum_short"] = np.cumsum(cs)
    out["cum_long"] = np.cumsum(cl[::-1])[::-1]
    return out
