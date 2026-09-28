"""Download Coinbase BTC-USD historical candles for research (read-only, public endpoints).

    PAPER_MODE=true python3 -m backtest.fetch_coinbase --start 2017-01-01 --tf 5m 1h

Uses the existing read-only exchange client (``CoinbaseAdvancedClient.get_candles``) -> allowlisted
GET ``/api/v3/brokerage/market/products/BTC-USD/candles`` (or the authenticated equivalent if keys
are configured). 350 candles per request, paced to stay under public rate limits, retried on errors.
Writes ``research_data/coinbase_btcusd_<tf>.csv.gz`` + ``research_data/MANIFEST.json`` (row counts,
date range, quality report, SHA-256) and, if API credentials work, ``research_data/fees.json``
(your maker/taker rates only -- no secrets). Re-running resumes from the last saved candle.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from backtest.data import DATA_DIR, TF_SECONDS, data_path, load_candles, quality_report, save_candles
from config.settings import PaperModeError, load_settings
from exchange.client import MAX_CANDLES_PER_REQUEST, CoinbaseAdvancedClient
from exchange.errors import ExchangeAPIError


def fetch(client, tf: str, start: datetime, end: datetime, pause_s: float = 0.15, log=print) -> pd.DataFrame:
    step = TF_SECONDS[tf]
    window = timedelta(seconds=step * (MAX_CANDLES_PER_REQUEST - 1))
    rows, t, n_req, t0 = [], start, 0, time.time()
    while t < end:
        w_end = min(t + window, end)
        for attempt in range(6):
            try:
                candles = client.get_candles("BTC-USD", t, w_end, tf)
                break
            except ExchangeAPIError as exc:
                wait = min(30, 1.5 * 2 ** attempt)
                log(f"  request failed ({exc}); retry in {wait:.0f}s")
                time.sleep(wait)
        else:
            raise RuntimeError(f"giving up at {t.isoformat()} after repeated errors")
        rows += [(int(c.start.timestamp()), float(c.open), float(c.high), float(c.low), float(c.close),
                  float(c.volume)) for c in candles]
        n_req += 1
        if n_req % 200 == 0:
            log(f"  {tf}: {t:%Y-%m-%d} ... {len(rows):,} candles, {n_req} requests, {time.time() - t0:.0f}s")
        t = w_end
        time.sleep(pause_s)
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.drop_duplicates("time").set_index("time").sort_index()
    return df[df.index < end]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download Coinbase BTC-USD candles for research (read-only)")
    ap.add_argument("--start", default="2017-01-01", help="UTC start date (default 2017-01-01)")
    ap.add_argument("--end", default=None, help="UTC end date (default: start of the current hour)")
    ap.add_argument("--tf", nargs="+", default=["5m", "1h"], choices=["1m", "5m", "15m", "30m", "1h", "1d"])
    args = ap.parse_args(argv)
    try:
        settings = load_settings()
    except PaperModeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    client = CoinbaseAdvancedClient(settings.credentials)
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) if args.end else now
    manifest_path = DATA_DIR / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"files": {}}
    for tf in args.tf:
        path = data_path(tf)
        existing = load_candles(path) if path.is_file() else None
        resume = start
        if existing is not None and len(existing):
            resume = max(start, existing.index.max().to_pydatetime() + timedelta(seconds=TF_SECONDS[tf]))
        print(f"{tf}: downloading {resume:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} UTC")
        new = fetch(client, tf, resume, end)
        df = pd.concat([existing, new]) if existing is not None else new
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df[df.index >= start]
        sha = save_candles(df, path)
        q = quality_report(df, tf)
        manifest["files"][path.name] = {"exchange": "Coinbase Advanced (public candles)", "product": "BTC-USD",
                                        "timeframe": tf, "sha256": sha, "downloaded_at": now.isoformat(),
                                        "quality": q.to_dict()}
        print(f"{tf}: {q.rows:,} candles {q.first} -> {q.last}; missing {q.missing_bars:,} ({q.missing_pct}%), "
              f"largest gap {q.largest_gap_bars} bars, bad OHLC {q.bad_ohlc_rows}, zero-volume {q.zero_volume_rows}")
    if settings.credentials:
        try:
            rates = client.get_fee_rates()
            (DATA_DIR / "fees.json").write_text(json.dumps(
                {"source": "Coinbase /transaction_summary", "fetched_at": now.isoformat(),
                 "maker_fee_rate": str(rates["maker_fee_rate"]), "taker_fee_rate": str(rates["taker_fee_rate"]),
                 "pricing_tier": rates.get("pricing_tier")}, indent=2))
            print(f"fees: maker {rates['maker_fee_rate']} taker {rates['taker_fee_rate']} ({rates.get('pricing_tier')})")
        except Exception as exc:  # noqa: BLE001
            print(f"fees: not read ({type(exc).__name__}); research will use the documented default", file=sys.stderr)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
