"""Instrument name parsers for options, bonds, and treasury bills.

Parses structured information from the Name field returned by TSETMC's
MarketWatchInit endpoint. Each instrument type encodes metadata in its
Name string (e.g. option type, strike price, expiry date).
"""

import re
from persiantools.jdatetime import JalaliDate


# ══════════════════════════════════════════════════════════════
#  Option name parsing
# ══════════════════════════════════════════════════════════════

# Pattern: "اختيارخ اهرم-34000-1404/12/26" or "اختيارف اهرم-34000-04/11/29"
# Supports both 4-digit (1404) and 2-digit (04) Jalali year formats.
_OPTION_NAME_RE = re.compile(
    r"اختيار([خف])\s+(.+?)\s*-\s*(\d+)\s*-\s*(\d{2,4}/\d{2}/\d{2})"
)

# Symbol prefix: ض = call, ط = put
_OPTION_SYMBOL_PREFIX = {"ض": "call", "ط": "put"}


def parse_option_name(name):
    """Parse an option instrument Name into structured fields.

    Parameters
    ----------
    name : str
        The full name from TSETMC, e.g.
        ``'اختيارخ اهرم-34000-1404/12/26'``

    Returns
    -------
    dict or None
        Dictionary with keys:

        - ``option_type`` — ``'call'`` or ``'put'``
        - ``underlying`` — Underlying symbol name (e.g. ``'اهرم'``)
        - ``strike`` — Strike price as int (e.g. ``34000``)
        - ``expiry_jalali`` — Expiry date string (e.g. ``'1404/12/26'``)
        - ``expiry_gregorian`` — Expiry as ``datetime.date`` or None

        Returns ``None`` if the name doesn't match the option pattern.
    """
    m = _OPTION_NAME_RE.match(name.strip())
    if not m:
        return None

    opt_type = "call" if m.group(1) == "خ" else "put"
    expiry_jalali = m.group(4)
    # Normalize 2-digit year (e.g. '04/11/29' → '1404/11/29')
    if len(expiry_jalali.split("/")[0]) == 2:
        yy = int(expiry_jalali.split("/")[0])
        full_year = 1400 + yy if yy < 80 else 1300 + yy
        expiry_jalali = (
            f"{full_year}/{expiry_jalali.split('/')[1]}/{expiry_jalali.split('/')[2]}"
        )
    expiry_greg = _jalali_str_to_date(expiry_jalali)

    return {
        "option_type": opt_type,
        "underlying": m.group(2).strip(),
        "strike": int(m.group(3)),
        "expiry_jalali": expiry_jalali,
        "expiry_gregorian": expiry_greg,
    }


def parse_option_symbol(symbol):
    """Determine option type from the symbol prefix character.

    Parameters
    ----------
    symbol : str
        Symbol like ``'ضهرم1116'`` or ``'طهرم1256'``.

    Returns
    -------
    str or None
        ``'call'``, ``'put'``, or ``None`` if not an option symbol.
    """
    if symbol and len(symbol) > 1:
        return _OPTION_SYMBOL_PREFIX.get(symbol[0])
    return None


# ══════════════════════════════════════════════════════════════
#  Bond / Murabaha parsing
# ══════════════════════════════════════════════════════════════

# Maturity patterns:
#   Government: "مرابحه عام دولت175-ش.خ060327" → ش.خ{YYMMDD}
#   Corporate:  "مرابحه طبيعت سبز-سپهر060920"  → trailing YYMMDD
#   With 14-prefix: "اجاره دومينو14061003"       → trailing YYMMDD
_BOND_MATURITY_SHKH = re.compile(r"ش\.خ\.?(\d{6})")  # Government bonds
_BOND_MATURITY_TAIL = re.compile(r"(\d{6})\s*(?:\(|$)")  # Corporate bonds
_BOND_TICKER_RE = re.compile(r"\(([^)]+)\)")


def parse_bond_name(name):
    """Parse a bond/murabaha instrument Name into structured fields.

    Parameters
    ----------
    name : str
        The full name, e.g.
        ``'مرابحه عام دولت175-ش.خ060327 (اراد1754)'``

    Returns
    -------
    dict or None
        Dictionary with keys:

        - ``bond_type`` — ``'murabaha'``, ``'ijara'``, ``'salaf'``, or ``'other'``
        - ``maturity_jalali`` — Maturity date string (e.g. ``'1406/03/27'``)
        - ``maturity_gregorian`` — Maturity as ``datetime.date`` or None
        - ``ticker`` — Ticker symbol (e.g. ``'اراد1754'``) or None

        Returns ``None`` if no maturity date can be extracted.
    """
    # Determine bond sub-type
    name_lower = name.strip()
    if "مرابحه" in name_lower:
        bond_type = "murabaha"
    elif "اجاره" in name_lower:
        bond_type = "ijara"
    elif "سلف" in name_lower:
        bond_type = "salaf"
    else:
        bond_type = "other"

    # Extract maturity: try ش.خ{YYMMDD} first, then trailing 6-digits
    m = _BOND_MATURITY_SHKH.search(name_lower)
    if not m:
        m = _BOND_MATURITY_TAIL.search(name_lower)
    if not m:
        return None

    maturity_jalali = _yymmdd_to_jalali(m.group(1))
    maturity_greg = _jalali_str_to_date(maturity_jalali)

    # Extract ticker from parentheses
    ticker_match = _BOND_TICKER_RE.search(name_lower)
    ticker = ticker_match.group(1).strip() if ticker_match else None

    return {
        "bond_type": bond_type,
        "maturity_jalali": maturity_jalali,
        "maturity_gregorian": maturity_greg,
        "ticker": ticker,
    }


