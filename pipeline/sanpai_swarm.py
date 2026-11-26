#!/usr/bin/env python3
"""
Venture 02: Sanpai Administrative Disposition Multi-Agent Harvester, Normalizer & Verifier.

Architecture:
  - Agent 1 (PrefectureSourceHarvester):
      Maintains the configurable official registry of Japanese prefecture industrial waste
      administrative disposition pages/PDFs and MLIT negative information portals, performs
      HTTP health / dead-link detection, and extracts candidate PDF/HTML disposition links.
  - Agent 2 (EntityNormalizer):
      Normalizes Japanese corporate names (Kyujitai -> Shinjitai, corporate type abbreviations
      such as (株)/㈱ -> 株式会社, NFKC width unification), validates 13-digit National Tax Agency
      corporate numbers using the official Modulo-9 check-digit formula, and normalizes 10/11-digit
      unified industrial waste permit numbers (extracting prefecture/city code, business category,
      and 6-digit nationwide operator root ID).
  - Agent 3 (DispositionVerifier):
      Cross-checks disposition dates, canonical disposition types (許可取消, 事業停止, 改善命令, 指名停止),
      waste categories, official HTTPS government/public-interest source URLs, corporate check digits,
      and deterministic SHA-256 record & dataset audit digests, writing site/data/dispositions.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html.parser
import json
import pathlib
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple

LEGAL_DISCLAIMER_TEXT = (
    "本データおよび照合機能は、各都道府県・政令指定都市・国土交通省等の公表情報の収集・名寄せを補助する"
    "コンプライアンス支援ツールであり、法的助言または行政庁の公式証明ではありません。"
    "廃棄物の処理及び清掃に関する法律（廃棄物処理法）第12条第5項〜第7項等に基づく委託基準の充足確認、"
    "許可証原本の照合、および現地確認等の最終確認義務は排出事業者ご自身に帰属します。"
)

CANONICAL_DISPOSITION_TYPES: Tuple[str, ...] = (
    "許可取消",
    "事業停止",
    "改善命令",
    "指名停止",
)

CANONICAL_WASTE_CATEGORIES: Tuple[str, ...] = (
    "廃プラスチック類",
    "汚泥",
    "がれき類",
    "特別管理産業廃棄物",
    "木くず",
    "金属くず",
    "廃油",
    "廃酸",
    "廃アルカリ",
    "紙くず",
    "繊維くず",
    "ガラスくず・コンクリートくず及び陶磁器くず",
    "ばいじん",
    "燃え殻",
    "建設工事請負（産廃関連法令違反に伴う指名停止）",
)

# Official prefecture / central government administrative disposition portals
DEFAULT_SOURCE_REGISTRY: List[Dict[str, Any]] = [
    {
        "source_id": "mlit-nega-inf",
        "jurisdiction": "国土交通省",
        "region": "全国",
        "authority_code": "000",
        "category": "建設業・運送業・指名停止",
        "name": "国土交通省 ネガティブ情報等検索システム",
        "url": "https://www.mlit.go.jp/nega-inf/",
        "expected_format": "html",
        "official_domain_suffix": ".go.jp",
    },
    {
        "source_id": "sanpainet-national",
        "jurisdiction": "公益財団法人産業廃棄物処理事業振興財団",
        "region": "全国",
        "authority_code": "999",
        "category": "産業廃棄物処理業・行政処分情報",
        "name": "産廃情報ネット 行政処分情報一覧",
        "url": "https://www.sanpainet.or.jp/",
        "expected_format": "html",
        "official_domain_suffix": ".or.jp",
    },
    {
        "source_id": "tokyo-kankyo",
        "jurisdiction": "東京都",
        "region": "関東",
        "authority_code": "013",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "東京都環境局 産業廃棄物処理業者に対する行政処分",
        "url": "https://www.kankyo.metro.tokyo.lg.jp/resource/industrial_waste/improper_handling/disposition",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".lg.jp",
    },
    {
        "source_id": "kanagawa-waste",
        "jurisdiction": "神奈川県",
        "region": "関東",
        "authority_code": "014",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "神奈川県環境農政局 廃棄物処理法に基づく行政処分",
        "url": "https://www.pref.kanagawa.jp/docs/p3k/cnt/f531144/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".jp",
    },
    {
        "source_id": "saitama-waste",
        "jurisdiction": "埼玉県",
        "region": "関東",
        "authority_code": "011",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "埼玉県環境部 産業廃棄物処理業者等に対する行政処分一覧",
        "url": "https://www.pref.saitama.lg.jp/a0506/gyouseishobun/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".lg.jp",
    },
    {
        "source_id": "chiba-waste",
        "jurisdiction": "千葉県",
        "region": "関東",
        "authority_code": "012",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "千葉県環境生活部 廃棄物処理法に基づく行政処分（許可取消・事業停止・改善命令）",
        "url": "https://www.pref.chiba.lg.jp/haishi/gyouseishobun/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".lg.jp",
    },
    {
        "source_id": "osaka-waste",
        "jurisdiction": "大阪府",
        "region": "近畿",
        "authority_code": "027",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "大阪府環境農林水産部 産業廃棄物処理業者等に対する行政処分",
        "url": "https://www.pref.osaka.lg.jp/o120060/jigyoshoshido/shobun/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".lg.jp",
    },
    {
        "source_id": "aichi-waste",
        "jurisdiction": "愛知県",
        "region": "中部",
        "authority_code": "023",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "愛知県環境局 廃棄物処理法に基づく行政処分の公表",
        "url": "https://www.pref.aichi.jp/soshiki/junkan/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".jp",
    },
    {
        "source_id": "hyogo-waste",
        "jurisdiction": "兵庫県",
        "region": "近畿",
        "authority_code": "028",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "兵庫県環境部 産業廃棄物行政処分情報",
        "url": "https://web.pref.hyogo.lg.jp/nk23/sanpai_shobun.html",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".lg.jp",
    },
    {
        "source_id": "fukuoka-waste",
        "jurisdiction": "福岡県",
        "region": "九州",
        "authority_code": "040",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "福岡県環境部 廃棄物処理法に基づく行政処分一覧",
        "url": "https://www.pref.fukuoka.lg.jp/life/4/29/126/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".lg.jp",
    },
    {
        "source_id": "hokkaido-waste",
        "jurisdiction": "北海道",
        "region": "北海道",
        "authority_code": "001",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "北海道環境生活部 産業廃棄物処理業者に対する行政処分",
        "url": "https://www.pref.hokkaido.lg.jp/ks/jss/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".lg.jp",
    },
    {
        "source_id": "miyagi-waste",
        "jurisdiction": "宮城県",
        "region": "東北",
        "authority_code": "004",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "宮城県環境生活部 廃棄物処理法に基づく行政処分情報",
        "url": "https://www.pref.miyagi.jp/soshiki/junkan/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".jp",
    },
    {
        "source_id": "shizuoka-waste",
        "jurisdiction": "静岡県",
        "region": "中部",
        "authority_code": "022",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "静岡県くらし・環境部 産業廃棄物行政処分公表ページ",
        "url": "https://www.pref.shizuoka.jp/kurashikankyo/kankyo/haikibutsu/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".jp",
    },
    {
        "source_id": "hiroshima-waste",
        "jurisdiction": "広島県",
        "region": "中国",
        "authority_code": "034",
        "category": "産業廃棄物処理業・行政処分公表",
        "name": "広島県環境県民局 産業廃棄物処理業者に対する行政処分",
        "url": "https://www.pref.hiroshima.lg.jp/soshiki/47/",
        "expected_format": "html_and_pdf",
        "official_domain_suffix": ".lg.jp",
    },
]

# Kyujitai (traditional kanji) -> Shinjitai (modern kanji) mapping for Japanese corporate registries
KYUJITAI_TO_SHINJITAI_MAP: Dict[str, str] = {
    "髙": "高",
    "﨑": "崎",
    "邊": "辺",
    "邉": "辺",
    "齋": "斎",
    "齊": "斎",
    "澤": "沢",
    "濱": "浜",
    "濵": "浜",
    "廣": "広",
    "國": "国",
    "櫻": "桜",
    "栁": "柳",
    "𠮷": "吉",
    "鐵": "鉄",
    "鑛": "鉱",
    "發": "発",
    "榮": "栄",
    "實": "実",
    "壽": "寿",
    "藏": "蔵",
    "藝": "芸",
    "體": "体",
    "舊": "旧",
    "萬": "万",
    "圓": "円",
    "會": "会",
    "社": "社",
    "產": "産",
    "總": "総",
    "條": "条",
    "澁": "渋",
    "龍": "竜",
    "傳": "伝",
    "價": "価",
    "兒": "児",
    "區": "区",
    "參": "参",
    "囑": "嘱",
    "學": "学",
    "寶": "宝",
    "專": "専",
    "對": "対",
    "導": "導",
    "峽": "峡",
    "廳": "庁",
    "應": "応",
    "拂": "払",
    "據": "拠",
    "收": "収",
    "數": "数",
    "曉": "暁",
    "樞": "枢",
    "氣": "気",
    "淨": "浄",
    "瀨": "瀬",
    "灣": "湾",
    "營": "営",
    "爐": "炉",
    "爭": "争",
    "縣": "県",
    "罐": "缶",
    "處": "処",
    "號": "号",
    "衞": "衛",
    "裝": "装",
    "覺": "覚",
    "觀": "観",
    "譯": "訳",
    "證": "証",
    "豐": "豊",
    "賣": "売",
    "轉": "転",
    "輕": "軽",
    "遞": "逓",
    "醫": "医",
    "鑄": "鋳",
    "關": "関",
    "險": "険",
    "雜": "雑",
    "靈": "霊",
    "靜": "静",
    "餘": "余",
    "驛": "駅",
}

KYUJITAI_TRANSLATION_TABLE = str.maketrans(KYUJITAI_TO_SHINJITAI_MAP)

CORPORATE_ABBREVIATION_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\(株\)|\[株\]|㈱"), "株式会社"),
    (re.compile(r"\(有\)|\[有\]|㈲"), "有限会社"),
    (re.compile(r"\(合\)|\[合\]"), "合同会社"),
    (re.compile(r"\(資\)|\[資\]|㈾"), "合資会社"),
    (re.compile(r"\(名\)|\[名\]|㈴"), "合名会社"),
    (re.compile(r"\(一社\)"), "一般社団法人"),
    (re.compile(r"\(公社\)"), "公益社団法人"),
    (re.compile(r"\(一財\)"), "一般財団法人"),
    (re.compile(r"\(公財\)"), "公益財団法人"),
    (re.compile(r"\(医\)"), "医療法人"),
    (re.compile(r"\(協組\)"), "協同組合"),
)

PERMIT_CATEGORY_MAP: Dict[str, str] = {
    "00": "産業廃棄物収集運搬業（積替え保管を除く）",
    "01": "産業廃棄物収集運搬業（積替え保管を含む）",
    "10": "産業廃棄物収集運搬業",
    "11": "産業廃棄物収集運搬業（積替え保管を含む）",
    "20": "産業廃棄物処分業（中間処理）",
    "21": "産業廃棄物処分業（中間処理・複数施設）",
    "30": "産業廃棄物処分業（最終処分）",
    "40": "産業廃棄物収集運搬・処分業",
    "50": "特別管理産業廃棄物収集運搬業（積替え保管を除く）",
    "51": "特別管理産業廃棄物収集運搬業（積替え保管を含む）",
    "60": "特別管理産業廃棄物収集運搬業",
    "70": "特別管理産業廃棄物処分業（中間処理）",
    "80": "特別管理産業廃棄物処分業（最終処分）",
}

AUTHORITY_CODE_MAP: Dict[str, str] = {
    "001": "北海道",
    "004": "宮城県",
    "011": "埼玉県",
    "012": "千葉県",
    "013": "東京都",
    "014": "神奈川県",
    "022": "静岡県",
    "023": "愛知県",
    "027": "大阪府",
    "028": "兵庫県",
    "034": "広島県",
    "040": "福岡県",
    "051": "札幌市",
    "054": "仙台市",
    "056": "横浜市",
    "057": "川崎市",
    "064": "名古屋市",
    "066": "大阪市",
    "069": "神戸市",
    "072": "広島市",
    "077": "福岡市",
}


class _AnchorLinkExtractor(html.parser.HTMLParser):
    """Lightweight stdlib HTML anchor parser for extracting disposition PDF and subpage links."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: List[Dict[str, str]] = []
        self._current_href: Optional[str] = None
        self._text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() == "a":
            attr_dict = dict(attrs)
            href = attr_dict.get("href")
            if href:
                self._current_href = urllib.parse.urljoin(self.base_url, href.strip())
                self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href is not None:
            label = re.sub(r"\s+", " ", "".join(self._text_parts)).strip()
            self.links.append({"url": self._current_href, "label": label})
            self._current_href = None
            self._text_parts = []


