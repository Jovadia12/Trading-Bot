# BTC-Trading-Bot

Research and **paper-trading-only** tooling. No live order path exists in this project:
- the Coinbase transport only allows allowlisted read-only GET endpoints;
- order and funds methods raise `LIVE ORDER EXECUTION DISABLED: paper mode only.`;
- every entry point refuses to start unless `PAPER_MODE=true`.

Strategy rules and research results: `MULTI_CRYPTO_MOMENTUM.md` and `research_results/`.

## Paper-trading dashboard

The dashboard is a local, read-only web view of the running `multi_crypto_momentum` paper session.

### Start it

From the repo root, in a separate terminal. The paper runner keeps running untouched.

```bash
pip install "flask>=3.0,<4"                # once
PAPER_MODE=true python3 -m dashboard       # options: --port 8050 --session mcm_<UTC> --records-dir <dir>
```

Then open **http://127.0.0.1:8050**. Stop it with Ctrl+C; that has no effect on the paper runner.

### What each section shows

The page auto-refreshes every 3 seconds. Missing values show as **N/A** and are never estimated.

| Tab | Contents |
|---|---|
| **Overview** | Equity, starting balance, total / today / this-month P&L ($ and %), cash, invested capital, gross exposure, open positions and closed trades, current drawdown, bot status, last market-data refresh, next decision time, error count, equity curve. A P&L breakdown shows that total = realized + unrealized − entry fees of open positions. |
| **Open positions** | Only positions the paper engine actually **filled**: entry time, open price and fill price, current price, size, allocation %, unrealized P&L ($ and %), 40-day return, EMA200, BTC regime, and the signal that caused the entry. |
| **Trade history** | Every paper trade, filterable All / Open / Closed: entry and exit time and price, size, fees, slippage, gross P&L (after slippage, before fees), net P&L, return %, entry and exit reasons. |
| **Strategy** | The current rules, plus each coin's signal state on its latest **completed** daily candle: 40-day return, EMA200, price, long/short eligibility, BTC regime, position, current signal and reason. A signal is not an order. |
| **Performance** | Equity curve, daily P&L, cumulative P&L, drawdown, monthly table, win rate, profit factor, average win and loss, best and worst trade, long vs short. |
| **Bot status** | Paper mode ON, live trading OFF, bot and data-feed status, last refresh, next decision, data errors, paper orders (filled) vs live orders (always 0), whether an order endpoint was called, and the signal → order → fill pipeline counts. |

### How paper mode is enforced

The dashboard doesn't relax any existing safety controls, and adds its own:
- It requires `PAPER_MODE=true`, like every entry point.
- It binds to loopback only (`127.0.0.1`, `localhost`, `::1`) and refuses any other host.
- It has **GET routes only**; POST, PUT, PATCH and DELETE return 405.
- It imports no exchange, execution or strategy code and makes **no network calls**.
- It never loads `.env` (Flask's `load_dotenv=False`), so API credentials never enter its process.
- The page's Content-Security-Policy only allows same-origin resources.

Tests in `tests/test_dashboard.py` check all of the above.

### Where the data comes from

The dashboard only **reads** what the paper runner already writes:
- `paper_trading/records/mcm_<UTC start>/state.json`, rewritten atomically every poll;
- `final_report.json`, once the session ends.

By default it uses the newest session. It is not a second trading engine and computes no trades.

Sessions started with an older runner version have no recorded per-coin EMA200, eligibility or order-endpoint flag; those show as N/A. They appear after the runner is next restarted with the current version.
