"""Interrupted-download, retry and resume behaviour of backtest.fetch_coinbase (no network)."""
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pandas as pd
import pytest

import backtest.data as data
import backtest.fetch_coinbase as fc
from backtest.data import load_candles
from exchange.errors import ExchangeAPIError
from market_data.models import Candle

S = datetime(2021, 3, 20, tzinfo=timezone.utc)
STEP = timedelta(minutes=5)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fc, "PARTIAL_DIR", tmp_path / ".partial")
    return tmp_path


def price(t):
    return 50000 + (int(t.timestamp()) // 300) % 97


class FakeCoinbase:
    """Serves deterministic 5m candles. `plan` maps call number (1-based) -> exception to raise."""

    def __init__(self, plan=None, down_from_call=None, down_error=None):
        self.plan, self.calls = dict(plan or {}), []
        self.down_from_call, self.down_error = down_from_call, down_error

    def get_candles(self, pid, start, end, tf):
        self.calls.append((start, end))
        n = len(self.calls)
        if self.down_from_call is not None and n >= self.down_from_call:
            raise self.down_error or ExchangeAPIError("GET candles failed: ReadTimeout")
        if n in self.plan:
            raise self.plan[n]
        out, t = [], start
        while t < end:
            p = D(price(t))
            out.append(Candle(t, p, p + 5, p - 5, p + 1, D(1)))
            t += STEP
        return list(reversed(out))     # Coinbase returns newest first


def expected_index(start, end):
    return pd.date_range(start, end - STEP, freq="5min", tz="UTC")


NO_SLEEP = lambda s: None
FAST = fc.RetryPolicy(attempts=4, base_s=2, cap_s=120, jitter=0.25)


def test_transient_failures_are_retried_with_exponential_backoff_and_no_data_loss():
    waits = []
    client = FakeCoinbase(plan={2: ExchangeAPIError("ReadTimeout"), 3: ExchangeAPIError("ConnectionError"),
                                4: ExchangeAPIError("HTTP 503", status=503)})
    end = S + timedelta(days=3)
    df = fc.download_timeframe(client, "5m", S, end, retry=fc.RetryPolicy(attempts=5, jitter=0.0),
                               pause_s=0, sleep=lambda s: waits.append(s) if s else None, log=lambda *a: None)
    assert list(df.index) == list(expected_index(S, end))
    assert [w for w in waits if w] == [2.0, 4.0, 8.0]                      # 2 s doubling
    assert not fc.partial_path("5m").exists() and data.data_path("5m").exists()


def test_backoff_is_capped_and_jittered():
    rng = random.Random(1)
    pol = fc.RetryPolicy(attempts=12, base_s=2, cap_s=120, jitter=0.25)
    ws = [pol.wait(a, rng) for a in range(1, 12)]
    assert all(0.75 * min(120, 2 * 2 ** (a - 1)) <= w <= 1.25 * min(120, 2 * 2 ** (a - 1)) for a, w in zip(range(1, 12), ws))
    assert max(ws) <= 150 and ws[-1] >= 90                                  # capped near 120 s


def test_outage_longer_than_retries_saves_progress_and_resume_continues_exactly(isolated_data_dir):
    end = S + timedelta(days=5)
    # first run: ~2 windows succeed, then Coinbase times out for good
    broken = FakeCoinbase(down_from_call=3)
    with pytest.raises(fc.FetchInterrupted) as exc:
        fc.download_timeframe(broken, "5m", S, end, retry=FAST, pause_s=0, sleep=NO_SLEEP, log=lambda *a: None)
    assert exc.value.completed_through is not None
    saved = fc.load_existing("5m")
    assert len(saved) == 2 * 349 and saved.index.is_unique                  # both completed windows on disk
    last = saved.index.max()
    # second run: resumes from the last completed candle + 1 bar, not from S
    healthy = FakeCoinbase()
    df = fc.download_timeframe(healthy, "5m", S, end, retry=FAST, pause_s=0, sleep=NO_SLEEP, log=lambda *a: None)
    assert healthy.calls[0][0] == last.to_pydatetime() + STEP
    assert list(df.index) == list(expected_index(S, end))                  # complete, contiguous, no duplicates
    assert (df.close == [price(t) + 1 for t in df.index]).all()
    assert not fc.partial_path("5m").exists()


def test_resume_does_not_restart_from_2017_when_file_already_covers_history():
    start = datetime(2017, 1, 1, tzinfo=timezone.utc)
    have_until = datetime(2021, 3, 27, tzinfo=timezone.utc)
    idx = pd.date_range(have_until - timedelta(days=1), have_until, freq="5min", tz="UTC", inclusive="left")
    data.save_candles(pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0}, index=idx),
                      data.data_path("5m"))
    client = FakeCoinbase()
    fc.download_timeframe(client, "5m", start, have_until + timedelta(hours=6), pause_s=0, sleep=NO_SLEEP,
                          log=lambda *a: None)
    assert client.calls[0][0] == have_until                                 # continues at 2021-03-27, not 2017
    assert min(c[0] for c in client.calls) >= have_until


