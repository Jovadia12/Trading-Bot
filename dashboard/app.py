"""Local, read-only web dashboard for the multi_crypto_momentum PAPER session.

    PAPER_MODE=true python3 -m dashboard            # then open http://127.0.0.1:8050

It only READS the runner's records (paper_trading/records/mcm_*/state.json); it is not a second trading engine.
Safety: GET routes only (anything else -> 405), binds to loopback only, imports no exchange/order code and makes
no network calls. Stopping or starting the dashboard has no effect on the paper-trading process.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from config.settings import PaperModeError, require_paper_mode
from dashboard.data import RECORDS_DIR, StateReader, build_dashboard

STATIC = Path(__file__).resolve().parent / "static"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
REFRESH_MS = 3000


def create_app(records_dir: Path = RECORDS_DIR, session: str | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    reader = StateReader(Path(records_dir), session)

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC, name)

    @app.get("/api/dashboard")
    def api_dashboard():
        data = build_dashboard(reader.read())
        data["refresh_ms"] = REFRESH_MS
        return jsonify(data)

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "paper_mode": "ON", "live_trading": "OFF", "read_only": True})

    @app.after_request
    def headers(resp):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; style-src 'self'; script-src 'self'; "
                                                   "img-src 'self' data:; connect-src 'self'")
        return resp

    return app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only paper-trading dashboard (local only)")
    ap.add_argument("--host", default="127.0.0.1", help="loopback only (127.0.0.1 / localhost / ::1)")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--records-dir", default=str(RECORDS_DIR))
    ap.add_argument("--session", default=None, help="session folder name (default: newest mcm_*)")
    args = ap.parse_args(argv)
    try:
        require_paper_mode()
    except PaperModeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.host not in LOOPBACK:
        print(f"Refusing to bind to {args.host}: the dashboard is local-only (use 127.0.0.1).", file=sys.stderr)
        return 2
    print(f"PAPER MODE: ON | LIVE TRADING: OFF | read-only dashboard at http://{args.host}:{args.port}  "
          f"(records: {args.records_dir})", flush=True)
    # load_dotenv=False: never pull the repo's .env (API credentials) into this read-only process
    create_app(Path(args.records_dir), args.session).run(host=args.host, port=args.port, debug=False,
                                                         use_reloader=False, load_dotenv=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
