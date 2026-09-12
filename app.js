const REQUESTED_ETF_CODES = [
  "00400A",
  "00401A",
  "00403A",
  "00405A",
  "00407A",
  "00980A",
  "00981A",
  "00982A",
  "00983A",
  "00984A",
  "00990A",
  "00991A",
  "00992A",
  "00998A",
  "00999A",
  "009816",
];
const COMPARE_LIMIT = 10;
const DAILY_UPDATE_POLICY = {
  frequency: "每日",
  timezone: "Asia/Taipei",
  scheduledAt: "18:30",
  sources: "投信 PCF / TWSE 公開資料",
};
const HISTORY_CHANGE_DAYS = 22;
const HISTORY_QUALITY_MODE = "real_only";
const AUTO_SYNC_INTERVAL_MS = 3 * 60 * 1000;
const AUTO_SYNC_STORAGE_KEY = "etf.true_exposure.auto_sync";
let DATA_END_DATE = getLatestTradingDate();
let dataRefreshState = "manual";
let dataRefreshMessage = "目前顯示前端種子資料或本機快取；按刷新資料可向本機 API 抓取公開頁資料。";
let selectorNoticeMessage = dataRefreshMessage;
let lastRefreshAt = "";
let latestPayloadQuality = null;
let lastOptimizeSource = "none";
let lastOptimizeError = "";
const historyApiState = {
  cache: new Map(),
  pending: new Set(),
};
const holdingApiState = {
  loaded: new Set(),
  pending: new Set(),
  errors: new Map(),
};
const universeApiState = {
  loaded: false,
  loading: false,
  error: "",
};
const compareApiState = {
  cache: new Map(),
  pending: new Set(),
  errors: new Map(),
};
const portfolioApiState = {
  rows: [],
  loading: false,
  selectedId: "",
  error: "",
};
const watchlistApiState = {
  rows: [],
  statuses: new Map(),
  loading: false,
  error: "",
  alertSummary: "",
  manualNotice: "",
  lastStatusHash: "",
};
const autoSyncState = {
  enabled: false,
  intervalMs: AUTO_SYNC_INTERVAL_MS,
  timerId: null,
  busy: false,
  lastRunAt: "",
};

const STOCKS = {
  "1101": { name: "台泥", sector: "水泥工業" },
  "1216": { name: "統一", sector: "食品工業" },
  "1301": { name: "台塑", sector: "塑膠工業" },
  "1303": { name: "南亞", sector: "塑膠工業" },
  "1476": { name: "儒鴻", sector: "紡織纖維" },
  "1590": { name: "亞德客-KY", sector: "電機機械" },
  "2049": { name: "上銀", sector: "電機機械" },
  "2059": { name: "川湖", sector: "電機機械" },
  "2207": { name: "和泰車", sector: "汽車工業" },
  "2301": { name: "光寶科", sector: "電子零組件業" },
  "2303": { name: "聯電", sector: "半導體業" },
  "2308": { name: "台達電", sector: "電子零組件業" },
  "2313": { name: "華通", sector: "電子零組件業" },
  "2317": { name: "鴻海", sector: "其他電子業" },
  "2324": { name: "仁寶", sector: "電腦及週邊設備業" },
  "2327": { name: "國巨", sector: "電子零組件業" },
  "2330": { name: "台積電", sector: "半導體業" },
  "2344": { name: "華邦電", sector: "半導體業" },
  "2345": { name: "智邦", sector: "通信網路業" },
  "2356": { name: "英業達", sector: "電腦及週邊設備業" },
  "2357": { name: "華碩", sector: "電腦及週邊設備業" },
  "2376": { name: "技嘉", sector: "電腦及週邊設備業" },
  "2379": { name: "瑞昱", sector: "半導體業" },
  "2382": { name: "廣達", sector: "電腦及週邊設備業" },
  "2383": { name: "台光電", sector: "電子零組件業" },
  "2395": { name: "研華", sector: "電腦及週邊設備業" },
  "2408": { name: "南亞科", sector: "半導體業" },
  "2412": { name: "中華電", sector: "通信網路業" },
  "2449": { name: "京元電子", sector: "半導體業" },
  "2454": { name: "聯發科", sector: "半導體業" },
  "2603": { name: "長榮", sector: "航運業" },
  "2609": { name: "陽明", sector: "航運業" },
  "2615": { name: "萬海", sector: "航運業" },
  "2880": { name: "華南金", sector: "金融保險業" },
  "2881": { name: "富邦金", sector: "金融保險業" },
  "2882": { name: "國泰金", sector: "金融保險業" },
  "2884": { name: "玉山金", sector: "金融保險業" },
  "2886": { name: "兆豐金", sector: "金融保險業" },
  "2887": { name: "台新金", sector: "金融保險業" },
  "2891": { name: "中信金", sector: "金融保險業" },
  "2892": { name: "第一金", sector: "金融保險業" },
  "3008": { name: "大立光", sector: "光電業" },
  "3017": { name: "奇鋐", sector: "電腦及週邊設備業" },
  "3034": { name: "聯詠", sector: "半導體業" },
  "3045": { name: "台灣大", sector: "通信網路業" },
  "3231": { name: "緯創", sector: "電腦及週邊設備業" },
  "3260": { name: "威剛", sector: "半導體業" },
  "3324": { name: "雙鴻", sector: "電子零組件業" },
  "3443": { name: "創意", sector: "半導體業" },
  "3661": { name: "世芯-KY", sector: "半導體業" },
  "3702": { name: "大聯大", sector: "電子通路業" },
  "3711": { name: "日月光投控", sector: "半導體業" },
  "4938": { name: "和碩", sector: "電腦及週邊設備業" },
  "5269": { name: "祥碩", sector: "半導體業" },
  "5871": { name: "中租-KY", sector: "其他金融業" },
  "5876": { name: "上海商銀", sector: "金融保險業" },
  "6213": { name: "聯茂", sector: "電子零組件業" },
  "6239": { name: "力成", sector: "半導體業" },
  "6415": { name: "矽力*-KY", sector: "半導體業" },
  "6669": { name: "緯穎", sector: "電腦及週邊設備業" },
  "6781": { name: "AES-KY", sector: "電子零組件業" },
  "8046": { name: "南電", sector: "電子零組件業" },
  "8069": { name: "元太", sector: "光電業" },
  "8299": { name: "群聯", sector: "半導體業" },
  "9910": { name: "豐泰", sector: "貿易百貨業" },
  AAPL: { name: "Apple", sector: "海外硬體科技" },
  AMAT: { name: "Applied Materials", sector: "海外半導體" },
  AMD: { name: "AMD", sector: "海外半導體" },
  AMZN: { name: "Amazon", sector: "海外雲端平台" },
  ASML: { name: "ASML", sector: "海外半導體" },
  AVGO: { name: "Broadcom", sector: "海外半導體" },
  BEAM: { name: "Beam Therapeutics", sector: "海外生技醫療" },
  COIN: { name: "Coinbase", sector: "海外金融科技" },
  CRSP: { name: "CRISPR Therapeutics", sector: "海外生技醫療" },
  GOOGL: { name: "Alphabet", sector: "海外雲端平台" },
  META: { name: "Meta", sector: "海外雲端平台" },
  MSFT: { name: "Microsoft", sector: "海外軟體服務" },
  NVDA: { name: "NVIDIA", sector: "海外半導體" },
  PATH: { name: "UiPath", sector: "海外軟體服務" },
  PLTR: { name: "Palantir", sector: "海外軟體服務" },
  ROKU: { name: "Roku", sector: "海外創新科技" },
  SHOP: { name: "Shopify", sector: "海外雲端平台" },
  SNOW: { name: "Snowflake", sector: "海外軟體服務" },
  SQ: { name: "Block", sector: "海外金融科技" },
  TSLA: { name: "Tesla", sector: "海外電動車" },
  TSM: { name: "TSMC ADR", sector: "海外半導體" },
  TWLO: { name: "Twilio", sector: "海外軟體服務" },
  U: { name: "Unity", sector: "海外創新科技" },
};

