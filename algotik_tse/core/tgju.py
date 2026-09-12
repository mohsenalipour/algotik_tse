"""Catalog and public helpers for TGJU market-history assets."""

from collections import OrderedDict

import pandas as pd

from algotik_tse.exceptions import InvalidParameterError

TGJU_CATEGORIES = (
    "currency",
    "official_rate",
    "gold",
    "silver",
    "coin",
    "coin_bubble",
    "global_metal",
)


def _asset(name, persian_name, slug, category, unit, *aliases):
    return {
        "Name": name,
        "PersianName": persian_name,
        "Slug": slug,
        "Category": category,
        "Unit": unit,
        "Aliases": tuple(aliases),
    }


# The catalog is intentionally explicit.  A profile is included only after its
# official TGJU history endpoint has returned the expected eight-field rows.
_TGJU_ASSET_ROWS = (
    # Free-market currencies (prices are rials unless noted otherwise).
    _asset(
        "dollar", "دلار", "price_dollar_rl", "currency", "rial_per_unit", "دلار آزاد"
    ),
    _asset("euro", "یورو", "price_eur", "currency", "rial_per_unit"),
    _asset("dirham", "درهم امارات", "price_aed", "currency", "rial_per_unit", "درهم"),
    _asset("pound", "پوند انگلیس", "price_gbp", "currency", "rial_per_unit", "پوند"),
    _asset("lira", "لیر ترکیه", "price_try", "currency", "rial_per_unit", "لیر"),
    _asset("swiss-franc", "فرانک سوئیس", "price_chf", "currency", "rial_per_unit"),
    _asset("yuan", "یوان چین", "price_cny", "currency", "rial_per_unit", "یوان"),
    _asset(
        "japanese-yen-100",
        "صد ین ژاپن",
        "price_jpy",
        "currency",
        "rial_per_100_units",
        "ین ژاپن",
        "ین",
    ),
    _asset(
        "south-korean-won",
        "وون کره جنوبی",
        "price_krw",
        "currency",
        "rial_per_unit",
        "وون کره",
    ),
    _asset("canadian-dollar", "دلار کانادا", "price_cad", "currency", "rial_per_unit"),
    _asset(
        "australian-dollar", "دلار استرالیا", "price_aud", "currency", "rial_per_unit"
    ),
    _asset(
        "new-zealand-dollar", "دلار نیوزیلند", "price_nzd", "currency", "rial_per_unit"
    ),
    _asset(
        "singapore-dollar", "دلار سنگاپور", "price_sgd", "currency", "rial_per_unit"
    ),
    _asset("indian-rupee", "روپیه هند", "price_inr", "currency", "rial_per_unit"),
    _asset(
        "pakistani-rupee", "روپیه پاکستان", "price_pkr", "currency", "rial_per_unit"
    ),
    _asset("iraqi-dinar", "دینار عراق", "price_iqd", "currency", "rial_per_unit"),
    _asset(
        "syrian-pound",
        "پوند سوریه",
        "price_syp",
        "currency",
        "rial_per_unit",
        "لیر سوریه",
    ),
    _asset("afghani", "افغانی", "price_afn", "currency", "rial_per_unit"),
    _asset("danish-krone", "کرون دانمارک", "price_dkk", "currency", "rial_per_unit"),
    _asset("swedish-krona", "کرون سوئد", "price_sek", "currency", "rial_per_unit"),
    _asset("norwegian-krone", "کرون نروژ", "price_nok", "currency", "rial_per_unit"),
    _asset("saudi-riyal", "ریال عربستان", "price_sar", "currency", "rial_per_unit"),
    _asset("qatari-riyal", "ریال قطر", "price_qar", "currency", "rial_per_unit"),
    _asset("omani-rial", "ریال عمان", "price_omr", "currency", "rial_per_unit"),
    _asset("kuwaiti-dinar", "دینار کویت", "price_kwd", "currency", "rial_per_unit"),
    _asset("bahraini-dinar", "دینار بحرین", "price_bhd", "currency", "rial_per_unit"),
    _asset(
        "malaysian-ringgit", "رینگیت مالزی", "price_myr", "currency", "rial_per_unit"
    ),
    _asset("thai-baht", "بات تایلند", "price_thb", "currency", "rial_per_unit"),
    _asset(
        "hong-kong-dollar", "دلار هنگ کنگ", "price_hkd", "currency", "rial_per_unit"
    ),
    _asset("russian-ruble", "روبل روسیه", "price_rub", "currency", "rial_per_unit"),
    _asset(
        "azerbaijani-manat", "منات آذربایجان", "price_azn", "currency", "rial_per_unit"
    ),
    _asset("armenian-dram", "درام ارمنستان", "price_amd", "currency", "rial_per_unit"),
    _asset("georgian-lari", "لاری گرجستان", "price_gel", "currency", "rial_per_unit"),
    _asset(
        "kyrgyzstani-som", "سوم قرقیزستان", "price_kgs", "currency", "rial_per_unit"
    ),
    _asset(
        "tajikistani-somoni",
        "سامانی تاجیکستان",
        "price_tjs",
        "currency",
        "rial_per_unit",
    ),
    _asset(
        "turkmenistani-manat",
        "منات ترکمنستان",
        "price_tmt",
        "currency",
        "rial_per_unit",
    ),
    # Published bank/SANA/NIMA series retained as distinct data products.
    _asset(
        "dollar-sana-sell",
        "دلار سنا فروش",
        "sana_sell_usd",
        "official_rate",
        "rial_per_unit",
        "دلار سنا-فروش",
    ),
    _asset(
        "euro-sana-sell",
        "یورو سنا فروش",
        "sana_sell_eur",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "pound-sana-sell",
        "پوند سنا فروش",
        "sana_sell_gbp",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "dirham-sana-sell",
        "درهم سنا فروش",
        "sana_sell_aed",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "canadian-dollar-sana-sell",
        "دلار کانادا سنا فروش",
        "sana_sell_cad",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "lira-sana-sell",
        "لیر ترکیه سنا فروش",
        "sana_sell_try",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "dollar-sana-buy",
        "دلار سنا خرید",
        "sana_buy_usd",
        "official_rate",
        "rial_per_unit",
        "دلار سنا-خرید",
    ),
    _asset(
        "dollar-sarafimelli-buy",
        "دلار صرافی ملی خرید",
        "sana_real_buy_usd",
        "official_rate",
        "rial_per_unit",
        "دلار صرافی ملی",
    ),
    _asset(
        "dollar-nima-sell",
        "دلار نیما فروش",
        "nima_sell_usd",
        "official_rate",
        "rial_per_unit",
        "دلار نیما-فروش",
    ),
    _asset(
        "euro-nima-sell",
        "یورو نیما فروش",
        "nima_sell_eur",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "pound-nima-sell",
        "پوند نیما فروش",
        "nima_sell_gbp",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "dirham-nima-sell",
        "درهم نیما فروش",
        "nima_sell_aed",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "dollar-nima-buy",
        "دلار نیما خرید",
        "nima_buy_usd",
        "official_rate",
        "rial_per_unit",
        "دلار نیما-خرید",
    ),
    _asset(
        "euro-nima-buy",
        "یورو نیما خرید",
        "nima_buy_eur",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "pound-nima-buy",
        "پوند نیما خرید",
        "nima_buy_gbp",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "dirham-nima-buy",
        "درهم نیما خرید",
        "nima_buy_aed",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "canadian-dollar-nima-buy",
        "دلار کانادا نیما خرید",
        "nima_buy_cad",
        "official_rate",
        "rial_per_unit",
    ),
    _asset(
        "lira-nima-buy",
        "لیر ترکیه نیما خرید",
        "nima_buy_try",
        "official_rate",
        "rial_per_unit",
    ),
    _asset("dollar-bank", "دلار بانکی", "bank_usd", "official_rate", "rial_per_unit"),
    _asset("euro-bank", "یورو بانکی", "bank_eur", "official_rate", "rial_per_unit"),
    _asset("pound-bank", "پوند بانکی", "bank_gbp", "official_rate", "rial_per_unit"),
    _asset("dirham-bank", "درهم بانکی", "bank_aed", "official_rate", "rial_per_unit"),
    _asset("yuan-bank", "یوان بانکی", "bank_cny", "official_rate", "rial_per_unit"),
    _asset("lira-bank", "لیر بانکی", "bank_try", "official_rate", "rial_per_unit"),
    # Domestic precious metals.
    _asset("gold-mesghal", "مثقال طلا", "mesghal", "gold", "rial_per_mesghal", "مثقال"),
    _asset(
        "gold-18k",
        "طلای 18 عیار",
        "geram18",
        "gold",
        "rial_per_gram",
        "طلای ۱۸ عیار",
        "طلای 750",
        "طلای ۷۵۰",
    ),
    _asset(
        "gold-24k", "طلای 24 عیار", "geram24", "gold", "rial_per_gram", "طلای ۲۴ عیار"
    ),
    _asset("used-gold", "طلای دست دوم", "gold_mini_size", "gold", "rial_per_gram"),
    _asset(
        "melted-gold-cash",
        "آبشده نقدی",
        "gold_futures",
        "gold",
        "rial_per_mesghal",
        "آبشده",
    ),
    _asset(
        "melted-gold-wholesale",
        "آبشده بنکداری",
        "gold_melted_wholesale",
        "gold",
        "rial_per_mesghal",
    ),
    _asset(
        "melted-gold-under-kilo",
        "آبشده کمتر از کیلو",
        "gold_world_futures",
        "gold",
        "rial_per_mesghal",
    ),
    _asset(
        "gold-18k-740",
        "طلای 18 عیار 740",
        "gold_740k",
        "gold",
        "rial_per_gram",
        "طلای ۱۸ عیار ۷۴۰",
    ),
    _asset(
        "gold-mesghal-global-purity",
        "مثقال با عیار جهانی",
        "gold_17",
        "gold",
        "rial_per_mesghal",
    ),
    _asset(
        "gold-mesghal-transfer",
        "مثقال حواله دلار",
        "gold_17_transfer",
        "gold",
        "rial_per_mesghal",
    ),
    _asset(
        "gold-mesghal-coin-transfer",
        "مثقال حواله دلار سکه",
        "gold_17_coin",
        "gold",
        "rial_per_mesghal",
    ),
    _asset(
        "silver-999", "نقره 999", "silver_999", "silver", "rial_per_gram", "نقره ۹۹۹"
    ),
    _asset(
        "silver-925", "نقره 925", "silver_925", "silver", "rial_per_gram", "نقره ۹۲۵"
    ),
    # Coins and their published bubbles.
    _asset("seke", "سکه امامی", "sekee", "coin", "rial_per_coin", "سکه"),
    _asset("seke-bahar-azadi", "سکه بهار آزادی", "sekeb", "coin", "rial_per_coin"),
    _asset("nim-seke", "نیم سکه", "nim", "coin", "rial_per_coin"),
    _asset("rob-seke", "ربع سکه", "rob", "coin", "rial_per_coin"),
    _asset("seke-gerami", "سکه گرمی", "gerami", "coin", "rial_per_coin"),
    _asset(
        "seke-bubble",
        "حباب سکه امامی",
        "coin_blubber",
        "coin_bubble",
        "rial_per_coin",
        "حباب سکه",
    ),
    _asset(
        "seke-bahar-azadi-bubble",
        "حباب سکه بهار آزادی",
        "sekeb_blubber",
        "coin_bubble",
        "rial_per_coin",
    ),
    _asset(
        "nim-seke-bubble", "حباب نیم سکه", "nim_blubber", "coin_bubble", "rial_per_coin"
    ),
    _asset(
        "rob-seke-bubble", "حباب ربع سکه", "rob_blubber", "coin_bubble", "rial_per_coin"
    ),
    _asset(
        "seke-gerami-bubble",
        "حباب سکه گرمی",
        "gerami_blubber",
        "coin_bubble",
        "rial_per_coin",
    ),
    # Global precious metals reported by TGJU in USD per troy ounce.
    _asset(
        "gold-ounce",
        "انس جهانی طلا",
        "ons",
        "global_metal",
        "usd_per_troy_ounce",
        "اونس طلا",
        "انس طلا",
    ),
    _asset(
        "silver-ounce",
        "انس جهانی نقره",
        "silver",
        "global_metal",
        "usd_per_troy_ounce",
        "اونس نقره",
        "انس نقره",
    ),
    _asset(
        "platinum-ounce",
        "انس جهانی پلاتین",
        "platinum",
        "global_metal",
        "usd_per_troy_ounce",
        "پلاتین",
    ),
    _asset(
        "palladium-ounce",
        "انس جهانی پالادیوم",
        "palladium",
        "global_metal",
        "usd_per_troy_ounce",
        "پالادیوم",
    ),
)

