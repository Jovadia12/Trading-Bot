import json
from decimal import Decimal

import pytest

from market_data.models import spread_bps
from market_data.order_book import L2OrderBook
from market_data.websocket_feed import FeedState, parse_message, replay_file, subscribe_messages
from tests.conftest import make_book


def test_spread_bps():
    assert spread_bps(Decimal("99.99"), Decimal("100.01")) == Decimal("2")
    with pytest.raises(ValueError):
        spread_bps(Decimal(0), Decimal(1))


def test_book_updates_and_removal():
    b = make_book([(100, 1), (99, 2)], [(101, 1), (102, 3)])
    assert b.best_bid() == (Decimal(100), Decimal(1)) and b.best_ask() == (Decimal(101), Decimal(1))
    b.apply("offer", "101", "0")          # Coinbase uses "offer" for asks
    assert b.best_ask()[0] == Decimal(102)
    b.apply("bid", "100.5", "0.5")
    assert b.best_bid()[0] == Decimal("100.5")
    assert b.mid() == (Decimal("100.5") + 102) / 2


def test_walk_by_quote_and_base_with_partial():
    b = make_book([(100, 1)], [(101, 1), (102, 1)])
    w = b.walk("BUY", quote_size=Decimal(202))                       # 1 @101 + 0.99.. @102
    assert w.complete and w.levels_used == 2 and w.touch == Decimal(101)
    assert abs(w.notional - Decimal(202)) < Decimal("1e-9")
    w2 = b.walk("BUY", base_size=Decimal(5))                          # only 2 BTC available
    assert not w2.complete and w2.filled_base == Decimal(2) and w2.vwap == Decimal("101.5")
    w3 = b.walk("SELL", base_size=Decimal("0.5"))
    assert w3.vwap == Decimal(100)


def test_subscribe_messages_format():
    msgs = subscribe_messages(["BTC-USD"], ["level2", "heartbeats"])
    assert msgs == [{"type": "subscribe", "product_ids": ["BTC-USD"], "channel": "level2"},
                    {"type": "subscribe", "product_ids": ["BTC-USD"], "channel": "heartbeats"}]
    assert all("jwt" not in m for m in msgs)  # public channels never carry credentials


def _msg(channel, seq, events, ts="2026-09-24T12:00:00.123456789Z"):
    return json.dumps({"channel": channel, "timestamp": ts, "sequence_num": seq, "events": events})


def test_parse_l2_ticker_trades_and_gap():
    st = FeedState(L2OrderBook())
    parse_message(_msg("l2_data", 0, [{"type": "snapshot", "product_id": "BTC-USD", "updates": [
        {"side": "bid", "price_level": "100", "new_quantity": "1"},
        {"side": "offer", "price_level": "101", "new_quantity": "2"}]}]), st)
    assert st.book.ready and st.book.spread_bps() is not None
    ev = parse_message(_msg("market_trades", 1, [{"type": "update", "trades": [
        {"trade_id": "1", "product_id": "BTC-USD", "price": "100.5", "size": "0.1", "side": "BUY",
         "time": "2026-09-24T12:00:00.5Z"}]}]), st)
    assert ev[0].kind == "trade" and ev[0].payload.price == Decimal("100.5")
    ev = parse_message(_msg("ticker", 2, [{"type": "update", "tickers": [
        {"product_id": "BTC-USD", "price": "100.5", "best_bid": "100", "best_ask": "101",
         "best_bid_quantity": "1", "best_ask_quantity": "2"}]}]), st)
    assert ev[0].kind == "ticker" and ev[0].payload.spread_bps > 0
    ev = parse_message(_msg("heartbeats", 5, [{"heartbeat_counter": 3}]), st)   # 3,4 missing
    assert ev[0].kind == "gap" and st.gaps == 1


def test_replay_fixture_keeps_book_consistent():
    n = 0
    for ev in replay_file("tests/fixtures/ws_btcusd_synthetic.jsonl"):
        if ev.kind == "book":
            n += 1
            assert not ev.payload.is_crossed()
    assert n > 100