const ETFS = [
  {
    code: "00400A",
    name: "主動國泰動能高息",
    type: "主動",
    tags: ["主動", "高股息", "動能", "台股"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2026-04-09",
    holdings: {
      "2330": 8.7,
      "2308": 6.4,
      "2383": 5.8,
      "3034": 4.6,
      "8046": 4.2,
      "2345": 3.9,
      "3702": 3.6,
      "2454": 3.4,
      "3017": 3.1,
      "2881": 2.8,
      "2891": 2.6,
    },
    rotation: ["2449", "6213", "3324", "6239"],
  },
  {
    code: "00401A",
    name: "主動摩根台灣鑫收",
    type: "主動",
    tags: ["主動", "月配", "收益", "掩護性買權"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2026-04-10",
    holdings: {
      "2330": 7.4,
      "2454": 6.8,
      "3702": 3.1,
      "2308": 3.0,
      "2317": 2.9,
      "2345": 2.6,
      "2881": 2.5,
      "2891": 2.4,
      "2313": 2.2,
      "2449": 2.0,
      "2412": 1.9,
    },
    rotation: ["2882", "5876", "8046", "6239"],
  },
  {
    code: "00403A",
    name: "主動統一升級50",
    type: "主動",
    tags: ["主動", "升級50", "半導體", "AI"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2026-05-12",
    holdings: {
      "2330": 18.2,
      "2454": 8.4,
      "3017": 7.2,
      "6669": 5.8,
      "2308": 5.1,
      "3661": 4.8,
      "2383": 4.2,
      "2345": 3.6,
      "2379": 3.1,
      "2059": 2.5,
    },
    rotation: ["3443", "5269", "3324", "8299"],
  },
  {
    code: "00405A",
    name: "主動富邦台灣龍耀",
    type: "主動",
    tags: ["主動", "AI供應鏈", "高速傳輸", "募集"],
    source: "模擬投組",
    status: "upcoming",
    listedDate: "",
    expectedListingDate: "2026-06 初",
    holdings: {
      "3017": 8.1,
      "2383": 6.9,
      "6669": 6.4,
      "3324": 5.8,
      "2345": 5.3,
      "3231": 4.6,
      "2059": 4.2,
      "8046": 3.8,
      "2395": 3.1,
      "2376": 2.8,
    },
    rotation: ["3661", "3443", "6213"],
  },
  {
    code: "00407A",
    name: "主動凱基台灣",
    type: "主動",
    tags: ["主動", "不配息", "AI", "待募集"],
    source: "模擬投組",
    status: "upcoming",
    listedDate: "",
    expectedListingDate: "募集 2026-06-04~2026-06-10",
    holdings: {
      "2330": 12.2,
      "2454": 7.8,
      "2308": 6.5,
      "2382": 5.7,
      "3017": 4.9,
      "2345": 4.7,
      "3443": 3.8,
      "2379": 3.4,
      "6669": 3.2,
      "2059": 2.7,
    },
    rotation: ["2395", "3324", "6415"],
  },
  {
    code: "00980A",
    name: "主動野村臺灣優選",
    type: "主動",
    tags: ["主動", "價值", "成長", "台股"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2025-05-05",
    holdings: {
      "2330": 13.4,
      "2454": 6.8,
      "2308": 5.5,
      "2382": 4.8,
      "2881": 4.1,
      "2891": 3.8,
      "3711": 3.5,
      "1216": 3.1,
      "5871": 2.8,
      "2207": 2.5,
    },
    rotation: ["3008", "1590", "8046"],
  },
  {
    code: "00981A",
    name: "主動統一台股增長",
    type: "主動",
    tags: ["主動", "成長", "台股", "精選"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2025-05-27",
    holdings: {
      "2330": 13.7,
      "2454": 6.9,
      "2382": 5.5,
      "3017": 5.2,
      "2308": 4.8,
      "2317": 4.2,
      "3661": 3.7,
      "2345": 3.5,
      "3034": 3.2,
      "2881": 2.9,
      "2603": 2.3,
    },
    rotation: ["3443", "5269", "3324"],
  },
  {
    code: "00982A",
    name: "主動群益台灣強棒",
    type: "主動",
    tags: ["主動", "量化", "台股", "強棒"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2025-05-22",
    holdings: {
      "2330": 12.8,
      "2454": 7.2,
      "2308": 5.7,
      "2317": 4.9,
      "2345": 4.4,
      "3017": 4.0,
      "2881": 3.8,
      "2886": 3.3,
      "2412": 2.9,
      "2603": 2.7,
    },
    rotation: ["3702", "8046", "5871"],
  },
  {
    code: "00983A",
    name: "主動中信ARK創新",
    type: "主動",
    tags: ["主動", "海外", "創新科技", "ARK"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2025-06-18",
    holdings: {
      TSLA: 8.2,
      COIN: 6.7,
      ROKU: 5.8,
      SHOP: 5.4,
      SQ: 4.9,
      BEAM: 3.4,
      CRSP: 3.2,
      PATH: 3.0,
      U: 2.8,
      TWLO: 2.6,
    },
    rotation: ["PLTR", "SNOW", "NVDA"],
  },
  {
    code: "00984A",
    name: "主動安聯台灣高息",
    type: "主動",
    tags: ["主動", "高股息", "成長", "台股"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2025-07-14",
    holdings: {
      "2454": 6.1,
      "2891": 5.6,
      "2886": 5.2,
      "2308": 4.7,
      "2383": 4.2,
      "3702": 3.8,
      "2603": 3.5,
      "2412": 3.2,
      "2882": 3.0,
      "1216": 2.8,
    },
    rotation: ["3045", "5871", "2317"],
  },
  {
    code: "00990A",
    name: "主動元大全球AI新經濟",
    type: "主動",
    tags: ["主動", "全球", "AI", "新經濟"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2025-12-18",
    holdings: {
      NVDA: 9.2,
      MSFT: 7.4,
      AVGO: 6.7,
      TSM: 5.8,
      ASML: 5.1,
      AMD: 4.8,
      AMZN: 4.5,
      GOOGL: 4.1,
      META: 3.7,
      PLTR: 3.2,
    },
    rotation: ["SNOW", "AMAT", "AAPL"],
  },
  {
    code: "00991A",
    name: "主動復華未來50",
    type: "主動",
    tags: ["主動", "未來50", "台股", "科技"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2025-12-22",
    holdings: {
      "2330": 11.8,
      "2454": 7.6,
      "2308": 6.2,
      "2382": 5.6,
      "3017": 5.1,
      "2345": 4.9,
      "3443": 4.0,
      "3661": 3.7,
      "6669": 3.4,
      "3034": 3.0,
    },
    rotation: ["5269", "8299", "3324"],
  },
  {
    code: "00992A",
    name: "主動群益科技創新",
    type: "主動",
    tags: ["主動", "科技", "創新", "台股"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2025-11-24",
    holdings: {
      "2330": 14.1,
      "2454": 7.9,
      "2308": 6.8,
      "3017": 6.1,
      "2383": 5.3,
      "2379": 4.8,
      "3443": 4.2,
      "8046": 3.9,
      "6669": 3.4,
      "2345": 3.2,
    },
    rotation: ["3324", "5269", "6415"],
  },
  {
    code: "00998A",
    name: "主動復華金融股息",
    type: "主動",
    tags: ["主動", "金融", "股息", "防禦"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2026-03-18",
    holdings: {
      "2881": 9.1,
      "2891": 8.6,
      "2886": 7.4,
      "2882": 6.7,
      "2892": 5.8,
      "2884": 5.2,
      "2880": 4.9,
      "2887": 4.1,
      "5876": 3.5,
      "5871": 3.2,
    },
    rotation: ["2412", "1216", "2603"],
  },
  {
    code: "00999A",
    name: "主動野村臺灣高息",
    type: "主動",
    tags: ["主動", "高股息", "季配", "台股"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2026-04-24",
    holdings: {
      "2454": 6.8,
      "2881": 6.3,
      "2891": 5.9,
      "2886": 5.5,
      "2603": 4.8,
      "2308": 4.3,
      "2383": 3.8,
      "2412": 3.6,
      "1303": 3.1,
      "1216": 2.9,
    },
    rotation: ["3045", "5871", "2317"],
  },
  {
    code: "009816",
    name: "凱基台灣TOP50",
    type: "被動",
    tags: ["被動", "TOP50", "不配息", "大型股"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2026-02-19",
    holdings: {
      "2330": 30.4,
      "2317": 5.3,
      "2454": 4.9,
      "2308": 4.5,
      "2382": 3.8,
      "2881": 3.0,
      "2882": 2.8,
      "3711": 2.4,
      "2303": 2.2,
      "2412": 2.1,
    },
    rotation: ["1216", "1590", "2207"],
  },
  {
    code: "0050",
    name: "元大台灣50",
    type: "被動",
    tags: ["被動", "市值型", "大型股", "台灣50"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2003-06-30",
    holdings: {
      "2330": 31.8,
      "2317": 5.5,
      "2454": 4.8,
      "2308": 4.2,
      "2382": 3.6,
      "2881": 3.1,
      "2882": 2.8,
      "2303": 2.5,
      "3711": 2.2,
      "2412": 2.0,
    },
    rotation: ["1216", "1590", "2207"],
  },
  {
    code: "006208",
    name: "富邦台50",
    type: "被動",
    tags: ["被動", "市值型", "大型股", "台灣50"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2012-07-17",
    holdings: {
      "2330": 31.5,
      "2317": 5.4,
      "2454": 4.7,
      "2308": 4.1,
      "2382": 3.4,
      "2881": 3.0,
      "2882": 2.7,
      "2303": 2.4,
      "3711": 2.1,
      "2412": 2.0,
    },
    rotation: ["1216", "1590", "2207"],
  },
  {
    code: "00878",
    name: "國泰永續高股息",
    type: "被動",
    tags: ["被動", "高股息", "ESG", "收益"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2020-07-20",
    holdings: {
      "2454": 6.2,
      "2317": 5.7,
      "2891": 5.1,
      "2882": 4.9,
      "2886": 4.5,
      "2412": 4.3,
      "3045": 3.9,
      "1303": 3.5,
      "5871": 3.2,
      "2603": 2.8,
    },
    rotation: ["1216", "2884", "2303"],
  },
  {
    code: "00881",
    name: "國泰台灣5G+",
    type: "被動",
    tags: ["被動", "科技", "5G", "半導體"],
    source: "前端種子資料",
    status: "listed",
    listedDate: "2020-12-10",
    holdings: {
      "2330": 23.6,
      "2454": 8.1,
      "2308": 6.7,
      "2382": 5.9,
      "3017": 5.5,
      "2345": 5.2,
      "2379": 4.4,
      "2383": 4.0,
      "3034": 3.5,
      "6669": 3.2,
    },
    rotation: ["3324", "8046", "3443"],
  },
];

const SECTOR_COLORS = {
  半導體業: "#087f73",
  "電腦及週邊設備業": "#116a8c",
  電子零組件業: "#6f7f1d",
  金融保險業: "#b86f00",
  通信網路業: "#4f6f52",
  其他電子業: "#8d5a36",
  航運業: "#8b5c94",
  食品工業: "#9d5f22",
  塑膠工業: "#5e6b7a",
  電機機械: "#4d7d8a",
  光電業: "#7f5b72",
  汽車工業: "#47636a",
  其他金融業: "#9a6b2f",
  水泥工業: "#707064",
  貿易百貨業: "#7a6345",
  電子通路業: "#886d3f",
  紡織纖維: "#705f7f",
  海外半導體: "#0d6f86",
  海外軟體服務: "#385a93",
  海外雲端平台: "#6f5b95",
  海外創新科技: "#7d5d74",
  海外生技醫療: "#2f7d69",
  海外金融科技: "#9a6c25",
  海外電動車: "#746331",
  海外硬體科技: "#4a7280",
  未分類: "#657270",
};

const state = {
  selected: [
    { code: "00400A", allocation: 30 },
    { code: "00403A", allocation: 35 },
    { code: "009816", allocation: 35 },
  ],
  query: "",
  overlapMin: 2,
  sectorView: "treemap",
  activeSector: "",
  historyEtfCode: "00400A",
  activePortfolioId: "",
};

const els = {
  updateStatusPill: document.getElementById("updateStatusPill"),
  refreshDataBtn: document.getElementById("refreshDataBtn"),
  autoSyncToggleBtn: document.getElementById("autoSyncToggleBtn"),
  lastRefreshText: document.getElementById("lastRefreshText"),
  search: document.getElementById("etfSearch"),
  universeSummary: document.getElementById("universeSummary"),
  searchResults: document.getElementById("searchResults"),
  notice: document.getElementById("selectorNotice"),
  autoAllocateBtn: document.getElementById("autoAllocateBtn"),
  autoAllocationNotice: document.getElementById("autoAllocationNotice"),
  targetSectors: [
    document.getElementById("targetSector1"),
    document.getElementById("targetSector2"),
    document.getElementById("targetSector3"),
  ],
  targetWeights: [
    document.getElementById("targetWeight1"),
    document.getElementById("targetWeight2"),
    document.getElementById("targetWeight3"),
  ],
  selectedEtfs: document.getElementById("selectedEtfs"),
  limitCounter: document.getElementById("limitCounter"),
  allocationTotal: document.getElementById("allocationTotal"),
  allocationBar: document.getElementById("allocationBar"),
  equalizeBtn: document.getElementById("equalizeBtn"),
  savePortfolioBtn: document.getElementById("savePortfolioBtn"),
  portfolioNameInput: document.getElementById("portfolioNameInput"),
  portfolioSelect: document.getElementById("portfolioSelect"),
  loadPortfolioBtn: document.getElementById("loadPortfolioBtn"),
  deletePortfolioBtn: document.getElementById("deletePortfolioBtn"),
  portfolioNotice: document.getElementById("portfolioNotice"),
  watchlistEtfSelect: document.getElementById("watchlistEtfSelect"),
  watchlistNoteInput: document.getElementById("watchlistNoteInput"),
  addWatchlistBtn: document.getElementById("addWatchlistBtn"),
  refreshWatchStatusBtn: document.getElementById("refreshWatchStatusBtn"),
  watchlistList: document.getElementById("watchlistList"),
  watchlistNotice: document.getElementById("watchlistNotice"),
  holdingCount: document.getElementById("holdingCount"),
  topExposure: document.getElementById("topExposure"),
  topSector: document.getElementById("topSector"),
  overlapCount: document.getElementById("overlapCount"),
  riskBadge: document.getElementById("riskBadge"),
  exportExposureCsvBtn: document.getElementById("exportExposureCsvBtn"),
  exportExposurePdfBtn: document.getElementById("exportExposurePdfBtn"),
  exposureChart: document.getElementById("exposureChart"),
  sectorViz: document.getElementById("sectorViz"),
  sectorDetail: document.getElementById("sectorDetail"),
  heatmap: document.getElementById("heatmap"),
  overlapSlider: document.getElementById("overlapSlider"),
  overlapValue: document.getElementById("overlapValue"),
  historyEtfSelect: document.getElementById("historyEtfSelect"),
  historySummary: document.getElementById("historySummary"),
  historyChart: document.getElementById("historyChart"),
  historyTable: document.getElementById("historyTable"),
  qualityPanel: document.getElementById("qualityPanel"),
};

const percent = new Intl.NumberFormat("zh-TW", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

function fmt(value) {
  return `${percent.format(value)}%`;
}

function signedFmt(value) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${percent.format(value)}%`;
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/[",\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

function downloadCsv(filename, rows) {
  const content = rows.map((row) => row.map(csvEscape).join(",")).join("\n");
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function timestampLabel(now = new Date()) {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  const h = String(now.getHours()).padStart(2, "0");
  const min = String(now.getMinutes()).padStart(2, "0");
  return `${y}${m}${d}-${h}${min}`;
}

function getEtf(code) {
  return ETFS.find((etf) => etf.code === code);
}

function setNotice(message) {
  selectorNoticeMessage = message;
  if (els.notice) els.notice.textContent = message;
}

function isListed(etf) {
  return etf?.status === "listed" && etf.listedDate && etf.listedDate <= DATA_END_DATE;
}

function canUseEtf(etf) {
  return Boolean(etf && isListed(etf) && etf.source !== "模擬投組");
}

function listingLabel(etf) {
  if (!etf) return "";
  if (isListed(etf)) return `已上市 ${etf.listedDate}`;
  return `未上市 ${etf.expectedListingDate || etf.listedDate || "待公告"}`;
}

function selectedCodes() {
  return new Set(state.selected.map((item) => item.code));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function sourceLabel(etf) {
  if (!etf) return "未知來源";
  if (etf.source === "模擬投組") return "模擬";
  if (etf.source === "前端種子資料") return "種子";
  return "API";
}

function coverageLabel(etf) {
  if (!etf) return "";
  if (etf.source === "模擬投組") return "模擬";
  if (etf.coverage && etf.coverage !== "full") return "部分持股";
  if (etf.coverage === "full") return "完整";
  if (etf.source === "前端種子資料") return "種子資料";
  return "待驗證";
}

function coverageClass(etf) {
  if (!etf) return "pending";
  if (etf.source === "模擬投組" || etf.source === "前端種子資料" || etf.coverage !== "full") return "pending";
  return "";
}

function scoreEtf(etf, query) {
  const q = query.trim().toLowerCase();
  if (!q) return 1;
  const haystack = [etf.code, etf.name, etf.type, etf.source, etf.status, ...etf.tags]
    .join(" ")
    .toLowerCase();
  if (etf.code.toLowerCase().startsWith(q)) return 100;
  if (etf.name.toLowerCase().includes(q)) return 80;
  if (etf.tags.some((tag) => tag.toLowerCase().includes(q))) return 70;
  return haystack.includes(q) ? 40 : 0;
}

function upsertEtfFromApi(apiRow) {
  const code = String(apiRow?.code || "").toUpperCase();
  if (!code) return;
  const existing = getEtf(code);
  const tags = Array.isArray(apiRow.tags) ? apiRow.tags : [];
  const status = apiRow.status || (apiRow.listed ? "listed" : "upcoming");

  if (existing) {
    existing.name = apiRow.name || existing.name;
    existing.type = apiRow.type || existing.type;
    existing.tags = tags.length ? tags : existing.tags;
    existing.source = apiRow.source || existing.source || "API";
    existing.status = status || existing.status;
    existing.listedDate = apiRow.listedDate ?? existing.listedDate;
    existing.expectedListingDate = apiRow.expectedListingDate ?? existing.expectedListingDate;
    return;
  }

  ETFS.push({
    code,
    name: apiRow.name || code,
    type: apiRow.type || "",
    tags,
    source: apiRow.source || "API",
    status,
    listedDate: apiRow.listedDate || "",
    expectedListingDate: apiRow.expectedListingDate || "",
    holdings: {},
    rotation: [],
  });
}

async function fetchEtfSearch(query = "") {
  const endpoint = `/api/etfs/search?q=${encodeURIComponent(query)}&ts=${Date.now()}`;
  const response = await fetch(endpoint, { cache: "no-store" });
  if (!response.ok) {
    let message = "ETF search API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

async function fetchEtfHoldingSnapshot(code) {
  const endpoint = `/api/etfs/${encodeURIComponent(code)}/holdings?ts=${Date.now()}`;
  const response = await fetch(endpoint, { cache: "no-store" });
  if (!response.ok) {
    let message = "ETF holdings API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function applyHoldingSnapshot(snapshot) {
  const code = String(snapshot?.code || "").toUpperCase();
  if (!code) return;
  const etf = getEtf(code);
  if (!etf) return;
  if (snapshot.holdings) etf.holdings = snapshot.holdings;
  if (snapshot.holdingDetails) {
    etf.holdingDetails = snapshot.holdingDetails;
    mergeHoldingDetails(snapshot.holdingDetails);
  }
  if (snapshot.coverage) etf.coverage = snapshot.coverage;
  if (snapshot.source) etf.source = snapshot.source;
  if (snapshot.declaredHoldingCount !== undefined) etf.declaredHoldingCount = snapshot.declaredHoldingCount;
  if (snapshot.parsedHoldingCount !== undefined) etf.parsedHoldingCount = snapshot.parsedHoldingCount;
  if (snapshot.asOf) etf.asOf = snapshot.asOf;
}

function ensureHoldingSnapshot(code) {
  if (holdingApiState.loaded.has(code) || holdingApiState.pending.has(code)) return;
  holdingApiState.pending.add(code);
  fetchEtfHoldingSnapshot(code)
    .then((snapshot) => {
      applyHoldingSnapshot(snapshot);
      holdingApiState.loaded.add(code);
      holdingApiState.errors.delete(code);
      historyApiState.cache.delete(historyCacheKey(code, HISTORY_CHANGE_DAYS));
    })
    .catch((error) => {
      holdingApiState.errors.set(code, error.message || "ETF holdings API failed.");
    })
    .finally(() => {
      holdingApiState.pending.delete(code);
      renderAll();
    });
}

function ensureSelectedHoldings() {
  for (const item of state.selected) {
    const code = String(item.code || "").toUpperCase();
    const etf = getEtf(code);
    if (!etf || !isListed(etf)) continue;
    if (holdingApiState.loaded.has(code)) continue;
    if (etf.source === "前端種子資料" || !etf.coverage || etf.coverage === "seed") {
      ensureHoldingSnapshot(code);
    }
  }
}

function setPortfolioNotice(message) {
  if (els.portfolioNotice) els.portfolioNotice.textContent = message || "";
}

function findPortfolioRow(id) {
  return portfolioApiState.rows.find((row) => row.id === id);
}

function defaultPortfolioName(now = new Date()) {
  const time = now.toLocaleTimeString("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `組合 ${formatDate(now)} ${time}`;
}

function selectedPortfolioId() {
  return els.portfolioSelect?.value || portfolioApiState.selectedId || "";
}

function buildPortfolioPositions() {
  return state.selected
    .map((item) => ({
      code: String(item.code || "").toUpperCase(),
      allocation: Number(item.allocation || 0),
    }))
    .filter((item) => item.code && item.allocation >= 0);
}

async function fetchPortfolios() {
  const response = await fetch(`/api/portfolios?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    let message = "Portfolios API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

async function fetchPortfolioById(id) {
  const response = await fetch(`/api/portfolios/${encodeURIComponent(id)}?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    let message = "Portfolio item API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

async function savePortfolioApi(payload) {
  const response = await fetch("/api/portfolios", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let message = "Save portfolio API failed.";
    try {
      const body = await response.json();
      message = body.message || body.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

async function deletePortfolioApi(id) {
  const response = await fetch(`/api/portfolios/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    let message = "Delete portfolio API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function renderPortfolioManager() {
  if (!els.portfolioSelect || !els.portfolioNameInput) return;
  const rows = portfolioApiState.rows;
  const selectedId = selectedPortfolioId();
  const selectedRow = findPortfolioRow(selectedId);

  els.portfolioSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = rows.length ? "選擇已儲存組合" : "尚無已儲存組合";
  placeholder.selected = !selectedRow;
  els.portfolioSelect.appendChild(placeholder);

  for (const row of rows) {
    const option = document.createElement("option");
    option.value = row.id;
    option.textContent = `${row.name} (${row.positionCount} 檔)`;
    option.selected = row.id === selectedId;
    els.portfolioSelect.appendChild(option);
  }

  els.portfolioSelect.disabled = !rows.length || portfolioApiState.loading;
  els.loadPortfolioBtn.disabled = !rows.length || !selectedPortfolioId() || portfolioApiState.loading;
  els.deletePortfolioBtn.disabled = !rows.length || !selectedPortfolioId() || portfolioApiState.loading;
  els.savePortfolioBtn.disabled = portfolioApiState.loading;
  if (selectedRow && !els.portfolioNameInput.value.trim()) {
    els.portfolioNameInput.value = selectedRow.name;
  }
}

async function loadPortfolioList() {
  portfolioApiState.loading = true;
  renderPortfolioManager();
  try {
    const payload = await fetchPortfolios();
    portfolioApiState.rows = Array.isArray(payload.rows) ? payload.rows : [];
    portfolioApiState.error = "";
    if (portfolioApiState.selectedId && !findPortfolioRow(portfolioApiState.selectedId)) {
      portfolioApiState.selectedId = "";
    }
  } catch (error) {
    portfolioApiState.error = error.message || "Portfolios API failed.";
    setPortfolioNotice(`組合清單載入失敗：${portfolioApiState.error}`);
  } finally {
    portfolioApiState.loading = false;
    renderPortfolioManager();
  }
}

async function saveCurrentPortfolio() {
  const positions = buildPortfolioPositions();
  if (!positions.length) {
    setPortfolioNotice("目前沒有可儲存的 ETF 配置。");
    return;
  }

  const selectedId = selectedPortfolioId();
  const selectedRow = findPortfolioRow(selectedId);
  const inputName = els.portfolioNameInput.value.trim();
  const name = inputName || selectedRow?.name || defaultPortfolioName();
  const shouldUpdateCurrent = Boolean(selectedRow && (!inputName || inputName === selectedRow.name));
  const payload = {
    id: shouldUpdateCurrent ? selectedRow.id : undefined,
    name,
    positions,
  };

  portfolioApiState.loading = true;
  renderPortfolioManager();
  try {
    const response = await savePortfolioApi(payload);
    portfolioApiState.rows = Array.isArray(response.rows) ? response.rows : portfolioApiState.rows;
    portfolioApiState.selectedId = response.summary?.id || response.portfolio?.id || "";
    state.activePortfolioId = portfolioApiState.selectedId;
    els.portfolioNameInput.value = response.summary?.name || name;
    setPortfolioNotice(`已儲存組合：${response.summary?.name || name}`);
  } catch (error) {
    setPortfolioNotice(`儲存失敗：${error.message || "未知錯誤"}`);
  } finally {
    portfolioApiState.loading = false;
    renderPortfolioManager();
  }
}

async function loadSelectedPortfolio() {
  const id = selectedPortfolioId();
  if (!id) {
    setPortfolioNotice("請先選擇要載入的組合。");
    return;
  }

  portfolioApiState.loading = true;
  renderPortfolioManager();
  try {
    const payload = await fetchPortfolioById(id);
    const portfolio = payload.portfolio || {};
    const positions = Array.isArray(portfolio.positions) ? portfolio.positions : [];
    const nextSelected = positions
      .map((row) => ({
        code: String(row.code || "").toUpperCase(),
        allocation: Number(row.allocation || 0),
      }))
      .filter((row) => row.code && getEtf(row.code));
    if (!nextSelected.length) {
      throw new Error("該組合沒有可用的 ETF 代碼。");
    }

    state.selected = nextSelected;
    state.activePortfolioId = portfolio.id || id;
    portfolioApiState.selectedId = portfolio.id || id;
    els.portfolioNameInput.value = portfolio.name || "";
    state.historyEtfCode = nextSelected.find((item) => isListed(getEtf(item.code)))?.code || "";
    setPortfolioNotice(`已載入組合：${portfolio.name || id}`);
    renderAll();
  } catch (error) {
    setPortfolioNotice(`載入失敗：${error.message || "未知錯誤"}`);
  } finally {
    portfolioApiState.loading = false;
    renderPortfolioManager();
  }
}

async function deleteSelectedPortfolio() {
  const id = selectedPortfolioId();
  if (!id) {
    setPortfolioNotice("請先選擇要刪除的組合。");
    return;
  }

  portfolioApiState.loading = true;
  renderPortfolioManager();
  try {
    const payload = await deletePortfolioApi(id);
    portfolioApiState.rows = Array.isArray(payload.rows) ? payload.rows : [];
    if (portfolioApiState.selectedId === id) portfolioApiState.selectedId = "";
    if (state.activePortfolioId === id) state.activePortfolioId = "";
    setPortfolioNotice(`已刪除組合：${payload.deleted?.name || id}`);
  } catch (error) {
    setPortfolioNotice(`刪除失敗：${error.message || "未知錯誤"}`);
  } finally {
    portfolioApiState.loading = false;
    renderPortfolioManager();
  }
}

function setWatchlistNotice(message, options = {}) {
  const { manual = true, ttlMs = 0 } = options;
  if (manual) {
    watchlistApiState.manualNotice = message || "";
    if (ttlMs > 0) {
      const currentMessage = watchlistApiState.manualNotice;
      setTimeout(() => {
        if (watchlistApiState.manualNotice === currentMessage) {
          watchlistApiState.manualNotice = "";
          renderWatchlistNotice();
        }
      }, ttlMs);
    }
  } else {
    watchlistApiState.alertSummary = message || "";
  }
  renderWatchlistNotice();
}

function renderWatchlistNotice() {
  if (!els.watchlistNotice) return;
  els.watchlistNotice.textContent = watchlistApiState.manualNotice || watchlistApiState.alertSummary || "";
}

function statusRowsHash(rows) {
  return rows
    .map((row) => `${row.code}:${row.status || ""}:${row.coverage || ""}:${row.historySnapshotCount || 0}:${row.asOf || ""}`)
    .sort()
    .join("|");
}

function buildWatchlistAlertSummary(statusRows) {
  const ready = statusRows.filter((row) => row.status === "ready").length;
  const partial = statusRows.filter((row) => row.status === "partial").length;
  const seed = statusRows.filter((row) => row.status === "seed").length;
  const missing = statusRows.filter((row) => row.status === "missing" || row.status === "empty").length;
  const lowHistory = statusRows.filter((row) => Number(row.historySnapshotCount || 0) < 2).length;
  const issues = partial + seed + missing;
  if (!statusRows.length) return "尚未加入追蹤。";
  if (issues === 0 && lowHistory === 0) return `追蹤狀態正常：${ready} 檔 ready。`;
  const parts = [];
  if (partial) parts.push(`partial ${partial}`);
  if (seed) parts.push(`seed ${seed}`);
  if (missing) parts.push(`missing ${missing}`);
  if (lowHistory) parts.push(`快照不足 ${lowHistory}`);
  return `追蹤提醒：${parts.join("、")}。`;
}

async function fetchWatchlist() {
  const response = await fetch(`/api/watchlist?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    let message = "Watchlist API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

async function saveWatchlistApi(payload) {
  const response = await fetch("/api/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let message = "Save watchlist API failed.";
    try {
      const body = await response.json();
      message = body.message || body.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

async function deleteWatchlistApi(code) {
  const response = await fetch(`/api/watchlist/${encodeURIComponent(code)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    let message = "Delete watchlist API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

async function fetchUpdatesStatus(codes) {
  const query = codes?.length ? `?codes=${encodeURIComponent(codes.join(","))}&ts=${Date.now()}` : `?ts=${Date.now()}`;
  const response = await fetch(`/api/updates/status${query}`, { cache: "no-store" });
  if (!response.ok) {
    let message = "Updates status API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function applyWatchlistPayload(payload) {
  watchlistApiState.rows = Array.isArray(payload.rows) ? payload.rows : [];
  const statuses = new Map();
  const statusRows = Array.isArray(payload.statuses) ? payload.statuses : [];
  for (const row of statusRows) {
    if (row?.code) statuses.set(row.code, row);
  }
  watchlistApiState.statuses = statuses;
  const nextHash = statusRowsHash(statusRows);
  const summary = buildWatchlistAlertSummary(statusRows);
  const changed = nextHash && nextHash !== watchlistApiState.lastStatusHash;
  watchlistApiState.lastStatusHash = nextHash;
  setWatchlistNotice(summary, { manual: false });
  if (changed && !watchlistApiState.manualNotice) {
    setNotice(`追蹤清單狀態有更新：${summary}`);
  }
}

function watchStatusLabel(statusRow) {
  if (!statusRow) return "無狀態";
  if (statusRow.status === "ready") return "已就緒";
  if (statusRow.status === "partial") return "部分";
  if (statusRow.status === "seed") return "種子";
  if (statusRow.status === "missing") return "缺資料";
  return statusRow.status || "未知";
}

function renderWatchlistManager() {
  if (!els.watchlistEtfSelect || !els.watchlistList) return;
  const listedEtfs = ETFS.filter(isListed).sort((a, b) => a.code.localeCompare(b.code));
  const currentValue = els.watchlistEtfSelect.value;
  els.watchlistEtfSelect.innerHTML = "";
  for (const etf of listedEtfs) {
    const option = document.createElement("option");
    option.value = etf.code;
    option.textContent = `${etf.code} ${etf.name}`;
    option.selected = etf.code === currentValue;
    els.watchlistEtfSelect.appendChild(option);
  }

  const rows = watchlistApiState.rows;
  els.watchlistList.innerHTML = "";
  if (!rows.length) {
    els.watchlistList.innerHTML = `<div class="empty-state small">尚未加入追蹤</div>`;
  } else {
    for (const row of rows) {
      const statusRow = watchlistApiState.statuses.get(row.code);
      const div = document.createElement("div");
      div.className = "watch-row";
      div.innerHTML = `
        <div class="watch-row-main">
          <div class="watch-row-head">
            <span class="code-chip">${escapeHtml(row.code)}</span>
            <span class="watch-chip ${escapeHtml(statusRow?.status || "missing")}">${escapeHtml(watchStatusLabel(statusRow))}</span>
            <span class="watch-chip">${escapeHtml(statusRow?.asOf || "no date")}</span>
          </div>
          <div class="watch-row-meta">
            <span class="watch-chip">${escapeHtml(statusRow?.coverage || "no coverage")}</span>
            <span class="watch-chip">${escapeHtml((statusRow?.historySnapshotCount ?? 0) + " 筆快照")}</span>
          </div>
          ${row.note ? `<div class="watch-row-note">${escapeHtml(row.note)}</div>` : ""}
        </div>
        <button class="remove-button" type="button" data-watchlist-delete="${escapeHtml(row.code)}" title="移除追蹤" aria-label="移除追蹤 ${escapeHtml(row.code)}">×</button>
      `;
      els.watchlistList.appendChild(div);
    }
  }

  els.watchlistEtfSelect.disabled = watchlistApiState.loading;
  els.addWatchlistBtn.disabled = watchlistApiState.loading || !listedEtfs.length;
  els.refreshWatchStatusBtn.disabled = watchlistApiState.loading;
}

async function loadWatchlist() {
  watchlistApiState.loading = true;
  renderWatchlistManager();
  try {
    const payload = await fetchWatchlist();
    applyWatchlistPayload(payload);
    watchlistApiState.error = "";
  } catch (error) {
    watchlistApiState.error = error.message || "Watchlist API failed.";
    setWatchlistNotice(`追蹤清單載入失敗：${watchlistApiState.error}`, { ttlMs: 9000 });
  } finally {
    watchlistApiState.loading = false;
    renderWatchlistManager();
  }
}

async function refreshWatchStatuses() {
  const codes = watchlistApiState.rows.map((row) => row.code);
  if (!codes.length) {
    setWatchlistNotice("尚未加入任何追蹤 ETF。", { ttlMs: 6000 });
    return;
  }
  watchlistApiState.loading = true;
  renderWatchlistManager();
  try {
    const payload = await fetchUpdatesStatus(codes);
    const statuses = new Map();
    for (const row of payload.rows || []) {
      if (row?.code) statuses.set(row.code, row);
    }
    watchlistApiState.statuses = statuses;
    const summary = payload.summary || {};
    setWatchlistNotice(`狀態已刷新：ready ${summary.ready ?? 0}、partial ${summary.partial ?? 0}、missing ${summary.missing ?? 0}`, { ttlMs: 7000 });
  } catch (error) {
    setWatchlistNotice(`狀態刷新失敗：${error.message || "未知錯誤"}`, { ttlMs: 9000 });
  } finally {
    watchlistApiState.loading = false;
    renderWatchlistManager();
  }
}

async function addWatchlist() {
  const code = String(els.watchlistEtfSelect.value || "").toUpperCase();
  if (!code) {
    setWatchlistNotice("請先選擇 ETF。", { ttlMs: 6000 });
    return;
  }
  watchlistApiState.loading = true;
  renderWatchlistManager();
  try {
    const payload = await saveWatchlistApi({
      code,
      note: els.watchlistNoteInput.value.trim(),
    });
    watchlistApiState.rows = Array.isArray(payload.rows) ? payload.rows : watchlistApiState.rows;
    els.watchlistNoteInput.value = "";
    setWatchlistNotice(`已加入追蹤：${code}`, { ttlMs: 7000 });
    await refreshWatchStatuses();
  } catch (error) {
    setWatchlistNotice(`加入追蹤失敗：${error.message || "未知錯誤"}`, { ttlMs: 9000 });
  } finally {
    watchlistApiState.loading = false;
    renderWatchlistManager();
  }
}

async function removeWatchlist(code) {
  watchlistApiState.loading = true;
  renderWatchlistManager();
  try {
    const payload = await deleteWatchlistApi(code);
    watchlistApiState.rows = Array.isArray(payload.rows) ? payload.rows : [];
    watchlistApiState.statuses.delete(code);
    setWatchlistNotice(`已移除追蹤：${code}`, { ttlMs: 7000 });
  } catch (error) {
    setWatchlistNotice(`移除追蹤失敗：${error.message || "未知錯誤"}`, { ttlMs: 9000 });
  } finally {
    watchlistApiState.loading = false;
    renderWatchlistManager();
  }
}

async function loadUniverseFromApi() {
  if (universeApiState.loaded || universeApiState.loading) return;
  universeApiState.loading = true;
  try {
    const payload = await fetchEtfSearch("");
    const rows = Array.isArray(payload.rows) ? payload.rows : [];
    rows.forEach(upsertEtfFromApi);
    universeApiState.loaded = true;
    universeApiState.error = "";
    if (payload.asOf) DATA_END_DATE = payload.asOf;
  } catch (error) {
    universeApiState.error = error.message || "ETF universe API failed.";
  } finally {
    universeApiState.loading = false;
  }
}

function buildComparePositions() {
  return state.selected
    .map((item) => ({
      code: String(item.code || "").toUpperCase(),
      allocation: Number(item.allocation || 0),
    }))
    .filter((item) => item.code && item.allocation > 0);
}

function compareCacheKey(positions) {
  const normalized = [...positions].sort((a, b) => a.code.localeCompare(b.code));
  return normalized.map((row) => `${row.code}:${row.allocation.toFixed(3)}`).join("|");
}

async function fetchExposureCompare(positions) {
  const response = await fetch("/api/exposure/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ positions }),
  });
  if (!response.ok) {
    let message = "Exposure compare API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function hydrateCompareSnapshots(snapshots) {
  if (!Array.isArray(snapshots)) return;
  for (const snapshot of snapshots) {
    const etf = getEtf(snapshot.code);
    if (!etf) continue;
    if (snapshot.coverage) etf.coverage = snapshot.coverage;
    if (snapshot.source) etf.source = snapshot.source;
    if (snapshot.asOf) etf.asOf = snapshot.asOf;
  }
}

function ensureCompareModel() {
  const positions = buildComparePositions();
  if (!positions.length) return;
  const key = compareCacheKey(positions);
  if (compareApiState.cache.has(key) || compareApiState.pending.has(key)) return;
  compareApiState.pending.add(key);
  fetchExposureCompare(positions)
    .then((payload) => {
      compareApiState.cache.set(key, payload);
      compareApiState.errors.delete(key);
      hydrateCompareSnapshots(payload.etfSnapshots);
    })
    .catch((error) => {
      compareApiState.errors.set(key, error.message || "Exposure compare API failed.");
    })
    .finally(() => {
      compareApiState.pending.delete(key);
      renderAnalytics();
    });
}

function computePortfolio() {
  const exposures = new Map();
  const sectorTotals = new Map();
  const totalAllocation = state.selected.reduce((sum, item) => sum + Number(item.allocation || 0), 0);

  for (const item of state.selected) {
    const etf = getEtf(item.code);
    const allocation = Number(item.allocation || 0) / 100;
    if (!etf || allocation <= 0) continue;

    for (const [stockCode, weight] of Object.entries(etf.holdings)) {
      const stock = STOCKS[stockCode];
      const contribution = allocation * weight;
      const row =
        exposures.get(stockCode) ||
        {
          code: stockCode,
          name: stock?.name || stockCode,
          sector: stock?.sector || "未分類",
          total: 0,
          count: 0,
          byEtf: {},
          byEtfContribution: {},
        };
      row.total += contribution;
      row.count += 1;
      row.byEtf[etf.code] = weight;
      row.byEtfContribution[etf.code] = (row.byEtfContribution[etf.code] || 0) + contribution;
      exposures.set(stockCode, row);
      sectorTotals.set(row.sector, (sectorTotals.get(row.sector) || 0) + contribution);
    }
  }

  return {
    totalAllocation,
    exposures: [...exposures.values()].sort((a, b) => b.total - a.total),
    sectors: [...sectorTotals.entries()]
      .map(([sector, total]) => ({ sector, total }))
      .sort((a, b) => b.total - a.total),
  };
}

function renderSearch() {
  const picked = selectedCodes();
  const atLimit = state.selected.length >= COMPARE_LIMIT;
  const apiNotice = universeApiState.loading
    ? "正在載入 ETF universe API..."
    : universeApiState.error
      ? `ETF universe API 無法使用：${universeApiState.error}`
      : selectorNoticeMessage;
  els.search.disabled = atLimit;
  els.search.placeholder = atLimit ? "已達最大比對數量" : "代號、關鍵字、產業主題";
  els.limitCounter.textContent = `${state.selected.length} / ${COMPARE_LIMIT}`;
  els.notice.textContent = atLimit
    ? `已達 ${COMPARE_LIMIT} 檔同步比對上限；ETF universe 仍可透過移除後重新選取。`
    : apiNotice;
  renderUniverseSummary();

  const matches = ETFS.map((etf) => ({ etf, score: scoreEtf(etf, state.query) }))
    .filter(({ etf, score }) => score > 0 && !picked.has(etf.code))
    .sort((a, b) => b.score - a.score || a.etf.code.localeCompare(b.etf.code))
    .slice(0, 40);

  els.searchResults.innerHTML = "";
  if (!matches.length || atLimit) return;

  const groups = [
    { title: "已上市 ETF", rows: matches.filter(({ etf }) => isListed(etf)) },
    { title: "未上市 / 募集中 ETF", rows: matches.filter(({ etf }) => !isListed(etf)) },
  ];

  for (const group of groups) {
    if (!group.rows.length) continue;
    const heading = document.createElement("div");
    heading.className = "search-group-title";
    heading.textContent = group.title;
    els.searchResults.appendChild(heading);

    for (const { etf } of group.rows) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `search-result ${canUseEtf(etf) ? "" : "unavailable"}`;
    button.disabled = !canUseEtf(etf);
    button.innerHTML = `
      <span class="code-chip">${escapeHtml(etf.code)}</span>
      <span>
        <span class="search-name">${escapeHtml(etf.name)}</span>
        <span class="search-meta">${escapeHtml(listingLabel(etf))} · ${escapeHtml(sourceLabel(etf))} · ${escapeHtml(etf.tags.join(" · "))}</span>
      </span>
      <span class="type-chip ${etf.type === "主動" ? "active" : ""}">${escapeHtml(etf.type)}</span>
    `;
    button.addEventListener("click", () => addEtf(etf.code));
    els.searchResults.appendChild(button);
    }
  }
}

function renderUniverseSummary() {
  const included = REQUESTED_ETF_CODES.filter((code) => getEtf(code));
  const missing = REQUESTED_ETF_CODES.filter((code) => !getEtf(code));
  const listed = included.filter((code) => isListed(getEtf(code))).length;
  const universeSourceLabel = universeApiState.loaded
    ? "ETF universe: API"
    : universeApiState.error
      ? "ETF universe: local fallback"
      : "ETF universe: seed";
  const selected = selectedCodes();
  const listedChips = ETFS.filter(isListed).map((etf) => renderUniverseChip(etf, selected)).join("");
  const unlistedChips = ETFS.filter((etf) => !isListed(etf)).map((etf) => renderUniverseChip(etf, selected)).join("");

  els.universeSummary.innerHTML = `
    <div class="universe-status">
      <strong>指定 ETF ${included.length}/${REQUESTED_ETF_CODES.length} 已納入</strong>
      <span>可搜尋 ${ETFS.length} 檔；同步比對上限 ${COMPARE_LIMIT} 檔</span>
      <span>${escapeHtml(universeSourceLabel)} · 最新資料日 ${escapeHtml(DATA_END_DATE)} · 指定清單已上市 ${listed} 檔</span>
      ${missing.length ? `<span class="missing-note">缺少：${escapeHtml(missing.join("、"))}</span>` : ""}
    </div>
    <div class="universe-chip-section">
      <div class="universe-chip-heading">已上市 ETF</div>
      <div class="universe-chip-row">${listedChips}</div>
    </div>
    <div class="universe-chip-section">
      <div class="universe-chip-heading">未上市 / 募集中 ETF</div>
      <div class="universe-chip-row">${unlistedChips || `<span class="universe-empty">目前沒有未上市 ETF</span>`}</div>
    </div>
  `;
}

function renderUniverseChip(etf, selected) {
  const listed = isListed(etf);
  const isSelected = selected.has(etf.code);
  const usable = canUseEtf(etf);
  const classes = [
    "universe-chip",
    listed ? "listed" : "unlisted",
    isSelected ? "selected" : "",
    usable ? "" : "unavailable",
  ].filter(Boolean).join(" ");
  const actionLabel = !usable ? `${etf.code} 尚未可比對` : isSelected ? `取消鎖定 ${etf.code}` : `鎖定 ${etf.code}`;
  return `
    <button class="${classes}" type="button" data-universe-code="${escapeHtml(etf.code)}" aria-pressed="${isSelected}" title="${escapeHtml(`${actionLabel} · ${listingLabel(etf)}`)}"${usable ? "" : " disabled"}>
      <strong>${escapeHtml(etf.code)}</strong>
      <span>${listed ? "已上市" : "未上市"}</span>
    </button>
  `;
}

function renderOptimizerOptions() {
  const sectors = getAvailableSectors();
  const defaults = ["半導體業", "電腦及週邊設備業", "金融保險業"];

  els.targetSectors.forEach((select, index) => {
    if (!select || select.options?.length) return;
    select.innerHTML = sectors
      .map((sector) => `<option value="${escapeHtml(sector)}">${escapeHtml(sector)}</option>`)
      .join("");
    select.value = defaults[index] && sectors.includes(defaults[index]) ? defaults[index] : sectors[index] || "";
  });
}

function getAvailableSectors() {
  return [...new Set(Object.values(STOCKS).map((stock) => stock.sector))]
    .filter((sector) => sector && sector !== "未分類")
    .sort((a, b) => a.localeCompare(b, "zh-Hant"));
}

async function fetchAllocationOptimize(targets, maxEtfs = Math.min(COMPARE_LIMIT, 6)) {
  const response = await fetch("/api/allocation/optimize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ targets, maxEtfs }),
  });
  if (!response.ok) {
    let message = "Allocation optimize API failed.";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function applyOptimizedRows(rows) {
  if (!Array.isArray(rows)) return [];
  const mapped = [];
  for (const row of rows) {
    const code = String(row.code || "").toUpperCase();
    const allocation = Number(row.allocation || 0);
    if (!code || allocation <= 0 || !getEtf(code)) continue;
    const etf = getEtf(code);
    if (row.source) etf.source = row.source;
    if (row.coverage) etf.coverage = row.coverage;
    if (row.asOf) etf.asOf = row.asOf;
    mapped.push({ code, allocation: Math.max(0.1, Number(allocation.toFixed(1))) });
  }
  return mapped;
}

async function applyAutoAllocation() {
  if (els.autoAllocateBtn.disabled) return;
  els.autoAllocateBtn.disabled = true;
  try {
    const targets = els.targetSectors
      .map((select, index) => ({
        sector: select.value,
        weight: Number(els.targetWeights[index].value || 0),
      }))
      .filter((target) => target.sector && target.weight > 0);

    const total = targets.reduce((sum, target) => sum + target.weight, 0);
    if (!targets.length || total <= 0) {
      els.autoAllocationNotice.textContent = "請至少輸入一個有效板塊比例。";
      return;
    }

    const normalizedTargets = targets.map((target) => ({
      ...target,
      weight: (target.weight / total) * 100,
    }));
    let selected = [];
    let messagePrefix = "API";
    try {
      const optimized = await fetchAllocationOptimize(normalizedTargets, Math.min(COMPARE_LIMIT, 6));
      selected = applyOptimizedRows(optimized.selected);
      if (!selected.length) {
        throw new Error("Allocation optimize API returned no selectable ETF.");
      }
      lastOptimizeSource = "api";
      lastOptimizeError = "";
    } catch (error) {
      selected = optimizeEtfAllocation(normalizedTargets);
      lastOptimizeSource = "local_fallback";
      lastOptimizeError = error.message || "allocation optimize API unavailable";
      messagePrefix = "Fallback";
    }

    if (!selected.length) {
      els.autoAllocationNotice.textContent = "找不到可用 ETF，請調整板塊或比重。";
      return;
    }

    state.selected = selected;
    state.historyEtfCode = selected.find((item) => isListed(getEtf(item.code)))?.code || "";
    state.activeSector = normalizedTargets[0]?.sector || state.activeSector;
    els.autoAllocationNotice.textContent = `${messagePrefix} 已依 ${normalizedTargets
      .map((target) => `${target.sector} ${fmt(target.weight)}`)
      .join("、")} 自動選擇 ${selected.length} 檔 ETF。`;
    renderAll();
  } catch (error) {
    lastOptimizeSource = "local_fallback";
    lastOptimizeError = error.message || "auto allocation failed";
    els.autoAllocationNotice.textContent = `自動配置失敗：${lastOptimizeError}`;
    renderAll();
  } finally {
    els.autoAllocateBtn.disabled = false;
  }
}

function optimizeEtfAllocation(targets) {
  const candidateScores = ETFS.filter(canUseEtf).map((etf) => {
    const vector = getEtfSectorVector(etf);
    const targetScore = targets.reduce((sum, target) => sum + (vector[target.sector] || 0) * target.weight, 0);
    const concentrationPenalty = Math.max(...Object.values(vector), 0) * 0.18;
    return { etf, score: targetScore - concentrationPenalty, vector };
  }).sort((a, b) => b.score - a.score);

  const selectedMap = new Map();
  for (const target of targets) {
    const best = candidateScores
      .filter((item) => (item.vector[target.sector] || 0) > 0)
      .sort((a, b) => (b.vector[target.sector] || 0) - (a.vector[target.sector] || 0))[0];
    if (best) selectedMap.set(best.etf.code, best);
  }

  for (const item of candidateScores) {
    if (selectedMap.size >= Math.min(COMPARE_LIMIT, 6)) break;
    selectedMap.set(item.etf.code, item);
  }

  const chosen = [...selectedMap.values()].slice(0, Math.min(COMPARE_LIMIT, 6));
  const rawWeights = chosen.map((item) => {
    const fit = targets.reduce((sum, target) => sum + (item.vector[target.sector] || 0) * target.weight, 0);
    return Math.max(1, fit);
  });
  const rawTotal = rawWeights.reduce((sum, value) => sum + value, 0) || 1;
  let remaining = 100;

  return chosen.map((item, index) => {
    const allocation = index === chosen.length - 1 ? Number(remaining.toFixed(1)) : Math.round((rawWeights[index] / rawTotal) * 1000) / 10;
    remaining -= allocation;
    return {
      code: item.etf.code,
      allocation: Math.max(0.1, allocation),
    };
  });
}

function getEtfSectorVector(etf) {
  const sectorTotals = {};
  let total = 0;
  for (const [stockCode, weight] of Object.entries(etf.holdings)) {
    const sector = STOCKS[stockCode]?.sector || "未分類";
    sectorTotals[sector] = (sectorTotals[sector] || 0) + weight;
    total += weight;
  }
  if (!total) return sectorTotals;
  for (const sector of Object.keys(sectorTotals)) {
    sectorTotals[sector] = (sectorTotals[sector] / total) * 100;
  }
  return sectorTotals;
}

function renderSelected() {
  els.selectedEtfs.innerHTML = "";
  for (const item of state.selected) {
    const etf = getEtf(item.code);
    if (!etf) continue;

    const row = document.createElement("div");
    row.className = "selected-row";
    const statusText = listingLabel(etf);
    row.innerHTML = `
      <div class="selected-title">
        <span class="code-chip">${escapeHtml(etf.code)}</span>
        <span class="type-chip ${etf.type === "主動" ? "active" : ""}">${escapeHtml(etf.type)}</span>
        <span class="status-chip ${isListed(etf) ? "" : "pending"}">${escapeHtml(statusText)}</span>
        <span class="status-chip ${coverageClass(etf)}">${escapeHtml(coverageLabel(etf))}</span>
        <span class="selected-name">${escapeHtml(etf.name)}</span>
      </div>
      <label class="allocation-input">
        <input type="number" min="0" max="100" step="0.1" value="${item.allocation}" aria-label="${escapeHtml(etf.code)} 資金配比" />
        <span>%</span>
      </label>
      <button class="remove-button" type="button" aria-label="移除 ${escapeHtml(etf.code)}" title="移除">×</button>
    `;

    row.querySelector("input").addEventListener("input", (event) => {
      item.allocation = Number(event.target.value || 0);
      renderAnalytics();
    });
    row.querySelector("button").addEventListener("click", () => removeEtf(etf.code));
    els.selectedEtfs.appendChild(row);
  }
}

function renderAllocation(total) {
  const balanced = Math.abs(total - 100) < 0.05;
  els.allocationTotal.textContent = fmt(total);
  els.allocationBar.style.width = `${Math.min(total, 100)}%`;
  els.allocationBar.style.background = balanced ? "var(--teal)" : total > 100 ? "var(--rose)" : "var(--amber)";
}

function renderMetrics(model) {
  const top = model.exposures[0];
  const sector = model.sectors[0];
  const overlapRows = model.exposures.filter((row) => row.count >= state.overlapMin);

  els.holdingCount.textContent = model.exposures.length;
  els.topExposure.textContent = top ? fmt(top.total) : "0%";
  els.topSector.textContent = sector ? sector.sector.replace("業", "") : "-";
  els.overlapCount.textContent = overlapRows.length;

  const warning = top && top.total > 20;
  els.riskBadge.textContent = warning ? `過度集中警示：${top.name}` : "分散正常";
  els.riskBadge.classList.toggle("warning", Boolean(warning));
}

function renderQualityPanel(model) {
  if (!els.qualityPanel) return;
  const selectedEtfs = state.selected.map((item) => getEtf(item.code)).filter(Boolean);
  const selectedSources = [...new Set(selectedEtfs.map((etf) => sourceLabel(etf)))].join("、") || "-";
  const partialEtfs = selectedEtfs.filter((etf) => etf.coverage && etf.coverage !== "full");
  const seededEtfs = selectedEtfs.filter((etf) => etf.source === "前端種子資料" || etf.source === "模擬投組");
  const unknownRows = model.exposures.filter((row) => row.sector === "未分類");
  const quality = latestPayloadQuality;
  const parsed = quality?.parsedHoldingCount || selectedEtfs.reduce((sum, etf) => sum + Object.keys(etf.holdings || {}).length, 0);
  const declared = quality?.declaredHoldingCount || 0;
  const coverageText = declared ? `${parsed}/${declared} 檔持股已解析` : `${parsed} 檔持股在前端模型`;
  const holdingReadyCount = selectedEtfs.filter((etf) => holdingApiState.loaded.has(etf.code)).length;
  const holdingPendingCount = selectedEtfs.filter((etf) => holdingApiState.pending.has(etf.code)).length;
  const holdingErrorCount = selectedEtfs.filter((etf) => holdingApiState.errors.has(etf.code)).length;
  const holdingStatus = holdingPendingCount
    ? `載入中 ${holdingPendingCount} 檔`
    : holdingErrorCount
      ? `失敗 ${holdingErrorCount} 檔`
      : holdingReadyCount
        ? `已接線 ${holdingReadyCount} 檔`
        : "尚未載入";
  const historyReadyCount = selectedEtfs.filter((etf) => historyApiState.cache.has(historyCacheKey(etf.code, HISTORY_CHANGE_DAYS))).length;
  const comparePositions = buildComparePositions();
  const compareKey = compareCacheKey(comparePositions);
  const compareStatus = compareApiState.pending.has(compareKey)
    ? "載入中"
    : compareApiState.errors.get(compareKey)
      ? `錯誤：${compareApiState.errors.get(compareKey)}`
      : compareApiState.cache.has(compareKey)
        ? "已接線"
        : "本機 fallback";
  const optimizeStatus = lastOptimizeSource === "api"
    ? "已接線"
    : lastOptimizeSource === "local_fallback"
      ? `fallback：${lastOptimizeError}`
      : "未執行";
  const historyStatus = historyReadyCount ? `已載入 ${historyReadyCount} 檔` : "尚未載入";
  const statusText =
    partialEtfs.length || seededEtfs.length || unknownRows.length
      ? "MVP 資料限制已標示"
      : "資料檢查正常";
  const qualityNotes = [];
  if (partialEtfs.length) qualityNotes.push(`${partialEtfs.map((etf) => etf.code).join("、")} 為公開頁部分持股`);
  if (seededEtfs.length) qualityNotes.push(`${seededEtfs.map((etf) => etf.code).join("、")} 尚未刷新成 API 資料`);
  if (unknownRows.length) qualityNotes.push(`${unknownRows.length} 檔股票缺少正式產業分類`);
  const noteText = [statusText, ...qualityNotes].join("；") + "。";

  els.qualityPanel.innerHTML = `
    <div class="quality-item">
      <span>目前來源</span>
      <strong>${escapeHtml(selectedSources)}</strong>
    </div>
    <div class="quality-item">
      <span>持股完整度</span>
      <strong>${escapeHtml(coverageText)}</strong>
    </div>
    <div class="quality-item">
      <span>未分類股票</span>
      <strong>${unknownRows.length}</strong>
    </div>
    <div class="quality-item">
      <span>歷史資料</span>
      <strong>${escapeHtml(historyStatus)}</strong>
    </div>
    <div class="quality-item">
      <span>Holdings API</span>
      <strong>${escapeHtml(holdingStatus)}</strong>
    </div>
    <div class="quality-item">
      <span>Compare API</span>
      <strong>${escapeHtml(compareStatus)}</strong>
    </div>
    <div class="quality-item">
      <span>Optimize API</span>
      <strong>${escapeHtml(optimizeStatus)}</strong>
    </div>
    <p class="quality-note">${escapeHtml(noteText)}</p>
  `;
}

function renderExposureChart(exposures) {
  els.exposureChart.innerHTML = "";
  if (!exposures.length) {
    els.exposureChart.innerHTML = `<div class="empty-state">尚未選取 ETF</div>`;
    return;
  }

  const topRows = exposures.slice(0, 10);
  const max = Math.max(...topRows.map((row) => row.total), 1);

  for (const row of topRows) {
    const div = document.createElement("div");
    div.className = "bar-row";
    const width = Math.max(2, (row.total / max) * 100);
    const warning = row.total > 20;
    div.innerHTML = `
      <div class="stock-label">
        <strong>${escapeHtml(row.name)}</strong>
        <span>${escapeHtml(row.code)} · ${escapeHtml(row.sector)}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill ${warning ? "warning" : ""}" style="width:${width}%"></div>
      </div>
      <div class="bar-value">${fmt(row.total)}</div>
    `;
    els.exposureChart.appendChild(div);
  }
}

function renderSector(model) {
  els.sectorViz.className = `sector-viz ${state.sectorView}`;
  els.sectorViz.innerHTML = "";

  if (!model.sectors.length) {
    state.activeSector = "";
    els.sectorViz.innerHTML = `<div class="empty-state">尚未選取 ETF</div>`;
    renderSectorDetail([]);
    return;
  }

  if (!model.sectors.some((item) => item.sector === state.activeSector)) {
    state.activeSector = model.sectors[0].sector;
  }

  if (state.sectorView === "donut") {
    renderDonut(model.sectors);
  } else {
    renderTreemap(model.sectors);
  }

  renderSectorDetail(model.exposures);
}

function renderTreemap(sectors) {
  const total = sectors.reduce((sum, item) => sum + item.total, 0) || 1;
  for (const item of sectors.slice(0, 10)) {
    const share = (item.total / total) * 100;
    const tile = document.createElement("button");
    const colSpan = Math.min(12, Math.max(3, Math.round(share / 8)));
    const rowSpan = Math.max(1, Math.round(share / 16));
    tile.type = "button";
    tile.className = `sector-tile ${item.sector === state.activeSector ? "active" : ""}`;
    tile.style.gridColumn = `span ${colSpan}`;
    tile.style.gridRow = `span ${rowSpan}`;
    tile.style.background = SECTOR_COLORS[item.sector] || "#657270";
    tile.innerHTML = `<strong>${escapeHtml(item.sector)}</strong><span>${fmt(item.total)}</span>`;
    tile.addEventListener("click", () => {
      state.activeSector = item.sector;
      renderAnalytics();
    });
    els.sectorViz.appendChild(tile);
  }
}

function renderDonut(sectors) {
  let cursor = 0;
  const total = sectors.reduce((sum, item) => sum + item.total, 0) || 1;
  const segments = sectors.map((item) => {
    const start = cursor;
    const end = cursor + (item.total / total) * 100;
    cursor = end;
    const color = SECTOR_COLORS[item.sector] || "#657270";
    return `${color} ${start}% ${end}%`;
  });

  const wrap = document.createElement("div");
  wrap.className = "donut-wrap";
  wrap.innerHTML = `
    <div class="donut-chart" style="background: conic-gradient(${segments.join(",")})"></div>
    <div class="sector-legend"></div>
  `;

  const legend = wrap.querySelector(".sector-legend");
  for (const item of sectors.slice(0, 10)) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `legend-row ${item.sector === state.activeSector ? "active" : ""}`;
    row.innerHTML = `
      <span class="legend-dot" style="background:${SECTOR_COLORS[item.sector] || "#657270"}"></span>
      <span class="legend-name">${escapeHtml(item.sector)}</span>
      <strong>${fmt(item.total)}</strong>
    `;
    row.addEventListener("click", () => {
      state.activeSector = item.sector;
      renderAnalytics();
    });
    legend.appendChild(row);
  }

  els.sectorViz.appendChild(wrap);
}

function renderSectorDetail(exposures) {
  if (!state.activeSector) {
    els.sectorDetail.innerHTML = "";
    return;
  }

  const rows = exposures.filter((row) => row.sector === state.activeSector).slice(0, 12);
  if (!rows.length) {
    els.sectorDetail.innerHTML = `<div class="empty-state small">此產業目前沒有合併持股</div>`;
    return;
  }

  const stockRows = rows
    .map((row) => {
      const etfTags = Object.entries(row.byEtfContribution)
        .sort((a, b) => b[1] - a[1])
        .map(([code, contribution]) => `<span class="mini-chip">${escapeHtml(code)} ${fmt(contribution)}</span>`)
        .join("");
      return `
        <div class="sector-stock-row">
          <div>
            <strong>${escapeHtml(row.name)}</strong>
            <span>${escapeHtml(row.code)}</span>
          </div>
          <div class="sector-stock-etfs">${etfTags}</div>
          <strong>${fmt(row.total)}</strong>
        </div>
      `;
    })
    .join("");

  els.sectorDetail.innerHTML = `
    <div class="sector-detail-head">
      <span>${escapeHtml(state.activeSector)}</span>
      <strong>${rows.length} 檔股票</strong>
    </div>
    <div class="sector-stock-list">${stockRows}</div>
  `;
}

function renderHeatmap(exposures) {
  const maxSelected = Math.max(1, state.selected.length);
  els.overlapSlider.max = String(maxSelected);
  if (state.overlapMin > maxSelected) state.overlapMin = maxSelected;
  els.overlapSlider.value = String(state.overlapMin);
  els.overlapValue.textContent = String(state.overlapMin);

  const rows = exposures
    .filter((row) => row.count >= state.overlapMin)
    .sort((a, b) => b.count - a.count || b.total - a.total)
    .slice(0, 18);

  els.heatmap.innerHTML = "";
  if (!rows.length || !state.selected.length) {
    els.heatmap.innerHTML = `<div class="empty-state">沒有符合門檻的共同持股</div>`;
    return;
  }

  const maxWeight = Math.max(
    ...rows.flatMap((row) => state.selected.map((item) => row.byEtf[item.code] || 0)),
    1,
  );

  const grid = document.createElement("div");
  grid.className = "heatmap-grid";
  grid.style.gridTemplateColumns = `190px repeat(${state.selected.length}, 72px)`;
  grid.appendChild(makeCell("heatmap-head", ""));

  for (const item of state.selected) {
    grid.appendChild(makeCell("heatmap-head", item.code));
  }

  for (const row of rows) {
    const label = makeCell("heatmap-label", `${escapeHtml(row.name)}<span>${escapeHtml(row.code)}</span>`);
    grid.appendChild(label);

    for (const item of state.selected) {
      const weight = row.byEtf[item.code] || 0;
      const cell = makeCell("heatmap-cell", weight ? fmt(weight) : "-");
      const alpha = weight ? Math.min(0.92, 0.12 + (weight / maxWeight) * 0.8) : 0.04;
      cell.style.background = weight ? `rgba(8, 127, 115, ${alpha})` : "rgba(101, 114, 112, 0.08)";
      cell.style.color = alpha > 0.43 ? "#fff" : "var(--ink)";
      grid.appendChild(cell);
    }
  }

  els.heatmap.appendChild(grid);
}

function makeCell(className, html) {
  const cell = document.createElement("div");
  cell.className = className;
  cell.innerHTML = html;
  return cell;
}

function historyCacheKey(code, days, quality = HISTORY_QUALITY_MODE) {
  return `${code}:${days}:${quality}`;
}

async function fetchHistoryRows(code, days = HISTORY_CHANGE_DAYS, quality = HISTORY_QUALITY_MODE) {
  const endpoint = `/api/etfs/${encodeURIComponent(code)}/holdings/changes?days=${days}&quality=${encodeURIComponent(quality)}`;
  const response = await fetch(endpoint, { cache: "no-store" });
  if (!response.ok) {
    let message = "每日持股 API 回應失敗";
    try {
      const payload = await response.json();
      message = payload.message || payload.error || message;
    } catch (error) {
      // Keep generic message when response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function ensureHistoryRows(code, days = HISTORY_CHANGE_DAYS, quality = HISTORY_QUALITY_MODE) {
  const key = historyCacheKey(code, days, quality);
  if (historyApiState.cache.has(key) || historyApiState.pending.has(key)) return;
  historyApiState.pending.add(key);
  fetchHistoryRows(code, days, quality)
    .then((payload) => {
      historyApiState.cache.set(key, payload);
    })
    .catch((error) => {
      historyApiState.cache.set(key, { rows: [], message: error.message || "每日持股 API 呼叫失敗。" });
    })
    .finally(() => {
      historyApiState.pending.delete(key);
      renderHistory();
    });
}

function renderHistory() {
  const selectedEtfs = state.selected.map((item) => getEtf(item.code)).filter(Boolean);
  const listedEtfs = selectedEtfs.filter(isListed);
  const availableCodes = new Set(selectedEtfs.map((etf) => etf.code));

  if (!availableCodes.has(state.historyEtfCode) || !isListed(getEtf(state.historyEtfCode))) {
    state.historyEtfCode = listedEtfs[0]?.code || "";
  }

  els.historyEtfSelect.innerHTML = "";
  for (const etf of selectedEtfs) {
    const option = document.createElement("option");
    option.value = etf.code;
    option.textContent = `${etf.code} ${etf.name}${isListed(etf) ? "" : "（尚未上市）"}`;
    option.disabled = !isListed(etf);
    option.selected = etf.code === state.historyEtfCode;
    els.historyEtfSelect.appendChild(option);
  }
  els.historyEtfSelect.disabled = !listedEtfs.length;

  const etf = getEtf(state.historyEtfCode);
  if (!etf) {
    els.historySummary.innerHTML = `<div class="empty-state small">已選 ETF 中沒有可用的上市日資料</div>`;
    els.historyChart.innerHTML = "";
    els.historyTable.innerHTML = "";
    return;
  }

  const cacheKey = historyCacheKey(etf.code, HISTORY_CHANGE_DAYS);
  const cached = historyApiState.cache.get(cacheKey);
  if (!cached) {
    ensureHistoryRows(etf.code, HISTORY_CHANGE_DAYS);
    els.historySummary.innerHTML = `
      <div class="empty-state small">正在載入 ${escapeHtml(etf.code)} 的每日持股快照資料…</div>
    `;
    els.historyChart.innerHTML = "";
    els.historyTable.innerHTML = "";
    return;
  }

  const rows = Array.isArray(cached.rows) ? cached.rows : [];
  if (!rows.length) {
    const message = cached.message || `${etf.code} 的歷史快照不足，暫時無法計算變化。`;
    els.historySummary.innerHTML = `<div class="empty-state small">${escapeHtml(message)}</div>`;
    els.historyChart.innerHTML = "";
    els.historyTable.innerHTML = "";
    return;
  }

  const newest = rows.at(-1);
  const monthLabel = rows.length >= 20 ? "近一個月" : `上市後 ${rows.length} 個交易日`;
  els.historySummary.innerHTML = `
    <div class="history-stat">
      <span>資料區間</span>
      <strong>${escapeHtml(rows[0].date)} - ${escapeHtml(newest.date)}</strong>
    </div>
    <div class="history-stat">
      <span>可用日數</span>
      <strong>${monthLabel}</strong>
    </div>
    <div class="history-stat">
      <span>最新調整幅度</span>
      <strong>${fmt(newest.turnover)}</strong>
    </div>
  `;

  renderHistoryChart(rows);
  renderHistoryTable(rows);
}

function renderHistoryChart(rows) {
  const chartRows = rows.slice(-22);
  const max = Math.max(...chartRows.map((row) => row.turnover), 0.1);
  els.historyChart.innerHTML = chartRows
    .map((row) => {
      const height = Math.max(6, (row.turnover / max) * 100);
      return `
        <div class="history-bar-wrap" title="${escapeHtml(row.date)} ${fmt(row.turnover)}">
          <span class="history-bar" style="height:${height}%"></span>
        </div>
      `;
    })
    .join("");
}

function renderHistoryTable(rows) {
  const displayRows = rows
    .slice()
    .reverse()
    .slice(0, 22)
    .map((row) => {
      const up = formatMoverList(row.increases);
      const down = formatMoverList(row.decreases);
      const added = row.added.length ? row.added.map((item) => item.name).join("、") : "-";
      const removed = row.removed.length ? row.removed.map((item) => item.name).join("、") : "-";
      return `
        <div class="history-table-row">
          <span>${escapeHtml(row.date)}</span>
          <div class="history-mover-list">${up}</div>
          <div class="history-mover-list">${down}</div>
          <span>${escapeHtml(added)}</span>
          <span>${escapeHtml(removed)}</span>
          <strong>${fmt(row.turnover)}</strong>
        </div>
      `;
    })
    .join("");

  els.historyTable.innerHTML = `
    <div class="history-table-head">
      <span>日期</span>
      <span>增持前三名</span>
      <span>減持前三名</span>
      <span>新增</span>
      <span>移除</span>
      <span>調整幅度</span>
    </div>
    ${displayRows}
  `;
}

function formatMoverList(items) {
  if (!items.length) return "-";
  return items
    .map((item, index) => {
      const amount = item.amountChange !== undefined ? item.amountChange : item.amount;
      const lotsRaw = item.lotsChange !== undefined ? item.lotsChange : item.lots;
      const lots = item.lotUnit === "股" ? Math.round(lotsRaw) : lotsRaw;
      return `
        <div class="history-mover-line">
          <strong>${index + 1}. ${escapeHtml(item.name)}</strong>
          <span>${signedFmt(item.diff)} · ${escapeHtml(formatMoney(Math.abs(amount || 0)))} · ${escapeHtml(formatLots(lots || 0, item.lotUnit || "張"))}</span>
        </div>
      `;
    })
    .join("");
}

function formatMoney(value) {
  if (value >= 100000000) return `${(value / 100000000).toFixed(2)} 億`;
  if (value >= 10000) return `${Math.round(value / 10000).toLocaleString("zh-TW")} 萬`;
  return `${Math.round(value).toLocaleString("zh-TW")} 元`;
}

function formatLots(value, unit) {
  const digits = unit === "股" ? 0 : 1;
  return `${Number(value).toLocaleString("zh-TW", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  })} ${unit}`;
}

function getLatestTradingDate(now = new Date()) {
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const hour = now.getHours();
  if (hour < 18) date.setDate(date.getDate() - 1);
  while (date.getDay() === 0 || date.getDay() === 6) {
    date.setDate(date.getDate() - 1);
  }
  return formatDate(date);
}

function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function resolvePortfolioModel() {
  const localModel = computePortfolio();
  const positions = buildComparePositions();
  if (!positions.length) return localModel;
  const key = compareCacheKey(positions);
  const cached = compareApiState.cache.get(key);
  if (!cached) return localModel;
  return {
    totalAllocation: Number(cached.totalAllocation ?? localModel.totalAllocation),
    exposures: Array.isArray(cached.exposures) ? cached.exposures : localModel.exposures,
    sectors: Array.isArray(cached.sectors) ? cached.sectors : localModel.sectors,
  };
}

function exportExposureCsv() {
  const model = resolvePortfolioModel();
  if (!model.exposures.length) {
    setNotice("目前沒有可匯出的曝險資料。");
    return;
  }
  const etfCodes = state.selected.map((item) => item.code);
  const header = ["code", "name", "sector", "total_exposure_pct", "overlap_count", ...etfCodes];
  const rows = [header];
  for (const row of model.exposures) {
    rows.push([
      row.code,
      row.name,
      row.sector,
      Number(row.total || 0).toFixed(4),
      row.count,
      ...etfCodes.map((code) => Number(row.byEtf?.[code] || 0).toFixed(4)),
    ]);
  }
  downloadCsv(`etf-exposure-${timestampLabel()}.csv`, rows);
  setNotice(`已匯出 ${rows.length - 1} 筆曝險資料。`);
}

function exportExposurePdf() {
  const model = resolvePortfolioModel();
  if (!model.exposures.length) {
    setNotice("目前沒有可匯出的曝險資料。");
    return;
  }
  const selectedRows = state.selected.map((item) => `${item.code} ${item.allocation}%`).join("、");
  const topSectors = model.sectors
    .slice(0, 12)
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.sector)}</td>
          <td style="text-align:right;">${Number(row.total || 0).toFixed(4)}%</td>
        </tr>`,
    )
    .join("");
  const watchRows = watchlistApiState.rows
    .slice(0, 20)
    .map((row) => {
      const status = watchlistApiState.statuses.get(row.code);
      return `
        <tr>
          <td>${escapeHtml(row.code)}</td>
          <td>${escapeHtml(watchStatusLabel(status))}</td>
          <td>${escapeHtml(status?.asOf || "-")}</td>
          <td>${escapeHtml(row.note || "-")}</td>
        </tr>`;
    })
    .join("");
  const topRows = model.exposures
    .slice(0, 40)
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.code)}</td>
          <td>${escapeHtml(row.name)}</td>
          <td>${escapeHtml(row.sector)}</td>
          <td style="text-align:right;">${Number(row.total || 0).toFixed(4)}%</td>
          <td style="text-align:right;">${row.count}</td>
        </tr>`,
    )
    .join("");
  const html = `<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <title>ETF Exposure Report</title>
  <style>
    body { font-family: Arial, "Noto Sans TC", sans-serif; margin: 24px; color: #17221f; }
    h1 { margin: 0 0 10px; font-size: 24px; }
    h2 { margin: 18px 0 8px; font-size: 16px; }
    p { margin: 6px 0; font-size: 13px; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }
    th, td { border: 1px solid #cfd8d5; padding: 6px 8px; }
    th { background: #eef3f1; text-align: left; }
    .meta-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 12px; margin: 8px 0 14px; }
    .meta-key { color: #5f6f6a; font-weight: 700; }
  </style>
</head>
<body>
  <h1>ETF True Exposure Report</h1>
  <div class="meta-grid">
    <div><span class="meta-key">匯出時間：</span>${escapeHtml(new Date().toLocaleString("zh-TW"))}</div>
    <div><span class="meta-key">最新資料日：</span>${escapeHtml(DATA_END_DATE)}</div>
    <div><span class="meta-key">組合：</span>${escapeHtml(selectedRows || "-")}</div>
    <div><span class="meta-key">資料狀態：</span>${escapeHtml(dataRefreshState)}</div>
  </div>
  <h2>產業分佈</h2>
  <table>
    <thead>
      <tr><th>Sector</th><th>Total Exposure</th></tr>
    </thead>
    <tbody>${topSectors || '<tr><td colspan="2">-</td></tr>'}</tbody>
  </table>
  <h2>底層持股曝險</h2>
  <table>
    <thead>
      <tr>
        <th>Code</th>
        <th>Name</th>
        <th>Sector</th>
        <th>Total Exposure</th>
        <th>Overlap Count</th>
      </tr>
    </thead>
    <tbody>
      ${topRows}
    </tbody>
  </table>
  <h2>追蹤清單狀態</h2>
  <table>
    <thead>
      <tr>
        <th>Code</th>
        <th>Status</th>
        <th>As Of</th>
        <th>Note</th>
      </tr>
    </thead>
    <tbody>${watchRows || '<tr><td colspan="4">尚未加入追蹤清單</td></tr>'}</tbody>
  </table>
</body>
</html>`;

  const reportWindow = window.open("", "_blank", "noopener,noreferrer");
  if (!reportWindow) {
    setNotice("無法開啟 PDF 視窗，請確認瀏覽器未封鎖彈窗。");
    return;
  }
  reportWindow.document.open();
  reportWindow.document.write(html);
  reportWindow.document.close();
  setTimeout(() => {
    reportWindow.focus();
    reportWindow.print();
  }, 120);
  setNotice("已開啟 PDF 匯出視窗。");
}

function renderAnalytics() {
  ensureSelectedHoldings();
  ensureCompareModel();
  const model = resolvePortfolioModel();
  renderAllocation(model.totalAllocation);
  renderMetrics(model);
  renderExposureChart(model.exposures);
  renderSector(model);
  renderHeatmap(model.exposures);
  renderHistory();
  renderQualityPanel(model);
}

function renderDataStatus() {
  const stateLabels = {
    manual: "使用快取資料",
    refreshing: "刷新中",
    ready: "已接資料 API",
    limited: "資料部分可用",
    failed: "未接資料 API",
  };
  els.updateStatusPill.className = `status-pill ${dataRefreshState}`;
  els.updateStatusPill.innerHTML = `<span></span>${stateLabels[dataRefreshState] || "資料狀態"}`;
  els.lastRefreshText.textContent = lastRefreshAt
    ? `最新資料日 ${DATA_END_DATE} · ${lastRefreshAt}`
    : `最新資料日 ${DATA_END_DATE}`;
  els.refreshDataBtn.disabled = dataRefreshState === "refreshing";
  els.refreshDataBtn.textContent = dataRefreshState === "refreshing" ? "刷新中..." : "刷新資料";
  if (els.autoSyncToggleBtn) {
    els.autoSyncToggleBtn.textContent = `自動刷新：${autoSyncState.enabled ? "開" : "關"}`;
    els.autoSyncToggleBtn.disabled = autoSyncState.busy;
    els.autoSyncToggleBtn.classList.toggle("danger", autoSyncState.enabled);
    if (autoSyncState.lastRunAt) {
      els.autoSyncToggleBtn.title = `上次背景同步 ${autoSyncState.lastRunAt}`;
    } else {
      els.autoSyncToggleBtn.title = "背景自動刷新";
    }
  }
}

function renderAll() {
  renderDataStatus();
  renderOptimizerOptions();
  renderSearch();
  renderSelected();
  renderPortfolioManager();
  renderWatchlistManager();
  renderAnalytics();
}

function addEtf(code) {
  if (state.selected.length >= COMPARE_LIMIT || selectedCodes().has(code)) return;
  const etf = getEtf(code);
  if (!canUseEtf(etf)) {
    setNotice(`${code} 尚未有可用的正式持股資料，暫不納入比對。`);
    return;
  }
  const suggested = state.selected.length ? Math.round(100 / (state.selected.length + 1)) : 100;
  state.selected.push({ code, allocation: suggested });
  state.query = "";
  els.search.value = "";
  renderAll();
}

function removeEtf(code) {
  state.selected = state.selected.filter((item) => item.code !== code);
  renderAll();
}

function equalizeAllocations() {
  if (!state.selected.length) return;
  const base = Math.floor(1000 / state.selected.length) / 10;
  let remaining = 100;
  state.selected.forEach((item, index) => {
    item.allocation = index === state.selected.length - 1 ? Number(remaining.toFixed(1)) : base;
    remaining -= base;
  });
  renderAll();
}

async function refreshLatestData() {
  dataRefreshState = "refreshing";
  dataRefreshMessage = "正在呼叫資料 API 抓取最新持股。";
  setNotice(dataRefreshMessage);
  renderDataStatus();

  try {
    const payload = await fetchLatestPayload();
    applyLatestPayload(payload);
    DATA_END_DATE = payload.asOf || payload.date || getLatestTradingDate();
    const partialCount = payload.etfs?.filter((etf) => etf.coverage && etf.coverage !== "full").length || 0;
    const errorCount = payload.errors?.length || 0;
    const warnings = [
      partialCount ? `${partialCount} 檔來源為分頁資料` : "",
      errorCount ? `${errorCount} 檔暫無法取得持股` : "",
    ].filter(Boolean);
    dataRefreshState = warnings.length ? "limited" : "ready";
    dataRefreshMessage = `已從本機資料 API 抓取 ETF 持股並重新計算${warnings.length ? `；${warnings.join("、")}。完整正式資料仍需接官方 PCF/TWSE adapter。` : "。"}`;
  } catch (error) {
    DATA_END_DATE = getLatestTradingDate();
    dataRefreshState = "failed";
    dataRefreshMessage = `資料 API 呼叫失敗：${error.message || "請確認 server.py 已啟動且資料來源可連線。"}`;
  }

  lastRefreshAt = new Date().toLocaleTimeString("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
  });
  setNotice(dataRefreshMessage);
  renderAll();
}

async function performBackgroundSync() {
  if (!autoSyncState.enabled || autoSyncState.busy) return;
  if (document.hidden) return;
  autoSyncState.busy = true;
  renderDataStatus();
  try {
    await refreshLatestData();
    await refreshWatchStatuses();
  } catch (error) {
    setNotice(`背景同步失敗：${error.message || "未知錯誤"}`);
  } finally {
    autoSyncState.lastRunAt = new Date().toLocaleTimeString("zh-TW", {
      hour: "2-digit",
      minute: "2-digit",
    });
    autoSyncState.busy = false;
    renderDataStatus();
  }
}

function setAutoSyncEnabled(enabled) {
  autoSyncState.enabled = Boolean(enabled);
  if (autoSyncState.timerId) {
    clearInterval(autoSyncState.timerId);
    autoSyncState.timerId = null;
  }
  if (autoSyncState.enabled) {
    autoSyncState.timerId = window.setInterval(() => {
      void performBackgroundSync();
    }, autoSyncState.intervalMs);
    setNotice(`已啟用背景同步（每 ${Math.round(autoSyncState.intervalMs / 60000)} 分鐘）。`);
  } else {
    setNotice("已關閉背景同步。");
  }
  renderDataStatus();
}

function loadAutoSyncPreference() {
  try {
    return window.localStorage.getItem(AUTO_SYNC_STORAGE_KEY) === "1";
  } catch (error) {
    return false;
  }
}

function saveAutoSyncPreference(enabled) {
  try {
    window.localStorage.setItem(AUTO_SYNC_STORAGE_KEY, enabled ? "1" : "0");
  } catch (error) {
    // Ignore storage failures (private mode / storage blocked).
  }
}

function setAutoSyncEnabled(enabled, options = {}) {
  const announce = options.announce !== false;
  const persist = options.persist !== false;
  autoSyncState.enabled = Boolean(enabled);
  if (autoSyncState.timerId) {
    clearInterval(autoSyncState.timerId);
    autoSyncState.timerId = null;
  }
  if (persist) saveAutoSyncPreference(autoSyncState.enabled);
  if (autoSyncState.enabled) {
    autoSyncState.timerId = window.setInterval(() => {
      void performBackgroundSync();
    }, autoSyncState.intervalMs);
    if (announce) {
      setNotice(`已啟用背景同步（每 ${Math.round(autoSyncState.intervalMs / 60000)} 分鐘）。`);
    }
  } else if (announce) {
    setNotice("已關閉背景同步。");
  }
  renderDataStatus();
}

function toggleAutoSync() {
  setAutoSyncEnabled(!autoSyncState.enabled);
}

async function fetchLatestPayload() {
  const requestedCodes = (state.selected.length ? state.selected.map((item) => item.code) : REQUESTED_ETF_CODES).join(",");
  const timestamp = Date.now();
  const endpoint = `/api/etfs/latest?codes=${encodeURIComponent(requestedCodes)}&ts=${timestamp}`;
  const response = await fetch(endpoint, { cache: "no-store" });

  if (!response.ok) {
    let message = "資料 API 回應失敗";
    try {
      const errorPayload = await response.json();
      message = errorPayload.message || errorPayload.error || message;
    } catch (error) {
      // Keep the generic message if the API did not return JSON.
    }
    throw new Error(message);
  }

  const payload = await response.json();
  return {
    ...payload,
    __source: "api",
  };
}

function applyLatestPayload(payload) {
  if (!payload?.etfs?.length) return;
  latestPayloadQuality = payload.dataQuality || summarizePayloadQuality(payload);
  for (const incoming of payload.etfs) {
    const etf = getEtf(incoming.code);
    if (!etf) continue;
    historyApiState.cache.delete(historyCacheKey(incoming.code, HISTORY_CHANGE_DAYS));
    holdingApiState.loaded.add(incoming.code);
    holdingApiState.errors.delete(incoming.code);
    mergeHoldingDetails(incoming.holdingDetails || []);
    if (incoming.holdings) etf.holdings = incoming.holdings;
    if (incoming.holdingDetails) etf.holdingDetails = incoming.holdingDetails;
    if (incoming.coverage) etf.coverage = incoming.coverage;
    if (incoming.declaredHoldingCount !== undefined) etf.declaredHoldingCount = incoming.declaredHoldingCount;
    if (incoming.parsedHoldingCount !== undefined) etf.parsedHoldingCount = incoming.parsedHoldingCount;
    if (incoming.status) etf.status = incoming.status;
    if (incoming.listedDate !== undefined) etf.listedDate = incoming.listedDate;
    if (incoming.expectedListingDate !== undefined) etf.expectedListingDate = incoming.expectedListingDate;
    if (incoming.source) etf.source = incoming.source;
  }
}

function mergeHoldingDetails(details) {
  for (const detail of details) {
    if (!detail?.code) continue;
    const existing = STOCKS[detail.code];
    if (existing) {
      if (!existing.name && detail.name) existing.name = detail.name;
      continue;
    }
    STOCKS[detail.code] = {
      name: detail.name || detail.code,
      sector: "未分類",
    };
  }
}

function summarizePayloadQuality(payload) {
  const etfs = payload.etfs || [];
  const declaredHoldingCount = etfs.reduce((sum, etf) => sum + Number(etf.declaredHoldingCount || 0), 0);
  const parsedHoldingCount = etfs.reduce((sum, etf) => sum + Number(etf.parsedHoldingCount || Object.keys(etf.holdings || {}).length || 0), 0);
  const partialCodes = etfs
    .filter((etf) => etf.coverage && etf.coverage !== "full")
    .map((etf) => etf.code);
  return {
    status: partialCodes.length || payload.errors?.length ? "partial" : "complete",
    declaredHoldingCount,
    parsedHoldingCount,
    partialCodes,
    errorCount: payload.errors?.length || 0,
  };
}

els.search.addEventListener("input", (event) => {
  state.query = event.target.value;
  renderSearch();
});

els.equalizeBtn.addEventListener("click", equalizeAllocations);

els.autoAllocateBtn.addEventListener("click", applyAutoAllocation);

els.refreshDataBtn.addEventListener("click", refreshLatestData);
els.autoSyncToggleBtn?.addEventListener("click", toggleAutoSync);

els.exportExposureCsvBtn?.addEventListener("click", exportExposureCsv);
els.exportExposurePdfBtn?.addEventListener("click", exportExposurePdf);

els.savePortfolioBtn?.addEventListener("click", () => {
  void saveCurrentPortfolio();
});

els.loadPortfolioBtn?.addEventListener("click", () => {
  void loadSelectedPortfolio();
});

els.deletePortfolioBtn?.addEventListener("click", () => {
  void deleteSelectedPortfolio();
});

els.portfolioSelect?.addEventListener("change", (event) => {
  portfolioApiState.selectedId = event.target.value;
  const row = findPortfolioRow(portfolioApiState.selectedId);
  if (row) els.portfolioNameInput.value = row.name;
  renderPortfolioManager();
});

els.addWatchlistBtn?.addEventListener("click", () => {
  void addWatchlist();
});

els.refreshWatchStatusBtn?.addEventListener("click", () => {
  void refreshWatchStatuses();
});

els.watchlistNoteInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    void addWatchlist();
  }
});

els.watchlistList?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-watchlist-delete]");
  if (!button) return;
  const code = String(button.dataset.watchlistDelete || "").toUpperCase();
  if (!code) return;
  void removeWatchlist(code);
});

els.universeSummary.addEventListener("click", (event) => {
  const button = event.target.closest("[data-universe-code]");
  if (!button) return;
  const code = button.dataset.universeCode;
  if (selectedCodes().has(code)) {
    removeEtf(code);
    setNotice(`已取消鎖定 ${code}。`);
    return;
  }
  if (state.selected.length >= COMPARE_LIMIT) {
    setNotice(`已達 ${COMPARE_LIMIT} 檔同步比對上限，請先移除一檔 ETF。`);
    return;
  }
  addEtf(code);
  setNotice(`已鎖定 ${code} 到比對清單。`);
});

els.overlapSlider.addEventListener("input", (event) => {
  state.overlapMin = Number(event.target.value);
  renderAnalytics();
});

els.historyEtfSelect.addEventListener("change", (event) => {
  state.historyEtfCode = event.target.value;
  renderHistory();
});

document.querySelectorAll("[data-sector-view]").forEach((button) => {
  button.addEventListener("click", () => {
    state.sectorView = button.dataset.sectorView;
    document.querySelectorAll("[data-sector-view]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    renderAnalytics();
  });
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && autoSyncState.enabled) {
    void performBackgroundSync();
  }
});

async function bootstrapApiData() {
  await loadUniverseFromApi();
  await loadPortfolioList();
  await loadWatchlist();
  if (universeApiState.error) {
    setNotice(`${selectorNoticeMessage} (ETF universe API unavailable; using local seed list.)`);
  }
  if (portfolioApiState.error) {
    setPortfolioNotice(`組合 API 不可用：${portfolioApiState.error}`);
  }
  if (watchlistApiState.error) {
    setWatchlistNotice(`追蹤清單 API 不可用：${watchlistApiState.error}`);
  }
  renderAll();
}

setAutoSyncEnabled(loadAutoSyncPreference(), { announce: false, persist: false });
renderAll();
void bootstrapApiData();
