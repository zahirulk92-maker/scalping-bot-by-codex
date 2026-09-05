# Operations guide

## Safety invariant

This platform is **PAPER TRADING ONLY**. `TRADING_MODE` and `EXECUTION_MODE` are validated as `paper`; no Binance private API, account access, live orders, futures, margin, leverage, deposits, or withdrawals exists.

## Profiles and startup

Allowed `APP_ENV` values are `development`, `test`, and `paper-production`. Unknown values fail startup. For a hardened deployment, set `APP_ENV=paper-production`, keep both modes `paper`, configure an explicit `FRONTEND_ORIGINS`, and run:

```bash
docker compose up -d
```

For local development, start the backend from `backend/` with `uvicorn app.main:app --host 127.0.0.1 --port 8000`, then start the frontend from `frontend/` with `npm run dev`.

## Health and readiness

`/api/system/live` shows whether the process is alive. `/api/system/ready` distinguishes ready, degraded, and not-ready states. A stale public feed is degraded rather than dead; a database or recovery failure makes the process not ready. `/api/system/health`, `/api/system/metrics`, `/api/system/diagnostics`, and `/api/system/version` expose only safe operational information.

## Persistence, restart, and recovery

The default SQLite database is `data/scalping_bot.db`; in Docker it is `/app/data/scalping_bot.db` on the `paper_data` volume. WAL mode and foreign keys are enabled per write connection, and startup performs `PRAGMA quick_check`. The active paper session resumes after restart. Open positions are marked recovery-pending, reconciled against public candles using stop-first handling, and block new paper entries until complete. A failed reconciliation remains fail-closed.

## Forward-test validation gate

The validation gate evaluates the complete chronological active paper session after each closed paper trade, at startup, and every 15 minutes. It persists each snapshot and exposes `/api/validation/status`, `/api/validation/rules`, and paginated `/api/validation/history`. Minimum evidence is `MIN_FORWARD_TRADES=30` and `MIN_FORWARD_DAYS=7`; preferred evidence is 100 trades and 30 days. Until both minimums are met, the only correct outcome is `INSUFFICIENT_DATA`.

Once enough data exists, hard rules require positive net expectancy and at least `MIN_FORWARD_EXPECTANCY_R`, `MIN_FORWARD_PROFIT_FACTOR`, drawdown no greater than `MAX_FORWARD_DRAWDOWN_PERCENT`, no more than `MAX_DAILY_LOCK_EVENTS`, no more than `MAX_CONSECUTIVE_LOSSES`, and at least `MIN_HEALTHY_SYMBOLS` independently acceptable symbols. A zero-loss profit-factor case is explicitly treated as unbounded only when net results are positive. Critical database/recovery health failures cannot PASS. Historical comparison is transparent and warning-only when a current in-memory backtest exists; its absence is never fabricated.

Warnings cover cost degradation, recent rolling decay, long/short dependence, historical divergence, stale-feed data quality, configuration mismatch, and time underwater. `PAUSE_PAPER_ON_VALIDATION_FAIL=true` blocks new simulated entries after a FAIL but never abandons an existing simulated position. There is no validation override button, no live-trading button, and no automatic execution transition. **PASS means eligible for manual review only; it never authorizes live trading.**

## Backup and restore

Create a consistent timestamped backup with:

```bash
PYTHONPATH=backend python -m app.tools.backup
```

The utility uses SQLite’s backup API, runs an integrity check on the copy, and retains only `BACKUP_RETENTION_COUNT` newest backups under `data/backups/`. It never deletes the active database. Restore is an explicit maintenance action: stop backend containers, preserve the current database, copy a verified backup into the configured database path, then start the backend and inspect readiness. The application never auto-restores a backup.

## Exports, logs, and incidents

`python -m app.tools.export paper-trades --format csv` exports durable paper records; `daily-metrics` and `alerts` are also supported. The download endpoint `/api/system/exports/{kind}?format=json|csv` additionally supports `backtest-summaries`, `optimization-summaries`, and `monitoring-metrics`; research exports cover the current bounded in-memory research history only. Resolved alerts older than `ALERT_RETENTION_DAYS` are pruned at startup; active alerts are retained. Development logs are readable text; `LOG_FORMAT=json` produces structured stdout/file logs. File logs rotate at 5 MB with five retained files. Every API response carries `X-Request-ID` and safe error envelopes include it.

For a Binance outage or stale feed, inspect health/alerts and let public-feed reconnect logic recover; no exchange account action is available. For database or recovery error, do not restart into trading assumptions—inspect the database/backup and recovery alert first. Frontend restart does not affect backend execution. Backtest and optimization requests are rate limited and serialized to prevent overload.
