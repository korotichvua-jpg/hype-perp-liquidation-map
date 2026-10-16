"""Market data via ccxt, snapshotting, and a deterministic synthetic fallback."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def make_exchange(name: str = "hyperliquid"):
    import ccxt  # imported lazily so offline mode works without network libs
    return getattr(ccxt, name)({"enableRateLimit": True})


def resolve_symbol(ex, symbol: str = "HYPE/USDC:USDC") -> str:
    markets = ex.load_markets()
    if symbol in markets:
        return symbol
    base = symbol.split("/")[0]
    for s, m in markets.items():
        if m.get("swap") and m.get("base") == base and m.get("linear", True):
            return s
    raise ValueError(f"No perpetual market found for {symbol} on {ex.id}")


def fetch_ohlcv_df(ex, symbol: str, timeframe: str = "1h", days: int = 30) -> pd.DataFrame:
    tf_ms = ex.parse_timeframe(timeframe) * 1000
    now = ex.milliseconds()
    since = now - days * 86_400_000
    rows, last_seen = [], -1
    while since < now:
        batch = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        last = batch[-1][0]
        if last <= last_seen:
            break
        last_seen = last
        since = last + tf_ms
        time.sleep(ex.rateLimit / 1000)
    df = pd.DataFrame(rows, columns=COLUMNS).drop_duplicates("timestamp").sort_values("timestamp")
    return df.reset_index(drop=True)


def fetch_open_interest_usd(ex, symbol: str, ref_price: float) -> float:
    """Current open interest in USD (one side). Tries ccxt unified calls, then ticker info."""
    try:
        oi = ex.fetch_open_interest(symbol)
        if oi.get("openInterestValue"):
            return float(oi["openInterestValue"])
        if oi.get("openInterestAmount"):
            return float(oi["openInterestAmount"]) * ref_price
    except Exception:
        pass
    try:
        info = ex.fetch_ticker(symbol).get("info", {})
        for key in ("openInterest", "openInterestAmount"):
            if info.get(key) is not None:
                return float(info[key]) * ref_price
    except Exception:
        pass
    raise RuntimeError("Could not fetch open interest; pass --oi-usd manually.")


def synthetic_ohlcv(n: int = 24 * 30, start_price: float = 40.0, seed: int = 42,
                    timeframe_ms: int = 3_600_000) -> pd.DataFrame:
    """Seeded random walk. For offline demos/tests ONLY - not real market data."""
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0002, 0.012, n)
    close = start_price * np.exp(np.cumsum(ret))
    open_ = np.concatenate([[start_price], close[:-1]])
    spread = np.abs(rng.normal(0, 0.006, n)) + 0.002
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    vol = rng.lognormal(11.5, 0.5, n) / close * 10
    end = 1_760_000_000_000
    ts = end - (n - 1 - np.arange(n)) * timeframe_ms
    return pd.DataFrame({"timestamp": ts, "open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


def save_snapshot(folder: Path, df: pd.DataFrame, meta: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    df.to_csv(folder / "ohlcv.csv", index=False)
    (folder / "meta.json").write_text(json.dumps(meta, indent=2))


def load_snapshot(folder: Path) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(folder / "ohlcv.csv")
    meta = json.loads((folder / "meta.json").read_text())
    return df, meta
