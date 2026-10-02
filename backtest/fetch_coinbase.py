"""Download Coinbase historical candles for research (read-only, public endpoints). Default product: BTC-USD.

    PAPER_MODE=true python3 -m backtest.fetch_coinbase --start 2017-01-01 --tf 5m 1h
    PAPER_MODE=true python3 -m backtest.fetch_coinbase --product ETH-USD --start 2025-09-01 --tf 5m

Uses the existing read-only exchange client (``CoinbaseAdvancedClient.get_candles``) -> allowlisted
GET ``/api/v3/brokerage/market/products/BTC-USD/candles`` (or the authenticated equivalent if keys
are configured). 350 candles per request, paced to stay under public rate limits.

Robustness (safe to interrupt and re-run at any time):
  * CHECKPOINTING: every successful request is appended to
    ``research_data/.partial/coinbase_btcusd_<tf>.partial.csv`` and fsync'd before the next request, so
    nothing already downloaded can be lost (network failure, Ctrl+C, crash, sleep).
  * RESUME: on start, the final file and any checkpoint are merged and downloading continues from
    the last completed candle + 1 bar -- never from --start again.
  * RETRIES: transient failures (timeouts, connection errors, HTTP 429/5xx) are retried with
    exponential backoff + jitter (2 s doubling, capped at 120 s, 10 attempts per request by default).
    Permanent errors (other HTTP 4xx) stop immediately. Either way progress stays on disk and the
    command prints how to resume.
  * The final ``coinbase_btcusd_<tf>.csv.gz`` is written atomically and the checkpoint removed.
Also writes ``research_data/MANIFEST.json`` (row counts, date range, quality report, SHA-256) and, if
API credentials work, ``research_data/fees.json`` (your maker/taker rates only -- no secrets).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from backtest.data import DATA_DIR, TF_SECONDS, data_path, load_candles, quality_report, save_candles
from config.settings import PaperModeError, load_settings
from exchange.client import MAX_CANDLES_PER_REQUEST, CoinbaseAdvancedClient
from exchange.errors import ExchangeAPIError
from exchange.transport import ReadOnlyTransport

COLUMNS = ["time", "open", "high", "low", "close", "volume"]
PARTIAL_DIR = DATA_DIR / ".partial"
REQUEST_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 10          # per request
    base_s: float = 2.0         # first backoff
    cap_s: float = 120.0        # longest single wait
    jitter: float = 0.25        # +/- fraction of the wait, so retries don't synchronise

    def wait(self, attempt: int, rng: random.Random) -> float:
        """Backoff before retry number ``attempt`` (1-based): base * 2**(attempt-1), capped, jittered."""
        w = min(self.cap_s, self.base_s * 2 ** (attempt - 1))
        return max(0.0, w * (1 + rng.uniform(-self.jitter, self.jitter)))


class FetchInterrupted(RuntimeError):
    """Download stopped (permanent error or retries exhausted). Progress is saved; re-run to resume."""

    def __init__(self, message: str, completed_through: Optional[datetime]):
        super().__init__(message)
        self.completed_through = completed_through


def is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status", None)
    return status is None or status == 429 or status >= 500


def product_key(product: str) -> str:
    """BTC-USD -> btcusd (the file-name convention of backtest.data.data_path)."""
    return product.replace("-", "").lower()


def partial_path(tf: str, product: str = "BTC-USD") -> Path:
    return PARTIAL_DIR / f"{data_path(tf, product_key(product)).name.replace('.csv.gz', '')}.partial.csv"


def read_partial(path: Path) -> pd.DataFrame:
    """Read a checkpoint file, tolerating a truncated last line from a hard crash."""
    rows = []
    if path.is_file():
        with open(path, newline="") as fh:
            for rec in csv.reader(fh):
                if len(rec) != 6 or rec[0] == "time":
                    continue
                try:
                    rows.append((int(rec[0]), *map(float, rec[1:])))
                except ValueError:
                    continue                       # partially written line
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.set_index("time")


def load_existing(tf: str, product: str = "BTC-USD") -> Optional[pd.DataFrame]:
    """Final file + checkpoint, merged and de-duplicated (checkpoint wins)."""
    parts = []
    final = data_path(tf, product_key(product))
    if final.is_file():
        parts.append(load_candles(final))
    p = read_partial(partial_path(tf, product))
    if len(p):
        parts.append(p)
    if not parts:
        return None
    df = pd.concat(parts)
    return df[~df.index.duplicated(keep="last")].sort_index()


class Checkpoint:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._drop_partial_last_line()
        self._fh = open(path, "a", newline="")

    def _drop_partial_last_line(self) -> None:
        """After a hard crash the file may end mid-row; cut back to the last complete line so the next
        append starts on a fresh line (otherwise its first row would be merged into the garbage)."""
        if not self.path.is_file() or self.path.stat().st_size == 0:
            return
        with open(self.path, "rb+") as fh:
            data = fh.read()
            if data.endswith(b"\n"):
                return
            cut = data.rfind(b"\n") + 1           # 0 if there is no complete line at all
            fh.truncate(cut)

    def append(self, rows: list[tuple]) -> None:
        if rows:
            csv.writer(self._fh).writerows(rows)
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        self._fh.close()


def fetch(client, tf: str, start: datetime, end: datetime, checkpoint: Optional[Checkpoint] = None,
          pause_s: float = 0.15, retry: RetryPolicy = RetryPolicy(), sleep: Callable[[float], None] = time.sleep,
          log=print, seed: Optional[int] = None, product: str = "BTC-USD") -> pd.DataFrame:
    """Download [start, end). Each completed window is checkpointed before the next request.

    Raises FetchInterrupted (after checkpointing everything completed) on a permanent error or when
    a request still fails after ``retry.attempts`` tries.
    """
    step = TF_SECONDS[tf]
    window = timedelta(seconds=step * (MAX_CANDLES_PER_REQUEST - 1))
    rng = random.Random(seed)
    rows, t, n_req, t0 = [], start, 0, time.time()
    completed: Optional[datetime] = None
    while t < end:
        w_end = min(t + window, end)
        for attempt in range(1, retry.attempts + 1):
            try:
                candles = client.get_candles(product, t, w_end, tf)
                break
            except ExchangeAPIError as exc:
                if not is_retryable(exc):
                    raise FetchInterrupted(f"{tf}: permanent error at {t:%Y-%m-%d %H:%M} UTC ({exc}); "
                                           f"progress saved -- fix the cause and re-run to resume", completed) from None
                if attempt == retry.attempts:
                    raise FetchInterrupted(f"{tf}: still failing at {t:%Y-%m-%d %H:%M} UTC after {attempt} attempts "
                                           f"({exc}); progress saved -- re-run the same command to resume",
                                           completed) from None
                wait = retry.wait(attempt, rng)
                log(f"  {tf}: request failed at {t:%Y-%m-%d %H:%M} ({exc}); retry {attempt}/{retry.attempts - 1} "
                    f"in {wait:.0f}s")
                sleep(wait)
        batch = [(int(c.start.timestamp()), float(c.open), float(c.high), float(c.low), float(c.close),
                  float(c.volume)) for c in candles if start <= c.start < end]
        if checkpoint is not None:
            checkpoint.append(batch)
        rows += batch
        completed = w_end
        n_req += 1
        if n_req % 200 == 0:
            log(f"  {tf}: through {w_end:%Y-%m-%d} ... {len(rows):,} new candles, {n_req} requests, "
                f"{time.time() - t0:.0f}s")
        t = w_end
        sleep(pause_s)
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.drop_duplicates("time").set_index("time").sort_index()


def download_timeframe(client, tf: str, start: datetime, end: datetime, retry: RetryPolicy = RetryPolicy(),
                       pause_s: float = 0.15, sleep=time.sleep, log=print, product: str = "BTC-USD") -> pd.DataFrame:
    """Resume-aware download of one timeframe; returns the complete merged frame (final file written)."""
    step = timedelta(seconds=TF_SECONDS[tf])
    existing = load_existing(tf, product)
    resume = start
    if existing is not None and len(existing):
        resume = max(start, existing.index.max().to_pydatetime() + step)
        log(f"{tf}: found {len(existing):,} candles through {existing.index.max():%Y-%m-%d %H:%M} UTC "
            f"-> resuming from {resume:%Y-%m-%d %H:%M} UTC")
    if resume < end:
        log(f"{tf}: downloading {resume:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} UTC")
        cp = Checkpoint(partial_path(tf, product))
        try:
            fetch(client, tf, resume, end, cp, pause_s=pause_s, retry=retry, sleep=sleep, log=log, product=product)
        finally:
            cp.close()
    else:
        log(f"{tf}: already complete through {end:%Y-%m-%d %H:%M} UTC")
    df = load_existing(tf, product)
    df = df[(df.index >= start) & (df.index < end)]
    save_candles(df, data_path(tf, product_key(product)))   # atomic write
    partial_path(tf, product).unlink(missing_ok=True)       # checkpoint merged into the final file
    return df


def make_client(settings) -> CoinbaseAdvancedClient:
    return CoinbaseAdvancedClient(transport=ReadOnlyTransport(settings.credentials, timeout=REQUEST_TIMEOUT_S))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download Coinbase candles for research (read-only, resumable)")
    ap.add_argument("--product", default="BTC-USD", help="Coinbase product id, e.g. ETH-USD (default BTC-USD)")
    ap.add_argument("--start", default="2017-01-01", help="UTC start date (default 2017-01-01)")
    ap.add_argument("--end", default=None, help="UTC end date (default: start of the current hour)")
    ap.add_argument("--tf", nargs="+", default=["5m", "1h"], choices=["1m", "5m", "15m", "30m", "1h", "1d"])
    ap.add_argument("--retries", type=int, default=RetryPolicy.attempts, help="attempts per request (default 10)")
    args = ap.parse_args(argv)
    try:
        settings = load_settings()
    except PaperModeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    client = make_client(settings)
    retry = RetryPolicy(attempts=max(1, args.retries))
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) if args.end else now
    manifest_path = DATA_DIR / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"files": {}}
    for tf in args.tf:
        try:
            df = download_timeframe(client, tf, start, end, retry, product=args.product)
        except FetchInterrupted as exc:
            saved = load_existing(tf, args.product)
            through = f"{saved.index.max():%Y-%m-%d %H:%M} UTC" if saved is not None and len(saved) else "nothing yet"
            print(f"\nDOWNLOAD PAUSED: {exc}\nSaved {0 if saved is None else len(saved):,} {tf} candles through {through}. "
                  f"Re-run the same command to continue from there.", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            saved = load_existing(tf, args.product)
            print(f"\nInterrupted. {0 if saved is None else len(saved):,} {tf} candles are saved; re-run to resume.",
                  file=sys.stderr)
            return 130
        path = data_path(tf, product_key(args.product))
        q = quality_report(df, tf)
        manifest["files"][path.name] = {"exchange": "Coinbase Advanced (public candles)", "product": args.product,
                                        "timeframe": tf, "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                                        "downloaded_at": now.isoformat(), "quality": q.to_dict()}
        print(f"{tf}: {q.rows:,} candles {q.first} -> {q.last}; missing {q.missing_bars:,} ({q.missing_pct}%), "
              f"largest gap {q.largest_gap_bars} bars, bad OHLC {q.bad_ohlc_rows}, zero-volume {q.zero_volume_rows}")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2))
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
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
