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


class LiquidationMapRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve files from directory and default root path to terminal.html or hype_liquidation_map.html."""

    def do_POST(self) -> None:
        if self.path in ("/api/refresh", "/api/refresh/"):
            try:
                print("Fetching latest live CCXT Hyperliquid HYPE perp data...", flush=True)
                run_pipeline()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ok", "message": "Successfully wired to live CCXT Hyperliquid HYPE perp"}')
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
            return
        self.send_error(404, "Not Found")

    def do_GET(self) -> None:
        if self.path in ("/refresh", "/refresh/"):
            print("Triggering manual refresh from live CCXT HYPE perps...", flush=True)
            try:
                run_pipeline()
            except Exception as e:
                print(f"Error refreshing CCXT data: {e}", flush=True)
            self.send_response(302)
            self.send_header("Location", "/map")
            self.end_headers()
            return

        if self.path in ("/api/refresh", "/api/refresh/"):
            try:
                print("Fetching latest live CCXT Hyperliquid HYPE perp data...", flush=True)
                run_pipeline()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ok", "message": "Successfully wired to live CCXT Hyperliquid HYPE perp"}')
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
            return

        if self.path in ("/", "", "/terminal", "/terminal/"):
            self.path = "/terminal.html"
        elif self.path in ("/map", "/map/"):
            self.path = "/hype_liquidation_map.html"
        try:
            return super().do_GET()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_HEAD(self) -> None:
        if self.path in ("/", "", "/terminal", "/terminal/"):
            self.path = "/terminal.html"
        elif self.path in ("/map", "/map/"):
            self.path = "/hype_liquidation_map.html"
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
