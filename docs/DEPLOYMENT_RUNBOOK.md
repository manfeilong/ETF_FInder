# Deployment Runbook (Local -> Production)

## Local Start
```powershell
python server.py --host 127.0.0.1 --port 4173
```

Open:
- `http://127.0.0.1:4173/index.html`
- `http://127.0.0.1:4173/api/health`

## Environment Variables
Copy `.env.example` and set values in your runtime environment:
- `ETF_ALLOWED_ORIGINS`
- `ETF_HOLDINGS_ADAPTER`
- `ETF_FETCH_TIMEOUT_SECONDS`
- `ETF_FETCH_RETRIES`
- `ETF_FETCH_BACKOFF_MS`
- `ETF_LIVE_REQUIRE_FULL_HOLDINGS`
- `ETF_LIVE_MIN_DECLARED_HOLDINGS`
- `ETF_LIVE_MIN_PARSED_HOLDINGS`
- `ETF_OFFICIAL_SNAPSHOT_DIR`
- `ETF_OFFICIAL_ENDPOINT_URL_TEMPLATE`
- `ETF_OFFICIAL_ENDPOINT_FORMAT`
- `ETF_OFFICIAL_ENDPOINT_HOLDINGS_PATH`
- `ETF_OFFICIAL_ENDPOINT_ASOF_PATH`
- `ETF_OFFICIAL_ENDPOINT_DECLARED_COUNT_PATH`
- `ETF_OFFICIAL_ENDPOINT_CODE_FIELD`
- `ETF_OFFICIAL_ENDPOINT_WEIGHT_FIELD`
- `ETF_OFFICIAL_ENDPOINT_NAME_FIELD`
- `ETF_OFFICIAL_ENDPOINT_SHARES_FIELD`
- `ETF_OFFICIAL_ENDPOINT_PRICE_FIELD`
- `ETF_OFFICIAL_ENDPOINT_DATE`
- `ETF_OFFICIAL_ENDPOINT_HEADERS`
- `ETF_OFFICIAL_PCF_URL_TEMPLATE`
- `ETF_OFFICIAL_PCF_FORMAT`
- `ETF_OFFICIAL_PCF_HEADERS`
- `ETF_OFFICIAL_TWSE_URL_TEMPLATE`
- `ETF_OFFICIAL_TWSE_FORMAT`
- `ETF_OFFICIAL_TWSE_HEADERS`
- `ETF_OFFICIAL_SOURCE_REGISTRY_FILE`
- `ETF_HISTORY_RETENTION_DAYS`
- `ETF_HISTORY_MAX_SNAPSHOTS_PER_CODE`
- `ETF_HISTORY_DROP_SEED_WHEN_REAL`
- `ETF_HISTORY_QUALITY_REPORT_FILE`
- `ETF_DEFAULT_USER_ID`
- `ETF_REQUIRE_USER_CONTEXT`
- `ETF_API_AUTH_MODE`
- `ETF_API_TOKEN`
- `ETF_RATE_LIMIT_ENABLED`
- `ETF_RATE_LIMIT_WINDOW_SECONDS`
- `ETF_RATE_LIMIT_MAX_REQUESTS`
- `ETF_RATE_LIMIT_KEY_MODE`
- `ETF_ACCESS_LOG_ENABLED`
- `ETF_ACCESS_LOG_FILE`
- `ETF_ACCESS_LOG_MAX_BYTES`
- `ETF_ACCESS_LOG_BACKUP_COUNT`
- `ETF_ALERT_WEBHOOK_URL`
- `ETF_ALERT_WEBHOOK_TIMEOUT_SECONDS`

## Scheduled Refresh (Recommended)
Use one-shot mode for cron/task scheduler:
```powershell
python server.py --refresh-once --codes "00400A,00403A,00405A"
```

If `--codes` is omitted, all listed ETF codes from `data/etf-universe.json` are used.
Use quotes for `--codes` in PowerShell to avoid numeric coercion on suffix codes (for example `00631L`).

Refresh all ETF codes from universe in one command (avoids manual code typing / leading-zero issues):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/refresh-universe-once.ps1
```

Listed-only version:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/refresh-universe-once.ps1 -ListedOnly
```

Or run the bundled daily workflow script (check + refresh + prune + gate):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/daily-refresh.ps1 -Codes "00400A,00403A" -HistoryQuality real_only -MinSnapshots 2
```

預設情況下，資料抓取、設定或程式錯誤會讓排程回傳失敗；歷史快照尚未累積到門檻則會留下品質警告，但排程本身仍回傳成功。若部署閘門需要把資料未就緒也視為失敗，加入 `-FailOnHistoryQuality`。只驗證工作流設定、不抓資料時可使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/daily-refresh.ps1 -ValidateOnly
```

Strict official quality mode (recommended for production):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/daily-refresh.ps1 `
  -Codes "0050,006208,00878,00881" `
  -StrictOfficialQuality `
  -MinDeclaredHoldings 30 `
  -MinParsedHoldings 30 `
  -HistoryQuality real_only `
  -MinSnapshots 2
```
If strict mode is enabled while adapter is still `etfinfo_public_page`, `python server.py --check-config` returns a non-zero exit code by design. Switch to an official adapter first.

Multi-issuer official source registry:
```powershell
Copy-Item data/import/official-source-registry-template.json data/official-source-registry.json
# Edit data/official-source-registry.json and enable real official CSV/JSON/PCF rows.
$env:ETF_HOLDINGS_ADAPTER="official_registry"
$env:ETF_OFFICIAL_SOURCE_REGISTRY_FILE="data/official-source-registry.json"
python server.py --check-config
python server.py --refresh-once --codes "0050"
```

Use CSV/JSON/PCF export URLs when available. Official HTML pages are supported, but they are treated as partial unless the page exposes complete row coverage.

Import official universe from TWSE endpoints (recommended):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-universe-twse-rwd.ps1
```