TGJU_ASSETS = OrderedDict((row["Name"], row) for row in _TGJU_ASSET_ROWS)

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _normalise_asset_key(value):
    if not isinstance(value, str):
        raise InvalidParameterError("TGJU asset name must be a string")
    text = value.translate(_DIGITS).replace("ي", "ی").replace("ك", "ک")
    text = text.replace("\u200c", " ").replace("_", "-")
    return " ".join(text.strip().lower().split())


def _build_lookup():
    lookup = {}
    for name, row in TGJU_ASSETS.items():
        values = (name, row["Slug"], row["PersianName"]) + row["Aliases"]
        for value in values:
            key = _normalise_asset_key(value)
            current = lookup.get(key)
            if current is not None and current != name:
                raise RuntimeError("duplicate TGJU alias {!r}".format(value))
            lookup[key] = name
    return lookup


_TGJU_LOOKUP = _build_lookup()


def resolve_tgju_asset(name):
    """Resolve a canonical name, Persian alias or official TGJU slug."""
    key = _normalise_asset_key(name)
    canonical = _TGJU_LOOKUP.get(key)
    if canonical is None:
        raise InvalidParameterError(
            "unknown TGJU asset {!r}; use list_tgju_assets() for valid names".format(
                name
            )
        )
    return TGJU_ASSETS[canonical]


