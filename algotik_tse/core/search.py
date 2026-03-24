import requests
from algotik_tse.settings import settings
from algotik_tse.http_client import safe_get


def _normalize_fa(text):
    """Normalize Arabic/Persian character variants for matching."""
    text = text.strip()
    text = text.replace("\u0643", "\u06A9")  # Arabic ك → Persian ک
    text = text.replace("\u064A", "\u06CC")  # Arabic ي → Persian ی
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


def search_stock(search_txt="شتران"):
    index_names = settings.index_names
    stock_id = ""
    if search_txt in index_names:
        webid_dict = {
            index_names[0]: 32097828799138957,
            index_names[1]: 67130298613737946,
            index_names[2]: 67130298613737946,
            index_names[3]: 67130298613737946,
            index_names[4]: 67130298613737946,
            index_names[5]: 67130298613737946,
            index_names[6]: 5798407779416661,
            index_names[7]: 8384385859414435,
            index_names[8]: 8384385859414435,
            index_names[9]: 8384385859414435,
            index_names[10]: 49579049405614711,
            index_names[11]: 49579049405614711,
            index_names[12]: 62752761908615603,
            index_names[13]: 71704845530629737,
            index_names[14]: 43754960038275285,
            index_names[15]: 10523825119011581,
            index_names[16]: 10523825119011581,
            index_names[17]: 10523825119011581,
            index_names[18]: 46342955726788357,
            index_names[19]: 46342955726788357,
            index_names[20]: 46342955726788357,
            index_names[21]: 46342955726788357,
            index_names[22]: 46342955726788357,
            index_names[23]: 46342955726788357,
        }
        return str(webid_dict[search_txt]) + "index"

    # Check industry indices (44 sectors) with Arabic/Persian normalization
    normalized = _normalize_fa(search_txt)
    if normalized in _INDUSTRY_DICT:
        return _INDUSTRY_DICT[normalized] + "industry"

    # Fallback: search API
    try:
        res_search = safe_get(settings.url_search.format(search_txt)).json()[
            "instrumentSearch"
        ]

        if len(res_search) > 0:
            stock_id = res_search[0]["insCode"]
        else:
            return None
    except requests.exceptions.RequestException:
        print("Connection Error!")
        return None
    except (ValueError, KeyError, IndexError, TypeError) as e:
        print("Search Error: {}".format(e))
        return None
    return stock_id
