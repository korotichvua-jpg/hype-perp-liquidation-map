# HYPE perp - deterministic liquidation map

ccxt (data) + Plotly (`go.Heatmap`, `go.Histogram2d`, candlesticks, bars).

## Run
```bash
pip install -r requirements.txt
python run.py                      # live: Hyperliquid HYPE/USDC:USDC, 30d of 1h candles
python run.py --snapshot data/last # re-run on the saved snapshot -> identical output
python run.py --offline            # seeded synthetic demo, no network
python -m pytest                   # model tests
```
Open `output/hype_liquidation_map.html`. Also written: `output/liquidation_profile.csv`.

Useful flags: `--timeframe 15m --days 14`, `--oi-usd 600e6` (override OI),
`--max-leverage 10 --tiers 2 3 5 10 --tier-weights .15 .25 .35 .25`,
`--half-life-hours 0` (no age decay), `--bins 200 --range-pct 0.25`.

## What "deterministic" means
No randomness. Output = f(OHLCV snapshot, open interest, ModelConfig). The live fetch
saves a snapshot (`data/last`) so you can reproduce a map exactly.

## Model (see liqmap/model.py)
1. Candle USD volume = weight (age-decayed, 168h half-life by default).
2. Long share = (close-low)/(high-low); short share = the rest.
3. Volume spread over 5 entry prices in [low, high] and fixed leverage tiers.
4. Hyperliquid isolated liq formula, maintenance rate = 1/(2*max leverage).
5. Positions that price already traded through are removed; survivors per side
   are scaled to equal current OI.

## Charts
- Heatmap: time x liquidation price, live levels at each moment, candles overlaid,
  plus profile bars and cumulative curves (shorts accumulate up, longs down).
- Histogram2d: entry time x liquidation price, summed by notional, longs vs shorts.

## Caveats
This is an estimate from public data, not real position data. Leverage mix, the
long/short heuristic, and decay are assumptions. Verify HYPE's max leverage on
Hyperliquid and adjust `--max-leverage` / `--tiers`. Not financial advice.
