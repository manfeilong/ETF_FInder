from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_FILE = DATA_DIR / "latest-etf-holdings.json"
ETF_UNIVERSE_FILE = DATA_DIR / "etf-universe.json"
STOCK_UNIVERSE_FILE = DATA_DIR / "stock-universe.json"
ETF_PROFILE_FILE = DATA_DIR / "etf-profiles.json"
HISTORY_FILE = DATA_DIR / "holdings-history.json"
HISTORY_QUALITY_REPORT_FILE = DATA_DIR / "history-quality-latest.json"
PORTFOLIOS_FILE = DATA_DIR / "portfolios.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
ALERTS_FILE = DATA_DIR / "refresh-alerts.jsonl"

MAX_CODES_PER_REQUEST = 20
MAX_SEARCH_RESULTS = 80
DEFAULT_CHANGE_DAYS = 22
MAX_CHANGE_DAYS = 180
DEFAULT_OPTIMIZE_MAX_ETFS = 6
MAX_OPTIMIZE_MAX_ETFS = 10
MAX_PORTFOLIO_NAME_LENGTH = 60
MAX_PORTFOLIO_POSITIONS = 10
CODE_PATTERN = re.compile(r"\d{4,6}[A-Z]?")
ETF_HOLDINGS_PATH = re.compile(r"^/api/etfs/([^/]+)/holdings$")
ETF_HOLDINGS_CHANGES_PATH = re.compile(r"^/api/etfs/([^/]+)/holdings/changes$")
ETF_METRICS_PATH = re.compile(r"^/api/etfs/([^/]+)/metrics$")
PORTFOLIO_ITEM_PATH = re.compile(r"^/api/portfolios/([^/]+)$")
WATCHLIST_ITEM_PATH = re.compile(r"^/api/watchlist/([^/]+)$")
USER_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{3,64}")
USER_ID_HEADER = "X-ETF-User"

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/data/latest-etf-holdings.json": ("data/latest-etf-holdings.json", "application/json; charset=utf-8"),
    "/data/etf-profiles.json": ("data/etf-profiles.json", "application/json; charset=utf-8"),
}

DEFAULT_CODES = [
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
]


