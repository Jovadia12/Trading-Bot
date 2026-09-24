"""Generate a SYNTHETIC Coinbase Advanced WebSocket replay file for offline tests.

The message *shapes* follow the official docs/SDK (channel l2_data / market_trades / ticker /
heartbeats, sequence_num, events[...]). The *prices and sizes are made up*. Nothing produced
from this file is market evidence.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

T0 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)


def ts(sec: float) -> str:
    return (T0 + timedelta(seconds=sec)).isoformat().replace("+00:00", "Z")


def main(path: Path) -> None:
    seq = 0
    lines = ["# SYNTHETIC DATA - message format mirrors Coinbase Advanced WS; prices/sizes are invented"]

    def emit(channel, t, events):
        nonlocal seq
        lines.append(json.dumps({"channel": channel, "client_id": "", "timestamp": ts(t),
                                 "sequence_num": seq, "events": events}))
        seq += 1

    emit("subscriptions", 0, [{"subscriptions": {"level2": ["BTC-USD"], "market_trades": ["BTC-USD"]}}])
    bid, ask = 64000.00, 64000.01
    snap = []
    live_bids, live_asks = set(), set()
    for i in range(10):
        live_bids.add(round(bid - i * 0.5, 2)); live_asks.add(round(ask + i * 0.5, 2))
        snap.append({"side": "bid", "event_time": ts(0), "price_level": f"{bid - i * 0.5:.2f}", "new_quantity": f"{0.05 + i * 0.02:.8f}"})
        snap.append({"side": "offer", "event_time": ts(0), "price_level": f"{ask + i * 0.5:.2f}", "new_quantity": f"{0.05 + i * 0.02:.8f}"})
    emit("l2_data", 0.1, [{"type": "snapshot", "product_id": "BTC-USD", "updates": snap}])
    t = 0.1
    # 60 seconds of activity; price dips at t~10s (trades through the bid), recovers later.
    for k in range(1, 121):
        t = 0.1 + k * 0.5
        drift = -3.0 if 10 <= t < 20 else (2.0 if 30 <= t < 40 else 0.0)
        bid = round(bid + drift * 0.05, 2)
        ask = round(bid + 0.01, 2)
        ups = []
        # keep the synthetic book uncrossed: delete levels the new top of book has moved past
        for p in sorted(b for b in live_bids if b > bid):
            ups.append({"side": "bid", "event_time": ts(t), "price_level": f"{p:.2f}", "new_quantity": "0"})
            live_bids.discard(p)
        for p in sorted(a for a in live_asks if a < ask):
            ups.append({"side": "offer", "event_time": ts(t), "price_level": f"{p:.2f}", "new_quantity": "0"})
            live_asks.discard(p)
        ups.append({"side": "bid", "event_time": ts(t), "price_level": f"{bid:.2f}", "new_quantity": "0.06000000"})
        ups.append({"side": "offer", "event_time": ts(t), "price_level": f"{ask:.2f}", "new_quantity": "0.07000000"})
        live_bids.add(bid); live_asks.add(ask)
        emit("l2_data", t, [{"type": "update", "product_id": "BTC-USD", "updates": ups}])
        if k % 2 == 0:
            price, side = (bid, "SELL") if drift < 0 else (ask, "BUY")
            emit("market_trades", t + 0.01, [{"type": "update", "trades": [
                {"trade_id": str(1000 + k), "product_id": "BTC-USD", "price": f"{price:.2f}",
                 "size": "0.01500000", "side": side, "time": ts(t + 0.01)}]}])
        if k % 4 == 0:
            emit("ticker", t + 0.02, [{"type": "update", "tickers": [
                {"type": "ticker", "product_id": "BTC-USD", "price": f"{bid:.2f}", "best_bid": f"{bid:.2f}",
                 "best_bid_quantity": "0.06", "best_ask": f"{ask:.2f}", "best_ask_quantity": "0.07"}]}])
        if k % 10 == 0:
            emit("heartbeats", t + 0.03, [{"current_time": ts(t), "heartbeat_counter": k // 10}])
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(Path(__file__).with_name("ws_btcusd_synthetic.jsonl"))
