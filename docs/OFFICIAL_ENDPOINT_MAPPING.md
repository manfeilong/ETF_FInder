# Official Endpoint Mapping Guide

Use `ETF_HOLDINGS_ADAPTER=official_endpoint` when your official source is exposed as JSON or CSV.

For direct production wiring with fallback between official sources, use:
```env
ETF_HOLDINGS_ADAPTER=official_pcf_twse
ETF_OFFICIAL_PCF_URL_TEMPLATE=https://pcf.example/{code}?date={date}
ETF_OFFICIAL_TWSE_URL_TEMPLATE=https://twse.example/{code}?date={date}
```
`official_pcf_twse` tries `PCF -> TWSE -> ETF_OFFICIAL_ENDPOINT_URL_TEMPLATE` in order.

## Required
- `ETF_OFFICIAL_ENDPOINT_URL_TEMPLATE`

The template supports:
- `{code}` for ETF code
- `{date}` for date string (`ETF_OFFICIAL_ENDPOINT_DATE`, or today's date)

Example:
```env
ETF_HOLDINGS_ADAPTER=official_endpoint
ETF_OFFICIAL_ENDPOINT_URL_TEMPLATE=https://example.com/etf/{code}/holdings?date={date}
ETF_OFFICIAL_ENDPOINT_FORMAT=json
```

## JSON Mapping Example
Source payload:
```json
{
  "meta": { "asOf": "2026-05-25", "declared": 50 },
  "data": {
    "rows": [
      { "stockCode": "2330", "stockName": "TSMC", "weightPct": "9.2", "shares": "1000", "price": "1000" }
    ]
  }
}
```

Env mapping:
```env
ETF_OFFICIAL_ENDPOINT_FORMAT=json
ETF_OFFICIAL_ENDPOINT_HOLDINGS_PATH=data.rows
ETF_OFFICIAL_ENDPOINT_ASOF_PATH=meta.asOf
ETF_OFFICIAL_ENDPOINT_DECLARED_COUNT_PATH=meta.declared
ETF_OFFICIAL_ENDPOINT_CODE_FIELD=stockCode
ETF_OFFICIAL_ENDPOINT_WEIGHT_FIELD=weightPct
ETF_OFFICIAL_ENDPOINT_NAME_FIELD=stockName
ETF_OFFICIAL_ENDPOINT_SHARES_FIELD=shares
ETF_OFFICIAL_ENDPOINT_PRICE_FIELD=price
```

## CSV Mapping Example
Source CSV:
```csv
asOf,stockCode,stockName,weightPct,shares,price
2026-05-25,2330,TSMC,9.2%,1000,1000
```

Env mapping:
```env
ETF_OFFICIAL_ENDPOINT_FORMAT=csv
ETF_OFFICIAL_ENDPOINT_CODE_FIELD=stockCode
ETF_OFFICIAL_ENDPOINT_WEIGHT_FIELD=weightPct
ETF_OFFICIAL_ENDPOINT_NAME_FIELD=stockName
ETF_OFFICIAL_ENDPOINT_SHARES_FIELD=shares
ETF_OFFICIAL_ENDPOINT_PRICE_FIELD=price
ETF_OFFICIAL_ENDPOINT_ASOF_PATH=asOf
```

## Optional Headers
Use JSON object string:
```env
ETF_OFFICIAL_ENDPOINT_HEADERS={"Authorization":"Bearer YOUR_TOKEN","Accept":"application/json"}
```

Profile-specific headers:
```env
ETF_OFFICIAL_PCF_HEADERS={"Authorization":"Bearer PCF_TOKEN"}
ETF_OFFICIAL_TWSE_HEADERS={"X-API-Key":"TWSE_KEY"}
```
