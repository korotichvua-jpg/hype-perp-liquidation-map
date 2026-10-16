"""Shared fixtures for deterministic, unit, TDD, traceability, and Playwright tests."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import pandas as pd

from liqmap.model import ModelConfig, build_grids, build_positions
from liqmap.data import synthetic_ohlcv


@pytest.fixture(scope="session")
def sample_ohlcv() -> pd.DataFrame:
    """Deterministic synthetic OHLCV dataframe (720 hourly candles)."""
    return synthetic_ohlcv(n=720, start_price=40.0, seed=42)


@pytest.fixture(scope="session")
def default_cfg() -> ModelConfig:
    """Standard model configuration."""
    return ModelConfig()


@pytest.fixture(scope="session")
def sample_positions(sample_ohlcv: pd.DataFrame, default_cfg: ModelConfig) -> pd.DataFrame:
    """Deterministic position dataset."""
    return build_positions(sample_ohlcv, oi_usd=500e6, cfg=default_cfg)


@pytest.fixture(scope="session")
def sample_grids(sample_positions: pd.DataFrame, sample_ohlcv: pd.DataFrame, default_cfg: ModelConfig) -> dict:
    """Deterministic price grids and liquidation profiles."""
    ref_price = float(sample_ohlcv["close"].iloc[-1])
    return build_grids(sample_positions, len(sample_ohlcv), ref_price, default_cfg)


@pytest.fixture(scope="session")
def server_url() -> str:
    """Base URL for the live server or Caddy reverse proxy."""
    import urllib.request
    candidates = ["http://localhost:41345", "http://localhost:12312"]
    for url in candidates:
        try:
            with urllib.request.urlopen(f"{url}/api/live", timeout=1.0) as resp:
                if resp.status == 200:
                    return url
        except Exception:
            pass
    # Default fallback to primary Caddy proxy port
    return "http://localhost:41345"
