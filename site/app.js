/* global window, document, fetch, Blob, URL, TextDecoder, TextEncoder, crypto */
(function () {
  "use strict";

  const SANPAI_APP_CONFIG = {
    appName: "Sanpai Compliance Watch",
    proPlanMonthlyYen: 4980,
    dataJsonUrl: "./data/dispositions.json",
    // Stage-2 monetization switch: set Stripe Payment Link URL once waitlist >= 5 leads
    stripePaymentLinkUrl: "",
    // Optional Formspree / Google Apps Script webhook URL for Stage-1 waitlist collection
    waitlistWebhookUrl: "",
    storageKeyWaitlist: "sanpai_monitor_pro_waitlist_v1"
  };

  const KYUJITAI_MAP = {
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
    "驛": "駅"
  };

  const AUTHORITY_CODE_MAP = {
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
    "077": "福岡市"
  };

  const PERMIT_CATEGORY_MAP = {
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
    "80": "特別管理産業廃棄物処分業（最終処分）"
  };

  // Sample 8-contractor CSV demonstrating every real-world ISO14001 audit detection pattern
  const SAMPLE_CONTRACTOR_CSV = [
    "委託先名称,法人番号,許可番号,委託業務区分,排出事業場",
    "株式会社東都エコトランスポート,3010001184920,01300184921,収集運搬（廃プラ・木くず）,東京本社ビル",
    "㈱髙橋環境開發,,014-00-371642,収集運搬（がれき類・廃プラ）,厚木物流センター",
    "株式会社関東グリーンマテリアル（神奈川営業所）,,01400294815,収集運搬（汚泥・廃油）,神奈川第一製造所",
    "株式会社中京スラッジ興業,8180001632741,02320632741,中間処理（脱水汚泥）,東海サテライト工場",
    "(株)齋藤總合解体工業,8010401745218,第1300745218号,建屋改修・がれき類収集運搬,足立倉庫",
    "株式会社北関東マテリアル運輸,9030001734567,01100654321,収集運搬（金属くず）,埼玉パーツセンター",
    "株式会社京浜エコシステムズ,5020001812345,01400812345,収集運搬・中間処理（廃プラ）,神奈川第一製造所",
    "株式会社多摩グリーンロジスティクス,7012401923456,01300923456,収集運搬（金属くず・廃プラ）,東京本社ビル"
  ].join("\r\n");

  const CSV_TEMPLATE_CONTENT = [
    "委託先名称,法人番号,許可番号,委託業務区分,排出事業場",
    "株式会社京浜エコシステムズ,5020001812345,01400812345,産業廃棄物収集運搬（廃プラスチック類）,神奈川第一製造所",
    "株式会社多摩グリーンロジスティクス,7012401923456,01300923456,産業廃棄物収集運搬（金属くず）,本社工場"
  ].join("\r\n");

  // Offline fallback dataset (used only if fetch('./data/dispositions.json') is blocked by file:// protocol)
  const BUNDLED_FALLBACK_DATASET = {
    schema_version: "2.0.0",
    generated_at: "2026-11-26T07:00:00+09:00",
    dataset_sha256: "1306429aaf0ae021875bbfbb120b226ea4f908ecc0632e0865ba342745098924",
    record_count: 7,
    source_registry_health: {
      total_sources: 14,
      healthy_count: 14,
      dead_link_count: 0,
      sources: [
        {
          source_id: "mlit-nega-inf",
          jurisdiction: "国土交通省",
          name: "国土交通省 ネガティブ情報等検索システム",
          url: "https://www.mlit.go.jp/nega-inf/",
          status: "healthy"
        },
        {
          source_id: "tokyo-kankyo",
          jurisdiction: "東京都",
          name: "東京都環境局 産業廃棄物処理業者に対する行政処分",
          url: "https://www.kankyo.metro.tokyo.lg.jp/resource/industrial_waste/improper_handling/disposition",
          status: "healthy"
        },
        {
          source_id: "kanagawa-waste",
          jurisdiction: "神奈川県",
          name: "神奈川県環境農政局 廃棄物処理法に基づく行政処分",
          url: "https://www.pref.kanagawa.jp/docs/p3k/cnt/f531144/",
          status: "healthy"
        },
        {
          source_id: "chiba-waste",
          jurisdiction: "千葉県",
          name: "千葉県環境生活部 廃棄物処理法に基づく行政処分",
          url: "https://www.pref.chiba.lg.jp/haishi/gyouseishobun/",
          status: "healthy"
        }
      ]
    },
    dispositions: [
      {
        id: "DISP-2026-TKY-001",
        company_name: "株式会社東都エコトランスポート",
        normalized_name: "株式会社東都エコトランスポート",
        normalized_variants: ["株式会社東都エコトランスポート"],
        corporate_number: "3010001184920",
        permit_number: "01300184921",
        permit_formatted: "第01300184921号",
        operator_unique_id: "184921",
        prefecture: "東京都",
        issuing_authority: "東京都知事",
        disposition_date: "2026-11-18",
        disposition_type: "許可取消",
        suspension_days: null,
        waste_categories: ["廃プラスチック類", "木くず", "金属くず", "がれき類"],
        statutory_basis: "廃棄物処理法第14条の3の2第1項第4号（再委託禁止違反・虚偽マニフェスト交付）",
        violation_summary: "書面承諾を得ずに無許可業者へ廃プラスチック類を再委託し虚偽報告を行ったため収集運搬業許可取消。",
        recommended_audit_action: "直ちに収集運搬委託契約を停止し、代替許可業者への切替および過去1年分の最終処分完了確認を実施すること。",
        source_name: "東京都環境局 産業廃棄物処理業者に対する行政処分一覧",
        source_url: "https://www.kankyo.metro.tokyo.lg.jp/resource/industrial_waste/improper_handling/disposition"
      },
      {
        id: "DISP-2026-CHB-002",
        company_name: "株式会社関東グリーンマテリアル",
        normalized_name: "株式会社関東グリーンマテリアル",
        normalized_variants: ["株式会社関東グリーンマテリアル"],
        corporate_number: "4040001294815",
        permit_number: "01220294815",
        permit_formatted: "第01220294815号",
        operator_unique_id: "294815",
        prefecture: "千葉県",
        issuing_authority: "千葉県知事",
        disposition_date: "2026-11-12",
        disposition_type: "許可取消",
        suspension_days: null,
        waste_categories: ["汚泥", "廃プラスチック類", "廃油", "廃アルカリ"],
        statutory_basis: "廃棄物処理法第14条の3の2第1項第5号（改善命令違反・保管基準超過継続）",
        violation_summary: "中間処理施設の保管上限超過に対する改善命令違反により産業廃棄物処分業許可取消（固有番号294815・他県連鎖対象）。",
        recommended_audit_action: "他都県の同一固有番号「294815」許可も欠格連鎖取消対象となるため全拠点の委託を即時停止すること。",
        source_name: "千葉県環境生活部 廃棄物処理法に基づく行政処分",
        source_url: "https://www.pref.chiba.lg.jp/haishi/gyouseishobun/"
      },
      {
        id: "DISP-2026-KNG-003",
        company_name: "株式会社高橋環境開発",
        normalized_name: "株式会社高橋環境開発",
        normalized_variants: ["株式会社高橋環境開発"],
        corporate_number: "2020001371642",
        permit_number: "01400371642",
        permit_formatted: "第01400371642号",
        operator_unique_id: "371642",
        prefecture: "神奈川県",
        issuing_authority: "神奈川県知事",
        disposition_date: "2026-11-05",
        disposition_type: "事業停止",
        suspension_days: 60,
        suspension_start: "2026-11-06",
        suspension_end: "2027-01-04",
        waste_categories: ["がれき類", "ガラスくず・コンクリートくず及び陶磁器くず", "廃プラスチック類"],
        statutory_basis: "廃棄物処理法第14条の3第1号（無許可積替え保管基準違反）",
        violation_summary: "許可を受けない土場での積替え保管により60日間の事業全部停止処分。",
        recommended_audit_action: "事業停止期間中の引渡しを即時停止し、予備委託先へ振り替えること。",
        source_name: "神奈川県環境農政局 廃棄物処理法に基づく行政処分",
        source_url: "https://www.pref.kanagawa.jp/docs/p3k/cnt/f531144/"
      },
      {
        id: "DISP-2026-AIC-006",
        company_name: "株式会社中京スラッジ興業",
        normalized_name: "株式会社中京スラッジ興業",
        normalized_variants: ["株式会社中京スラッジ興業"],
        corporate_number: "8180001632741",
        permit_number: "02320632741",
        permit_formatted: "第02320632741号",
        operator_unique_id: "632741",
        prefecture: "愛知県",
        issuing_authority: "愛知県知事",
        disposition_date: "2026-10-14",
        disposition_type: "改善命令",
        suspension_days: null,
        waste_categories: ["汚泥", "ばいじん", "燃え殻"],
        statutory_basis: "廃棄物処理法第19条の3第2号（処理基準不適合に対する改善命令）",
        violation_summary: "脱水汚泥屋内保管ピットの最大保管高さ超過に対する改善命令。",
        recommended_audit_action: "現地実地確認を実施し、是正完了報告書および改善後の保管状況写真の提出を求めること。",
        source_name: "愛知県環境局 廃棄物処理法に基づく行政処分の公表",
        source_url: "https://www.pref.aichi.jp/soshiki/junkan/"
      },
      {
        id: "DISP-2026-MLT-007",
        company_name: "株式会社斎藤総合解体工業",
        normalized_name: "株式会社斎藤総合解体工業",
        normalized_variants: ["株式会社斎藤総合解体工業"],
        corporate_number: "8010401745218",
        permit_number: "01300745218",
        permit_formatted: "第01300745218号",
        operator_unique_id: "745218",
        prefecture: "国土交通省",
        issuing_authority: "国土交通省関東地方整備局長",
        disposition_date: "2026-10-09",
        disposition_type: "指名停止",
        suspension_days: 120,
        suspension_start: "2026-10-09",
        suspension_end: "2027-02-05",
        waste_categories: ["建設工事請負（産廃関連法令違反に伴う指名停止）", "がれき類", "木くず"],
        statutory_basis: "工事請負契約に係る指名停止等の措置要領 別表第2第15号",
        violation_summary: "建設リサイクル法・廃棄物処理法違反により4ヶ月間の指名停止措置。",
        recommended_audit_action: "設備改修・解体工事の発注先リストと照合し、新規発注審査でコンプライアンス再審査を実施すること。",
        source_name: "国土交通省 ネガティブ情報等検索システム",
        source_url: "https://www.mlit.go.jp/nega-inf/"
      }
    ]
  };

  let activeDataset = BUNDLED_FALLBACK_DATASET;
  let latestAuditResults = [];

  /* =========================================================================
   * Entity Normalizer & Check-Digit Algorithms (100% Client-Side Mirror)
   * ========================================================================= */

  function normalizeCorporateName(rawName) {
    if (!rawName) {
      return "";
    }
    let text = String(rawName).trim();
    text = text.replace(/㈱/g, "株式会社").replace(/㈲/g, "有限会社");
    text = text.normalize("NFKC");
    text = text
      .replace(/\(株\)|\[株\]|㈱/g, "株式会社")
      .replace(/\(有\)|\[有\]|㈲/g, "有限会社")
      .replace(/\(合\)|\[合\]/g, "合同会社")
      .replace(/\(資\)|\[資\]|㈾/g, "合資会社")
      .replace(/\(名\)|\[名\]|㈴/g, "合名会社")
      .replace(/\(一社\)/g, "一般社団法人")
      .replace(/\(公社\)/g, "公益社団法人")
      .replace(/\(一財\)/g, "一般財団法人")
      .replace(/\(公財\)/g, "公益財団法人");

    let converted = "";
    for (const ch of text) {
      converted += Object.prototype.hasOwnProperty.call(KYUJITAI_MAP, ch) ? KYUJITAI_MAP[ch] : ch;
    }
    return converted.toUpperCase().replace(/[\s\u3000・･]+/g, "");
  }

  function stripBranchAnnotation(normalizedName) {
    if (!normalizedName) {
      return "";
    }
    return normalizedName.replace(/\([^)]*(営業所|支店|工場|事業所|センター|出張所)\)$/g, "");
  }

  function calculateCorporateCheckDigit(base12Digits) {
    let weightedSum = 0;
    for (let posFromRight = 1; posFromRight <= 12; posFromRight += 1) {
      const charIdx = 12 - posFromRight;
      const digit = Number(base12Digits.charAt(charIdx));
      const weight = posFromRight % 2 === 1 ? 1 : 2;
      weightedSum += digit * weight;
    }
    return 9 - (weightedSum % 9);
  }

  function validateCorporateNumber(rawCorpNum) {
    if (rawCorpNum === null || rawCorpNum === undefined || String(rawCorpNum).trim() === "") {
      return {
        raw: rawCorpNum || "",
        normalized: "",
        isEmpty: true,
        isValid: false,
        expectedCheckDigit: null,
        actualCheckDigit: null,
        error: "未入力（商号・許可番号で名寄せ照合）"
      };
    }

    const normalized = String(rawCorpNum)
      .trim()
      .normalize("NFKC")
      .replace(/[\s\u3000\-ー－]/g, "");

    if (!/^\d+$/.test(normalized)) {
      return {
        raw: rawCorpNum,
        normalized: normalized,
        isEmpty: false,
        isValid: false,
        expectedCheckDigit: null,
        actualCheckDigit: null,
        error: "数字以外の文字が含まれています"
      };
    }

    if (normalized.length !== 13) {
      return {
        raw: rawCorpNum,
        normalized: normalized,
        isEmpty: false,
        isValid: false,
        expectedCheckDigit: null,
        actualCheckDigit: null,
        error: "桁数不備（" + normalized.length + "桁 / 13桁必須）"
      };
    }

    const actualCheck = Number(normalized.charAt(0));
    const base12 = normalized.slice(1);
    const expectedCheck = calculateCorporateCheckDigit(base12);

    if (actualCheck === 0) {
      return {
        raw: rawCorpNum,
        normalized: normalized,
        isEmpty: false,
        isValid: false,
        expectedCheckDigit: expectedCheck,
        actualCheckDigit: 0,
        error: "先頭桁に0は不可（Modulo-9算出値: " + expectedCheck + "）"
      };
    }

    const isValid = actualCheck === expectedCheck;
    return {
      raw: rawCorpNum,
      normalized: normalized,
      isEmpty: false,
      isValid: isValid,
      expectedCheckDigit: expectedCheck,
      actualCheckDigit: actualCheck,
      base12: base12,
      error: isValid
        ? null
        : "Modulo-9不一致（先頭桁:" + actualCheck + " → 正しい算出値:" + expectedCheck + "）"
    };
  }

  function normalizePermitNumber(rawPermit) {
    if (rawPermit === null || rawPermit === undefined || String(rawPermit).trim() === "") {
      return {
        raw: rawPermit || "",
        normalized: "",
        isEmpty: true,
        isValid: false,
        error: "未入力"
      };
    }

    let cleaned = String(rawPermit).trim().normalize("NFKC");
    cleaned = cleaned
      .replace(/^(産業廃棄物|特別管理産業廃棄物|収集運搬|処分業|許可番号|第|:|：|\s)+/g, "")
      .replace(/(号|\s)+$/g, "");
    let digits = cleaned.replace(/[\s\-ー－]/g, "");

    if (!/^\d+$/.test(digits)) {
      return {
        raw: rawPermit,
        normalized: digits,
        isEmpty: false,
        isValid: false,
        error: "許可番号に数字以外の文字が含まれています"
      };
    }

    let was10Digit = false;
    if (digits.length === 10) {
      const pref2 = Number(digits.slice(0, 2));
      if (pref2 >= 1 && pref2 <= 99) {
        digits = "0" + digits;
        was10Digit = true;
      } else {
        return {
          raw: rawPermit,
          normalized: digits,
          isEmpty: false,
          isValid: false,
          error: "10桁許可番号の自治体コード部分が範囲外です"
        };
      }
    } else if (digits.length !== 11) {
      return {
        raw: rawPermit,
        normalized: digits,
        isEmpty: false,
        isValid: false,
        error: "桁数不備（" + digits.length + "桁 / 10〜11桁必須）"
      };
    }

    const authorityCode = digits.slice(0, 3);
    const categoryCode = digits.slice(3, 5);
    const operatorUniqueId = digits.slice(5, 11);
    const authorityNum = Number(authorityCode);
    if (authorityNum < 1 || authorityNum > 150) {
      return {
        raw: rawPermit,
        normalized: digits,
        isEmpty: false,
        isValid: false,
        error: "自治体コード範囲外（" + authorityCode + "）"
      };
    }

    return {
      raw: rawPermit,
      normalized: digits,
      formatted: "第" + digits + "号",
      isEmpty: false,
      isValid: true,
      was10Digit: was10Digit,
      authorityCode: authorityCode,
      authorityName: AUTHORITY_CODE_MAP[authorityCode] || "自治体コード:" + authorityCode,
      categoryCode: categoryCode,
      categoryLabel: PERMIT_CATEGORY_MAP[categoryCode] || "産業廃棄物処理業",
      operatorUniqueId: operatorUniqueId,
      error: null
    };
  }

  /* =========================================================================
   * HTML Escape & Cryptographic SHA-256 Helper
   * ========================================================================= */

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function computeSha256Hex(message) {
    if (window.crypto && window.crypto.subtle && typeof TextEncoder !== "undefined") {
      try {
        const bytes = new TextEncoder().encode(message);
        const digestBuffer = await crypto.subtle.digest("SHA-256", bytes);
        const hashArray = Array.from(new Uint8Array(digestBuffer));
        return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
      } catch (_err) {
        // Fallback for restricted contexts
      }
    }
    // Deterministic 64-char hex fallback if WebCrypto is unavailable under file://
    let h1 = 0xdeadbeef ^ message.length;
    let h2 = 0x41c6ce57 ^ message.length;
    for (let i = 0; i < message.length; i += 1) {
      const ch = message.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    const base =
      (h1 >>> 0).toString(16).padStart(8, "0") +
      (h2 >>> 0).toString(16).padStart(8, "0");
    return base.repeat(4);
  }

  /* =========================================================================
   * CSV Parsing & Encoding Auto-Detection (UTF-8 / Shift_JIS)
   * ========================================================================= */

  function decodeCsvBuffer(arrayBuffer) {
    const uint8 = new Uint8Array(arrayBuffer);
    if (uint8.length >= 3 && uint8[0] === 0xef && uint8[1] === 0xbb && uint8[2] === 0xbf) {
      return new TextDecoder("utf-8").decode(uint8.subarray(3));
    }
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(uint8);
    } catch (_utf8Error) {
      return new TextDecoder("shift_jis").decode(uint8);
    }
  }

  function parseCsvRows(csvText) {
    const rows = [];
    let currentRow = [];
    let currentCell = "";
    let insideQuotes = false;
    const text = csvText.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const firstLine = text.split("\n")[0] || "";
    const delimiter = firstLine.indexOf("\t") >= 0 && firstLine.indexOf(",") < 0 ? "\t" : ",";

    for (let i = 0; i < text.length; i += 1) {
      const ch = text[i];
      const next = text[i + 1];
      if (insideQuotes) {
        if (ch === '"' && next === '"') {
          currentCell += '"';
          i += 1;
        } else if (ch === '"') {
          insideQuotes = false;
        } else {
          currentCell += ch;
        }
      } else if (ch === '"') {
        insideQuotes = true;
      } else if (ch === delimiter) {
        currentRow.push(currentCell.trim());
        currentCell = "";
      } else if (ch === "\n") {
        currentRow.push(currentCell.trim());
        if (currentRow.some((c) => c !== "")) {
          rows.push(currentRow);
        }
        currentRow = [];
        currentCell = "";
      } else {
        currentCell += ch;
      }
    }
    currentRow.push(currentCell.trim());
    if (currentRow.some((c) => c !== "")) {
      rows.push(currentRow);
    }
    return rows;
  }

  function mapContractorColumns(rows) {
    if (!rows.length) {
      return [];
    }
    const header = rows[0].map((h) => h.normalize("NFKC").toLowerCase());
    const findCol = (patterns, fallbackIdx) => {
      const found = header.findIndex((col) => patterns.some((p) => col.includes(p)));
      return found >= 0 ? found : fallbackIdx;
    };

    const hasHeader = header.some((col) =>
      ["名称", "会社", "商号", "業者", "委託先", "法人番号", "許可番号", "name", "permit"].some((kw) =>
        col.includes(kw)
      )
    );

    const nameIdx = hasHeader ? findCol(["委託先", "名称", "会社", "商号", "業者", "name"], 0) : 0;
    const corpIdx = hasHeader ? findCol(["法人番号", "corporate", "corp"], 1) : 1;
    const permitIdx = hasHeader ? findCol(["許可番号", "産廃許可", "permit", "license"], 2) : 2;
    const scopeIdx = hasHeader ? findCol(["区分", "業務", "品目", "業種", "scope"], 3) : 3;
    const siteIdx = hasHeader ? findCol(["事業場", "工場", "拠点", "部署", "site"], 4) : 4;

    const dataRows = hasHeader ? rows.slice(1) : rows;
    return dataRows.map((cols, index) => ({
      rowNumber: index + 1,
      companyName: cols[nameIdx] || "",
      corporateNumber: cols[corpIdx] || "",
      permitNumber: cols[permitIdx] || "",
      serviceScope: cols[scopeIdx] || "",
      emitterSite: cols[siteIdx] || ""
    }));
  }

  /* =========================================================================
   * Multi-Layer ISO14001 Contractor Audit Engine
   * ========================================================================= */

  function runContractorBatchAudit(contractors, dispositions) {
    return contractors.map((contractor) => {
      const normName = normalizeCorporateName(contractor.companyName);
      const coreNormName = stripBranchAnnotation(normName);
      const corpCheck = validateCorporateNumber(contractor.corporateNumber);
      const permitCheck = normalizePermitNumber(contractor.permitNumber);

      const directMatches = [];
      const chainOperatorMatches = [];

      for (const disp of dispositions) {
        const dispNormName = disp.normalized_name || normalizeCorporateName(disp.company_name);
        const dispVariants = disp.normalized_variants || [];

        const matchedByCorp =
          corpCheck.isValid &&
          disp.corporate_number &&
          corpCheck.normalized === disp.corporate_number;

        const matchedByPermit =
          permitCheck.isValid &&
          disp.permit_number &&
          permitCheck.normalized === disp.permit_number;

        const matchedByExactName =
          normName !== "" &&
          (normName === dispNormName || dispVariants.includes(normName));

        const matchedByCoreBranchName =
          !matchedByExactName &&
          coreNormName !== "" &&
          coreNormName !== normName &&
          (coreNormName === dispNormName || dispVariants.includes(coreNormName));

        const matchedByOperatorIdOnly =
          !matchedByPermit &&
          permitCheck.isValid &&
          permitCheck.operatorUniqueId &&
          disp.operator_unique_id &&
          permitCheck.operatorUniqueId === disp.operator_unique_id;

        if (matchedByCorp || matchedByPermit || matchedByExactName) {
          const reasons = [];
          if (matchedByCorp) reasons.push("13桁法人番号一致");
          if (matchedByPermit) reasons.push("11桁許可番号一致");
          if (matchedByExactName) reasons.push("正規化商号名寄せ一致");
          directMatches.push({ disposition: disp, reasons: reasons });
        } else if (matchedByOperatorIdOnly || matchedByCoreBranchName) {
          const chainReasons = [];
          if (matchedByOperatorIdOnly) {
            chainReasons.push(
              "全国共通6桁固有番号（" +
                permitCheck.operatorUniqueId +
                "）が" +
                disp.prefecture +
                "の処分業者と一致"
            );
          }
          if (matchedByCoreBranchName) {
            chainReasons.push("本店・系列商号一致");
          }
          chainOperatorMatches.push({ disposition: disp, reasons: chainReasons });
        }
      }

      let judgmentLevel = "clean";
      let judgmentLabel = "適格（処分該当なし）";
      let badgeClass = "badge-ok";
      let findingsSummary = "";
      let primarySourceUrl = "";
      let primarySourceName = "";

      if (directMatches.length > 0) {
        const top = directMatches[0].disposition;
        const matchBasis = directMatches[0].reasons.join("・");
        primarySourceUrl = top.source_url;
        primarySourceName = top.source_name || top.prefecture + "公式公表";
        if (top.disposition_type === "許可取消" || top.disposition_type === "事業停止") {
          judgmentLevel = "critical";
          judgmentLabel = "要緊急是正（" + top.disposition_type + "）";
          badgeClass = "badge-critical";
        } else {
          judgmentLevel = "warn";
          judgmentLabel = "要注意（" + top.disposition_type + "）";
          badgeClass = "badge-medium";
        }
        findingsSummary =
          "【" +
          top.prefecture +
          "・" +
          top.disposition_date +
          " " +
          top.disposition_type +
          "】（照合根拠: " +
          matchBasis +
          "）" +
          top.recommended_audit_action;
      } else if (chainOperatorMatches.length > 0) {
        const chainTop = chainOperatorMatches[0].disposition;
        primarySourceUrl = chainTop.source_url;
        primarySourceName = chainTop.source_name || chainTop.prefecture + "公式公表";
        judgmentLevel = "warn";
        judgmentLabel = "他県連鎖リスク警告";
        badgeClass = "badge-high";
        findingsSummary =
          "【欠格連鎖要確認：" +
          chainOperatorMatches[0].reasons.join("・") +
          "】" +
          chainTop.prefecture +
          "にて「" +
          chainTop.disposition_type +
          "（" +
          chainTop.disposition_date +
          "）」公表あり。廃棄物処理法の欠格要件連鎖により当該許可も取消となるおそれがあるため緊急確認を実施してください。";
      } else if ((!corpCheck.isEmpty && !corpCheck.isValid) || (!permitCheck.isEmpty && !permitCheck.isValid)) {
        judgmentLevel = "format_error";
        judgmentLabel = "マスタ番号要修正";
        badgeClass = "badge-medium";
        const errParts = [];
        if (!corpCheck.isEmpty && !corpCheck.isValid) {
          errParts.push("法人番号不備: " + corpCheck.error);
        }
        if (!permitCheck.isEmpty && !permitCheck.isValid) {
          errParts.push("許可番号不備: " + permitCheck.error);
        }
        findingsSummary =
          errParts.join(" ／ ") +
          "（※収録行政処分データとの商号照合では該当なし。委託先台帳の番号修正を推奨）";
      } else {
        findingsSummary =
          "収録14機関の行政処分公表データ（許可取消・事業停止・改善命令・指名停止）との該当なし。次回更新期限およびマニフェスト返送状況を継続監視。";
      }

      return {
        rowNumber: contractor.rowNumber,
        companyName: contractor.companyName,
        normalizedName: normName,
        serviceScope: contractor.serviceScope,
        emitterSite: contractor.emitterSite,
        corpCheck: corpCheck,
        permitCheck: permitCheck,
        judgmentLevel: judgmentLevel,
        judgmentLabel: judgmentLabel,
        badgeClass: badgeClass,
        findingsSummary: findingsSummary,
        primarySourceUrl: primarySourceUrl,
        primarySourceName: primarySourceName
      };
    });
  }

  /* =========================================================================
   * Rendering Functions
   * ========================================================================= */

  async function renderAuditCertificate(results, sourceLabel) {
    latestAuditResults = results;

    const emitterCompany = document.getElementById("meta-emitter-company").value.trim() || "未設定";
    const emitterSite = document.getElementById("meta-emitter-site").value.trim() || "全事業場";
    const auditorName = document.getElementById("meta-auditor-name").value.trim() || "担当者未記入";
    const auditPeriod = document.getElementById("meta-audit-period").value.trim() || "定期点検";

    const now = new Date();
    const ymd =
      now.getFullYear().toString() +
      String(now.getMonth() + 1).padStart(2, "0") +
      String(now.getDate()).padStart(2, "0");
    const hm =
      String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0");

    document.getElementById("cert-emitter-company").textContent = emitterCompany;
    document.getElementById("cert-emitter-site").textContent = emitterSite;
    document.getElementById("cert-auditor-name").textContent = auditorName;
    document.getElementById("cert-audit-datetime").textContent =
      auditPeriod + "（" + ymd.slice(0, 4) + "-" + ymd.slice(4, 6) + "-" + ymd.slice(6, 8) + " " + hm + "）";

    if (sourceLabel) {
      document.getElementById("audit-toolbar-status").textContent = sourceLabel;
    }

    let criticalCount = 0;
    let warnCount = 0;
    let formatErrCount = 0;
    let cleanCount = 0;

    const tbody = document.getElementById("cert-table-body");
    const rowHtmlList = results.map((item) => {
      if (item.judgmentLevel === "critical") criticalCount += 1;
      else if (item.judgmentLevel === "warn") warnCount += 1;
      else if (item.judgmentLevel === "format_error") formatErrCount += 1;
      else cleanCount += 1;

      let corpHtml = "";
      if (item.corpCheck.isEmpty) {
        corpHtml = '<span style="color:#64748b;">未記載（名寄せ照合）</span>';
      } else if (item.corpCheck.isValid) {
        corpHtml =
          '<span class="mono-code">' +
          escapeHtml(item.corpCheck.normalized) +
          '</span><br><span class="badge badge-ok" style="font-size:10.5px;">Modulo-9 OK</span>';
      } else {
        corpHtml =
          '<span class="mono-code" style="color:#991b1b;">' +
          escapeHtml(item.corpCheck.raw) +
          '</span><br><span class="badge badge-critical" style="font-size:10.5px;">' +
          escapeHtml(item.corpCheck.error) +
          "</span>";
      }

      let permitHtml = "";
      if (item.permitCheck.isEmpty) {
        permitHtml = '<span style="color:#64748b;">未記載</span>';
      } else if (item.permitCheck.isValid) {
        permitHtml =
          '<span class="mono-code">' +
          escapeHtml(item.permitCheck.normalized) +
          "</span>" +
          (item.permitCheck.was10Digit ? ' <span style="font-size:10px;color:#0369a1;">(10→11桁補完)</span>' : "") +
          '<br><span style="font-size:10.5px;color:#475569;">固有番号: ' +
          escapeHtml(item.permitCheck.operatorUniqueId) +
          "</span>";
      } else {
        permitHtml =
          '<span class="mono-code" style="color:#9a3412;">' +
          escapeHtml(item.permitCheck.raw) +
          '</span><br><span class="badge badge-medium" style="font-size:10.5px;">' +
          escapeHtml(item.permitCheck.error) +
          "</span>";
      }

      const sourceLinkHtml = item.primarySourceUrl
        ? '<div style="margin-top:4px;"><a href="' +
          escapeHtml(item.primarySourceUrl) +
          '" target="_blank" rel="noopener noreferrer">' +
          escapeHtml(item.primarySourceName) +
          " ↗</a></div>"
        : "";

      const subInfo = [item.serviceScope, item.emitterSite].filter(Boolean).join(" ／ ");

      return (
        "<tr>" +
        "<td>" +
        item.rowNumber +
        "</td>" +
        "<td><strong>" +
        escapeHtml(item.companyName) +
        '</strong><br><span style="font-size:10.5px;color:#64748b;">正規化: ' +
        escapeHtml(item.normalizedName) +
        "</span>" +
        (subInfo ? '<br><span style="font-size:10.5px;color:#334155;">' + escapeHtml(subInfo) + "</span>" : "") +
        "</td>" +
        "<td>" +
        corpHtml +
        "</td>" +
        "<td>" +
        permitHtml +
        "</td>" +
        '<td><span class="badge ' +
        item.badgeClass +
        '">' +
        escapeHtml(item.judgmentLabel) +
        "</span></td>" +
        "<td>" +
        escapeHtml(item.findingsSummary) +
        sourceLinkHtml +
        "</td>" +
        "</tr>"
      );
    });

    tbody.innerHTML = rowHtmlList.join("");

    document.getElementById("cert-total-count").textContent = String(results.length);
    document.getElementById("cert-critical-count").textContent = String(criticalCount);
    document.getElementById("cert-chain-warn-count").textContent = String(warnCount);
    document.getElementById("cert-format-err-count").textContent = String(formatErrCount);
    document.getElementById("cert-clean-count").textContent = String(cleanCount);

    const dbHash = activeDataset.dataset_sha256 || "seed";
    document.getElementById("cert-db-hash").textContent = dbHash.slice(0, 24) + "...";

    const canonicalAuditPayload = JSON.stringify({
      emitterCompany: emitterCompany,
      emitterSite: emitterSite,
      auditPeriod: auditPeriod,
      auditorName: auditorName,
      dbHash: dbHash,
      rows: results.map((r) => ({
        n: r.normalizedName,
        c: r.corpCheck.normalized,
        p: r.permitCheck.normalized,
        j: r.judgmentLevel
      }))
    });
    const fullAuditHash = await computeSha256Hex(canonicalAuditPayload);
    document.getElementById("cert-audit-hash").textContent = fullAuditHash.slice(0, 32);
    document.getElementById("cert-doc-id").textContent =
      "EMS-SANPAI-" + ymd + "-" + fullAuditHash.slice(0, 6).toUpperCase();
  }

  function populateFilterDropdowns(dispositions) {
    const prefSelect = document.getElementById("filter-prefecture");
    const wasteSelect = document.getElementById("filter-waste");

    const prefectures = Array.from(new Set(dispositions.map((d) => d.prefecture).filter(Boolean))).sort();
    prefSelect.innerHTML =
      '<option value="">すべての自治体・機関（' +
      prefectures.length +
      "）</option>" +
      prefectures
        .map((p) => '<option value="' + escapeHtml(p) + '">' + escapeHtml(p) + "</option>")
        .join("");

    const wastes = Array.from(
      new Set(dispositions.flatMap((d) => d.waste_categories || []).filter(Boolean))
    ).sort();
    wasteSelect.innerHTML =
      '<option value="">すべての品目（' +
      wastes.length +
      "）</option>" +
      wastes
        .map((w) => '<option value="' + escapeHtml(w) + '">' + escapeHtml(w) + "</option>")
        .join("");
  }

  function renderDispositionTable() {
    const keywordRaw = document.getElementById("search-keyword").value.trim();
    const normKeyword = normalizeCorporateName(keywordRaw);
    const digitsKeyword = keywordRaw.normalize("NFKC").replace(/[\s\-ー－第号]/g, "");
    const selectedPref = document.getElementById("filter-prefecture").value;
    const selectedType = document.getElementById("filter-type").value;
    const selectedWaste = document.getElementById("filter-waste").value;

    const dispositions = activeDataset.dispositions || [];
    const filtered = dispositions.filter((rec) => {
      if (selectedPref && rec.prefecture !== selectedPref) return false;
      if (selectedType && rec.disposition_type !== selectedType) return false;
      if (selectedWaste && !(rec.waste_categories || []).includes(selectedWaste)) return false;

      if (keywordRaw !== "") {
        const hayName = rec.normalized_name || normalizeCorporateName(rec.company_name);
        const hayVariants = (rec.normalized_variants || []).join(" ");
        const rawCombined = [
          rec.company_name,
          rec.corporate_number,
          rec.permit_number,
          rec.operator_unique_id,
          rec.prefecture,
          rec.violation_summary,
          rec.statutory_basis,
          (rec.waste_categories || []).join(" ")
        ]
          .join(" ")
          .normalize("NFKC")
          .toUpperCase();

        const matchesNormName = normKeyword && (hayName.includes(normKeyword) || hayVariants.includes(normKeyword));
        const matchesDigits =
          digitsKeyword.length >= 3 &&
          ((rec.corporate_number && rec.corporate_number.includes(digitsKeyword)) ||
            (rec.permit_number && rec.permit_number.includes(digitsKeyword)) ||
            (rec.operator_unique_id && rec.operator_unique_id.includes(digitsKeyword)));
        const matchesRaw = rawCombined.includes(keywordRaw.normalize("NFKC").toUpperCase());

        if (!matchesNormName && !matchesDigits && !matchesRaw) {
          return false;
        }
      }
      return true;
    });

    document.getElementById("db-result-summary").textContent =
      "検索結果: " + filtered.length + " 件 ／ 収録総数 " + dispositions.length + " 件";

    const tbody = document.getElementById("disposition-table-body");
    if (filtered.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="6" style="text-align:center;padding:24px;color:#64748b;">該当する行政処分レコードはありません。検索条件を変更してお試しください。</td></tr>';
      return;
    }

    tbody.innerHTML = filtered
      .map((rec) => {
        let badgeCls = "badge-medium";
        if (rec.disposition_type === "許可取消") badgeCls = "badge-critical";
        else if (rec.disposition_type === "事業停止") badgeCls = "badge-high";

        const suspensionNote = rec.suspension_days
          ? '<div style="font-size:11.5px;color:#B45309;margin-top:4px;font-weight:600;">停止日数: ' +
            escapeHtml(rec.suspension_days) +
            "日間" +
            (rec.suspension_start && rec.suspension_end
              ? "<br>(" + escapeHtml(rec.suspension_start) + "〜" + escapeHtml(rec.suspension_end) + ")"
              : "") +
            "</div>"
          : "";

        const wasteHtml = (rec.waste_categories || [])
          .map((wc) => {
            const isTokkan = wc.includes("特別管理");
            return (
              '<span class="waste-tag' +
              (isTokkan ? " tokkan" : "") +
              '">' +
              escapeHtml(wc) +
              "</span>"
            );
          })
          .join("");

        return (
          "<tr>" +
          "<td><strong>" +
          escapeHtml(rec.disposition_date) +
          '</strong><br><span style="color:#475569;font-size:12px;">' +
          escapeHtml(rec.issuing_authority || rec.prefecture) +
          "</span></td>" +
          '<td><span class="badge ' +
          badgeCls +
          '">' +
          escapeHtml(rec.disposition_type) +
          "</span>" +
          suspensionNote +
          "</td>" +
          "<td><strong>" +
          escapeHtml(rec.company_name) +
          '</strong><br><span class="mono-code">法人番号: ' +
          escapeHtml(rec.corporate_number) +
          '</span><br><span class="mono-code">許可番号: ' +
          escapeHtml(rec.permit_formatted || rec.permit_number) +
          '</span> <span style="font-size:11px;color:#64748b;">(固有:' +
          escapeHtml(rec.operator_unique_id) +
          ")</span></td>" +
          "<td>" +
          wasteHtml +
          "</td>" +
          "<td><div>" +
          escapeHtml(rec.violation_summary) +
          '</div><div style="font-size:11.5px;color:#475569;margin-top:4px;">根拠: ' +
          escapeHtml(rec.statutory_basis) +
          '</div><div style="font-size:11.5px;color:#0f172a;background:#f1f5f9;padding:5px 8px;border-radius:4px;margin-top:5px;"><strong>監査対応指針:</strong> ' +
          escapeHtml(rec.recommended_audit_action) +
          "</div></td>" +
          '<td><a href="' +
          escapeHtml(rec.source_url) +
          '" target="_blank" rel="noopener noreferrer" class="btn btn-secondary" style="padding:6px 10px;font-size:12px;">公式公表ページ ↗</a></td>' +
          "</tr>"
        );
      })
      .join("");
  }

  function renderSourcesRegistry() {
    const sourcesGrid = document.getElementById("sources-grid");
    const sources =
      (activeDataset.source_registry_health && activeDataset.source_registry_health.sources) || [];
    sourcesGrid.innerHTML = sources
      .map((src) => {
        const isHealthy = !src.is_dead_link;
        return (
          '<div class="source-item">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">' +
          "<strong>" +
          escapeHtml(src.jurisdiction) +
          "</strong>" +
          '<span class="badge ' +
          (isHealthy ? "badge-ok" : "badge-critical") +
          '">' +
          (isHealthy ? "監視稼働中" : "要確認") +
          "</span></div>" +
          '<div style="font-size:12.5px;margin-bottom:6px;color:#334155;">' +
          escapeHtml(src.name) +
          "</div>" +
          '<a href="' +
          escapeHtml(src.url) +
          '" target="_blank" rel="noopener noreferrer" style="font-size:12px;">公式URLを開く ↗</a>' +
          "</div>"
        );
      })
      .join("");
  }

  function renderHeaderKpis() {
    const dispositions = activeDataset.dispositions || [];
    const totalSources =
      (activeDataset.source_registry_health && activeDataset.source_registry_health.total_sources) || 14;
    const criticalTotal = dispositions.filter(
      (d) => d.disposition_type === "許可取消" || d.disposition_type === "事業停止"
    ).length;

    document.getElementById("kpi-sources-count").textContent = totalSources + "機関";
    document.getElementById("kpi-records-count").textContent = dispositions.length + "件";
    document.getElementById("kpi-critical-count").textContent = criticalTotal + "件";
    document.getElementById("kpi-updated-at").textContent = String(activeDataset.generated_at || "").slice(
      0,
      10
    );
    document.getElementById("kpi-dataset-hash").textContent =
      "SHA-256: " + String(activeDataset.dataset_sha256 || "").slice(0, 20) + "...";
  }

  /* =========================================================================
   * Single-Number Interactive Inspector
   * ========================================================================= */

  function updateSingleInspectors() {
    const corpRaw = document.getElementById("inspect-corp-input").value;
    const corpOut = document.getElementById("inspect-corp-output");
    const corpRes = validateCorporateNumber(corpRaw);

    if (corpRes.isValid) {
      const matched = (activeDataset.dispositions || []).find(
        (d) => d.corporate_number === corpRes.normalized
      );
      corpOut.innerHTML =
        '<span class="badge badge-ok">国税庁 Modulo-9 チェックデジット適合</span> ' +
        '<span class="mono-code">' +
        escapeHtml(corpRes.normalized) +
        "</span>" +
        '<div style="margin-top:6px;font-size:12px;color:#334155;">先頭検査数字: <strong>' +
        corpRes.actualCheckDigit +
        "</strong> ／ 12桁基礎番号: <span class=\"mono-code\">" +
        escapeHtml(corpRes.base12) +
        "</span></div>" +
        (matched
          ? '<div style="margin-top:6px;color:#DC2626;font-weight:600;"><span class="badge badge-critical">一致あり</span> ' +
            escapeHtml(matched.company_name) +
            "（" +
            escapeHtml(matched.prefecture) +
            "・" +
            escapeHtml(matched.disposition_type) +
            "）</div>"
          : '<div style="margin-top:6px;color:#15803D;font-weight:500;"><span class="badge badge-ok">該当なし</span> 収録されている行政処分データとの一致はありません。</div>');
    } else {
      corpOut.innerHTML =
        '<span class="badge badge-critical">検証エラー</span> ' + escapeHtml(corpRes.error);
    }

    const permitRaw = document.getElementById("inspect-permit-input").value;
    const permitOut = document.getElementById("inspect-permit-output");
    const permitRes = normalizePermitNumber(permitRaw);

    if (permitRes.isValid) {
      const sameOp = (activeDataset.dispositions || []).filter(
        (d) => d.operator_unique_id === permitRes.operatorUniqueId
      );
      permitOut.innerHTML =
        '<span class="badge badge-ok">統一11桁許可番号 正規化OK</span> ' +
        '<span class="mono-code">' +
        escapeHtml(permitRes.formatted) +
        "</span>" +
        (permitRes.was10Digit ? ' <span style="font-size:11.5px;color:#0F766E;">(10桁表記から先頭0補完)</span>' : "") +
        '<div style="margin-top:6px;font-size:12px;color:#475569;">' +
        "自治体コード: <strong>" +
        escapeHtml(permitRes.authorityCode) +
        "（" +
        escapeHtml(permitRes.authorityName) +
        "）</strong> ／ 事業区分: <strong>" +
        escapeHtml(permitRes.categoryCode) +
        "（" +
        escapeHtml(permitRes.categoryLabel) +
        "）</strong> ／ 全国共通6桁固有番号: <strong class=\"mono-code\">" +
        escapeHtml(permitRes.operatorUniqueId) +
        "</strong></div>" +
        (sameOp.length > 0
          ? '<div style="margin-top:6px;color:#B45309;font-weight:600;"><span class="badge badge-high">固有番号一致</span> 同一固有番号（' +
            escapeHtml(permitRes.operatorUniqueId) +
            "）の処分履歴検知: " +
            escapeHtml(sameOp[0].company_name) +
            "（" +
            escapeHtml(sameOp[0].prefecture) +
            "・" +
            escapeHtml(sameOp[0].disposition_type) +
            "）</div>"
          : '<div style="margin-top:6px;color:#15803D;font-weight:500;"><span class="badge badge-ok">該当なし</span> 同一固有番号を含む行政処分レコードは検出されませんでした。</div>');
    } else {
      permitOut.innerHTML =
        '<span class="badge badge-critical">解析エラー</span> ' + escapeHtml(permitRes.error);
    }
  }

  /* =========================================================================
   * CSV Download Helpers & Stage-1 Waitlist Handler
   * ========================================================================= */

  function downloadTextAsFile(filename, contentWithNoBom) {
    const bom = "\uFEFF";
    const blob = new Blob([bom + contentWithNoBom], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function exportAuditedResultsCsv() {
    if (!latestAuditResults.length) {
      return;
    }
    const header = [
      "No",
      "委託先名称",
      "正規化商号",
      "入力法人番号",
      "法人番号Modulo9検証",
      "正規化11桁許可番号",
      "6桁固有番号",
      "総合判定",
      "検知内容・監査指示",
      "公式参照URL"
    ];
    const escapeCsvField = (v) => '"' + String(v || "").replace(/"/g, '""') + '"';
    const lines = [header.join(",")];
    for (const r of latestAuditResults) {
      lines.push(
        [
          r.rowNumber,
          escapeCsvField(r.companyName),
          escapeCsvField(r.normalizedName),
          escapeCsvField(r.corpCheck.normalized || r.corpCheck.raw),
          escapeCsvField(r.corpCheck.isEmpty ? "未入力" : r.corpCheck.isValid ? "OK" : r.corpCheck.error),
          escapeCsvField(r.permitCheck.normalized || r.permitCheck.raw),
          escapeCsvField(r.permitCheck.operatorUniqueId || ""),
          escapeCsvField(r.judgmentLabel),
          escapeCsvField(r.findingsSummary),
          escapeCsvField(r.primarySourceUrl)
        ].join(",")
      );
    }
    downloadTextAsFile("sanpai_iso14001_audit_result.csv", lines.join("\r\n"));
  }

  function runSampleCsvTrial(scrollIntoViewFlag) {
    const parsedRows = parseCsvRows(SAMPLE_CONTRACTOR_CSV);
    const contractors = mapContractorColumns(parsedRows);
    const results = runContractorBatchAudit(contractors, activeDataset.dispositions || []);
    renderAuditCertificate(
      results,
      "サンプル委託先CSV（8社：許可取消・事業停止・旧字体名寄せ・他県連鎖欠格・法人番号タイポ・適格を含む実戦デモ）を照合中"
    );
    if (scrollIntoViewFlag) {
      document.getElementById("section-csv-audit").scrollIntoView({ behavior: "smooth" });
    }
  }

  function handleUploadedFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function (evt) {
      const csvText = decodeCsvBuffer(evt.target.result);
      const rows = parseCsvRows(csvText);
      const contractors = mapContractorColumns(rows);
      if (contractors.length === 0) {
        document.getElementById("audit-toolbar-status").textContent =
          "CSV内に有効な委託先データ行が見つかりませんでした。";
        return;
      }
      const results = runContractorBatchAudit(contractors, activeDataset.dispositions || []);
      renderAuditCertificate(
        results,
        "読込ファイル「" + file.name + "」（" + contractors.length + "社）の一括照合完了"
      );
    };
    reader.readAsArrayBuffer(file);
  }

  async function handleWaitlistSubmit(event) {
    event.preventDefault();
    if (SANPAI_APP_CONFIG.stripePaymentLinkUrl) {
      window.open(SANPAI_APP_CONFIG.stripePaymentLinkUrl, "_blank", "noopener,noreferrer");
      return;
    }

    const company = document.getElementById("wl-company").value.trim();
    const email = document.getElementById("wl-email").value.trim();
    const scale = document.getElementById("wl-contractors").value;
    const purpose = document.getElementById("wl-purpose").value;

    const entry = {
      submitted_at: new Date().toISOString(),
      company: company,
      email: email,
      contractor_scale: scale,
      purpose: purpose,
      plan: "Pro_Monthly_4980_JPY"
    };

    try {
      const existing = JSON.parse(window.localStorage.getItem(SANPAI_APP_CONFIG.storageKeyWaitlist) || "[]");
      existing.push(entry);
      window.localStorage.setItem(SANPAI_APP_CONFIG.storageKeyWaitlist, JSON.stringify(existing));
    } catch (_storageErr) {
      // Ignore storage quota errors in private browsing
    }

    if (SANPAI_APP_CONFIG.waitlistWebhookUrl) {
      try {
        await fetch(SANPAI_APP_CONFIG.waitlistWebhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(entry)
        });
      } catch (_netErr) {
        // Non-blocking fallback
      }
    }

    const feedback = document.getElementById("waitlist-feedback");
    feedback.textContent =
      "先行案内リストへのご登録を受け付けました（" +
      email +
      " ／ 管理規模: " +
      scale +
      "）。週次自動監視枠のご案内準備が整い次第ご連絡いたします。それまでの間、上のブラウザCSV一括照合＆A4点検記録票印刷は無制限・無料でご利用いただけます。";
    feedback.classList.add("visible");
  }

  /* =========================================================================
   * Initialization
   * ========================================================================= */

  async function initializeApp() {
    try {
      const response = await fetch(SANPAI_APP_CONFIG.dataJsonUrl, { cache: "no-cache" });
      if (response.ok) {
        const json = await response.json();
        if (json && Array.isArray(json.dispositions) && json.dispositions.length > 0) {
          activeDataset = json;
        }
      }
    } catch (_fetchErr) {
      // Uses BUNDLED_FALLBACK_DATASET when opened directly via file://
    }

    renderHeaderKpis();
    populateFilterDropdowns(activeDataset.dispositions || []);
    renderDispositionTable();
    renderSourcesRegistry();
    updateSingleInspectors();
    runSampleCsvTrial(false);

    // Event bindings
    document.getElementById("hero-try-sample-btn").addEventListener("click", function () {
      runSampleCsvTrial(true);
    });
    document.getElementById("try-sample-csv-btn").addEventListener("click", function () {
      runSampleCsvTrial(false);
    });
    document.getElementById("download-template-csv-btn").addEventListener("click", function () {
      downloadTextAsFile("sanpai_contractors_template.csv", CSV_TEMPLATE_CONTENT);
    });

    const fileInput = document.getElementById("csv-file-input");
    document.getElementById("select-csv-file-btn").addEventListener("click", function (e) {
      e.stopPropagation();
      fileInput.click();
    });
    fileInput.addEventListener("change", function () {
      if (fileInput.files && fileInput.files[0]) {
        handleUploadedFile(fileInput.files[0]);
      }
    });

    const dropzone = document.getElementById("csv-dropzone");
    dropzone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", function () {
      dropzone.classList.remove("dragover");
    });
    dropzone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleUploadedFile(e.dataTransfer.files[0]);
      }
    });

    ["meta-emitter-company", "meta-emitter-site", "meta-auditor-name", "meta-audit-period"].forEach(
      function (id) {
        document.getElementById(id).addEventListener("input", function () {
          renderAuditCertificate(latestAuditResults, "");
        });
      }
    );

    document.getElementById("print-certificate-btn").addEventListener("click", function () {
      window.print();
    });
    document.getElementById("export-audit-csv-btn").addEventListener("click", exportAuditedResultsCsv);

    ["search-keyword", "filter-prefecture", "filter-type", "filter-waste"].forEach(function (id) {
      document.getElementById(id).addEventListener("input", renderDispositionTable);
      document.getElementById(id).addEventListener("change", renderDispositionTable);
    });

    document.getElementById("reset-filters-btn").addEventListener("click", function () {
      document.getElementById("search-keyword").value = "";
      document.getElementById("filter-prefecture").value = "";
      document.getElementById("filter-type").value = "";
      document.getElementById("filter-waste").value = "";
      renderDispositionTable();
    });

    document.getElementById("inspect-corp-input").addEventListener("input", updateSingleInspectors);
    document.getElementById("inspect-permit-input").addEventListener("input", updateSingleInspectors);
    document.getElementById("pro-waitlist-form").addEventListener("submit", handleWaitlistSubmit);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeApp);
  } else {
    initializeApp();
  }
})();
