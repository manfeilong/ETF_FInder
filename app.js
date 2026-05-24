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
let DATA_END_DATE = getLatestTradingDate();
let dataRefreshState = "manual";
let dataRefreshMessage = "尚未接上後端自動日更；可按刷新資料嘗試抓取最新檔案。";
let lastRefreshAt = "";

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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "投信 PCF",
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
    source: "公開 API",
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
    source: "公開 API",
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
    source: "公開 API",
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
    source: "公開 API",
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
    source: "公開 API",
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
};

const els = {
  updateStatusPill: document.getElementById("updateStatusPill"),
  refreshDataBtn: document.getElementById("refreshDataBtn"),
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
  holdingCount: document.getElementById("holdingCount"),
  topExposure: document.getElementById("topExposure"),
  topSector: document.getElementById("topSector"),
  overlapCount: document.getElementById("overlapCount"),
  riskBadge: document.getElementById("riskBadge"),
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

function getEtf(code) {
  return ETFS.find((etf) => etf.code === code);
}

function isListed(etf) {
  return etf?.status === "listed" && etf.listedDate && etf.listedDate <= DATA_END_DATE;
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
          sector: stock?.sector || "其他",
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
  els.search.disabled = atLimit;
  els.search.placeholder = atLimit ? "已達最大比對數量" : "代號、關鍵字、產業主題";
  els.limitCounter.textContent = `${state.selected.length} / ${COMPARE_LIMIT}`;
  els.notice.textContent = atLimit ? `已達 ${COMPARE_LIMIT} 檔同步比對上限；ETF universe 仍可透過移除後重新選取。` : "";
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
    button.className = "search-result";
    button.innerHTML = `
      <span class="code-chip">${escapeHtml(etf.code)}</span>
      <span>
        <span class="search-name">${escapeHtml(etf.name)}</span>
        <span class="search-meta">${escapeHtml(listingLabel(etf))} · ${escapeHtml(etf.tags.join(" · "))}</span>
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
  const selected = selectedCodes();
  const listedChips = ETFS.filter(isListed).map((etf) => renderUniverseChip(etf, selected)).join("");
  const unlistedChips = ETFS.filter((etf) => !isListed(etf)).map((etf) => renderUniverseChip(etf, selected)).join("");

  els.universeSummary.innerHTML = `
    <div class="universe-status">
      <strong>指定 ETF ${included.length}/${REQUESTED_ETF_CODES.length} 已納入</strong>
      <span>可搜尋 ${ETFS.length} 檔；同步比對上限 ${COMPARE_LIMIT} 檔</span>
      <span>目前未接後端自動日更 · 最新資料日 ${escapeHtml(DATA_END_DATE)} · 指定清單已上市 ${listed} 檔</span>
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
  const classes = [
    "universe-chip",
    listed ? "listed" : "unlisted",
    isSelected ? "selected" : "",
  ].filter(Boolean).join(" ");
  const actionLabel = isSelected ? `取消鎖定 ${etf.code}` : `鎖定 ${etf.code}`;
  return `
    <button class="${classes}" type="button" data-universe-code="${escapeHtml(etf.code)}" aria-pressed="${isSelected}" title="${escapeHtml(`${actionLabel} · ${listingLabel(etf)}`)}">
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
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b, "zh-Hant"));
}

function applyAutoAllocation() {
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
  const selected = optimizeEtfAllocation(normalizedTargets);
  state.selected = selected;
  state.historyEtfCode = selected.find((item) => isListed(getEtf(item.code)))?.code || "";
  state.activeSector = normalizedTargets[0]?.sector || state.activeSector;
  els.autoAllocationNotice.textContent = `已依 ${normalizedTargets
    .map((target) => `${target.sector} ${fmt(target.weight)}`)
    .join("、")} 自動選擇 ${selected.length} 檔 ETF。`;
  renderAll();
}

function optimizeEtfAllocation(targets) {
  const candidateScores = ETFS.map((etf) => {
    const vector = getEtfSectorVector(etf);
    const targetScore = targets.reduce((sum, target) => sum + (vector[target.sector] || 0) * target.weight, 0);
    const concentrationPenalty = Math.max(...Object.values(vector), 0) * 0.18;
    const listingPenalty = isListed(etf) ? 0 : 8;
    return { etf, score: targetScore - concentrationPenalty - listingPenalty, vector };
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
    const sector = STOCKS[stockCode]?.sector || "其他";
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

  const rows = buildHistoryRows(etf);
  if (!rows.length) {
    els.historySummary.innerHTML = `<div class="empty-state small">${escapeHtml(etf.code)} 尚未上市，無每日持股變化</div>`;
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

function buildHistoryRows(etf) {
  if (!isListed(etf)) return [];
  const allDates = getTradingDates(DATA_END_DATE, 22);
  const dates = allDates.filter((date) => date >= etf.listedDate);
  const snapshots = dates.map((date, index) => ({
    date,
    holdings: holdingsForDate(etf, date, index, dates.length),
  }));

  return snapshots.map((snapshot, index) => {
    const previous = snapshots[index - 1]?.holdings || {};
    const diff = diffHoldings(snapshot.holdings, previous, etf);
    return {
      date: snapshot.date,
      ...diff,
    };
  });
}

function holdingsForDate(etf, date, index, totalDays) {
  const holdings = {};
  const middle = Math.max(1, totalDays / 2);
  for (const [stockCode, weight] of Object.entries(etf.holdings)) {
    const seed = hash(`${etf.code}-${stockCode}`);
    const wave = Math.sin((index + (seed % 17)) / 3.3) * 0.28;
    const trend = ((index - middle) / middle) * (((seed % 9) - 4) * 0.045);
    const activeBias = etf.type === "主動" ? 1.35 : 0.6;
    holdings[stockCode] = roundWeight(Math.max(0.05, weight + (wave + trend) * activeBias));
  }

  for (const [rotationIndex, stockCode] of (etf.rotation || []).entries()) {
    const seed = hash(`${date}-${etf.code}-${stockCode}`);
    const phase = (index + seed + rotationIndex) % 11;
    if (phase >= 3 && phase <= 8) {
      holdings[stockCode] = roundWeight(0.65 + (phase - 3) * 0.18 + rotationIndex * 0.14);
    }
  }

  return holdings;
}

function diffHoldings(current, previous, etf) {
  const codes = new Set([...Object.keys(current), ...Object.keys(previous)]);
  const changes = [...codes].map((code) => {
    const diff = (current[code] || 0) - (previous[code] || 0);
    const stock = STOCKS[code];
    const amount = Math.abs(diff) / 100 * getEtfAumNtd(etf);
    const lotSize = getLotSize(code);
    return {
      code,
      name: stock?.name || code,
      diff,
      current: current[code] || 0,
      previous: previous[code] || 0,
      amount,
      lots: amount / (getStockPriceNtd(code) * lotSize),
      lotUnit: lotSize === 1 ? "股" : "張",
    };
  });

  const increases = changes
    .filter((item) => item.diff > 0.05 && item.previous > 0)
    .sort((a, b) => b.diff - a.diff)
    .slice(0, 3);
  const decreases = changes
    .filter((item) => item.diff < -0.05 && item.current > 0)
    .sort((a, b) => a.diff - b.diff)
    .slice(0, 3);
  const added = changes.filter((item) => item.previous === 0 && item.current > 0).slice(0, 2);
  const removed = changes.filter((item) => item.previous > 0 && item.current === 0).slice(0, 2);
  const turnover = changes.reduce((sum, item) => sum + Math.abs(item.diff), 0) / 2;

  return {
    increases,
    decreases,
    added,
    removed,
    turnover,
  };
}

function formatMoverList(items) {
  if (!items.length) return "-";
  return items
    .map((item, index) => {
      const lots = item.lotUnit === "股" ? Math.round(item.lots) : item.lots;
      return `
        <div class="history-mover-line">
          <strong>${index + 1}. ${escapeHtml(item.name)}</strong>
          <span>${signedFmt(item.diff)} · ${escapeHtml(formatMoney(item.amount))} · ${escapeHtml(formatLots(lots, item.lotUnit))}</span>
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

function getEtfAumNtd(etf) {
  if (etf.aumBillion) return etf.aumBillion * 1000000000;
  const base = isListed(etf) ? 6.5 : 1.2;
  return (base + (hash(etf.code) % 90) / 10) * 1000000000;
}

function getStockPriceNtd(code) {
  const listedPrices = {
    "2330": 1080,
    "2454": 1320,
    "2308": 390,
    "2382": 305,
    "3017": 815,
    "6669": 2550,
    "2881": 84,
    "2891": 43,
    "2886": 42,
    "2603": 178,
    NVDA: 950,
    MSFT: 14500,
    AVGO: 7800,
    TSLA: 5900,
    TSM: 5600,
  };
  return listedPrices[code] || 40 + (hash(code) % 2200);
}

function getLotSize(code) {
  return /^\d+$/.test(code) ? 1000 : 1;
}

function getTradingDates(endDate, count) {
  const dates = [];
  const date = parseDate(endDate);
  while (dates.length < count) {
    const day = date.getDay();
    if (day !== 0 && day !== 6) dates.unshift(formatDate(date));
    date.setDate(date.getDate() - 1);
  }
  return dates;
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

function parseDate(dateString) {
  const [year, month, day] = dateString.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function roundWeight(value) {
  return Math.round(value * 100) / 100;
}

function hash(value) {
  let result = 0;
  for (let index = 0; index < value.length; index += 1) {
    result = (result * 31 + value.charCodeAt(index)) % 100000;
  }
  return result;
}

function renderAnalytics() {
  const model = computePortfolio();
  renderAllocation(model.totalAllocation);
  renderMetrics(model);
  renderExposureChart(model.exposures);
  renderSector(model);
  renderHeatmap(model.exposures);
  renderHistory();
}

function renderDataStatus() {
  const stateLabels = {
    manual: "未接自動日更",
    refreshing: "刷新中",
    ready: "已接資料 API",
    failed: "未接資料 API",
  };
  els.updateStatusPill.className = `status-pill ${dataRefreshState}`;
  els.updateStatusPill.innerHTML = `<span></span>${stateLabels[dataRefreshState] || "資料狀態"}`;
  els.lastRefreshText.textContent = lastRefreshAt
    ? `最新資料日 ${DATA_END_DATE} · ${lastRefreshAt}`
    : `最新資料日 ${DATA_END_DATE}`;
  els.refreshDataBtn.disabled = dataRefreshState === "refreshing";
  els.refreshDataBtn.textContent = dataRefreshState === "refreshing" ? "刷新中..." : "刷新資料";
}

function renderAll() {
  renderDataStatus();
  renderOptimizerOptions();
  renderSearch();
  renderSelected();
  renderAnalytics();
}

function addEtf(code) {
  if (state.selected.length >= COMPARE_LIMIT || selectedCodes().has(code)) return;
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
    dataRefreshState = "ready";
    dataRefreshMessage = `已從本機資料 API 抓取最新 ETF 持股、寫入 data/latest-etf-holdings.json 並重新計算${warnings.length ? `；${warnings.join("、")}，完整官方資料需接 PCF。` : "。"}`;
  } catch (error) {
    DATA_END_DATE = getLatestTradingDate();
    dataRefreshState = "failed";
    dataRefreshMessage = `資料 API 呼叫失敗：${error.message || "請確認 server.py 已啟動且資料來源可連線。"}`;
  }

  lastRefreshAt = new Date().toLocaleTimeString("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
  });
  els.notice.textContent = dataRefreshMessage;
  renderAll();
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
  for (const incoming of payload.etfs) {
    const etf = getEtf(incoming.code);
    if (!etf) continue;
    if (incoming.holdings) etf.holdings = incoming.holdings;
    if (incoming.status) etf.status = incoming.status;
    if (incoming.listedDate !== undefined) etf.listedDate = incoming.listedDate;
    if (incoming.expectedListingDate !== undefined) etf.expectedListingDate = incoming.expectedListingDate;
    if (incoming.source) etf.source = incoming.source;
  }
}

els.search.addEventListener("input", (event) => {
  state.query = event.target.value;
  renderSearch();
});

els.equalizeBtn.addEventListener("click", equalizeAllocations);

els.autoAllocateBtn.addEventListener("click", applyAutoAllocation);

els.refreshDataBtn.addEventListener("click", refreshLatestData);

els.universeSummary.addEventListener("click", (event) => {
  const button = event.target.closest("[data-universe-code]");
  if (!button) return;
  const code = button.dataset.universeCode;
  if (selectedCodes().has(code)) {
    removeEtf(code);
    els.notice.textContent = `已取消鎖定 ${code}。`;
    return;
  }
  if (state.selected.length >= COMPARE_LIMIT) {
    els.notice.textContent = `已達 ${COMPARE_LIMIT} 檔同步比對上限，請先移除一檔 ETF。`;
    return;
  }
  addEtf(code);
  els.notice.textContent = `已鎖定 ${code} 到比對清單。`;
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

renderAll();
