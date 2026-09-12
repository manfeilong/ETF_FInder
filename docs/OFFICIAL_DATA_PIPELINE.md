# Official Data Pipeline Playbook

This playbook moves the project from prototype data toward production-grade ETF data operations.

## 1) Official Holdings Source (No Partial Parser in Production)

Set adapter to an official source chain:

```powershell
$env:ETF_HOLDINGS_ADAPTER="official_pcf_twse"
$env:ETF_OFFICIAL_PCF_URL_TEMPLATE="https://your-pcf-endpoint/{code}?date={date}"
$env:ETF_OFFICIAL_TWSE_URL_TEMPLATE="https://your-twse-endpoint/{code}?date={date}"
```

For real multi-issuer production wiring, prefer the source registry:

```powershell
Copy-Item data/import/official-source-registry-template.json data/official-source-registry.json
# Edit data/official-source-registry.json and enable real official CSV/JSON/PCF rows.
$env:ETF_HOLDINGS_ADAPTER="official_registry"
$env:ETF_OFFICIAL_SOURCE_REGISTRY_FILE="data/official-source-registry.json"
python server.py --check-config
```

在啟用 registry 前先驗證 schema、來源可追溯欄位與所有已上市 ETF 的覆蓋率：

```powershell
python server.py --check-official-registry
```

每個來源必須明確提供 `enabled`、`status`、`publisher`、`authorityType`、`verifiedAt`、`format`，以及 `urlTemplate`、`url` 或 `urlsByCode` 其中一種網址設定，並提供至少一種代碼／發行商比對條件。驗證器不會把缺乏官方身分、HTTPS 網址或驗證日期的網址視為正式來源。

Registry rows can match exact `codes`, per-code `urlsByCode`, `codePrefixes`, `issuerContains`, or `nameContains`, and can fetch `json`, `csv`, or official `html` pages. HTML pages may expose labeled rows, native tables, responsive `div` tables, or name-only top-holdings tables; supported holding identifiers include Taiwan codes, exchange-suffixed symbols, and ISINs. Name-only rows are matched exactly against the local stock universe, while unresolved foreign or bond names remain explicit `NAME:` identifiers. HTML results remain `partial_official_page` unless a CSV/JSON/PCF export proves complete coverage.

Enable strict completeness gate for official snapshots:

```powershell
$env:ETF_LIVE_REQUIRE_FULL_HOLDINGS="1"
$env:ETF_LIVE_MIN_DECLARED_HOLDINGS="30"
$env:ETF_LIVE_MIN_PARSED_HOLDINGS="30"
```

Validate configuration:

```powershell
python server.py --check-config
```

Notes:
- When `ETF_LIVE_REQUIRE_FULL_HOLDINGS=1`, `--check-config` now fails if `ETF_HOLDINGS_ADAPTER` is still a non-official adapter (for example `etfinfo_public_page`).
- `etfinfo_public_page` now prefers the embedded Nuxt `__NUXT_DATA__` payload, which greatly improves parsed holding coverage, but production should still run on official adapters (`official_pcf_twse` / `official_endpoint` / `official_snapshot_file`).

## 2) Build 22-Day Real Snapshot History

Daily workflow (strict official quality + history gate + report):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/daily-refresh.ps1 `
  -Codes "0050,006208,00878,00881" `
  -StrictOfficialQuality `
  -HistoryQuality real_only `
  -MinSnapshots 2
```

Backfill from downloaded official snapshot files:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-history-snapshots.ps1 `
  -Directory "data/official-history" `
  -CheckHistoryQuality `
  -HistoryQuality real_only `
  -MinSnapshots 2
```

Read the latest gate report:

```text
GET /api/history/quality/latest
```

Production data readiness check:

```powershell
python server.py --check-production-data --production-min-snapshots 22
```

This checks the current adapter, official source registry coverage, metric completeness, and `real_only` snapshot count. It exits non-zero until the data layer is genuinely production-ready.

## 3) Expand ETF Universe (Official TWSE API)

