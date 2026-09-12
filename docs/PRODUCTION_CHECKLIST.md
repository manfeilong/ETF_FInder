# ETF Finder Production Checklist

## 1) Data Reliability
- [x] `official_snapshot_file` adapter available for local official snapshots.
- [x] `official_endpoint` adapter available for direct JSON/CSV endpoint mapping.
- [x] Replace `official_pcf_stub` with direct official PCF/TWSE fetch adapter.
- [x] `official_registry` adapter available for per-code/per-issuer official JSON/CSV/HTML sources.
- [x] Registry schema and traceability validation CLI (`python server.py --check-official-registry`).
- [ ] Populate `data/official-source-registry.json` with real official PCF / TWSE / issuer URLs for every production ETF code.
- [x] Keep `coverage`, `declaredHoldingCount`, and `parsedHoldingCount` in every snapshot.
- [x] Validate parser output with unit tests for known ETF snapshots.
- [x] Add strict official quality gates (`ETF_LIVE_REQUIRE_FULL_HOLDINGS`, min declared/parsed thresholds).
- [x] Add official snapshot directory bulk import pipeline for history backfill.
- [ ] Confirm `GET /api/etfs/{code}/holdings/changes` is driven by real daily snapshots for all production codes.
- [x] `GET /api/etfs/{code}/holdings/changes` supports `quality=real_only` gating.

## 2) Backend API Readiness
- [x] `GET /api/etfs/search`
- [x] `GET /api/etfs/universe`
- [x] `GET /api/etfs/{code}/metrics`
- [x] Universe response includes product classification fields (strategy/assetClass/region/distribution/leverage).
- [x] `GET /api/etfs/{code}/holdings?date=`
- [x] `POST /api/exposure/compare`
- [x] `GET /api/etfs/{code}/holdings/changes?days=22`
- [x] `GET/POST/DELETE /api/watchlist`
- [x] `GET /api/updates/status`
- [x] `GET /api/alerts`
- [x] `GET /api/access-logs`
- [x] `GET /api/live-fetch/config`
- [x] `GET /api/live-fetch/probe`
- [x] `GET /api/history/quality`
- [x] `GET /api/history/quality/latest`
- [x] `GET /api/pipeline/status`
- [x] Listed-only universe includes official listed rows whose source does not provide a separate listing date.

## 3) Operations and Monitoring
- [x] Live refresh retry policy via env:
  - `ETF_FETCH_TIMEOUT_SECONDS`
  - `ETF_FETCH_RETRIES`
  - `ETF_FETCH_BACKOFF_MS`
- [x] One-shot refresh mode for scheduler/cron:
  - `python server.py --refresh-once --codes ...`
- [x] Daily workflow script for scheduler:
  - `scripts/daily-refresh.ps1`
- [x] Windows task registration scripts:
  - `scripts/register-daily-task.ps1`
  - `scripts/unregister-daily-task.ps1`
- [x] Scheduler health check script:
  - `scripts/check-daily-task.ps1`
- [x] Manual task run-and-wait script:
  - `scripts/run-daily-task-now.ps1`
- [x] Universe import script:
  - `scripts/import-universe-twse-rwd.ps1`
  - `scripts/import-universe-csv.ps1`
- [x] Metrics import script:
  - `scripts/import-metrics-etffortune.ps1`
  - `scripts/import-metrics-csv.ps1`
- [x] History snapshot import/backfill script:
  - `scripts/import-history-snapshots.ps1`
- [x] History retention policy and prune command:
  - `ETF_HISTORY_RETENTION_DAYS`
  - `ETF_HISTORY_MAX_SNAPSHOTS_PER_CODE`
  - `ETF_HISTORY_DROP_SEED_WHEN_REAL`
  - `python server.py --prune-history`
- [x] History quality gate CLI:
  - `python server.py --check-history-quality --history-quality real_only`
- [x] Refresh alerts persisted at `data/refresh-alerts.jsonl`.
- [x] Optional alert webhook:
  - `ETF_ALERT_WEBHOOK_URL`
- [x] Health endpoint exposes live fetch config and latest data summary.
- [x] Config diagnostics endpoint exposes adapter readiness (`/api/live-fetch/config`).
- [x] Probe endpoint validates live adapter fetch without writing data (`/api/live-fetch/probe`).
- [ ] Add external uptime checks and alert routing (Slack/Email/PagerDuty).

## 4) Security and Deployment
- [x] CORS allowlist support via `ETF_ALLOWED_ORIGINS`.
- [x] Basic response security headers (CSP, no-store, nosniff, referrer policy).
- [x] Optional API token modes (`off`, `write_token`, `all_token`).
- [x] Optional in-process rate limit guard.
- [ ] Put service behind reverse proxy (TLS termination, rate limiting, request logging).
- [ ] Run as managed service (systemd/Windows service/container orchestrator).
- [x] Add structured access/error logs with retention policy.
  - Access log JSONL rotation:
    - `ETF_ACCESS_LOG_ENABLED`
    - `ETF_ACCESS_LOG_FILE`
    - `ETF_ACCESS_LOG_MAX_BYTES`
    - `ETF_ACCESS_LOG_BACKUP_COUNT`
  - Refresh/error events:
    - `data/refresh-alerts.jsonl`

## 5) Product Completion
- [x] Portfolio save/load/delete
- [x] Watchlist + data status
- [x] Per-user ownership scope for portfolio/watchlist via `user` query or `X-ETF-User` header
- [x] CSV export
- [x] PDF print export
- [ ] Full authentication (login/session/token) and user lifecycle management
- [ ] Watchlist notifications (email/push/webhook)
- [ ] Full mobile QA across key pages and interactions

## 6) Launch Gate
Go-live is recommended only when all unchecked items in sections 1, 3, and 4 are complete.
