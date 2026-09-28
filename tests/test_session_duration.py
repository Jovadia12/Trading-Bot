"""--duration N must end the whole paper session after ~N seconds and still print the report.

Uses local fake WebSocket servers (127.0.0.1 only) that imitate the failure modes behind the
original bug: a busy feed, a half-dead peer that never answers the close handshake, a silent
peer, an unreachable host, and Ctrl+C.
"""
import asyncio
import base64
import hashlib
import json
import os
import signal
import socket
import threading
import time

import pytest
import requests
import websockets

import market_data.websocket_feed as wf
from market_data.websocket_feed import CoinbaseMarketDataFeed, SessionClock

DURATION = 2.0
SLACK = 1.5                       # scheduler/CI jitter
CLOSE_BOUND = wf.CLOSE_TIMEOUT_S + 0.5


def _snapshot(levels=200):
    ups = [{"side": "bid", "price_level": f"{64000 - i * 0.01:.2f}", "new_quantity": "0.1"} for i in range(levels)]
    ups += [{"side": "offer", "price_level": f"{64000.01 + i * 0.01:.2f}", "new_quantity": "0.1"} for i in range(levels)]
    return {"channel": "l2_data", "timestamp": "2026-09-28T00:00:00Z", "sequence_num": 0,
            "events": [{"type": "snapshot", "product_id": "BTC-USD", "updates": ups}]}


class _ServerThread:
    """Runs an asyncio server factory in a background thread; yields its port."""

    def __init__(self, start):
        self._start, self.port, self._ready = start, None, threading.Event()
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._run, daemon=True).start()
        assert self._ready.wait(5)

    def _run(self):
        asyncio.set_event_loop(self._loop)
        server = self._loop.run_until_complete(self._start())
        self.port = server.sockets[0].getsockname()[1]
        self._ready.set()
        self._loop.run_forever()


async def _busy_server():
    async def handler(ws):
        seq = 1
        await ws.send(json.dumps(_snapshot()))
        while True:
            await ws.send(json.dumps({"channel": "l2_data", "timestamp": "2026-09-28T00:00:01Z", "sequence_num": seq,
                                      "events": [{"type": "update", "updates": [
                                          {"side": "bid", "price_level": "63999.50", "new_quantity": str(seq % 7 + 1)}]}]}))
            seq += 1
            await asyncio.sleep(0.005)
    return await websockets.serve(handler, "127.0.0.1", 0, max_size=None)


def _raw_ws_server(mode):
    """Handshake + snapshot, then either stream forever ignoring close ('noclose') or go silent ('stall')."""
    def frame(p):
        n = len(p)
        head = bytes([0x81, n]) if n < 126 else (bytes([0x81, 126]) + n.to_bytes(2, "big") if n < 65536
                                                   else bytes([0x81, 127]) + n.to_bytes(8, "big"))
        return head + p

    async def handle(r, w):
        req = b""
        while b"\r\n\r\n" not in req:
            req += await r.read(4096)
        key = [l.split(b": ", 1)[1] for l in req.split(b"\r\n") if l.lower().startswith(b"sec-websocket-key")][0]
        acc = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
        w.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                b"Sec-WebSocket-Accept: " + acc + b"\r\n\r\n")
        w.write(frame(json.dumps(_snapshot()).encode()))
        await w.drain()
        seq = 1
        while True:
            if mode == "noclose":
                w.write(frame(json.dumps({"channel": "heartbeats", "timestamp": "2026-09-28T00:00:01Z",
                                          "sequence_num": seq, "events": [{"heartbeat_counter": seq}]}).encode()))
                seq += 1
                try:
                    await w.drain()
                except Exception:
                    return
                await asyncio.sleep(0.05)
            else:
                await asyncio.sleep(3600)

    async def start():
        return await asyncio.start_server(handle, "127.0.0.1", 0)
    return start


@pytest.fixture(scope="module")
def servers():
    return {"busy": _ServerThread(_busy_server).port,
            "noclose": _ServerThread(_raw_ws_server("noclose")).port,
            "stall": _ServerThread(_raw_ws_server("stall")).port}


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port   # nothing listens here -> connection refused


