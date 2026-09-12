# ETF True Exposure Lab

支援最多 10 檔 ETF 同步交叉比對的正式 MVP，涵蓋主動式與被動式 ETF 的資金配比、真實底層曝險、持股交集熱力圖、產業 X-Ray，以及依目標產業自動產生 ETF 資金配比。

目前版本會清楚標示資料品質限制：前端種子資料、公開頁部分解析資料、未分類股票與歷史快照不足都不會被包裝成完整官方資料。

## 開啟方式

正式 MVP 請用內建本機 API server 啟動，不建議直接用瀏覽器開啟 `index.html`：

```powershell
python server.py --host 127.0.0.1 --port 4173
```

接著開啟 `http://127.0.0.1:4173/index.html`。按下「刷新資料」時，前端會呼叫 `GET /api/etfs/latest?codes=...`，把目前已選 ETF 清單送到後端抓取資料並重新計算圖表。

健康檢查：

```powershell
Invoke-WebRequest http://127.0.0.1:4173/api/health -UseBasicParsing
```

## ETF 清單

目前 universe 由 `data/etf-universe.json` 提供，畫面與 API 以該檔案為準，不再假設硬編碼清單一定仍然有效。2026-09-12 重新匯入 TWSE 官方清單後共有 240 檔；現有主動式 ETF 重點清單包含：00400A、00401A、00403A、00405A、00407A、00980A、00981A、00982A、00983A、00984A、00990A、00991A、00992A、00999A、009816。先前清單中的 00998A 目前不在官方 universe，因此不會被預設刷新或品質檢查誤判成程式錯誤。

畫面中的「10 檔」是同步交叉比對上限，不是 ETF universe 上限。Selector Hub 會顯示指定 16 檔是否全部納入，搜尋清單也會依「已上市 ETF」與「未上市 / 募集中 ETF」分組；已上市顯示上市日，未上市顯示預計上市或募集時間。只有已有可用持股資料且非模擬投組的 ETF 可納入比對。

## 已實作模組

- Selector Hub：啟動時優先透過 `GET /api/etfs/search?q=` 載入 ETF universe，並支援 ETF 模糊搜尋、最多 10 檔同步比對限制、上市狀態、主動/被動標籤、資金配比輸入。
- Holdings Snapshot：前端選取 ETF 後會優先透過 `GET /api/etfs/{code}/holdings` 拉最新可用持股快照，逐步替換前端 seed 持股。
- 自動產生資金配比：使用者輸入 3 個期望板塊與比例，前端依 ETF 底層產業曝險自動挑選 ETF 並設定資金比例。
- Portfolio Manager：可儲存、載入、刪除自訂 ETF 組合（本機 API 持久化）。
- True Exposure Matrix：優先呼叫 `POST /api/exposure/compare` 計算底層股票真實曝險（失敗時 fallback 到前端模型），並標示單股超過 20% 的集中警示。
- CSV 匯出：可從曝險面板匯出底層持股曝險明細 CSV。
- PDF 匯出：可從曝險面板開啟可列印報告視窗，輸出 PDF。
- Watchlist：可加入追蹤 ETF、附註記，並刷新每檔資料就緒狀態（ready / partial / seed / missing）。
- Overlap Heatmap：以 ETF 為 X 軸、股票為 Y 軸，支援「至少出現在 X 檔 ETF」的交集門檻。
- Sector X-Ray：依產業別加總底層持股，支援矩形圖與圓環圖切換；點擊產業後列出該產業股票與來源 ETF。
- Holding Change：已改為讀取 `GET /api/etfs/{code}/holdings/changes?days=22` 的 daily snapshot 差異；若快照天數不足會明確提示。
- Data Quality：顯示目前來源、持股解析完整度、未分類股票，與 Holdings / Compare / Optimize / History API 接線狀態。

## 每日更新方式

目前已提供可運作的本機資料 API：`server.py` 會在使用者點擊「刷新資料」時即時抓取公開 ETF 持股頁，回傳標準化 JSON，前端收到後會套用持股並重算所有分析。這不是單純測試按鈕；按鈕會真的發出 API request。

目前 `server.py` 內建的是公開頁抓取器，payload 會包含 `declaredHoldingCount`、`parsedHoldingCount` 與 `coverage`，用來標示來源頁宣告的持股總數與目前解析到的筆數。若 `coverage` 是 `partial_public_page`，代表公開頁有分頁或互動資料尚未完全展開；正式投產時應改接官方 PCF / 投信投資組合明細 adapter。

目前刷新只走一條 MVP 流程：`/api/etfs/latest?codes=...` 由 `server.py` 即時抓資料；抓取成功後會覆寫 `data/latest-etf-holdings.json`，再把同一份 payload 回傳給前端重算圖表。若沒有用 `server.py` 啟動網站，刷新會明確顯示 API 呼叫失敗。

狀態燈不會宣稱「自動日更」。只有成功打到 `/api/etfs/latest` 時才顯示 API 狀態；若公開頁只能解析部分持股，畫面會顯示「資料部分可用」。

`server.py` 只提供白名單靜態檔與 API，不再把整個資料夾當成靜態網站公開。若需要跨網域部署，可用環境變數設定允許來源：

```powershell
$env:ETF_ALLOWED_ORIGINS="https://your-domain.example"
python server.py --host 127.0.0.1 --port 4173
```

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

## 已接線 API

- `GET /api/etfs/search?q=`：ETF 搜尋、上市狀態與分類資料。
- `POST /api/exposure/compare`：輸入 ETF code 與資金配比，回傳股票曝險、ETF 權重矩陣與產業加總。
- `POST /api/allocation/optimize`：輸入目標產業與比例，回傳建議 ETF 與資金配比（前端 auto-allocation 已優先接線此 API）。
- `GET /api/etfs/{code}/holdings?date=`：查詢單檔 ETF 每日持股。
- `GET /api/etfs/{code}/holdings/changes?days=22`：查詢近月持股增減、新增/移除、金額與張數變化。
- `GET /api/portfolios`：列出已儲存組合摘要。
- `POST /api/portfolios`：建立或更新組合（可帶 `id`）。
- `GET /api/portfolios/{id}`：取得單一組合內容。
- `DELETE /api/portfolios/{id}`：刪除組合。
- `GET /api/watchlist`：取得追蹤清單與每檔狀態。
- `POST /api/watchlist`：新增或更新追蹤 ETF（含註記）。
- `DELETE /api/watchlist/{code}`：移除追蹤 ETF。
- `GET /api/updates/status?codes=...`：查詢各 ETF 最新快照就緒狀態與歷史快照數。
