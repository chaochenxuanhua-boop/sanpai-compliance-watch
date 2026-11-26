#!/usr/bin/env python3
"""Unit tests for Venture 02 Sanpai Multi-Agent Pipeline & Bundled Dataset."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

VENTURE_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(VENTURE_ROOT) not in sys.path:
    sys.path.insert(0, str(VENTURE_ROOT))

from pipeline.sanpai_swarm import (  # noqa: E402
    CANONICAL_DISPOSITION_TYPES,
    DispositionVerifier,
    EntityNormalizer,
    PrefectureSourceHarvester,
    SanpaiMonitorSwarm,
    main as cli_main,
)


class TestSanpaiSwarmPipeline(unittest.TestCase):
    def test_real_nta_corporate_numbers_modulo9(self) -> None:
        # Official real-world Japanese Corporate Numbers:
        # 7000012050002 = National Tax Agency (国税庁)
        # 1180301018771 = Toyota Motor Corporation
        # 8000020130001 = Tokyo Metropolitan Government
        for valid_num in ("7000012050002", "1180301018771", "8000020130001", "７０００-０１２０-５０００２"):
            res = EntityNormalizer.validate_corporate_number(valid_num)
            self.assertTrue(res["is_valid"], msg=f"Expected valid corporate number for {valid_num}: {res}")

        # Corrupted check digits and malformed inputs must fail
        for invalid_num in ("8000012050002", "0000012050002", "9030001734567", "123456789012", "123456789012A"):
            res = EntityNormalizer.validate_corporate_number(invalid_num)
            self.assertFalse(res["is_valid"], msg=f"Expected invalid corporate number for {invalid_num}")

    def test_corporate_name_normalization_and_kyujitai(self) -> None:
        self.assertEqual(
            EntityNormalizer.normalize_corporate_name("㈱ 髙橋環境開發"),
            "株式会社高橋環境開発",
        )
        self.assertEqual(
            EntityNormalizer.normalize_corporate_name("（株）齋藤總合解体工業"),
            "株式会社斎藤総合解体工業",
        )
        self.assertEqual(
            EntityNormalizer.normalize_corporate_name("㈲ 武蔵野アスベストクリーン"),
            "有限会社武蔵野アスベストクリーン",
        )
        # Ensure normal kanji containing 名 or 資 inside names are preserved intact
        self.assertEqual(
            EntityNormalizer.normalize_corporate_name("(株)名古屋資源リサイクル"),
            "株式会社名古屋資源リサイクル",
        )

    def test_permit_number_normalization_10_and_11_digits(self) -> None:
        res11 = EntityNormalizer.normalize_permit_number("第012-20-294815号")
        self.assertTrue(res11["is_valid"])
        self.assertEqual(res11["normalized"], "01220294815")
        self.assertEqual(res11["authority_code"], "012")
        self.assertEqual(res11["business_category_code"], "20")
        self.assertEqual(res11["operator_unique_id"], "294815")
        self.assertFalse(res11["was_10_digit"])

        res10 = EntityNormalizer.normalize_permit_number("第１３００７４５２１８号")
        self.assertTrue(res10["is_valid"])
        self.assertEqual(res10["normalized"], "01300745218")
        self.assertTrue(res10["was_10_digit"])
        self.assertEqual(res10["operator_unique_id"], "745218")

        bad = EntityNormalizer.normalize_permit_number("12345")
        self.assertFalse(bad["is_valid"])

    def test_harvester_dry_run_and_html_link_extraction(self) -> None:
        harvester = PrefectureSourceHarvester()
        report = harvester.check_all_sources(dry_run=True)
        self.assertGreaterEqual(report["total_sources"], 12)
        self.assertEqual(report["dead_link_count"], 0)
        self.assertEqual(report["healthy_count"], report["total_sources"])

        sample_html = """
        <html><body>
          <a href="/docs/202611_shobun_list.pdf">令和8年11月 産業廃棄物行政処分一覧(PDF)</a>
          <a href="https://www.pref.chiba.lg.jp/privacy.html">プライバシーポリシー</a>
        </body></html>
        """
        links = harvester.extract_disposition_links_from_html(
            sample_html, "https://www.pref.chiba.lg.jp/haishi/gyouseishobun/"
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["is_pdf"], "true")
        self.assertTrue(links[0]["url"].endswith("202611_shobun_list.pdf"))

    def test_verifier_and_bundled_dataset_integrity(self) -> None:
        swarm = SanpaiMonitorSwarm()
        dataset = swarm.run_pipeline(dry_run=True, write_output=False)
        self.assertTrue(dataset["verification_passed"])
        self.assertGreaterEqual(dataset["record_count"], 14)

        seen_types = {r["disposition_type"] for r in dataset["dispositions"]}
        for expected_type in CANONICAL_DISPOSITION_TYPES:
            self.assertIn(expected_type, seen_types)

        bundled_json = VENTURE_ROOT / "site" / "data" / "dispositions.json"
        self.assertTrue(bundled_json.is_file())
        on_disk = json.loads(bundled_json.read_text(encoding="utf-8"))
        self.assertTrue(on_disk["verification_passed"])
        self.assertEqual(on_disk["record_count"], dataset["record_count"])
        self.assertIn("最終確認義務は排出事業者に帰属", on_disk["legal_disclaimer"]["short"])

        verifier = DispositionVerifier()
        bad_record = dict(dataset["dispositions"][0])
        bad_record["corporate_number"] = "9010001184920"
        ok, _, errs = verifier.verify_record(bad_record)
        self.assertFalse(ok)
        self.assertTrue(any("corporate_number" in e for e in errs))

    def test_cli_dry_run_no_write(self) -> None:
        exit_code = cli_main(["--dry-run", "--no-write"])
        self.assertEqual(exit_code, 0)

    def test_frontend_dom_id_parity_and_clean_tree(self) -> None:
        html_text = (VENTURE_ROOT / "site" / "index.html").read_text(encoding="utf-8")
        js_text = (VENTURE_ROOT / "site" / "app.js").read_text(encoding="utf-8")
        css_text = (VENTURE_ROOT / "site" / "style.css").read_text(encoding="utf-8")
        self.assertIn("@media print", css_text)
        self.assertIn("公表情報の収集補助ツールであり最終確認義務は排出事業者に帰属します", html_text)

        html_ids = set(re.findall(r'id="([^"]+)"', html_text))
        js_ids = set(re.findall(r'getElementById\("([^"]+)"\)', js_text))
        js_grouped_ids = set(re.findall(r'"((?:meta-|search-|filter-)[a-z-]+)"', js_text))
        missing_ids = (js_ids | js_grouped_ids) - html_ids
        self.assertEqual(missing_ids, set(), msg=f"Missing DOM IDs in index.html: {missing_ids}")

        forbidden_re = re.compile(
            "|".join(["TO" + "DO", "FIX" + "ME", "\u7701\u7565", "place" + "holder", "dum" + "my"]),
            re.IGNORECASE,
        )
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv"}
        text_exts = {".py", ".html", ".css", ".js", ".json", ".yml", ".yaml", ".md"}
        for file_path in VENTURE_ROOT.rglob("*"):
            if (
                file_path.is_file()
                and not (skip_dirs & set(file_path.parts))
                and file_path.suffix.lower() in text_exts
            ):
                content = file_path.read_text(encoding="utf-8")
                match = forbidden_re.search(content)
                self.assertIsNone(match, msg=f"Forbidden marker {match} in {file_path}")


if __name__ == "__main__":
    unittest.main()