@pytest.fixture
def run_main(monkeypatch, tmp_path, capsys):
    """Run paper_trading.main against a local ws:// URL with REST mocked (fast, offline)."""
    class R:
        status_code, text = 503, ""

        def json(self):
            return {}
    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kw: R())

    def go(url, *extra):
        import paper_trading.runner as runner
        monkeypatch.setattr(runner, "LIVE_WS_URL", url)
        t0 = time.monotonic()
        rc = runner.main(["--duration", str(DURATION), "--records-dir", str(tmp_path), *extra])
        elapsed = time.monotonic() - t0
        out = capsys.readouterr()
        report = dict(l.split(": ", 1) for l in out.out.splitlines() if ": " in l)
        return rc, elapsed, out, report
    return go


def test_busy_feed_stops_at_duration_and_prints_report(servers, run_main):
    rc, elapsed, out, rep = run_main(f"ws://127.0.0.1:{servers['busy']}")
    assert DURATION - 0.2 <= elapsed <= DURATION + SLACK, elapsed
    assert "--- SESSION REPORT" in out.out and rep["session_end"] == "duration reached"
    assert rep["market_data_received"] == "YES" and rep["bid"] != "n/a" and int(rep["market_data_messages"]) > 50
    assert rep["order_endpoint_called"] == "NO" and rc == 0
    assert float(rep["session_seconds"]) <= DURATION + SLACK


@pytest.mark.parametrize("mode", ["noclose", "stall"])
def test_half_dead_or_silent_peer_cannot_extend_the_session(servers, run_main, mode):
    rc, elapsed, out, rep = run_main(f"ws://127.0.0.1:{servers[mode]}")
    assert elapsed <= DURATION + CLOSE_BOUND + SLACK, elapsed      # was ~33 s before the fix
    assert "--- SESSION REPORT" in out.out and rep["session_end"] == "duration reached"


def test_unreachable_feed_with_retries_stops_at_duration(run_main):
    rc, elapsed, out, rep = run_main(f"ws://127.0.0.1:{_free_port()}")
    assert elapsed <= DURATION + SLACK, elapsed
    assert "--- SESSION REPORT" in out.out and rep["market_data_received"] == "NO" and rc == 1


def test_ctrl_c_stops_gracefully_and_still_reports(servers, run_main, monkeypatch):
    monkeypatch.setattr("tests.test_session_duration.DURATION", 30.0)
    threading.Timer(1.0, os.kill, (os.getpid(), signal.SIGINT)).start()
    rc, elapsed, out, rep = run_main(f"ws://127.0.0.1:{servers['busy']}")
    assert elapsed < 1.0 + SLACK + CLOSE_BOUND, elapsed
    assert rep["session_end"] == "interrupted (Ctrl+C)" and "--- SESSION REPORT" in out.out
    assert "Ctrl+C received" in out.err


def test_feed_stream_alone_honours_stop_after(servers):
    async def go():
        feed = CoinbaseMarketDataFeed(url=f"ws://127.0.0.1:{servers['noclose']}", idle_timeout=30)
        n = 0
        async for _ in feed.stream(stop_after=DURATION):
            n += 1
        return n
    t0 = time.monotonic()
    assert asyncio.run(go()) > 0
    assert time.monotonic() - t0 <= DURATION + CLOSE_BOUND + SLACK


def test_session_clock_counts_wall_time_when_monotonic_pauses(monkeypatch):
    """macOS can pause the monotonic clock during sleep; the wall clock must still end the session."""
    clock = SessionClock(3600)
    real_time = time.time
    monkeypatch.setattr(wf.time, "time", lambda: real_time() + 3601)     # woke up an hour later
    assert clock.expired() and clock.elapsed() >= 3600


def test_session_clock_ignores_wall_clock_going_backwards(monkeypatch):
    clock = SessionClock(1.0)
    real_time = time.time
    monkeypatch.setattr(wf.time, "time", lambda: real_time() - 3600)
    time.sleep(1.05)
    assert clock.expired()    # monotonic still advances