def test_permanent_error_stops_immediately_without_retries_and_keeps_progress():
    client = FakeCoinbase(plan={2: ExchangeAPIError("HTTP 400", status=400)})
    sleeps = []
    with pytest.raises(fc.FetchInterrupted, match="permanent error"):
        fc.download_timeframe(client, "5m", S, S + timedelta(days=3), retry=FAST, pause_s=0,
                              sleep=lambda s: sleeps.append(s), log=lambda *a: None)
    assert len(client.calls) == 2 and all(s == 0 for s in sleeps)
    assert len(fc.load_existing("5m")) == 349


def test_rate_limit_429_is_retried():
    client = FakeCoinbase(plan={1: ExchangeAPIError("HTTP 429", status=429)})
    df = fc.download_timeframe(client, "5m", S, S + timedelta(hours=2), retry=FAST, pause_s=0, sleep=NO_SLEEP,
                               log=lambda *a: None)
    assert len(df) == 24 and len(client.calls) == 2


def test_checkpoint_is_written_after_every_request(monkeypatch):
    sizes = []
    real_append = fc.Checkpoint.append

    def spy(self, rows):
        real_append(self, rows)
        sizes.append(len(fc.read_partial(self.path)))
    monkeypatch.setattr(fc.Checkpoint, "append", spy)
    fc.download_timeframe(FakeCoinbase(), "5m", S, S + timedelta(days=2), pause_s=0, sleep=NO_SLEEP, log=lambda *a: None)
    assert sizes == [349, 576]                                             # durable after each window


def test_truncated_checkpoint_line_from_a_crash_is_tolerated():
    end = S + timedelta(days=2)
    with pytest.raises(fc.FetchInterrupted):
        fc.download_timeframe(FakeCoinbase(down_from_call=2), "5m", S, end, retry=FAST, pause_s=0,
                              sleep=NO_SLEEP, log=lambda *a: None)
    with open(fc.partial_path("5m"), "a") as fh:
        fh.write("1616457600,50000.0,500")                                 # half a line, as if the process died
    df = fc.download_timeframe(FakeCoinbase(), "5m", S, end, pause_s=0, sleep=NO_SLEEP, log=lambda *a: None)
    assert list(df.index) == list(expected_index(S, end))


def test_ctrl_c_mid_download_keeps_completed_windows():
    class Interrupting(FakeCoinbase):
        def get_candles(self, *a):
            if len(self.calls) == 2:
                raise KeyboardInterrupt
            return super().get_candles(*a)
    with pytest.raises(KeyboardInterrupt):
        fc.download_timeframe(Interrupting(), "5m", S, S + timedelta(days=3), pause_s=0, sleep=NO_SLEEP,
                              log=lambda *a: None)
    assert len(fc.load_existing("5m")) == 2 * 349


def test_cli_reports_pause_then_completes_on_rerun(monkeypatch, capsys, isolated_data_dir):
    clients = [FakeCoinbase(down_from_call=3), FakeCoinbase()]
    monkeypatch.setattr(fc, "make_client", lambda settings: clients.pop(0))
    monkeypatch.setattr(fc.time, "sleep", lambda s: None)
    args = ["--start", "2021-03-20", "--end", "2021-03-25", "--tf", "5m", "--retries", "3"]
    assert fc.main(args) == 1
    err = capsys.readouterr().err
    assert "DOWNLOAD PAUSED" in err and "Re-run the same command to continue" in err and "698 5m candles" in err
    assert fc.main(args) == 0
    out = capsys.readouterr().out
    assert "resuming from" in out and "1,440 candles" in out
    df = load_candles(data.data_path("5m"))
    assert len(df) == 1440 and df.index.is_unique and (isolated_data_dir / "MANIFEST.json").is_file()
    assert not fc.partial_path("5m").exists()


def test_cli_still_requires_paper_mode(monkeypatch, capsys):
    monkeypatch.setenv("PAPER_MODE", "false")
    assert fc.main(["--tf", "5m"]) == 2
