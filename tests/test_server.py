import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import server


class ServerLogicTests(unittest.TestCase):
    def test_listed_flag_trusts_listed_status_when_date_is_unavailable(self):
        self.assertTrue(server.listed_flag({"status": "listed", "listedDate": ""}, "2026-09-12"))
        self.assertTrue(server.listed_flag({"status": "listed", "listedDate": "2026-09-11"}, "2026-09-12"))
        self.assertFalse(server.listed_flag({"status": "listed", "listedDate": "2026-09-13"}, "2026-09-12"))
        self.assertFalse(server.listed_flag({"status": "upcoming", "listedDate": ""}, "2026-09-12"))

    def test_parse_requested_codes_dedup_and_order(self):
        available = {"00400A", "009816", "0050"}
        result = server.parse_requested_codes("00400A,009816,00400A", available)
        self.assertEqual(result, ["00400A", "009816"])

    def test_parse_requested_codes_reject_invalid(self):
        available = {"00400A"}
        with self.assertRaises(ValueError):
            server.parse_requested_codes("BAD_CODE", available)

    def test_parse_requested_codes_accepts_leading_zero_loss(self):
        available = {"00400A", "009816"}
        result = server.parse_requested_codes("400A,9816", available)
        self.assertEqual(result, ["00400A", "009816"])

    def test_parse_requested_codes_recovers_shell_numeric_with_unique_suffix_match(self):
        available = {"00631L", "00632R", "00400A"}
        result = server.parse_requested_codes("631,632R", available)
        self.assertEqual(result, ["00631L", "00632R"])

    def test_parse_requested_codes_ignores_stale_defaults(self):
        available = {"00400A", "00403A", "009816"}
        result = server.parse_requested_codes("", available)
        self.assertEqual(result, ["00400A", "00403A", "009816"])

    def test_parse_requested_codes_falls_back_to_available_universe(self):
        available = {"0050", "0056"}
        result = server.parse_requested_codes("", available)
        self.assertEqual(result, ["0050", "0056"])

    def test_parse_requested_codes_rejects_empty_universe(self):
        with self.assertRaisesRegex(ValueError, "No ETF codes"):
            server.parse_requested_codes("", set())

    def test_profile_index_and_view(self):
        profile_store = {
            "asOf": "2026-05-27",
            "source": "seed",
            "rows": [
                {
                    "code": "0050",
                    "strategy": "passive",
                    "assetClass": "equity",
                    "region": "tw",
                    "expenseRatioPct": "0.32",
                    "trackingErrorPct": "0.45%",
                }
            ],
        }
        index = server.build_etf_profile_index(profile_store)
        self.assertIn("0050", index)
        view = server.profile_view(index["0050"])
        self.assertEqual(view["strategy"], "passive")
        self.assertAlmostEqual(view["expenseRatioPct"], 0.32, places=4)
        self.assertAlmostEqual(view["trackingErrorPct"], 0.45, places=4)

    def test_filter_universe_rows_with_profile_filters(self):
        universe = [
            {"code": "0050", "name": "ETF A", "status": "listed", "listedDate": "2020-01-01", "tags": ["tw"]},
            {"code": "00983A", "name": "ETF B", "status": "listed", "listedDate": "2024-01-01", "tags": ["global"]},
        ]
        profile_index = {
            "0050": {"code": "0050", "strategy": "passive", "assetClass": "equity", "region": "tw"},
            "00983A": {"code": "00983A", "strategy": "active", "assetClass": "equity", "region": "global"},
        }
        rows = server.filter_universe_rows(
            universe=universe,
            reference_date="2026-05-27",
            profile_index=profile_index,
            query="",
            strategy_values={"passive"},
            region_values={"tw"},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["code"], "0050")

    def test_profile_coverage_summary(self):
        universe = [{"code": "0050"}, {"code": "006208"}, {"code": "00878"}]
        profile_index = {"0050": {"code": "0050"}, "00878": {"code": "00878"}}
        summary = server.profile_coverage_summary(universe, profile_index)
        self.assertEqual(summary["universeCount"], 3)
        self.assertEqual(summary["coveredCount"], 2)
        self.assertEqual(summary["missingCount"], 1)
        self.assertEqual(summary["missingCodes"], ["006208"])

    def test_profile_metrics_coverage_summary_reports_missing_by_field(self):
        universe = [{"code": "0050"}, {"code": "0056"}]
        profile_index = {
            "0050": {"code": "0050", "aumTwdBn": 10.0},
            "0056": {"code": "0056", "aumTwdBn": 20.0, "expenseRatioPct": 0.3},
        }
        summary = server.profile_metrics_coverage_summary(universe, profile_index)
        self.assertEqual(summary["byField"]["aumTwdBn"]["availableCount"], 2)
        self.assertEqual(summary["byField"]["expenseRatioPct"]["missingCount"], 1)
        self.assertEqual(summary["byField"]["expenseRatioPct"]["missingCodes"], ["0050"])

    def test_snapshot_quality_check_strict(self):
        row_full = {"coverage": "full", "declaredHoldingCount": 50, "parsedHoldingCount": 50}
        row_partial = {"coverage": "partial_official_endpoint", "declaredHoldingCount": 50, "parsedHoldingCount": 15}
        ok, _ = server.snapshot_quality_check(row_full, require_full=True, min_declared=30, min_parsed=30)
        self.assertTrue(ok)
        ok2, reason2 = server.snapshot_quality_check(row_partial, require_full=True, min_declared=30, min_parsed=30)
        self.assertFalse(ok2)
        self.assertIn("coverage", reason2)

    def test_snapshot_quality_check_rejects_unavailable_weights(self):
        row = {
            "coverage": "partial_official_pcf_missing_weights",
            "declaredHoldingCount": 30,
            "parsedHoldingCount": 30,
            "holdings": {"2330": 0.0, "2454": 0.0},
        }
        ok, reason = server.snapshot_quality_check(row, require_full=False, min_declared=0, min_parsed=0)
        self.assertFalse(ok)
        self.assertIn("all zero", reason)

    def test_parse_etfinfo_holdings_prefers_nuxt_payload(self):
        nuxt_pool = [
            None,
            {"etf-detail-base-00400A": 2},
            {"holdings": 3},
            {"snapshotDate": 4, "source": 5, "holdings": 6},
            "2026-06-01",
            "issuer-official",
            [7, 8],
            {"code": 9, "name": 10, "weight": 11, "shares": 12},
            {"code": 13, "name": 14, "weight": 15, "shares": 16},
            "2330",
            "台積電",
            58.28,
            488733482,
            "2454",
            "聯發科",
            6.42,
            29430406,
        ]
        markup = (
            '<script type="application/json" id="__NUXT_DATA__">'
            + json.dumps(nuxt_pool, ensure_ascii=False)
            + "</script>"
        )
        parsed = server.parse_etfinfo_holdings("00400A", markup)
        self.assertEqual(parsed["code"], "00400A")
        self.assertEqual(parsed["asOf"], "2026-06-01")
        self.assertEqual(parsed["coverage"], "full")
        self.assertEqual(parsed["declaredHoldingCount"], 2)
        self.assertEqual(parsed["parsedHoldingCount"], 2)
        self.assertAlmostEqual(parsed["holdings"]["2330"], 58.28, places=4)
        self.assertEqual(parsed["holdingDetails"][0]["shares"], "488733482")
        self.assertIn("issuer-official", parsed["source"])

    def test_import_universe_from_csv(self):
        original_universe = server.ETF_UNIVERSE_FILE
        original_profile = server.ETF_PROFILE_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            server.ETF_UNIVERSE_FILE = base / "etf-universe.json"
            server.ETF_PROFILE_FILE = base / "etf-profiles.json"
            server.ETF_UNIVERSE_FILE.write_text("[]", encoding="utf-8")
            server.ETF_PROFILE_FILE.write_text('{"rows":[]}', encoding="utf-8")
            csv_path = base / "universe.csv"
            csv_path.write_text(
                "code,name,listedDate,strategy,assetClass,region,distributionType,leverageType\n"
                "0050,ETF50,2003-06-30,passive,equity,tw,distribution,regular\n"
                "00905,ETF Bond,2024-01-01,passive,bond,tw,distribution,regular\n",
                encoding="utf-8",
            )
            try:
                result = server.import_universe_from_csv(str(csv_path))
                self.assertTrue(result["ok"])
                saved = server.load_etf_universe()
                self.assertEqual(len(saved), 2)
                by_code = {row["code"]: row for row in saved}
                self.assertEqual(by_code["0050"]["strategy"], "passive")
                self.assertEqual(by_code["00905"]["assetClass"], "bond")
            finally:
                server.ETF_UNIVERSE_FILE = original_universe
                server.ETF_PROFILE_FILE = original_profile

    def test_import_metrics_from_csv(self):
        original_profile = server.ETF_PROFILE_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            server.ETF_PROFILE_FILE = base / "etf-profiles.json"
            server.ETF_PROFILE_FILE.write_text('{"rows":[]}', encoding="utf-8")
            csv_path = base / "metrics.csv"
            csv_path.write_text(
                "code,expenseRatio,aum,avgDailyVolume,premiumDiscount,dividendYield,trackingError\n"
                "0050,0.32,395.2,56.4,0.01,3.5,0.45\n",
                encoding="utf-8",
            )
            try:
                result = server.import_metrics_from_csv(str(csv_path), as_of="2026-06-01", source="official_metrics_csv")
                self.assertTrue(result["ok"])
                store = server.load_etf_profile_store()
                index = server.build_etf_profile_index(store)
                row = index["0050"]
                self.assertAlmostEqual(row["expenseRatioPct"], 0.32, places=4)
                self.assertAlmostEqual(row["trackingErrorPct"], 0.45, places=4)
                self.assertEqual(store["asOf"], "2026-06-01")
            finally:
                server.ETF_PROFILE_FILE = original_profile

    def test_fetch_etffortune_chart_series_retries_same_origin_308_with_cookie(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'[{"date":"2026/09/11","count":"10"}]'

        redirect = server.urllib.error.HTTPError(
            "https://www.twse.com.tw/chart",
            308,
            "Permanent Redirect",
            {"Location": "/chart", "Set-Cookie": "__chtcdn=challenge; path=/; Secure"},
            io.BytesIO(),
        )
        requests = []

        def fake_urlopen(request, timeout=20):
            requests.append(request)
            if len(requests) == 1:
                raise redirect
            return FakeResponse()

        original_endpoint = server.ETFFORTUNE_CHART_ENDPOINT
        original_base = server.TWSE_RWD_BASE_URL
        try:
            server.HTTP_CHALLENGE_COOKIE_CACHE.clear()
            server.TWSE_RWD_BASE_URL = "https://www.twse.com.tw"
            server.ETFFORTUNE_CHART_ENDPOINT = "/chart"
            with patch("server.urllib.request.urlopen", side_effect=fake_urlopen):
                payload = server.fetch_etffortune_chart_series(
                    "0050",
                    server.date(2025, 9, 12),
                    server.date(2026, 9, 12),
                    "close",
                )
            self.assertEqual(payload[0]["count"], "10")
            self.assertEqual(requests[1].get_header("Cookie"), "__chtcdn=challenge")
            self.assertEqual(requests[1].get_method(), "POST")
        finally:
            server.HTTP_CHALLENGE_COOKIE_CACHE.clear()
            server.ETFFORTUNE_CHART_ENDPOINT = original_endpoint
            server.TWSE_RWD_BASE_URL = original_base

    def test_import_history_snapshots_from_dir(self):
        original_history = server.HISTORY_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            server.HISTORY_FILE = base / "holdings-history.json"
            server.HISTORY_FILE.write_text('{"history":{}}', encoding="utf-8")
            snapshot_dir = base / "snapshots" / "2026-05-30"
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "0050.json").write_text(
                """{
  "code": "0050",
  "asOf": "2026-05-30",
  "coverage": "full",
  "declaredHoldingCount": 2,
  "parsedHoldingCount": 2,
  "holdings": {
    "2330": 31.0,
    "2317": 5.0
  }
}
""",
                encoding="utf-8",
            )
            try:
                result = server.import_history_snapshots_from_dir(str(base / "snapshots"))
                self.assertTrue(result["ok"])
                history = server.load_history_store()
                self.assertIn("0050", history["history"])
                self.assertIn("2026-05-30", history["history"]["0050"])
            finally:
                server.HISTORY_FILE = original_history

    def test_extract_twse_code_tokens_multiline(self):
        raw = "006205(新臺幣)\n00625K(人民幣)\n00636K(美元)"
        self.assertEqual(server.extract_twse_code_tokens(raw), ["006205", "00625K", "00636K"])

    def test_parse_twse_rwd_category_rows_pairing(self):
        payload = {
            "data": [
                ["006205(新臺幣)\n00625K(人民幣)", "富邦上証(新臺幣)\n富邦上証+R(人民幣)", "", "foreign"]
            ]
        }
        rows = server.parse_twse_rwd_category_rows(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["code"], "006205")
        self.assertEqual(rows[1]["code"], "00625K")
        self.assertEqual(rows[0]["category"], "foreign")

    def test_import_universe_from_twse_rwd_with_mock_payloads(self):
        original_universe = server.ETF_UNIVERSE_FILE
        original_profile = server.ETF_PROFILE_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            server.ETF_UNIVERSE_FILE = base / "etf-universe.json"
            server.ETF_PROFILE_FILE = base / "etf-profiles.json"
            server.ETF_UNIVERSE_FILE.write_text("[]", encoding="utf-8")
            server.ETF_PROFILE_FILE.write_text('{"rows":[]}', encoding="utf-8")

            route_payloads = {
                "/ETF/list": {
                    "stat": "OK",
                    "data": [
                        ["2003.06.30", "0050", "元大台灣50", "IssuerA", "臺灣50指數"],
                        ["2024.01.15", "00980A", "主動野村臺灣優選", "IssuerB", "無"],
                        ["2024.02.20", "00710B", "復華彭博非投等債", "IssuerC", "彭博非投等債指數"],
                    ],
                },
                "/ETF/domestic": {
                    "status": "success",
                    "data": [
                        ["0050", "元大台灣50", "", "domestic"],
                        ["00980A", "主動野村臺灣優選", "主動式交易所交易基金", "domestic"],
                    ],
                },
                "/ETF/foreign": {"status": "success", "data": []},
                "/ETF/li": {"status": "success", "data": []},
                "/ETF/activeList": {
                    "status": "success",
                    "data": [["00980A", "主動野村臺灣優選", "主動式交易所交易基金", "domestic"]],
                },
                "/ETF/BFIncome": {
                    "status": "success",
                    "data": [["00710B", "復華彭博非投等債", "", "bfIncome"]],
                },
                "/ETF/liFutures": {"status": "success", "data": []},
                "/ETF/vanillaFutures": {"status": "success", "data": []},
            }

            def fake_fetch(route, lang="zh"):
                self.assertEqual(lang, "zh")
                if route not in route_payloads:
                    raise AssertionError(f"Unexpected route {route}")
                return route_payloads[route]

            try:
                with patch("server.fetch_twse_rwd_payload", side_effect=fake_fetch):
                    result = server.import_universe_from_twse_rwd(lang="zh")
                self.assertTrue(result["ok"])
                rows = server.load_etf_universe()
                self.assertEqual(len(rows), 3)
                by_code = {row["code"]: row for row in rows}
                self.assertEqual(by_code["00980A"]["strategy"], "active")
                self.assertEqual(by_code["00710B"]["assetClass"], "bond")
                store = server.load_etf_profile_store()
                self.assertEqual(store["source"], "official_twse_rwd")
            finally:
                server.ETF_UNIVERSE_FILE = original_universe
                server.ETF_PROFILE_FILE = original_profile

    def test_import_metrics_from_etffortune_with_mock_payloads(self):
        original_profile = server.ETF_PROFILE_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            server.ETF_PROFILE_FILE = base / "etf-profiles.json"
            server.ETF_PROFILE_FILE.write_text('{"rows":[]}', encoding="utf-8")

            fake_products = [
                {
                    "stockNo": "0050",
                    "stockName": "ETF 50",
                    "listingDate": "2003.06.30",
                    "indexName": "TW50",
                    "totalAv": "200.0",
                    "close1": "100.0",
                    "holders": "123,456",
                    "valueYTD": "10.5",
                    "volumeYTD": "5,000,000",
                    "issuer": "IssuerA",
                }
            ]

            close_series = [
                {"date": "2025/06/01", "count": 80.0},
                {"date": "2026/01/02", "count": 90.0},
                {"date": "2026/03/01", "count": 95.0},
                {"date": "2026/05/01", "count": 98.0},
                {"date": "2026/06/01", "count": 100.0},
            ]
            fund_series = {
                "netPrice": [
                    {"date": "2026/05/30", "count": 99.2},
                    {"date": "2026/06/01", "count": 99.5},
                ],
                "atmps": [
                    {"date": "2026/05/30", "count": 0.25},
                    {"date": "2026/06/01", "count": 0.35},
                ],
            }

            def fake_chart(code, start_date, end_date, series_type):
                self.assertEqual(code, "0050")
                if series_type == "close":
                    return close_series
                if series_type == "fundPric":
                    return fund_series
                return []

            try:
                with patch("server.fetch_etffortune_products_rows", return_value=fake_products):
                    with patch("server.fetch_etffortune_chart_series", side_effect=fake_chart):
                        result = server.import_metrics_from_etffortune(
                            codes=["0050"],
                            as_of="2026-06-01",
                            source="official_twse_etffortune",
                        )
                self.assertTrue(result["ok"])
                store = server.load_etf_profile_store()
                row = server.build_etf_profile_index(store)["0050"]
                self.assertAlmostEqual(row["aumTwdBn"], 20.0, places=4)
                self.assertAlmostEqual(row["avgDailyVolumeM"], 5.0, places=4)
                self.assertAlmostEqual(row["premiumDiscountPct"], 0.35, places=4)
                self.assertIn("return1mPct", row)
            finally:
                server.ETF_PROFILE_FILE = original_profile

    def test_summarize_quality_partial(self):
        etfs = [
            {
                "code": "00400A",
                "declaredHoldingCount": 40,
                "parsedHoldingCount": 20,
                "coverage": "partial_public_page",
            }
        ]
        summary = server.summarize_quality(etfs, [])
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["declaredHoldingCount"], 40)
        self.assertEqual(summary["parsedHoldingCount"], 20)
        self.assertEqual(summary["partialCodes"], ["00400A"])

    def test_build_changes_response_from_two_snapshots(self):
        history_store = {
            "history": {
                "00400A": {
                    "2026-05-21": {
                        "holdings": {"2330": 8.0, "2454": 5.0},
                        "holdingDetails": [
                            {"code": "2330", "shares": "1000", "price": "100"},
                            {"code": "2454", "shares": "2000", "price": "200"},
                        ],
                    },
                    "2026-05-22": {
                        "holdings": {"2330": 9.0, "2454": 4.5},
                        "holdingDetails": [
                            {"code": "2330", "shares": "1300", "price": "110"},
                            {"code": "2454", "shares": "1800", "price": "190"},
                        ],
                    },
                }
            }
        }
        stock_universe = {
            "2330": {"name": "台積電", "sector": "半導體業"},
            "2454": {"name": "聯發科", "sector": "半導體業"},
        }
        payload = server.build_changes_response("00400A", 22, history_store, stock_universe)
        self.assertEqual(payload["code"], "00400A")
        self.assertEqual(len(payload["rows"]), 1)
        row = payload["rows"][0]
        self.assertEqual(row["date"], "2026-05-22")
        self.assertGreater(row["turnover"], 0)
        self.assertTrue(any(item["code"] == "2330" for item in row["increases"]))

    def test_build_changes_response_real_only_filters_non_real(self):
        history_store = {
            "history": {
                "00400A": {
                    "2026-05-21": {
                        "source": "seed",
                        "coverage": "seed",
                        "declaredHoldingCount": 2,
                        "parsedHoldingCount": 2,
                        "holdings": {"2330": 8.0, "2454": 5.0},
                        "holdingDetails": [],
                    },
                    "2026-05-22": {
                        "source": "Official PCF/TWSE endpoint",
                        "adapter": "official_endpoint",
                        "coverage": "full",
                        "declaredHoldingCount": 2,
                        "parsedHoldingCount": 2,
                        "holdings": {"2330": 9.0, "2454": 4.5},
                        "holdingDetails": [],
                    },
                    "2026-05-23": {
                        "source": "Official PCF/TWSE endpoint",
                        "adapter": "official_endpoint",
                        "coverage": "full",
                        "declaredHoldingCount": 2,
                        "parsedHoldingCount": 2,
                        "holdings": {"2330": 9.5, "2454": 4.3},
                        "holdingDetails": [],
                    },
                }
            }
        }
        payload = server.build_changes_response("00400A", 22, history_store, {}, quality_mode="real_only")
        self.assertEqual(payload["qualityMode"], "real_only")
        self.assertEqual(payload["snapshotDates"], ["2026-05-22", "2026-05-23"])
        self.assertEqual(len(payload["rows"]), 1)
        self.assertTrue(payload["rows"][0]["realSnapshot"])

    def test_evaluate_history_quality_gate(self):
        history_store = {
            "history": {
                "00400A": {
                    "2026-05-24": {
                        "source": "Official PCF/TWSE endpoint",
                        "adapter": "official_endpoint",
                        "coverage": "full",
                        "declaredHoldingCount": 1,
                        "parsedHoldingCount": 1,
                        "holdings": {"2330": 10.0},
                        "holdingDetails": [],
                    },
                    "2026-05-25": {
                        "source": "Official PCF/TWSE endpoint",
                        "adapter": "official_endpoint",
                        "coverage": "full",
                        "declaredHoldingCount": 1,
                        "parsedHoldingCount": 1,
                        "holdings": {"2330": 10.1},
                        "holdingDetails": [],
                    },
                }
            }
        }
        gate = server.evaluate_history_quality_gate(
            codes=["00400A"],
            days=22,
            quality_mode="real_only",
            min_snapshots=2,
            history_store=history_store,
            stock_universe={},
        )
        self.assertTrue(gate["ok"])
        self.assertEqual(gate["passCount"], 1)
        self.assertEqual(gate["rows"][0]["qualifiedSnapshotCount"], 2)

    def test_normalize_changes_quality_mode(self):
        self.assertEqual(server.normalize_changes_quality_mode("any"), "any")
        self.assertEqual(server.normalize_changes_quality_mode("full_only"), "full_only")
        self.assertEqual(server.normalize_changes_quality_mode("real_only"), "real_only")
        with self.assertRaises(ValueError):
            server.normalize_changes_quality_mode("bad_mode")

    def test_compute_exposure_compare(self):
        positions = [{"code": "00400A", "allocation": 100}]
        latest_payload = {}
        history_store = {
            "history": {
                "00400A": {
                    "2026-05-22": {
                        "holdings": {"2330": 10.0, "2454": 5.0},
                        "holdingDetails": [],
                    }
                }
            }
        }
        universe_index = {"00400A": {"code": "00400A", "holdings": {"2330": 8.0}}}
        stock_universe = {
            "2330": {"name": "台積電", "sector": "半導體業"},
            "2454": {"name": "聯發科", "sector": "半導體業"},
        }
        result = server.compute_exposure_compare(
            positions=positions,
            latest_payload=latest_payload,
            history_store=history_store,
            universe_index=universe_index,
            stock_universe=stock_universe,
        )
        self.assertEqual(result["totalAllocation"], 100)
        self.assertEqual(result["exposures"][0]["code"], "2330")
        self.assertAlmostEqual(result["exposures"][0]["total"], 10.0, places=4)

    def test_normalize_optimize_targets(self):
        targets = server.normalize_optimize_targets(
            {
                "targets": [
                    {"sector": "半導體業", "weight": 70},
                    {"sector": "金融保險業", "weight": 30},
                    {"sector": "半導體業", "weight": 30},
                ]
            }
        )
        by_sector = {row["sector"]: row["weight"] for row in targets}
        self.assertAlmostEqual(by_sector["半導體業"], 76.9230769, places=4)
        self.assertAlmostEqual(by_sector["金融保險業"], 23.0769231, places=4)

    def test_optimize_allocation(self):
        universe = [
            {
                "code": "00400A",
                "name": "A",
                "status": "listed",
                "listedDate": "2026-01-01",
                "source": "API",
            },
            {
                "code": "00403A",
                "name": "B",
                "status": "listed",
                "listedDate": "2026-01-01",
                "source": "API",
            },
        ]
        universe_index = {row["code"]: row for row in universe}
        latest_payload = {"asOf": "2026-05-22"}
        history_store = {
            "history": {
                "00400A": {
                    "2026-05-22": {
                        "holdings": {"2330": 60.0, "2454": 30.0, "2881": 10.0},
                        "holdingDetails": [],
                    }
                },
                "00403A": {
                    "2026-05-22": {
                        "holdings": {"2881": 55.0, "2891": 35.0, "2330": 10.0},
                        "holdingDetails": [],
                    }
                },
            }
        }
        stock_universe = {
            "2330": {"name": "TSMC", "sector": "半導體業"},
            "2454": {"name": "MediaTek", "sector": "半導體業"},
            "2881": {"name": "Fubon", "sector": "金融保險業"},
            "2891": {"name": "CTBC", "sector": "金融保險業"},
        }

        payload = {
            "targets": [
                {"sector": "半導體業", "weight": 70},
                {"sector": "金融保險業", "weight": 30},
            ],
            "maxEtfs": 2,
        }
        result = server.optimize_allocation(
            payload=payload,
            universe=universe,
            universe_index=universe_index,
            latest_payload=latest_payload,
            history_store=history_store,
            stock_universe=stock_universe,
        )
        self.assertEqual(result["requestedMaxEtfs"], 2)
        self.assertEqual(len(result["selected"]), 2)
        self.assertAlmostEqual(sum(row["allocation"] for row in result["selected"]), 100, places=1)
        self.assertEqual(result["selected"][0]["code"], "00400A")

    def test_portfolio_upsert_and_summary(self):
        store = {"portfolios": []}
        row = server.upsert_portfolio_record(
            store=store,
            portfolio_id="pf_a",
            name="My Portfolio",
            positions=[
                {"code": "00400A", "allocation": 60},
                {"code": "00403A", "allocation": 40},
            ],
        )
        self.assertEqual(row["id"], "pf_a")
        self.assertEqual(len(store["portfolios"]), 1)

        row2 = server.upsert_portfolio_record(
            store=store,
            portfolio_id="pf_a",
            name="My Portfolio v2",
            positions=[
                {"code": "00400A", "allocation": 50},
                {"code": "00403A", "allocation": 50},
            ],
        )
        self.assertEqual(len(store["portfolios"]), 1)
        self.assertEqual(row2["name"], "My Portfolio v2")
        summary = server.portfolio_summary(row2)
        self.assertEqual(summary["positionCount"], 2)
        self.assertAlmostEqual(summary["totalAllocation"], 100.0, places=4)

    def test_portfolio_user_scoped_operations(self):
        store = {"portfolios": []}
        server.upsert_portfolio_record(
            store=store,
            portfolio_id="pf_public",
            name="Public",
            positions=[{"code": "00400A", "allocation": 100}],
        )
        server.upsert_portfolio_record(
            store=store,
            portfolio_id="pf_alice",
            name="Alice",
            positions=[{"code": "00403A", "allocation": 100}],
            user_id="alice_01",
        )
        server.upsert_portfolio_record(
            store=store,
            portfolio_id="pf_bob",
            name="Bob",
            positions=[{"code": "009816", "allocation": 100}],
            user_id="bob_01",
        )

        alice_rows = server.list_portfolio_summaries(store, user_id="alice_01")
        bob_rows = server.list_portfolio_summaries(store, user_id="bob_01")
        public_rows = server.list_portfolio_summaries(store)

        self.assertEqual(len(alice_rows), 1)
        self.assertEqual(alice_rows[0]["id"], "pf_alice")
        self.assertEqual(len(bob_rows), 1)
        self.assertEqual(bob_rows[0]["id"], "pf_bob")
        self.assertEqual(len(public_rows), 1)
        self.assertEqual(public_rows[0]["id"], "pf_public")

    def test_normalize_portfolio_name_validation(self):
        with self.assertRaises(ValueError):
            server.normalize_portfolio_name("")
        self.assertEqual(server.normalize_portfolio_name("  Alpha  "), "Alpha")

    def test_normalize_user_id(self):
        self.assertEqual(server.normalize_user_id("alice_01"), "alice_01")
        with self.assertRaises(ValueError):
            server.normalize_user_id("a")
        with self.assertRaises(ValueError):
            server.normalize_user_id("bad user")

    def test_normalize_watchlist_payload(self):
        code, note = server.normalize_watchlist_payload(
            {"code": "00400A", "note": "high priority"},
            {"00400A", "00403A"},
        )
        self.assertEqual(code, "00400A")
        self.assertEqual(note, "high priority")
        with self.assertRaises(ValueError):
            server.normalize_watchlist_payload({"code": "BAD!"}, {"00400A"})

    def test_build_updates_status_rows(self):
        universe_index = {
            "00400A": {"code": "00400A", "name": "ETF A", "holdings": {"2330": 10.0}},
            "00403A": {"code": "00403A", "name": "ETF B", "holdings": {"2454": 8.0}},
        }
        latest_payload = {"savedAt": "2026-05-24T00:00:00+00:00", "etfs": []}
        history_store = {
            "history": {
                "00400A": {
                    "2026-05-23": {
                        "holdings": {"2330": 11.0},
                        "coverage": "full",
                        "declaredHoldingCount": 1,
                        "parsedHoldingCount": 1,
                        "holdingDetails": [],
                        "source": "history",
                    }
                }
            }
        }
        rows = server.build_updates_status_rows(
            codes=["00400A", "00403A"],
            universe_index=universe_index,
            latest_payload=latest_payload,
            history_store=history_store,
        )
        by_code = {row["code"]: row for row in rows}
        self.assertEqual(by_code["00400A"]["status"], "ready")
        self.assertEqual(by_code["00400A"]["historySnapshotCount"], 1)
        self.assertIn(by_code["00403A"]["status"], {"seed", "partial", "ready", "empty"})

    def test_watchlist_upsert_and_delete(self):
        store = {"rows": []}
        created = server.upsert_watchlist_row(store, code="00400A", note="breakout")
        self.assertEqual(created["code"], "00400A")
        self.assertEqual(created["note"], "breakout")
        self.assertEqual(len(store["rows"]), 1)

        updated = server.upsert_watchlist_row(store, code="00400A", note="pullback")
        self.assertEqual(updated["note"], "pullback")
        self.assertEqual(len(store["rows"]), 1)

        deleted = server.delete_watchlist_row(store, "00400A")
        self.assertIsNotNone(deleted)
        self.assertEqual(len(store["rows"]), 0)

    def test_watchlist_user_scoped_operations(self):
        store = {"rows": []}
        server.upsert_watchlist_row(store, code="00400A", note="public")
        server.upsert_watchlist_row(store, code="00403A", note="alice", user_id="alice_01")
        server.upsert_watchlist_row(store, code="009816", note="bob", user_id="bob_01")

        self.assertEqual([row["code"] for row in server.list_watchlist_rows(store)], ["00400A"])
        self.assertEqual([row["code"] for row in server.list_watchlist_rows(store, user_id="alice_01")], ["00403A"])
        self.assertEqual([row["code"] for row in server.list_watchlist_rows(store, user_id="bob_01")], ["009816"])

        deleted = server.delete_watchlist_row(store, "00403A", user_id="alice_01")
        self.assertIsNotNone(deleted)
        self.assertFalse(server.list_watchlist_rows(store, user_id="alice_01"))

    def test_status_level_from_snapshot(self):
        self.assertEqual(server.status_level_from_snapshot({"coverage": "full"}), "ready")
        self.assertEqual(server.status_level_from_snapshot({"coverage": "seed", "holdings": {"2330": 8}}), "seed")
        self.assertEqual(server.status_level_from_snapshot({"coverage": "partial_public_page", "holdings": {"2330": 8}}), "partial")
        self.assertEqual(server.status_level_from_snapshot({"coverage": "partial_public_page", "holdings": {}}), "empty")

    def test_select_live_adapter(self):
        default_adapter = server.select_live_adapter("etfinfo_public_page")
        self.assertEqual(default_adapter.name, "etfinfo_public_page")
        official_adapter = server.select_live_adapter("official")
        self.assertIn(
            official_adapter.name,
            {"official_snapshot_file", "official_endpoint", "official_pcf_twse", "official_registry"},
        )
        stub_adapter = server.select_live_adapter("official_pcf_stub")
        self.assertEqual(stub_adapter.name, "official_pcf_twse")
        pcf_adapter = server.select_live_adapter("official_pcf_twse")
        self.assertEqual(pcf_adapter.name, "official_pcf_twse")
        endpoint_adapter = server.select_live_adapter("official_endpoint")
        self.assertEqual(endpoint_adapter.name, "official_endpoint")
        with self.assertRaises(ValueError):
            server.select_live_adapter("unknown_adapter")

    def test_parse_csv_dict_rows_semicolon_and_bom(self):
        csv_text = "\ufeffcode;weight;name\n2330;9.2%;TSMC\n2454;4.1%;MediaTek\n"
        rows = server.parse_csv_dict_rows(csv_text)
        self.assertEqual(len(rows), 2)
        self.assertIn("code", rows[0])
        self.assertEqual(rows[0]["code"], "2330")
        self.assertEqual(rows[1]["name"], "MediaTek")

    def test_parse_official_html_labeled_holdings(self):
        markup = """
        <html><body>
        <section>基金權重-股票</section>
        <div>交易日期:</div><div>2026/06/02</div>
        <div>商品代碼</div><div>2330</div>
        <div>商品名稱</div><div>台積電</div>
        <div>商品數量</div><div>490,182,594</div>
        <div>商品權重</div><div>57.88</div>
        <div>商品代碼</div><div>2454</div>
        <div>商品名稱</div><div>聯發科</div>
        <div>商品數量</div><div>29,517,755</div>
        <div>商品權重</div><div>6.63%</div>
        </body></html>
        """
        parsed = server.parse_official_html_labeled_holdings(
            code="0050",
            markup=markup,
            fetch_url="https://example.test/0050/ratio",
            fallback_date="2026-06-03",
            source_label="Official HTML",
        )
        self.assertEqual(parsed["asOf"], "2026-06-02")
        self.assertEqual(parsed["coverage"], "partial_official_page")
        self.assertAlmostEqual(parsed["holdings"]["2330"], 57.88, places=4)
        self.assertEqual(parsed["holdingDetails"][0]["shares"], "490182594")

    def test_parse_official_html_table_holdings(self):
        markup = """
        <div>資料日期：2026/09/11</div>
        <table>
          <thead><tr><th>股票代號</th><th>股票名稱</th><th>持股權重(%)</th><th>股數</th></tr></thead>
          <tbody>
            <tr><td>2881</td><td>富邦金</td><td>14.97%</td><td>611,770,000</td></tr>
            <tr><td>2330</td><td>台積電</td><td>12.48%</td><td>1,000</td></tr>
          </tbody>
        </table>
        """
        parsed = server.parse_official_html_labeled_holdings(
            code="00919",
            markup=markup,
            fetch_url="https://issuer.example/00919",
            fallback_date="2026-09-12",
            source_label="Issuer official page",
        )
        self.assertEqual(parsed["asOf"], "2026-09-11")
        self.assertEqual(parsed["parsedHoldingCount"], 2)
        self.assertAlmostEqual(parsed["holdings"]["2881"], 14.97, places=4)
        self.assertEqual(parsed["holdingDetails"][0]["shares"], "611770000")

    def test_parse_ctbc_asset_tables_with_plain_weights_and_futures(self):
        markup = """
        <div>基金資產</div>
        <table><tr><td>資料日期:</td><td>2026/09/11</td></tr></table>
        <table id="Table_STOCK">
          <tr><th>股票代碼</th><th>股票名稱</th><th>股數</th><th>權重(%)</th></tr>
          <tr><td>2330</td><td>台積電</td><td>11,130,000.00</td><td>40.58</td></tr>
          <tr><td>ASML NA</td><td>艾司摩爾</td><td>14,700.00</td><td>7.04</td></tr>
          <tr><td>006400 KS Equity</td><td>三星電管</td><td>22,480.00</td><td>9.65</td></tr>
        </table>
        <table id="Table_FUTURE">
          <tr><th>期貨代碼</th><th>期貨名稱</th><th>口數</th><th>權重(%)</th></tr>
          <tr><td>TX</td><td>臺股期貨</td><td>5.00</td><td>0.07</td></tr>
        </table>
        """
        parsed = server.parse_official_html_labeled_holdings(
            code="00891",
            markup=markup,
            fetch_url="https://www.ctbcinvestments.com.tw/example",
            fallback_date="2026-09-12",
            source_label="CTBC official page",
        )
        self.assertEqual(parsed["asOf"], "2026-09-11")
        self.assertEqual(parsed["parsedHoldingCount"], 4)
        self.assertEqual(server.count_official_html_security_rows(markup), 4)
        self.assertAlmostEqual(parsed["holdings"]["ASML NA"], 7.04, places=4)
        self.assertAlmostEqual(parsed["holdings"]["006400 KS EQUITY"], 9.65, places=4)
        self.assertAlmostEqual(parsed["holdings"]["TX"], 0.07, places=4)
        stock = next(row for row in parsed["holdingDetails"] if row["code"] == "2330")
        self.assertEqual(stock["shares"], "11130000.00")

    def test_ctbc_official_adapter_marks_full_only_after_row_verification(self):
        markup = """
        <div>基金資產</div><div>資料日期: 2026/09/11</div>
        <table id="Table_STOCK">
          <tr><th>股票代碼</th><th>股票名稱</th><th>股數</th><th>權重(%)</th></tr>
          <tr><td>2330</td><td>台積電</td><td>100</td><td>60.5</td></tr>
          <tr><td>2454</td><td>聯發科</td><td>50</td><td>39.5</td></tr>
        </table>
        """
        adapter = server.CtbcOfficialHoldingsAdapter(
            "https://www.ctbcinvestments.com.tw/CTWEB/Content/ETF/pcd.aspx?ETF_ID={code}"
        )
        original_get_url = server.get_url_with_retry
        try:
            server.get_url_with_retry = lambda **kwargs: (markup, 1)
            payload = adapter.fetch_one("00891")
        finally:
            server.get_url_with_retry = original_get_url
        self.assertEqual(payload["coverage"], "full")
        self.assertEqual(payload["declaredHoldingCount"], 2)
        self.assertEqual(payload["parsedHoldingCount"], 2)
        self.assertEqual(payload["adapter"], "ctbc_official_holdings")

    def test_parse_fuhwa_security_and_futures_table_labels(self):
        markup = """
        <div>資料日期：2026/09/11</div>
        <table>
          <tr><th>證券代號</th><th>證券名稱</th><th>股數</th><th>金額</th><th>權重 (%)</th></tr>
          <tr><td>000333 CH</td><td>美的集團</td><td>655</td><td>1000</td><td>2.50%</td></tr>
        </table>
        <table>
          <tr><th>期貨代號</th><th>期貨名稱</th><th>口數</th><th>金額</th><th>權重 (%)</th></tr>
          <tr><td>NK202609</td><td>日經225近月期貨</td><td>20</td><td>1000</td><td>3.690%</td></tr>
        </table>
        """
        parsed = server.parse_official_html_labeled_holdings(
            code="00949",
            markup=markup,
            fetch_url="https://www.fhtrust.com.tw/ETF/etf_detail/ETF22",
            fallback_date="2026-09-12",
            source_label="Fuhwa official page",
        )
        self.assertEqual(parsed["asOf"], "2026-09-11")
        self.assertEqual(parsed["parsedHoldingCount"], 2)
        self.assertAlmostEqual(parsed["holdings"]["000333 CH"], 2.5, places=4)
        self.assertAlmostEqual(parsed["holdings"]["NK202609"], 3.69, places=4)

    def test_parse_official_html_flat_responsive_holdings(self):
        markup = """
        <div>股票</div>
        <div>股票代號</div><div>股票名稱</div><div>股票名稱與代號</div>
        <div>持股權重(%)</div><div>持股權重(%)</div><div>股數</div>
        <div>2881</div><div>富邦金</div><div>14.97%</div><div>611,770,000</div>
        <div>2882</div><div>國泰金</div><div>12.48%</div><div>685,780,000</div>
        <div>2881</div><div>富邦金</div><div>14.97%</div>
        <div>債券代號</div>
        <div>12345</div><div>不應跨區解析</div><div>99.99%</div>
        """
        parsed = server.parse_official_html_labeled_holdings(
            code="00919",
            markup=markup,
            fetch_url="https://issuer.example/00919",
            fallback_date="2026-09-12",
            source_label="Issuer official page",
        )
        self.assertEqual(parsed["parsedHoldingCount"], 2)
        self.assertAlmostEqual(parsed["holdings"]["2881"], 14.97, places=4)
        first_row = next(row for row in parsed["holdingDetails"] if row["code"] == "2881")
        self.assertEqual(first_row["shares"], "611770000")

    def test_parse_official_html_flat_foreign_and_bond_identifiers(self):
        markup = """
        <div>股票代號</div><div>股票名稱</div><div>股票名稱與代號</div>
        <div>持股權重(%)</div><div>持股權重(%)</div><div>股數</div>
        <div>002475 CH</div><div>立訊精密</div><div>6.12%</div><div>305,300</div>
        <div>債券代號</div><div>債券名稱</div><div>債券名稱與代號</div>
        <div>面額</div><div>市值</div><div>持股權重(%)</div><div>持股權重(%)</div>
        <div>US15089QAN43</div><div>CE 7.33 07/15/29</div>
        <div>13,780,000</div><div>14,409,878</div><div>1.04%</div>
        """
        parsed = server.parse_official_html_labeled_holdings(
            code="00953B",
            markup=markup,
            fetch_url="https://issuer.example/00953B",
            fallback_date="2026-09-12",
            source_label="Issuer official page",
        )
        self.assertEqual(parsed["parsedHoldingCount"], 2)
        self.assertAlmostEqual(parsed["holdings"]["002475 CH"], 6.12, places=4)
        self.assertAlmostEqual(parsed["holdings"]["US15089QAN43"], 1.04, places=4)
        bond = next(row for row in parsed["holdingDetails"] if row["code"] == "US15089QAN43")
        self.assertEqual(bond["shares"], "13780000")

    def test_parse_official_html_named_top_holdings_table(self):
        markup = """
        <table><tr><th>投資項目</th><th>比例(%)</th></tr><tr><td>電子類股</td><td>80</td></tr></table>
        <table>
          <tr><th>投資類型</th><th>投資標的</th><th>比例(%)</th></tr>
          <tr><td>半導體業</td><td>台積電</td><td>60.56</td></tr>
          <tr><td>海外股票</td><td>Example Corp</td><td>5.25</td></tr>
        </table>
        """
        holdings, details, unresolved = server.extract_official_html_named_table_holdings(
            markup,
            stock_universe={"2330": {"name": "台積電", "sector": "半導體業"}},
        )
        self.assertEqual(len(holdings), 2)
        self.assertAlmostEqual(holdings["2330"], 60.56, places=4)
        self.assertAlmostEqual(holdings["NAME:Example Corp"], 5.25, places=4)
        self.assertEqual(details[0]["name"], "台積電")
        self.assertEqual(unresolved, ["Example Corp"])

    def test_official_pcf_twse_adapter_profile_fallback(self):
        original_endpoint_template = server.OFFICIAL_ENDPOINT_URL_TEMPLATE
        server.OFFICIAL_ENDPOINT_URL_TEMPLATE = ""
        adapter = server.OfficialPcfTwseAdapter(
            pcf_url_template="https://pcf.example/{code}?date={date}",
            twse_url_template="https://twse.example/{code}?date={date}",
            fallback_endpoint_url_template="",
            default_as_of="2026-05-25",
        )
        original_get_url = server.get_url_with_retry
        try:
            def fake_get_url(url: str, timeout=20, retries=0, backoff_ms=0, headers=None):
                if "pcf.example" in url:
                    raise RuntimeError("pcf unavailable")
                return "code,weight,name\n2330,9.2%,TSMC\n2454,4.1%,MediaTek\n", 1

            server.get_url_with_retry = fake_get_url
            payload = adapter.fetch_one("00400A")
            self.assertEqual(payload["adapter"], "official_pcf_twse")
            self.assertEqual(payload["profile"], "twse")
            self.assertEqual(payload["code"], "00400A")
            self.assertAlmostEqual(payload["holdings"]["2330"], 9.2, places=4)
            self.assertTrue(any("pcf failed" in item for item in payload.get("warnings", [])))
        finally:
            server.get_url_with_retry = original_get_url
            server.OFFICIAL_ENDPOINT_URL_TEMPLATE = original_endpoint_template

    def test_official_registry_adapter_exact_code(self):
        original_registry = server.OFFICIAL_SOURCE_REGISTRY_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            server.OFFICIAL_SOURCE_REGISTRY_FILE = base / "official-source-registry.json"
            server.OFFICIAL_SOURCE_REGISTRY_FILE.write_text(
                server.json.dumps(
                    {
                        "sources": [
                            {
                                "name": "test-official-csv",
                                "codes": ["0050"],
                                "format": "csv",
                                "urlTemplate": "https://official.example/{code}.csv",
                                "codeField": "stockCode",
                                "weightField": "weightPct",
                                "nameField": "stockName",
                                "sharesField": "shares",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            original_get_url = server.get_url_with_retry
            try:
                def fake_get_url(url: str, timeout=20, retries=0, backoff_ms=0, headers=None):
                    self.assertEqual(url, "https://official.example/0050.csv")
                    return "stockCode,stockName,weightPct,shares\n2330,TSMC,57.88,100\n", 1

                server.get_url_with_retry = fake_get_url
                payload = server.OfficialRegistryAdapter().fetch_one("0050")
                self.assertEqual(payload["adapter"], "official_registry")
                self.assertEqual(payload["registrySource"], "test-official-csv")
                self.assertAlmostEqual(payload["holdings"]["2330"], 57.88, places=4)
            finally:
                server.get_url_with_retry = original_get_url
                server.OFFICIAL_SOURCE_REGISTRY_FILE = original_registry

    def test_validate_official_source_registry_requires_traceability_and_coverage(self):
        universe = [
            {"code": "0050", "name": "ETF A", "issuer": "Issuer A", "status": "listed"},
            {"code": "0056", "name": "ETF B", "issuer": "Issuer B", "status": "listed"},
        ]
        registry = {
            "schemaVersion": 1,
            "sources": [
                {
                    "name": "issuer-a-official",
                    "enabled": True,
                    "status": "active",
                    "publisher": "Issuer A",
                    "authorityType": "issuer",
                    "verifiedAt": "2026-09-12",
                    "codes": ["0050"],
                    "format": "csv",
                    "expectedCoverage": "full",
                    "urlTemplate": "https://issuer.example/pcf/{code}.csv",
                }
            ],
        }
        result = server.validate_official_source_registry(registry, universe)
        self.assertFalse(result["ok"])
        self.assertEqual(result["coverage"]["coveredListedCount"], 1)
        self.assertEqual(result["coverage"]["missingListedCount"], 1)
        self.assertTrue(any("missing 1 of 2" in issue for issue in result["issues"]))

    def test_validate_official_source_registry_accepts_complete_registry(self):
        universe = [
            {"code": "0050", "name": "ETF A", "issuer": "Issuer A", "status": "listed"},
            {"code": "0056", "name": "ETF B", "issuer": "Issuer A", "status": "listed"},
        ]
        registry = {
            "schemaVersion": 1,
            "sources": [
                {
                    "name": "issuer-a-official",
                    "enabled": True,
                    "status": "active",
                    "publisher": "Issuer A",
                    "authorityType": "issuer",
                    "verifiedAt": "2026-09-12",
                    "issuerContains": ["Issuer A"],
                    "format": "json",
                    "expectedCoverage": "full",
                    "urlTemplate": "https://issuer.example/api/{code}?date={date}",
                }
            ],
        }
        result = server.validate_official_source_registry(registry, universe)
        self.assertTrue(result["ok"])
        self.assertEqual(result["enabledSourceCount"], 1)
        self.assertEqual(result["coverage"]["coveredListedCount"], 2)

    def test_official_registry_supports_per_code_urls(self):
        source = {
            "enabled": True,
            "urlsByCode": {
                "0050": "https://issuer.example/funds/123/holdings",
                "0056": "https://issuer.example/funds/456/holdings",
            },
            "format": "html",
        }
        self.assertTrue(server.official_registry_source_matches(source, "0050", None))
        self.assertFalse(server.official_registry_source_matches(source, "006208", None))
        adapter = server.OfficialRegistryAdapter().build_source_adapter(source, code="0056")
        self.assertEqual(adapter.url_template, "https://issuer.example/funds/456/holdings")

    def test_cathay_official_pcf_adapter_combines_asset_types_without_claiming_weights(self):
        adapter = server.CathayOfficialPcfAdapter(
            api_base_url="https://cwapi.example/api/BuySale",
            fund_code="CN",
            headers={"Referer": "https://issuer.example/product"},
        )
        responses = {
            "GetBuySale": {
                "result": {
                    "date": "2026/09/14",
                    "basketUnit": "500,000",
                    "basketNav": "17,165,000",
                    "currency": "新台幣",
                },
                "returnCode": "2000",
                "success": True,
            },
            "GetStocksList": {
                "result": [{"prod": "2330", "prodName": "台積電", "basketShares": "10,000"}],
                "returnCode": "2000",
                "success": True,
            },
            "GetBondsList": {
                "result": [
                    {
                        "figiCode": "BBG000TEST",
                        "prodName": "US TREASURY",
                        "basketSharesF": "1,362",
                        "marketValB": "1,396",
                    }
                ],
                "returnCode": "2000",
                "success": True,
            },
            "GetFuturesList": {
                "result": [{"prod": "YM", "prodName": "MINI DJ", "basketSharesF": "4.18", "ftDate": "2026/09"}],
                "returnCode": "2000",
                "success": True,
            },
        }
        requested_urls = []
        original_get_url = server.get_url_with_retry
        try:
            def fake_get_url(url: str, timeout=20, retries=0, backoff_ms=0, headers=None):
                requested_urls.append(url)
                endpoint = next(name for name in responses if f"/{name}?" in url)
                return server.json.dumps(responses[endpoint], ensure_ascii=False), 1

            server.get_url_with_retry = fake_get_url
            payload = adapter.fetch_one("00878")
        finally:
            server.get_url_with_retry = original_get_url

        self.assertEqual(payload["asOf"], "2026-09-14")
        self.assertEqual(payload["declaredHoldingCount"], 3)
        self.assertEqual(payload["parsedHoldingCount"], 3)
        self.assertEqual(payload["coverage"], "partial_official_pcf_missing_weights")
        self.assertEqual(payload["holdings"]["2330"], 0.0)
        self.assertEqual(payload["holdings"]["BBG000TEST"], 0.0)
        self.assertEqual(payload["holdings"]["FUTURE:YM:2026/09"], 0.0)
        self.assertEqual(payload["holdingDetails"][1]["marketValue"], "1,396")
        self.assertTrue(any("SearchDate=2026%2F09%2F14" in url for url in requested_urls))
        self.assertTrue(any("not constituent weights" in warning for warning in payload["warnings"]))

    def test_official_registry_supports_cathay_fund_code_mapping(self):
        source = {
            "enabled": True,
            "format": "cathay_pcf",
            "url": "https://cwapi.example/api/BuySale",
            "fundCodesByCode": {"00878": "CN", "00636K": "66"},
        }
        self.assertTrue(server.official_registry_source_matches(source, "00636K", None))
        self.assertFalse(server.official_registry_source_matches(source, "0050", None))
        adapter = server.OfficialRegistryAdapter().build_source_adapter(source, code="00878")
        self.assertIsInstance(adapter, server.CathayOfficialPcfAdapter)
        self.assertEqual(adapter.fund_code, "CN")

    def test_validate_official_source_registry_accepts_cathay_mapping(self):
        universe = [{"code": "00878", "name": "ETF A", "issuer": "Cathay", "status": "listed"}]
        registry = {
            "schemaVersion": 1,
            "sources": [
                {
                    "name": "cathay-official",
                    "enabled": True,
                    "status": "active",
                    "publisher": "Cathay",
                    "authorityType": "issuer",
                    "verifiedAt": "2026-09-12",
                    "format": "cathay_pcf",
                    "expectedCoverage": "partial",
                    "url": "https://cwapi.example/api/BuySale",
                    "fundCodesByCode": {"00878": "CN"},
                }
            ],
        }
        result = server.validate_official_source_registry(registry, universe)
        self.assertTrue(result["ok"])
        self.assertEqual(result["coverage"]["coveredListedCount"], 1)

    def test_nomura_official_pcf_adapter_combines_all_asset_types_with_weights(self):
        self.assertEqual(server.parse_weight_value(0), 0.0)
        adapter = server.NomuraOfficialPcfAdapter(
            api_base_url="https://issuer.example/API/ETFAPI/api",
            headers={"Referer": "https://issuer.example/ETFWEB/pcf"},
        )
        responses = {
            "Fund/GetFundTradeInfoDate": {
                "StatusCode": 0,
                "Entries": {"LatestDate": "2026/09/14", "AllDate": ["2026/09/14"]},
            },
            "Fund/GetFundTradeInfo": {
                "StatusCode": 0,
                "Entries": {
                    "CFundId": "00935",
                    "CPcfdate": "2026-09-14T00:00:00",
                    "Stocks": [
                        {
                            "CStockCode": "2330",
                            "CStockName": "台積電",
                            "CQuantity": 5086000,
                            "CWeightsPct": 24.38,
                        }
                    ],
                    "Bonds": [
                        {
                            "CBondCode": "US91282TEST",
                            "CBondName": "US TREASURY",
                            "CBalParValue": 5920000,
                            "CMarketValue": 5559798.73,
                            "CHoldRatio": 11.25,
                        }
                    ],
                    "Etfs": [
                        {
                            "CStockCode": "1306 JP",
                            "CStockName": "NEXT FUNDS TOPIX",
                            "CQuantity": 13497620,
                            "CWeightsPct": 2.5,
                        }
                    ],
                    "Futures": [
                        {
                            "CFuturesCode": "TX",
                            "CFuturesName": "TAIEX FUTURE",
                            "CQuantity": 144,
                            "CWeightsPct": 2.65,
                            "CContractYm": "2026/09",
                        }
                    ],
                    "Options": [],
                },
            },
        }
        calls = []
        original_post_json = server.post_json_with_retry
        try:
            def fake_post_json(url: str, payload: dict, timeout=20, retries=0, backoff_ms=0, headers=None):
                calls.append((url, payload))
                endpoint = next(name for name in responses if url.endswith(name))
                return responses[endpoint], 1

            server.post_json_with_retry = fake_post_json
            payload = adapter.fetch_one("00935")
        finally:
            server.post_json_with_retry = original_post_json

        self.assertEqual(payload["asOf"], "2026-09-14")
        self.assertEqual(payload["declaredHoldingCount"], 4)
        self.assertEqual(payload["parsedHoldingCount"], 4)
        self.assertEqual(payload["coverage"], "full")
        self.assertEqual(payload["holdings"]["2330"], 24.38)
        self.assertEqual(payload["holdings"]["US91282TEST"], 11.25)
        self.assertEqual(payload["holdings"]["1306 JP"], 2.5)
        self.assertEqual(payload["holdings"]["FUTURE:TX:2026/09"], 2.65)
        self.assertEqual(payload["holdingDetails"][1]["marketValue"], "5559798.73")
        self.assertEqual(calls[1][1]["Date"], "2026/09/14")

    def test_official_registry_builds_nomura_pcf_adapter(self):
        source = {
            "enabled": True,
            "format": "nomura_pcf",
            "url": "https://www.nomurafunds.com.tw/API/ETFAPI/api",
            "codes": ["00935"],
        }
        adapter = server.OfficialRegistryAdapter().build_source_adapter(source, code="00935")
        self.assertIsInstance(adapter, server.NomuraOfficialPcfAdapter)

    def test_validate_official_source_registry_accepts_nomura_pcf(self):
        universe = [{"code": "00935", "name": "ETF A", "issuer": "Nomura", "status": "listed"}]
        registry = {
            "schemaVersion": 1,
            "sources": [
                {
                    "name": "nomura-official",
                    "enabled": True,
                    "status": "active",
                    "publisher": "Nomura",
                    "authorityType": "issuer",
                    "verifiedAt": "2026-09-12",
                    "format": "nomura_pcf",
                    "expectedCoverage": "full",
                    "url": "https://www.nomurafunds.com.tw/API/ETFAPI/api",
                    "codes": ["00935"],
                }
            ],
        }
        result = server.validate_official_source_registry(registry, universe)
        self.assertTrue(result["ok"])
        self.assertEqual(result["coverage"]["productionReadyListedCount"], 1)

    def test_append_and_read_refresh_alerts(self):
        original_file = server.ALERTS_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            server.ALERTS_FILE = Path(tmp_dir) / "alerts.jsonl"
            try:
                server.append_refresh_alert("warning", "partial fetch", {"code": "00400A"})
                server.append_refresh_alert("error", "all failed", {"requestedCodes": ["00400A"]})
                rows = server.read_recent_refresh_alerts(limit=5)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["level"], "error")
                self.assertEqual(rows[1]["level"], "warning")
            finally:
                server.ALERTS_FILE = original_file

    def test_append_and_read_access_logs(self):
        original_enabled = server.ACCESS_LOG_ENABLED
        original_file = server.ACCESS_LOG_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            server.ACCESS_LOG_ENABLED = True
            server.ACCESS_LOG_FILE = Path(tmp_dir) / "access-log.jsonl"
            try:
                server.append_access_log({"time": "2026-05-25T00:00:00+00:00", "status": 200, "path": "/api/health"})
                server.append_access_log({"time": "2026-05-25T00:01:00+00:00", "status": 404, "path": "/missing"})
                rows = server.read_recent_access_logs(limit=10)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["status"], 404)
                self.assertEqual(rows[1]["status"], 200)
            finally:
                server.ACCESS_LOG_ENABLED = original_enabled
                server.ACCESS_LOG_FILE = original_file

    def test_append_jsonl_record_rotates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "access.jsonl"
            server.append_jsonl_record(
                path=log_file,
                payload={"index": 1, "message": "x" * 120},
                rotate_max_bytes=64,
                backup_count=3,
            )
            server.append_jsonl_record(
                path=log_file,
                payload={"index": 2, "message": "y"},
                rotate_max_bytes=64,
                backup_count=3,
            )
            self.assertTrue(log_file.exists())
            self.assertTrue((Path(tmp_dir) / "access.jsonl.1").exists())
            latest_lines = log_file.read_text(encoding="utf-8").splitlines()
            self.assertTrue(latest_lines)
            latest = server.json.loads(latest_lines[-1])
            self.assertEqual(latest["index"], 2)

    def test_append_access_log_respects_enabled_flag(self):
        original_enabled = server.ACCESS_LOG_ENABLED
        original_file = server.ACCESS_LOG_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            server.ACCESS_LOG_ENABLED = False
            server.ACCESS_LOG_FILE = Path(tmp_dir) / "access.jsonl"
            try:
                server.append_access_log({"time": "2026-05-25T00:00:00+00:00", "status": 200})
                self.assertFalse(server.ACCESS_LOG_FILE.exists())
            finally:
                server.ACCESS_LOG_ENABLED = original_enabled
                server.ACCESS_LOG_FILE = original_file

    def test_upsert_history_from_payload_records_adapter(self):
        original_history = server.HISTORY_FILE
        with tempfile.TemporaryDirectory() as tmp_dir:
            server.HISTORY_FILE = Path(tmp_dir) / "history.json"
            payload = {
                "asOf": "2026-05-25",
                "source": "Official PCF/TWSE endpoint",
                "adapter": "official_endpoint",
                "etfs": [
                    {
                        "code": "00400A",
                        "asOf": "2026-05-25",
                        "source": "Official PCF/TWSE endpoint",
                        "coverage": "full",
                        "declaredHoldingCount": 2,
                        "parsedHoldingCount": 2,
                        "holdings": {"2330": 9.2, "2454": 4.1},
                        "holdingDetails": [],
                    }
                ],
            }
            try:
                server.upsert_history_from_payload(payload)
                store = server.load_history_store()
                entry = store["history"]["00400A"]["2026-05-25"]
                self.assertEqual(entry["adapter"], "official_endpoint")
            finally:
                server.HISTORY_FILE = original_history

    def test_history_store_quality_overview(self):
        store = {
            "history": {
                "00400A": {
                    "2026-05-24": {
                        "source": "seed",
                        "coverage": "seed",
                        "declaredHoldingCount": 1,
                        "parsedHoldingCount": 1,
                        "holdings": {"2330": 10.0},
                    },
                    "2026-05-25": {
                        "source": "Official PCF/TWSE endpoint",
                        "adapter": "official_endpoint",
                        "coverage": "full",
                        "declaredHoldingCount": 1,
                        "parsedHoldingCount": 1,
                        "holdings": {"2330": 10.1},
                    },
                }
            }
        }
        overview = server.history_store_quality_overview(store)
        self.assertEqual(overview["summary"]["etfCount"], 1)
        self.assertEqual(overview["summary"]["totalSnapshots"], 2)
        self.assertEqual(overview["summary"]["realSnapshotCount"], 1)

    def test_apply_history_retention_policy_by_age(self):
        original_days = server.HISTORY_RETENTION_DAYS
        original_max = server.HISTORY_MAX_SNAPSHOTS_PER_CODE
        original_drop_seed = server.HISTORY_DROP_SEED_WHEN_REAL
        try:
            server.HISTORY_RETENTION_DAYS = 5
            server.HISTORY_MAX_SNAPSHOTS_PER_CODE = 0
            server.HISTORY_DROP_SEED_WHEN_REAL = False
            today = server.date.today()
            old_date = (today - server.timedelta(days=10)).isoformat()
            recent_date = (today - server.timedelta(days=2)).isoformat()
            store = {
                "history": {
                    "00400A": {
                        old_date: {
                            "source": "Official PCF/TWSE endpoint",
                            "adapter": "official_endpoint",
                            "coverage": "full",
                            "declaredHoldingCount": 1,
                            "parsedHoldingCount": 1,
                            "holdings": {"2330": 10.0},
                        },
                        recent_date: {
                            "source": "Official PCF/TWSE endpoint",
                            "adapter": "official_endpoint",
                            "coverage": "full",
                            "declaredHoldingCount": 1,
                            "parsedHoldingCount": 1,
                            "holdings": {"2330": 10.2},
                        },
                    }
                }
            }
            summary = server.apply_history_retention_policy(store, today=today)
            self.assertEqual(summary["removedSnapshotCount"], 1)
            self.assertEqual(summary["removedByAge"], 1)
            self.assertNotIn(old_date, store["history"]["00400A"])
            self.assertIn(recent_date, store["history"]["00400A"])
        finally:
            server.HISTORY_RETENTION_DAYS = original_days
            server.HISTORY_MAX_SNAPSHOTS_PER_CODE = original_max
            server.HISTORY_DROP_SEED_WHEN_REAL = original_drop_seed

    def test_apply_history_retention_policy_drop_seed_when_real(self):
        original_days = server.HISTORY_RETENTION_DAYS
        original_max = server.HISTORY_MAX_SNAPSHOTS_PER_CODE
        original_drop_seed = server.HISTORY_DROP_SEED_WHEN_REAL
        try:
            server.HISTORY_RETENTION_DAYS = 0
            server.HISTORY_MAX_SNAPSHOTS_PER_CODE = 0
            server.HISTORY_DROP_SEED_WHEN_REAL = True
            store = {
                "history": {
                    "00400A": {
                        "2026-05-20": {
                            "source": "seed",
                            "coverage": "seed",
                            "declaredHoldingCount": 1,
                            "parsedHoldingCount": 1,
                            "holdings": {"2330": 9.0},
                        },
                        "2026-05-21": {
                            "source": "Official PCF/TWSE endpoint",
                            "adapter": "official_endpoint",
                            "coverage": "full",
                            "declaredHoldingCount": 1,
                            "parsedHoldingCount": 1,
                            "holdings": {"2330": 9.3},
                        },
                    }
                }
            }
            summary = server.apply_history_retention_policy(store)
            self.assertEqual(summary["removedSeedAfterReal"], 1)
            self.assertNotIn("2026-05-20", store["history"]["00400A"])
            self.assertIn("2026-05-21", store["history"]["00400A"])
        finally:
            server.HISTORY_RETENTION_DAYS = original_days
            server.HISTORY_MAX_SNAPSHOTS_PER_CODE = original_max
            server.HISTORY_DROP_SEED_WHEN_REAL = original_drop_seed

    def test_apply_history_retention_policy_max_snapshots(self):
        original_days = server.HISTORY_RETENTION_DAYS
        original_max = server.HISTORY_MAX_SNAPSHOTS_PER_CODE
        original_drop_seed = server.HISTORY_DROP_SEED_WHEN_REAL
        try:
            server.HISTORY_RETENTION_DAYS = 0
            server.HISTORY_MAX_SNAPSHOTS_PER_CODE = 2
            server.HISTORY_DROP_SEED_WHEN_REAL = False
            store = {
                "history": {
                    "00400A": {
                        "2026-05-20": {
                            "source": "Official PCF/TWSE endpoint",
                            "adapter": "official_endpoint",
                            "coverage": "full",
                            "declaredHoldingCount": 1,
                            "parsedHoldingCount": 1,
                            "holdings": {"2330": 9.0},
                        },
                        "2026-05-21": {
                            "source": "Official PCF/TWSE endpoint",
                            "adapter": "official_endpoint",
                            "coverage": "full",
                            "declaredHoldingCount": 1,
                            "parsedHoldingCount": 1,
                            "holdings": {"2330": 9.3},
                        },
                        "2026-05-22": {
                            "source": "Official PCF/TWSE endpoint",
                            "adapter": "official_endpoint",
                            "coverage": "full",
                            "declaredHoldingCount": 1,
                            "parsedHoldingCount": 1,
                            "holdings": {"2330": 9.8},
                        },
                    }
                }
            }
            summary = server.apply_history_retention_policy(store)
            self.assertEqual(summary["removedByMaxPerCode"], 1)
            self.assertEqual(summary["removedSnapshotCount"], 1)
            self.assertNotIn("2026-05-20", store["history"]["00400A"])
            self.assertEqual(len(store["history"]["00400A"]), 2)
        finally:
            server.HISTORY_RETENTION_DAYS = original_days
            server.HISTORY_MAX_SNAPSHOTS_PER_CODE = original_max
            server.HISTORY_DROP_SEED_WHEN_REAL = original_drop_seed

    def test_run_prune_history_once(self):
        original_history = server.HISTORY_FILE
        original_days = server.HISTORY_RETENTION_DAYS
        original_max = server.HISTORY_MAX_SNAPSHOTS_PER_CODE
        original_drop_seed = server.HISTORY_DROP_SEED_WHEN_REAL
        capture = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            server.HISTORY_FILE = Path(tmp_dir) / "holdings-history.json"
            server.HISTORY_FILE.write_text(
                """{
  "history": {
    "00400A": {
      "2026-05-20": {
        "source": "Official PCF/TWSE endpoint",
        "adapter": "official_endpoint",
        "coverage": "full",
        "declaredHoldingCount": 1,
        "parsedHoldingCount": 1,
        "holdings": {"2330": 9.0}
      },
      "2026-05-21": {
        "source": "Official PCF/TWSE endpoint",
        "adapter": "official_endpoint",
        "coverage": "full",
        "declaredHoldingCount": 1,
        "parsedHoldingCount": 1,
        "holdings": {"2330": 9.3}
      },
      "2026-05-22": {
        "source": "Official PCF/TWSE endpoint",
        "adapter": "official_endpoint",
        "coverage": "full",
        "declaredHoldingCount": 1,
        "parsedHoldingCount": 1,
        "holdings": {"2330": 9.8}
      }
    }
  }
}
""",
                encoding="utf-8",
            )
            try:
                server.HISTORY_RETENTION_DAYS = 0
                server.HISTORY_MAX_SNAPSHOTS_PER_CODE = 2
                server.HISTORY_DROP_SEED_WHEN_REAL = False
                with redirect_stdout(capture):
                    self.assertEqual(server.run_prune_history_once(), 0)
                store = server.load_history_store()
                self.assertEqual(len(store["history"]["00400A"]), 2)
                self.assertIn("historyRetention", store)
            finally:
                server.HISTORY_FILE = original_history
                server.HISTORY_RETENTION_DAYS = original_days
                server.HISTORY_MAX_SNAPSHOTS_PER_CODE = original_max
                server.HISTORY_DROP_SEED_WHEN_REAL = original_drop_seed

    def test_latest_payload_summary(self):
        summary = server.latest_payload_summary(
            {
                "asOf": "2026-05-24",
                "savedAt": "2026-05-24T00:00:00+00:00",
                "source": "ETFInfo public page",
                "adapter": "etfinfo_public_page",
                "errors": [{"code": "00400A"}],
                "etfs": [
                    {"code": "00400A", "coverage": "full"},
                    {"code": "00403A", "coverage": "partial_public_page"},
                ],
            }
        )
        self.assertEqual(summary["etfCount"], 2)
        self.assertEqual(summary["errorCount"], 1)
        self.assertEqual(summary["partialCount"], 1)

    def test_official_snapshot_file_adapter(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir)
            (snapshot_dir / "00400A.json").write_text(
                """{
  "code": "00400A",
  "asOf": "2026-05-24",
  "coverage": "full",
  "holdings": {
    "2330": 9.1,
    "2454": 4.2
  }
}
""",
                encoding="utf-8",
            )
            adapter = server.OfficialSnapshotFileAdapter(snapshot_dir=snapshot_dir)
            payload = adapter.fetch_one("00400A")
            self.assertEqual(payload["code"], "00400A")
            self.assertEqual(payload["adapter"], "official_snapshot_file")
            self.assertEqual(payload["coverage"], "full")
            self.assertAlmostEqual(payload["holdings"]["2330"], 9.1, places=4)

    def test_official_snapshot_file_adapter_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir)
            (snapshot_dir / "00400A.json").write_text(
                """{
  "code": "00400A",
  "asOf": "2026-05-24",
  "holdings": {
    "2330": 9.1
  }
}
""",
                encoding="utf-8-sig",
            )
            adapter = server.OfficialSnapshotFileAdapter(snapshot_dir=snapshot_dir)
            payload = adapter.fetch_one("00400A")
            self.assertEqual(payload["code"], "00400A")
            self.assertAlmostEqual(payload["holdings"]["2330"], 9.1, places=4)

    def test_validate_live_payload_rejects_invalid_as_of(self):
        invalid_payload = {
            "asOf": "2026/05/24",
            "etfs": [
                {
                    "code": "00400A",
                    "asOf": "2026-05-24",
                    "holdings": {"2330": 10.0},
                }
            ],
            "errors": [],
        }
        with self.assertRaises(ValueError):
            server.validate_live_payload(invalid_payload)

    def test_resolve_json_path(self):
        payload = {"meta": {"asOf": "2026-05-25"}, "data": {"rows": [{"code": "2330"}]}}
        self.assertEqual(server.resolve_json_path(payload, "meta.asOf"), "2026-05-25")
        rows = server.resolve_json_path(payload, "data.rows")
        self.assertEqual(len(rows), 1)

    def test_official_endpoint_adapter_parse_json_payload(self):
        adapter = server.OfficialEndpointAdapter(
            url_template="https://example.test/{code}?date={date}",
            data_format="json",
            holdings_path="data.rows",
            as_of_path="meta.asOf",
            declared_count_path="meta.declared",
            code_field="stockCode",
            weight_field="weightPct",
            name_field="stockName",
            shares_field="shares",
            price_field="price",
            default_as_of="2026-05-25",
        )
        payload = {
            "meta": {"asOf": "2026-05-25", "declared": 2},
            "data": {
                "rows": [
                    {"stockCode": "2330", "stockName": "TSMC", "weightPct": "9.20", "shares": "1000", "price": "1000"},
                    {"stockCode": "2454", "stockName": "MediaTek", "weightPct": "4.10", "shares": "500", "price": "500"},
                ]
            },
        }
        parsed = adapter.parse_json_payload("00400A", payload, "https://example.test")
        self.assertEqual(parsed["asOf"], "2026-05-25")
        self.assertEqual(parsed["coverage"], "full")
        self.assertAlmostEqual(parsed["holdings"]["2330"], 9.2, places=4)
        self.assertEqual(parsed["declaredHoldingCount"], 2)

    def test_official_endpoint_adapter_parse_csv_payload(self):
        adapter = server.OfficialEndpointAdapter(
            url_template="https://example.test/{code}?date={date}",
            data_format="csv",
            code_field="stockCode",
            weight_field="weightPct",
            name_field="stockName",
            as_of_path="asOf",
            default_as_of="2026-05-25",
        )
        csv_text = "asOf,stockCode,stockName,weightPct\n2026-05-25,2330,TSMC,9.2%\n2026-05-25,2454,MediaTek,4.1%\n"
        parsed = adapter.parse_csv_payload("00400A", csv_text, "https://example.test")
        self.assertEqual(parsed["coverage"], "full")
        self.assertEqual(parsed["asOf"], "2026-05-25")
        self.assertAlmostEqual(parsed["holdings"]["2454"], 4.1, places=4)

    def test_live_fetch_config_status_reports_endpoint_issues(self):
        original_adapter = server.LIVE_FETCH_ADAPTER
        original_template = server.OFFICIAL_ENDPOINT_URL_TEMPLATE
        original_format = server.OFFICIAL_ENDPOINT_FORMAT
        original_holdings_path = server.OFFICIAL_ENDPOINT_HOLDINGS_PATH
        try:
            server.LIVE_FETCH_ADAPTER = "official_endpoint"
            server.OFFICIAL_ENDPOINT_URL_TEMPLATE = ""
            server.OFFICIAL_ENDPOINT_FORMAT = "xml"
            server.OFFICIAL_ENDPOINT_HOLDINGS_PATH = ""
            status = server.live_fetch_config_status()
            self.assertFalse(status["ok"])
            self.assertTrue(any("URL_TEMPLATE" in item for item in status["issues"]))
            self.assertTrue(any("must be json, csv, or html" in item for item in status["issues"]))
        finally:
            server.LIVE_FETCH_ADAPTER = original_adapter
            server.OFFICIAL_ENDPOINT_URL_TEMPLATE = original_template
            server.OFFICIAL_ENDPOINT_FORMAT = original_format
            server.OFFICIAL_ENDPOINT_HOLDINGS_PATH = original_holdings_path

    def test_live_fetch_config_status_unknown_adapter(self):
        status = server.live_fetch_config_status("not_real")
        self.assertFalse(status["ok"])
        self.assertTrue(any("Unsupported ETF_HOLDINGS_ADAPTER" in item for item in status["issues"]))

    def test_live_fetch_config_status_strict_mode_requires_official_adapter(self):
        original_strict = server.LIVE_REQUIRE_FULL_HOLDINGS
        try:
            server.LIVE_REQUIRE_FULL_HOLDINGS = True
            status = server.live_fetch_config_status("etfinfo_public_page")
            self.assertFalse(status["ok"])
            self.assertTrue(any("requires an official adapter" in item for item in status["issues"]))
        finally:
            server.LIVE_REQUIRE_FULL_HOLDINGS = original_strict

    def test_live_fetch_config_status_official_pcf_twse_requires_source(self):
        original_pcf = server.OFFICIAL_PCF_URL_TEMPLATE
        original_twse = server.OFFICIAL_TWSE_URL_TEMPLATE
        original_endpoint = server.OFFICIAL_ENDPOINT_URL_TEMPLATE
        try:
            server.OFFICIAL_PCF_URL_TEMPLATE = ""
            server.OFFICIAL_TWSE_URL_TEMPLATE = ""
            server.OFFICIAL_ENDPOINT_URL_TEMPLATE = ""
            status = server.live_fetch_config_status("official_pcf_twse")
            self.assertFalse(status["ok"])
            self.assertTrue(any("requires ETF_OFFICIAL_PCF_URL_TEMPLATE" in item for item in status["issues"]))
        finally:
            server.OFFICIAL_PCF_URL_TEMPLATE = original_pcf
            server.OFFICIAL_TWSE_URL_TEMPLATE = original_twse
            server.OFFICIAL_ENDPOINT_URL_TEMPLATE = original_endpoint

    def test_resolve_probe_code(self):
        available = {"00400A", "00403A", "009816"}
        self.assertEqual(server.resolve_probe_code("00403A", available), "00403A")
        self.assertIn(server.resolve_probe_code("", available), available)
        with self.assertRaises(ValueError):
            server.resolve_probe_code("0050", available)
        with self.assertRaises(ValueError):
            server.resolve_probe_code("", set())

    def test_probe_live_fetch_once(self):
        class FakeAdapter:
            name = "fake_adapter"
            source_label = "Fake Adapter"

            def fetch_one(self, code: str) -> dict:
                self.last_code = code
                return {
                    "code": code,
                    "asOf": "2026-05-25",
                    "coverage": "full",
                    "holdings": {"2330": 9.2, "2454": "4.1"},
                    "declaredHoldingCount": "2",
                    "parsedHoldingCount": 2,
                    "fetchUrl": "https://example.test/etf",
                    "warnings": [],
                }

        fake_adapter = FakeAdapter()
        original_select = server.select_live_adapter
        captured_adapter_name = {"value": None}
        try:
            def fake_select(adapter_name=None):
                captured_adapter_name["value"] = adapter_name
                return fake_adapter

            server.select_live_adapter = fake_select
            result = server.probe_live_fetch_once("00400A", "official_snapshot_file")
            self.assertTrue(result["ok"])
            self.assertEqual(result["adapter"], "fake_adapter")
            self.assertEqual(result["code"], "00400A")
            self.assertEqual(result["declaredHoldingCount"], 2)
            self.assertEqual(result["parsedHoldingCount"], 2)
            self.assertGreaterEqual(result["durationMs"], 0)
            self.assertEqual(result["sampleHoldings"][0]["code"], "2330")
            self.assertEqual(fake_adapter.last_code, "00400A")
            self.assertEqual(captured_adapter_name["value"], "official_snapshot_file")
        finally:
            server.select_live_adapter = original_select

    def test_run_check_config_once_exit_code(self):
        original_adapter = server.LIVE_FETCH_ADAPTER
        original_alerts = server.ALERTS_FILE
        capture = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            server.ALERTS_FILE = Path(tmp_dir) / "alerts.jsonl"
            try:
                server.LIVE_FETCH_ADAPTER = "not_real"
                with redirect_stdout(capture):
                    self.assertEqual(server.run_check_config_once(), 1)
                rows = server.read_recent_refresh_alerts(limit=5)
                self.assertTrue(any(row.get("message") == "Live fetch config check failed." for row in rows))
                server.LIVE_FETCH_ADAPTER = "etfinfo_public_page"
                with redirect_stdout(capture):
                    self.assertEqual(server.run_check_config_once(), 0)
            finally:
                server.LIVE_FETCH_ADAPTER = original_adapter
                server.ALERTS_FILE = original_alerts

    def test_run_check_history_quality_exit_code(self):
        original_universe = server.ETF_UNIVERSE_FILE
        original_history = server.HISTORY_FILE
        original_stock = server.STOCK_UNIVERSE_FILE
        original_alerts = server.ALERTS_FILE
        capture = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            server.ETF_UNIVERSE_FILE = base / "etf-universe.json"
            server.HISTORY_FILE = base / "holdings-history.json"
            server.STOCK_UNIVERSE_FILE = base / "stock-universe.json"
            server.ALERTS_FILE = base / "alerts.jsonl"
            server.ETF_UNIVERSE_FILE.write_text(
                '[{"code":"00400A","name":"A","status":"listed","listedDate":"2020-01-01","source":"API"}]',
                encoding="utf-8",
            )
            server.STOCK_UNIVERSE_FILE.write_text("{}", encoding="utf-8")
            server.HISTORY_FILE.write_text(
                """{
  "history": {
    "00400A": {
      "2026-05-24": {
        "source": "Official PCF/TWSE endpoint",
        "adapter": "official_endpoint",
        "coverage": "full",
        "declaredHoldingCount": 1,
        "parsedHoldingCount": 1,
        "holdings": {"2330": 10.0},
        "holdingDetails": []
      },
      "2026-05-25": {
        "source": "Official PCF/TWSE endpoint",
        "adapter": "official_endpoint",
        "coverage": "full",
        "declaredHoldingCount": 1,
        "parsedHoldingCount": 1,
        "holdings": {"2330": 10.1},
        "holdingDetails": []
      }
    }
  }
}
""",
                encoding="utf-8",
            )
            try:
                with redirect_stdout(capture):
                    self.assertEqual(
                        server.run_check_history_quality("00400A", 22, "real_only", 2),
                        0,
                    )
                with redirect_stdout(capture):
                    self.assertEqual(
                        server.run_check_history_quality("00400A", 22, "real_only", 3),
                        1,
                    )
                rows = server.read_recent_refresh_alerts(limit=10)
                self.assertTrue(any(row.get("message") == "History quality gate failed." for row in rows))
            finally:
                server.ETF_UNIVERSE_FILE = original_universe
                server.HISTORY_FILE = original_history
                server.STOCK_UNIVERSE_FILE = original_stock
                server.ALERTS_FILE = original_alerts

    def test_build_production_data_readiness_ok(self):
        original_universe = server.ETF_UNIVERSE_FILE
        original_history = server.HISTORY_FILE
        original_profile = server.ETF_PROFILE_FILE
        original_stock = server.STOCK_UNIVERSE_FILE
        original_registry = server.OFFICIAL_SOURCE_REGISTRY_FILE
        original_adapter = server.LIVE_FETCH_ADAPTER
        original_endpoint = server.OFFICIAL_ENDPOINT_URL_TEMPLATE
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            server.ETF_UNIVERSE_FILE = base / "etf-universe.json"
            server.HISTORY_FILE = base / "holdings-history.json"
            server.ETF_PROFILE_FILE = base / "etf-profiles.json"
            server.STOCK_UNIVERSE_FILE = base / "stock-universe.json"
            server.OFFICIAL_SOURCE_REGISTRY_FILE = base / "official-source-registry.json"
            metric_values = {field: 1 for field in server.PROFILE_METRIC_FIELDS}
            try:
                server.LIVE_FETCH_ADAPTER = "official_endpoint"
                server.OFFICIAL_ENDPOINT_URL_TEMPLATE = "https://official.example/{code}"
                server.ETF_UNIVERSE_FILE.write_text(
                    '[{"code":"0050","name":"ETF50","status":"listed"}]',
                    encoding="utf-8",
                )
                server.ETF_PROFILE_FILE.write_text(
                    server.json.dumps({"rows": [{"code": "0050", **metric_values}]}),
                    encoding="utf-8",
                )
                server.STOCK_UNIVERSE_FILE.write_text("{}", encoding="utf-8")
                server.OFFICIAL_SOURCE_REGISTRY_FILE.write_text(
                    server.json.dumps(
                        {
                            "schemaVersion": 1,
                            "sources": [
                                {
                                    "name": "official-test-json",
                                    "enabled": True,
                                    "status": "active",
                                    "publisher": "Test issuer",
                                    "authorityType": "issuer",
                                    "verifiedAt": "2026-05-02",
                                    "format": "json",
                                    "expectedCoverage": "full",
                                    "codes": ["0050"],
                                    "urlTemplate": "https://official.example/{code}",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                server.HISTORY_FILE.write_text(
                    """{
  "history": {
    "0050": {
      "2026-05-01": {
        "source": "Official PCF/TWSE endpoint",
        "adapter": "official_endpoint",
        "coverage": "full",
        "declaredHoldingCount": 1,
        "parsedHoldingCount": 1,
        "holdings": {"2330": 10.0}
      },
      "2026-05-02": {
        "source": "Official PCF/TWSE endpoint",
        "adapter": "official_endpoint",
        "coverage": "full",
        "declaredHoldingCount": 1,
        "parsedHoldingCount": 1,
        "holdings": {"2330": 10.1}
      }
    }
  }
}
""",
                    encoding="utf-8",
                )
                result = server.build_production_data_readiness("0050", days=22, min_snapshots=2)
                self.assertTrue(result["ok"])
                self.assertFalse(result["blockers"])
            finally:
                server.ETF_UNIVERSE_FILE = original_universe
                server.HISTORY_FILE = original_history
                server.ETF_PROFILE_FILE = original_profile
                server.STOCK_UNIVERSE_FILE = original_stock
                server.OFFICIAL_SOURCE_REGISTRY_FILE = original_registry
                server.LIVE_FETCH_ADAPTER = original_adapter
                server.OFFICIAL_ENDPOINT_URL_TEMPLATE = original_endpoint


if __name__ == "__main__":
    unittest.main()