Recommended first step (auto pulls official TWSE ETF list + categories):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-universe-twse-rwd.ps1
```

Equivalent CLI:

```powershell
python server.py --import-universe-twse-rwd --twse-lang zh
```

This pulls and merges:
- `/rwd/zh/ETF/list`
- `/rwd/zh/ETF/domestic`
- `/rwd/zh/ETF/foreign`
- `/rwd/zh/ETF/li`
- `/rwd/zh/ETF/activeList`
- `/rwd/zh/ETF/BFIncome`
- `/rwd/zh/ETF/liFutures`
- `/rwd/zh/ETF/vanillaFutures`

Fallback mode (manual CSV import) is still supported:

Import universe list (CSV) into `data/etf-universe.json`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-universe-csv.ps1 `
  -CsvPath "data/import/universe.csv"
```

The importer updates:
- ETF code/name/listed status
- classification fields:
  - `strategy`
  - `assetClass`
  - `region`
  - `distributionType`
  - `leverageType`

## 4) Promote Metrics (Official ETFortune + CSV fallback)

Recommended first step (official ETFortune bulk + chart endpoints):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-metrics-etffortune.ps1
```

Equivalent CLI:

```powershell
python server.py --import-metrics-etffortune
```

Optional subset:

```powershell
python server.py --import-metrics-etffortune --metrics-codes 0050,00878
```

CSV import remains available for metrics not exposed by ETFortune:

Import metrics into `data/etf-profiles.json`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-metrics-csv.ps1 `
  -CsvPath "data/import/metrics.csv" `
  -AsOf "2026-06-01" `
  -Source "official_metrics_csv"
```

Supported metrics:
- `expenseRatioPct`
- `aumTwdBn`
- `avgDailyVolumeM`
- `premiumDiscountPct`
- `dividendYieldPct`
- `return1mPct`
- `return3mPct`
- `returnYtdPct`
- `return1yPct`
- `volatility1yPct`
- `maxDrawdown1yPct`
- `trackingErrorPct`

Notes:
- `--import-metrics-etffortune` automatically fills metrics derivable from official ETFortune feeds, including:
  - `aumTwdBn`
  - `avgDailyVolumeM`
  - `premiumDiscountPct`
  - `return1mPct` / `return3mPct` / `returnYtdPct` / `return1yPct`
  - `volatility1yPct` / `maxDrawdown1yPct`
- Metrics not provided by ETFortune (for example `expenseRatioPct`, `trackingErrorPct`) should be filled via official CSV/API import.
- The importer follows the official CDN's same-origin challenge redirect while preserving request method and JSON headers. It reports request/success/error counts and exits non-zero if any requested series fails, so a partial bulk import cannot be mistaken for a successful run.

## 5) Production Hardening Controls

### Auth (optional, token mode)

```powershell
$env:ETF_API_AUTH_MODE="write_token"   # off | write_token | all_token
$env:ETF_API_TOKEN="replace-with-secret"
```

Pass token via:
- `Authorization: Bearer <token>`
- `X-ETF-Token: <token>`
- or query `?token=<token>` (for automation scripts)

### Rate limit (optional)

```powershell
$env:ETF_RATE_LIMIT_ENABLED="1"
$env:ETF_RATE_LIMIT_WINDOW_SECONDS="60"
$env:ETF_RATE_LIMIT_MAX_REQUESTS="120"
$env:ETF_RATE_LIMIT_KEY_MODE="ip"      # ip | ip_path
```

### Pipeline status endpoint

```text
GET /api/pipeline/status
```

This returns:
- live adapter/settings/latest quality
- history quality/retention/report summary
- universe category coverage
- metrics coverage summary
- auth and rate-limit settings

## 6) Go-Live Expectation

Before enabling Holding Change for end users:
1. `ETF_HOLDINGS_ADAPTER` is official (not public parser).
2. Strict full holdings gate passes for all listed target ETFs.
3. `history/quality/latest` shows `ok=true` and sufficient snapshots.
4. Metrics source is official CSV/API import (not seed-only).
5. Reverse proxy + TLS + external monitoring configured outside this app.