# ══════════════════════════════════════════════════════════════
#  Treasury bill (اسناد خزانه / اخزا) parsing
# ══════════════════════════════════════════════════════════════

# Pattern: "اسنادخزانه-م4بودجه02-051021" or "اسناد خزانه-م2بودجه04-070614"
# The maturity is the trailing 6-digit date at end of name (or before parenthesis).
_TREASURY_MATURITY_RE = re.compile(r"(\d{6})\s*(?:\(|$)")
_TREASURY_TICKER_RE = re.compile(r"\(([^)]+)\)")


def parse_treasury_name(name):
    """Parse a treasury bill Name into structured fields.

    Parameters
    ----------
    name : str
        The full name, e.g.
        ``'اسناد خزانه-م2بودجه04-070614 (اخزا4024)'``

    Returns
    -------
    dict or None
        Dictionary with keys:

        - ``bond_type`` — Always ``'treasury'``
        - ``maturity_jalali`` — Maturity date (e.g. ``'1407/06/14'``)
        - ``maturity_gregorian`` — Maturity as ``datetime.date`` or None
        - ``ticker`` — Ticker symbol (e.g. ``'اخزا4024'``) or None

        Returns ``None`` if no maturity date can be extracted.
    """
    name_stripped = name.strip()

    # Guard: must contain treasury keywords, reject bonds with ش.خ
    if not any(kw in name_stripped for kw in ["اسناد", "خزانه", "اخزا"]):
        return None

    m = _TREASURY_MATURITY_RE.search(name_stripped)
    if not m:
        return None

    maturity_jalali = _yymmdd_to_jalali(m.group(1))
    maturity_greg = _jalali_str_to_date(maturity_jalali)

    ticker_match = _TREASURY_TICKER_RE.search(name_stripped)
    ticker = ticker_match.group(1).strip() if ticker_match else None

    return {
        "bond_type": "treasury",
        "maturity_jalali": maturity_jalali,
        "maturity_gregorian": maturity_greg,
        "ticker": ticker,
    }


# ══════════════════════════════════════════════════════════════
#  Unified parser
# ══════════════════════════════════════════════════════════════


def parse_instrument_name(name, symbol=None):
    """Auto-detect instrument type and parse its Name field.

    Tries option → treasury → bond patterns in order.

    Parameters
    ----------
    name : str
        The full instrument name from TSETMC.
    symbol : str, optional
        The instrument symbol (used for option type detection from prefix).

    Returns
    -------
    dict or None
        Parsed data dict with an ``'instrument_category'`` key added
        (``'option'``, ``'treasury'``, ``'bond'``), or ``None`` if
        no pattern matches.
    """
    # Try option
    result = parse_option_name(name)
    if result:
        result["instrument_category"] = "option"
        # Enrich with symbol prefix if available
        if symbol:
            sym_type = parse_option_symbol(symbol)
            if sym_type:
                result["option_type"] = sym_type
        return result

    # Try treasury (before generic bond — treasury also has parenthesis)
    if "اسناد" in name or "خزانه" in name or "اخزا" in name:
        result = parse_treasury_name(name)
        if result:
            result["instrument_category"] = "treasury"
            return result

    # Try bond / murabaha
    result = parse_bond_name(name)
    if result:
        result["instrument_category"] = "bond"
        return result

    return None


# ══════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════


def _yymmdd_to_jalali(s):
    """Convert a 6-digit YYMMDD string to Jalali date string.

    '060327' → '1406/03/27'
    '070614' → '1407/06/14'
    """
    yy = int(s[:2])
    mm = int(s[2:4])
    dd = int(s[4:6])
    year = 1400 + yy if yy < 80 else 1300 + yy
    return f"{year}/{mm:02d}/{dd:02d}"


def _jalali_str_to_date(jalali_str):
    """Convert a Jalali date string ('1404/12/26') to a Gregorian datetime.date.

    Returns None on parse failure.
    """
    try:
        parts = jalali_str.split("/")
        jy, jm, jd = int(parts[0]), int(parts[1]), int(parts[2])
        return JalaliDate(jy, jm, jd).to_gregorian()
    except Exception:
        return None


def _days_until(target_date):
    """Calculate days from today to a target Gregorian date.

    Parameters
    ----------
    target_date : datetime.date
        The target date.

    Returns
    -------
    int
        Number of days (negative if in the past).
    """
    import datetime

    today = datetime.date.today()
    return (target_date - today).days
