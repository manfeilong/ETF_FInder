from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "latest-etf-holdings.json"
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


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"tr", "td", "th", "li", "br", "p", "div", "section", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def text(self) -> str:
        return "\n".join(self.parts)


def get_url(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 ETF True Exposure Lab data refresh",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def html_to_lines(markup: str) -> list[str]:
    parser = TextExtractor()
    parser.feed(markup)
    text = html.unescape(parser.text())
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_etfinfo_holdings(code: str, markup: str) -> dict:
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


def fetch_live_payload(codes: list[str]) -> dict:
    etfs = []
    errors = []
    as_of_values = []

    def fetch_one(code: str) -> dict:
        url = f"https://www.etfinfo.tw/etf/{code}/holdings"
        try:
            parsed = parse_etfinfo_holdings(code, get_url(url))
            if parsed["holdings"]:
                return {"ok": True, "payload": parsed}
            return {"ok": False, "error": {"code": code, "message": "No holdings parsed", "url": url}}
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return {"ok": False, "error": {"code": code, "message": str(exc), "url": url}}

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
        raise RuntimeError("No live ETF holdings could be fetched.")

    etfs.sort(key=lambda item: codes.index(item["code"]) if item["code"] in codes else len(codes))
    as_of = max(as_of_values) if as_of_values else time.strftime("%Y-%m-%d")
    return {
        "asOf": as_of,
        "source": "ETFInfo public page",
        "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "requestedCodes": codes,
        "etfs": etfs,
        "errors": errors,
    }


def persist_latest_payload(payload: dict) -> dict:
    persisted = {
        **payload,
        "savedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "savedTo": "data/latest-etf-holdings.json",
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = DATA_FILE.with_suffix(".json.tmp")
    temporary_file.write_text(
        json.dumps(persisted, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_file.replace(DATA_FILE)
    return persisted


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/etfs/latest":
            self.send_latest(parsed.query)
            return
        super().do_GET()

    def send_latest(self, query: str) -> None:
        params = parse_qs(query)
        requested = params.get("codes", [""])[0].strip()
        codes = [part.strip().upper() for part in requested.split(",") if part.strip()] or DEFAULT_CODES
        try:
            payload = persist_latest_payload(fetch_live_payload(codes))
            self.send_json(200, payload)
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                502,
                {
                    "error": "live_fetch_failed",
                    "message": str(exc),
                    "source": "ETFInfo public page",
                },
            )

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="ETF True Exposure Lab local API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving ETF dashboard at http://{args.host}:{args.port}/index.html")
    print(f"Live refresh API at http://{args.host}:{args.port}/api/etfs/latest")
    server.serve_forever()


if __name__ == "__main__":
    main()
