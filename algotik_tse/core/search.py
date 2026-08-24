def _normalize_fa(text):
    """Normalize Arabic/Persian character variants for matching."""
    text = text.strip()
    text = text.replace("\u0643", "\u06a9")  # Arabic ك → Persian ک
    text = text.replace("\u064a", "\u06cc")  # Arabic ي → Persian ی
    text = text.replace("\u200c", " ")  # half-space → space
    text = " ".join(text.split())  # collapse whitespace
    return text


# ── Complete industry indices ─────────────────────────────────
# Source: https://cdn.tsetmc.com/api/Index/GetIndexB1LastAll/All/1
# Each entry: web_id → list of Persian name variants (already normalized)
_INDUSTRY_RAW = {
    "34408080767216529": ["زراعت"],
    "19219679288446732": ["ذغال سنگ"],
    "65675836323214668": ["استخراج نفت", "استخراج نفت جز کشف"],
    "13235969998952202": ["کانه فلزی"],
    "62691002126902464": ["سایر معادن", "معادن"],
    "59288237226302898": ["منسوجات"],
    "69306841376553334": ["محصولات چرمی"],
    "58440550086834602": ["محصولات چوبی"],
    "30106839080444358": ["محصولات کاغذ", "محصولات کاغذی", "کاغذ"],
    "25766336681098389": ["انتشار و چاپ"],
    "12331083953323969": ["فراورده نفتی", "فرآورده نفتی", "فرآورده های نفتی"],
    "36469751685735891": ["لاستیک", "لاستیک و پلاستیک"],
    "32453344048876642": ["فلزات اساسی"],
    "1123534346391630": ["محصولات فلزی"],
    "11451389074113298": ["ماشین آلات"],
    "33878047680249697": ["دستگاههای برقی", "تجهیزات برقی"],
    "24733701189547084": ["وسایل ارتباطی"],
    "61848754958448778": ["ابزار پزشکی"],
    "20213770409093165": ["خودرو", "خودرو و ساخت قطعات"],
    "58231368623465359": ["حمل و نقل", "حمل ونقل"],
    "29331053506731535": ["مبلمان"],
    "21948907150049163": ["قند و شکر"],
    "40355846462826897": ["چند رشته ای صنعتی", "چند رشته ای"],
    "54843635503648458": ["آب، برق، گاز", "تامین آب، برق، گاز", "یوتیلیتی"],
    "15508900928481581": ["غذایی بجز قند", "غذایی", "مواد غذایی"],
    "3615666621538524": ["مواد دارویی", "دارویی", "دارو"],
    "33626672012415176": ["شیمیایی"],
    "41934470778361119": ["پیمانکاری", "پیمانکاری صنعتی"],
    "65986638607018835": ["خرده فروشی"],
    "57616105980228781": ["کاشی و سرامیک", "کاشی"],
    "70077233737515808": ["سیمان"],
    "14651627750314021": ["کانی غیرفلزی"],
    "64514606457616199": ["هتل و رستوران"],
    "34295935482222451": ["سرمایه گذاریها", "سرمایه گذاری"],
    "72002976013856737": ["بانکها", "بانک"],
    "25163959460949732": ["سایرمالی", "سایر مالی"],
    "24187097921483699": ["حمل و نقل آبی", "کشتیرانی"],
    "41867092385281437": ["رادیویی", "مخابرات"],
    "61247168213690670": ["مالی", "واسطه گری مالی"],
    "59105676994811497": ["بیمه و بازنشسته", "بیمه"],
    "61985386521682984": ["اداره بازارهای مالی"],
    "4654922806626448": ["انبوه سازی", "ساختمان"],
    "8900726085939949": ["رایانه", "کامپیوتر"],
    "18780171241610744": ["اطلاعات و ارتباطات", "فناوری اطلاعات"],
    "47233872677452574": ["فنی مهندسی"],
}

# Build comprehensive lookup: normalized name → web_id
# Generates "X", "شاخص X", and "شاخص صنعت X" for each variant automatically
_INDUSTRY_DICT = {}
for _webid, _names in _INDUSTRY_RAW.items():
    for _name in _names:
        _n = _normalize_fa(_name)
        _INDUSTRY_DICT[_n] = _webid
        _INDUSTRY_DICT[_normalize_fa("شاخص " + _name)] = _webid
        _INDUSTRY_DICT[_normalize_fa("شاخص صنعت " + _name)] = _webid

