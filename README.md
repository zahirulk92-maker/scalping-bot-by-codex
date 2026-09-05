# Scalping Bot — Phase 11 Forward-Test Validation Gate

THIS PROJECT IS CURRENTLY PAPER-TRADING MONITORING ONLY. NO LIVE TRADING OR EXCHANGE EXECUTION IS IMPLEMENTED.

## Phase 10 production hardening

Docker, readiness/liveness checks, SQLite backup/export utilities, bounded heavy-job execution, request correlation IDs, safe error envelopes, structured/rotating logs, and the `/operations` dashboard are included. See [operations documentation](docs/operations.md). **PAPER RESULTS AND BACKTESTS DO NOT GUARANTEE FUTURE RETURNS.**

## Phase 11 forward-test validation gate

The `/validation` dashboard and `/api/validation/*` endpoints produce only `PASS`, `FAIL`, `INSUFFICIENT_DATA`, or `PAUSED` decisions for the complete active paper-forward session. A PASS means **eligible for manual review only**—it does not authorize, configure, or create live trading. The gate requires at least 30 closed trades and seven forward days by default, then evaluates net expectancy in R after costs, profit factor, drawdown, daily-loss-lock events, losing streaks, symbol coverage, operational health, data quality, configuration consistency, historical comparison (when current in-memory research evidence exists), and rolling 7/30-day performance.

Hard failures can pause only new paper entries when `PAUSE_PAPER_ON_VALIDATION_FAIL=true`; open simulated positions continue their normal stop/target monitoring. Directional dependence, cost degradation, recent decay, historical deviation, and configuration mismatch are surfaced as explainable warnings. Validation snapshots and transitions are stored in SQLite. **PASS DOES NOT AUTHORIZE LIVE TRADING.**

This monorepo supplies a safe, testable cryptocurrency market-monitoring foundation. It receives public Binance Spot 1-minute kline data, validates normalized candles, calculates indicators and signals, produces risk plans, simulates paper positions, and replays the same logic against historical data.

## Architecture

```text
Public historical candles → chronological replay → indicator engine → strategy signal engine → risk plan engine → paper execution engine → audited result and analytics
```

## Technology stack

- Backend: Python 3.12+, FastAPI, Pydantic, Uvicorn, Pytest
- Frontend: Next.js, TypeScript, Tailwind CSS
- Communication: REST plus a backend-owned dashboard WebSocket

## Folder structure

```text
backend/
  app/
    api/routes/       # health, status, market REST and dashboard WebSocket
    core/             # logging and exceptions
    market/            # normalized models, store, service, Binance adapter
    indicators/        # incremental EMA, RSI, ATR, VWAP, and volume engine
    strategy/          # deterministic signal-only scoring and filters
    risk/              # ATR stops, Decimal sizing, guards, and bounded plan store
    execution/         # deterministic paper fills, positions, account, and trade history
    backtest/          # historical loader/cache, chronological replay, journal, analytics
    optimization/      # bounded candidate evaluation, validation ranking, and holdout audit
    db/                # versioned SQLite schema and explicit repositories
    monitoring/        # forward-test health, freshness, and alert deduplication
    models/ services/
  tests/
  logs/
frontend/
  app/                # Next.js App Router
  components/
  lib/api.ts          # typed API client
  types/
data/                 # reserved for future local data
```

## Setup

Copy `.env.example` to `.env` in the repository root and adjust non-secret paper settings if needed. `TRADING_MODE` must remain `paper`; `live` is deliberately rejected at startup.

### Backend

From `backend/`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The available endpoints include the existing paper APIs plus simulation-only backtests and research-only optimization: `POST /api/optimization/run`, `GET /api/optimization`, `GET /api/optimization/{run_id}`, and `POST /api/optimization/{run_id}/final-evaluate`. Phase 9 adds `GET /api/paper/session`, `/api/paper/metrics`, `/api/paper/metrics/daily`, `/api/paper/metrics/symbols`, `/api/paper/audit`, `/api/system/health`, `/api/system/database`, and `/api/system/alerts`. Historical public data is cached in `data/backtest/` by exact range when fetched.

## Durable forward-paper sessions

Phase 9 stores simulated forward-test state in SQLite at `data/scalping_bot.db` by default (`DATABASE_URL=sqlite:///./data/scalping_bot.db`). The parent directory is created automatically. Schema upgrades are versioned in `schema_migrations`; startup applies pending built-in migrations transactionally and fails clearly if initialization fails. Do not delete this file during normal operation: it contains the active PAPER session, account, open positions, trades, signal/risk audit trail, metrics, and alerts.

On startup the application resumes the latest active PAPER session rather than resetting to 100 USDT. Its saved configuration snapshot is reconstructed and used for the session, so changing `.env` does not mutate an active forward test. `STRATEGY_PROFILE=baseline` is the default. `research_candidate` requires an explicit JSON object in `RESEARCH_CANDIDATE_PARAMETERS_JSON`, limited to the same validated Phase 8 parameter allowlist; it is never selected or activated automatically.

Open paper positions restore as `RECOVERY_PENDING`, which blocks new paper entries. The backend fetches public historical candles, replays missed 1-minute candles using the normal conservative stop-first policy, and persists a resulting close exactly once. If reconciliation fails, state becomes `RECOVERY_ERROR` and new entries remain blocked. No position is assumed closed merely because the backend was offline.