Import official universe CSV (fallback/manual):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-universe-csv.ps1 -CsvPath "data/import/universe.csv"
```

Import official metrics from ETFortune endpoints (recommended):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-metrics-etffortune.ps1
```

Import official metrics CSV (fallback/manual):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-metrics-csv.ps1 -CsvPath "data/import/metrics.csv" -AsOf "2026-06-01"
```

Import historical snapshot directory:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-history-snapshots.ps1 -Directory "data/official-history" -CheckHistoryQuality
```

Run the production data readiness gate:
```powershell
python server.py --check-production-data --production-min-snapshots 22
```

Register a Windows daily scheduled task (current user, interactive logon):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/register-daily-task.ps1 -TaskName ETF-Finder-DailyRefresh -At 18:30 -HistoryQuality real_only -MinSnapshots 2
```

Remove scheduled task:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/unregister-daily-task.ps1 -TaskName ETF-Finder-DailyRefresh
```

Check scheduled task + recent alerts + API health:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-daily-task.ps1 -TaskName ETF-Finder-DailyRefresh
```

健康檢查分開回報 `operationalHealthy` 與 `dataReady`。`status=data_not_ready` 代表排程正常、但正式資料門檻尚未通過；只有 `status=operational_failure` 代表排程或執行本身需要處理。
Exit code is `0` when healthy and `1` when unhealthy.
Note: right after registration, `hasRun=false` is expected until the first scheduled execution.

JSON output mode:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-daily-task.ps1 -TaskName ETF-Finder-DailyRefresh -AsJson
```

Allow report-only mode (never fail on unhealthy):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-daily-task.ps1 -TaskName ETF-Finder-DailyRefresh -AsJson -NoFailOnUnhealthy
```

Run the scheduled task immediately and wait for result:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-daily-task-now.ps1 -TaskName ETF-Finder-DailyRefresh -WaitSeconds 240
```
Exit code:
- `0`: completed and success
- `1`: completed but task result is non-zero
- `2`: did not finish within wait window
Note: Windows may still report `state=Queued` briefly; if a new `lastRunTime` is detected and `lastTaskResult=0`, this is treated as success.

Preflight config check:
```powershell
python server.py --check-config
```
Exit code is `0` when adapter configuration is ready, `1` when blocking issues exist.

History quality gate (recommended before enabling change analysis in production):
```powershell
python server.py --check-history-quality --codes 00400A,00403A --history-days 22 --history-quality real_only --min-snapshots 2
```
Exit code is `0` when all requested codes meet the threshold; `1` when any code fails the gate.

Apply history retention policy immediately (optional maintenance step):
```powershell
python server.py --prune-history
```
This applies `ETF_HISTORY_RETENTION_DAYS`, `ETF_HISTORY_MAX_SNAPSHOTS_PER_CODE`, and `ETF_HISTORY_DROP_SEED_WHEN_REAL`.

Official endpoint field mapping examples:
- `docs/OFFICIAL_ENDPOINT_MAPPING.md`

## Health and Monitoring
Use these endpoints for checks:
- `GET /api/health`
- `GET /api/pipeline/status`
- `GET /api/etfs/universe?listedOnly=1`
- `GET /api/etfs/0050/metrics`
- `GET /api/live-fetch/config`
- `GET /api/live-fetch/config?adapter=official_pcf_twse`
- `GET /api/live-fetch/probe?code=00400A`
- `GET /api/live-fetch/probe?code=00400A&adapter=official_snapshot_file`
- `GET /api/live-fetch/probe?code=00400A&adapter=official_pcf_twse`
- `GET /api/history/quality?quality=real_only&minSnapshots=2`
- `GET /api/history/quality/latest`
- `GET /api/updates/status`
- `GET /api/alerts?limit=50`
- `GET /api/access-logs?limit=100`

Reference data file for product metrics/classification:
- `data/etf-profiles.json`

Pipeline playbook:
- `docs/OFFICIAL_DATA_PIPELINE.md`

For per-user endpoints, pass user context:
- Query string: `?user=alice_01`
- Header: `X-ETF-User: alice_01`

Affected APIs:
- `/api/portfolios`
- `/api/watchlist`
- `/api/updates/status`
- `/api/history/quality`

For daily holding change quality gate:
- `GET /api/etfs/00400A/holdings/changes?days=22&quality=real_only`

Alert events are persisted in:
- `data/refresh-alerts.jsonl`

Access logs are persisted in JSONL with rotation:
- `ETF_ACCESS_LOG_FILE`
- Rotated files: `<file>.1`, `<file>.2`, ...

## Reverse Proxy (Recommended)
Put API behind Nginx/Caddy/IIS and enforce:
- HTTPS/TLS
- Request size limits
- Rate limiting
- Access logs

## Pre-Release Verification
1. Run static checks:
   - `python -m py_compile server.py`
   - `node --check app.js`
2. Run tests:
   - `python -m unittest -v tests.test_server`
3. Validate API contract:
   - `/api/etfs/universe?listedOnly=1`
   - `/api/etfs/search`
   - `/api/etfs/{code}/metrics`
   - `/api/etfs/{code}/holdings`
   - `/api/exposure/compare`
   - `/api/etfs/{code}/holdings/changes`
   - `/api/etfs/{code}/holdings/changes?quality=real_only`
   - `/api/history/quality?quality=real_only&minSnapshots=2`
   - `/api/live-fetch/config`
   - `/api/live-fetch/probe?code=00400A`
   - `/api/access-logs?limit=100`
4. Run optional history retention maintenance:
   - `python server.py --prune-history`
5. Verify mobile viewport behavior (390px and 768px).