# Web ID → English name (used by stock.py for ticker labels)
INDUSTRY_NAMES = {
    "34408080767216529": "Agriculture",
    "19219679288446732": "Coal",
    "65675836323214668": "Oil Extraction",
    "13235969998952202": "Metal Ores",
    "62691002126902464": "Other Mines",
    "59288237226302898": "Textiles",
    "69306841376553334": "Leather Products",
    "58440550086834602": "Wood Products",
    "30106839080444358": "Paper Products",
    "25766336681098389": "Publishing",
    "12331083953323969": "Petroleum Products",
    "36469751685735891": "Rubber and Plastic",
    "32453344048876642": "Basic Metals",
    "1123534346391630": "Metal Products",
    "11451389074113298": "Machinery",
    "33878047680249697": "Electrical Equipment",
    "24733701189547084": "Communication Equipment",
    "61848754958448778": "Medical Instruments",
    "20213770409093165": "Automobile",
    "58231368623465359": "Other Transportation",
    "29331053506731535": "Furniture",
    "21948907150049163": "Sugar",
    "40355846462826897": "Multidisciplinary Industrial",
    "54843635503648458": "Utilities",
    "15508900928481581": "Food Products",
    "3615666621538524": "Pharmaceutical",
    "33626672012415176": "Chemical",
    "41934470778361119": "Industrial Contracting",
    "65986638607018835": "Retail",
    "57616105980228781": "Tile and Ceramic",
    "70077233737515808": "Cement",
    "14651627750314021": "Non-Metallic Minerals",
    "64514606457616199": "Hotel and Restaurant",
    "34295935482222451": "Investment Companies",
    "72002976013856737": "Banking",
    "25163959460949732": "Other Financial",
    "24187097921483699": "Shipping",
    "41867092385281437": "Telecommunications",
    "61247168213690670": "Financial Intermediation",
    "59105676994811497": "Insurance",
    "61985386521682984": "Financial Markets Admin",
    "4654922806626448": "Real Estate",
    "8900726085939949": "Computer",
    "18780171241610744": "IT and Communication",
    "47233872677452574": "Technical Engineering",
}


def search_stock(
    search_txt="شتران",
    *,
    ins_code=None,
    asset_type="auto",
    snapshot=None,
    require_active=True,
):
    """Return the legacy web-id string using exact central resolution.

    Index and industry suffixes are retained so every pre-1.1 caller keeps its
    established return type.  Ambiguity and invalid selectors intentionally
    raise their typed exceptions instead of silently selecting the first fuzzy
    search result.
    """
    from algotik_tse.core.resolver import (
        normalize_instrument_text,
        resolve_instrument,
        validate_ins_code,
    )
    from algotik_tse.exceptions import (
        ConnectionError,
        DataParsingError,
        StockNotFoundError,
    )

    normalized_selector = normalize_instrument_text(search_txt)
    normalized_code = None if ins_code is None else validate_ins_code(ins_code)
    # History/detail endpoints already use the canonical numeric ID directly.
    # Avoid an unnecessary InstrumentInfo call when no identity/type data is
    # requested, while still validating an explicitly conflicting ID.
    if (
        snapshot is None
        and asset_type == "auto"
        and normalized_selector.isascii()
        and normalized_selector.isdigit()
    ):
        selector_code = validate_ins_code(search_txt)
        if normalized_code is not None and normalized_code != normalized_selector:
            from algotik_tse.exceptions import InvalidParameterError

            raise InvalidParameterError(
                "selector and ins_code refer to different instruments"
            )
        ref = resolve_instrument(
            selector_code,
            ins_code=normalized_code,
            asset_type="auto",
            snapshot={},
            require_active=require_active,
        )
        if ref.asset_type == "index":
            return ref.ins_code + "index"
        if ref.asset_type == "industry":
            return ref.ins_code + "industry"
        return ref.ins_code
    try:
        ref = resolve_instrument(
            search_txt,
            ins_code=ins_code,
            asset_type=asset_type,
            snapshot=snapshot,
            require_active=require_active,
        )
    except StockNotFoundError:
        return None
    except (ConnectionError, DataParsingError) as exc:
        print("Search Error: {}".format(exc))
        return None
    if ref.asset_type == "index":
        return ref.ins_code + "index"
    if ref.asset_type == "industry":
        return ref.ins_code + "industry"
    return ref.ins_code


def search_stock_symbol(
    search_txt="فملی",
    *,
    ins_code=None,
    asset_type="auto",
    snapshot=None,
    require_active=True,
):
    """Return the verified canonical provider symbol for an exact identity.

    Some TSETMC/Codal endpoints use ``lVal18AFC`` rather than ``InsCode``.
    Resolution follows the central exact/active/type rules and never returns a
    fuzzy first hit. ``snapshot`` is authoritative when supplied; otherwise
    identity may be enriched through InstrumentInfo. Ambiguous and invalid
    inputs raise their typed exceptions, while the legacy no-match result
    remains ``None``.
    """
    from algotik_tse.core.resolver import resolve_instrument
    from algotik_tse.exceptions import (
        ConnectionError,
        DataParsingError,
        StockNotFoundError,
    )

    try:
        ref = resolve_instrument(
            search_txt,
            ins_code=ins_code,
            asset_type=asset_type,
            snapshot=snapshot,
            require_active=require_active,
        )
    except StockNotFoundError:
        return None
    except (ConnectionError, DataParsingError) as exc:
        print("Search Error: {}".format(exc))
        return None
    return ref.symbol
