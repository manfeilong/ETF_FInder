# ETF True Exposure Lab

支援最多 10 檔 ETF 同步交叉比對的前端原型，涵蓋主動式與被動式 ETF 的資金配比、真實底層曝險、持股交集熱力圖、產業 X-Ray、近月每日持股變化，以及依目標產業自動產生 ETF 資金配比。

## 開啟方式

若只想看靜態畫面，可以直接用瀏覽器開啟 `index.html`。若要讓「刷新資料」真的去抓最新資料，請用內建本機 API server 啟動：

```powershell
python server.py --host 127.0.0.1 --port 4173
```

接著開啟 `http://127.0.0.1:4173/index.html`。按下「刷新資料」時，前端會優先呼叫 `GET /api/etfs/latest?codes=...`，把目前已選或指定 ETF 清單送到後端抓取資料並重新計算圖表。

## ETF 清單

已加入：00400A、00401A、00403A、00405A、00407A、00980A、00981A、00982A、00983A、00984A、00990A、00991A、00992A、00998A、00999A、009816。

畫面中的「10 檔」是同步交叉比對上限，不是 ETF universe 上限。Selector Hub 會顯示指定 16 檔是否全部納入，搜尋清單也會依「已上市 ETF」與「未上市 / 募集中 ETF」分組；已上市顯示上市日，未上市顯示預計上市或募集時間。ETF chip 可點擊鎖定，再點一次即可取消鎖定。

## 已實作模組

- Selector Hub：ETF 模糊搜尋、最多 10 檔同步比對限制、上市狀態、主動/被動標籤、資金配比輸入。
- 自動產生資金配比：使用者輸入 3 個期望板塊與比例，前端依 ETF 底層產業曝險自動挑選 ETF 並設定資金比例。
- True Exposure Matrix：依資金配比換算底層股票真實曝險，並標示單股超過 20% 的集中警示。
- Overlap Heatmap：以 ETF 為 X 軸、股票為 Y 軸，支援「至少出現在 X 檔 ETF」的交集門檻。
- Sector X-Ray：依產業別加總底層持股，支援矩形圖與圓環圖切換；點擊產業後列出該產業股票與來源 ETF。
- Daily Holding Change：針對已上市且已選取的 ETF，顯示近 22 個交易日的每日增持前三名、減持前三名、新增/移除、調整幅度，並包含估算金額與張數變化。

## 每日更新方式

目前已提供可運作的本機資料 API：`server.py` 會在使用者點擊「刷新資料」時即時抓取公開 ETF 持股頁，回傳標準化 JSON，前端收到後會套用持股並重算所有分析。這不是單純測試按鈕；按鈕會真的發出 API request。

目前 `server.py` 內建的是公開頁抓取器，payload 會包含 `declaredHoldingCount`、`parsedHoldingCount` 與 `coverage`，用來標示來源頁宣告的持股總數與目前解析到的筆數。若 `coverage` 是 `partial_public_page`，代表公開頁有分頁或互動資料尚未完全展開；正式投產時應改接官方 PCF / 投信投資組合明細 adapter。

目前刷新只走一條正式流程：`/api/etfs/latest?codes=...` 由 `server.py` 即時抓資料；抓取成功後會覆寫 `data/latest-etf-holdings.json`，再把同一份 payload 回傳給前端重算圖表。若沒有用 `server.py` 啟動網站，刷新會明確顯示 API 呼叫失敗，不會再退回示範資料。

狀態燈不會宣稱「自動日更」。只有成功打到 `/api/etfs/latest` 時才顯示「已接資料 API」；API 不可用時會顯示失敗狀態。

若要把資料源升級成嚴格意義的官方資料，需要把 `server.py` 內的抓取器替換或擴充成各投信 / TWSE / 櫃買中心 adapter。原因是台灣 ETF 持股並沒有一個涵蓋所有發行商、所有主被動 ETF 的單一官方 JSON API；正式版通常會做一層 source adapter，把不同格式統一成目前前端使用的 payload。

正式版建議採自動排程，不需要人工重製資料；本機版則可用按鈕手動刷新。

建議流程：

- 每個交易日 18:30 Asia/Taipei 由排程工作自動執行。
- 主動式 ETF 從各投信 PCF 或官方持股檔抓取每日持股。
- 被動式 ETF 從 TWSE、櫃買中心、投信公開檔抓取成分與權重。
- 抓取後寫入 PostgreSQL 的 `holdings_daily` 與 `holdings_changes_daily`。
- Redis 更新 `etf:holdings:{date}:{code}`、`etf:changes:{date}:{code}` 快取。
- 前端不需要重新部署；使用者可點擊「刷新資料」、重新整理頁面，或由前端以輪詢 / stale-while-revalidate 方式重新抓 API，即可看到最新資料。
- 若當天非交易日，前端顯示最近一個交易日資料，不會產生空白日。

## 後續 API 接線

- `GET /api/etfs/search?q=`：ETF 搜尋、上市狀態與分類資料。
- `POST /api/exposure/compare`：輸入 ETF code 與資金配比，回傳股票曝險、ETF 權重矩陣與產業加總。
- `POST /api/allocation/optimize`：輸入三個產業板塊與目標比例，回傳建議 ETF 與資金配比。
- `GET /api/etfs/{code}/holdings?date=`：查詢單檔 ETF 每日持股。
- `GET /api/etfs/{code}/holdings/changes?days=22`：查詢近月持股增減、新增/移除、金額與張數變化。