Closed paper trades and account changes are persisted atomically in one SQLite transaction. Entries, signal snapshots, and risk plans use stable lifecycle identifiers (`signal_id → plan_id → position_id → trade_id`) and idempotent unique writes. Position progress is persisted on closed candles, avoiding per-tick write amplification.

Forward metrics include paper lifecycle counts, PnL, fees, expectancy, profit factor, R proxy, current/max drawdown, daily UTC slices, and BTC/ETH/SOL breakdowns. Historical comparisons remain descriptive research only; no forward result auto-retunes strategy values. `GET /api/system/health` provides component status and freshness. Internal alerts are persisted and deduplicated by code/symbol with `ALERT_COOLDOWN_SECONDS`; no Telegram, email, Discord, or other external notification is sent.

### Frontend

From `frontend/`:

```powershell
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local` if the API is hosted somewhere other than `http://127.0.0.1:8000`. Configure `FRONTEND_ORIGINS` in the root `.env` when the dashboard is served from a different permitted origin.

## Tests and quality checks

From `backend/`, run `pytest`. From `frontend/`, run `npm run lint`, `npm run typecheck`, and `npm run build`.

## Safety guarantees

- Startup fails for invalid configuration, empty symbols, invalid balances/risk values, unsupported market exchanges, and any mode other than `paper`.
- Public Binance data is normalized, UTC-timestamped, validated, deduplicated, and retained in bounded per-symbol history.
- Official EMA 9/21, Wilder RSI 14, Wilder ATR 14, UTC-daily VWAP, and Volume MA 20 update only after validated closed candles. EMA seeds from an SMA; RSI flat markets report 50, no-loss markets 100, and no-gain markets 0.
- Historical public kline warm-up is best-effort: a failure leaves indicators honestly not ready while public market streaming continues.
- The strategy engine evaluates only official closed-candle indicator snapshots. Its transparent 100-point score weights trend (30), VWAP confirmation (20), RSI zone (20), volume confirmation (20), and ATR guardrails (10). Stale data, missing values, duplicate/out-of-order candles, or failed mandatory strategy rules produce `NO_TRADE`.
- The risk engine accepts only actionable LONG/SHORT signals. It uses the signal candle close as entry, `ATR × 1.5` for the stop distance, and `stop distance × 1.5` for take-profit distance. Planned risk is `equity × risk_per_trade`; estimated quantity is `risk ÷ stop distance`. A maximum-notional cap reduces quantity and recomputes actual risk.
- Plans are rejected for stale/unhealthy inputs, invalid/tiny/wide ATR stops, signal quality failures, daily-loss or open-position limits, insufficient reward:risk, or costs that remove expected reward. Planning-only round-trip fee and slippage estimates are configurable.
- An approved plan waits for the next eligible public market observation. Long entries pay positive entry slippage and shorts receive negative entry slippage; exits are always adverse. Entry and exit fees are `notional × PAPER_FEE_BPS / 10,000`. Long net PnL is `(exit - entry) × quantity - fees`; short net PnL is `(entry - exit) × quantity - fees`.
- Open paper positions use public market observations to monitor stop and target levels. If a historical OHLC observation crosses both levels, the simulator deterministically assumes the stop loss happened first. At 00:00 UTC it resets only `realized_pnl_today`; equity, total PnL, fees, and trade history remain intact.
- Backtests replay normalized closed candles chronologically. A signal created from candle N cannot enter on that candle: pending plans first become eligible at candle N+1, using its **open** plus deterministic entry slippage. Existing positions evaluate the later candle's range with stop-first collision handling. If a candle opens through a stop or target, the simulated exit uses that adverse/open gap price before applying exit slippage.
- Results include an equity curve, drawdown, win rate, profit factor (null when there are no losing trades), net expectancy, average R, per-symbol and long/short slices, fees, and an audit journal.
- Optimization is a bounded grid search over an explicit allowlist: EMA periods, RSI bounds, signal score, VWAP/EMA/volume/ATR filters, ATR stop multiplier, and target reward:risk. Every candidate is rebuilt through the same validated `Settings` model; balance, execution mode, secrets, and non-strategy controls cannot be varied.
- Each optimization preserves a current-settings baseline and uses chronological 60% train, 20% validation, and 20% holdout partitions. Candidate selection uses validation only. The holdout is unavailable until the user explicitly calls final evaluation for the selected candidate.
- The transparent 0–100 validation score weighs positive expectancy (30%), capped profit factor (25%), drawdown control (25%), and cross-symbol consistency (20%), then reduces thin samples. Selection additionally requires the configured minimum trade count, maximum drawdown, and minimum profit factor.
- Selected candidates receive normal/high/stress cost replay plus rolling walk-forward checks when the requested range is long enough. Flags include thin data, drawdown, low profit factor, single-symbol dependence, parameter sensitivity, cost sensitivity, walk-forward inconsistency, and holdout degradation.
- Optimization output is research evidence only. It never changes the running configuration, modifies paper execution, or creates any order.
- The dashboard connects only to this backend; it never invents prices, PnL, trades, or backend data when offline.
- All fills, positions, balances, fees, and PnL are durable PAPER simulations in local SQLite. They survive backend restart within the same active paper session. No exchange credentials, account access, private streams, real order route, manual controls, leverage, futures, margin, deposits, withdrawals, or live execution exists.

## Intentionally deferred

Any live exchange execution is deliberately out of scope. Forward-paper state is durable in SQLite; bounded in-memory backtest and optimization research results reset on restart. **BACKTEST RESULTS DO NOT GUARANTEE FUTURE PERFORMANCE.**
