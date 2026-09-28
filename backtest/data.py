"""Historical candle data: loading, validation (quality report) and resampling.

Canonical storage: ``research_data/coinbase_btcusd_<tf>.csv.gz`` with columns
``time,open,high,low,close,volume`` (UTC epoch seconds, bar START time), written by
``python3 -m backtest.fetch_coinbase``. Nothing here downloads data.
"""
from __future__ import annotations

import gzip
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "research_data"
TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}


def epoch_seconds(idx: pd.DatetimeIndex) -> np.ndarray:
    """UTC epoch seconds, independent of the index's internal unit (pandas 3 may use us, not ns)."""
    return idx.as_unit("s").asi8.astype("int64")


def data_path(tf: str, product: str = "btcusd", exchange: str = "coinbase") -> Path:
    return DATA_DIR / f"{exchange}_{product}_{tf}.csv.gz"


def load_candles(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time").sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def save_candles(df: pd.DataFrame, path: Path) -> str:
    """Write gzip CSV deterministically (mtime=0) and return its SHA-256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out.index = epoch_seconds(out.index)
    out.index.name = "time"
    raw = out.to_csv(float_format="%.8g").encode()
    with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(raw)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class QualityReport:
    rows: int
    first: str
    last: str
    expected_bars: int
    missing_bars: int
    missing_pct: float
    largest_gap_bars: int
    duplicate_timestamps: int
    misaligned_timestamps: int
    bad_ohlc_rows: int
    nonpositive_price_rows: int
    zero_volume_rows: int
    extreme_return_rows: int

    def to_dict(self) -> dict:
        return asdict(self)


def quality_report(df: pd.DataFrame, tf: str, extreme_ret: float = 0.25) -> QualityReport:
    step = TF_SECONDS[tf]
    t = pd.Index(epoch_seconds(df.index))
    expected = int((t.max() - t.min()) // step) + 1 if len(df) else 0
    diffs = np.diff(np.asarray(t)) // step if len(df) > 1 else np.array([1])
    bad = ((df.high < df[["open", "close"]].max(axis=1)) | (df.low > df[["open", "close"]].min(axis=1)) |
           (df.high < df.low))
    rets = np.abs(np.log(df.close / df.close.shift(1))).fillna(0)
    return QualityReport(
        rows=len(df), first=str(df.index.min()), last=str(df.index.max()), expected_bars=expected,
        missing_bars=max(0, expected - df.index.nunique()),
        missing_pct=round(100 * max(0, expected - df.index.nunique()) / expected, 4) if expected else 0.0,
        largest_gap_bars=int(diffs.max()) - 1 if len(diffs) else 0,
        duplicate_timestamps=int(df.index.duplicated().sum()),
        misaligned_timestamps=int((np.asarray(t) % step != 0).sum()),
        bad_ohlc_rows=int(bad.sum()),
        nonpositive_price_rows=int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()),
        zero_volume_rows=int((df.volume <= 0).sum()),
        extreme_return_rows=int((rets > extreme_ret).sum()),
    )


def resample(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Aggregate to a higher timeframe (UTC-aligned, left-labelled). Buckets with no source bars are dropped."""
    rule = {"5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h", "1d": "1D"}[tf]
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna(subset=["open"])


def load_timeframe(tf: str, base_tf: str = "5m", path: Optional[Path] = None) -> pd.DataFrame:
    """Load a timeframe from its own file if present, otherwise resample from the base file."""
    own = path or data_path(tf)
    if own.is_file():
        return load_candles(own)
    base = load_candles(data_path(base_tf))
    return base if tf == base_tf else resample(base, tf)
