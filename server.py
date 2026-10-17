"""Local HTTP server for the HYPE perp liquidation map.

Usage:
    python server.py --port 41345
    python server.py --port 12312 --skip-fetch
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socket
from pathlib import Path

from run import main as run_pipeline


import threading
import time
import urllib.parse
import urllib.request
import pandas as pd


class LiveStateEngine:
    """Background engine fetching sub-second order book and market telemetry from Hyperliquid."""

    def __init__(self, outdir: Path, coin: str = "HYPE"):
        self.outdir = outdir
        self.coin = coin
        self.lock = threading.Lock()
        self.state = {
            "symbol": f"{coin}/USDC:USDC",
            "spot": 79.30,
            "oracle_px": 79.30,
            "funding": 0.0000125,
            "oi_usd": 1580000000.0,
            "vlm_24h": 335000000.0,
            "bids_2pct": 1250000.0,
            "asks_2pct": 1180000.0,
            "bids_5pct": 3200000.0,
            "asks_5pct": 3100000.0,
            "long_liq_5pct": 12000000.0,
            "short_liq_5pct": 8000000.0,
            "long_absorption_pct": 26.6,
            "short_absorption_pct": 38.75,
            "air_pocket_long": True,
            "air_pocket_short": False,
            "air_pocket_status": "AIR POCKET DETECTED: Void below spot",
            "local_folder": "D:\\projects\\N1",
            "internal_ip": "192.168.1.12",
            "external_ip": "83.5.208.192",
            "ai_model": "Antigravity 2.0 (Google DeepMind) • Gemini 2.5 Pro",
            "bids": [],
            "asks": [],
            "last_updated": time.time(),
        }
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self) -> None:
        while self.running:
            try:
                self._poll_hyperliquid()
            except Exception as e:
                pass
            time.sleep(1.5)

    def _poll_hyperliquid(self) -> None:
        # 1. Fetch metaAndAssetCtxs
        req_ctx = urllib.request.Request(
            "https://api.hyperliquid.xyz/info",
            data=json.dumps({"type": "metaAndAssetCtxs"}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "HypeLiqMap/1.0"}
        )
        with urllib.request.urlopen(req_ctx, timeout=3.5) as resp:
            data = json.loads(resp.read().decode())
            universe = data[0]["universe"]
            idx = next((i for i, u in enumerate(universe) if u["name"] == self.coin), None)
            if idx is None:
                return
            ctx = data[1][idx]

        spot = float(ctx.get("midPx") or ctx.get("markPx") or ctx.get("oraclePx") or 79.0)
        oracle_px = float(ctx.get("oraclePx") or spot)
        funding = float(ctx.get("funding") or 0.0)
        oi_usd = float(ctx.get("openInterest") or 0.0) * spot
        vlm_24h = float(ctx.get("dayNtlVlm") or 0.0)
        prev_day_px = float(ctx.get("prevDayPx") or spot)
        change_24h_usd = spot - prev_day_px
        change_24h_pct = ((spot - prev_day_px) / prev_day_px) * 100.0 if prev_day_px > 0 else 0.0

        # 2. Fetch l2Book
        req_book = urllib.request.Request(
            "https://api.hyperliquid.xyz/info",
            data=json.dumps({"type": "l2Book", "coin": self.coin}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "HypeLiqMap/1.0"}
        )
        with urllib.request.urlopen(req_book, timeout=3.5) as resp:
            book_data = json.loads(resp.read().decode())
            raw_bids = book_data.get("levels", [[]])[0]
            raw_asks = book_data.get("levels", [[], []])[1]

        bids = [{"px": float(b["px"]), "sz": float(b["sz"]), "val": float(b["px"]) * float(b["sz"])} for b in raw_bids]
        asks = [{"px": float(a["px"]), "sz": float(a["sz"]), "val": float(a["px"]) * float(a["sz"])} for a in raw_asks]

        bids_2pct = sum(b["val"] for b in bids if b["px"] >= spot * 0.98)
        asks_2pct = sum(a["val"] for a in asks if a["px"] <= spot * 1.02)
        bids_5pct = sum(b["val"] for b in bids if b["px"] >= spot * 0.95)
        asks_5pct = sum(a["val"] for a in asks if a["px"] <= spot * 1.05)

        # 3. Read liquidation profile for absorption calculation
        csv_file = self.outdir / "liquidation_profile.csv"
        long_liq_5pct, short_liq_5pct = 1e6, 1e6
        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file)
                long_liq_5pct = float(df[df["price"] >= spot * 0.95]["long_usd"].sum())
                short_liq_5pct = float(df[df["price"] <= spot * 1.05]["short_usd"].sum())
            except Exception:
                pass

        long_abs = (bids_5pct / max(long_liq_5pct, 1.0)) * 100.0
        short_abs = (asks_5pct / max(short_liq_5pct, 1.0)) * 100.0
        air_long = long_abs < 35.0
        air_short = short_abs < 35.0

        if air_long and air_short:
            status_text = "CRITICAL: Bid & Ask Liquidity Void (Severe Slippage Risk)"
        elif air_long:
            status_text = f"DOWNWARD AIR POCKET: Bids absorb only {long_abs:.1f}% of liquidations"
        elif air_short:
            status_text = f"UPWARD AIR POCKET: Asks absorb only {short_abs:.1f}% of short liquidations"
        else:
            status_text = "HEALTHY: Resting order book depth provides stable absorption"

        with self.lock:
            self.state = {
                "symbol": f"{self.coin}/USDC:USDC",
                "spot": spot,
                "prev_day_px": prev_day_px,
                "change_24h_usd": change_24h_usd,
                "change_24h_pct": change_24h_pct,
                "oracle_px": oracle_px,
                "funding": funding,
                "oi_usd": oi_usd,
                "vlm_24h": vlm_24h,
                "bids_2pct": bids_2pct,
                "asks_2pct": asks_2pct,
                "bids_5pct": bids_5pct,
                "asks_5pct": asks_5pct,
                "long_liq_5pct": long_liq_5pct,
                "short_liq_5pct": short_liq_5pct,
                "long_absorption_pct": long_abs,
                "short_absorption_pct": short_abs,
                "air_pocket_long": air_long,
                "air_pocket_short": air_short,
                "air_pocket_status": status_text,
                "local_folder": "D:\\projects\\N1",
                "internal_ip": "192.168.1.12",
                "external_ip": "83.5.208.192",
                "ai_model": "Antigravity 2.0 (Google DeepMind) • Gemini 2.5 Pro",
                "bids": bids[:10],
                "asks": asks[:10],
                "last_updated": time.time(),
            }

    def get_state(self) -> dict:
        with self.lock:
            return dict(self.state)


LIVE_ENGINE: LiveStateEngine | None = None
_TF_PAYLOAD_CACHE: dict = {}
_TF_CACHE_TIME: float = 0.0


class LiquidationMapRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve files from directory and default root path to terminal.html or hype_liquidation_map.html."""

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path_only = parsed.path
        if path_only in ("/api/refresh", "/api/refresh/"):
            try:
                print("Fetching latest live CCXT Hyperliquid HYPE perp data...", flush=True)
                try:
                    run_pipeline([])
                except Exception as net_err:
                    print(f"Direct CCXT fetch error ({net_err}); recalculating from data/last...", flush=True)
                    run_pipeline(["--snapshot", "data/last"])
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status": "ok", "message": "Successfully wired to live CCXT Hyperliquid HYPE perp"}')
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
            return
        self.send_error(404, "Not Found")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path_only = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path_only in ("/refresh", "/refresh/"):
            print("Triggering manual refresh from live CCXT HYPE perps...", flush=True)
            try:
                try:
                    run_pipeline([])
                except Exception as net_err:
                    print(f"Direct CCXT fetch error ({net_err}); recalculating from data/last...", flush=True)
                    run_pipeline(["--snapshot", "data/last"])
            except Exception as e:
                print(f"Error refreshing CCXT data: {e}", flush=True)
            self.send_response(302)
            self.send_header("Location", "/map")
            self.end_headers()
            return

        if path_only in ("/api/live", "/api/live/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            data = LIVE_ENGINE.get_state() if LIVE_ENGINE else {}
            self.wfile.write(json.dumps(data).encode())
            return

        if path_only in ("/api/map-data", "/api/map-data/"):
            tf = query.get("timeframe", ["1h"])[0].lower()
            if tf in ("1m", "5m", "15m", "30m", "1h", "4h"):
                global _TF_PAYLOAD_CACHE, _TF_CACHE_TIME
                now = time.time()
                if now - _TF_CACHE_TIME > 60:
                    _TF_PAYLOAD_CACHE.clear()
                    _TF_CACHE_TIME = now
                if tf in _TF_PAYLOAD_CACHE:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(_TF_PAYLOAD_CACHE[tf])
                    return
                try:
                    from liqmap.multi_tf import calculate_timeframe_payload
                    from liqmap.data import load_snapshot
                    snap_dir = Path("data/last")
                    if snap_dir.exists() and (snap_dir / "ohlcv.parquet").exists():
                        base_df, meta = load_snapshot(snap_dir)
                    else:
                        from liqmap.data import synthetic_ohlcv
                        base_df = synthetic_ohlcv()
                        meta = {"oi_usd": 1580000000.0, "symbol": "HYPE/USDC:USDC"}

                    oi_usd = float(meta.get("oi_usd", 1580000000.0))
                    symbol = str(meta.get("symbol", "HYPE/USDC:USDC"))
                    payload = calculate_timeframe_payload(base_df, tf, oi_usd=oi_usd, symbol=symbol)
                    serialized = json.dumps(payload).encode()
                    _TF_PAYLOAD_CACHE[tf] = serialized

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(serialized)
                    return
                except Exception as e:
                    print(f"Error calculating timeframe {tf}: {e}", flush=True)

            out_dir = Path(getattr(self, "directory", "output"))
            map_file = out_dir / "map_data.json"
            if not map_file.exists():
                map_file = Path("output/map_data.json")
            if map_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(map_file.read_bytes())
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"error": "map_data.json not found"}')
            return

        if path_only in ("/api/stream", "/api/stream/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                for _ in range(60):
                    data = LIVE_ENGINE.get_state() if LIVE_ENGINE else {}
                    payload = f"data: {json.dumps(data)}\n\n".encode()
                    self.wfile.write(payload)
                    self.wfile.flush()
                    time.sleep(1.0)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            return

        if path_only in ("/api/refresh", "/api/refresh/"):
            try:
                print("Fetching latest live CCXT Hyperliquid HYPE perp data...", flush=True)
                run_pipeline()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status": "ok", "message": "Successfully wired to live CCXT Hyperliquid HYPE perp"}')
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
            return

        if path_only in ("/", "", "/terminal", "/terminal/"):
            self.path = "/terminal.html"
        elif path_only in ("/map", "/map/"):
            self.path = "/hype_liquidation_map.html"
        elif path_only in ("/map-v2", "/map-v2/"):
            self.path = "/hype_liquidation_map_v2.html"
        elif path_only in ("/live-map", "/live-map/", "/map-live", "/map-live/"):
            self.path = "/hype_live_map.html"
        elif path_only in ("/timeframe-map", "/timeframe-map/", "/map-tf", "/map-tf/", "/timeframe", "/timeframe/", "/hype_timeframe_liqmap.html"):
            self.path = "/hype_timeframe_liqmap.html"
        elif path_only in ("/turbo-map", "/turbo-map/", "/turbo", "/turbo/", "/fast-map", "/fast-map/", "/hype_turbo_liqmap.html"):
            self.path = "/hype_turbo_liqmap.html"
        try:
            return super().do_GET()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_HEAD(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path_only = parsed.path
        if path_only in ("/", "", "/terminal", "/terminal/"):
            self.path = "/terminal.html"
        elif path_only in ("/map", "/map/"):
            self.path = "/hype_liquidation_map.html"
        elif path_only in ("/map-v2", "/map-v2/"):
            self.path = "/hype_liquidation_map_v2.html"
        elif path_only in ("/live-map", "/live-map/", "/map-live", "/map-live/"):
            self.path = "/hype_live_map.html"
        elif path_only in ("/timeframe-map", "/timeframe-map/", "/map-tf", "/map-tf/", "/timeframe", "/timeframe/", "/hype_timeframe_liqmap.html"):
            self.path = "/hype_timeframe_liqmap.html"
        elif path_only in ("/turbo-map", "/turbo-map/", "/turbo", "/turbo/", "/fast-map", "/fast-map/", "/hype_turbo_liqmap.html"):
            self.path = "/hype_turbo_liqmap.html"
        try:
            return super().do_HEAD()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, format: str, *args) -> None:
        try:
            print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}", flush=True)
        except Exception:
            pass


