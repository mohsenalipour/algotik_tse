"""Market data module — live market watchlist and client type data.

Provides bulk market data from TSETMC in a single API call:

- ``market_watch()``  — Real-time prices, volumes, and comprehensive
  instrument data (symbol, name, EPS, price limits, etc.) for all
  instruments.
- ``market_client_type()``  — Individual (حقیقی) vs institutional (حقوقی)
  trade breakdown for all instruments.
"""

import warnings

import pandas as pd

from ..http_client import safe_get
from ..settings import settings
from ..exceptions import ConnectionError, DataParsingError

# ── helpers ───────────────────────────────────────────────────


def _heven_to_time_str(heven):
    """Convert hEven integer (e.g. 125205) to 'HH:MM:SS' string."""
    try:
        val = int(heven)
        h = val // 10000
        m = (val % 10000) // 100
        s = val % 100
        return f"{h:02d}:{m:02d}:{s:02d}"
    except (ValueError, TypeError):
        return str(heven)


def _safe_int(val, default=0):
    """Convert to int, return *default* on failure.

    Handles float-strings like ``'22964.00'`` by trying
    ``int(float(val))`` as a fallback.
    """
    try:
        return int(val)
    except (ValueError, TypeError):
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default


def _safe_float(val, default=0.0):
    """Convert to float, return *default* on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ── backward-compat shim ─────────────────────────────────────


def market_data():
    """Deprecated — use :func:`market_watch` instead.

    .. deprecated:: 1.0.0
        ``market_data()`` was a placeholder. It now redirects to
        :func:`market_watch`.
    """
    warnings.warn(
        "market_data() is deprecated. Use market_watch() instead.",
        FutureWarning,
        stacklevel=2,
    )
    return market_watch()


# ══════════════════════════════════════════════════════════════
#  market_watch()
# ══════════════════════════════════════════════════════════════


def market_watch():
    """Get live market data for all instruments in one API call.

    Fetches comprehensive market data from the TSETMC MarketWatchInit
    endpoint, including symbol names, ISIN codes, EPS, price limits,
    and much more.

    Returns
    -------
    dict
        A dictionary with the following keys:

        - ``'stocks'`` : pd.DataFrame — Comprehensive data for every
          instrument on TSETMC.

          Columns: ``InsCode``, ``ISIN``, ``Symbol``, ``Name``,
          ``Time``, ``Yesterday``, ``Close``, ``Last``, ``TradeCount``,
          ``Volume``, ``Value``, ``Low``, ``High``, ``EPS``,
          ``PriceYesterday``, ``Flow``,
          ``SectorCode``, ``MaxAllowed``, ``MinAllowed``, ``BaseVolume``,
          ``InstrumentType``, ``NAV``, ``MarketCode``,
          ``Change``, ``ChangePct``

        - ``'market_time'`` : str — Jalali date/time string.

        - ``'index_value'`` : float — Total market index (شاخص کل).

    Raises
    ------
    ConnectionError
        If the HTTP request fails.
    DataParsingError
        If the response format is unexpected.

    Examples
    --------
    >>> import algotik_tse as att
    >>> data = att.market_watch()
    >>> print(data['stocks'].head())
    >>> # Filter regular stocks only
    >>> regular = data['stocks'][data['stocks']['InstrumentType'].isin([300, 303, 309])]
    """
    url = settings.url_market_watch_init
    response = safe_get(url)
    if response is None:
        raise ConnectionError(f"Failed to fetch market watch data from {url}")

    text = response.text.strip()
    if not text:
        raise DataParsingError("Empty response from market watch endpoint")

    parts = text.split("@")
    if len(parts) < 3:
        raise DataParsingError(
            f"Unexpected market watch format: expected at least 3 "
            f"'@'-separated parts, got {len(parts)}"
        )

    # ── Header / market time & index (part 1) ─────────────────
    # Format: "04/11/29 14:11:39,P,3806768.04,..."
    market_time = ""
    index_value = 0.0
    try:
        header_text = parts[1].replace("\n", ",").replace("\r", "")
        header_fields = header_text.split(",")
        if header_fields:
            market_time = header_fields[0].strip()
        if len(header_fields) >= 3:
            index_value = _safe_float(header_fields[2])
    except Exception:
        pass

    # ── Stocks (part 2) ───────────────────────────────────────
    # MarketWatchInit record format (26 fields, ';'-separated):
    #  0: InsCode          — Instrument code (unique ID)
    #  1: ISIN             — e.g. IRO1NORI0001
    #  2: Symbol           — نماد (e.g. نوری)
    #  3: Name             — نام کامل (e.g. پتروشيمي نوري)
    #  4: hEven            — Last trade time (HHMMSS)
    #  5: PDrCotVal        — Yesterday reference price (دیروز)
    #  6: PClosing         — Closing weighted avg (قیمت پایانی)
    #  7: PLast            — Last traded price (آخرین)
    #  8: ZTotTran         — Trade count (تعداد)
    #  9: QTotTran5J       — Volume (حجم)
    # 10: QTotCap          — Value in Rials (ارزش)
    # 11: PriceMin         — Day's low (کمترین)
    # 12: PriceMax         — Day's high (بیشترین)
    # 13: PriceYesterday   — Yesterday actual close / opening
    # 14: EPS              — Earnings per share
    # 15-16: internal metadata
    # 17: Flow             — Market type (1=بازار اول, ...)
    # 18: CS               — Industry/sector code
    # 19: tMax             — Upper price limit (سقف مجاز)
    # 20: tMin             — Lower price limit (کف مجاز)
    # 21: BaseVol          — Base volume / total shares
    # 22: InstrumentCode   — Instrument type (300=stock, 305=ETF, ...)
    # 23: NAV              — Net Asset Value (ETFs only)
    # 24: (empty)
    # 25: MarketCode       — Market identifier (N1, N2, Z1, P1, ...)
    stock_records = []
    stock_data = parts[2].strip() if len(parts) > 2 else ""
    if stock_data:
        for item in stock_data.split(";"):
            fields = item.split(",")
            if len(fields) < 22:
                continue
            try:
                stock_records.append(
                    {
                        "InsCode": fields[0].strip(),
                        "ISIN": fields[1].strip(),
                        "Symbol": fields[2].strip(),
                        "Name": fields[3].strip(),
                        "Time": _heven_to_time_str(fields[4]),
                        "Yesterday": _safe_int(fields[5]),
                        "Close": _safe_int(fields[6]),
                        "Last": _safe_int(fields[7]),
                        "TradeCount": _safe_int(fields[8]),
                        "Volume": _safe_int(fields[9]),
                        "Value": _safe_int(fields[10]),
                        "Low": _safe_int(fields[11]),
                        "High": _safe_int(fields[12]),
                        "EPS": _safe_int(fields[14]),
                        "PriceYesterday": (
                            _safe_int(fields[13]) if len(fields) > 13 else 0
                        ),
                        "Flow": _safe_int(fields[17]) if len(fields) > 17 else 0,
                        "SectorCode": fields[18].strip() if len(fields) > 18 else "",
                        "MaxAllowed": _safe_int(fields[19]) if len(fields) > 19 else 0,
                        "MinAllowed": _safe_int(fields[20]) if len(fields) > 20 else 0,
                        "BaseVolume": _safe_int(fields[21]) if len(fields) > 21 else 0,
                        "InstrumentType": (
                            _safe_int(fields[22]) if len(fields) > 22 else 0
                        ),
                        "NAV": _safe_int(fields[23]) if len(fields) > 23 else 0,
                        "MarketCode": fields[25].strip() if len(fields) > 25 else "",
                    }
                )
            except Exception:
                continue

    stocks_df = pd.DataFrame(stock_records)

    if not stocks_df.empty:
        stocks_df["Change"] = stocks_df["Close"] - stocks_df["Yesterday"]
        stocks_df["ChangePct"] = (
            stocks_df["Change"] / stocks_df["Yesterday"].replace(0, float("nan")) * 100
        ).round(2)
        # Ensure Change is int (int - int = int, but be safe)
        stocks_df["Change"] = stocks_df["Change"].astype(int)

    return {
        "stocks": stocks_df,
        "market_time": market_time,
        "index_value": index_value,
    }


# ══════════════════════════════════════════════════════════════
#  market_client_type()
# ══════════════════════════════════════════════════════════════


def market_client_type():
    """Get individual vs institutional trade data for all instruments.

    Fetches the ClientTypeAll endpoint in a single API call, returning
    today's breakdown of trade counts and volumes between individual
    (حقیقی) and institutional (حقوقی) participants for every instrument.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``InsCode`` — Instrument code (str)
        - ``Buy_I_Count`` — Number of individual (حقیقی) buy trades
        - ``Buy_N_Count`` — Number of institutional (حقوقی) buy trades
        - ``Buy_I_Volume`` — Volume bought by individuals
        - ``Buy_N_Volume`` — Volume bought by institutions
        - ``Sell_I_Count`` — Number of individual sell trades
        - ``Sell_N_Count`` — Number of institutional sell trades
        - ``Sell_I_Volume`` — Volume sold by individuals
        - ``Sell_N_Volume`` — Volume sold by institutions
        - ``Net_I_Volume`` — Net individual volume (buy - sell)
        - ``Net_N_Volume`` — Net institutional volume (buy - sell)

    Raises
    ------
    ConnectionError
        If the HTTP request fails.
    DataParsingError
        If the response format is unexpected.

    Examples
    --------
    >>> import algotik_tse as att
    >>> df = att.market_client_type()
    >>> print(df.head())
    >>> # Filter for net institutional buyers
    >>> buyers = df[df['Net_N_Volume'] > 0]
    """
    url = settings.url_client_type_all
    response = safe_get(url)
    if response is None:
        raise ConnectionError(f"Failed to fetch client type data from {url}")

    text = response.text.strip()
    if not text:
        raise DataParsingError("Empty response from client type endpoint")

    records = []
    for item in text.split(";"):
        fields = item.split(",")
        if len(fields) < 9:
            continue
        try:
            records.append(
                {
                    "InsCode": fields[0],
                    "Buy_I_Count": _safe_int(fields[1]),
                    "Buy_N_Count": _safe_int(fields[2]),
                    "Buy_I_Volume": _safe_int(fields[3]),
                    "Buy_N_Volume": _safe_int(fields[4]),
                    "Sell_I_Count": _safe_int(fields[5]),
                    "Sell_N_Count": _safe_int(fields[6]),
                    "Sell_I_Volume": _safe_int(fields[7]),
                    "Sell_N_Volume": _safe_int(fields[8]),
                }
            )
        except Exception:
            continue

    df = pd.DataFrame(records)

    if not df.empty:
        df["Net_I_Volume"] = df["Buy_I_Volume"] - df["Sell_I_Volume"]
        df["Net_N_Volume"] = df["Buy_N_Volume"] - df["Sell_N_Volume"]

    return df