def list_tgju_assets(category=None, include_aliases=False):
    """Return the verified assets supported by the TGJU history provider.

    Parameters
    ----------
    category : str or sequence of str, optional
        One or more of ``currency``, ``official_rate``, ``gold``, ``silver``,
        ``coin``, ``coin_bubble`` and ``global_metal``.
    include_aliases : bool, default False
        Include an ``Aliases`` tuple column.
    """
    if not isinstance(include_aliases, bool):
        raise InvalidParameterError("include_aliases must be bool")
    if category is None:
        categories = None
    else:
        values = [category] if isinstance(category, str) else list(category)
        categories = {str(value).strip().lower() for value in values}
        invalid = categories.difference(TGJU_CATEGORIES)
        if invalid:
            raise InvalidParameterError(
                "category must contain only: {}".format(", ".join(TGJU_CATEGORIES))
            )
    rows = []
    for row in TGJU_ASSETS.values():
        if categories is not None and row["Category"] not in categories:
            continue
        item = dict(row)
        if not include_aliases:
            item.pop("Aliases")
        rows.append(item)
    columns = ["Name", "PersianName", "Slug", "Category", "Unit"]
    if include_aliases:
        columns.append("Aliases")
    result = pd.DataFrame(rows, columns=columns)
    result.attrs.update(
        {
            "source": "tgju",
            "endpoint": "https://api.tgju.org/v1/market/indicator/summary-table-data/{slug}",
            "verified_row_width": 8,
            "category": category,
        }
    )
    return result


def get_tgju_history(
    name="",
    start=None,
    end=None,
    limit=0,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    dropna=True,
    return_type=None,
    ascending=True,
    save_path=None,
    **kwargs
):
    """Get history for any asset listed by :func:`list_tgju_assets`."""
    from algotik_tse.core.currency import currency_coin

    return currency_coin(
        name=name,
        start=start,
        end=end,
        limit=limit,
        output_type=output_type,
        date_format=date_format,
        progress=progress,
        save_to_file=save_to_file,
        dropna=dropna,
        return_type=return_type,
        ascending=ascending,
        save_path=save_path,
        **kwargs
    )


__all__ = [
    "TGJU_ASSETS",
    "TGJU_CATEGORIES",
    "resolve_tgju_asset",
    "list_tgju_assets",
    "get_tgju_history",
]