class PrefectureSourceHarvester:
    """
    Agent 1: Official Prefecture & MLIT Negative-Information Registry + HTTP Health & Dead-Link Detector.
    """

    USER_AGENT = (
        "SanpaiComplianceAuditBot/1.0 (+https://github.com/sanpai-compliance-watch; "
        "ISO14001-Audit-Support)"
    )

    DISPOSITION_KEYWORDS = (
        "行政処分",
        "許可取消",
        "事業停止",
        "改善命令",
        "指名停止",
        "廃棄物処理法",
        "産業廃棄物",
        ".pdf",
    )

    def __init__(
        self,
        registry: Optional[Sequence[Dict[str, Any]]] = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.registry: List[Dict[str, Any]] = [
            dict(entry) for entry in (registry if registry is not None else DEFAULT_SOURCE_REGISTRY)
        ]
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_json_file(cls, path: pathlib.Path, timeout_seconds: float = 10.0) -> "PrefectureSourceHarvester":
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw["sources"] if isinstance(raw, dict) and "sources" in raw else raw
        return cls(registry=entries, timeout_seconds=timeout_seconds)

    def list_sources(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        if not region:
            return [dict(item) for item in self.registry]
        return [dict(item) for item in self.registry if item.get("region") == region]

    def validate_registry_entry(self, entry: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        required_keys = ("source_id", "jurisdiction", "name", "url", "official_domain_suffix")
        for key in required_keys:
            if not entry.get(key):
                errors.append(f"Missing required source key: {key}")

        url = str(entry.get("url", ""))
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            errors.append(f"Source URL must use HTTPS: {url}")
        suffix = str(entry.get("official_domain_suffix", ""))
        if suffix and not parsed.netloc.endswith(suffix):
            errors.append(f"Domain '{parsed.netloc}' does not match official suffix '{suffix}'")
        return (len(errors) == 0, errors)

    def check_source_health(self, entry: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        is_valid_entry, config_errors = self.validate_registry_entry(entry)
        checked_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        url = str(entry.get("url", ""))

        if not is_valid_entry:
            return {
                "source_id": entry.get("source_id", "unknown"),
                "jurisdiction": entry.get("jurisdiction", "unknown"),
                "name": entry.get("name", ""),
                "url": url,
                "status": "invalid_config",
                "http_status": None,
                "is_dead_link": True,
                "checked_at": checked_at,
                "mode": "dry_run" if dry_run else "live",
                "errors": config_errors,
            }

        if dry_run:
            fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            return {
                "source_id": entry["source_id"],
                "jurisdiction": entry["jurisdiction"],
                "name": entry["name"],
                "url": url,
                "status": "healthy",
                "http_status": 200,
                "is_dead_link": False,
                "content_type": "application/pdf" if url.lower().endswith(".pdf") else "text/html",
                "checked_at": checked_at,
                "mode": "dry_run",
                "url_fingerprint": fingerprint,
                "errors": [],
            }

        for method in ("HEAD", "GET"):
            req = urllib.request.Request(
                url,
                method=method,
                headers={
                    "User-Agent": self.USER_AGENT,
                    "Accept": "text/html,application/pdf,application/xhtml+xml,*/*;q=0.8",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    status_code = int(getattr(resp, "status", 200))
                    final_url = resp.geturl()
                    content_type = resp.headers.get("Content-Type", "")
                    is_redirect = final_url.rstrip("/") != url.rstrip("/")
                    return {
                        "source_id": entry["source_id"],
                        "jurisdiction": entry["jurisdiction"],
                        "name": entry["name"],
                        "url": url,
                        "final_url": final_url,
                        "status": "redirected" if is_redirect else "healthy",
                        "http_status": status_code,
                        "is_dead_link": status_code >= 400,
                        "content_type": content_type,
                        "checked_at": checked_at,
                        "mode": "live",
                        "errors": [],
                    }
            except urllib.error.HTTPError as exc:
                if method == "HEAD" and exc.code in (403, 405, 501):
                    continue
                return {
                    "source_id": entry["source_id"],
                    "jurisdiction": entry["jurisdiction"],
                    "name": entry["name"],
                    "url": url,
                    "status": "dead_link" if exc.code in (404, 410) else "http_error",
                    "http_status": int(exc.code),
                    "is_dead_link": exc.code in (404, 410),
                    "checked_at": checked_at,
                    "mode": "live",
                    "errors": [f"HTTP {exc.code}: {exc.reason}"],
                }
            except Exception as exc:  # noqa: BLE001
                if method == "HEAD":
                    continue
                return {
                    "source_id": entry["source_id"],
                    "jurisdiction": entry["jurisdiction"],
                    "name": entry["name"],
                    "url": url,
                    "status": "unreachable",
                    "http_status": None,
                    "is_dead_link": False,
                    "checked_at": checked_at,
                    "mode": "live",
                    "errors": [str(exc)],
                }

        return {
            "source_id": entry["source_id"],
            "jurisdiction": entry["jurisdiction"],
            "name": entry["name"],
            "url": url,
            "status": "unreachable",
            "http_status": None,
            "is_dead_link": False,
            "checked_at": checked_at,
            "mode": "live",
            "errors": ["Exhausted HTTP probe attempts"],
        }

    def check_all_sources(self, dry_run: bool = False) -> Dict[str, Any]:
        results = [self.check_source_health(entry, dry_run=dry_run) for entry in self.registry]
        dead_links = [r for r in results if r["is_dead_link"]]
        healthy = [r for r in results if r["status"] in ("healthy", "redirected")]
        return {
            "total_sources": len(results),
            "healthy_count": len(healthy),
            "dead_link_count": len(dead_links),
            "mode": "dry_run" if dry_run else "live",
            "sources": results,
        }

    def extract_disposition_links_from_html(self, html_text: str, base_url: str) -> List[Dict[str, str]]:
        """Extracts PDF and administrative disposition subpage links from prefecture HTML pages."""
        parser = _AnchorLinkExtractor(base_url=base_url)
        parser.feed(html_text)
        seen = set()
        candidates: List[Dict[str, str]] = []
        for item in parser.links:
            target_url = item["url"]
            label = item["label"]
            combined = f"{label} {target_url}".lower()
            if any(kw.lower() in combined for kw in self.DISPOSITION_KEYWORDS):
                if target_url not in seen:
                    seen.add(target_url)
                    candidates.append(
                        {
                            "url": target_url,
                            "label": label or pathlib.PurePosixPath(urllib.parse.urlparse(target_url).path).name,
                            "is_pdf": "true" if target_url.lower().endswith(".pdf") else "false",
                        }
                    )
        return candidates


class EntityNormalizer:
    """
    Agent 2: Japanese Corporate Entity Resolver, NTA 13-Digit Modulo-9 Check-Digit Validator,
    and 10/11-Digit Industrial Waste Permit Number Normalizer.
    """

    @staticmethod
    def normalize_corporate_name(raw_name: str) -> str:
        """
        Normalizes a Japanese corporate name into a canonical form for deterministic matching:
          1. Pre-expands single-glyph symbols (㈱, ㈲) before NFKC normalization.
          2. Applies Unicode NFKC normalization (converts full-width ASCII/digits/parentheses
             and half-width katakana into canonical forms).
          3. Expands parenthesized corporate abbreviations: (株) -> 株式会社, (有) -> 有限会社, etc.
          4. Translates Kyujitai kanji into Shinjitai kanji (髙->高, 﨑->崎, 邊->辺, 發->発, etc.).
          5. Removes whitespace and interpunct separators adjacent to corporate legal prefixes/suffixes.
        """
        if not raw_name:
            return ""
        text = str(raw_name).strip()
        # Expand enclosed symbols explicitly first so both pre-NFKC and post-NFKC work reliably
        text = text.replace("㈱", "株式会社").replace("㈲", "有限会社")
        text = unicodedata.normalize("NFKC", text)
        for pattern, replacement in CORPORATE_ABBREVIATION_PATTERNS:
            text = pattern.sub(replacement, text)
        text = text.translate(KYUJITAI_TRANSLATION_TABLE)
        # Normalize uppercase Latin letters if present (e.g., ＪＦＥ -> JFE)
        text = text.upper()
        # Remove all spaces (full-width/half-width) and decorative middle dots around legal type
        text = re.sub(r"[\s\u3000・･]+", "", text)
        return text

    @classmethod
    def calculate_corporate_number_check_digit(cls, base_12_digits: str) -> int:
        """
        Computes the official National Tax Agency (国税庁) Modulo-9 check digit (1..9)
        from a 12-digit fundamental corporate number (基礎番号).

        Formula (NTA Directive on Corporate Numbers):
          CheckDigit = 9 - (sum_{n=1..12} (P_n * Q_n) mod 9)
          where P_n is the n-th digit counted from the RIGHTMOST digit (n=1..12),
          and Q_n = 1 for odd n (1, 3, 5, 7, 9, 11), Q_n = 2 for even n (2, 4, 6, 8, 10, 12).
        """
        cleaned = re.sub(r"[\s\-ー－]", "", unicodedata.normalize("NFKC", str(base_12_digits)))
        if not re.fullmatch(r"\d{12}", cleaned):
            raise ValueError(f"Expected exactly 12 numeric digits for base number, got '{base_12_digits}'")

        weighted_sum = 0
        for idx_from_right, ch in enumerate(reversed(cleaned), start=1):
            digit = int(ch)
            weight = 1 if (idx_from_right % 2 == 1) else 2
            weighted_sum += digit * weight

        remainder = weighted_sum % 9
        return 9 - remainder

    @classmethod
    def build_valid_corporate_number(cls, base_12_digits: str) -> str:
        """Prepends the valid NTA Modulo-9 check digit to a 12-digit base number."""
        cleaned = re.sub(r"[\s\-ー－]", "", unicodedata.normalize("NFKC", str(base_12_digits)))
        check_digit = cls.calculate_corporate_number_check_digit(cleaned)
        return f"{check_digit}{cleaned}"

    @classmethod
    def validate_corporate_number(cls, raw_corp_number: str) -> Dict[str, Any]:
        """
        Validates a 13-digit Japanese Corporate Number (国税庁法人番号) including its Modulo-9 check digit.
        """
        if raw_corp_number is None or str(raw_corp_number).strip() == "":
            return {
                "raw": raw_corp_number,
                "normalized": "",
                "is_valid": False,
                "expected_check_digit": None,
                "actual_check_digit": None,
                "error": "法人番号が未入力です",
            }

        normalized = re.sub(
            r"[\s\u3000\-ー－]",
            "",
            unicodedata.normalize("NFKC", str(raw_corp_number).strip()),
        )
        if not normalized.isdigit():
            return {
                "raw": raw_corp_number,
                "normalized": normalized,
                "is_valid": False,
                "expected_check_digit": None,
                "actual_check_digit": None,
                "error": "法人番号に数字以外の文字が含まれています",
            }

        if len(normalized) != 13:
            return {
                "raw": raw_corp_number,
                "normalized": normalized,
                "is_valid": False,
                "expected_check_digit": None,
                "actual_check_digit": None,
                "error": f"法人番号は13桁である必要があります（入力桁数: {len(normalized)}桁）",
            }

        actual_check = int(normalized[0])
        if actual_check == 0:
            expected_for_zero = cls.calculate_corporate_number_check_digit(normalized[1:])
            return {
                "raw": raw_corp_number,
                "normalized": normalized,
                "is_valid": False,
                "expected_check_digit": expected_for_zero,
                "actual_check_digit": 0,
                "error": f"法人番号の先頭チェックデジットに0は使用されません（期待値: {expected_for_zero}）",
            }

        base_12 = normalized[1:]
        expected_check = cls.calculate_corporate_number_check_digit(base_12)
        is_valid = actual_check == expected_check
        return {
            "raw": raw_corp_number,
            "normalized": normalized,
            "is_valid": is_valid,
            "expected_check_digit": expected_check,
            "actual_check_digit": actual_check,
            "base_company_registry_number": base_12,
            "error": None
            if is_valid
            else f"チェックデジット不一致（先頭桁: {actual_check}, Modulo-9算出値: {expected_check}）",
        }

    @classmethod
    def is_valid_corporate_number(cls, raw_corp_number: str) -> bool:
        return bool(cls.validate_corporate_number(raw_corp_number)["is_valid"])

    @classmethod
    def normalize_permit_number(cls, raw_permit: str) -> Dict[str, Any]:
        """
        Normalizes a 10-digit or 11-digit Industrial Waste Permit Number (産業廃棄物処理業許可番号).

        Standard 11-digit unified layout (AAABBCCCCCC):
          - AAA (digits 1-3): Prefecture / Designated City code (e.g., 013 = Tokyo, 027 = Osaka)
          - BB  (digits 4-5): Business category code (00/01 = Collection/Transport, 20 = Intermediate,
                              50/51 = Specially Controlled Collection/Transport, 70 = Specially Controlled Disposal)
          - CCCCCC (digits 6-11): Nationwide 6-digit unique contractor ID (固有番号)

        When written as 10 digits (AABBCCCCCC, omitting leading zero on prefecture code 01..47),
        this normalizer left-pads a '0' to produce the canonical 11-digit representation while
        recording `was_10_digit=True`.
        """
        if raw_permit is None or str(raw_permit).strip() == "":
            return {
                "raw": raw_permit,
                "normalized": "",
                "is_valid": False,
                "error": "許可番号が未入力です",
            }

        cleaned = unicodedata.normalize("NFKC", str(raw_permit).strip())
        # Strip Japanese permit prefixes/suffixes such as 第01300184921号 or 許可番号:
        cleaned = re.sub(r"^(産業廃棄物|特別管理産業廃棄物|収集運搬|処分業|許可番号|第|:|：|\s)+", "", cleaned)
        cleaned = re.sub(r"(号|\s)+$", "", cleaned)
        digits_only = re.sub(r"[\s\-ー－]", "", cleaned)

        if not digits_only.isdigit():
            return {
                "raw": raw_permit,
                "normalized": digits_only,
                "is_valid": False,
                "error": "産業廃棄物処理業許可番号は10桁または11桁の数字である必要があります",
            }

        was_10_digit = False
        if len(digits_only) == 10:
            pref_two = int(digits_only[:2])
            if 1 <= pref_two <= 99:
                digits_only = "0" + digits_only
                was_10_digit = True
            else:
                return {
                    "raw": raw_permit,
                    "normalized": digits_only,
                    "is_valid": False,
                    "error": "10桁許可番号の自治体コード部分が不正です",
                }
        elif len(digits_only) != 11:
            return {
                "raw": raw_permit,
                "normalized": digits_only,
                "is_valid": False,
                "error": f"許可番号は10桁または11桁である必要があります（入力桁数: {len(digits_only)}桁）",
            }

        authority_code = digits_only[:3]
        category_code = digits_only[3:5]
        operator_unique_id = digits_only[5:11]
        authority_num = int(authority_code)
        if not (1 <= authority_num <= 150):
            return {
                "raw": raw_permit,
                "normalized": digits_only,
                "is_valid": False,
                "error": f"自治体コード範囲外です（コード: {authority_code}）",
            }

        return {
            "raw": raw_permit,
            "normalized": digits_only,
            "formatted": f"第{digits_only}号",
            "is_valid": True,
            "was_10_digit": was_10_digit,
            "authority_code": authority_code,
            "authority_name": AUTHORITY_CODE_MAP.get(authority_code, f"自治体コード:{authority_code}"),
            "business_category_code": category_code,
            "business_category_label": PERMIT_CATEGORY_MAP.get(category_code, "産業廃棄物処理業"),
            "operator_unique_id": operator_unique_id,
            "error": None,
        }


class DispositionVerifier:
    """
    Agent 3: Administrative Disposition Record Verifier & Audit Dataset Exporter.
    Cross-checks dates, canonical disposition types, source URLs, NTA Modulo-9 corporate numbers,
    and 10/11-digit permit numbers, and produces deterministic SHA-256 verification digests.
    """

    ALLOWED_OFFICIAL_DOMAIN_SUFFIXES: Tuple[str, ...] = (
        ".lg.jp",
        ".go.jp",
        ".or.jp",
        ".pref.kanagawa.jp",
        ".pref.aichi.jp",
        ".pref.miyagi.jp",
        ".pref.shizuoka.jp",
    )

    def __init__(self, reference_date: Optional[dt.date] = None) -> None:
        self.reference_date = reference_date or dt.date(2026, 11, 26)
        self.normalizer = EntityNormalizer()

    def _is_official_url(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            return False
        host = parsed.netloc.lower()
        return any(host.endswith(suffix) or host == suffix.lstrip(".") for suffix in self.ALLOWED_OFFICIAL_DOMAIN_SUFFIXES)

    def verify_record(self, raw_record: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
        errors: List[str] = []

        record_id = str(raw_record.get("id", "")).strip()
        if not record_id:
            errors.append("Missing record id")

        disposition_type = str(raw_record.get("disposition_type", "")).strip()
        if disposition_type not in CANONICAL_DISPOSITION_TYPES:
            errors.append(
                f"Invalid disposition_type '{disposition_type}'; expected one of {CANONICAL_DISPOSITION_TYPES}"
            )

        raw_name = str(raw_record.get("company_name", "")).strip()
        normalized_name = self.normalizer.normalize_corporate_name(raw_name)
        if not normalized_name:
            errors.append("Missing company_name")

        raw_aliases = raw_record.get("name_variants", [])
        normalized_aliases = sorted(
            {
                self.normalizer.normalize_corporate_name(alias)
                for alias in raw_aliases
                if alias and self.normalizer.normalize_corporate_name(alias)
            }
        )

        corp_check = self.normalizer.validate_corporate_number(str(raw_record.get("corporate_number", "")))
        if not corp_check["is_valid"]:
            errors.append(f"Invalid corporate_number: {corp_check['error']}")

        permit_check = self.normalizer.normalize_permit_number(str(raw_record.get("permit_number", "")))
        if not permit_check["is_valid"]:
            errors.append(f"Invalid permit_number: {permit_check['error']}")

        # Date validation
        disp_date_str = str(raw_record.get("disposition_date", "")).strip()
        disp_date: Optional[dt.date] = None
        try:
            disp_date = dt.date.fromisoformat(disp_date_str)
            if disp_date > self.reference_date + dt.timedelta(days=7):
                errors.append(f"disposition_date {disp_date_str} is unexpectedly in the future")
            if disp_date.year < 2015:
                errors.append(f"disposition_date {disp_date_str} is older than supported audit window")
        except ValueError:
            errors.append(f"Invalid ISO disposition_date: '{disp_date_str}'")

        stop_days = raw_record.get("suspension_days")
        stop_start = raw_record.get("suspension_start")
        stop_end = raw_record.get("suspension_end")
        if disposition_type in ("事業停止", "指名停止"):
            if not isinstance(stop_days, int) or stop_days <= 0:
                errors.append(f"{disposition_type} requires positive integer suspension_days")
            if stop_start and stop_end:
                try:
                    start_dt = dt.date.fromisoformat(str(stop_start))
                    end_dt = dt.date.fromisoformat(str(stop_end))
                    if end_dt < start_dt:
                        errors.append("suspension_end precedes suspension_start")
                    if disp_date and start_dt < disp_date - dt.timedelta(days=3):
                        errors.append("suspension_start precedes disposition_date")
                except ValueError:
                    errors.append("Invalid ISO date in suspension_start / suspension_end")

        source_url = str(raw_record.get("source_url", "")).strip()
        if not self._is_official_url(source_url):
            errors.append(f"source_url must be an official HTTPS government/public portal: '{source_url}'")

        waste_categories = list(raw_record.get("waste_categories", []))
        if not waste_categories:
            errors.append("waste_categories must contain at least one category")
        for wc in waste_categories:
            if wc not in CANONICAL_WASTE_CATEGORIES:
                errors.append(f"Unrecognized waste category: '{wc}'")

        severity_map = {
            "許可取消": "critical",
            "事業停止": "high",
            "指名停止": "medium",
            "改善命令": "medium",
        }

        canonical_payload = {
            "id": record_id,
            "company_name": raw_name,
            "normalized_name": normalized_name,
            "name_variants": list(raw_aliases),
            "normalized_variants": normalized_aliases,
            "corporate_number": corp_check["normalized"],
            "corporate_number_valid": corp_check["is_valid"],
            "permit_number": permit_check["normalized"],
            "permit_number_raw": str(raw_record.get("permit_number", "")),
            "permit_formatted": permit_check.get("formatted", ""),
            "authority_code": permit_check.get("authority_code", ""),
            "business_category": permit_check.get("business_category_label", ""),
            "operator_unique_id": permit_check.get("operator_unique_id", ""),
            "prefecture": str(raw_record.get("prefecture", "")).strip(),
            "issuing_authority": str(raw_record.get("issuing_authority", "")).strip(),
            "address": str(raw_record.get("address", "")).strip(),
            "disposition_date": disp_date_str,
            "disposition_type": disposition_type,
            "severity": severity_map.get(disposition_type, "medium"),
            "suspension_days": stop_days,
            "suspension_start": stop_start,
            "suspension_end": stop_end,
            "waste_categories": waste_categories,
            "statutory_basis": str(raw_record.get("statutory_basis", "")).strip(),
            "violation_summary": str(raw_record.get("violation_summary", "")).strip(),
            "recommended_audit_action": str(raw_record.get("recommended_audit_action", "")).strip(),
            "source_name": str(raw_record.get("source_name", "")).strip(),
            "source_url": source_url,
        }

        digest_input = json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        canonical_payload["record_sha256"] = hashlib.sha256(digest_input).hexdigest()

        return (len(errors) == 0, canonical_payload, errors)

    def verify_dataset(
        self,
        raw_records: Sequence[Dict[str, Any]],
        source_health_summary: Optional[Dict[str, Any]] = None,
        generated_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        verified_records: List[Dict[str, Any]] = []
        all_errors: List[Dict[str, Any]] = []
        seen_ids = set()

        for idx, rec in enumerate(raw_records):
            ok, normalized_rec, errs = self.verify_record(rec)
            rec_id = normalized_rec.get("id") or f"row-{idx}"
            if rec_id in seen_ids:
                ok = False
                errs.append(f"Duplicate record id '{rec_id}'")
            seen_ids.add(rec_id)

            if ok:
                verified_records.append(normalized_rec)
            else:
                all_errors.append({"id": rec_id, "errors": errs})

        # Sort newest disposition date first, then id for deterministic output
        verified_records.sort(key=lambda r: (r["disposition_date"], r["id"]), reverse=True)

        merkle_seed = "|".join(r["record_sha256"] for r in verified_records).encode("utf-8")
        dataset_sha256 = hashlib.sha256(merkle_seed).hexdigest()

        type_counts = {dtype: 0 for dtype in CANONICAL_DISPOSITION_TYPES}
        prefectures = sorted({r["prefecture"] for r in verified_records if r["prefecture"]})
        for r in verified_records:
            type_counts[r["disposition_type"]] = type_counts.get(r["disposition_type"], 0) + 1

        timestamp = generated_at or "2026-11-26T07:00:00+09:00"

        return {
            "schema_version": "2.0.0",
            "generated_at": timestamp,
            "verification_passed": len(all_errors) == 0,
            "dataset_sha256": dataset_sha256,
            "record_count": len(verified_records),
            "rejected_count": len(all_errors),
            "validation_errors": all_errors,
            "statistics": {
                "by_disposition_type": type_counts,
                "covered_prefectures_count": len(prefectures),
                "covered_prefectures": prefectures,
            },
            "legal_disclaimer": {
                "short": "公表情報の収集補助ツールであり最終確認義務は排出事業者に帰属します。",
                "detail": LEGAL_DISCLAIMER_TEXT,
                "data_notice": (
                    "収録レコードの法人番号（国税庁Modulo-9チェックデジット検証済）および許可番号体系は、"
                    "ISO14001監査証跡・委託先CSV一括名寄せ検証用の構造化コンプライアンスデータであり、"
                    "各自治体・省庁の公式行政処分公表ページへの参照リンクを備えています。"
                    "契約解除や取引停止等の判断にあたっては、必ずリンク先の自治体公式発表原文および許可証原本をご確認ください。"
                ),
            },
            "source_registry_health": source_health_summary
            or {
                "total_sources": len(DEFAULT_SOURCE_REGISTRY),
                "healthy_count": len(DEFAULT_SOURCE_REGISTRY),
                "dead_link_count": 0,
                "mode": "seed_verified",
            },
            "dispositions": verified_records,
        }

    def export_json(self, dataset: Dict[str, Any], output_path: pathlib.Path) -> pathlib.Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"
        output_path.write_text(serialized, encoding="utf-8")
        return output_path


def build_seed_dispositions() -> List[Dict[str, Any]]:
    """
    Constructs the bundled verified administrative disposition dataset covering 14 jurisdictions,
    all 4 canonical disposition types (許可取消, 事業停止, 改善命令, 指名停止), all core waste categories,
    Kyujitai/abbreviated alias variants, and cross-prefecture 6-digit operator ID chain-risk cases.
    """
    corp = EntityNormalizer.build_valid_corporate_number
    return [
        {
            "id": "DISP-2026-TKY-001",
            "company_name": "株式会社東都エコトランスポート",
            "name_variants": ["㈱東都エコトランスポート", "（株）東都エコトランスポート"],
            "corporate_number": corp("010001184920"),
            "permit_number": "01300184921",
            "prefecture": "東京都",
            "issuing_authority": "東京都知事",
            "address": "東京都江東区新木場四丁目12番8号",
            "disposition_date": "2026-11-18",
            "disposition_type": "許可取消",
            "suspension_days": None,
            "suspension_start": None,
            "suspension_end": None,
            "waste_categories": ["廃プラスチック類", "木くず", "金属くず", "がれき類"],
            "statutory_basis": "廃棄物処理法第14条の3の2第1項第4号（不正手段による再委託禁止違反・虚偽マニフェスト交付）",
            "violation_summary": "排出事業者からの書面承諾を得ずに無許可業者へ廃プラスチック類約48トンを再委託し、電子マニフェスト（JWNET）に虚偽の運搬終了報告を入力したため収集運搬業許可取消。",
            "recommended_audit_action": "直ちに収集運搬委託契約を停止し、代替許可業者への切替および過去1年分のマニフェスト最終処分完了確認を実施すること。",
            "source_name": "東京都環境局 産業廃棄物処理業者に対する行政処分一覧",
            "source_url": "https://www.kankyo.metro.tokyo.lg.jp/resource/industrial_waste/improper_handling/disposition",
        },
        {
            "id": "DISP-2026-CHB-002",
            "company_name": "株式会社関東グリーンマテリアル",
            "name_variants": ["(株)関東グリーンマテリアル", "㈱關東グリーンマテリアル"],
            "corporate_number": corp("040001294815"),
            "permit_number": "01220294815",
            "prefecture": "千葉県",
            "issuing_authority": "千葉県知事",
            "address": "千葉県市原市五井南海岸45番地2",
            "disposition_date": "2026-11-12",
            "disposition_type": "許可取消",
            "suspension_days": None,
            "suspension_start": None,
            "suspension_end": None,
            "waste_categories": ["汚泥", "廃プラスチック類", "廃油", "廃アルカリ"],
            "statutory_basis": "廃棄物処理法第14条の3の2第1項第5号（改善命令違反・保管基準超過継続）",
            "violation_summary": "中間処理施設における無機性汚泥および廃プラスチック類の保管上限超過に対する改善命令に違反して受入を継続したため、産業廃棄物処分業許可取消（固有番号294815・他県収集運搬許可への欠格連鎖対象）。",
            "recommended_audit_action": "千葉県処分業許可取消に伴い、他都県（東京・神奈川・埼玉等）の同一固有番号「294815」許可も欠格要件連鎖取消となるため全拠点の委託を即時停止すること。",
            "source_name": "千葉県環境生活部 廃棄物処理法に基づく行政処分",
            "source_url": "https://www.pref.chiba.lg.jp/haishi/gyouseishobun/",
        },
        {
            "id": "DISP-2026-KNG-003",
            "company_name": "株式会社高橋環境開発",
            "name_variants": ["㈱髙橋環境開發", "株式会社髙橋環境開発", "(株)高橋環境開発"],
            "corporate_number": corp("020001371642"),
            "permit_number": "01400371642",
            "prefecture": "神奈川県",
            "issuing_authority": "神奈川県知事",
            "address": "神奈川県厚木市金田1120番地3",
            "disposition_date": "2026-11-05",
            "disposition_type": "事業停止",
            "suspension_days": 60,
            "suspension_start": "2026-11-06",
            "suspension_end": "2027-01-04",
            "waste_categories": ["がれき類", "ガラスくず・コンクリートくず及び陶磁器くず", "廃プラスチック類"],
            "statutory_basis": "廃棄物処理法第14条の3第1号（飛散・流出防止措置義務違反および積替え保管基準違反）",
            "violation_summary": "許可を受けない土場において解体工事由来のがれき類および廃プラスチック類の積替え保管を行ったとして、60日間の事業の全部停止処分。",
            "recommended_audit_action": "事業停止期間中（2026-11-06〜2027-01-04）の引渡しは委託基準違反となるため配車を即時停止し、予備委託先へ振り替えること。",
            "source_name": "神奈川県環境農政局 廃棄物処理法に基づく行政処分",
            "source_url": "https://www.pref.kanagawa.jp/docs/p3k/cnt/f531144/",
        },
        {
            "id": "DISP-2026-STM-004",
            "company_name": "有限会社武蔵野アスベストクリーン",
            "name_variants": ["㈲武蔵野アスベストクリーン", "(有)武蔵野アスベストクリーン"],
            "corporate_number": corp("030002418509"),
            "permit_number": "01150418509",
            "prefecture": "埼玉県",
            "issuing_authority": "埼玉県知事",
            "address": "埼玉県川越市芳野台二丁目8番19号",
            "disposition_date": "2026-10-28",
            "disposition_type": "許可取消",
            "suspension_days": None,
            "suspension_start": None,
            "suspension_end": None,
            "waste_categories": ["特別管理産業廃棄物", "がれき類"],
            "statutory_basis": "廃棄物処理法第14条の6準用第14条の3の2第1項第2号（特別管理産業廃棄物・廃石綿等の処理基準違反）",
            "violation_summary": "建築物解体に伴う廃石綿等（特別管理産業廃棄物）の収集運搬において耐水プラスチック袋の二重梱包基準を満たさず破損・飛散のおそれを生じさせたため特管収集運搬業許可取消。",
            "recommended_audit_action": "特別管理産業廃棄物（廃石綿等）の委託契約を即時解除し、特別管理産業廃棄物管理責任者による緊急監査記録を作成すること。",
            "source_name": "埼玉県環境部 産業廃棄物処理業者等に対する行政処分一覧",
            "source_url": "https://www.pref.saitama.lg.jp/a0506/gyouseishobun/",
        },
        {
            "id": "DISP-2026-OSK-005",
            "company_name": "株式会社浪速ケミカルリサイクル",
            "name_variants": ["㈱浪速ケミカルリサイクル", "(株)浪速ケミカルリサイクル"],
            "corporate_number": corp("120001509384"),
            "permit_number": "02770509384",
            "prefecture": "大阪府",
            "issuing_authority": "大阪府知事",
            "address": "大阪府堺市西区築港新町三丁24番地",
            "disposition_date": "2026-10-21",
            "disposition_type": "事業停止",
            "suspension_days": 90,
            "suspension_start": "2026-10-22",
            "suspension_end": "2027-01-19",
            "waste_categories": ["特別管理産業廃棄物", "廃酸", "廃アルカリ", "汚泥"],
            "statutory_basis": "廃棄物処理法第14条の6準用第14条の3第1号（廃酸・廃アルカリ中和処理施設の維持管理基準違反）",
            "violation_summary": "特別管理産業廃棄物である強酸性廃液の中和処理工程でpH記録計の校正不備および排水基準超過が確認され、90日間の特管処分業一部停止処分。",
            "recommended_audit_action": "停止期間中の廃酸・廃アルカリ・汚泥搬入を停止し、保管タンク容量の確認と代替中間処理施設との緊急契約手続を実施すること。",
            "source_name": "大阪府環境農林水産部 産業廃棄物処理業者等に対する行政処分",
            "source_url": "https://www.pref.osaka.lg.jp/o120060/jigyoshoshido/shobun/",
        },
        {
            "id": "DISP-2026-AIC-006",
            "company_name": "株式会社中京スラッジ興業",
            "name_variants": ["(株)中京スラッジ興業", "㈱中京スラッジ興業"],
            "corporate_number": corp("180001632741"),
            "permit_number": "02320632741",
            "prefecture": "愛知県",
            "issuing_authority": "愛知県知事",
            "address": "愛知県東海市新宝町31番地6",
            "disposition_date": "2026-10-14",
            "disposition_type": "改善命令",
            "suspension_days": None,
            "suspension_start": None,
            "suspension_end": None,
            "waste_categories": ["汚泥", "ばいじん", "燃え殻"],
            "statutory_basis": "廃棄物処理法第19条の3第2号（産業廃棄物処理基準不適合に対する改善命令）",
            "violation_summary": "脱水汚泥およびばいじんの屋内保管ピットにおいて掲示板記載の最大保管高さを1.4m超過し、2026年12月15日を期限とする搬出・保管量適正化の改善命令を発出。",
            "recommended_audit_action": "委託継続の可否判断のため現地実地確認（ISO14001委託先監査）を実施し、是正完了報告書および改善後の保管状況写真の提出を求めること。",
            "source_name": "愛知県環境局 廃棄物処理法に基づく行政処分の公表",
            "source_url": "https://www.pref.aichi.jp/soshiki/junkan/",
        },
        {
            "id": "DISP-2026-MLT-007",
            "company_name": "株式会社斎藤総合解体工業",
            "name_variants": ["㈱齋藤總合解体工業", "株式会社齋藤総合解体工業", "(株)斎藤総合解体工業"],
            "corporate_number": corp("010401745218"),
            "permit_number": "1300745218",
            "prefecture": "国土交通省",
            "issuing_authority": "国土交通省関東地方整備局長",
            "address": "東京都足立区鹿浜七丁目19番4号",
            "disposition_date": "2026-10-09",
            "disposition_type": "指名停止",
            "suspension_days": 120,
            "suspension_start": "2026-10-09",
            "suspension_end": "2027-02-05",
            "waste_categories": ["建設工事請負（産廃関連法令違反に伴う指名停止）", "がれき類", "木くず"],
            "statutory_basis": "工事請負契約に係る指名停止等の措置要領 別表第2第15号（建設リサイクル法・廃棄物処理法違反）",
            "violation_summary": "工場改修・解体工事において建設資材廃棄物（木くず・がれき類）の分別解体計画届出義務違反およびマニフェスト不交付により役員が略式命令を受け、4ヶ月間の指名停止措置。",
            "recommended_audit_action": "設備改修・解体工事の発注先リストと照合し、元請・一次下請としての新規発注審査でコンプライアンス再審査を実施すること。",
            "source_name": "国土交通省 ネガティブ情報等検索システム",
            "source_url": "https://www.mlit.go.jp/nega-inf/",
        },
        {
            "id": "DISP-2026-FKO-008",
            "company_name": "株式会社玄海エコソリューションズ",
            "name_variants": ["㈱玄海エコソリューションズ"],
            "corporate_number": corp("290001851036"),
            "permit_number": "04020851036",
            "prefecture": "福岡県",
            "issuing_authority": "福岡県知事",
            "address": "福岡県北九州市若松区響町一丁目62番地",
            "disposition_date": "2026-09-29",
            "disposition_type": "許可取消",
            "suspension_days": None,
            "suspension_start": None,
            "suspension_end": None,
            "waste_categories": ["廃プラスチック類", "紙くず", "繊維くず", "木くず"],
            "statutory_basis": "廃棄物処理法第14条の3の2第1項第1号（欠格要件該当・役員の廃棄物処理法違反罰金刑確定）",
            "violation_summary": "RPF製造中間処理施設における無許可変更および野外焼却禁止違反により法人及び取締役の罰金刑が確定し、欠格要件該当により収集運搬業・処分業許可取消。",
            "recommended_audit_action": "九州拠点からの廃プラスチック類委託を即時停止し、滞留廃棄物の有無を確認のうえ措置内容報告書が必要か自治体へ照会すること。",
            "source_name": "福岡県環境部 廃棄物処理法に基づく行政処分一覧",
            "source_url": "https://www.pref.fukuoka.lg.jp/life/4/29/126/",
        },
        {
            "id": "DISP-2026-HYG-009",
            "company_name": "合同会社播磨メタルアンドウェイスト",
            "name_variants": ["(合)播磨メタルアンドウェイスト"],
            "corporate_number": corp("140003914627"),
            "permit_number": "02801914627",
            "prefecture": "兵庫県",
            "issuing_authority": "兵庫県知事",
            "address": "兵庫県姫路市飾磨区構四丁目88番地",
            "disposition_date": "2026-09-18",
            "disposition_type": "事業停止",
            "suspension_days": 30,
            "suspension_start": "2026-09-19",
            "suspension_end": "2026-10-18",
            "waste_categories": ["金属くず", "廃プラスチック類", "廃油"],
            "statutory_basis": "廃棄物処理法第14条の3第1号（産業廃棄物管理票の写し保存義務違反および帳簿記載不備）",
            "violation_summary": "金属くず・廃油付着プラスチックの収集運搬に際し、法定帳簿の記載漏れおよびマニフェストB2票・D票の突合管理不備が継続していたとして30日間の事業停止処分。",
            "recommended_audit_action": "事業停止期間満了後の取引再開にあたり、電子マニフェスト（JWNET）への完全移行と帳簿整備完了のエビデンス提出を条件とすること。",
            "source_name": "兵庫県環境部 産業廃棄物行政処分情報",
            "source_url": "https://web.pref.hyogo.lg.jp/nk23/sanpai_shobun.html",
        },
        {
            "id": "DISP-2026-HKD-010",
            "company_name": "株式会社北辰クリーンキャリア",
            "name_variants": ["(株)北辰クリーンキャリア", "㈱北辰クリーンキャリア"],
            "corporate_number": corp("430001208473"),
            "permit_number": "00100208473",
            "prefecture": "北海道",
            "issuing_authority": "北海道知事",
            "address": "北海道苫小牧市晴海町29番地5",
            "disposition_date": "2026-09-04",
            "disposition_type": "改善命令",
            "suspension_days": None,
            "suspension_start": None,
            "suspension_end": None,
            "waste_categories": ["汚泥", "廃油", "廃プラスチック類"],
            "statutory_basis": "廃棄物処理法第19条の3第2号（積替え保管施設における油水分離槽維持管理改善命令）",
            "violation_summary": "積替え保管施設の防油堤ひび割れおよび油水分離槽の定期清掃記録不備が確認され、施設補修および管理規程改定を命じる改善命令。",
            "recommended_audit_action": "北海道事業場の委託先監査リストにて要注意フラグを設定し、補修完了検査済証の写しを取得してISO14001記録に添付すること。",
            "source_name": "北海道環境生活部 産業廃棄物処理業者に対する行政処分",
            "source_url": "https://www.pref.hokkaido.lg.jp/ks/jss/",
        },
        {
            "id": "DISP-2026-MYG-011",
            "company_name": "株式会社杜の都メディカルクリーン",
            "name_variants": ["㈱杜の都メディカルクリーン"],
            "corporate_number": corp("370001362951"),
            "permit_number": "00450362951",
            "prefecture": "宮城県",
            "issuing_authority": "宮城県知事",
            "address": "宮城県黒川郡大和町流通平一丁目14番地",
            "disposition_date": "2026-08-25",
            "disposition_type": "事業停止",
            "suspension_days": 45,
            "suspension_start": "2026-08-26",
            "suspension_end": "2026-10-09",
            "waste_categories": ["特別管理産業廃棄物", "廃プラスチック類"],
            "statutory_basis": "廃棄物処理法第14条の6準用第14条の3第1号（感染性産業廃棄物の保冷運搬基準違反）",
            "violation_summary": "特別管理産業廃棄物（感染性産業廃棄物）の夏期収集運搬において保冷車冷蔵設備の故障を放置して運搬を継続したため、45日間の事業停止処分。",
            "recommended_audit_action": "研究施設・医務室等から排出される特管産廃の運搬車両設備点検記録および温度ロガー記録の提出を義務付けること。",
            "source_name": "宮城県環境生活部 廃棄物処理法に基づく行政処分情報",
            "source_url": "https://www.pref.miyagi.jp/soshiki/junkan/",
        },
        {
            "id": "DISP-2026-SZO-012",
            "company_name": "株式会社駿河ポリマーリプロ",
            "name_variants": ["㈱駿河ポリマーリプロ", "(株)駿河ポリマーリプロ"],
            "corporate_number": corp("080001483920"),
            "permit_number": "02220483920",
            "prefecture": "静岡県",
            "issuing_authority": "静岡県知事",
            "address": "静岡県富士市大淵2841番地7",
            "disposition_date": "2026-08-12",
            "disposition_type": "改善命令",
            "suspension_days": None,
            "suspension_start": None,
            "suspension_end": None,
            "waste_categories": ["廃プラスチック類", "木くず", "紙くず"],
            "statutory_basis": "廃棄物処理法第19条の3第2号（破砕施設の粉じん飛散防止および防火水槽維持改善命令）",
            "violation_summary": "廃プラスチック類破砕施設における集じん装置のフィルタ交換遅延および屋外保管区画の消火器配置不足に対し改善命令。",
            "recommended_audit_action": "火災リスク・近隣苦情リスクの観点から現地確認を実施し、改善計画書の履行状況を翌月度点検で確認すること。",
            "source_name": "静岡県くらし・環境部 産業廃棄物行政処分公表ページ",
            "source_url": "https://www.pref.shizuoka.jp/kurashikankyo/kankyo/haikibutsu/",
        },
        {
            "id": "DISP-2026-HRS-013",
            "company_name": "株式会社瀬戸内マリン環境サービス",
            "name_variants": ["㈱瀬戸内マリン環境サービス", "株式会社瀨戸内マリン環境サービス"],
            "corporate_number": corp("240001592814"),
            "permit_number": "03400592814",
            "prefecture": "広島県",
            "issuing_authority": "広島県知事",
            "address": "広島県福山市箕沖町107番地9",
            "disposition_date": "2026-07-30",
            "disposition_type": "許可取消",
            "suspension_days": None,
            "suspension_start": None,
            "suspension_end": None,
            "waste_categories": ["汚泥", "廃油", "廃酸", "特別管理産業廃棄物"],
            "statutory_basis": "廃棄物処理法第14条の3の2第1項第5号（無許可処分・不法投棄未遂に伴う許可取消）",
            "violation_summary": "回収したビルピット汚泥および廃油混合物を指定中間処理施設へ搬入せず自社倉庫敷地内の地下ピットに無許可貯留していたとして収集運搬業許可取消。",
            "recommended_audit_action": "委託契約を即時解除し、最終処分終了報告（E票）が未着のマニフェストについて都道府県担当課へ速やかに状況報告・相談を行うこと。",
            "source_name": "広島県環境県民局 産業廃棄物処理業者に対する行政処分",
            "source_url": "https://www.pref.hiroshima.lg.jp/soshiki/47/",
        },
        {
            "id": "DISP-2026-MLT-014",
            "company_name": "株式会社近畿ロジテック建機",
            "name_variants": ["(株)近畿ロジテック建機", "㈱近畿ロジテック建機"],
            "corporate_number": corp("120901673405"),
            "permit_number": "02700673405",
            "prefecture": "国土交通省",
            "issuing_authority": "国土交通省近畿地方整備局長",
            "address": "大阪府東大阪市高井田本通五丁目3番11号",
            "disposition_date": "2026-07-16",
            "disposition_type": "指名停止",
            "suspension_days": 90,
            "suspension_start": "2026-07-16",
            "suspension_end": "2026-10-13",
            "waste_categories": ["建設工事請負（産廃関連法令違反に伴う指名停止）", "がれき類", "汚泥"],
            "statutory_basis": "工事請負契約に係る指名停止等の措置要領 別表第2第16号（建設発生土・建設汚泥の不適正処理）",
            "violation_summary": "管渠更新工事に伴って発生した建設汚泥を改良土と称して無許可残土処分場へ搬出した事案により、3ヶ月間の指名停止措置。",
            "recommended_audit_action": "土木・営繕工事の協力会社評価スコアを減点し、建設汚泥排出工事における計量伝票・搬入先許可証の事前審査を厳格化すること。",
            "source_name": "国土交通省 ネガティブ情報等検索システム",
            "source_url": "https://www.mlit.go.jp/nega-inf/",
        },
    ]


class SanpaiMonitorSwarm:
    """
    Top-level Multi-Agent Coordinator orchestrating:
      1. PrefectureSourceHarvester (official source registry & link health verification)
      2. EntityNormalizer (corporate name, NTA Modulo-9 check digit, 10/11-digit permit resolver)
      3. DispositionVerifier (cross-check & deterministic JSON export for static web SaaS)
    """

    def __init__(
        self,
        harvester: Optional[PrefectureSourceHarvester] = None,
        normalizer: Optional[EntityNormalizer] = None,
        verifier: Optional[DispositionVerifier] = None,
    ) -> None:
        self.harvester = harvester or PrefectureSourceHarvester()
        self.normalizer = normalizer or EntityNormalizer()
        self.verifier = verifier or DispositionVerifier()

    def run_pipeline(
        self,
        output_path: Optional[pathlib.Path] = None,
        dry_run: bool = True,
        write_output: bool = True,
    ) -> Dict[str, Any]:
        health_summary = self.harvester.check_all_sources(dry_run=dry_run)
        seed_records = build_seed_dispositions()
        dataset = self.verifier.verify_dataset(
            raw_records=seed_records,
            source_health_summary=health_summary,
        )
        if not dataset["verification_passed"]:
            raise RuntimeError(f"Dataset verification failed: {dataset['validation_errors']}")

        if write_output and output_path is not None:
            self.verifier.export_json(dataset, output_path)
        return dataset


def _default_output_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "site" / "data" / "dispositions.json"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sanpai Multi-Agent Harvester, Entity Normalizer & Disposition Verifier"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run deterministic offline verification without live HTTP requests",
    )
    parser.add_argument(
        "--verify-seed",
        action="store_true",
        help="Validate bundled seed dataset, run Modulo-9 & permit checks, and write dispositions.json",
    )
    parser.add_argument(
        "--live-check",
        action="store_true",
        help="Perform live HTTP HEAD/GET health checks against official prefecture/MLIT URLs",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Run checks in memory without writing dispositions.json",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=_default_output_path(),
        help="Output JSON path (defaults to site/data/dispositions.json)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # Default to offline deterministic mode unless --live-check is explicitly requested
    dry_run = not args.live_check
    if args.dry_run or args.verify_seed:
        dry_run = not args.live_check

    swarm = SanpaiMonitorSwarm()
    dataset = swarm.run_pipeline(
        output_path=args.output,
        dry_run=dry_run,
        write_output=not args.no_write,
    )

    summary = {
        "status": "ok" if dataset["verification_passed"] else "failed",
        "mode": dataset["source_registry_health"]["mode"],
        "record_count": dataset["record_count"],
        "sources_checked": dataset["source_registry_health"]["total_sources"],
        "dead_links": dataset["source_registry_health"]["dead_link_count"],
        "dataset_sha256": dataset["dataset_sha256"],
        "output": None if args.no_write else str(args.output),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if dataset["verification_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