def parse_int_env(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if minimum is not None and value < minimum:
        return minimum
    if maximum is not None and value > maximum:
        return maximum
    return value


def parse_bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


LIVE_FETCH_ADAPTER = os.environ.get("ETF_HOLDINGS_ADAPTER", "etfinfo_public_page").strip().lower() or "etfinfo_public_page"
LIVE_FETCH_TIMEOUT_SECONDS = parse_int_env("ETF_FETCH_TIMEOUT_SECONDS", 20, minimum=5, maximum=120)
LIVE_FETCH_RETRIES = parse_int_env("ETF_FETCH_RETRIES", 2, minimum=0, maximum=6)
LIVE_FETCH_BACKOFF_MS = parse_int_env("ETF_FETCH_BACKOFF_MS", 600, minimum=0, maximum=10000)
LIVE_REQUIRE_FULL_HOLDINGS = parse_bool_env("ETF_LIVE_REQUIRE_FULL_HOLDINGS", False)
LIVE_MIN_DECLARED_HOLDINGS = parse_int_env("ETF_LIVE_MIN_DECLARED_HOLDINGS", 30, minimum=0, maximum=2000)
LIVE_MIN_PARSED_HOLDINGS = parse_int_env("ETF_LIVE_MIN_PARSED_HOLDINGS", 30, minimum=0, maximum=2000)
OFFICIAL_SNAPSHOT_DIR_RAW = os.environ.get("ETF_OFFICIAL_SNAPSHOT_DIR", str(DATA_DIR / "official-snapshots")).strip()
OFFICIAL_SNAPSHOT_DIR = Path(OFFICIAL_SNAPSHOT_DIR_RAW)
if not OFFICIAL_SNAPSHOT_DIR.is_absolute():
    OFFICIAL_SNAPSHOT_DIR = (ROOT / OFFICIAL_SNAPSHOT_DIR).resolve()
else:
    OFFICIAL_SNAPSHOT_DIR = OFFICIAL_SNAPSHOT_DIR.resolve()
ALERT_WEBHOOK_URL = os.environ.get("ETF_ALERT_WEBHOOK_URL", "").strip()
ALERT_WEBHOOK_TIMEOUT_SECONDS = parse_int_env("ETF_ALERT_WEBHOOK_TIMEOUT_SECONDS", 3, minimum=1, maximum=30)
OFFICIAL_ENDPOINT_URL_TEMPLATE = os.environ.get("ETF_OFFICIAL_ENDPOINT_URL_TEMPLATE", "").strip()
OFFICIAL_ENDPOINT_FORMAT = os.environ.get("ETF_OFFICIAL_ENDPOINT_FORMAT", "json").strip().lower() or "json"
OFFICIAL_ENDPOINT_HOLDINGS_PATH = os.environ.get("ETF_OFFICIAL_ENDPOINT_HOLDINGS_PATH", "").strip()
OFFICIAL_ENDPOINT_ASOF_PATH = os.environ.get("ETF_OFFICIAL_ENDPOINT_ASOF_PATH", "").strip()
OFFICIAL_ENDPOINT_DECLARED_COUNT_PATH = os.environ.get("ETF_OFFICIAL_ENDPOINT_DECLARED_COUNT_PATH", "").strip()
OFFICIAL_ENDPOINT_CODE_FIELD = os.environ.get("ETF_OFFICIAL_ENDPOINT_CODE_FIELD", "code").strip() or "code"
OFFICIAL_ENDPOINT_WEIGHT_FIELD = os.environ.get("ETF_OFFICIAL_ENDPOINT_WEIGHT_FIELD", "weight").strip() or "weight"
OFFICIAL_ENDPOINT_NAME_FIELD = os.environ.get("ETF_OFFICIAL_ENDPOINT_NAME_FIELD", "name").strip() or "name"
OFFICIAL_ENDPOINT_SHARES_FIELD = os.environ.get("ETF_OFFICIAL_ENDPOINT_SHARES_FIELD", "shares").strip() or "shares"
OFFICIAL_ENDPOINT_PRICE_FIELD = os.environ.get("ETF_OFFICIAL_ENDPOINT_PRICE_FIELD", "price").strip() or "price"
OFFICIAL_ENDPOINT_DATE = os.environ.get("ETF_OFFICIAL_ENDPOINT_DATE", "").strip()
OFFICIAL_ENDPOINT_HEADERS_RAW = os.environ.get("ETF_OFFICIAL_ENDPOINT_HEADERS", "").strip()
OFFICIAL_PCF_URL_TEMPLATE = os.environ.get("ETF_OFFICIAL_PCF_URL_TEMPLATE", "").strip()
OFFICIAL_PCF_FORMAT = os.environ.get("ETF_OFFICIAL_PCF_FORMAT", "csv").strip().lower() or "csv"
OFFICIAL_PCF_HOLDINGS_PATH = os.environ.get("ETF_OFFICIAL_PCF_HOLDINGS_PATH", "").strip()
OFFICIAL_PCF_ASOF_PATH = os.environ.get("ETF_OFFICIAL_PCF_ASOF_PATH", "").strip()
OFFICIAL_PCF_DECLARED_COUNT_PATH = os.environ.get("ETF_OFFICIAL_PCF_DECLARED_COUNT_PATH", "").strip()
OFFICIAL_PCF_CODE_FIELD = os.environ.get("ETF_OFFICIAL_PCF_CODE_FIELD", "").strip()
OFFICIAL_PCF_WEIGHT_FIELD = os.environ.get("ETF_OFFICIAL_PCF_WEIGHT_FIELD", "").strip()
OFFICIAL_PCF_NAME_FIELD = os.environ.get("ETF_OFFICIAL_PCF_NAME_FIELD", "").strip()
OFFICIAL_PCF_SHARES_FIELD = os.environ.get("ETF_OFFICIAL_PCF_SHARES_FIELD", "").strip()
OFFICIAL_PCF_PRICE_FIELD = os.environ.get("ETF_OFFICIAL_PCF_PRICE_FIELD", "").strip()
OFFICIAL_PCF_HEADERS_RAW = os.environ.get("ETF_OFFICIAL_PCF_HEADERS", "").strip()
OFFICIAL_TWSE_URL_TEMPLATE = os.environ.get("ETF_OFFICIAL_TWSE_URL_TEMPLATE", "").strip()
OFFICIAL_TWSE_FORMAT = os.environ.get("ETF_OFFICIAL_TWSE_FORMAT", "csv").strip().lower() or "csv"
OFFICIAL_TWSE_HOLDINGS_PATH = os.environ.get("ETF_OFFICIAL_TWSE_HOLDINGS_PATH", "").strip()
OFFICIAL_TWSE_ASOF_PATH = os.environ.get("ETF_OFFICIAL_TWSE_ASOF_PATH", "").strip()
OFFICIAL_TWSE_DECLARED_COUNT_PATH = os.environ.get("ETF_OFFICIAL_TWSE_DECLARED_COUNT_PATH", "").strip()
OFFICIAL_TWSE_CODE_FIELD = os.environ.get("ETF_OFFICIAL_TWSE_CODE_FIELD", "").strip()
OFFICIAL_TWSE_WEIGHT_FIELD = os.environ.get("ETF_OFFICIAL_TWSE_WEIGHT_FIELD", "").strip()
OFFICIAL_TWSE_NAME_FIELD = os.environ.get("ETF_OFFICIAL_TWSE_NAME_FIELD", "").strip()
OFFICIAL_TWSE_SHARES_FIELD = os.environ.get("ETF_OFFICIAL_TWSE_SHARES_FIELD", "").strip()
OFFICIAL_TWSE_PRICE_FIELD = os.environ.get("ETF_OFFICIAL_TWSE_PRICE_FIELD", "").strip()
OFFICIAL_TWSE_HEADERS_RAW = os.environ.get("ETF_OFFICIAL_TWSE_HEADERS", "").strip()
OFFICIAL_SOURCE_REGISTRY_FILE_RAW = os.environ.get(
    "ETF_OFFICIAL_SOURCE_REGISTRY_FILE",
    str(DATA_DIR / "official-source-registry.json"),
).strip()
OFFICIAL_SOURCE_REGISTRY_FILE = Path(OFFICIAL_SOURCE_REGISTRY_FILE_RAW)
if not OFFICIAL_SOURCE_REGISTRY_FILE.is_absolute():
    OFFICIAL_SOURCE_REGISTRY_FILE = (ROOT / OFFICIAL_SOURCE_REGISTRY_FILE).resolve()
else:
    OFFICIAL_SOURCE_REGISTRY_FILE = OFFICIAL_SOURCE_REGISTRY_FILE.resolve()
HISTORY_RETENTION_DAYS = parse_int_env("ETF_HISTORY_RETENTION_DAYS", 730, minimum=0, maximum=3650)
HISTORY_MAX_SNAPSHOTS_PER_CODE = parse_int_env("ETF_HISTORY_MAX_SNAPSHOTS_PER_CODE", 0, minimum=0, maximum=10000)
HISTORY_DROP_SEED_WHEN_REAL = parse_bool_env("ETF_HISTORY_DROP_SEED_WHEN_REAL", True)
HISTORY_QUALITY_REPORT_FILE_RAW = os.environ.get(
    "ETF_HISTORY_QUALITY_REPORT_FILE",
    str(HISTORY_QUALITY_REPORT_FILE),
).strip()
HISTORY_QUALITY_REPORT_FILE = Path(HISTORY_QUALITY_REPORT_FILE_RAW)
if not HISTORY_QUALITY_REPORT_FILE.is_absolute():
    HISTORY_QUALITY_REPORT_FILE = (ROOT / HISTORY_QUALITY_REPORT_FILE).resolve()
else:
    HISTORY_QUALITY_REPORT_FILE = HISTORY_QUALITY_REPORT_FILE.resolve()
DEFAULT_USER_ID_RAW = os.environ.get("ETF_DEFAULT_USER_ID", "public").strip() or "public"
DEFAULT_USER_ID = DEFAULT_USER_ID_RAW if USER_ID_PATTERN.fullmatch(DEFAULT_USER_ID_RAW) else "public"
REQUIRE_USER_CONTEXT = parse_bool_env("ETF_REQUIRE_USER_CONTEXT", False)
ACCESS_LOG_ENABLED = parse_bool_env("ETF_ACCESS_LOG_ENABLED", True)
ACCESS_LOG_FILE_RAW = os.environ.get("ETF_ACCESS_LOG_FILE", str(DATA_DIR / "access-log.jsonl")).strip()
ACCESS_LOG_FILE = Path(ACCESS_LOG_FILE_RAW)
if not ACCESS_LOG_FILE.is_absolute():
    ACCESS_LOG_FILE = (ROOT / ACCESS_LOG_FILE).resolve()
else:
    ACCESS_LOG_FILE = ACCESS_LOG_FILE.resolve()
ACCESS_LOG_MAX_BYTES = parse_int_env("ETF_ACCESS_LOG_MAX_BYTES", 5 * 1024 * 1024, minimum=1024, maximum=500 * 1024 * 1024)
ACCESS_LOG_BACKUP_COUNT = parse_int_env("ETF_ACCESS_LOG_BACKUP_COUNT", 5, minimum=1, maximum=30)
API_AUTH_MODE = (os.environ.get("ETF_API_AUTH_MODE", "off").strip().lower() or "off")
API_TOKEN = os.environ.get("ETF_API_TOKEN", "").strip()
RATE_LIMIT_ENABLED = parse_bool_env("ETF_RATE_LIMIT_ENABLED", False)
RATE_LIMIT_WINDOW_SECONDS = parse_int_env("ETF_RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1, maximum=3600)
RATE_LIMIT_MAX_REQUESTS = parse_int_env("ETF_RATE_LIMIT_MAX_REQUESTS", 120, minimum=1, maximum=100000)
RATE_LIMIT_KEY_MODE = (os.environ.get("ETF_RATE_LIMIT_KEY_MODE", "ip").strip().lower() or "ip")
TWSE_RWD_BASE_URL = os.environ.get("ETF_TWSE_RWD_BASE_URL", "https://www.twse.com.tw").strip().rstrip("/")
TWSE_RWD_LANG = os.environ.get("ETF_TWSE_RWD_LANG", "zh").strip().lower() or "zh"
ETFFORTUNE_PRODUCTS_ENDPOINT = os.environ.get(
    "ETF_ETFFORTUNE_PRODUCTS_ENDPOINT",
    "/zh/ETFortune/ajaxProductsResult",
).strip() or "/zh/ETFortune/ajaxProductsResult"
ETFFORTUNE_CHART_ENDPOINT = os.environ.get(
    "ETF_ETFFORTUNE_CHART_ENDPOINT",
    "/zh/ETFortune-institute/ajaxEtfInfoChart",
).strip() or "/zh/ETFortune-institute/ajaxEtfInfoChart"
TWSE_ETF_CATEGORY_ROUTES = {
    "domestic": "/ETF/domestic",
    "foreign": "/ETF/foreign",
    "li": "/ETF/li",
    "activeList": "/ETF/activeList",
    "bfIncome": "/ETF/BFIncome",
    "liFutures": "/ETF/liFutures",
    "vanillaFutures": "/ETF/vanillaFutures",
}


def allowed_origins() -> set[str]:
    configured = os.environ.get("ETF_ALLOWED_ORIGINS", "")
    return {origin.strip() for origin in configured.split(",") if origin.strip()}


def parse_json_object_env(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in payload.items():
        name = str(key or "").strip()
        if not name:
            continue
        normalized[name] = str(value)
    return normalized


def decode_text_bytes(raw_bytes: bytes) -> str:
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "cp950", "big5", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise ValueError(f"Unable to decode bytes with known encodings: {last_error}") from last_error
    raise ValueError("Unable to decode bytes with known encodings.")


def read_text_file_with_fallback(path: Path) -> str:
    return decode_text_bytes(path.read_bytes())


OFFICIAL_ENDPOINT_HEADERS = parse_json_object_env(OFFICIAL_ENDPOINT_HEADERS_RAW)
OFFICIAL_PCF_HEADERS = parse_json_object_env(OFFICIAL_PCF_HEADERS_RAW)
OFFICIAL_TWSE_HEADERS = parse_json_object_env(OFFICIAL_TWSE_HEADERS_RAW)


def load_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except json.JSONDecodeError:
        return default


def read_json_file_strict(path: Path):
    raw_bytes = path.read_bytes()
    decode_errors = []
    for encoding in ("utf-8", "utf-8-sig", "cp950", "big5"):
        try:
            return json.loads(raw_bytes.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            decode_errors.append(f"{encoding}: {exc}")
            continue
    joined = "; ".join(decode_errors[:4])
    raise ValueError(f"File is not valid JSON in known encodings: {path} ({joined})")


def load_official_source_registry() -> dict:
    payload = load_json_file(OFFICIAL_SOURCE_REGISTRY_FILE, {"sources": []})
    if isinstance(payload, list):
        payload = {"sources": payload}
    if not isinstance(payload, dict):
        payload = {"sources": []}
    sources = payload.get("sources")
    if not isinstance(sources, list):
        payload["sources"] = []
    return payload


REGISTRY_FORMATS = {"json", "csv", "html"}
REGISTRY_AUTHORITY_TYPES = {"issuer", "exchange", "regulator"}
REGISTRY_SOURCE_STATUSES = {"active", "testing", "disabled", "deprecated"}


def validate_official_source_registry(registry: dict, universe: list[dict]) -> dict:
    issues: list[str] = []
    warnings: list[str] = []
    source_reports: list[dict] = []
    seen_names: set[str] = set()

    if not isinstance(registry, dict):
        registry = {}
        issues.append("Registry root must be a JSON object.")
    schema_version = registry.get("schemaVersion")
    if schema_version != 1:
        issues.append("Registry schemaVersion must be 1.")
    sources = registry.get("sources", [])
    if not isinstance(sources, list):
        sources = []
        issues.append("Registry sources must be an array.")

    universe_index = build_universe_index(universe)
    available_codes = known_codes(universe_index)
    selector_fields = ("codes", "codePrefixes", "issuerContains", "nameContains")
    for index, source in enumerate(sources):
        label = f"source #{index + 1}"
        source_issues: list[str] = []
        source_warnings: list[str] = []
        if not isinstance(source, dict):
            issues.append(f"{label} must be an object.")
            continue

        name = str(source.get("name") or "").strip()
        if not name:
            source_issues.append("name is required")
            name = label
        elif name in seen_names:
            source_issues.append("name must be unique")
        seen_names.add(name)

        enabled = source.get("enabled")
        if not isinstance(enabled, bool):
            source_issues.append("enabled must be an explicit boolean")
            enabled = False

        status = str(source.get("status") or "").strip().lower()
        if status not in REGISTRY_SOURCE_STATUSES:
            source_issues.append("status must be active, testing, disabled, or deprecated")
        if enabled and status != "active":
            source_issues.append("enabled sources must have status=active")
        if not enabled and status == "active":
            source_warnings.append("active source is disabled")

        publisher = str(source.get("publisher") or "").strip()
        if not publisher:
            source_issues.append("publisher is required")
        authority_type = str(source.get("authorityType") or "").strip().lower()
        if authority_type not in REGISTRY_AUTHORITY_TYPES:
            source_issues.append("authorityType must be issuer, exchange, or regulator")

        verified_at = str(source.get("verifiedAt") or "").strip()
        try:
            date.fromisoformat(verified_at)
        except ValueError:
            source_issues.append("verifiedAt must be an ISO date (YYYY-MM-DD)")

        data_format = str(source.get("format") or "").strip().lower()
        if data_format not in REGISTRY_FORMATS:
            source_issues.append("format must be json, csv, or html")
        expected_coverage = str(source.get("expectedCoverage") or "").strip().lower()
        if expected_coverage not in {"full", "partial"}:
            source_issues.append("expectedCoverage must be full or partial")
        elif enabled and expected_coverage == "partial":
            source_warnings.append("source is official but cannot satisfy strict full-holdings quality")
        url_template = str(source.get("urlTemplate") or source.get("url") or "").strip()
        urls_by_code = source.get("urlsByCode")
        if url_template:
            parsed_url = urlparse(url_template.replace("{code}", "0050").replace("{date}", "2026-01-01"))
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                source_issues.append("urlTemplate must be an absolute HTTP(S) URL")
            elif enabled and parsed_url.scheme != "https":
                source_issues.append("enabled source urlTemplate must use HTTPS")
        elif not isinstance(urls_by_code, dict) or not urls_by_code:
            source_issues.append("urlTemplate or urlsByCode is required")

        selectors_present = False
        for field in selector_fields:
            values = source.get(field)
            if values is None:
                continue
            if not isinstance(values, list) or not all(str(value).strip() for value in values):
                source_issues.append(f"{field} must be a non-empty string array")
                continue
            if values:
                selectors_present = True
        if urls_by_code is not None:
            if not isinstance(urls_by_code, dict) or not urls_by_code:
                source_issues.append("urlsByCode must be a non-empty object")
            else:
                selectors_present = True
                normalized_url_codes: list[str] = []
                for raw_code, raw_url in urls_by_code.items():
                    mapped_code = normalize_code(str(raw_code))
                    normalized_url_codes.append(mapped_code)
                    mapped_url = str(raw_url or "").strip()
                    parsed_mapped_url = urlparse(mapped_url)
                    if not CODE_PATTERN.fullmatch(mapped_code):
                        source_issues.append(f"urlsByCode has invalid ETF code: {raw_code}")
                    if parsed_mapped_url.scheme not in {"http", "https"} or not parsed_mapped_url.netloc:
                        source_issues.append(f"urlsByCode[{raw_code}] must be an absolute HTTP(S) URL")
                    elif enabled and parsed_mapped_url.scheme != "https":
                        source_issues.append(f"urlsByCode[{raw_code}] must use HTTPS when enabled")
                if len(normalized_url_codes) != len(set(normalized_url_codes)):
                    source_issues.append("urlsByCode contains duplicate normalized ETF codes")
                unknown_url_codes = sorted({code for code in normalized_url_codes if code not in available_codes})
                if unknown_url_codes:
                    source_warnings.append(
                        f"urlsByCode codes not found in current universe: {','.join(unknown_url_codes[:20])}"
                    )
        if not selectors_present:
            source_issues.append(f"one selector is required: {', '.join(selector_fields)}, urlsByCode")

        configured_codes = source.get("codes")
        if isinstance(configured_codes, list):
            normalized_codes = [normalize_code(str(value)) for value in configured_codes]
            if len(normalized_codes) != len(set(normalized_codes)):
                source_issues.append("codes contains duplicates")
            unknown_codes = sorted({code for code in normalized_codes if code and code not in available_codes})
            if unknown_codes:
                source_warnings.append(f"codes not found in current universe: {','.join(unknown_codes[:20])}")

        source_reports.append(
            {
                "name": name,
                "enabled": bool(enabled),
                "status": status,
                "publisher": publisher,
                "authorityType": authority_type,
                "format": data_format,
                "expectedCoverage": expected_coverage,
                "verifiedAt": verified_at,
                "issues": source_issues,
                "warnings": source_warnings,
            }
        )
        issues.extend(f"{name}: {message}" for message in source_issues)
        warnings.extend(f"{name}: {message}" for message in source_warnings)

    coverage = official_source_registry_summary(universe, registry=registry)
    if coverage.get("missingListedCount", 0):
        issues.append(
            f"Official source registry is missing {coverage['missingListedCount']} of "
            f"{coverage['listedCount']} listed ETF codes."
        )
    enabled_count = sum(1 for source in source_reports if source.get("enabled"))
    if enabled_count == 0:
        issues.append("Official source registry has no enabled sources.")

    return {
        "ok": not issues,
        "schemaVersion": schema_version,
        "sourceCount": len(source_reports),
        "enabledSourceCount": enabled_count,
        "issues": issues,
        "warnings": warnings,
        "sources": source_reports,
        "coverage": coverage,
    }


def write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = path.with_suffix(path.suffix + ".tmp")
    temporary_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_file.replace(path)


def load_etf_universe() -> list[dict]:
    return load_json_file(ETF_UNIVERSE_FILE, [])


def load_stock_universe() -> dict[str, dict]:
    return load_json_file(STOCK_UNIVERSE_FILE, {})


PROFILE_CATEGORY_FIELDS = (
    "strategy",
    "assetClass",
    "region",
    "distributionType",
    "leverageType",
)

PROFILE_METRIC_FIELDS = (
    "expenseRatioPct",
    "aumTwdBn",
    "avgDailyVolumeM",
    "premiumDiscountPct",
    "dividendYieldPct",
    "return1mPct",
    "return3mPct",
    "returnYtdPct",
    "return1yPct",
    "volatility1yPct",
    "maxDrawdown1yPct",
    "trackingErrorPct",
)

RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_STATE: dict[str, list[float]] = {}
HTTP_CHALLENGE_COOKIE_LOCK = threading.Lock()
HTTP_CHALLENGE_COOKIE_CACHE: dict[str, str] = {}


def parse_optional_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


def adapter_is_official(adapter_name: str) -> bool:
    normalized = str(adapter_name or "").strip().lower()
    return normalized in {
        "official",
        "pcf",
        "official_endpoint",
        "official_direct",
        "pcf_endpoint",
        "official_registry",
        "official_sources",
        "official_source_registry",
        "official_pcf_twse",
        "pcf_twse",
        "official_snapshot_file",
        "official_file",
        "pcf_file",
    }


def snapshot_quality_check(
    row: dict,
    require_full: bool = LIVE_REQUIRE_FULL_HOLDINGS,
    min_declared: int = LIVE_MIN_DECLARED_HOLDINGS,
    min_parsed: int = LIVE_MIN_PARSED_HOLDINGS,
) -> tuple[bool, str]:
    declared = int(row.get("declaredHoldingCount") or 0)
    parsed = int(row.get("parsedHoldingCount") or 0)
    coverage = str(row.get("coverage", "")).strip().lower()

    if require_full and coverage != "full":
        return False, f"coverage is {coverage or 'unknown'}, expected full"
    if min_declared > 0 and declared < min_declared:
        return False, f"declared holding count {declared} is below minimum {min_declared}"
    if min_parsed > 0 and parsed < min_parsed:
        return False, f"parsed holding count {parsed} is below minimum {min_parsed}"
    return True, ""


def build_auth_settings_summary() -> dict:
    return {
        "mode": API_AUTH_MODE,
        "tokenConfigured": bool(API_TOKEN),
    }


def build_rate_limit_settings_summary() -> dict:
    return {
        "enabled": RATE_LIMIT_ENABLED,
        "windowSeconds": RATE_LIMIT_WINDOW_SECONDS,
        "maxRequests": RATE_LIMIT_MAX_REQUESTS,
        "keyMode": RATE_LIMIT_KEY_MODE,
    }


def load_etf_profile_store() -> dict:
    payload = load_json_file(ETF_PROFILE_FILE, {"rows": []})
    if isinstance(payload, list):
        return {"rows": payload}
    if not isinstance(payload, dict):
        return {"rows": []}

    rows = payload.get("rows")
    if not isinstance(rows, list):
        legacy_profiles = payload.get("profiles")
        if isinstance(legacy_profiles, dict):
            rows = []
            for code, row in legacy_profiles.items():
                if not isinstance(row, dict):
                    continue
                rows.append({"code": code, **row})
        else:
            rows = []
    payload["rows"] = rows
    return payload


def build_etf_profile_index(profile_store: dict) -> dict[str, dict]:
    rows = profile_store.get("rows", []) if isinstance(profile_store, dict) else []
    index: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = normalize_code(str(row.get("code", "")))
        if not code:
            continue
        normalized = dict(row)
        normalized["code"] = code
        index[code] = normalized
    return index


def profile_coverage_summary(universe: list[dict], profile_index: dict[str, dict]) -> dict:
    universe_codes = [normalize_code(str(row.get("code", ""))) for row in universe if row.get("code")]
    missing_codes = [code for code in universe_codes if code and code not in profile_index]
    return {
        "universeCount": len(universe_codes),
        "profileCount": len(profile_index),
        "coveredCount": len(universe_codes) - len(missing_codes),
        "missingCount": len(missing_codes),
        "missingCodes": missing_codes[:50],
    }


def profile_metrics_coverage_summary(universe: list[dict], profile_index: dict[str, dict]) -> dict:
    universe_codes = [normalize_code(str(row.get("code", ""))) for row in universe if row.get("code")]
    required_metrics = list(PROFILE_METRIC_FIELDS)
    complete = 0
    partial = 0
    missing = 0
    by_field = {
        field: {"availableCount": 0, "missingCount": 0, "missingCodes": []}
        for field in required_metrics
    }

    for code in universe_codes:
        profile = profile_index.get(code, {})
        if not isinstance(profile, dict) or not profile:
            missing += 1
            continue
        available = 0
        for field in required_metrics:
            value = parse_optional_float(profile.get(field))
            if value is not None:
                available += 1
                by_field[field]["availableCount"] += 1
            else:
                by_field[field]["missingCount"] += 1
                if len(by_field[field]["missingCodes"]) < 50:
                    by_field[field]["missingCodes"].append(code)
        if available == len(required_metrics):
            complete += 1
        elif available == 0:
            missing += 1
        else:
            partial += 1
    return {
        "requiredMetricCount": len(required_metrics),
        "universeCount": len(universe_codes),
        "completeCount": complete,
        "partialCount": partial,
        "missingCount": missing,
        "byField": by_field,
    }


def profile_view(row: dict | None) -> dict:
    if not isinstance(row, dict):
        return {}
    view: dict[str, object] = {}
    for field in PROFILE_CATEGORY_FIELDS:
        value = str(row.get(field, "")).strip()
        if value:
            view[field] = value
    for field in PROFILE_METRIC_FIELDS:
        value = parse_optional_float(row.get(field))
        if value is not None:
            view[field] = value
    as_of = str(row.get("asOf", "")).strip()
    if as_of:
        view["asOf"] = as_of
    source = str(row.get("source", "")).strip()
    if source:
        view["source"] = source
    return view


def enrich_etf_row(row: dict, profile_index: dict[str, dict]) -> dict:
    code = normalize_code(str(row.get("code", "")))
    next_row = dict(row)
    if code:
        next_row["code"] = code
    profile = profile_view(profile_index.get(code))
    if profile:
        next_row["profile"] = profile
        for field in PROFILE_CATEGORY_FIELDS:
            if field in profile and field not in next_row:
                next_row[field] = profile[field]
    return next_row


def listed_only_flag(raw_value: str | None) -> bool:
    if raw_value is None:
        return False
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_user_id(value) -> str:
    candidate = str(value or "").strip()
    if not USER_ID_PATTERN.fullmatch(candidate):
        raise ValueError("user id must match [A-Za-z0-9._-]{3,64}.")
    return candidate


def resolve_workspace_path(raw_path: str) -> Path:
    path = Path(str(raw_path or "").strip())
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    else:
        path = path.resolve()
    return path


def normalize_header_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def detect_field_key(row: dict, aliases: set[str], fallback_index: int | None = None) -> str | None:
    if not isinstance(row, dict):
        return None
    by_norm: dict[str, str] = {}
    keys = list(row.keys())
    for key in keys:
        normalized = normalize_header_name(key)
        if normalized:
            by_norm[normalized] = key
    for alias in aliases:
        if alias in by_norm:
            return by_norm[alias]
    if fallback_index is not None and fallback_index >= 0 and fallback_index < len(keys):
        return keys[fallback_index]
    return None


def normalize_import_date(raw_value: object) -> str:
    text = str(raw_value or "").strip()
    if not text:
        raise ValueError("date value is empty.")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", text):
        yyyy, mm, dd = text.split("/")
        return f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
    if re.fullmatch(r"\d{3}/\d{1,2}/\d{1,2}", text):
        yyy, mm, dd = text.split("/")
        return f"{int(yyy) + 1911:04d}-{int(mm):02d}-{int(dd):02d}"
    if re.fullmatch(r"\d{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    raise ValueError(f"Unsupported date format: {text!r}")


def safe_import_date(raw_value: object) -> str:
    try:
        return normalize_import_date(raw_value)
    except ValueError:
        return ""


def infer_universe_status(listed_date: str, raw_status: object = "") -> str:
    status_text = str(raw_status or "").strip().lower()
    if status_text in {"listed", "upcoming"}:
        return status_text
    if status_text in {"delisted", "terminated"}:
        return "upcoming"
    if listed_date:
        return "listed" if listed_date <= time.strftime("%Y-%m-%d") else "upcoming"
    return "listed"


def infer_distribution_type(name: str, tags_text: str) -> str:
    text = f"{name} {tags_text}".lower()
    if any(keyword in text for keyword in {"acc", "accum", "累積"}):
        return "accumulating"
    return "distribution"


def infer_leverage_type(name: str, tags_text: str) -> str:
    text = f"{name} {tags_text}".lower()
    if any(keyword in text for keyword in {"反向", "inverse", "short"}):
        return "inverse"
    if any(keyword in text for keyword in {"槓桿", "lever", "2x", "3x"}):
        return "leveraged"
    return "regular"


def infer_asset_class(name: str, type_value: str, tags_text: str) -> str:
    text = f"{name} {type_value} {tags_text}".lower()
    if any(keyword in text for keyword in {"債", "bond", "fixedincome"}):
        return "bond"
    if any(keyword in text for keyword in {"money", "cash", "貨幣"}):
        return "money_market"
    return "equity"


def infer_region(name: str, tags_text: str) -> str:
    text = f"{name} {tags_text}".lower()
    if any(keyword in text for keyword in {"美", "us", "s&p", "nasdaq"}):
        return "us"
    if any(keyword in text for keyword in {"全球", "world", "global"}):
        return "global"
    if any(keyword in text for keyword in {"中國", "china", "陸"}):
        return "cn"
    if any(keyword in text for keyword in {"日本", "japan", "日經"}):
        return "jp"
    return "tw"


def infer_strategy(code: str, name: str, tags_text: str) -> str:
    text = f"{name} {tags_text}".lower()
    if code.endswith("A") or any(keyword in text for keyword in {"主動", "active"}):
        return "active"
    return "passive"


def default_universe_row_from_code(code: str) -> dict:
    return {
        "code": code,
        "name": code,
        "type": "ETF",
        "tags": [],
        "source": "official_import",
        "status": "listed",
        "listedDate": "",
        "holdings": {},
        "rotation": [],
    }


def fetch_json_from_url(url: str, headers: dict[str, str] | None = None) -> object:
    body, _attempts = get_url_with_retry(url=url, headers=headers or None)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Endpoint did not return valid JSON: {url} ({exc})") from exc


def build_twse_rwd_url(api_path: str, lang: str = TWSE_RWD_LANG) -> str:
    route = str(api_path or "").strip()
    if not route:
        raise ValueError("TWSE route cannot be empty.")
    route = route.lstrip("/")
    return f"{TWSE_RWD_BASE_URL}/rwd/{lang}/{route}?response=json"


def fetch_twse_rwd_payload(api_path: str, lang: str = TWSE_RWD_LANG) -> dict:
    payload = fetch_json_from_url(build_twse_rwd_url(api_path, lang=lang))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected TWSE payload type for {api_path}: {type(payload).__name__}")
    return payload


def split_twse_lines(raw_value: object) -> list[str]:
    text = str(raw_value or "").replace("\r", "\n")
    rows = [segment.strip() for segment in text.split("\n") if segment.strip()]
    return rows


def extract_twse_code_tokens(raw_value: object) -> list[str]:
    text = str(raw_value or "").upper()
    tokens = re.findall(r"\d{4,6}[A-Z]?", text)
    codes: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        code = normalize_code(token)
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def clean_twse_name(raw_name: str) -> str:
    text = str(raw_name or "").strip()
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text)
    return text.strip()


def parse_twse_rwd_category_rows(payload: dict) -> list[dict]:
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        return []
    parsed: list[dict] = []
    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        code_cell = row[0] if len(row) > 0 else ""
        name_cell = row[1] if len(row) > 1 else ""
        management = str(row[2] if len(row) > 2 else "").strip()
        category = str(row[3] if len(row) > 3 else "").strip()
        codes = extract_twse_code_tokens(code_cell)
        if not codes:
            continue
        names = [clean_twse_name(item) for item in split_twse_lines(name_cell)]
        for index, code in enumerate(codes):
            name = names[index] if index < len(names) else (names[0] if names else "")
            parsed.append(
                {
                    "code": code,
                    "name": name,
                    "management": management,
                    "category": category,
                }
            )
    return parsed


def build_twse_category_index(lang: str = TWSE_RWD_LANG) -> tuple[dict[str, dict], dict[str, int]]:
    code_index: dict[str, dict] = {}
    route_counts: dict[str, int] = {}

    for route_name, route_path in TWSE_ETF_CATEGORY_ROUTES.items():
        payload = fetch_twse_rwd_payload(route_path, lang=lang)
        parsed_rows = parse_twse_rwd_category_rows(payload)
        route_counts[route_name] = len(parsed_rows)
        for row in parsed_rows:
            code = row["code"]
            current = code_index.setdefault(
                code,
                {"code": code, "name": row.get("name", ""), "management": "", "categories": set()},
            )
            name = str(row.get("name", "")).strip()
            if name:
                current["name"] = name
            management = str(row.get("management", "")).strip()
            if management:
                current["management"] = management
            category = str(row.get("category", "")).strip() or route_name
            categories: set[str] = current["categories"]
            categories.add(category)

    return code_index, route_counts


def infer_twse_leverage_type(code: str, categories: set[str], name: str) -> str:
    upper_code = code.upper()
    if upper_code.endswith("L") or "li-futures" in categories:
        return "leveraged"
    if upper_code.endswith("R"):
        return "inverse"
    if "反向" in name:
        return "inverse"
    if "槓桿" in name or "正2" in name:
        return "leveraged"
    return "regular"


def infer_twse_asset_class(code: str, categories: set[str], name: str, benchmark: str) -> str:
    text = f"{name} {benchmark}".lower()
    upper_code = code.upper()
    if upper_code.endswith("T"):
        return "multi_asset"
    if "bfIncome" in categories or upper_code.endswith(("B", "D")) or "債" in text or "bond" in text:
        return "bond"
    if "vanilla-futures" in categories or "li-futures" in categories or upper_code.endswith("U"):
        return "commodity_futures"
    return "equity"


def infer_twse_region(categories: set[str], name: str, benchmark: str) -> str:
    text = f"{name} {benchmark}".lower()
    if any(keyword in text for keyword in {"美國", "us", "s&p", "nasdaq", "dow jones"}):
        return "us"
    if any(keyword in text for keyword in {"中國", "china", "滬深", "上證"}):
        return "cn"
    if any(keyword in text for keyword in {"日本", "japan", "日經"}):
        return "jp"
    if any(keyword in text for keyword in {"印度", "india"}):
        return "in"
    if any(keyword in text for keyword in {"全球", "world", "global", "新興市場", "emerging"}):
        return "global"
    if "foreign" in categories:
        return "overseas"
    return "tw"


def infer_twse_distribution_type(name: str, benchmark: str) -> str:
    text = f"{name} {benchmark}".lower()
    if any(keyword in text for keyword in {"不配息", "累積", "acc", "accum"}):
        return "accumulating"
    return "distribution"


def infer_twse_strategy(code: str, name: str, management: str) -> str:
    text = f"{name} {management}".lower()
    if code.upper().endswith(("A", "D")):
        return "active"
    if "主動" in text or "active" in text:
        return "active"
    return "passive"


def import_universe_from_twse_rwd(lang: str = TWSE_RWD_LANG) -> dict:
    list_payload = fetch_twse_rwd_payload("/ETF/list", lang=lang)
    list_rows = list_payload.get("data", [])
    if not isinstance(list_rows, list) or not list_rows:
        raise ValueError("TWSE ETF list returned no rows.")

    category_index, route_counts = build_twse_category_index(lang=lang)
    existing_rows = load_etf_universe()
    existing_index = build_universe_index(existing_rows)
    imported_rows: list[dict] = []
    profile_rows: list[dict] = []

    for row in list_rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        listed_date = safe_import_date(str(row[0]).replace(".", "/"))
        code_tokens = extract_twse_code_tokens(row[1])
        if not code_tokens:
            continue
        name_tokens = [clean_twse_name(value) for value in split_twse_lines(row[2])]
        issuer = str(row[3]).strip()
        benchmark_tokens = split_twse_lines(row[4])
        benchmark_text = " / ".join(item.strip() for item in benchmark_tokens if item.strip())

        for index, code in enumerate(code_tokens):
            if not CODE_PATTERN.fullmatch(code):
                continue
            existing = existing_index.get(code, default_universe_row_from_code(code))
            category_meta = category_index.get(code, {})
            categories = set(category_meta.get("categories", set()))
            management = str(category_meta.get("management", "")).strip()
            name = (
                name_tokens[index]
                if index < len(name_tokens)
                else (name_tokens[0] if name_tokens else "")
            ) or str(existing.get("name", code))
            if not name:
                name = str(category_meta.get("name", "")).strip() or code

            strategy = infer_twse_strategy(code=code, name=name, management=management)
            leverage_type = infer_twse_leverage_type(code=code, categories=categories, name=name)
            asset_class = infer_twse_asset_class(code=code, categories=categories, name=name, benchmark=benchmark_text)
            region = infer_twse_region(categories=categories, name=name, benchmark=benchmark_text)
            distribution_type = infer_twse_distribution_type(name=name, benchmark=benchmark_text)
            status = infer_universe_status(listed_date, "listed")
            tags = [token for token in [issuer, benchmark_text, *sorted(categories)] if token]

            imported_rows.append(
                {
                    **existing,
                    "code": code,
                    "name": name,
                    "type": "ETF",
                    "tags": tags,
                    "source": "official_twse_rwd",
                    "status": status,
                    "listedDate": listed_date if status == "listed" else "",
                    "expectedListingDate": listed_date if status != "listed" else "",
                    "issuer": issuer,
                    "benchmark": benchmark_text,
                    "strategy": strategy,
                    "assetClass": asset_class,
                    "region": region,
                    "distributionType": distribution_type,
                    "leverageType": leverage_type,
                    "holdings": existing.get("holdings", {}),
                    "rotation": existing.get("rotation", []),
                }
            )

            profile_rows.append(
                {
                    "code": code,
                    "strategy": strategy,
                    "assetClass": asset_class,
                    "region": region,
                    "distributionType": distribution_type,
                    "leverageType": leverage_type,
                    "name": name,
                    "source": "official_twse_rwd",
                }
            )

    dedup_index: dict[str, dict] = {}
    for row in imported_rows:
        dedup_index[row["code"]] = row
    final_rows = [dedup_index[code] for code in sorted(dedup_index.keys())]
    write_json_atomic(ETF_UNIVERSE_FILE, final_rows)

    profile_store = load_etf_profile_store()
    profile_index = build_etf_profile_index(profile_store)
    for row in profile_rows:
        code = row["code"]
        current = profile_index.get(code, {"code": code})
        profile_index[code] = {**current, **row}
    profile_store["rows"] = [profile_index[code] for code in sorted(profile_index.keys())]
    profile_store["source"] = "official_twse_rwd"
    profile_store["asOf"] = time.strftime("%Y-%m-%d")
    write_json_atomic(ETF_PROFILE_FILE, profile_store)

    covered_by_categories = 0
    for row in final_rows:
        if row.get("benchmark") or row.get("leverageType") != "regular":
            covered_by_categories += 1

    return {
        "ok": True,
        "source": "official_twse_rwd",
        "lang": lang,
        "importedCount": len(final_rows),
        "listedCount": sum(1 for row in final_rows if row.get("status") == "listed"),
        "upcomingCount": sum(1 for row in final_rows if row.get("status") != "listed"),
        "routeRows": route_counts,
        "categoryIndexCount": len(category_index),
        "coveredByCategoryOrBenchmark": covered_by_categories,
        "savedUniverseFile": str(ETF_UNIVERSE_FILE),
        "savedProfileFile": str(ETF_PROFILE_FILE),
    }


def parse_numeric_text(raw_value: object) -> float | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip().replace(",", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


def parse_etffortune_date(raw_value: object) -> date | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    for sep in ("/", ".", "-"):
        if sep in text:
            parts = text.split(sep)
            if len(parts) == 3 and all(part.strip().isdigit() for part in parts):
                yyyy = int(parts[0])
                mm = int(parts[1])
                dd = int(parts[2])
                if yyyy < 1900:
                    yyyy += 1911
                try:
                    return date(yyyy, mm, dd)
                except ValueError:
                    return None
    return None


def fetch_etffortune_products_rows() -> list[dict]:
    endpoint = ETFFORTUNE_PRODUCTS_ENDPOINT
    if endpoint.startswith("/"):
        endpoint = f"{TWSE_RWD_BASE_URL}{endpoint}"
    payload = fetch_json_from_url(
        endpoint,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{TWSE_RWD_BASE_URL}/zh/ETFortune/products",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
    )
    if not isinstance(payload, dict):
        raise RuntimeError("ETFortune products API returned non-object payload.")
    if str(payload.get("status", "")).lower() != "success":
        raise RuntimeError(f"ETFortune products API status is not success: {payload.get('status')!r}")
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def parse_series_points(rows: list[dict]) -> list[tuple[date, float]]:
    points: list[tuple[date, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        point_date = parse_etffortune_date(row.get("date"))
        point_value = parse_numeric_text(row.get("count"))
        if point_date is None or point_value is None:
            continue
        points.append((point_date, point_value))
    points.sort(key=lambda item: item[0])
    return points


def fetch_etffortune_chart_series(code: str, start_date: date, end_date: date, series_type: str) -> object:
    endpoint = ETFFORTUNE_CHART_ENDPOINT
    if endpoint.startswith("/"):
        endpoint = f"{TWSE_RWD_BASE_URL}{endpoint}"
    payload = urlencode(
        {
            "id": code,
            "startDate": start_date.strftime("%Y/%m/%d"),
            "endDate": end_date.strftime("%Y/%m/%d"),
            "type": series_type,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{TWSE_RWD_BASE_URL}/zh/ETFortune-institute/etfInfo/{code}",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        method="POST",
    )
    with open_url_with_same_origin_308(request, timeout=LIVE_FETCH_TIMEOUT_SECONDS) as response:
        body = decode_text_bytes(response.read())
    return json.loads(body)


def find_latest_on_or_before(points: list[tuple[date, float]], target: date) -> float | None:
    value = None
    for point_date, point_value in points:
        if point_date <= target:
            value = point_value
        else:
            break
    return value


def compute_return_pct(points: list[tuple[date, float]], target_date: date) -> float | None:
    if len(points) < 2:
        return None
    current_value = points[-1][1]
    baseline_value = find_latest_on_or_before(points, target_date)
    if baseline_value is None or baseline_value <= 0:
        return None
    return round((current_value / baseline_value - 1.0) * 100.0, 4)


def compute_annualized_volatility_pct(points: list[tuple[date, float]]) -> float | None:
    if len(points) < 3:
        return None
    returns: list[float] = []
    for index in range(1, len(points)):
        prev = points[index - 1][1]
        curr = points[index][1]
        if prev <= 0:
            continue
        returns.append(curr / prev - 1.0)
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((row - mean) ** 2 for row in returns) / (len(returns) - 1)
    return round(math.sqrt(variance) * math.sqrt(252) * 100.0, 4)


def compute_max_drawdown_pct(points: list[tuple[date, float]]) -> float | None:
    if len(points) < 2:
        return None
    peak = points[0][1]
    max_drawdown = 0.0
    for _point_date, point_value in points:
        if point_value > peak:
            peak = point_value
        if peak <= 0:
            continue
        drawdown = (point_value / peak) - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
    return round(abs(max_drawdown) * 100.0, 4)


def import_metrics_from_etffortune(
    codes: list[str] | None = None,
    as_of: str | None = None,
    source: str = "official_twse_etffortune",
) -> dict:
    products_rows = fetch_etffortune_products_rows()
    if not products_rows:
        raise ValueError("ETFortune products API returned no rows.")

    product_index: dict[str, dict] = {}
    for row in products_rows:
        code = normalize_code(str(row.get("stockNo", "")).strip())
        if not code:
            continue
        product_index[code] = row

    selected_codes = list(product_index.keys())
    if codes:
        selected_codes = [code for code in codes if code in product_index]
        if not selected_codes:
            raise ValueError("None of the requested codes are present in ETFortune products data.")

    profile_store = load_etf_profile_store()
    profile_index = build_etf_profile_index(profile_store)
    end_date = date.today()
    start_date = end_date - timedelta(days=400)
    imported = 0
    errors: list[dict] = []
    series_success_count = 0

    for code in selected_codes:
        row = product_index.get(code, {})
        current = profile_index.get(code, {"code": code})
        next_row = dict(current)
        next_row["code"] = code
        next_row["source"] = source
        if as_of:
            next_row["asOf"] = normalize_import_date(as_of)
        else:
            next_row["asOf"] = end_date.isoformat()

        stock_name = str(row.get("stockName", "")).strip()
        if stock_name:
            next_row["name"] = stock_name

        aum_100m = parse_numeric_text(row.get("totalAv"))
        if aum_100m is not None:
            next_row["aumTwdBn"] = round(aum_100m / 10.0, 4)

        avg_daily_volume = parse_numeric_text(row.get("volumeYTD"))
        if avg_daily_volume is not None:
            next_row["avgDailyVolumeM"] = round(avg_daily_volume / 1_000_000.0, 4)

        close_price = parse_numeric_text(row.get("close1"))
        if close_price is not None:
            next_row["latestClosePrice"] = round(close_price, 4)

        holder_count = parse_numeric_text(row.get("holders"))
        if holder_count is not None:
            next_row["holdersCount"] = int(holder_count)

        value_ytd = parse_numeric_text(row.get("valueYTD"))
        if value_ytd is not None:
            next_row["avgDailyTradeValueYtdTwd100m"] = round(value_ytd, 4)

        issuer = str(row.get("issuer", "")).strip()
        if issuer:
            next_row["issuer"] = issuer

        benchmark = str(row.get("indexName", "")).strip()
        if benchmark:
            next_row["benchmark"] = benchmark

        listing_date = safe_import_date(str(row.get("listingDate", "")).replace(".", "/"))
        if listing_date:
            next_row["listedDate"] = listing_date

        try:
            close_payload = fetch_etffortune_chart_series(
                code=code,
                start_date=start_date,
                end_date=end_date,
                series_type="close",
            )
            series_success_count += 1
            close_points = parse_series_points(close_payload if isinstance(close_payload, list) else [])
            if close_points:
                latest_close_date = close_points[-1][0]
                next_row["return1mPct"] = compute_return_pct(close_points, latest_close_date - timedelta(days=30))
                next_row["return3mPct"] = compute_return_pct(close_points, latest_close_date - timedelta(days=90))
                next_row["returnYtdPct"] = compute_return_pct(
                    close_points,
                    date(latest_close_date.year, 1, 1),
                )
                next_row["return1yPct"] = compute_return_pct(close_points, latest_close_date - timedelta(days=365))
                next_row["volatility1yPct"] = compute_annualized_volatility_pct(close_points)
                next_row["maxDrawdown1yPct"] = compute_max_drawdown_pct(close_points)
        except Exception as exc:  # noqa: BLE001
            errors.append({"code": code, "series": "close", "message": str(exc)})

        try:
            fund_payload = fetch_etffortune_chart_series(
                code=code,
                start_date=start_date,
                end_date=end_date,
                series_type="fundPric",
            )
            series_success_count += 1
            if isinstance(fund_payload, dict):
                premium_points = parse_series_points(fund_payload.get("atmps", []))
                if premium_points:
                    next_row["premiumDiscountPct"] = round(premium_points[-1][1], 4)
                nav_points = parse_series_points(fund_payload.get("netPrice", []))
                if nav_points:
                    next_row["latestNavPrice"] = round(nav_points[-1][1], 4)
        except Exception as exc:  # noqa: BLE001
            errors.append({"code": code, "series": "fundPric", "message": str(exc)})

        for metric_field in PROFILE_METRIC_FIELDS:
            if next_row.get(metric_field) is None:
                next_row.pop(metric_field, None)

        profile_index[code] = next_row
        imported += 1

    profile_store["rows"] = [profile_index[code] for code in sorted(profile_index.keys())]
    profile_store["source"] = source
    profile_store["asOf"] = normalize_import_date(as_of) if as_of else end_date.isoformat()
    write_json_atomic(ETF_PROFILE_FILE, profile_store)

    failed_codes = sorted({str(row.get("code") or "") for row in errors if row.get("code")})
    series_request_count = len(selected_codes) * 2
    return {
        "ok": not errors,
        "source": source,
        "asOf": profile_store["asOf"],
        "productRowCount": len(products_rows),
        "importedCount": imported,
        "seriesRequestCount": series_request_count,
        "seriesSuccessCount": series_success_count,
        "errorCount": len(errors),
        "failedCodeCount": len(failed_codes),
        "failedCodes": failed_codes,
        "errors": errors[:50],
        "savedProfileFile": str(ETF_PROFILE_FILE),
    }


def import_universe_from_csv(csv_path: str) -> dict:
    path = resolve_workspace_path(csv_path)
    rows = parse_csv_dict_rows(read_text_file_with_fallback(path))
    if not rows:
        raise ValueError(f"No rows found in universe CSV: {path}")

    code_key = detect_field_key(rows[0], {"code", "etfcode", "securitycode", "symbol", "ticker"}, fallback_index=0)
    name_key = detect_field_key(rows[0], {"name", "etfname", "securityname", "productname"}, fallback_index=1)
    listed_date_key = detect_field_key(rows[0], {"listeddate", "listingdate", "startdate"})
    status_key = detect_field_key(rows[0], {"status", "state"})
    type_key = detect_field_key(rows[0], {"type", "category", "assetclass", "producttype"})
    tag_key = detect_field_key(rows[0], {"tags", "theme", "indexname", "benchmark"})
    strategy_key = detect_field_key(rows[0], {"strategy", "activepassive", "managementstyle"})
    asset_class_key = detect_field_key(rows[0], {"assetclass", "assettype"})
    region_key = detect_field_key(rows[0], {"region", "country", "market"})
    distribution_key = detect_field_key(rows[0], {"distributiontype", "dividendtype", "incomepolicy"})
    leverage_key = detect_field_key(rows[0], {"leveragetype", "inverseleveraged"})

    existing_rows = load_etf_universe()
    existing_index = build_universe_index(existing_rows)
    imported_rows: list[dict] = []
    profile_rows: list[dict] = []

    for csv_row in rows:
        raw_code = str(csv_row.get(code_key or "", "")).strip().upper()
        if not raw_code:
            continue
        code = resolve_code_in_universe(raw_code, set(existing_index.keys())) if existing_index else raw_code
        code = normalize_code(code)
        if not CODE_PATTERN.fullmatch(code):
            continue

        existing = existing_index.get(code, default_universe_row_from_code(code))
        name = str(csv_row.get(name_key or "", "")).strip() or str(existing.get("name", code))
        listed_date = safe_import_date(csv_row.get(listed_date_key or "", ""))
        status = infer_universe_status(listed_date, csv_row.get(status_key or "", ""))
        type_value = str(csv_row.get(type_key or "", "")).strip() or str(existing.get("type", "ETF"))
        tags_text = str(csv_row.get(tag_key or "", "")).strip()
        tags = [token.strip() for token in re.split(r"[|,;/]+", tags_text) if token.strip()]

        strategy = str(csv_row.get(strategy_key or "", "")).strip().lower() or infer_strategy(code, name, tags_text)
        asset_class = str(csv_row.get(asset_class_key or "", "")).strip().lower() or infer_asset_class(name, type_value, tags_text)
        region = str(csv_row.get(region_key or "", "")).strip().lower() or infer_region(name, tags_text)
        distribution_type = str(csv_row.get(distribution_key or "", "")).strip().lower() or infer_distribution_type(name, tags_text)
        leverage_type = str(csv_row.get(leverage_key or "", "")).strip().lower() or infer_leverage_type(name, tags_text)

        row = {
            **existing,
            "code": code,
            "name": name,
            "type": type_value,
            "tags": tags if tags else existing.get("tags", []),
            "source": "official_universe_csv",
            "status": status,
            "listedDate": listed_date if status == "listed" else "",
            "expectedListingDate": listed_date if status != "listed" else existing.get("expectedListingDate", ""),
            "strategy": strategy,
            "assetClass": asset_class,
            "region": region,
            "distributionType": distribution_type,
            "leverageType": leverage_type,
            "holdings": existing.get("holdings", {}),
            "rotation": existing.get("rotation", []),
        }
        imported_rows.append(row)

        profile_rows.append(
            {
                "code": code,
                "strategy": strategy,
                "assetClass": asset_class,
                "region": region,
                "distributionType": distribution_type,
                "leverageType": leverage_type,
                "source": "official_universe_csv",
            }
        )

    imported_rows.sort(key=lambda row: row.get("code", ""))
    write_json_atomic(ETF_UNIVERSE_FILE, imported_rows)

    profile_store = load_etf_profile_store()
    profile_index = build_etf_profile_index(profile_store)
    for profile_row in profile_rows:
        code = profile_row["code"]
        current = profile_index.get(code, {"code": code})
        profile_index[code] = {
            **current,
            **profile_row,
        }
    profile_store["rows"] = [profile_index[code] for code in sorted(profile_index.keys())]
    profile_store["source"] = "official_universe_csv"
    profile_store["asOf"] = time.strftime("%Y-%m-%d")
    write_json_atomic(ETF_PROFILE_FILE, profile_store)

    listed_count = sum(1 for row in imported_rows if row.get("status") == "listed")
    return {
        "ok": True,
        "path": str(path),
        "importedCount": len(imported_rows),
        "listedCount": listed_count,
        "upcomingCount": len(imported_rows) - listed_count,
        "savedUniverseFile": str(ETF_UNIVERSE_FILE),
        "savedProfileFile": str(ETF_PROFILE_FILE),
    }


def import_metrics_from_csv(csv_path: str, as_of: str | None = None, source: str = "official_metrics_csv") -> dict:
    path = resolve_workspace_path(csv_path)
    rows = parse_csv_dict_rows(read_text_file_with_fallback(path))
    if not rows:
        raise ValueError(f"No rows found in metrics CSV: {path}")

    code_key = detect_field_key(rows[0], {"code", "etfcode", "securitycode", "symbol", "ticker"}, fallback_index=0)

    metric_aliases: dict[str, set[str]] = {
        "expenseRatioPct": {"expenseratio", "expense", "feeratio", "managementfee"},
        "aumTwdBn": {"aum", "fundsize", "assets", "netassets"},
        "avgDailyVolumeM": {"avgdailyvolume", "dailyvolume", "volume", "avgvolume"},
        "premiumDiscountPct": {"premiumdiscount", "premium", "discount", "premiumdiscountpct"},
        "dividendYieldPct": {"dividendyield", "yield", "distributionyield"},
        "return1mPct": {"return1m", "r1m", "monthreturn"},
        "return3mPct": {"return3m", "r3m"},
        "returnYtdPct": {"returnytd", "rytd", "ytd"},
        "return1yPct": {"return1y", "r1y", "annualreturn"},
        "volatility1yPct": {"volatility1y", "volatility", "stddev", "sigma1y"},
        "maxDrawdown1yPct": {"maxdrawdown1y", "maxdrawdown", "mdd1y"},
        "trackingErrorPct": {"trackingerror", "te", "trackingdifference"},
        "strategy": {"strategy", "activepassive", "managementstyle"},
        "assetClass": {"assetclass", "assettype"},
        "region": {"region", "country", "market"},
        "distributionType": {"distributiontype", "dividendtype", "incomepolicy"},
        "leverageType": {"leveragetype", "inverseleveraged"},
        "name": {"name", "etfname", "securityname", "productname"},
    }

    key_map: dict[str, str] = {}
    for target, aliases in metric_aliases.items():
        key = detect_field_key(rows[0], aliases)
        if key:
            key_map[target] = key

    profile_store = load_etf_profile_store()
    profile_index = build_etf_profile_index(profile_store)

    parsed_rows = 0
    updated_codes: list[str] = []
    for csv_row in rows:
        code = normalize_code(str(csv_row.get(code_key or "", "")).strip())
        if not code or not CODE_PATTERN.fullmatch(code):
            continue
        parsed_rows += 1
        current = profile_index.get(code, {"code": code})
        next_row = dict(current)
        next_row["code"] = code
        next_row["source"] = source
        if as_of:
            next_row["asOf"] = normalize_import_date(as_of)

        for category_field in PROFILE_CATEGORY_FIELDS:
            key = key_map.get(category_field)
            if not key:
                continue
            value = str(csv_row.get(key, "")).strip().lower()
            if value:
                next_row[category_field] = value

        for metric_field in PROFILE_METRIC_FIELDS:
            key = key_map.get(metric_field)
            if not key:
                continue
            value = parse_optional_float(csv_row.get(key))
            if value is not None:
                next_row[metric_field] = value

        name_key = key_map.get("name")
        if name_key:
            name_value = str(csv_row.get(name_key, "")).strip()
            if name_value:
                next_row["name"] = name_value

        profile_index[code] = next_row
        updated_codes.append(code)

    profile_store["rows"] = [profile_index[code] for code in sorted(profile_index.keys())]
    if as_of:
        profile_store["asOf"] = normalize_import_date(as_of)
    else:
        profile_store["asOf"] = time.strftime("%Y-%m-%d")
    profile_store["source"] = source
    write_json_atomic(ETF_PROFILE_FILE, profile_store)

    return {
        "ok": True,
        "path": str(path),
        "parsedRows": parsed_rows,
        "updatedCount": len(updated_codes),
        "updatedCodes": updated_codes[:50],
        "savedProfileFile": str(ETF_PROFILE_FILE),
    }


def import_history_snapshots_from_dir(directory: str, source: str = "official_snapshot_import") -> dict:
    base_dir = resolve_workspace_path(directory)
    if not base_dir.exists() or not base_dir.is_dir():
        raise ValueError(f"Snapshot directory does not exist: {base_dir}")

    snapshot_rows: list[dict] = []
    parse_errors: list[dict] = []

    for path in sorted(base_dir.rglob("*.json")):
        try:
            payload = read_json_file_strict(path)
        except (OSError, ValueError) as exc:
            parse_errors.append({"file": str(path), "message": str(exc)})
            continue

        candidate_rows: list[dict]
        if isinstance(payload, dict) and isinstance(payload.get("etfs"), list):
            candidate_rows = [row for row in payload.get("etfs", []) if isinstance(row, dict)]
        elif isinstance(payload, list):
            candidate_rows = [row for row in payload if isinstance(row, dict)]
        elif isinstance(payload, dict):
            candidate_rows = [payload]
        else:
            parse_errors.append({"file": str(path), "message": "Unsupported JSON structure."})
            continue

        for row in candidate_rows:
            code = normalize_code(str(row.get("code", "")).strip())
            if not code or not CODE_PATTERN.fullmatch(code):
                continue
            as_of = safe_import_date(row.get("asOf", ""))
            if not as_of:
                parent_as_of = safe_import_date(path.parent.name)
                as_of = parent_as_of
            if not as_of:
                file_as_of_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.stem)
                if file_as_of_match:
                    as_of = file_as_of_match.group(1)
            if not as_of:
                parse_errors.append(
                    {
                        "file": str(path),
                        "code": code,
                        "message": "Missing asOf (provide row.asOf, date folder name, or date in filename).",
                    }
                )
                continue

            try:
                holdings = normalize_holdings_map(row.get("holdings", {}))
            except ValueError as exc:
                parse_errors.append({"file": str(path), "code": code, "message": str(exc)})
                continue

            declared = int(row.get("declaredHoldingCount") or len(holdings))
            parsed_count = int(row.get("parsedHoldingCount") or len(holdings))
            coverage = str(row.get("coverage", "")).strip() or ("full" if declared == parsed_count else "partial_official_file")
            details = row.get("holdingDetails", [])
            if not isinstance(details, list):
                details = []

            snapshot_rows.append(
                {
                    "code": code,
                    "asOf": as_of,
                    "source": str(row.get("source", "")).strip() or source,
                    "coverage": coverage,
                    "declaredHoldingCount": declared,
                    "parsedHoldingCount": parsed_count,
                    "holdings": holdings,
                    "holdingDetails": details,
                }
            )

    if not snapshot_rows:
        raise ValueError("No valid snapshot rows were imported.")

    upsert_history_from_payload(
        {
            "asOf": max(row["asOf"] for row in snapshot_rows),
            "source": source,
            "etfs": snapshot_rows,
            "errors": [],
        }
    )
    return {
        "ok": True,
        "directory": str(base_dir),
        "importedRows": len(snapshot_rows),
        "uniqueCodes": len({row["code"] for row in snapshot_rows}),
        "uniqueDates": len({row["asOf"] for row in snapshot_rows}),
        "latestAsOf": max(row["asOf"] for row in snapshot_rows),
        "parseErrorCount": len(parse_errors),
        "parseErrors": parse_errors[:20],
    }


def build_universe_index(etfs: list[dict]) -> dict[str, dict]:
    return {str(etf.get("code", "")).upper(): etf for etf in etfs if etf.get("code")}


def known_codes(universe_index: dict[str, dict]) -> set[str]:
    return set(universe_index)


def normalize_code(code: str) -> str:
    return code.strip().upper()


def resolve_code_in_universe(code: str, available_codes: set[str]) -> str:
    if code in available_codes:
        return code

    matched = re.fullmatch(r"(\d+)([A-Z]?)", code)
    if not matched:
        return code

    numeric_part = matched.group(1)
    suffix = matched.group(2) or ""
    normalized_numeric = numeric_part.lstrip("0") or "0"

    candidates = []
    for available in available_codes:
        available_match = re.fullmatch(r"(\d+)([A-Z]?)", available)
        if not available_match:
            continue
        available_numeric = available_match.group(1)
        available_suffix = available_match.group(2) or ""
        if available_suffix != suffix:
            continue
        available_normalized = available_numeric.lstrip("0") or "0"
        if available_normalized == normalized_numeric:
            candidates.append(available)

    if len(candidates) == 1:
        return candidates[0]

    if not candidates and not suffix:
        numeric_only_candidates = []
        for available in available_codes:
            available_match = re.fullmatch(r"(\d+)([A-Z]?)", available)
            if not available_match:
                continue
            available_numeric = available_match.group(1)
            available_normalized = available_numeric.lstrip("0") or "0"
            if available_normalized == normalized_numeric:
                numeric_only_candidates.append(available)
        if len(numeric_only_candidates) == 1:
            return numeric_only_candidates[0]
    return code


def parse_requested_codes(requested: str, available_codes: set[str]) -> list[str]:
    raw_codes = [normalize_code(part) for part in requested.split(",") if part.strip()]
    if not raw_codes:
        raw_codes = [code for code in DEFAULT_CODES if code in available_codes]
        if not raw_codes:
            raw_codes = sorted(available_codes)[:MAX_CODES_PER_REQUEST]
    if not raw_codes:
        raise ValueError("No ETF codes are configured in ETF universe.")
    codes = []
    seen = set()
    for raw_code in raw_codes:
        if not CODE_PATTERN.fullmatch(raw_code) and not re.fullmatch(r"\d{1,6}[A-Z]?", raw_code):
            raise ValueError(f"Invalid ETF code format: {raw_code}")
        resolved_code = resolve_code_in_universe(raw_code, available_codes)
        if resolved_code not in available_codes:
            raise ValueError(f"ETF code is not in the configured universe: {raw_code}")
        if resolved_code not in seen:
            codes.append(resolved_code)
            seen.add(resolved_code)
    if len(codes) > MAX_CODES_PER_REQUEST:
        raise ValueError(f"Too many ETF codes requested; maximum is {MAX_CODES_PER_REQUEST}.")
    return codes


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_data(self, data: str) -> None:
        if self.ignored_depth:
            return
        text = data.strip()
        if text:
            self.parts.append(text)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if tag in {"tr", "td", "th", "li", "br", "p", "div", "section", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self.ignored_depth:
            self.ignored_depth -= 1

    def text(self) -> str:
        return "\n".join(self.parts)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_refresh_alert(level: str, message: str, context: dict | None = None) -> dict:
    payload = {
        "time": utc_now_iso(),
        "level": str(level or "info").lower(),
        "message": str(message or "").strip(),
        "context": context or {},
    }
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_FILE.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def send_alert_webhook(payload: dict) -> bool:
    if not ALERT_WEBHOOK_URL:
        return False
    request = urllib.request.Request(
        ALERT_WEBHOOK_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=ALERT_WEBHOOK_TIMEOUT_SECONDS) as response:
        return int(getattr(response, "status", 0) or 0) < 400


def emit_refresh_alert(level: str, message: str, context: dict | None = None) -> dict:
    payload = append_refresh_alert(level=level, message=message, context=context)
    try:
        delivered = send_alert_webhook(payload)
        payload["webhookDelivered"] = delivered
    except Exception as exc:  # noqa: BLE001
        payload["webhookDelivered"] = False
        payload["webhookError"] = str(exc)
    return payload


def read_recent_refresh_alerts(limit: int = 20) -> list[dict]:
    bounded = max(1, min(int(limit or 20), 200))
    if not ALERTS_FILE.exists():
        return []
    try:
        lines = ALERTS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines[-bounded:]:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
        except json.JSONDecodeError:
            continue
    return rows[::-1]


def read_recent_access_logs(limit: int = 100) -> list[dict]:
    bounded = max(1, min(int(limit or 100), 500))
    if not ACCESS_LOG_FILE.exists():
        return []
    try:
        lines = ACCESS_LOG_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines[-bounded:]:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
        except json.JSONDecodeError:
            continue
    return rows[::-1]


def rotate_jsonl_log(path: Path, backup_count: int) -> None:
    if backup_count < 1:
        return
    for index in range(backup_count - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        target = path.with_name(f"{path.name}.{index + 1}")
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
    first_backup = path.with_name(f"{path.name}.1")
    if path.exists():
        first_backup.parent.mkdir(parents=True, exist_ok=True)
        path.replace(first_backup)


def append_jsonl_record(path: Path, payload: dict, rotate_max_bytes: int, backup_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= rotate_max_bytes:
        rotate_jsonl_log(path, backup_count)
    with path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(payload, ensure_ascii=False) + "\n")


def access_log_settings() -> dict:
    return {
        "enabled": ACCESS_LOG_ENABLED,
        "file": str(ACCESS_LOG_FILE),
        "maxBytes": ACCESS_LOG_MAX_BYTES,
        "backupCount": ACCESS_LOG_BACKUP_COUNT,
    }


def append_access_log(payload: dict) -> None:
    if not ACCESS_LOG_ENABLED:
        return
    append_jsonl_record(
        path=ACCESS_LOG_FILE,
        payload=payload,
        rotate_max_bytes=ACCESS_LOG_MAX_BYTES,
        backup_count=ACCESS_LOG_BACKUP_COUNT,
    )


def get_url(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> str:
    default_headers = {
        "User-Agent": "Mozilla/5.0 ETF True Exposure Lab data refresh",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    if headers:
        default_headers.update(headers)
    request = urllib.request.Request(
        url,
        headers=default_headers,
    )
    with open_url_with_same_origin_308(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def open_url_with_same_origin_308(request: urllib.request.Request, timeout: int = 20):
    request_origin = urlparse(request.full_url)
    origin_key = f"{request_origin.scheme}://{request_origin.netloc}"
    with HTTP_CHALLENGE_COOKIE_LOCK:
        cached_cookie = HTTP_CHALLENGE_COOKIE_CACHE.get(origin_key, "")
    if cached_cookie and not request.get_header("Cookie"):
        cached_headers = dict(request.header_items())
        cached_headers["Cookie"] = cached_cookie
        request = urllib.request.Request(
            request.full_url,
            data=request.data,
            headers=cached_headers,
            method=request.get_method(),
        )
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code not in {308, 428}:
            raise
        location = str(exc.headers.get("Location") or "").strip()
        cookie_header = str(exc.headers.get("Set-Cookie") or "").split(";", 1)[0].strip()
        redirected_url = urljoin(request.full_url, location) if location else request.full_url
        original_origin = urlparse(request.full_url)
        redirected_origin = urlparse(redirected_url)
        if (
            (exc.code == 308 and not location)
            or (exc.code == 428 and not cookie_header)
            or original_origin.scheme != redirected_origin.scheme
            or original_origin.netloc != redirected_origin.netloc
        ):
            raise RuntimeError(f"Endpoint returned an unsafe HTTP {exc.code} challenge response.") from exc
        retry_headers = dict(request.header_items())
        if cookie_header:
            retry_headers["Cookie"] = cookie_header
            with HTTP_CHALLENGE_COOKIE_LOCK:
                HTTP_CHALLENGE_COOKIE_CACHE[origin_key] = cookie_header
        retry_request = urllib.request.Request(
            redirected_url,
            data=request.data,
            headers=retry_headers,
            method=request.get_method(),
        )
        return urllib.request.urlopen(retry_request, timeout=timeout)


def get_url_with_retry(
    url: str,
    timeout: int = LIVE_FETCH_TIMEOUT_SECONDS,
    retries: int = LIVE_FETCH_RETRIES,
    backoff_ms: int = LIVE_FETCH_BACKOFF_MS,
    headers: dict[str, str] | None = None,
) -> tuple[str, int]:
    attempts = max(1, retries + 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return get_url(url, timeout=timeout, headers=headers), attempt
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            if backoff_ms > 0:
                time.sleep(backoff_ms / 1000)
    raise RuntimeError(f"Failed to fetch URL after {attempts} attempts: {last_error}") from last_error


class HoldingsAdapter(Protocol):
    name: str
    source_label: str

    def fetch_one(self, code: str) -> dict:
        ...


class ETFInfoPublicPageAdapter:
    name = "etfinfo_public_page"
    source_label = "ETFInfo public page"

    def fetch_one(self, code: str) -> dict:
        url = f"https://www.etfinfo.tw/etf/{code}/holdings"
        markup, attempts = get_url_with_retry(url=url)
        parsed = parse_etfinfo_holdings(code, markup)
        source_label = str(parsed.get("source", "")).strip()
        parsed["source"] = source_label or self.source_label
        parsed["adapter"] = self.name
        parsed["fetchUrl"] = url
        parsed["attempts"] = attempts
        return parsed


def normalize_holdings_map(raw: dict) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise ValueError("holdings must be an object.")
    normalized: dict[str, float] = {}
    for stock_code, raw_weight in raw.items():
        code = str(stock_code or "").strip().upper()
        if not code:
            continue
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid holding weight for {code}: {raw_weight!r}") from None
        if weight < 0:
            raise ValueError(f"Holding weight must be non-negative for {code}.")
        normalized[code] = weight
    if not normalized:
        raise ValueError("holdings map is empty.")
    return normalized


def parse_snapshot_entry_for_code(payload: object, code: str) -> dict:
    if isinstance(payload, dict) and isinstance(payload.get("etfs"), list):
        for row in payload.get("etfs", []):
            if isinstance(row, dict) and normalize_code(str(row.get("code", ""))) == code:
                return row
        raise ValueError(f"Snapshot file does not include ETF {code}.")
    if isinstance(payload, dict):
        row_code = normalize_code(str(payload.get("code", "")))
        if row_code and row_code != code:
            raise ValueError(f"Snapshot ETF code mismatch: expected {code}, got {row_code}.")
        return payload
    raise ValueError("Snapshot file must be a JSON object.")


def normalize_snapshot_as_of(raw_as_of: object) -> str:
    as_of = str(raw_as_of or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise ValueError(f"Invalid asOf date format: {as_of!r}. Expected YYYY-MM-DD.")
    return as_of


def parse_weight_value(raw_weight: object) -> float:
    text = str(raw_weight or "").strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1].strip()
    value = float(text)
    if value < 0:
        raise ValueError(f"Holding weight must be non-negative: {raw_weight!r}")
    return value


def resolve_json_path(payload: object, path: str) -> object:
    cursor = payload
    for part in [segment for segment in path.split(".") if segment]:
        if isinstance(cursor, dict):
            if part not in cursor:
                raise ValueError(f"Path segment {part!r} not found in JSON object.")
            cursor = cursor[part]
            continue
        if isinstance(cursor, list):
            try:
                index = int(part)
            except ValueError:
                raise ValueError(f"Path segment {part!r} is not a valid list index.") from None
            if index < 0 or index >= len(cursor):
                raise ValueError(f"Path index {index} is out of range.")
            cursor = cursor[index]
            continue
        raise ValueError(f"Path segment {part!r} cannot be resolved on non-container value.")
    return cursor


def endpoint_rows_from_payload(payload: object, holdings_path: str) -> object:
    if holdings_path:
        return resolve_json_path(payload, holdings_path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("holdings"), list):
            return payload["holdings"]
        if isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload.get("rows"), list):
            return payload["rows"]
    raise ValueError("Unable to resolve holdings rows. Set ETF_OFFICIAL_ENDPOINT_HOLDINGS_PATH.")


def endpoint_as_of_from_payload(payload: object, as_of_path: str, fallback_date: str) -> str:
    if as_of_path:
        value = resolve_json_path(payload, as_of_path)
        return normalize_snapshot_as_of(value)
    if isinstance(payload, dict):
        candidate = payload.get("asOf") or payload.get("date")
        if candidate:
            return normalize_snapshot_as_of(candidate)
    return normalize_snapshot_as_of(fallback_date)


def endpoint_declared_count(payload: object, rows, declared_count_path: str) -> int:
    if declared_count_path:
        value = resolve_json_path(payload, declared_count_path)
        return int(value)
    if isinstance(rows, list):
        return len(rows)
    if isinstance(rows, dict):
        return len(rows)
    return 0


def normalize_endpoint_rows(
    rows,
    code_field: str,
    weight_field: str,
    name_field: str,
    shares_field: str,
    price_field: str,
) -> tuple[dict[str, float], list[dict]]:
    if isinstance(rows, dict):
        return normalize_holdings_map(rows), []

    if not isinstance(rows, list):
        raise ValueError("Holdings rows must be a list or an object map.")

    holdings: dict[str, float] = {}
    details: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = normalize_code(str(row.get(code_field, "")))
        if not code:
            continue
        if weight_field not in row:
            continue
        try:
            weight = parse_weight_value(row.get(weight_field))
        except (TypeError, ValueError):
            raise ValueError(f"Invalid weight field for {code}: {row.get(weight_field)!r}") from None
        holdings[code] = weight
        details.append(
            {
                "code": code,
                "name": str(row.get(name_field, code) or code),
                "weight": weight,
                "shares": str(row.get(shares_field, "") or ""),
                "price": str(row.get(price_field, "") or ""),
            }
        )

    if not holdings:
        raise ValueError("No valid holdings rows were parsed from endpoint payload.")
    return holdings, details


OFFICIAL_HTML_CODE_LABELS = {"商品代碼", "股票代碼", "股票代號", "債券代碼", "債券代號", "代號", "Code"}
OFFICIAL_HTML_NAME_LABELS = {"商品名稱", "股票名稱", "債券名稱", "名稱", "Name"}
OFFICIAL_HTML_SHARES_LABELS = {"商品數量", "股數", "數量", "持有數", "面額", "Qty", "Quantity"}
OFFICIAL_HTML_WEIGHT_LABELS = {"商品權重", "權重", "持股比重", "持股權重", "持股權重(%)", "Weight"}
OFFICIAL_HTML_ALL_LABELS = (
    OFFICIAL_HTML_CODE_LABELS
    | OFFICIAL_HTML_NAME_LABELS
    | OFFICIAL_HTML_SHARES_LABELS
    | OFFICIAL_HTML_WEIGHT_LABELS
    | {"商品年月", "交易日期", "交易日期:"}
)


def normalize_html_label(text: str) -> str:
    return str(text or "").strip().replace("：", ":").rstrip(":").strip()


def is_official_html_label(text: str) -> bool:
    return normalize_html_label(text) in OFFICIAL_HTML_ALL_LABELS


def value_after_html_label(lines: list[str], index: int, labels: set[str]) -> str:
    current = str(lines[index] if 0 <= index < len(lines) else "").strip()
    normalized_current = normalize_html_label(current)
    normalized_labels = {normalize_html_label(label) for label in labels}

    for label in normalized_labels:
        if normalized_current == label:
            break
        if normalized_current.startswith(label):
            rest = current[len(label):].strip(" :：")
            if rest:
                return rest

    next_index = index + 1
    if next_index >= len(lines):
        return ""
    candidate = str(lines[next_index] or "").strip()
    if is_official_html_label(candidate):
        return ""
    return candidate


def find_labeled_value_until_next_code(lines: list[str], start: int, labels: set[str], max_distance: int = 10) -> str:
    stop = min(len(lines), start + max_distance + 1)
    for index in range(start + 1, stop):
        normalized = normalize_html_label(lines[index])
        if normalized in {normalize_html_label(label) for label in OFFICIAL_HTML_CODE_LABELS}:
            return ""
        if normalized in {normalize_html_label(label) for label in labels}:
            return value_after_html_label(lines, index, labels)
    return ""


def extract_official_html_as_of(lines: list[str], fallback_date: str) -> str:
    for index, line in enumerate(lines):
        normalized = normalize_html_label(line)
        if normalized == "交易日期":
            candidate = value_after_html_label(lines, index, {"交易日期"})
            normalized_date = safe_import_date(candidate)
            if normalized_date:
                return normalized_date
        match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", str(line))
        if match and any(keyword in str(line) for keyword in {"交易日期", "公告日期", "資料日期"}):
            return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return normalize_snapshot_as_of(fallback_date)


class HTMLTableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.table_depth = 0
        self.current_table: list[list[str]] | None = None
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.tables: list[list[list[str]]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "table":
            self.table_depth += 1
            if self.table_depth == 1:
                self.current_table = []
        elif self.table_depth and normalized_tag == "tr":
            self.current_row = []
        elif self.table_depth and normalized_tag in {"td", "th"}:
            self.current_cell = []
        elif self.current_cell is not None and normalized_tag == "br":
            self.current_cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if self.table_depth and normalized_tag in {"td", "th"} and self.current_cell is not None:
            value = " ".join("".join(self.current_cell).split())
            if self.current_row is not None:
                self.current_row.append(value)
            self.current_cell = None
        elif self.table_depth and normalized_tag == "tr":
            if self.current_table is not None and self.current_row and any(self.current_row):
                self.current_table.append(self.current_row)
            self.current_row = None
        elif normalized_tag == "table" and self.table_depth:
            if self.table_depth == 1 and self.current_table:
                self.tables.append(self.current_table)
            self.current_table = None
            self.table_depth -= 1


def normalize_official_table_header(value: str) -> str:
    return re.sub(r"[\s()（）%％:_-]", "", str(value or "")).lower()


def normalize_official_holding_identifier(value: str) -> str:
    return " ".join(str(value or "").strip().upper().split())


def is_official_holding_identifier(value: str) -> bool:
    identifier = normalize_official_holding_identifier(value)
    return bool(
        CODE_PATTERN.fullmatch(identifier)
        or re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", identifier)
        or re.fullmatch(r"[A-Z0-9][A-Z0-9./-]{0,15} [A-Z]{1,4}", identifier)
    )


def extract_official_html_table_holdings(markup: str) -> tuple[dict[str, float], list[dict]]:
    extractor = HTMLTableExtractor()
    extractor.feed(markup)
    holdings: dict[str, float] = {}
    details_by_code: dict[str, dict] = {}
    for table in extractor.tables:
        header_text = " ".join(cell for row in table[:3] for cell in row)
        normalized_header = normalize_official_table_header(header_text)
        has_code_header = any(token in normalized_header for token in {"商品代碼", "股票代碼", "股票代號", "債券代碼", "code"})
        has_weight_header = any(token in normalized_header for token in {"商品權重", "持股權重", "持股比重", "weight"})
        if not has_code_header or not has_weight_header:
            continue
        for row in table:
            holding_index = next(
                (
                    index
                    for index, cell in enumerate(row)
                    if is_official_holding_identifier(cell)
                ),
                -1,
            )
            if holding_index < 0:
                continue
            holding_code = normalize_official_holding_identifier(row[holding_index])
            weight_index = next(
                (
                    index
                    for index in range(holding_index + 1, len(row))
                    if str(row[index]).strip().endswith(("%", "％"))
                ),
                -1,
            )
            if weight_index < 0:
                continue
            try:
                weight = parse_weight_value(row[weight_index])
            except (TypeError, ValueError):
                continue
            name = holding_code
            if holding_index + 1 < weight_index:
                name = str(row[holding_index + 1] or holding_code).strip() or holding_code
            shares = ""
            if weight_index + 1 < len(row):
                shares = re.sub(r"[^0-9.-]", "", str(row[weight_index + 1]))
            holdings[holding_code] = weight
            details_by_code[holding_code] = {
                "code": holding_code,
                "name": name,
                "weight": weight,
                "shares": shares,
                "price": "",
            }
    return holdings, list(details_by_code.values())


def normalize_official_security_name(value: str) -> str:
    return re.sub(r"[\s*＊]+", "", str(value or "")).strip().lower()


def extract_official_html_named_table_holdings(
    markup: str,
    stock_universe: dict[str, dict] | None = None,
) -> tuple[dict[str, float], list[dict], list[str]]:
    """Parse issuer top-holdings tables that publish names and weights without security codes."""
    extractor = HTMLTableExtractor()
    extractor.feed(markup)
    stock_universe = stock_universe if stock_universe is not None else load_stock_universe()
    code_by_name = {
        normalize_official_security_name(row.get("name")): normalize_code(code)
        for code, row in stock_universe.items()
        if isinstance(row, dict) and normalize_official_security_name(row.get("name"))
    }

    for table in extractor.tables:
        if not table:
            continue
        header = [normalize_official_table_header(cell) for cell in table[0]]
        name_index = next((index for index, value in enumerate(header) if value in {"投資標的", "持有標的"}), -1)
        weight_index = next((index for index, value in enumerate(header) if value in {"比例", "權重", "持股權重", "持股比重"}), -1)
        if name_index < 0 or weight_index < 0:
            continue

        holdings: dict[str, float] = {}
        details: list[dict] = []
        unresolved_names: list[str] = []
        for row in table[1:]:
            if max(name_index, weight_index) >= len(row):
                continue
            name = str(row[name_index] or "").strip()
            normalized_name = normalize_official_security_name(name)
            if not normalized_name:
                continue
            try:
                weight = parse_weight_value(row[weight_index])
            except (TypeError, ValueError):
                continue
            holding_code = code_by_name.get(normalized_name)
            if not holding_code:
                holding_code = f"NAME:{name}"
                unresolved_names.append(name)
            holdings[holding_code] = weight
            details.append(
                {
                    "code": holding_code,
                    "name": name,
                    "weight": weight,
                    "shares": "",
                    "price": "",
                }
            )
        if holdings:
            return holdings, details, unresolved_names
    return {}, [], []


def extract_official_html_flat_holdings(lines: list[str]) -> tuple[dict[str, float], list[dict]]:
    """Parse responsive issuer tables rendered as adjacent div text rather than table tags."""
    normalized_code_labels = {normalize_official_table_header(label) for label in OFFICIAL_HTML_CODE_LABELS}
    normalized_name_labels = {normalize_official_table_header(label) for label in OFFICIAL_HTML_NAME_LABELS}
    normalized_weight_labels = {normalize_official_table_header(label) for label in OFFICIAL_HTML_WEIGHT_LABELS}
    normalized_share_labels = {normalize_official_table_header(label) for label in OFFICIAL_HTML_SHARES_LABELS}
    holdings: dict[str, float] = {}
    details_by_code: dict[str, dict] = {}

    for header_start, line in enumerate(lines):
        if normalize_official_table_header(line) not in normalized_code_labels:
            continue
        header_stop = min(len(lines), header_start + 10)
        header_tokens = {
            normalize_official_table_header(value)
            for value in lines[header_start:header_stop]
        }
        if not (header_tokens & normalized_name_labels and header_tokens & normalized_weight_labels):
            continue

        data_start = header_start + 1
        while data_start < header_stop:
            token = normalize_official_table_header(lines[data_start])
            if token not in normalized_code_labels | normalized_name_labels | normalized_weight_labels | normalized_share_labels:
                break
            data_start += 1

        index = data_start
        while index + 2 < len(lines):
            normalized_line = normalize_official_table_header(lines[index])
            if index > data_start and normalized_line in normalized_code_labels:
                break
            holding_code = normalize_official_holding_identifier(lines[index])
            if not is_official_holding_identifier(holding_code):
                index += 1
                continue
            name = str(lines[index + 1] or "").strip()
            weight_index = next(
                (
                    candidate_index
                    for candidate_index in range(index + 2, min(len(lines), index + 7))
                    if str(lines[candidate_index] or "").strip().endswith(("%", "％"))
                    and not any(
                        is_official_holding_identifier(lines[intermediate_index])
                        for intermediate_index in range(index + 2, candidate_index)
                    )
                ),
                -1,
            )
            if not name or is_official_html_label(name) or weight_index < 0:
                index += 1
                continue
            weight_raw = str(lines[weight_index] or "").strip()
            try:
                weight = parse_weight_value(weight_raw)
            except (TypeError, ValueError):
                index += 1
                continue

            shares = ""
            if header_tokens & normalized_share_labels:
                shares_index = weight_index + 1
                if "面額" in header_tokens and index + 2 < weight_index:
                    shares_index = index + 2
            else:
                shares_index = -1
            if 0 <= shares_index < len(lines):
                shares_raw = str(lines[shares_index] or "").strip()
                next_value_starts_row = (
                    is_official_holding_identifier(shares_raw)
                    and shares_index + 2 < len(lines)
                    and str(lines[shares_index + 2] or "").strip().endswith(("%", "％"))
                )
                if not next_value_starts_row and re.fullmatch(r"[-+]?\d[\d,]*(?:\.\d+)?", shares_raw):
                    shares = shares_raw.replace(",", "")
            previous = details_by_code.get(holding_code, {})
            holdings[holding_code] = weight
            details_by_code[holding_code] = {
                "code": holding_code,
                "name": name,
                "weight": weight,
                "shares": shares or str(previous.get("shares", "")),
                "price": "",
            }
            index = weight_index + 1

    return holdings, list(details_by_code.values())


def parse_official_html_labeled_holdings(
    code: str,
    markup: str,
    fetch_url: str,
    fallback_date: str,
    source_label: str,
) -> dict:
    lines = html_to_lines(markup)
    as_of = extract_official_html_as_of(lines, fallback_date)
    holdings: dict[str, float] = {}
    details: list[dict] = []

    table_holdings, table_details = extract_official_html_table_holdings(markup)
    holdings.update(table_holdings)
    details.extend(table_details)

    flat_holdings, flat_details = extract_official_html_flat_holdings(lines)
    holdings.update(flat_holdings)
    for row in flat_details:
        existing_index = next((row_index for row_index, existing in enumerate(details) if existing.get("code") == row.get("code")), -1)
        if existing_index >= 0:
            if not row.get("shares"):
                row["shares"] = details[existing_index].get("shares", "")
            details[existing_index] = row
        else:
            details.append(row)

    unresolved_names: list[str] = []
    if not holdings:
        named_holdings, named_details, unresolved_names = extract_official_html_named_table_holdings(markup)
        holdings.update(named_holdings)
        details.extend(named_details)

    normalized_code_labels = {normalize_html_label(label) for label in OFFICIAL_HTML_CODE_LABELS}
    for index, line in enumerate(lines):
        if normalize_html_label(line) not in normalized_code_labels:
            continue
        holding_code = normalize_code(value_after_html_label(lines, index, OFFICIAL_HTML_CODE_LABELS))
        if not holding_code or is_official_html_label(holding_code):
            continue
        weight_raw = find_labeled_value_until_next_code(lines, index, OFFICIAL_HTML_WEIGHT_LABELS)
        if not weight_raw:
            continue
        try:
            weight = parse_weight_value(weight_raw)
        except (TypeError, ValueError):
            continue

        name = find_labeled_value_until_next_code(lines, index, OFFICIAL_HTML_NAME_LABELS) or holding_code
        shares = find_labeled_value_until_next_code(lines, index, OFFICIAL_HTML_SHARES_LABELS).replace(",", "")
        holdings[holding_code] = weight
        replacement = {
            "code": holding_code,
            "name": name,
            "weight": weight,
            "shares": shares,
            "price": "",
        }
        existing_index = next((row_index for row_index, row in enumerate(details) if row.get("code") == holding_code), -1)
        if existing_index >= 0:
            details[existing_index] = replacement
        else:
            details.append(replacement)

    if not holdings:
        raise ValueError("No official HTML holdings rows were parsed.")

    parsed_count = len(holdings)
    warnings = [
        "Official HTML page parser cannot prove full row coverage; prefer official CSV/JSON/PCF export when available."
    ]
    if unresolved_names:
        warnings.append(
            f"{len(unresolved_names)} holding names did not match the local stock universe and use NAME: identifiers."
        )
    return {
        "code": code,
        "source": source_label,
        "adapter": "official_endpoint",
        "asOf": as_of,
        "holdings": holdings,
        "holdingDetails": details,
        "declaredHoldingCount": parsed_count,
        "parsedHoldingCount": parsed_count,
        "coverage": "partial_official_page",
        "fetchUrl": fetch_url,
        "warnings": warnings,
    }


def pick_setting(preferred: str, fallback: str) -> str:
    value = str(preferred or "").strip()
    return value if value else str(fallback or "").strip()


def parse_csv_dict_rows(csv_text: str) -> list[dict]:
    sample = (csv_text or "")[:4096]
    dialect = csv.excel
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(csv_text), dialect=dialect)
    rows = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        normalized = {}
        for key, value in row.items():
            if key is None:
                continue
            clean_key = str(key).replace("\ufeff", "").strip()
            normalized[clean_key] = value
        rows.append(normalized)
    return rows


def build_snapshot_adapter_payload(code: str, row: dict, source_label: str, adapter_name: str, fetch_url: str) -> dict:
    holdings = normalize_holdings_map(row.get("holdings", {}))
    as_of = normalize_snapshot_as_of(row.get("asOf"))
    declared = int(row.get("declaredHoldingCount") or len(holdings))
    parsed_count = len(holdings)
    coverage = str(row.get("coverage", "")).strip() or ("full" if declared == parsed_count else "partial_official_file")
    details = row.get("holdingDetails", [])
    if not isinstance(details, list):
        details = []
    return {
        "code": code,
        "source": source_label,
        "adapter": adapter_name,
        "asOf": as_of,
        "holdings": holdings,
        "holdingDetails": details,
        "declaredHoldingCount": declared,
        "parsedHoldingCount": parsed_count,
        "coverage": coverage,
        "fetchUrl": fetch_url,
        "attempts": 1,
    }


class OfficialSnapshotFileAdapter:
    name = "official_snapshot_file"
    source_label = "Official PCF/TWSE snapshot file"

    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self.snapshot_dir = snapshot_dir or OFFICIAL_SNAPSHOT_DIR

    def snapshot_path(self, code: str) -> Path:
        return self.snapshot_dir / f"{code}.json"

    def fetch_one(self, code: str) -> dict:
        path = self.snapshot_path(code)
        if not path.exists():
            raise RuntimeError(f"Snapshot file not found: {path}")
        try:
            payload = read_json_file_strict(path)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Invalid snapshot file for {code}: {exc}") from exc
        row = parse_snapshot_entry_for_code(payload, code)
        return build_snapshot_adapter_payload(
            code=code,
            row=row,
            source_label=self.source_label,
            adapter_name=self.name,
            fetch_url=str(path),
        )


class OfficialEndpointAdapter:
    name = "official_endpoint"
    source_label = "Official PCF/TWSE endpoint"

    def __init__(
        self,
        url_template: str | None = None,
        data_format: str | None = None,
        headers: dict[str, str] | None = None,
        holdings_path: str | None = None,
        as_of_path: str | None = None,
        declared_count_path: str | None = None,
        code_field: str | None = None,
        weight_field: str | None = None,
        name_field: str | None = None,
        shares_field: str | None = None,
        price_field: str | None = None,
        default_as_of: str | None = None,
    ) -> None:
        self.url_template = (url_template or OFFICIAL_ENDPOINT_URL_TEMPLATE).strip()
        self.data_format = (data_format or OFFICIAL_ENDPOINT_FORMAT).strip().lower() or "json"
        self.headers = headers or OFFICIAL_ENDPOINT_HEADERS
        self.holdings_path = (holdings_path or OFFICIAL_ENDPOINT_HOLDINGS_PATH).strip()
        self.as_of_path = (as_of_path or OFFICIAL_ENDPOINT_ASOF_PATH).strip()
        self.declared_count_path = (declared_count_path or OFFICIAL_ENDPOINT_DECLARED_COUNT_PATH).strip()
        self.code_field = (code_field or OFFICIAL_ENDPOINT_CODE_FIELD).strip()
        self.weight_field = (weight_field or OFFICIAL_ENDPOINT_WEIGHT_FIELD).strip()
        self.name_field = (name_field or OFFICIAL_ENDPOINT_NAME_FIELD).strip()
        self.shares_field = (shares_field or OFFICIAL_ENDPOINT_SHARES_FIELD).strip()
        self.price_field = (price_field or OFFICIAL_ENDPOINT_PRICE_FIELD).strip()
        self.default_as_of = (default_as_of or OFFICIAL_ENDPOINT_DATE).strip() or time.strftime("%Y-%m-%d")

    def build_url(self, code: str) -> str:
        if not self.url_template:
            raise RuntimeError("ETF_OFFICIAL_ENDPOINT_URL_TEMPLATE is required for official endpoint adapter.")
        return self.url_template.format(code=code, date=self.default_as_of)

    def parse_json_payload(self, code: str, payload: object, fetch_url: str) -> dict:
        rows = endpoint_rows_from_payload(payload, self.holdings_path)
        as_of = endpoint_as_of_from_payload(payload, self.as_of_path, self.default_as_of)
        declared = endpoint_declared_count(payload, rows, self.declared_count_path)
        holdings, details = normalize_endpoint_rows(
            rows=rows,
            code_field=self.code_field,
            weight_field=self.weight_field,
            name_field=self.name_field,
            shares_field=self.shares_field,
            price_field=self.price_field,
        )
        parsed_count = len(holdings)
        coverage = "full" if declared and declared == parsed_count else "partial_official_endpoint"
        return {
            "code": code,
            "source": self.source_label,
            "adapter": self.name,
            "asOf": as_of,
            "holdings": holdings,
            "holdingDetails": details,
            "declaredHoldingCount": declared or parsed_count,
            "parsedHoldingCount": parsed_count,
            "coverage": coverage,
            "fetchUrl": fetch_url,
            "attempts": 1,
        }

    def parse_csv_payload(self, code: str, csv_text: str, fetch_url: str) -> dict:
        rows = parse_csv_dict_rows(csv_text)
        if not rows:
            raise ValueError("CSV endpoint returned no rows.")
        as_of = self.default_as_of
        if self.as_of_path and rows[0].get(self.as_of_path):
            as_of = normalize_snapshot_as_of(rows[0].get(self.as_of_path))
        holdings, details = normalize_endpoint_rows(
            rows=rows,
            code_field=self.code_field,
            weight_field=self.weight_field,
            name_field=self.name_field,
            shares_field=self.shares_field,
            price_field=self.price_field,
        )
        parsed_count = len(holdings)
        declared = parsed_count
        return {
            "code": code,
            "source": self.source_label,
            "adapter": self.name,
            "asOf": as_of,
            "holdings": holdings,
            "holdingDetails": details,
            "declaredHoldingCount": declared,
            "parsedHoldingCount": parsed_count,
            "coverage": "full",
            "fetchUrl": fetch_url,
            "attempts": 1,
        }

    def parse_html_payload(self, code: str, markup: str, fetch_url: str) -> dict:
        return parse_official_html_labeled_holdings(
            code=code,
            markup=markup,
            fetch_url=fetch_url,
            fallback_date=self.default_as_of,
            source_label=self.source_label,
        )

    def fetch_one(self, code: str) -> dict:
        url = self.build_url(code)
        body, attempts = get_url_with_retry(url=url, headers=self.headers)
        if self.data_format == "json":
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Official endpoint returned invalid JSON for {code}: {exc}") from exc
            parsed = self.parse_json_payload(code=code, payload=payload, fetch_url=url)
        elif self.data_format == "csv":
            parsed = self.parse_csv_payload(code=code, csv_text=body, fetch_url=url)
        elif self.data_format == "html":
            parsed = self.parse_html_payload(code=code, markup=body, fetch_url=url)
        else:
            raise RuntimeError(f"Unsupported ETF_OFFICIAL_ENDPOINT_FORMAT: {self.data_format}")
        parsed["attempts"] = attempts
        return parsed


class OfficialPcfTwseAdapter:
    name = "official_pcf_twse"
    source_label = "Official PCF/TWSE direct endpoint"

    def __init__(
        self,
        pcf_url_template: str | None = None,
        twse_url_template: str | None = None,
        fallback_endpoint_url_template: str | None = None,
        default_as_of: str | None = None,
    ) -> None:
        self.default_as_of = (default_as_of or OFFICIAL_ENDPOINT_DATE).strip() or time.strftime("%Y-%m-%d")
        self.profile_adapters = []

        pcf_template = (
            str(pcf_url_template).strip() if pcf_url_template is not None else str(OFFICIAL_PCF_URL_TEMPLATE).strip()
        )
        twse_template = (
            str(twse_url_template).strip() if twse_url_template is not None else str(OFFICIAL_TWSE_URL_TEMPLATE).strip()
        )
        fallback_template = (
            str(fallback_endpoint_url_template).strip()
            if fallback_endpoint_url_template is not None
            else str(OFFICIAL_ENDPOINT_URL_TEMPLATE).strip()
        )

        pcf_adapter = self.build_profile_adapter(
            profile_name="pcf",
            url_template=pcf_template,
            data_format=pick_setting(OFFICIAL_PCF_FORMAT, OFFICIAL_ENDPOINT_FORMAT),
            headers=OFFICIAL_PCF_HEADERS if OFFICIAL_PCF_HEADERS else OFFICIAL_ENDPOINT_HEADERS,
            holdings_path=pick_setting(OFFICIAL_PCF_HOLDINGS_PATH, OFFICIAL_ENDPOINT_HOLDINGS_PATH),
            as_of_path=pick_setting(OFFICIAL_PCF_ASOF_PATH, OFFICIAL_ENDPOINT_ASOF_PATH),
            declared_count_path=pick_setting(OFFICIAL_PCF_DECLARED_COUNT_PATH, OFFICIAL_ENDPOINT_DECLARED_COUNT_PATH),
            code_field=pick_setting(OFFICIAL_PCF_CODE_FIELD, OFFICIAL_ENDPOINT_CODE_FIELD),
            weight_field=pick_setting(OFFICIAL_PCF_WEIGHT_FIELD, OFFICIAL_ENDPOINT_WEIGHT_FIELD),
            name_field=pick_setting(OFFICIAL_PCF_NAME_FIELD, OFFICIAL_ENDPOINT_NAME_FIELD),
            shares_field=pick_setting(OFFICIAL_PCF_SHARES_FIELD, OFFICIAL_ENDPOINT_SHARES_FIELD),
            price_field=pick_setting(OFFICIAL_PCF_PRICE_FIELD, OFFICIAL_ENDPOINT_PRICE_FIELD),
        )
        if pcf_adapter:
            self.profile_adapters.append(pcf_adapter)

        twse_adapter = self.build_profile_adapter(
            profile_name="twse",
            url_template=twse_template,
            data_format=pick_setting(OFFICIAL_TWSE_FORMAT, OFFICIAL_ENDPOINT_FORMAT),
            headers=OFFICIAL_TWSE_HEADERS if OFFICIAL_TWSE_HEADERS else OFFICIAL_ENDPOINT_HEADERS,
            holdings_path=pick_setting(OFFICIAL_TWSE_HOLDINGS_PATH, OFFICIAL_ENDPOINT_HOLDINGS_PATH),
            as_of_path=pick_setting(OFFICIAL_TWSE_ASOF_PATH, OFFICIAL_ENDPOINT_ASOF_PATH),
            declared_count_path=pick_setting(OFFICIAL_TWSE_DECLARED_COUNT_PATH, OFFICIAL_ENDPOINT_DECLARED_COUNT_PATH),
            code_field=pick_setting(OFFICIAL_TWSE_CODE_FIELD, OFFICIAL_ENDPOINT_CODE_FIELD),
            weight_field=pick_setting(OFFICIAL_TWSE_WEIGHT_FIELD, OFFICIAL_ENDPOINT_WEIGHT_FIELD),
            name_field=pick_setting(OFFICIAL_TWSE_NAME_FIELD, OFFICIAL_ENDPOINT_NAME_FIELD),
            shares_field=pick_setting(OFFICIAL_TWSE_SHARES_FIELD, OFFICIAL_ENDPOINT_SHARES_FIELD),
            price_field=pick_setting(OFFICIAL_TWSE_PRICE_FIELD, OFFICIAL_ENDPOINT_PRICE_FIELD),
        )
        if twse_adapter:
            self.profile_adapters.append(twse_adapter)

        if fallback_template and fallback_template not in {pcf_template, twse_template}:
            fallback_adapter = self.build_profile_adapter(
                profile_name="endpoint",
                url_template=fallback_template,
                data_format=OFFICIAL_ENDPOINT_FORMAT,
                headers=OFFICIAL_ENDPOINT_HEADERS,
                holdings_path=OFFICIAL_ENDPOINT_HOLDINGS_PATH,
                as_of_path=OFFICIAL_ENDPOINT_ASOF_PATH,
                declared_count_path=OFFICIAL_ENDPOINT_DECLARED_COUNT_PATH,
                code_field=OFFICIAL_ENDPOINT_CODE_FIELD,
                weight_field=OFFICIAL_ENDPOINT_WEIGHT_FIELD,
                name_field=OFFICIAL_ENDPOINT_NAME_FIELD,
                shares_field=OFFICIAL_ENDPOINT_SHARES_FIELD,
                price_field=OFFICIAL_ENDPOINT_PRICE_FIELD,
            )
            if fallback_adapter:
                self.profile_adapters.append(fallback_adapter)

    def build_profile_adapter(
        self,
        profile_name: str,
        url_template: str,
        data_format: str,
        headers: dict[str, str],
        holdings_path: str,
        as_of_path: str,
        declared_count_path: str,
        code_field: str,
        weight_field: str,
        name_field: str,
        shares_field: str,
        price_field: str,
    ) -> dict | None:
        template = str(url_template or "").strip()
        if not template:
            return None
        endpoint = OfficialEndpointAdapter(
            url_template=template,
            data_format=data_format,
            headers=headers,
            holdings_path=holdings_path,
            as_of_path=as_of_path,
            declared_count_path=declared_count_path,
            code_field=code_field,
            weight_field=weight_field,
            name_field=name_field,
            shares_field=shares_field,
            price_field=price_field,
            default_as_of=self.default_as_of,
        )
        return {"profile": profile_name, "endpoint": endpoint}

    def fetch_one(self, code: str) -> dict:
        if not self.profile_adapters:
            raise RuntimeError(
                "No direct official endpoint is configured. "
                "Set ETF_OFFICIAL_PCF_URL_TEMPLATE or ETF_OFFICIAL_TWSE_URL_TEMPLATE."
            )

        failures = []
        warnings = []
        for profile_row in self.profile_adapters:
            profile = profile_row["profile"]
            endpoint = profile_row["endpoint"]
            try:
                payload = endpoint.fetch_one(code)
                payload["adapter"] = self.name
                payload["source"] = f"{self.source_label} ({profile})"
                payload["profile"] = profile
                payload_warnings = payload.get("warnings", [])
                if not isinstance(payload_warnings, list):
                    payload_warnings = [str(payload_warnings)]
                if warnings:
                    payload_warnings.extend(warnings)
                if payload_warnings:
                    payload["warnings"] = payload_warnings
                return payload
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{profile}: {exc}")
                warnings.append(f"{profile} failed; trying next source.")

        raise RuntimeError(
            f"Official PCF/TWSE fetch failed for {code}. "
            f"Tried profiles: {', '.join(failures)}"
        )


def official_registry_source_matches(source: dict, code: str, universe_row: dict | None) -> bool:
    if not isinstance(source, dict) or source.get("enabled") is False:
        return False
    normalized_code = normalize_code(code)
    urls_by_code = source.get("urlsByCode")
    if isinstance(urls_by_code, dict) and urls_by_code:
        configured_url_codes = {normalize_code(str(item)) for item in urls_by_code}
        return normalized_code in configured_url_codes
    configured_codes = source.get("codes")
    if isinstance(configured_codes, list) and configured_codes:
        return normalized_code in {normalize_code(str(item)) for item in configured_codes}

    prefixes = source.get("codePrefixes")
    if isinstance(prefixes, list) and prefixes:
        if not any(normalized_code.startswith(normalize_code(str(prefix))) for prefix in prefixes):
            return False

    if universe_row is None:
        return bool(prefixes)

    haystack = " ".join(
        str(universe_row.get(field, ""))
        for field in ("code", "name", "issuer", "source", "benchmark")
    ).lower()
    issuer_contains = source.get("issuerContains")
    if isinstance(issuer_contains, list) and issuer_contains:
        return any(str(value).strip().lower() in haystack for value in issuer_contains if str(value).strip())
    name_contains = source.get("nameContains")
    if isinstance(name_contains, list) and name_contains:
        return any(str(value).strip().lower() in haystack for value in name_contains if str(value).strip())
    return bool(prefixes)


def official_registry_candidates(code: str) -> list[dict]:
    registry = load_official_source_registry()
    universe_index = build_universe_index(load_etf_universe())
    universe_row = universe_index.get(normalize_code(code))
    sources = registry.get("sources", [])
    if not isinstance(sources, list):
        return []
    candidates = [
        source
        for source in sources
        if isinstance(source, dict) and official_registry_source_matches(source, code, universe_row)
    ]
    candidates.sort(key=lambda row: int(row.get("priority", 100)))
    return candidates


class OfficialRegistryAdapter:
    name = "official_registry"
    source_label = "Official source registry"

    def build_source_adapter(self, source: dict, code: str = "") -> OfficialEndpointAdapter:
        url_template = ""
        urls_by_code = source.get("urlsByCode")
        if isinstance(urls_by_code, dict) and code:
            normalized_urls = {normalize_code(str(key)): str(value).strip() for key, value in urls_by_code.items()}
            url_template = normalized_urls.get(normalize_code(code), "")
        if not url_template:
            url_template = str(source.get("urlTemplate") or source.get("url") or "").strip()
        if not url_template:
            raise ValueError("Registry source is missing urlTemplate.")
        return OfficialEndpointAdapter(
            url_template=url_template,
            data_format=str(source.get("format") or "json").strip().lower(),
            headers=parse_json_object_env(json.dumps(source.get("headers", {}), ensure_ascii=False))
            if isinstance(source.get("headers"), dict)
            else parse_json_object_env(str(source.get("headers", ""))),
            holdings_path=str(source.get("holdingsPath") or ""),
            as_of_path=str(source.get("asOfPath") or ""),
            declared_count_path=str(source.get("declaredCountPath") or ""),
            code_field=str(source.get("codeField") or OFFICIAL_ENDPOINT_CODE_FIELD),
            weight_field=str(source.get("weightField") or OFFICIAL_ENDPOINT_WEIGHT_FIELD),
            name_field=str(source.get("nameField") or OFFICIAL_ENDPOINT_NAME_FIELD),
            shares_field=str(source.get("sharesField") or OFFICIAL_ENDPOINT_SHARES_FIELD),
            price_field=str(source.get("priceField") or OFFICIAL_ENDPOINT_PRICE_FIELD),
            default_as_of=str(source.get("date") or OFFICIAL_ENDPOINT_DATE or time.strftime("%Y-%m-%d")),
        )

    def fetch_one(self, code: str) -> dict:
        candidates = official_registry_candidates(code)
        if not candidates:
            raise RuntimeError(
                f"No official registry source is configured for {code}. "
                f"Add a matching row to {OFFICIAL_SOURCE_REGISTRY_FILE}."
            )

        failures = []
        warnings = []
        for source in candidates:
            name = str(source.get("name") or source.get("urlTemplate") or "source").strip()
            try:
                adapter = self.build_source_adapter(source, code=code)
                payload = adapter.fetch_one(code)
                payload["adapter"] = self.name
                payload["source"] = f"{self.source_label} ({name})"
                payload["registrySource"] = name
                if warnings:
                    payload_warnings = payload.get("warnings", [])
                    if not isinstance(payload_warnings, list):
                        payload_warnings = [str(payload_warnings)]
                    payload_warnings.extend(warnings)
                    payload["warnings"] = payload_warnings
                return payload
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: {exc}")
                warnings.append(f"{name} failed; trying next registry source.")
        raise RuntimeError(f"Official registry fetch failed for {code}. Tried: {', '.join(failures)}")


def select_live_adapter(adapter_name: str | None = None) -> HoldingsAdapter:
    normalized = (adapter_name or LIVE_FETCH_ADAPTER).strip().lower()
    if normalized in {"etfinfo", "etfinfo_public_page"}:
        return ETFInfoPublicPageAdapter()
    if normalized in {"official_registry", "official_sources", "official_source_registry"}:
        return OfficialRegistryAdapter()
    if normalized in {"official_endpoint", "official_direct", "pcf_endpoint"}:
        return OfficialEndpointAdapter()
    if normalized in {"official_pcf_twse", "pcf_twse", "official_pcf_stub", "pcf_stub"}:
        return OfficialPcfTwseAdapter()
    if normalized in {"official", "pcf"}:
        registry = load_official_source_registry()
        if registry.get("sources"):
            return OfficialRegistryAdapter()
        if OFFICIAL_PCF_URL_TEMPLATE or OFFICIAL_TWSE_URL_TEMPLATE:
            return OfficialPcfTwseAdapter()
        if OFFICIAL_ENDPOINT_URL_TEMPLATE:
            return OfficialEndpointAdapter()
        return OfficialSnapshotFileAdapter()
    if normalized in {"official_snapshot_file", "official_file", "pcf_file"}:
        return OfficialSnapshotFileAdapter()
    raise ValueError(f"Unsupported ETF_HOLDINGS_ADAPTER: {normalized}")


def live_fetch_settings() -> dict:
    return {
        "adapter": LIVE_FETCH_ADAPTER,
        "timeoutSeconds": LIVE_FETCH_TIMEOUT_SECONDS,
        "retries": LIVE_FETCH_RETRIES,
        "backoffMs": LIVE_FETCH_BACKOFF_MS,
        "requireFullHoldings": LIVE_REQUIRE_FULL_HOLDINGS,
        "minDeclaredHoldings": LIVE_MIN_DECLARED_HOLDINGS,
        "minParsedHoldings": LIVE_MIN_PARSED_HOLDINGS,
        "officialSnapshotDir": str(OFFICIAL_SNAPSHOT_DIR),
        "officialEndpointConfigured": bool(OFFICIAL_ENDPOINT_URL_TEMPLATE),
        "officialEndpointFormat": OFFICIAL_ENDPOINT_FORMAT,
        "officialEndpointHoldingsPath": OFFICIAL_ENDPOINT_HOLDINGS_PATH,
        "officialEndpointAsOfPath": OFFICIAL_ENDPOINT_ASOF_PATH,
        "officialPcfConfigured": bool(OFFICIAL_PCF_URL_TEMPLATE),
        "officialPcfFormat": OFFICIAL_PCF_FORMAT,
        "officialTwseConfigured": bool(OFFICIAL_TWSE_URL_TEMPLATE),
        "officialTwseFormat": OFFICIAL_TWSE_FORMAT,
        "officialSourceRegistryFile": str(OFFICIAL_SOURCE_REGISTRY_FILE),
        "officialSourceRegistryConfigured": bool(load_official_source_registry().get("sources")),
        "historyRetention": history_retention_settings(),
        "accessLog": access_log_settings(),
        "alertWebhookEnabled": bool(ALERT_WEBHOOK_URL),
    }


def live_fetch_config_status(adapter_name: str | None = None) -> dict:
    adapter_name = (adapter_name or LIVE_FETCH_ADAPTER or "").strip().lower() or "etfinfo_public_page"
    issues: list[str] = []
    warnings: list[str] = []

    if adapter_name in {"etfinfo", "etfinfo_public_page"}:
        pass
    elif adapter_name in {"official_registry", "official_sources", "official_source_registry"}:
        registry = load_official_source_registry()
        validation = validate_official_source_registry(registry, load_etf_universe())
        issues.extend(validation.get("issues", []))
        warnings.extend(validation.get("warnings", []))
    elif adapter_name in {"official_endpoint", "official_direct", "pcf_endpoint"}:
        if not OFFICIAL_ENDPOINT_URL_TEMPLATE:
            issues.append("ETF_OFFICIAL_ENDPOINT_URL_TEMPLATE is required for official_endpoint adapter.")
        if OFFICIAL_ENDPOINT_FORMAT not in {"json", "csv", "html"}:
            issues.append("ETF_OFFICIAL_ENDPOINT_FORMAT must be json, csv, or html.")
        if OFFICIAL_ENDPOINT_FORMAT == "json" and not OFFICIAL_ENDPOINT_HOLDINGS_PATH:
            warnings.append("ETF_OFFICIAL_ENDPOINT_HOLDINGS_PATH is empty; auto-detection will be used.")
    elif adapter_name in {"official_snapshot_file", "official_file", "pcf_file"}:
        if not OFFICIAL_SNAPSHOT_DIR.exists():
            warnings.append(f"Snapshot directory does not exist yet: {OFFICIAL_SNAPSHOT_DIR}")
    elif adapter_name in {"official_pcf_twse", "pcf_twse", "official_pcf_stub", "pcf_stub"}:
        if not OFFICIAL_PCF_URL_TEMPLATE and not OFFICIAL_TWSE_URL_TEMPLATE and not OFFICIAL_ENDPOINT_URL_TEMPLATE:
            issues.append(
                "Direct official adapter requires ETF_OFFICIAL_PCF_URL_TEMPLATE or ETF_OFFICIAL_TWSE_URL_TEMPLATE. "
                "Fallback via ETF_OFFICIAL_ENDPOINT_URL_TEMPLATE is also accepted."
            )
        if OFFICIAL_PCF_URL_TEMPLATE and OFFICIAL_PCF_FORMAT not in {"json", "csv", "html"}:
            issues.append("ETF_OFFICIAL_PCF_FORMAT must be json, csv, or html.")
        if OFFICIAL_TWSE_URL_TEMPLATE and OFFICIAL_TWSE_FORMAT not in {"json", "csv", "html"}:
            issues.append("ETF_OFFICIAL_TWSE_FORMAT must be json, csv, or html.")
    elif adapter_name in {"official", "pcf"}:
        if not OFFICIAL_PCF_URL_TEMPLATE and not OFFICIAL_TWSE_URL_TEMPLATE and not OFFICIAL_ENDPOINT_URL_TEMPLATE and not OFFICIAL_SNAPSHOT_DIR.exists():
            warnings.append("No official endpoint template and no snapshot directory found.")
    else:
        issues.append(f"Unsupported ETF_HOLDINGS_ADAPTER value: {adapter_name}")

    if LIVE_REQUIRE_FULL_HOLDINGS and not adapter_is_official(adapter_name):
        issues.append(
            "ETF_LIVE_REQUIRE_FULL_HOLDINGS=1 requires an official adapter "
            "(official / official_pcf_twse / official_endpoint / official_snapshot_file)."
        )

    if API_AUTH_MODE not in {"off", "write_token", "all_token"}:
        warnings.append("ETF_API_AUTH_MODE should be one of: off, write_token, all_token.")
    if API_AUTH_MODE in {"write_token", "all_token"} and not API_TOKEN:
        warnings.append("ETF_API_AUTH_MODE requires ETF_API_TOKEN to be set.")
    if RATE_LIMIT_ENABLED and RATE_LIMIT_MAX_REQUESTS < 10:
        warnings.append("ETF_RATE_LIMIT_MAX_REQUESTS is very low; verify this is intentional.")

    return {
        "ok": not issues,
        "adapter": adapter_name,
        "issues": issues,
        "warnings": warnings,
        "settings": live_fetch_settings(),
    }


def resolve_probe_code(requested_code: str, available_codes: set[str]) -> str:
    code = normalize_code(requested_code or "")
    if code:
        if code not in available_codes:
            raise ValueError(f"ETF code is not in the configured universe: {code}")
        return code

    for candidate in DEFAULT_CODES:
        if candidate in available_codes:
            return candidate

    if available_codes:
        return sorted(available_codes)[0]
    raise ValueError("No ETF codes are configured in ETF universe.")


def probe_live_fetch_once(code: str, adapter_name: str | None = None) -> dict:
    started_at = time.perf_counter()
    adapter = select_live_adapter(adapter_name)
    row = adapter.fetch_one(code)
    validate_etf_snapshot_row(row)

    holdings = row.get("holdings", {})
    parsed_count = int(row.get("parsedHoldingCount") or len(holdings))
    declared_raw = row.get("declaredHoldingCount")
    try:
        declared_count = int(declared_raw) if declared_raw not in {None, ""} else parsed_count
    except (TypeError, ValueError):
        declared_count = parsed_count
    warnings = row.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    sample_holdings = []
    for stock_code, weight in list(holdings.items())[:5]:
        try:
            normalized_weight = float(weight)
        except (TypeError, ValueError):
            continue
        sample_holdings.append({"code": str(stock_code), "weight": normalized_weight})

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {
        "ok": True,
        "adapter": adapter.name,
        "source": adapter.source_label,
        "code": row.get("code") or code,
        "asOf": row.get("asOf") or "",
        "coverage": row.get("coverage") or "",
        "declaredHoldingCount": declared_count,
        "parsedHoldingCount": parsed_count,
        "fetchUrl": row.get("fetchUrl", ""),
        "warnings": warnings,
        "sampleHoldings": sample_holdings,
        "durationMs": duration_ms,
        "probedAt": utc_now_iso(),
    }


def html_to_lines(markup: str) -> list[str]:
    parser = TextExtractor()
    parser.feed(markup)
    text = html.unescape(parser.text())
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_nuxt_data_payload(markup: str) -> object | None:
    match = re.search(
        r'<script type="application/json"[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>',
        markup,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    raw_payload = match.group(1).strip()
    if not raw_payload:
        return None
    try:
        return json.loads(raw_payload)
    except json.JSONDecodeError:
        return None


def resolve_nuxt_pool_value(pool: list, value: object, max_depth: int = 24) -> object:
    current = value
    depth = 0
    while depth < max_depth:
        if isinstance(current, int) and 0 <= current < len(pool):
            current = pool[current]
            depth += 1
            continue
        if (
            isinstance(current, list)
            and len(current) == 2
            and isinstance(current[0], str)
            and current[0] in {"ShallowReactive", "Reactive", "Ref", "ShallowRef"}
        ):
            current = current[1]
            depth += 1
            continue
        break
    return current


def parse_etfinfo_holdings_from_nuxt(code: str, markup: str) -> dict | None:
    payload = extract_nuxt_data_payload(markup)
    if not isinstance(payload, list):
        return None

    normalized_code = normalize_code(code)
    detail_key = f"etf-detail-base-{normalized_code}"
    detail_index = None
    for row in payload:
        if isinstance(row, dict) and detail_key in row:
            detail_index = row.get(detail_key)
            break
    if not isinstance(detail_index, int):
        return None

    detail_row = resolve_nuxt_pool_value(payload, detail_index)
    if not isinstance(detail_row, dict):
        return None

    holdings_meta = resolve_nuxt_pool_value(payload, detail_row.get("holdings"))
    if not isinstance(holdings_meta, dict):
        return None

    snapshot_date = str(resolve_nuxt_pool_value(payload, holdings_meta.get("snapshotDate")) or "").strip()
    as_of = snapshot_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", snapshot_date) else ""

    holdings_refs = resolve_nuxt_pool_value(payload, holdings_meta.get("holdings"))
    if not isinstance(holdings_refs, list):
        return None

    holdings: dict[str, float] = {}
    details: list[dict] = []
    declared_count = 0
    for item_ref in holdings_refs:
        item = resolve_nuxt_pool_value(payload, item_ref)
        if not isinstance(item, dict):
            continue

        stock_code = normalize_code(str(resolve_nuxt_pool_value(payload, item.get("code")) or ""))
        if not stock_code:
            continue
        declared_count += 1

        weight_raw = resolve_nuxt_pool_value(payload, item.get("weight"))
        try:
            weight = float(weight_raw)
        except (TypeError, ValueError):
            continue
        if weight < 0:
            continue

        stock_name = str(resolve_nuxt_pool_value(payload, item.get("name")) or stock_code).strip() or stock_code
        shares_raw = resolve_nuxt_pool_value(payload, item.get("shares"))
        shares = ""
        if shares_raw is not None and shares_raw != "":
            if isinstance(shares_raw, float) and shares_raw.is_integer():
                shares = str(int(shares_raw))
            else:
                shares = str(shares_raw).replace(",", "").strip()
                if shares.endswith(".0") and shares[:-2].isdigit():
                    shares = shares[:-2]

        holdings[stock_code] = weight
        details.append(
            {
                "code": stock_code,
                "name": stock_name,
                "weight": weight,
                "shares": shares,
                "price": "",
            }
        )

    if not holdings:
        return None

    parsed_count = len(holdings)
    declared_count = max(declared_count, parsed_count)
    source_raw = str(resolve_nuxt_pool_value(payload, holdings_meta.get("source")) or "").strip()
    source_label = f"ETFInfo {source_raw}" if source_raw else "ETFInfo public page"
    coverage = "full" if parsed_count == declared_count else "partial_public_page"

    return {
        "code": normalized_code,
        "source": source_label,
        "asOf": as_of,
        "holdings": holdings,
        "holdingDetails": details,
        "declaredHoldingCount": declared_count,
        "parsedHoldingCount": parsed_count,
        "coverage": coverage,
    }


def parse_etfinfo_holdings(code: str, markup: str) -> dict:
    parsed_from_nuxt = parse_etfinfo_holdings_from_nuxt(code, markup)
    if parsed_from_nuxt is not None:
        return parsed_from_nuxt
    lines = html_to_lines(markup)
    joined = "\n".join(lines)
    date_match = re.search(r"(?:快照|持股快照)[:：\s]*(\d{4}-\d{2}-\d{2})", joined)
    count_match = re.search(r"共\s*(\d+)\s*檔持股", joined)
    as_of = date_match.group(1) if date_match else ""
    declared_count = int(count_match.group(1)) if count_match else 0
    holdings: dict[str, float] = {}
    details = []
    table_start = 0
    table_end = len(lines)

    for index, line in enumerate(lines):
        if line == "完整持股明細":
            table_start = index
        if table_start and line == "成分股明細常見問題":
            table_end = index
            break

    index = table_start
    while index < table_end - 6:
        stock_code = lines[index].replace(" ", "")
        if not re.fullmatch(r"\d{4}[A-Z]?|[A-Z]{1,6}(?:\s+US)?", stock_code):
            index += 1
            continue

        name = lines[index + 1]
        change = lines[index + 2]
        price = lines[index + 3].replace(",", "")
        weight_text = lines[index + 4]
        shares = lines[index + 5]
        contribution = lines[index + 6]

        if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?%", change):
            index += 1
            continue
        weight_match = re.fullmatch(r"(\d+(?:\.\d+)?)%", weight_text)
        if not weight_match or not re.fullmatch(r"[\d,]+", shares):
            index += 1
            continue

        weight = float(weight_match.group(1))
        holdings[stock_code] = weight
        details.append(
            {
                "code": stock_code,
                "name": name,
                "weight": weight,
                "shares": shares.replace(",", ""),
                "price": price,
                "change": change,
                "contribution": contribution,
            }
        )
        index += 7

    return {
        "code": code,
        "source": "ETFInfo public page",
        "asOf": as_of,
        "holdings": holdings,
        "holdingDetails": details,
        "declaredHoldingCount": declared_count,
        "parsedHoldingCount": len(details),
        "coverage": "full" if declared_count and declared_count == len(details) else "partial_public_page",
    }


def summarize_quality(etfs: list[dict], errors: list[dict]) -> dict:
    declared_total = sum(int(etf.get("declaredHoldingCount") or 0) for etf in etfs)
    parsed_total = sum(int(etf.get("parsedHoldingCount") or 0) for etf in etfs)
    partial_codes = [
        etf["code"]
        for etf in etfs
        if etf.get("coverage") != "full"
        or (etf.get("declaredHoldingCount") and etf.get("parsedHoldingCount") != etf.get("declaredHoldingCount"))
    ]
    status = "complete"
    if partial_codes or errors:
        status = "partial"
    return {
        "status": status,
        "declaredHoldingCount": declared_total,
        "parsedHoldingCount": parsed_total,
        "partialCodes": partial_codes,
        "errorCount": len(errors),
        "message": (
            "Public-page parser returned partial holdings; use official PCF/TWSE adapters for production-grade completeness."
            if status == "partial"
            else "All requested public-page holdings were parsed."
        ),
    }


def fetch_live_payload(codes: list[str], adapter: HoldingsAdapter | None = None) -> dict:
    adapter_instance = adapter or select_live_adapter()
    etfs = []
    errors = []
    as_of_values = []
    enforce_official_quality = adapter_is_official(adapter_instance.name)

    def fetch_one(code: str) -> dict:
        try:
            parsed = adapter_instance.fetch_one(code)
            if parsed["holdings"]:
                if enforce_official_quality:
                    ok, reason = snapshot_quality_check(parsed)
                    if not ok:
                        return {
                            "ok": False,
                            "error": {
                                "code": code,
                                "message": f"Official snapshot quality gate failed: {reason}",
                                "adapter": adapter_instance.name,
                                "coverage": parsed.get("coverage"),
                                "declaredHoldingCount": parsed.get("declaredHoldingCount"),
                                "parsedHoldingCount": parsed.get("parsedHoldingCount"),
                                "url": parsed.get("fetchUrl", ""),
                            },
                        }
                return {"ok": True, "payload": parsed}
            return {
                "ok": False,
                "error": {
                    "code": code,
                    "message": "No holdings parsed",
                    "adapter": adapter_instance.name,
                    "url": parsed.get("fetchUrl", ""),
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": {
                    "code": code,
                    "message": str(exc),
                    "adapter": adapter_instance.name,
                },
            }

    with ThreadPoolExecutor(max_workers=min(6, max(1, len(codes)))) as executor:
        futures = {executor.submit(fetch_one, code): code for code in codes}
        for future in as_completed(futures):
            result = future.result()
            if result["ok"]:
                parsed = result["payload"]
                etfs.append(parsed)
                if parsed["asOf"]:
                    as_of_values.append(parsed["asOf"])
            else:
                errors.append(result["error"])

    if not etfs:
        emit_refresh_alert(
            "error",
            "Live holdings refresh failed for all requested ETF codes.",
            {
                "requestedCodes": codes,
                "adapter": adapter_instance.name,
                "errors": errors[:20],
            },
        )
        raise RuntimeError("No live ETF holdings could be fetched.")

    etfs.sort(key=lambda item: codes.index(item["code"]) if item["code"] in codes else len(codes))
    as_of = max(as_of_values) if as_of_values else time.strftime("%Y-%m-%d")
    payload = {
        "asOf": as_of,
        "source": adapter_instance.source_label,
        "adapter": adapter_instance.name,
        "fetchSettings": live_fetch_settings(),
        "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "requestedCodes": codes,
        "etfs": etfs,
        "errors": errors,
    }
    payload["dataQuality"] = summarize_quality(etfs, errors)
    if errors or payload["dataQuality"].get("status") == "partial":
        emit_refresh_alert(
            "warning",
            "Live holdings refresh completed with partial quality or per-code errors.",
            {
                "requestedCodes": codes,
                "adapter": adapter_instance.name,
                "errorCount": len(errors),
                "partialCodes": payload["dataQuality"].get("partialCodes", []),
            },
        )
    return payload


def validate_etf_snapshot_row(row: dict) -> None:
    code = normalize_code(str(row.get("code", "")))
    if not code:
        raise ValueError("Each ETF row must include a code.")
    as_of = str(row.get("asOf", "")).strip()
    if as_of and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise ValueError(f"ETF {code} has invalid asOf date: {as_of!r}.")
    holdings = row.get("holdings", {})
    if not isinstance(holdings, dict):
        raise ValueError(f"ETF {code} holdings must be an object.")
    for stock_code, raw_weight in holdings.items():
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            raise ValueError(f"ETF {code} has invalid weight for {stock_code}: {raw_weight!r}.") from None
        if weight < 0:
            raise ValueError(f"ETF {code} has negative weight for {stock_code}: {weight}.")


def validate_live_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")
    as_of = str(payload.get("asOf", "")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise ValueError(f"Payload has invalid asOf date: {as_of!r}.")
    etfs = payload.get("etfs", [])
    if not isinstance(etfs, list) or not etfs:
        raise ValueError("Payload etfs must be a non-empty array.")
    for row in etfs:
        if not isinstance(row, dict):
            raise ValueError("Each ETF row must be a JSON object.")
        validate_etf_snapshot_row(row)
    errors = payload.get("errors", [])
    if not isinstance(errors, list):
        raise ValueError("Payload errors must be an array.")


def persist_latest_payload(payload: dict) -> dict:
    validate_live_payload(payload)
    persisted = {
        **payload,
        "savedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "savedTo": "data/latest-etf-holdings.json",
    }
    write_json_atomic(DATA_FILE, persisted)
    return persisted


def load_latest_payload() -> dict:
    return load_json_file(DATA_FILE, {})


def latest_payload_summary(payload: dict) -> dict:
    etfs = payload.get("etfs", [])
    partial_count = sum(1 for row in etfs if row.get("coverage") and row.get("coverage") != "full")
    return {
        "asOf": payload.get("asOf", ""),
        "savedAt": payload.get("savedAt") or payload.get("fetchedAt") or "",
        "source": payload.get("source", ""),
        "adapter": payload.get("adapter") or LIVE_FETCH_ADAPTER,
        "etfCount": len(etfs),
        "errorCount": len(payload.get("errors", [])),
        "partialCount": partial_count,
    }


def official_snapshot_inventory() -> dict:
    if not OFFICIAL_SNAPSHOT_DIR.exists() or not OFFICIAL_SNAPSHOT_DIR.is_dir():
        return {
            "exists": False,
            "dir": str(OFFICIAL_SNAPSHOT_DIR),
            "fileCount": 0,
        }
    file_count = sum(1 for item in OFFICIAL_SNAPSHOT_DIR.glob("*.json") if item.is_file())
    return {
        "exists": True,
        "dir": str(OFFICIAL_SNAPSHOT_DIR),
        "fileCount": file_count,
    }


def official_source_registry_summary(universe: list[dict], registry: dict | None = None) -> dict:
    registry = registry if isinstance(registry, dict) else load_official_source_registry()
    sources = registry.get("sources", [])
    if not isinstance(sources, list):
        sources = []
    listed_rows = [
        row
        for row in universe
        if normalize_code(str(row.get("code", "")))
        and str(row.get("status", "")).strip().lower() in {"", "listed"}
    ]
    covered_codes = []
    production_ready_codes = []
    missing_codes = []
    by_format: dict[str, int] = {}
    by_issuer: dict[str, dict[str, int]] = {}
    for source in sources:
        if not isinstance(source, dict) or source.get("enabled") is False:
            continue
        data_format = str(source.get("format") or "json").strip().lower() or "json"
        by_format[data_format] = by_format.get(data_format, 0) + 1

    for row in listed_rows:
        code = normalize_code(str(row.get("code", "")))
        issuer = str(row.get("issuer") or "unknown").strip() or "unknown"
        issuer_summary = by_issuer.setdefault(issuer, {"listedCount": 0, "coveredCount": 0, "missingCount": 0})
        issuer_summary["listedCount"] += 1
        matching_sources = [
            source
            for source in sources
            if isinstance(source, dict) and official_registry_source_matches(source, code, row)
        ]
        if matching_sources:
            covered_codes.append(code)
            issuer_summary["coveredCount"] += 1
            if any(str(source.get("expectedCoverage") or "").strip().lower() == "full" for source in matching_sources):
                production_ready_codes.append(code)
        else:
            missing_codes.append(code)
            issuer_summary["missingCount"] += 1
    return {
        "configured": bool(sources),
        "file": str(OFFICIAL_SOURCE_REGISTRY_FILE),
        "sourceCount": len([source for source in sources if isinstance(source, dict) and source.get("enabled") is not False]),
        "listedCount": len(listed_rows),
        "coveredListedCount": len(covered_codes),
        "productionReadyListedCount": len(production_ready_codes),
        "nonProductionReadyListedCount": len(listed_rows) - len(production_ready_codes),
        "missingListedCount": len(missing_codes),
        "missingCodes": missing_codes[:80],
        "byFormat": by_format,
        "byIssuer": by_issuer,
    }


def history_store_quality_overview(store: dict) -> dict:
    history = store.get("history", {}) if isinstance(store, dict) else {}
    if not isinstance(history, dict):
        history = {}
    per_code = {}
    total = {
        "etfCount": 0,
        "totalSnapshots": 0,
        "fullSnapshotCount": 0,
        "realSnapshotCount": 0,
        "partialSnapshotCount": 0,
        "seedSnapshotCount": 0,
    }
    for code, code_history in history.items():
        summary = history_quality_summary(code_history if isinstance(code_history, dict) else {})
        per_code[code] = summary
        total["etfCount"] += 1
        total["totalSnapshots"] += summary.get("totalSnapshots", 0)
        total["fullSnapshotCount"] += summary.get("fullSnapshotCount", 0)
        total["realSnapshotCount"] += summary.get("realSnapshotCount", 0)
        total["partialSnapshotCount"] += summary.get("partialSnapshotCount", 0)
        total["seedSnapshotCount"] += summary.get("seedSnapshotCount", 0)
    return {
        "summary": total,
        "perCode": per_code,
    }


def load_history_store() -> dict:
    store = load_json_file(HISTORY_FILE, {"history": {}})
    if "history" not in store or not isinstance(store["history"], dict):
        store["history"] = {}
    return store


def load_history_quality_report() -> dict:
    report = load_json_file(HISTORY_QUALITY_REPORT_FILE, {})
    if not isinstance(report, dict):
        return {}
    return report


def save_history_quality_report(report: dict) -> dict:
    payload = dict(report)
    payload["savedAt"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(HISTORY_QUALITY_REPORT_FILE, payload)
    return payload


def history_quality_report_summary(report: dict) -> dict:
    if not isinstance(report, dict) or not report:
        return {
            "exists": False,
            "file": str(HISTORY_QUALITY_REPORT_FILE),
        }
    rows = report.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    return {
        "exists": True,
        "file": str(HISTORY_QUALITY_REPORT_FILE),
        "generatedAt": report.get("generatedAt"),
        "savedAt": report.get("savedAt"),
        "ok": bool(report.get("ok", False)),
        "qualityMode": report.get("qualityMode"),
        "days": report.get("days"),
        "minSnapshots": report.get("minSnapshots"),
        "codeCount": len(report.get("codes", []) or []),
        "rowCount": len(rows),
        "passCount": report.get("passCount"),
        "failCount": report.get("failCount"),
    }


def ensure_portfolio_users(store: dict) -> dict[str, dict]:
    users = store.get("users")
    if isinstance(users, dict):
        legacy_rows = store.get("portfolios", [])
        if not isinstance(legacy_rows, list):
            legacy_rows = []
        normalized_users: dict[str, dict] = {}
        for raw_user_id, raw_user_store in users.items():
            try:
                user_id = normalize_user_id(raw_user_id)
            except ValueError:
                continue
            user_store = raw_user_store if isinstance(raw_user_store, dict) else {}
            portfolios = user_store.get("portfolios", [])
            if not isinstance(portfolios, list):
                portfolios = []
            normalized_users[user_id] = {
                **user_store,
                "portfolios": portfolios,
            }
        if legacy_rows and DEFAULT_USER_ID not in normalized_users:
            normalized_users[DEFAULT_USER_ID] = {"portfolios": legacy_rows}
        store["users"] = normalized_users
        return normalized_users

    legacy_rows = store.get("portfolios", [])
    if not isinstance(legacy_rows, list):
        legacy_rows = []
    store["users"] = {
        DEFAULT_USER_ID: {
            "portfolios": legacy_rows,
            "updatedAt": store.get("updatedAt"),
        }
    }
    return store["users"]


def ensure_watchlist_users(store: dict) -> dict[str, dict]:
    users = store.get("users")
    if isinstance(users, dict):
        legacy_rows = store.get("rows", [])
        if not isinstance(legacy_rows, list):
            legacy_rows = []
        normalized_users: dict[str, dict] = {}
        for raw_user_id, raw_user_store in users.items():
            try:
                user_id = normalize_user_id(raw_user_id)
            except ValueError:
                continue
            user_store = raw_user_store if isinstance(raw_user_store, dict) else {}
            rows = user_store.get("rows", [])
            if not isinstance(rows, list):
                rows = []
            normalized_users[user_id] = {
                **user_store,
                "rows": rows,
            }
        if legacy_rows and DEFAULT_USER_ID not in normalized_users:
            normalized_users[DEFAULT_USER_ID] = {"rows": legacy_rows}
        store["users"] = normalized_users
        return normalized_users

    legacy_rows = store.get("rows", [])
    if not isinstance(legacy_rows, list):
        legacy_rows = []
    store["users"] = {
        DEFAULT_USER_ID: {
            "rows": legacy_rows,
            "updatedAt": store.get("updatedAt"),
        }
    }
    return store["users"]


def portfolio_rows_for_user(store: dict, user_id: str | None = None, create: bool = False) -> list[dict]:
    if user_id is None:
        rows = store.get("portfolios", [])
        if isinstance(rows, list):
            return rows
        store["portfolios"] = []
        return store["portfolios"]

    users = ensure_portfolio_users(store)
    user_store = users.get(user_id)
    if user_store is None:
        if not create:
            return []
        user_store = {"portfolios": []}
        users[user_id] = user_store
    portfolios = user_store.get("portfolios", [])
    if not isinstance(portfolios, list):
        portfolios = []
        user_store["portfolios"] = portfolios
    return portfolios


def watchlist_rows_for_user(store: dict, user_id: str | None = None, create: bool = False) -> list[dict]:
    if user_id is None:
        rows = store.get("rows", [])
        if isinstance(rows, list):
            return rows
        store["rows"] = []
        return store["rows"]

    users = ensure_watchlist_users(store)
    user_store = users.get(user_id)
    if user_store is None:
        if not create:
            return []
        user_store = {"rows": []}
        users[user_id] = user_store
    rows = user_store.get("rows", [])
    if not isinstance(rows, list):
        rows = []
        user_store["rows"] = rows
    return rows


def load_portfolio_store() -> dict:
    store = load_json_file(PORTFOLIOS_FILE, {"portfolios": []})
    portfolios = store.get("portfolios")
    if not isinstance(portfolios, list):
        store["portfolios"] = []
    users = ensure_portfolio_users(store)
    default_rows = portfolio_rows_for_user(store, DEFAULT_USER_ID, create=True)
    store["portfolios"] = default_rows
    if DEFAULT_USER_ID in users:
        users[DEFAULT_USER_ID]["portfolios"] = default_rows
    return store


def save_portfolio_store(store: dict) -> dict:
    store["updatedAt"] = datetime.now(timezone.utc).isoformat()
    default_rows = portfolio_rows_for_user(store, DEFAULT_USER_ID, create=True)
    store["portfolios"] = default_rows
    write_json_atomic(PORTFOLIOS_FILE, store)
    return store


def load_watchlist_store() -> dict:
    store = load_json_file(WATCHLIST_FILE, {"rows": []})
    rows = store.get("rows")
    if not isinstance(rows, list):
        store["rows"] = []
    users = ensure_watchlist_users(store)
    default_rows = watchlist_rows_for_user(store, DEFAULT_USER_ID, create=True)
    store["rows"] = default_rows
    if DEFAULT_USER_ID in users:
        users[DEFAULT_USER_ID]["rows"] = default_rows
    return store


def save_watchlist_store(store: dict) -> dict:
    store["updatedAt"] = datetime.now(timezone.utc).isoformat()
    default_rows = watchlist_rows_for_user(store, DEFAULT_USER_ID, create=True)
    store["rows"] = default_rows
    write_json_atomic(WATCHLIST_FILE, store)
    return store


def list_watchlist_rows(store: dict, user_id: str | None = None) -> list[dict]:
    rows = watchlist_rows_for_user(store, user_id=user_id, create=False)
    normalized = []
    for row in rows:
        code = normalize_code(str(row.get("code", "")))
        if not code:
            continue
        normalized.append(
            {
                "code": code,
                "note": str(row.get("note", "")).strip(),
                "createdAt": row.get("createdAt"),
                "updatedAt": row.get("updatedAt"),
            }
        )
    normalized.sort(key=lambda row: row.get("updatedAt") or "", reverse=True)
    return normalized


def upsert_watchlist_row(store: dict, code: str, note: str = "", user_id: str | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    rows = watchlist_rows_for_user(store, user_id=user_id, create=True)
    for row in rows:
        if normalize_code(str(row.get("code", ""))) == code:
            row["note"] = note
            row["updatedAt"] = now
            return row
    created = {
        "code": code,
        "note": note,
        "createdAt": now,
        "updatedAt": now,
    }
    rows.append(created)
    return created


def delete_watchlist_row(store: dict, code: str, user_id: str | None = None) -> dict | None:
    rows = watchlist_rows_for_user(store, user_id=user_id, create=False)
    for index, row in enumerate(rows):
        if normalize_code(str(row.get("code", ""))) == code:
            return rows.pop(index)
    return None


def normalize_portfolio_name(value) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("name is required.")
    if len(name) > MAX_PORTFOLIO_NAME_LENGTH:
        raise ValueError(f"name must be at most {MAX_PORTFOLIO_NAME_LENGTH} characters.")
    return name


def normalize_portfolio_id(value) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return f"pf_{int(time.time() * 1000)}"
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,80}", candidate):
        raise ValueError("id must match [A-Za-z0-9._-]{3,80}.")
    return candidate


def find_portfolio_index(store: dict, portfolio_id: str, user_id: str | None = None) -> int:
    portfolios = portfolio_rows_for_user(store, user_id=user_id, create=False)
    for index, row in enumerate(portfolios):
        if str(row.get("id", "")) == portfolio_id:
            return index
    return -1


def normalize_portfolio_positions(payload: dict, available_codes: set[str]) -> list[dict]:
    positions = normalize_positions(payload, available_codes)
    if len(positions) > MAX_PORTFOLIO_POSITIONS:
        raise ValueError(f"positions cannot exceed {MAX_PORTFOLIO_POSITIONS} ETFs.")
    total = sum(parse_float(row.get("allocation", 0)) for row in positions)
    if total <= 0:
        raise ValueError("positions total allocation must be greater than 0.")
    return positions


def portfolio_summary(row: dict) -> dict:
    positions = row.get("positions", [])
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "positionCount": len(positions),
        "totalAllocation": round(sum(parse_float(item.get("allocation", 0)) for item in positions), 4),
        "updatedAt": row.get("updatedAt"),
        "createdAt": row.get("createdAt"),
    }


def list_portfolio_summaries(store: dict, user_id: str | None = None) -> list[dict]:
    rows = [portfolio_summary(row) for row in portfolio_rows_for_user(store, user_id=user_id, create=False)]
    rows.sort(key=lambda row: row.get("updatedAt", ""), reverse=True)
    return rows


def upsert_portfolio_record(
    store: dict,
    portfolio_id: str,
    name: str,
    positions: list[dict],
    user_id: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    portfolios = portfolio_rows_for_user(store, user_id=user_id, create=True)
    index = find_portfolio_index(store, portfolio_id, user_id=user_id)
    if index >= 0:
        current = portfolios[index]
        next_row = {
            **current,
            "id": portfolio_id,
            "name": name,
            "positions": positions,
            "updatedAt": now,
        }
        portfolios[index] = next_row
        return next_row

    created = {
        "id": portfolio_id,
        "name": name,
        "positions": positions,
        "createdAt": now,
        "updatedAt": now,
    }
    portfolios.append(created)
    return created


def upsert_history_from_payload(payload: dict) -> None:
    if not payload.get("etfs"):
        return
    store = load_history_store()
    changed = False
    history = store["history"]
    recorded_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    for etf_payload in payload["etfs"]:
        code = normalize_code(etf_payload.get("code", ""))
        if not code:
            continue
        as_of = etf_payload.get("asOf") or payload.get("asOf")
        if not as_of:
            continue
        code_history = history.setdefault(code, {})
        next_entry = {
            "asOf": as_of,
            "source": etf_payload.get("source") or payload.get("source"),
            "adapter": etf_payload.get("adapter") or payload.get("adapter") or LIVE_FETCH_ADAPTER,
            "coverage": etf_payload.get("coverage", ""),
            "declaredHoldingCount": int(etf_payload.get("declaredHoldingCount") or 0),
            "parsedHoldingCount": int(etf_payload.get("parsedHoldingCount") or 0),
            "holdings": etf_payload.get("holdings", {}),
            "holdingDetails": etf_payload.get("holdingDetails", []),
            "recordedAt": recorded_at,
        }
        current_entry = code_history.get(as_of)
        if current_entry != next_entry:
            code_history[as_of] = next_entry
            changed = True

    retention_summary = apply_history_retention_policy(store)
    if retention_summary.get("removedSnapshotCount", 0) > 0:
        changed = True

    if changed:
        store["updatedAt"] = recorded_at
        store["historyRetention"] = {
            "lastRunAt": recorded_at,
            "lastSummary": retention_summary,
            "policy": history_retention_settings(),
        }
        write_json_atomic(HISTORY_FILE, store)


def maybe_seed_history_from_latest() -> None:
    if HISTORY_FILE.exists():
        return
    latest = load_latest_payload()
    if latest.get("etfs"):
        upsert_history_from_payload(latest)


def parse_number(value: str, default_value: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return default_value


def build_holding_detail_map(detail_rows: list[dict]) -> dict[str, dict]:
    return {row.get("code", ""): row for row in detail_rows if row.get("code")}


def find_latest_entry_for_code(code: str, latest_payload: dict) -> dict | None:
    for row in latest_payload.get("etfs", []):
        if normalize_code(row.get("code", "")) == code:
            return row
    return None


def get_holding_snapshot(
    code: str,
    target_date: str | None,
    history_store: dict,
    latest_payload: dict,
    universe_index: dict[str, dict],
) -> dict | None:
    code_history = history_store.get("history", {}).get(code, {})
    if target_date:
        entry = code_history.get(target_date)
        if entry:
            flags = history_entry_flags(entry)
            return {
                "code": code,
                "asOf": target_date,
                "source": entry.get("source", "history"),
                "adapter": entry.get("adapter") or LIVE_FETCH_ADAPTER,
                "coverage": entry.get("coverage", ""),
                "declaredHoldingCount": int(entry.get("declaredHoldingCount") or 0),
                "parsedHoldingCount": int(entry.get("parsedHoldingCount") or 0),
                "holdings": entry.get("holdings", {}),
                "holdingDetails": entry.get("holdingDetails", []),
                "fullSnapshot": flags["full"],
                "realSnapshot": flags["real"],
            }
        return None

    if code_history:
        newest_date = max(code_history)
        newest = code_history[newest_date]
        flags = history_entry_flags(newest)
        return {
            "code": code,
            "asOf": newest_date,
            "source": newest.get("source", "history"),
            "adapter": newest.get("adapter") or LIVE_FETCH_ADAPTER,
            "coverage": newest.get("coverage", ""),
            "declaredHoldingCount": int(newest.get("declaredHoldingCount") or 0),
            "parsedHoldingCount": int(newest.get("parsedHoldingCount") or 0),
            "holdings": newest.get("holdings", {}),
            "holdingDetails": newest.get("holdingDetails", []),
            "fullSnapshot": flags["full"],
            "realSnapshot": flags["real"],
        }

    latest_entry = find_latest_entry_for_code(code, latest_payload)
    if latest_entry:
        next_row = dict(latest_entry)
        flags = history_entry_flags(next_row)
        next_row.setdefault("adapter", latest_payload.get("adapter") or LIVE_FETCH_ADAPTER)
        next_row.setdefault("fullSnapshot", flags["full"])
        next_row.setdefault("realSnapshot", flags["real"])
        return next_row

    seed = universe_index.get(code)
    if seed:
        holdings = seed.get("holdings", {})
        return {
            "code": code,
            "asOf": latest_payload.get("asOf") or "",
            "source": seed.get("source", "seed"),
            "adapter": "seed",
            "coverage": "seed",
            "declaredHoldingCount": len(holdings),
            "parsedHoldingCount": len(holdings),
            "holdings": holdings,
            "holdingDetails": [],
            "fullSnapshot": True,
            "realSnapshot": False,
        }
    return None


def parse_int_safely(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_history_date(raw_value: object) -> date | None:
    text = str(raw_value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def history_entry_flags(entry: dict) -> dict:
    coverage = str(entry.get("coverage", "")).strip().lower()
    source = str(entry.get("source", "")).strip().lower()
    adapter = str(entry.get("adapter", "")).strip().lower()
    holdings = entry.get("holdings", {})
    parsed_count = parse_int_safely(entry.get("parsedHoldingCount"), len(holdings) if isinstance(holdings, dict) else 0)
    declared_raw = entry.get("declaredHoldingCount")
    declared_count = parse_int_safely(declared_raw, parsed_count)
    if declared_raw in {None, ""}:
        declared_count = parsed_count

    if coverage:
        is_full = coverage == "full"
    else:
        is_full = bool(parsed_count > 0 and declared_count > 0 and parsed_count == declared_count)
    is_seed = coverage == "seed" or "seed" in source or "種子" in source
    is_official_source = (
        adapter.startswith("official")
        or "official" in source
        or "pcf" in source
        or "twse" in source
    )
    is_real = bool(is_full and is_official_source and not is_seed)

    return {
        "full": is_full,
        "seed": is_seed,
        "official": is_official_source,
        "real": is_real,
        "parsedHoldingCount": parsed_count,
        "declaredHoldingCount": declared_count,
    }


def history_retention_settings() -> dict:
    return {
        "retentionDays": HISTORY_RETENTION_DAYS,
        "maxSnapshotsPerCode": HISTORY_MAX_SNAPSHOTS_PER_CODE,
        "dropSeedWhenReal": HISTORY_DROP_SEED_WHEN_REAL,
    }


def history_date_sort_key(snapshot_date: str) -> tuple[int, date, str]:
    parsed = parse_history_date(snapshot_date)
    if parsed is None:
        return (0, date.min, snapshot_date)
    return (1, parsed, snapshot_date)


def apply_history_retention_policy(store: dict, today: date | None = None) -> dict:
    history_map = store.get("history", {}) if isinstance(store, dict) else {}
    if not isinstance(history_map, dict):
        history_map = {}
        if isinstance(store, dict):
            store["history"] = history_map

    today_value = today or date.today()
    cutoff = None
    if HISTORY_RETENTION_DAYS > 0:
        cutoff = today_value - timedelta(days=HISTORY_RETENTION_DAYS)

    summary = {
        "policy": history_retention_settings(),
        "evaluatedCodeCount": 0,
        "changedCodeCount": 0,
        "snapshotsBefore": 0,
        "snapshotsAfter": 0,
        "removedSnapshotCount": 0,
        "removedByAge": 0,
        "removedByMaxPerCode": 0,
        "removedSeedAfterReal": 0,
        "invalidDateSnapshotCount": 0,
    }

    for code in list(history_map.keys()):
        code_history = history_map.get(code)
        if not isinstance(code_history, dict):
            history_map.pop(code, None)
            summary["changedCodeCount"] += 1
            continue

        snapshot_dates = sorted(code_history.keys(), key=history_date_sort_key)
        summary["evaluatedCodeCount"] += 1
        summary["snapshotsBefore"] += len(snapshot_dates)
        dates_to_remove: set[str] = set()

        has_real_snapshot = False
        if HISTORY_DROP_SEED_WHEN_REAL:
            for snapshot_date in snapshot_dates:
                entry = code_history.get(snapshot_date, {})
                flags = history_entry_flags(entry if isinstance(entry, dict) else {})
                if flags["real"]:
                    has_real_snapshot = True
                    break
            if has_real_snapshot:
                for snapshot_date in snapshot_dates:
                    entry = code_history.get(snapshot_date, {})
                    flags = history_entry_flags(entry if isinstance(entry, dict) else {})
                    if flags["seed"] and snapshot_date not in dates_to_remove:
                        dates_to_remove.add(snapshot_date)
                        summary["removedSeedAfterReal"] += 1

        for snapshot_date in snapshot_dates:
            parsed_snapshot_date = parse_history_date(snapshot_date)
            if parsed_snapshot_date is None:
                summary["invalidDateSnapshotCount"] += 1
                continue
            if cutoff is not None and parsed_snapshot_date < cutoff and snapshot_date not in dates_to_remove:
                dates_to_remove.add(snapshot_date)
                summary["removedByAge"] += 1

        if HISTORY_MAX_SNAPSHOTS_PER_CODE > 0:
            remaining_dates = [item for item in snapshot_dates if item not in dates_to_remove]
            overflow_count = len(remaining_dates) - HISTORY_MAX_SNAPSHOTS_PER_CODE
            if overflow_count > 0:
                for snapshot_date in remaining_dates[:overflow_count]:
                    if snapshot_date in dates_to_remove:
                        continue
                    dates_to_remove.add(snapshot_date)
                    summary["removedByMaxPerCode"] += 1

        if dates_to_remove:
            for snapshot_date in dates_to_remove:
                code_history.pop(snapshot_date, None)
            summary["removedSnapshotCount"] += len(dates_to_remove)
            summary["changedCodeCount"] += 1

        if not code_history:
            history_map.pop(code, None)
            continue
        summary["snapshotsAfter"] += len(code_history)

    return summary


def history_retention_overview(store: dict) -> dict:
    metadata = store.get("historyRetention", {}) if isinstance(store, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    last_summary = metadata.get("lastSummary", {})
    if not isinstance(last_summary, dict):
        last_summary = {}
    return {
        "policy": history_retention_settings(),
        "lastRunAt": str(metadata.get("lastRunAt") or ""),
        "lastSummary": last_summary,
    }


def history_quality_summary(code_history: dict) -> dict:
    summary = {
        "totalSnapshots": 0,
        "fullSnapshotCount": 0,
        "realSnapshotCount": 0,
        "partialSnapshotCount": 0,
        "seedSnapshotCount": 0,
        "latestSnapshotDate": "",
        "latestRealSnapshotDate": "",
    }
    if not isinstance(code_history, dict) or not code_history:
        return summary

    dates = sorted(code_history.keys())
    summary["totalSnapshots"] = len(dates)
    summary["latestSnapshotDate"] = dates[-1]

    latest_real = ""
    for date in dates:
        entry = code_history.get(date, {})
        flags = history_entry_flags(entry if isinstance(entry, dict) else {})
        if flags["full"]:
            summary["fullSnapshotCount"] += 1
        else:
            summary["partialSnapshotCount"] += 1
        if flags["seed"]:
            summary["seedSnapshotCount"] += 1
        if flags["real"]:
            summary["realSnapshotCount"] += 1
            latest_real = date
    summary["latestRealSnapshotDate"] = latest_real
    return summary


def normalize_changes_quality_mode(raw_value: str | None) -> str:
    value = str(raw_value or "").strip().lower() or "any"
    allowed = {"any", "full_only", "real_only"}
    if value not in allowed:
        raise ValueError("quality must be one of: any, full_only, real_only.")
    return value


def status_level_from_snapshot(snapshot: dict) -> str:
    flags = history_entry_flags(snapshot if isinstance(snapshot, dict) else {})
    if flags["seed"]:
        return "seed"
    if flags["full"]:
        return "ready"
    if snapshot.get("holdings"):
        return "partial"
    return "empty"


def build_updates_status_rows(
    codes: list[str],
    universe_index: dict[str, dict],
    latest_payload: dict,
    history_store: dict,
) -> list[dict]:
    rows = []
    history_map = history_store.get("history", {})
    latest_saved_at = latest_payload.get("savedAt") or latest_payload.get("fetchedAt") or ""

    for code in codes:
        seed = universe_index.get(code, {})
        snapshot = get_holding_snapshot(
            code=code,
            target_date=None,
            history_store=history_store,
            latest_payload=latest_payload,
            universe_index=universe_index,
        )
        if not snapshot:
            rows.append(
                {
                    "code": code,
                    "name": seed.get("name", code),
                    "status": "missing",
                    "message": "No holdings snapshot found.",
                    "historySnapshotCount": len(history_map.get(code, {})),
                }
            )
            continue

        history_count = len(history_map.get(code, {}))
        quality_summary = history_quality_summary(history_map.get(code, {}))
        declared = int(snapshot.get("declaredHoldingCount") or 0)
        parsed = int(snapshot.get("parsedHoldingCount") or len(snapshot.get("holdings", {})))
        rows.append(
            {
                "code": code,
                "name": seed.get("name", code),
                "status": status_level_from_snapshot(snapshot),
                "coverage": snapshot.get("coverage", ""),
                "source": snapshot.get("source", ""),
                "asOf": snapshot.get("asOf", ""),
                "declaredHoldingCount": declared,
                "parsedHoldingCount": parsed,
                "historySnapshotCount": history_count,
                "realSnapshotCount": quality_summary.get("realSnapshotCount", 0),
                "latestRealSnapshotDate": quality_summary.get("latestRealSnapshotDate", ""),
                "latestSavedAt": latest_saved_at,
            }
        )
    return rows


def get_snapshot_dates(code_history: dict, days: int) -> list[str]:
    dates = sorted(code_history.keys())
    if days <= 0:
        return dates
    return dates[-days:]


def parse_shares(value: str) -> int:
    try:
        return int(str(value).replace(",", ""))
    except ValueError:
        return 0


def get_lot_size(stock_code: str) -> int:
    return 1000 if stock_code.isdigit() else 1


def format_change_row(
    stock_code: str,
    previous_weight: float,
    current_weight: float,
    previous_detail: dict | None,
    current_detail: dict | None,
    stock_universe: dict[str, dict],
) -> dict:
    diff_weight = round(current_weight - previous_weight, 4)
    prev_shares = parse_shares(previous_detail.get("shares", "")) if previous_detail else 0
    curr_shares = parse_shares(current_detail.get("shares", "")) if current_detail else 0
    share_delta = curr_shares - prev_shares
    price = parse_number((current_detail or previous_detail or {}).get("price", 0))
    amount = abs(share_delta) * price
    lot_size = get_lot_size(stock_code)
    lots = share_delta / lot_size if lot_size else 0
    stock_info = stock_universe.get(stock_code, {})
    return {
        "code": stock_code,
        "name": stock_info.get("name") or (current_detail or previous_detail or {}).get("name") or stock_code,
        "sector": stock_info.get("sector", "未分類"),
        "diff": diff_weight,
        "current": round(current_weight, 4),
        "previous": round(previous_weight, 4),
        "sharesChange": share_delta,
        "amountChange": round(amount, 2),
        "lotsChange": round(lots, 3),
        "lotUnit": "張" if lot_size == 1000 else "股",
    }


def build_changes_response(
    code: str,
    days: int,
    history_store: dict,
    stock_universe: dict[str, dict],
    quality_mode: str = "any",
) -> dict:
    code_history = history_store.get("history", {}).get(code, {})
    all_dates = sorted(code_history.keys())
    qualified_dates = []
    for date in all_dates:
        entry = code_history.get(date, {})
        flags = history_entry_flags(entry if isinstance(entry, dict) else {})
        if quality_mode == "full_only" and not flags["full"]:
            continue
        if quality_mode == "real_only" and not flags["real"]:
            continue
        qualified_dates.append(date)

    dates = qualified_dates[-days:] if days > 0 else qualified_dates
    quality_summary = history_quality_summary(code_history)
    if len(dates) < 2:
        message = "Not enough daily snapshots. Refresh latest data across multiple trading days to build history."
        if quality_mode == "full_only":
            message = "Not enough full-quality daily snapshots for the selected window."
        elif quality_mode == "real_only":
            message = "Not enough real official daily snapshots for the selected window."
        return {
            "code": code,
            "days": days,
            "qualityMode": quality_mode,
            "rows": [],
            "snapshotDates": dates,
            "availableSnapshotCount": len(all_dates),
            "qualifiedSnapshotCount": len(qualified_dates),
            "qualitySummary": quality_summary,
            "message": message,
        }

    rows = []
    for index in range(1, len(dates)):
        prev_date = dates[index - 1]
        current_date = dates[index]
        prev_entry = code_history[prev_date]
        curr_entry = code_history[current_date]

        prev_holdings = prev_entry.get("holdings", {})
        curr_holdings = curr_entry.get("holdings", {})
        prev_details = build_holding_detail_map(prev_entry.get("holdingDetails", []))
        curr_details = build_holding_detail_map(curr_entry.get("holdingDetails", []))
        stock_codes = set(prev_holdings) | set(curr_holdings)

        changes = [
            format_change_row(
                stock_code=stock_code,
                previous_weight=float(prev_holdings.get(stock_code, 0.0)),
                current_weight=float(curr_holdings.get(stock_code, 0.0)),
                previous_detail=prev_details.get(stock_code),
                current_detail=curr_details.get(stock_code),
                stock_universe=stock_universe,
            )
            for stock_code in stock_codes
        ]

        increases = [row for row in changes if row["diff"] > 0]
        decreases = [row for row in changes if row["diff"] < 0]
        added = [row for row in changes if row["previous"] == 0 and row["current"] > 0]
        removed = [row for row in changes if row["previous"] > 0 and row["current"] == 0]
        turnover = sum(abs(row["diff"]) for row in changes) / 2

        increases.sort(key=lambda row: row["diff"], reverse=True)
        decreases.sort(key=lambda row: row["diff"])
        rows.append(
            {
                "date": current_date,
                "prevDate": prev_date,
                "increases": increases[:3],
                "decreases": decreases[:3],
                "added": added[:3],
                "removed": removed[:3],
                "turnover": round(turnover, 4),
                "coverage": curr_entry.get("coverage", ""),
                "realSnapshot": history_entry_flags(curr_entry).get("real", False),
            }
        )

    return {
        "code": code,
        "days": days,
        "qualityMode": quality_mode,
        "rows": rows,
        "snapshotDates": dates,
        "availableSnapshotCount": len(all_dates),
        "qualifiedSnapshotCount": len(qualified_dates),
        "qualitySummary": quality_summary,
    }


def evaluate_history_quality_gate(
    codes: list[str],
    days: int,
    quality_mode: str,
    min_snapshots: int,
    history_store: dict,
    stock_universe: dict[str, dict],
) -> dict:
    rows = []
    pass_count = 0
    for code in codes:
        response = build_changes_response(
            code=code,
            days=days,
            history_store=history_store,
            stock_universe=stock_universe,
            quality_mode=quality_mode,
        )
        qualified = int(response.get("qualifiedSnapshotCount") or 0)
        row_ok = qualified >= min_snapshots
        if row_ok:
            pass_count += 1
        rows.append(
            {
                "code": code,
                "ok": row_ok,
                "qualifiedSnapshotCount": qualified,
                "requiredSnapshotCount": min_snapshots,
                "rowsCount": len(response.get("rows", [])),
                "snapshotDates": response.get("snapshotDates", []),
                "message": response.get("message", ""),
                "qualitySummary": response.get("qualitySummary", {}),
            }
        )
    return {
        "ok": pass_count == len(codes),
        "qualityMode": quality_mode,
        "days": days,
        "minSnapshots": min_snapshots,
        "codeCount": len(codes),
        "passCount": pass_count,
        "failCount": len(codes) - pass_count,
        "rows": rows,
    }


def normalize_positions(payload: dict, available_codes: set[str]) -> list[dict]:
    positions = payload.get("positions", [])
    normalized = []
    for row in positions:
        code = normalize_code(str(row.get("code", "")))
        allocation = float(row.get("allocation", 0))
        if not code or code not in available_codes:
            raise ValueError(f"Unknown ETF code in positions: {code or '(empty)'}")
        if allocation < 0:
            raise ValueError(f"Allocation must be non-negative for {code}")
        normalized.append({"code": code, "allocation": allocation})
    if not normalized:
        raise ValueError("positions must include at least one ETF.")
    return normalized


def normalize_watchlist_payload(payload: dict, available_codes: set[str]) -> tuple[str, str]:
    code = normalize_code(str(payload.get("code", "")))
    if not code:
        raise ValueError("code is required.")
    if not CODE_PATTERN.fullmatch(code):
        raise ValueError(f"Invalid ETF code format: {code}")
    if code not in available_codes:
        raise ValueError(f"ETF code is not in the configured universe: {code}")
    note = str(payload.get("note", "")).strip()
    if len(note) > 120:
        raise ValueError("note must be at most 120 characters.")
    return code, note


def parse_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_optimize_targets(payload: dict) -> list[dict]:
    rows = payload.get("targets", [])
    if not isinstance(rows, list):
        raise ValueError("targets must be an array.")

    merged: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sector = str(row.get("sector", "")).strip()
        weight = parse_float(row.get("weight", 0))
        if not sector or weight <= 0:
            continue
        merged[sector] = merged.get(sector, 0.0) + weight

    if not merged:
        raise ValueError("targets must include at least one positive sector weight.")

    total = sum(merged.values())
    return [
        {
            "sector": sector,
            "weight": (weight / total) * 100,
        }
        for sector, weight in merged.items()
    ]


def parse_optimize_max_etfs(payload: dict) -> int:
    value = payload.get("maxEtfs", DEFAULT_OPTIMIZE_MAX_ETFS)
    try:
        max_etfs = int(value)
    except (TypeError, ValueError):
        raise ValueError("maxEtfs must be an integer.")
    if max_etfs < 1 or max_etfs > MAX_OPTIMIZE_MAX_ETFS:
        raise ValueError(f"maxEtfs must be between 1 and {MAX_OPTIMIZE_MAX_ETFS}.")
    return max_etfs


def parse_candidate_codes(payload: dict, available_codes: set[str]) -> list[str] | None:
    raw = payload.get("candidateCodes")
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("candidateCodes must be an array.")

    normalized = []
    seen = set()
    for value in raw:
        code = normalize_code(str(value or ""))
        if not code:
            continue
        if code not in available_codes:
            raise ValueError(f"Unknown ETF code in candidateCodes: {code}")
        if code not in seen:
            normalized.append(code)
            seen.add(code)

    if not normalized:
        raise ValueError("candidateCodes must include at least one valid ETF code.")
    return normalized


def compute_sector_vector(holdings: dict, stock_universe: dict[str, dict]) -> dict[str, float]:
    sector_totals: dict[str, float] = {}
    total = 0.0
    for stock_code, weight in holdings.items():
        value = parse_float(weight)
        if value <= 0:
            continue
        sector = stock_universe.get(stock_code, {}).get("sector") or "未分類"
        sector_totals[sector] = sector_totals.get(sector, 0.0) + value
        total += value

    if total <= 0:
        return {}
    return {sector: (value / total) * 100 for sector, value in sector_totals.items()}


def normalize_allocations(raw_scores: list[float]) -> list[float]:
    if not raw_scores:
        return []
    total = sum(raw_scores) or 1.0
    rounded = []
    remaining = 100.0
    for index, score in enumerate(raw_scores):
        if index == len(raw_scores) - 1:
            allocation = max(0.1, round(remaining, 1))
        else:
            allocation = max(0.1, round((score / total) * 100, 1))
            remaining -= allocation
        rounded.append(allocation)

    # Rebalance tiny rounding drift to keep sum close to 100.
    drift = round(100 - sum(rounded), 1)
    if rounded and abs(drift) >= 0.1:
        rounded[-1] = round(max(0.1, rounded[-1] + drift), 1)
    return rounded


def optimize_allocation(
    payload: dict,
    universe: list[dict],
    universe_index: dict[str, dict],
    latest_payload: dict,
    history_store: dict,
    stock_universe: dict[str, dict],
) -> dict:
    available_codes = known_codes(universe_index)
    targets = normalize_optimize_targets(payload)
    max_etfs = parse_optimize_max_etfs(payload)
    candidate_codes_override = parse_candidate_codes(payload, available_codes)
    reference_date = latest_payload.get("asOf") or time.strftime("%Y-%m-%d")

    candidate_rows = []
    for etf in universe:
        code = normalize_code(str(etf.get("code", "")))
        if not code:
            continue
        if candidate_codes_override and code not in candidate_codes_override:
            continue
        if not candidate_codes_override:
            if not listed_flag(etf, reference_date):
                continue
            if etf.get("source") == "模擬投組":
                continue

        snapshot = get_holding_snapshot(
            code=code,
            target_date=None,
            history_store=history_store,
            latest_payload=latest_payload,
            universe_index=universe_index,
        )
        if not snapshot:
            continue

        vector = compute_sector_vector(snapshot.get("holdings", {}), stock_universe)
        if not vector:
            continue

        target_score = sum((vector.get(target["sector"], 0.0) * target["weight"]) for target in targets)
        concentration_penalty = (max(vector.values()) if vector else 0.0) * 0.18
        score = target_score - concentration_penalty
        candidate_rows.append(
            {
                "code": code,
                "name": etf.get("name", code),
                "score": score,
                "targetScore": target_score,
                "concentrationPenalty": concentration_penalty,
                "vector": vector,
                "source": snapshot.get("source", etf.get("source", "")),
                "coverage": snapshot.get("coverage", ""),
                "asOf": snapshot.get("asOf", ""),
            }
        )

    if not candidate_rows:
        raise ValueError("No candidate ETF with usable holdings was found for optimization.")

    candidate_rows.sort(key=lambda row: row["score"], reverse=True)
    selected_map: dict[str, dict] = {}

    for target in targets:
        options = [row for row in candidate_rows if row["vector"].get(target["sector"], 0.0) > 0]
        options.sort(key=lambda row: row["vector"].get(target["sector"], 0.0), reverse=True)
        if options:
            selected_map[options[0]["code"]] = options[0]

    for row in candidate_rows:
        if len(selected_map) >= max_etfs:
            break
        selected_map[row["code"]] = row

    chosen = list(selected_map.values())[:max_etfs]
    fit_scores = [max(1.0, sum(item["vector"].get(target["sector"], 0.0) * target["weight"] for target in targets)) for item in chosen]
    allocations = normalize_allocations(fit_scores)

    selected = []
    for index, item in enumerate(chosen):
        selected.append(
            {
                "code": item["code"],
                "name": item["name"],
                "allocation": allocations[index],
                "fitScore": round(fit_scores[index], 4),
                "targetScore": round(item["targetScore"], 4),
                "concentrationPenalty": round(item["concentrationPenalty"], 4),
                "source": item["source"],
                "coverage": item["coverage"],
                "asOf": item["asOf"],
            }
        )

    selected.sort(key=lambda row: row["allocation"], reverse=True)
    return {
        "targets": [
            {
                "sector": target["sector"],
                "weight": round(target["weight"], 4),
            }
            for target in targets
        ],
        "selected": selected,
        "candidateCount": len(candidate_rows),
        "requestedMaxEtfs": max_etfs,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def compute_exposure_compare(
    positions: list[dict],
    latest_payload: dict,
    history_store: dict,
    universe_index: dict[str, dict],
    stock_universe: dict[str, dict],
) -> dict:
    total_allocation = sum(position["allocation"] for position in positions)
    denominator = total_allocation if total_allocation > 0 else 1

    exposures: dict[str, dict] = {}
    sectors: dict[str, float] = {}
    etf_used = []

    for position in positions:
        snapshot = get_holding_snapshot(
            code=position["code"],
            target_date=None,
            history_store=history_store,
            latest_payload=latest_payload,
            universe_index=universe_index,
        )
        if not snapshot:
            continue
        allocation_ratio = position["allocation"] / denominator
        etf_used.append(
            {
                "code": position["code"],
                "allocation": position["allocation"],
                "asOf": snapshot.get("asOf", ""),
                "coverage": snapshot.get("coverage", ""),
                "source": snapshot.get("source", ""),
            }
        )

        for stock_code, weight in snapshot.get("holdings", {}).items():
            contribution = allocation_ratio * float(weight)
            stock_info = stock_universe.get(stock_code, {})
            row = exposures.get(stock_code)
            if not row:
                row = {
                    "code": stock_code,
                    "name": stock_info.get("name", stock_code),
                    "sector": stock_info.get("sector", "未分類"),
                    "total": 0.0,
                    "count": 0,
                    "byEtf": {},
                    "byEtfContribution": {},
                }
                exposures[stock_code] = row
            row["total"] += contribution
            row["count"] += 1
            row["byEtf"][position["code"]] = float(weight)
            row["byEtfContribution"][position["code"]] = row["byEtfContribution"].get(position["code"], 0.0) + contribution
            sectors[row["sector"]] = sectors.get(row["sector"], 0.0) + contribution

    exposure_rows = sorted(exposures.values(), key=lambda row: row["total"], reverse=True)
    sector_rows = [{"sector": sector, "total": total} for sector, total in sectors.items()]
    sector_rows.sort(key=lambda row: row["total"], reverse=True)

    return {
        "positions": positions,
        "totalAllocation": total_allocation,
        "etfSnapshots": etf_used,
        "exposures": exposure_rows,
        "sectors": sector_rows,
    }


def listed_flag(etf_row: dict, reference_date: str) -> bool:
    if etf_row.get("status") != "listed":
        return False
    listed_date = etf_row.get("listedDate")
    return not listed_date or listed_date <= reference_date


def matches_filter_value(raw_value: object, allowed_values: set[str]) -> bool:
    if not allowed_values:
        return True
    value = str(raw_value or "").strip().lower()
    return bool(value and value in allowed_values)


def parse_filter_values(raw_value: str | None) -> set[str]:
    if raw_value is None:
        return set()
    return {token.strip().lower() for token in str(raw_value).split(",") if token.strip()}


def filter_universe_rows(
    universe: list[dict],
    reference_date: str,
    profile_index: dict[str, dict],
    query: str = "",
    status_values: set[str] | None = None,
    listed_only: bool = False,
    strategy_values: set[str] | None = None,
    asset_class_values: set[str] | None = None,
    region_values: set[str] | None = None,
    distribution_values: set[str] | None = None,
    leverage_values: set[str] | None = None,
) -> list[dict]:
    query_norm = query.strip().lower()
    status_values = status_values or set()
    strategy_values = strategy_values or set()
    asset_class_values = asset_class_values or set()
    region_values = region_values or set()
    distribution_values = distribution_values or set()
    leverage_values = leverage_values or set()

    def score(row: dict) -> int:
        if not query_norm:
            return 1
        code = str(row.get("code", "")).lower()
        name = str(row.get("name", "")).lower()
        strategy = str(row.get("strategy", "")).lower()
        asset_class = str(row.get("assetClass", "")).lower()
        region = str(row.get("region", "")).lower()
        distribution = str(row.get("distributionType", "")).lower()
        leverage = str(row.get("leverageType", "")).lower()
        tags = [str(tag).lower() for tag in row.get("tags", [])]
        status = str(row.get("status", "")).lower()
        haystack = " ".join([code, name, status, strategy, asset_class, region, distribution, leverage, *tags])
        if code.startswith(query_norm):
            return 100
        if query_norm in name:
            return 80
        if any(query_norm in tag for tag in tags):
            return 70
        if query_norm in {strategy, asset_class, region, distribution, leverage}:
            return 60
        return 40 if query_norm in haystack else 0

    rows = []
    for etf in (enrich_etf_row(row, profile_index) for row in universe):
        if status_values and not matches_filter_value(etf.get("status"), status_values):
            continue
        if listed_only and not listed_flag(etf, reference_date):
            continue
        if strategy_values and not matches_filter_value(etf.get("strategy"), strategy_values):
            continue
        if asset_class_values and not matches_filter_value(etf.get("assetClass"), asset_class_values):
            continue
        if region_values and not matches_filter_value(etf.get("region"), region_values):
            continue
        if distribution_values and not matches_filter_value(etf.get("distributionType"), distribution_values):
            continue
        if leverage_values and not matches_filter_value(etf.get("leverageType"), leverage_values):
            continue

        row_score = score(etf)
        if row_score <= 0:
            continue
        rows.append(
            {
                "code": etf.get("code"),
                "name": etf.get("name"),
                "type": etf.get("type"),
                "tags": etf.get("tags", []),
                "source": etf.get("source"),
                "status": etf.get("status"),
                "listedDate": etf.get("listedDate"),
                "expectedListingDate": etf.get("expectedListingDate", ""),
                "strategy": etf.get("strategy", ""),
                "assetClass": etf.get("assetClass", ""),
                "region": etf.get("region", ""),
                "distributionType": etf.get("distributionType", ""),
                "leverageType": etf.get("leverageType", ""),
                "profile": etf.get("profile", {}),
                "listed": listed_flag(etf, reference_date),
                "score": row_score,
            }
        )
    rows.sort(key=lambda row: (-row["listed"], -row["score"], row["code"]))
    return rows


def search_etfs(
    universe: list[dict],
    query: str,
    reference_date: str,
    profile_index: dict[str, dict] | None = None,
) -> list[dict]:
    profile_index = profile_index or {}
    rows = filter_universe_rows(
        universe=universe,
        reference_date=reference_date,
        profile_index=profile_index,
        query=query,
    )
    return rows[:MAX_SEARCH_RESULTS]


class Handler(BaseHTTPRequestHandler):
    def auth_mode_requires_token(self, method: str) -> bool:
        mode = API_AUTH_MODE
        if mode in {"all", "all_token", "required"}:
            return True
        if mode in {"write", "write_token"}:
            return method in {"POST", "PUT", "DELETE"}
        return False

    def resolve_request_token(self) -> str:
        header_token = self.headers.get("X-ETF-Token", "").strip()
        if header_token:
            return header_token
        auth_header = self.headers.get("Authorization", "").strip()
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        query_token = params.get("token", [""])[0].strip()
        return query_token

    def reject_unauthorized(self, message: str) -> None:
        payload = {
            "error": "unauthorized",
            "message": message,
            "auth": build_auth_settings_summary(),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(401)
        self.send_standard_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.emit_access_log(status=401, content_type="application/json; charset=utf-8", bytes_sent=len(body))

    def enforce_auth(self, method: str) -> bool:
        if not self.auth_mode_requires_token(method):
            return False
        if not API_TOKEN:
            self.reject_unauthorized("API token is required by server config but ETF_API_TOKEN is not configured.")
            return True
        token = self.resolve_request_token()
        if token != API_TOKEN:
            self.reject_unauthorized("Missing or invalid API token.")
            return True
        return False

    def rate_limit_key(self) -> str:
        remote = self.client_address[0] if isinstance(self.client_address, tuple) and self.client_address else "unknown"
        if RATE_LIMIT_KEY_MODE == "ip_path":
            parsed = urlparse(self.path)
            return f"{remote}:{parsed.path}"
        return remote

    def reject_rate_limited(self, retry_after_seconds: int) -> None:
        payload = {
            "error": "rate_limited",
            "message": "Too many requests.",
            "retryAfterSeconds": retry_after_seconds,
            "rateLimit": build_rate_limit_settings_summary(),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(429)
        self.send_standard_headers("application/json; charset=utf-8")
        self.send_header("Retry-After", str(max(1, retry_after_seconds)))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.emit_access_log(status=429, content_type="application/json; charset=utf-8", bytes_sent=len(body))

    def enforce_rate_limit(self) -> bool:
        if not RATE_LIMIT_ENABLED:
            return False
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW_SECONDS
        key = self.rate_limit_key()

        with RATE_LIMIT_LOCK:
            bucket = RATE_LIMIT_STATE.get(key, [])
            bucket = [ts for ts in bucket if ts >= window_start]
            if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
                oldest = min(bucket) if bucket else now
                retry_after = int(max(1, (oldest + RATE_LIMIT_WINDOW_SECONDS) - now))
                RATE_LIMIT_STATE[key] = bucket
                self.reject_rate_limited(retry_after)
                return True
            bucket.append(now)
            RATE_LIMIT_STATE[key] = bucket
        return False

    def mark_request_start(self) -> None:
        self._request_started_at = time.perf_counter()

    def request_duration_ms(self) -> float:
        started_at = getattr(self, "_request_started_at", None)
        if started_at is None:
            return 0.0
        return max(0.0, (time.perf_counter() - started_at) * 1000)

    def emit_access_log(self, status: int, content_type: str, bytes_sent: int) -> None:
        try:
            remote_addr = self.client_address[0] if isinstance(self.client_address, tuple) and self.client_address else ""
            append_access_log(
                {
                    "time": utc_now_iso(),
                    "remote": remote_addr,
                    "method": str(self.command or ""),
                    "path": str(self.path or ""),
                    "status": int(status),
                    "contentType": content_type,
                    "bytesSent": int(bytes_sent),
                    "durationMs": round(self.request_duration_ms(), 3),
                    "userAgent": self.headers.get("User-Agent", ""),
                }
            )
        except OSError:
            return

    def do_GET(self):
        self.mark_request_start()
        if self.enforce_rate_limit():
            return
        if self.enforce_auth("GET"):
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/etfs/latest":
            self.send_latest(parsed.query)
            return
        if path == "/api/health":
            self.send_health()
            return
        if path == "/api/pipeline/status":
            self.send_pipeline_status()
            return
        if path == "/api/live-fetch/config":
            self.send_live_fetch_config(parsed.query)
            return
        if path == "/api/live-fetch/probe":
            self.send_live_fetch_probe(parsed.query)
            return
        if path == "/api/history/quality":
            self.send_history_quality(parsed.query)
            return
        if path == "/api/history/quality/latest":
            self.send_history_quality_latest()
            return
        if path == "/api/etfs/universe":
            self.send_universe(parsed.query)
            return
        if path == "/api/etfs/search":
            self.send_search(parsed.query)
            return
        if path == "/api/portfolios":
            self.send_portfolios()
            return
        if path == "/api/watchlist":
            self.send_watchlist()
            return
        if path == "/api/updates/status":
            self.send_updates_status(parsed.query)
            return
        if path == "/api/alerts":
            self.send_alerts(parsed.query)
            return
        if path == "/api/access-logs":
            self.send_access_logs(parsed.query)
            return

        holdings_match = ETF_HOLDINGS_PATH.match(path)
        if holdings_match:
            self.send_holdings(holdings_match.group(1), parsed.query)
            return

        changes_match = ETF_HOLDINGS_CHANGES_PATH.match(path)
        if changes_match:
            self.send_holdings_changes(changes_match.group(1), parsed.query)
            return

        metrics_match = ETF_METRICS_PATH.match(path)
        if metrics_match:
            self.send_etf_metrics(metrics_match.group(1))
            return

        portfolio_match = PORTFOLIO_ITEM_PATH.match(path)
        if portfolio_match:
            portfolio_id = unquote(portfolio_match.group(1))
            self.send_portfolio_item(portfolio_id)
            return
        watchlist_match = WATCHLIST_ITEM_PATH.match(path)
        if watchlist_match:
            code = normalize_code(unquote(watchlist_match.group(1)))
            self.send_watchlist_item(code)
            return

        self.send_static(path)

    def do_POST(self):
        self.mark_request_start()
        if self.enforce_rate_limit():
            return
        if self.enforce_auth("POST"):
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/exposure/compare":
            self.send_exposure_compare()
            return
        if parsed.path == "/api/allocation/optimize":
            self.send_allocation_optimize()
            return
        if parsed.path == "/api/portfolios":
            self.save_portfolio()
            return
        if parsed.path == "/api/watchlist":
            self.save_watchlist()
            return
        self.send_text(404, "Not found")

    def do_PUT(self):
        self.mark_request_start()
        if self.enforce_rate_limit():
            return
        if self.enforce_auth("PUT"):
            return
        parsed = urlparse(self.path)
        portfolio_match = PORTFOLIO_ITEM_PATH.match(parsed.path)
        if portfolio_match:
            portfolio_id = unquote(portfolio_match.group(1))
            self.save_portfolio(portfolio_id=portfolio_id)
            return
        self.send_text(404, "Not found")

    def do_DELETE(self):
        self.mark_request_start()
        if self.enforce_rate_limit():
            return
        if self.enforce_auth("DELETE"):
            return
        parsed = urlparse(self.path)
        portfolio_match = PORTFOLIO_ITEM_PATH.match(parsed.path)
        if portfolio_match:
            portfolio_id = unquote(portfolio_match.group(1))
            self.delete_portfolio(portfolio_id)
            return
        watchlist_match = WATCHLIST_ITEM_PATH.match(parsed.path)
        if watchlist_match:
            code = normalize_code(unquote(watchlist_match.group(1)))
            self.delete_watchlist_item(code)
            return
        self.send_text(404, "Not found")

    def do_OPTIONS(self):
        self.mark_request_start()
        if self.enforce_rate_limit():
            return
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_response(404)
            self.end_headers()
            self.emit_access_log(status=404, content_type="text/plain; charset=utf-8", bytes_sent=0)
            return
        self.send_response(204)
        self.send_standard_headers("text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", f"Content-Type, Authorization, X-ETF-Token, {USER_ID_HEADER}")
        self.end_headers()
        self.emit_access_log(status=204, content_type="text/plain; charset=utf-8", bytes_sent=0)

    def send_health(self) -> None:
        latest = load_latest_payload()
        history_store = load_history_store()
        universe = load_etf_universe()
        profile_store = load_etf_profile_store()
        profile_index = build_etf_profile_index(profile_store)
        history_quality_report = load_history_quality_report()
        alerts = read_recent_refresh_alerts(limit=1)
        self.send_json(
            200,
            {
                "ok": True,
                "service": "ETF True Exposure MVP API",
                "time": utc_now_iso(),
                "dataFileExists": DATA_FILE.exists(),
                "historyFileExists": HISTORY_FILE.exists(),
                "historyQualityReportFileExists": HISTORY_QUALITY_REPORT_FILE.exists(),
                "universeFileExists": ETF_UNIVERSE_FILE.exists(),
                "profileFileExists": ETF_PROFILE_FILE.exists(),
                "portfolioFileExists": PORTFOLIOS_FILE.exists(),
                "watchlistFileExists": WATCHLIST_FILE.exists(),
                "alertsFileExists": ALERTS_FILE.exists(),
                "liveFetch": live_fetch_settings(),
                "liveFetchConfig": live_fetch_config_status(),
                "auth": build_auth_settings_summary(),
                "rateLimit": build_rate_limit_settings_summary(),
                "accessLog": access_log_settings(),
                "officialSnapshots": official_snapshot_inventory(),
                "officialSourceRegistry": official_source_registry_summary(universe),
                "historyQuality": history_store_quality_overview(history_store),
                "historyRetention": history_retention_overview(history_store),
                "latestHistoryQualityReport": history_quality_report_summary(history_quality_report),
                "profileCoverage": profile_coverage_summary(universe, profile_index),
                "latestData": latest_payload_summary(latest),
                "lastAlert": alerts[0] if alerts else None,
                "userContext": {
                    "header": USER_ID_HEADER,
                    "defaultUserId": DEFAULT_USER_ID,
                    "requireUserContext": REQUIRE_USER_CONTEXT,
                },
            },
        )

    def send_pipeline_status(self) -> None:
        universe = load_etf_universe()
        universe_index = build_universe_index(universe)
        latest = load_latest_payload()
        history_store = load_history_store()
        profile_store = load_etf_profile_store()
        profile_index = build_etf_profile_index(profile_store)
        history_report = load_history_quality_report()

        by_strategy: dict[str, int] = {}
        by_asset_class: dict[str, int] = {}
        by_region: dict[str, int] = {}
        by_distribution: dict[str, int] = {}
        by_leverage: dict[str, int] = {}
        listed = 0
        upcoming = 0
        for row in universe:
            code = normalize_code(str(row.get("code", "")))
            if not code:
                continue
            merged = enrich_etf_row(row, profile_index)
            status = str(merged.get("status", "")).strip().lower()
            if status == "listed":
                listed += 1
            else:
                upcoming += 1

            strategy = str(merged.get("strategy", "")).strip().lower() or "unknown"
            asset_class = str(merged.get("assetClass", "")).strip().lower() or "unknown"
            region = str(merged.get("region", "")).strip().lower() or "unknown"
            distribution = str(merged.get("distributionType", "")).strip().lower() or "unknown"
            leverage = str(merged.get("leverageType", "")).strip().lower() or "unknown"

            by_strategy[strategy] = by_strategy.get(strategy, 0) + 1
            by_asset_class[asset_class] = by_asset_class.get(asset_class, 0) + 1
            by_region[region] = by_region.get(region, 0) + 1
            by_distribution[distribution] = by_distribution.get(distribution, 0) + 1
            by_leverage[leverage] = by_leverage.get(leverage, 0) + 1

        quality = latest.get("dataQuality", {}) if isinstance(latest, dict) else {}
        response = {
            "generatedAt": utc_now_iso(),
            "liveFetch": {
                "settings": live_fetch_settings(),
                "config": live_fetch_config_status(),
                "latest": latest_payload_summary(latest),
                "latestQuality": quality,
                "officialSourceRegistry": official_source_registry_summary(universe),
            },
            "history": {
                "qualityOverview": history_store_quality_overview(history_store),
                "retention": history_retention_overview(history_store),
                "latestQualityReport": history_quality_report_summary(history_report),
            },
            "universe": {
                "count": len(universe_index),
                "listedCount": listed,
                "upcomingCount": upcoming,
                "byStrategy": by_strategy,
                "byAssetClass": by_asset_class,
                "byRegion": by_region,
                "byDistributionType": by_distribution,
                "byLeverageType": by_leverage,
            },
            "metrics": {
                "profileAsOf": profile_store.get("asOf"),
                "profileSource": profile_store.get("source"),
                "profileCoverage": profile_coverage_summary(universe, profile_index),
                "metricCoverage": profile_metrics_coverage_summary(universe, profile_index),
            },
            "security": {
                "auth": build_auth_settings_summary(),
                "rateLimit": build_rate_limit_settings_summary(),
            },
        }
        self.send_json(200, response)

    def send_live_fetch_config(self, query: str) -> None:
        params = parse_qs(query)
        requested_adapter = params.get("adapter", [""])[0].strip()
        self.send_json(200, live_fetch_config_status(requested_adapter or None))

    def send_live_fetch_probe(self, query: str) -> None:
        params = parse_qs(query)
        requested_adapter = params.get("adapter", [""])[0].strip()
        selected_adapter = requested_adapter or LIVE_FETCH_ADAPTER
        config_status = live_fetch_config_status(selected_adapter)
        if not config_status.get("ok"):
            self.send_json(
                409,
                {
                    "error": "live_fetch_config_invalid",
                    "message": "Live fetch adapter config has blocking issues; fix /api/live-fetch/config issues first.",
                    "adapter": selected_adapter,
                    "config": config_status,
                },
            )
            return

        universe_index = build_universe_index(load_etf_universe())
        available_codes = known_codes(universe_index)
        requested_code = params.get("code", [""])[0].strip()

        try:
            code = resolve_probe_code(requested_code, available_codes)
        except ValueError as exc:
            self.send_json(400, {"error": "invalid_request", "message": str(exc)})
            return

        try:
            payload = probe_live_fetch_once(code, requested_adapter or None)
            self.send_json(200, payload)
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                502,
                {
                    "error": "live_fetch_probe_failed",
                    "message": str(exc),
                    "adapter": selected_adapter,
                    "code": code,
                },
            )

    def send_history_quality(self, query: str) -> None:
        maybe_seed_history_from_latest()
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        params = parse_qs(query)
        requested = params.get("codes", [""])[0].strip()
        days_raw = params.get("days", [str(DEFAULT_CHANGE_DAYS)])[0]
        quality_raw = params.get("quality", ["real_only"])[0]
        min_snapshots_raw = params.get("minSnapshots", ["2"])[0]

        try:
            days = int(days_raw)
        except ValueError:
            self.send_json(400, {"error": "invalid_request", "message": "days must be an integer."})
            return
        if days < 2 or days > MAX_CHANGE_DAYS:
            self.send_json(
                400,
                {"error": "invalid_request", "message": f"days must be between 2 and {MAX_CHANGE_DAYS}."},
            )
            return
        try:
            min_snapshots = int(min_snapshots_raw)
        except ValueError:
            self.send_json(400, {"error": "invalid_request", "message": "minSnapshots must be an integer."})
            return
        if min_snapshots < 2:
            self.send_json(400, {"error": "invalid_request", "message": "minSnapshots must be at least 2."})
            return
        try:
            quality_mode = normalize_changes_quality_mode(quality_raw)
        except ValueError as exc:
            self.send_json(400, {"error": "invalid_request", "message": str(exc)})
            return

        universe = load_etf_universe()
        universe_index = build_universe_index(universe)
        available_codes = known_codes(universe_index)
        try:
            if requested:
                codes = parse_requested_codes(requested, available_codes)
            else:
                watch_rows = list_watchlist_rows(load_watchlist_store(), user_id=user_id)
                codes = [row["code"] for row in watch_rows if row["code"] in available_codes]
                if not codes:
                    codes = [code for code in DEFAULT_CODES if code in available_codes][:MAX_CODES_PER_REQUEST]
        except ValueError as exc:
            self.send_json(400, {"error": "invalid_request", "message": str(exc)})
            return

        history_store = load_history_store()
        result = evaluate_history_quality_gate(
            codes=codes,
            days=days,
            quality_mode=quality_mode,
            min_snapshots=min_snapshots,
            history_store=history_store,
            stock_universe=load_stock_universe(),
        )
        result["retention"] = history_retention_overview(history_store)
        result["userId"] = user_id
        result["userIdExplicit"] = user_id_explicit
        self.send_json(200, result)

    def send_history_quality_latest(self) -> None:
        report = load_history_quality_report()
        if not report:
            self.send_json(
                404,
                {
                    "error": "not_found",
                    "message": "No history quality report found. Run daily refresh history gate first.",
                    "summary": history_quality_report_summary(report),
                },
            )
            return
        self.send_json(
            200,
            {
                "report": report,
                "summary": history_quality_report_summary(report),
            },
        )

    def send_latest(self, query: str) -> None:
        universe = load_etf_universe()
        universe_index = build_universe_index(universe)
        available_codes = known_codes(universe_index)
        params = parse_qs(query)
        requested = params.get("codes", [""])[0].strip()
        try:
            codes = parse_requested_codes(requested, available_codes)
        except ValueError as exc:
            self.send_json(
                400,
                {
                    "error": "invalid_request",
                    "message": str(exc),
                    "allowedCodes": sorted(available_codes),
                    "maxCodes": MAX_CODES_PER_REQUEST,
                },
            )
            return

        try:
            payload = persist_latest_payload(fetch_live_payload(codes))
            upsert_history_from_payload(payload)
            self.send_json(200, payload)
        except Exception as exc:  # noqa: BLE001
            emit_refresh_alert(
                "error",
                "Live holdings refresh API request failed.",
                {
                    "requestedCodes": codes,
                    "adapter": LIVE_FETCH_ADAPTER,
                    "message": str(exc),
                },
            )
            self.send_json(
                502,
                {
                    "error": "live_fetch_failed",
                    "message": str(exc),
                    "source": LIVE_FETCH_ADAPTER,
                },
            )

    def send_search(self, query: str) -> None:
        latest_payload = load_latest_payload()
        params = parse_qs(query)
        text = params.get("q", [""])[0]
        reference_date = latest_payload.get("asOf") or time.strftime("%Y-%m-%d")
        universe = load_etf_universe()
        profile_index = build_etf_profile_index(load_etf_profile_store())
        rows = search_etfs(universe, text, reference_date, profile_index=profile_index)
        self.send_json(
            200,
            {
                "q": text,
                "count": len(rows),
                "rows": rows,
                "asOf": reference_date,
            },
        )

    def send_universe(self, query: str) -> None:
        latest_payload = load_latest_payload()
        reference_date = latest_payload.get("asOf") or time.strftime("%Y-%m-%d")
        params = parse_qs(query)

        query_text = params.get("q", [""])[0]
        status_values = parse_filter_values(params.get("status", [""])[0])
        strategy_values = parse_filter_values(params.get("strategy", [""])[0])
        asset_class_values = parse_filter_values(params.get("assetClass", [""])[0])
        region_values = parse_filter_values(params.get("region", [""])[0])
        distribution_values = parse_filter_values(params.get("distributionType", [""])[0])
        leverage_values = parse_filter_values(params.get("leverageType", [""])[0])
        listed_only = listed_only_flag(params.get("listedOnly", [""])[0])

        profile_store = load_etf_profile_store()
        profile_index = build_etf_profile_index(profile_store)
        rows = filter_universe_rows(
            universe=load_etf_universe(),
            reference_date=reference_date,
            profile_index=profile_index,
            query=query_text,
            status_values=status_values,
            listed_only=listed_only,
            strategy_values=strategy_values,
            asset_class_values=asset_class_values,
            region_values=region_values,
            distribution_values=distribution_values,
            leverage_values=leverage_values,
        )

        def collect_facet(field: str) -> list[dict]:
            counter: dict[str, int] = {}
            for row in rows:
                value = str(row.get(field, "")).strip()
                if not value:
                    continue
                counter[value] = counter.get(value, 0) + 1
            return [{"value": key, "count": value} for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))]

        self.send_json(
            200,
            {
                "q": query_text,
                "count": len(rows),
                "rows": rows,
                "asOf": reference_date,
                "profileAsOf": profile_store.get("asOf"),
                "profileSource": profile_store.get("source"),
                "filters": {
                    "status": sorted(status_values),
                    "listedOnly": listed_only,
                    "strategy": sorted(strategy_values),
                    "assetClass": sorted(asset_class_values),
                    "region": sorted(region_values),
                    "distributionType": sorted(distribution_values),
                    "leverageType": sorted(leverage_values),
                },
                "facets": {
                    "status": collect_facet("status"),
                    "strategy": collect_facet("strategy"),
                    "assetClass": collect_facet("assetClass"),
                    "region": collect_facet("region"),
                    "distributionType": collect_facet("distributionType"),
                    "leverageType": collect_facet("leverageType"),
                },
            },
        )

    def send_etf_metrics(self, raw_code: str) -> None:
        code = normalize_code(raw_code)
        latest_payload = load_latest_payload()
        reference_date = latest_payload.get("asOf") or time.strftime("%Y-%m-%d")
        universe_index = build_universe_index(load_etf_universe())
        etf = universe_index.get(code)
        if not etf:
            self.send_json(404, {"error": "not_found", "message": f"ETF {code} is not in the configured universe."})
            return

        profile_store = load_etf_profile_store()
        profile_index = build_etf_profile_index(profile_store)
        profile = profile_view(profile_index.get(code))
        metrics = {field: profile.get(field) for field in PROFILE_METRIC_FIELDS if field in profile}
        categories = {field: profile.get(field) for field in PROFILE_CATEGORY_FIELDS if field in profile}
        self.send_json(
            200,
            {
                "code": code,
                "name": etf.get("name"),
                "type": etf.get("type"),
                "status": etf.get("status"),
                "listedDate": etf.get("listedDate"),
                "listed": listed_flag(etf, reference_date),
                "asOf": profile.get("asOf") or profile_store.get("asOf"),
                "source": profile.get("source") or profile_store.get("source"),
                "categories": categories,
                "metrics": metrics,
            },
        )

    def send_holdings(self, raw_code: str, query: str) -> None:
        maybe_seed_history_from_latest()
        code = normalize_code(raw_code)
        params = parse_qs(query)
        requested_date = params.get("date", [""])[0].strip() or None
        universe_index = build_universe_index(load_etf_universe())
        available_codes = known_codes(universe_index)
        if code not in available_codes:
            self.send_json(404, {"error": "not_found", "message": f"ETF {code} is not in the configured universe."})
            return

        snapshot = get_holding_snapshot(
            code=code,
            target_date=requested_date,
            history_store=load_history_store(),
            latest_payload=load_latest_payload(),
            universe_index=universe_index,
        )
        if not snapshot:
            self.send_json(404, {"error": "not_found", "message": f"No holdings snapshot found for {code}."})
            return
        self.send_json(200, snapshot)

    def send_holdings_changes(self, raw_code: str, query: str) -> None:
        maybe_seed_history_from_latest()
        code = normalize_code(raw_code)
        universe_index = build_universe_index(load_etf_universe())
        if code not in known_codes(universe_index):
            self.send_json(404, {"error": "not_found", "message": f"ETF {code} is not in the configured universe."})
            return
        params = parse_qs(query)
        days_raw = params.get("days", [str(DEFAULT_CHANGE_DAYS)])[0]
        quality_raw = params.get("quality", ["any"])[0]
        try:
            days = int(days_raw)
        except ValueError:
            self.send_json(400, {"error": "invalid_request", "message": "days must be an integer."})
            return
        try:
            quality_mode = normalize_changes_quality_mode(quality_raw)
        except ValueError as exc:
            self.send_json(400, {"error": "invalid_request", "message": str(exc)})
            return
        if days < 2 or days > MAX_CHANGE_DAYS:
            self.send_json(
                400,
                {"error": "invalid_request", "message": f"days must be between 2 and {MAX_CHANGE_DAYS}."},
            )
            return

        response = build_changes_response(
            code=code,
            days=days,
            history_store=load_history_store(),
            stock_universe=load_stock_universe(),
            quality_mode=quality_mode,
        )
        self.send_json(200, response)

    def send_exposure_compare(self) -> None:
        universe = load_etf_universe()
        universe_index = build_universe_index(universe)
        available_codes = known_codes(universe_index)
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json(400, {"error": "invalid_json", "message": "Request body must be valid JSON."})
            return

        try:
            positions = normalize_positions(payload, available_codes)
        except (ValueError, TypeError) as exc:
            self.send_json(400, {"error": "invalid_request", "message": str(exc)})
            return

        maybe_seed_history_from_latest()
        compare = compute_exposure_compare(
            positions=positions,
            latest_payload=load_latest_payload(),
            history_store=load_history_store(),
            universe_index=universe_index,
            stock_universe=load_stock_universe(),
        )
        self.send_json(200, compare)

    def send_allocation_optimize(self) -> None:
        universe = load_etf_universe()
        universe_index = build_universe_index(universe)
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json(400, {"error": "invalid_json", "message": "Request body must be valid JSON."})
            return

        maybe_seed_history_from_latest()
        try:
            optimized = optimize_allocation(
                payload=payload,
                universe=universe,
                universe_index=universe_index,
                latest_payload=load_latest_payload(),
                history_store=load_history_store(),
                stock_universe=load_stock_universe(),
            )
        except (ValueError, TypeError) as exc:
            self.send_json(400, {"error": "invalid_request", "message": str(exc)})
            return

        self.send_json(200, optimized)

    def send_portfolios(self) -> None:
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        store = load_portfolio_store()
        rows = list_portfolio_summaries(store, user_id=user_id)
        self.send_json(
            200,
            {
                "count": len(rows),
                "rows": rows,
                "updatedAt": store.get("updatedAt"),
                "userId": user_id,
                "userIdExplicit": user_id_explicit,
            },
        )

    def send_portfolio_item(self, portfolio_id: str) -> None:
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        store = load_portfolio_store()
        index = find_portfolio_index(store, portfolio_id, user_id=user_id)
        if index < 0:
            self.send_json(404, {"error": "not_found", "message": f"Portfolio {portfolio_id} does not exist."})
            return
        row = portfolio_rows_for_user(store, user_id=user_id, create=False)[index]
        self.send_json(
            200,
            {
                "portfolio": row,
                "summary": portfolio_summary(row),
                "userId": user_id,
                "userIdExplicit": user_id_explicit,
            },
        )

    def resolve_user_context(self) -> tuple[str, bool]:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        from_query = params.get("user", [""])[0].strip()
        from_header = self.headers.get(USER_ID_HEADER, "").strip()

        explicit = bool(from_query or from_header)
        candidate = from_query or from_header or DEFAULT_USER_ID
        if REQUIRE_USER_CONTEXT and not explicit:
            raise ValueError(
                f"Missing user context. Provide query parameter user=... or header {USER_ID_HEADER}."
            )
        return normalize_user_id(candidate), explicit

    def parse_json_body(self) -> dict:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            raise ValueError("Request body must be valid JSON.") from None
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def save_portfolio(self, portfolio_id: str | None = None) -> None:
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        universe_index = build_universe_index(load_etf_universe())
        available_codes = known_codes(universe_index)
        try:
            payload = self.parse_json_body()
        except ValueError as exc:
            self.send_json(400, {"error": "invalid_json", "message": str(exc)})
            return

        raw_id = portfolio_id if portfolio_id is not None else payload.get("id")
        try:
            normalized_id = normalize_portfolio_id(raw_id)
            name = normalize_portfolio_name(payload.get("name"))
            positions = normalize_portfolio_positions(payload, available_codes)
        except (TypeError, ValueError) as exc:
            self.send_json(400, {"error": "invalid_request", "message": str(exc)})
            return

        store = load_portfolio_store()
        row = upsert_portfolio_record(
            store=store,
            portfolio_id=normalized_id,
            name=name,
            positions=positions,
            user_id=user_id,
        )
        save_portfolio_store(store)
        self.send_json(
            200,
            {
                "portfolio": row,
                "summary": portfolio_summary(row),
                "rows": list_portfolio_summaries(store, user_id=user_id),
                "userId": user_id,
                "userIdExplicit": user_id_explicit,
            },
        )

    def delete_portfolio(self, portfolio_id: str) -> None:
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        store = load_portfolio_store()
        index = find_portfolio_index(store, portfolio_id, user_id=user_id)
        if index < 0:
            self.send_json(404, {"error": "not_found", "message": f"Portfolio {portfolio_id} does not exist."})
            return
        deleted = portfolio_rows_for_user(store, user_id=user_id, create=False).pop(index)
        save_portfolio_store(store)
        self.send_json(
            200,
            {
                "deleted": portfolio_summary(deleted),
                "rows": list_portfolio_summaries(store, user_id=user_id),
                "userId": user_id,
                "userIdExplicit": user_id_explicit,
            },
        )

    def send_watchlist(self) -> None:
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        universe_index = build_universe_index(load_etf_universe())
        rows = list_watchlist_rows(load_watchlist_store(), user_id=user_id)
        codes = [row["code"] for row in rows]
        statuses = build_updates_status_rows(
            codes=codes,
            universe_index=universe_index,
            latest_payload=load_latest_payload(),
            history_store=load_history_store(),
        )
        self.send_json(
            200,
            {
                "count": len(rows),
                "rows": rows,
                "statuses": statuses,
                "userId": user_id,
                "userIdExplicit": user_id_explicit,
            },
        )

    def send_watchlist_item(self, code: str) -> None:
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        rows = list_watchlist_rows(load_watchlist_store(), user_id=user_id)
        matched = [row for row in rows if row["code"] == code]
        if not matched:
            self.send_json(404, {"error": "not_found", "message": f"Watchlist code {code} does not exist."})
            return
        universe_index = build_universe_index(load_etf_universe())
        statuses = build_updates_status_rows(
            codes=[code],
            universe_index=universe_index,
            latest_payload=load_latest_payload(),
            history_store=load_history_store(),
        )
        self.send_json(
            200,
            {
                "row": matched[0],
                "status": statuses[0] if statuses else None,
                "userId": user_id,
                "userIdExplicit": user_id_explicit,
            },
        )

    def save_watchlist(self) -> None:
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        universe_index = build_universe_index(load_etf_universe())
        available_codes = known_codes(universe_index)
        try:
            payload = self.parse_json_body()
            code, note = normalize_watchlist_payload(payload, available_codes)
        except (TypeError, ValueError) as exc:
            self.send_json(400, {"error": "invalid_request", "message": str(exc)})
            return

        store = load_watchlist_store()
        row = upsert_watchlist_row(store, code=code, note=note, user_id=user_id)
        save_watchlist_store(store)
        rows = list_watchlist_rows(store, user_id=user_id)
        self.send_json(
            200,
            {
                "row": row,
                "rows": rows,
                "count": len(rows),
                "userId": user_id,
                "userIdExplicit": user_id_explicit,
            },
        )

    def delete_watchlist_item(self, code: str) -> None:
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        store = load_watchlist_store()
        deleted = delete_watchlist_row(store, code, user_id=user_id)
        if not deleted:
            self.send_json(404, {"error": "not_found", "message": f"Watchlist code {code} does not exist."})
            return
        save_watchlist_store(store)
        rows = list_watchlist_rows(store, user_id=user_id)
        self.send_json(
            200,
            {
                "deleted": deleted,
                "rows": rows,
                "count": len(rows),
                "userId": user_id,
                "userIdExplicit": user_id_explicit,
            },
        )

    def send_updates_status(self, query: str) -> None:
        try:
            user_id, user_id_explicit = self.resolve_user_context()
        except ValueError as exc:
            self.send_json(401, {"error": "missing_user_context", "message": str(exc)})
            return
        universe = load_etf_universe()
        universe_index = build_universe_index(universe)
        available_codes = known_codes(universe_index)
        params = parse_qs(query)
        requested = params.get("codes", [""])[0].strip()
        try:
            if requested:
                codes = parse_requested_codes(requested, available_codes)
            else:
                watch_rows = list_watchlist_rows(load_watchlist_store(), user_id=user_id)
                codes = [row["code"] for row in watch_rows if row["code"] in available_codes]
                if not codes:
                    codes = [code for code in DEFAULT_CODES if code in available_codes][:MAX_CODES_PER_REQUEST]
        except ValueError as exc:
            self.send_json(
                400,
                {
                    "error": "invalid_request",
                    "message": str(exc),
                },
            )
            return

        latest_payload = load_latest_payload()
        history_store = load_history_store()
        rows = build_updates_status_rows(
            codes=codes,
            universe_index=universe_index,
            latest_payload=latest_payload,
            history_store=history_store,
        )
        ready = sum(1 for row in rows if row.get("status") == "ready")
        partial = sum(1 for row in rows if row.get("status") == "partial")
        missing = sum(1 for row in rows if row.get("status") in {"missing", "empty"})
        self.send_json(
            200,
            {
                "count": len(rows),
                "rows": rows,
                "summary": {
                    "ready": ready,
                    "partial": partial,
                    "missing": missing,
                },
                "userId": user_id,
                "userIdExplicit": user_id_explicit,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
            },
        )

    def send_alerts(self, query: str) -> None:
        params = parse_qs(query)
        limit_raw = params.get("limit", ["20"])[0]
        try:
            limit = int(limit_raw)
        except ValueError:
            self.send_json(400, {"error": "invalid_request", "message": "limit must be an integer."})
            return
        if limit < 1 or limit > 200:
            self.send_json(400, {"error": "invalid_request", "message": "limit must be between 1 and 200."})
            return
        rows = read_recent_refresh_alerts(limit=limit)
        self.send_json(
            200,
            {
                "count": len(rows),
                "rows": rows,
            },
        )

    def send_access_logs(self, query: str) -> None:
        params = parse_qs(query)
        limit_raw = params.get("limit", ["100"])[0]
        try:
            limit = int(limit_raw)
        except ValueError:
            self.send_json(400, {"error": "invalid_request", "message": "limit must be an integer."})
            return
        if limit < 1 or limit > 500:
            self.send_json(400, {"error": "invalid_request", "message": "limit must be between 1 and 500."})
            return
        rows = read_recent_access_logs(limit=limit)
        self.send_json(
            200,
            {
                "count": len(rows),
                "rows": rows,
                "enabled": ACCESS_LOG_ENABLED,
                "file": str(ACCESS_LOG_FILE),
            },
        )

    def send_static(self, path: str) -> None:
        file_info = STATIC_FILES.get(path)
        if not file_info:
            self.send_text(404, "Not found")
            return
        relative_path, content_type = file_info
        file_path = (ROOT / relative_path).resolve()
        if not str(file_path).startswith(str(ROOT)) or not file_path.is_file():
            self.send_text(404, "Not found")
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_standard_headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.emit_access_log(status=200, content_type=content_type, bytes_sent=len(body))

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_standard_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.emit_access_log(status=status, content_type="application/json; charset=utf-8", bytes_sent=len(body))

    def send_text(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_standard_headers("text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.emit_access_log(status=status, content_type="text/plain; charset=utf-8", bytes_sent=len(body))

    def send_standard_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        origins = allowed_origins()
        origin = self.headers.get("Origin")
        if origin and origin in origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def run_refresh_once(codes_arg: str) -> int:
    universe = load_etf_universe()
    universe_index = build_universe_index(universe)
    available_codes = known_codes(universe_index)
    requested = codes_arg.strip()
    if requested:
        try:
            codes = parse_requested_codes(requested, available_codes)
        except ValueError as exc:
            print(f"[refresh-once] invalid codes: {exc}")
            return 2
    else:
        listed_codes = []
        for row in sorted(universe, key=lambda item: normalize_code(str(item.get("code", "")))):
            code = normalize_code(str(row.get("code", "")))
            if not code or code not in available_codes:
                continue
            status = str(row.get("status", "")).strip().lower()
            if status in {"", "listed"}:
                listed_codes.append(code)
        if listed_codes:
            codes = listed_codes
        else:
            codes = [code for code in DEFAULT_CODES if code in available_codes]
        if not codes:
            print("[refresh-once] invalid state: no ETF codes are configured in ETF universe.")
            return 2
    try:
        payload = persist_latest_payload(fetch_live_payload(codes))
        upsert_history_from_payload(payload)
        quality = payload.get("dataQuality", {})
        print(
            json.dumps(
                {
                    "ok": True,
                    "adapter": payload.get("adapter"),
                    "requestedCodes": payload.get("requestedCodes", []),
                    "asOf": payload.get("asOf"),
                    "etfCount": len(payload.get("etfs", [])),
                    "errorCount": len(payload.get("errors", [])),
                    "qualityStatus": quality.get("status"),
                    "partialCodes": quality.get("partialCodes", []),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        emit_refresh_alert(
            "error",
            "refresh-once execution failed.",
            {
                "requestedCodes": codes,
                "adapter": LIVE_FETCH_ADAPTER,
                "message": str(exc),
            },
        )
        print(json.dumps({"ok": False, "error": str(exc), "adapter": LIVE_FETCH_ADAPTER}, ensure_ascii=False))
        return 1


def run_check_config_once() -> int:
    status = live_fetch_config_status()
    print(json.dumps(status, ensure_ascii=False))
    if status.get("ok"):
        return 0
    emit_refresh_alert(
        "warning",
        "Live fetch config check failed.",
        {
            "adapter": status.get("adapter"),
            "issues": status.get("issues", []),
            "warnings": status.get("warnings", []),
        },
    )
    return 1


def run_check_official_registry() -> int:
    result = validate_official_source_registry(load_official_source_registry(), load_etf_universe())
    result["file"] = str(OFFICIAL_SOURCE_REGISTRY_FILE)
    result["generatedAt"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def run_check_history_quality(
    codes_arg: str,
    days: int,
    quality_mode: str,
    min_snapshots: int,
    write_report: bool = False,
) -> int:
    universe = load_etf_universe()
    universe_index = build_universe_index(universe)
    available_codes = known_codes(universe_index)
    try:
        if codes_arg.strip():
            codes = parse_requested_codes(codes_arg.strip(), available_codes)
        else:
            codes = listed_universe_codes(universe)
            if not codes:
                raise ValueError("No listed ETF codes are configured in ETF universe.")
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "reason": "invalid_codes"}, ensure_ascii=False))
        return 2

    if days < 2 or days > MAX_CHANGE_DAYS:
        print(
            json.dumps(
                {"ok": False, "error": f"history-days must be between 2 and {MAX_CHANGE_DAYS}.", "reason": "invalid_days"},
                ensure_ascii=False,
            )
        )
        return 2
    if min_snapshots < 2:
        print(json.dumps({"ok": False, "error": "min-snapshots must be at least 2.", "reason": "invalid_threshold"}, ensure_ascii=False))
        return 2

    result = evaluate_history_quality_gate(
        codes=codes,
        days=days,
        quality_mode=quality_mode,
        min_snapshots=min_snapshots,
        history_store=load_history_store(),
        stock_universe=load_stock_universe(),
    )
    result["generatedAt"] = datetime.now(timezone.utc).isoformat()
    result["codes"] = codes
    if write_report:
        save_history_quality_report(result)
    print(json.dumps(result, ensure_ascii=False))
    if result.get("ok"):
        return 0
    emit_refresh_alert(
        "warning",
        "History quality gate failed.",
        {
            "codes": codes,
            "days": days,
            "qualityMode": quality_mode,
            "minSnapshots": min_snapshots,
            "passCount": result.get("passCount"),
            "failCount": result.get("failCount"),
            "rows": result.get("rows", [])[:20],
        },
    )
    return 1


def listed_universe_codes(universe: list[dict]) -> list[str]:
    codes = []
    for row in sorted(universe, key=lambda item: normalize_code(str(item.get("code", "")))):
        code = normalize_code(str(row.get("code", "")))
        if not code:
            continue
        status = str(row.get("status", "")).strip().lower()
        if status in {"", "listed"}:
            codes.append(code)
    return codes


def build_production_data_readiness(codes_arg: str, days: int, min_snapshots: int) -> dict:
    universe = load_etf_universe()
    universe_index = build_universe_index(universe)
    available_codes = known_codes(universe_index)
    if codes_arg.strip():
        codes = parse_requested_codes(codes_arg.strip(), available_codes)
    else:
        codes = listed_universe_codes(universe)

    profile_store = load_etf_profile_store()
    profile_index = build_etf_profile_index(profile_store)
    live_config = live_fetch_config_status()
    registry_summary = official_source_registry_summary(universe)
    metrics_summary = profile_metrics_coverage_summary(universe, profile_index)
    history_gate = evaluate_history_quality_gate(
        codes=codes,
        days=days,
        quality_mode="real_only",
        min_snapshots=min_snapshots,
        history_store=load_history_store(),
        stock_universe=load_stock_universe(),
    )
    failing_history_codes = [row["code"] for row in history_gate.get("rows", []) if not row.get("ok")]

    blockers = []
    adapter = LIVE_FETCH_ADAPTER
    if not adapter_is_official(adapter):
        blockers.append(f"ETF_HOLDINGS_ADAPTER is not official: {adapter}")
    if not live_config.get("ok"):
        blockers.extend(live_config.get("issues", []))
    if history_gate.get("failCount", 0) > 0:
        blockers.append(f"{history_gate.get('failCount')} ETF codes do not have {min_snapshots} real snapshots.")
    if metrics_summary.get("missingCount", 0) or metrics_summary.get("partialCount", 0):
        blockers.append("ETF profile metrics are incomplete for the configured universe.")

    if registry_summary.get("missingListedCount", 0) > 0:
        blockers.append("Official source registry does not cover every listed ETF code.")
    if registry_summary.get("productionReadyListedCount", 0) < registry_summary.get("listedCount", 0):
        blockers.append("Official source registry does not provide full production-ready holdings for every listed ETF code.")

    return {
        "ok": not blockers,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "adapter": adapter,
        "codeCount": len(codes),
        "blockers": blockers,
        "liveFetchConfig": live_config,
        "officialSourceRegistry": registry_summary,
        "universe": {
            "count": len(universe_index),
            "listedCount": len(listed_universe_codes(universe)),
        },
        "metrics": metrics_summary,
        "history": {
            "qualityMode": "real_only",
            "days": days,
            "minSnapshots": min_snapshots,
            "passCount": history_gate.get("passCount", 0),
            "failCount": history_gate.get("failCount", 0),
            "failingCodes": failing_history_codes[:80],
        },
    }


def run_check_production_data(codes_arg: str, days: int, min_snapshots: int) -> int:
    try:
        result = build_production_data_readiness(
            codes_arg=codes_arg,
            days=days,
            min_snapshots=min_snapshots,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "reason": "invalid_request"}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def run_prune_history_once() -> int:
    store = load_history_store()
    summary = apply_history_retention_policy(store)
    changed = bool(summary.get("removedSnapshotCount", 0))
    now_iso = datetime.now(timezone.utc).isoformat()
    store["historyRetention"] = {
        "lastRunAt": now_iso,
        "lastSummary": summary,
        "policy": history_retention_settings(),
    }
    if changed:
        store["updatedAt"] = now_iso
    write_json_atomic(HISTORY_FILE, store)
    print(json.dumps({"ok": True, "changed": changed, **summary}, ensure_ascii=False))
    return 0


def run_import_universe_twse_rwd(lang: str) -> int:
    try:
        result = import_universe_from_twse_rwd(lang=lang or TWSE_RWD_LANG)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc), "lang": lang}, ensure_ascii=False))
        return 1


def run_import_metrics_etffortune(codes_arg: str, as_of: str, source: str) -> int:
    universe_index = build_universe_index(load_etf_universe())
    available_codes = known_codes(universe_index)
    codes: list[str] | None = None
    if codes_arg.strip():
        try:
            codes = parse_requested_codes(codes_arg.strip(), available_codes)
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc), "reason": "invalid_codes"}, ensure_ascii=False))
            return 2
    try:
        result = import_metrics_from_etffortune(
            codes=codes,
            as_of=as_of or None,
            source=source or "official_twse_etffortune",
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


def run_import_universe_csv(csv_path: str) -> int:
    try:
        result = import_universe_from_csv(csv_path)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc), "path": csv_path}, ensure_ascii=False))
        return 1


def run_import_metrics_csv(csv_path: str, as_of: str, source: str) -> int:
    try:
        result = import_metrics_from_csv(csv_path=csv_path, as_of=as_of or None, source=source or "official_metrics_csv")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc), "path": csv_path}, ensure_ascii=False))
        return 1


def run_import_history_snapshots(directory: str, source: str) -> int:
    try:
        result = import_history_snapshots_from_dir(directory=directory, source=source or "official_snapshot_import")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc), "directory": directory}, ensure_ascii=False))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="ETF True Exposure Lab local API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Print live fetch config status JSON and exit with code 0/1.",
    )
    parser.add_argument(
        "--check-official-registry",
        action="store_true",
        help="Validate official source registry schema, traceability metadata, and listed ETF coverage.",
    )
    parser.add_argument(
        "--check-history-quality",
        action="store_true",
        help="Check history snapshot quality for codes and exit with code 0/1.",
    )
    parser.add_argument(
        "--check-production-data",
        action="store_true",
        help="Check production data readiness across official sources, metrics, universe, and real snapshots.",
    )
    parser.add_argument(
        "--prune-history",
        action="store_true",
        help="Apply history retention policy and persist removals.",
    )
    parser.add_argument("--refresh-once", action="store_true", help="Fetch holdings once, persist, and exit.")
    parser.add_argument(
        "--import-universe-csv",
        default="",
        help="Import ETF universe from CSV and update data/etf-universe.json.",
    )
    parser.add_argument(
        "--import-universe-twse-rwd",
        action="store_true",
        help="Import ETF universe from TWSE official /rwd ETF endpoints.",
    )
    parser.add_argument(
        "--twse-lang",
        default=TWSE_RWD_LANG,
        help="Language segment used by TWSE /rwd import endpoints (default: zh).",
    )
    parser.add_argument(
        "--import-metrics-csv",
        default="",
        help="Import ETF profile metrics from CSV and update data/etf-profiles.json.",
    )
    parser.add_argument(
        "--import-metrics-etffortune",
        action="store_true",
        help="Import ETF profile metrics from TWSE ETFortune official endpoints.",
    )
    parser.add_argument(
        "--metrics-as-of",
        default="",
        help="As-of date for --import-metrics-csv (YYYY-MM-DD, YYYY/MM/DD, or ROC date).",
    )
    parser.add_argument(
        "--metrics-source",
        default="official_metrics_csv",
        help="Source label written into etf profile rows during --import-metrics-csv.",
    )
    parser.add_argument(
        "--metrics-codes",
        default="",
        help="Optional comma-separated ETF codes used by --import-metrics-etffortune.",
    )
    parser.add_argument(
        "--import-history-snapshots",
        default="",
        help="Import historical snapshot JSON files from a directory into holdings history.",
    )
    parser.add_argument(
        "--history-import-source",
        default="official_snapshot_import",
        help="Source label used when importing snapshots with --import-history-snapshots.",
    )
    parser.add_argument(
        "--codes",
        default="",
        help="Comma-separated ETF codes used by --refresh-once. When omitted, --refresh-once uses listed universe codes.",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=DEFAULT_CHANGE_DAYS,
        help="Number of days used by --check-history-quality.",
    )
    parser.add_argument(
        "--history-quality",
        default="real_only",
        help="Quality mode for --check-history-quality: any, full_only, real_only.",
    )
    parser.add_argument(
        "--min-snapshots",
        type=int,
        default=2,
        help="Minimum qualified snapshots required per code for --check-history-quality.",
    )
    parser.add_argument(
        "--write-history-quality-report",
        action="store_true",
        help="Persist --check-history-quality output to history quality report JSON file.",
    )
    parser.add_argument(
        "--production-min-snapshots",
        type=int,
        default=22,
        help="Minimum real snapshots required by --check-production-data.",
    )
    args = parser.parse_args()

    maybe_seed_history_from_latest()
    if args.import_universe_csv:
        return run_import_universe_csv(args.import_universe_csv)
    if args.import_universe_twse_rwd:
        return run_import_universe_twse_rwd(args.twse_lang)
    if args.import_metrics_csv:
        return run_import_metrics_csv(
            csv_path=args.import_metrics_csv,
            as_of=args.metrics_as_of,
            source=args.metrics_source,
        )
    if args.import_metrics_etffortune:
        etffortune_source = args.metrics_source
        if etffortune_source == "official_metrics_csv":
            etffortune_source = "official_twse_etffortune"
        return run_import_metrics_etffortune(
            codes_arg=args.metrics_codes,
            as_of=args.metrics_as_of,
            source=etffortune_source,
        )
    if args.import_history_snapshots:
        return run_import_history_snapshots(
            directory=args.import_history_snapshots,
            source=args.history_import_source,
        )
    if args.check_config:
        return run_check_config_once()
    if args.check_official_registry:
        return run_check_official_registry()
    if args.check_history_quality:
        try:
            quality_mode = normalize_changes_quality_mode(args.history_quality)
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc), "reason": "invalid_quality_mode"}, ensure_ascii=False))
            return 2
        return run_check_history_quality(
            codes_arg=args.codes,
            days=args.history_days,
            quality_mode=quality_mode,
            min_snapshots=args.min_snapshots,
            write_report=args.write_history_quality_report,
        )
    if args.check_production_data:
        return run_check_production_data(
            codes_arg=args.codes,
            days=args.history_days,
            min_snapshots=args.production_min_snapshots,
        )
    if args.prune_history:
        return run_prune_history_once()
    if args.refresh_once:
        return run_refresh_once(args.codes)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving ETF dashboard at http://{args.host}:{args.port}/index.html")
    print(f"Live refresh API at http://{args.host}:{args.port}/api/etfs/latest")
    print(f"Pipeline status API at http://{args.host}:{args.port}/api/pipeline/status")
    print(f"ETF universe API at http://{args.host}:{args.port}/api/etfs/universe?listedOnly=1")
    print(f"ETF search API at http://{args.host}:{args.port}/api/etfs/search?q=0050")
    print(f"Holdings API at http://{args.host}:{args.port}/api/etfs/00400A/holdings")
    print(f"ETF metrics API at http://{args.host}:{args.port}/api/etfs/0050/metrics")
    print(f"Holdings changes API at http://{args.host}:{args.port}/api/etfs/00400A/holdings/changes?days=22")
    print(f"Exposure compare API at http://{args.host}:{args.port}/api/exposure/compare")
    print(f"Allocation optimize API at http://{args.host}:{args.port}/api/allocation/optimize")
    print(f"Portfolios API at http://{args.host}:{args.port}/api/portfolios")
    print(f"Watchlist API at http://{args.host}:{args.port}/api/watchlist")
    print(f"Updates status API at http://{args.host}:{args.port}/api/updates/status")
    print(f"Alerts API at http://{args.host}:{args.port}/api/alerts?limit=20")
    print(f"Access logs API at http://{args.host}:{args.port}/api/access-logs?limit=100")
    print(f"Live fetch config API at http://{args.host}:{args.port}/api/live-fetch/config")
    print(
        f"Live fetch probe API at http://{args.host}:{args.port}/api/live-fetch/probe?code=00400A&adapter=official_pcf_twse"
    )
    print(f"Live fetch settings: {json.dumps(live_fetch_settings(), ensure_ascii=False)}")
    print(f"Health check at http://{args.host}:{args.port}/api/health")
    print(f"History quality API at http://{args.host}:{args.port}/api/history/quality?quality=real_only&minSnapshots=2")
    print(f"Latest history quality report API at http://{args.host}:{args.port}/api/history/quality/latest")
    print("History quality gate CLI: python server.py --check-history-quality --codes 00400A --history-quality real_only")
    print("Production data readiness CLI: python server.py --check-production-data --production-min-snapshots 22")
    print("History quality report CLI: python server.py --check-history-quality --write-history-quality-report")
    print("History prune CLI: python server.py --prune-history")
    print("Universe import CLI: python server.py --import-universe-csv data/universe.csv")
    print("TWSE universe import CLI: python server.py --import-universe-twse-rwd")
    print("Metrics import CLI: python server.py --import-metrics-csv data/metrics.csv --metrics-as-of 2026-06-01")
    print("ETFortune metrics import CLI: python server.py --import-metrics-etffortune --metrics-codes 0050,00878")
    print("History snapshot import CLI: python server.py --import-history-snapshots data/official-history")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
