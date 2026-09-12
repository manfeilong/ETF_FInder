# Import Templates

Use these templates to import official data into the local pipeline.

## Official auto-import (recommended)

TWSE universe/category import:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-universe-twse-rwd.ps1
```

ETFortune metrics import:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-metrics-etffortune.ps1
```

## Universe import

Template file:
- `universe-template.csv`

Import command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-universe-csv.ps1 -CsvPath "data/import/universe-template.csv"
```

## Metrics import

Template file:
- `metrics-template.csv`

Import command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-metrics-csv.ps1 `
  -CsvPath "data/import/metrics-template.csv" `
  -AsOf "2026-06-01" `
  -Source "official_metrics_csv"
```

## Historical snapshot import

Place JSON snapshots under:
- `data/official-history/<YYYY-MM-DD>/<ETF_CODE>.json`

Then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-history-snapshots.ps1 `
  -Directory "data/official-history" `
  -CheckHistoryQuality `
  -HistoryQuality real_only `
  -MinSnapshots 2
```