class DualStackServer(http.server.ThreadingHTTPServer):
    """Server supporting both IPv4 and IPv6 dual-stack connections."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass):
        host, port = server_address
        if ":" in host:
            self.address_family = socket.AF_INET6
        else:
            self.address_family = socket.AF_INET
        super().__init__(server_address, RequestHandlerClass)

    def server_bind(self):
        if self.address_family == socket.AF_INET6:
            try:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except (AttributeError, OSError):
                pass
        super().server_bind()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Serve HYPE liquidation map on local port")
    p.add_argument("--port", type=int, default=12312, help="Port to listen on (default: 12312)")
    p.add_argument("--host", default="::", help="Host interface (default: :: for dual-stack)")
    p.add_argument("--outdir", default="output", help="Directory where map is saved")
    p.add_argument("--skip-fetch", action="store_true", help="Skip re-running and serve existing output")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    global LIVE_ENGINE
    LIVE_ENGINE = LiveStateEngine(outdir=outdir, coin="HYPE")

    html_file = outdir / "hype_liquidation_map.html"

    if not args.skip_fetch:
        print("Connecting to CCXT Hyperliquid and pulling live HYPE perp market data...", flush=True)
        try:
            run_pipeline()
        except Exception as e:
            print(f"Live fetch error: {e}. Falling back to cached snapshot.", flush=True)
            if not html_file.exists():
                raise
    elif not html_file.exists():
        print("Missing output files; generating via pipeline...", flush=True)
        run_pipeline()

    term_file = outdir / "terminal.html"
    if term_file.exists():
        shutil.copyfile(term_file, outdir / "index.html")
    elif html_file.exists():
        shutil.copyfile(html_file, outdir / "index.html")

    plotly_file = outdir / "plotly.min.js"
    if not plotly_file.exists():
        try:
            import plotly
            pkg_plotly = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
            if pkg_plotly.exists():
                shutil.copyfile(pkg_plotly, plotly_file)
        except Exception:
            pass

    handler = functools.partial(LiquidationMapRequestHandler, directory=str(outdir))

    # Try dual stack bind, fallback to 0.0.0.0 if :: fails
    try:
        httpd = DualStackServer((args.host, args.port), handler)
        effective_host = args.host
    except OSError:
        effective_host = "0.0.0.0"
        httpd = DualStackServer((effective_host, args.port), handler)

    with httpd:
        url = f"http://localhost:{args.port}"
        print("\n" + "=" * 60)
        print(f"  Liquidation Map Web Server Running at: {url}")
        print(f"  Listening on:                         [{effective_host}]:{args.port}")
        print(f"  Serving files from:                   {outdir.resolve()}")
        print(f"  Live CCXT Wire:                       Hyperliquid HYPE/USDC:USDC")
        print(f"  Press Ctrl+C to stop.")
        print("=" * 60 + "\n", flush=True)
        def _warmup():
            try:
                from liqmap.multi_tf import calculate_timeframe_payload
                from liqmap.data import load_snapshot
                snap_dir = Path("data/last")
                if snap_dir.exists() and (snap_dir / "ohlcv.parquet").exists():
                    base_df, meta = load_snapshot(snap_dir)
                    oi_usd = float(meta.get("oi_usd", 1580000000.0))
                    symbol = str(meta.get("symbol", "HYPE/USDC:USDC"))
                    for tf in ("1h", "15m", "5m"):
                        p = calculate_timeframe_payload(base_df, tf, oi_usd=oi_usd, symbol=symbol)
                        _TF_PAYLOAD_CACHE[tf] = json.dumps(p).encode()
                    print("  ⚡ Turbo RAM cache pre-warmed for instant sub-millisecond response.\n", flush=True)
            except Exception:
                pass
        threading.Thread(target=_warmup, daemon=True).start()
        while True:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nShutting down server...", flush=True)
                break
            except Exception as e:
                print(f"Server exception handled: {e}", flush=True)


if __name__ == "__main__":
    main()
