"""Instrument-specific data functions for options, ETFs, bonds, and funds.

Provides enriched views of market data by combining ``market_watch()``
output with parsed instrument metadata (strike, expiry, NAV, maturity, etc.)
and optional per-instrument API calls for open interest.

Also provides ``list_funds()`` which fetches detailed fund information
(NAV, returns, portfolio composition, manager, etc.) from TSETMC Fund API.
"""

import time
import numpy as np
import pandas as pd

from algotik_tse.settings import settings
from algotik_tse.http_client import safe_get
from algotik_tse.core.market_data import market_watch
from algotik_tse.core.parsers import (
    parse_option_name,
    parse_option_symbol,
    parse_bond_name,
    parse_treasury_name,
    _days_until,
)


# ══════════════════════════════════════════════════════════════
#  Options
# ══════════════════════════════════════════════════════════════

def list_options(underlying=None, progress=True):
    """List all active option contracts with parsed metadata.

    Fetches ``market_watch()`` and filters to option instruments
    (InstrumentType 311=call, 312=put), then parses the Name field to
    extract underlying, strike price, and expiry date.

    Parameters
    ----------
    underlying : str, optional
        Filter by underlying symbol name (e.g. ``'اهرم'``).
        If ``None``, returns all options.
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``InsCode`` — Instrument code (str)
        - ``ISIN`` — International Securities ID
        - ``Symbol`` — Option symbol (e.g. ``'ضهرم1116'``)
        - ``Name`` — Full name
        - ``OptionType`` — ``'call'`` or ``'put'``
        - ``Underlying`` — Underlying asset name (e.g. ``'اهرم'``)
        - ``Strike`` — Strike price (int)
        - ``ExpiryJalali`` — Expiry date (Jalali string)
        - ``ExpiryGregorian`` — Expiry date (datetime.date)
        - ``DaysToExpiry`` — Days remaining to expiry (int)
        - ``Last`` — Last traded price (premium)
        - ``Close`` — Closing / weighted avg price
        - ``Yesterday`` — Yesterday reference price
        - ``Volume`` — Trading volume
        - ``Value`` — Trading value (Rials)
        - ``TradeCount`` — Number of trades
        - ``Change`` — Price change
        - ``ChangePct`` — Change percentage
        - ``MaxAllowed`` — Upper price limit
        - ``MinAllowed`` — Lower price limit

    Examples
    --------
    >>> import algotik_tse as att
    >>> options = att.list_options()                      # All options
    >>> calls = att.list_options(underlying='اهرم')       # Just اهرم options
    """
    if progress:
        print("Fetching market data...")

    data = market_watch()
    stocks_df = data['stocks']

    # Filter to options only (311=call, 312=put)
    options_df = stocks_df[stocks_df['InstrumentType'].isin([311, 312])].copy()

    if options_df.empty:
        if progress:
            print("No options found in market data.")
        return pd.DataFrame()

    if progress:
        print(f"Found {len(options_df)} option contracts. Parsing metadata...")

    # Parse Name field for each option
    parsed_rows = []
    for _, row in options_df.iterrows():
        parsed = parse_option_name(row['Name'])
        if parsed:
            parsed_rows.append({
                'InsCode': row['InsCode'],
                'ISIN': row['ISIN'],
                'Symbol': row['Symbol'],
                'Name': row['Name'],
                'OptionType': parsed['option_type'],
                'Underlying': parsed['underlying'],
                'Strike': parsed['strike'],
                'ExpiryJalali': parsed['expiry_jalali'],
                'ExpiryGregorian': parsed['expiry_gregorian'],
                'DaysToExpiry': _days_until(parsed['expiry_gregorian']) if parsed['expiry_gregorian'] else None,
                'Last': row['Last'],
                'Close': row['Close'],
                'Yesterday': row['Yesterday'],
                'Volume': row['Volume'],
                'Value': row['Value'],
                'TradeCount': row['TradeCount'],
                'Change': row['Change'],
                'ChangePct': row['ChangePct'],
                'MaxAllowed': row['MaxAllowed'],
                'MinAllowed': row['MinAllowed'],
            })
        else:
            # Fallback: use symbol prefix for type detection
            opt_type = parse_option_symbol(row['Symbol']) or 'unknown'
            parsed_rows.append({
                'InsCode': row['InsCode'],
                'ISIN': row['ISIN'],
                'Symbol': row['Symbol'],
                'Name': row['Name'],
                'OptionType': opt_type,
                'Underlying': None,
                'Strike': None,
                'ExpiryJalali': None,
                'ExpiryGregorian': None,
                'DaysToExpiry': None,
                'Last': row['Last'],
                'Close': row['Close'],
                'Yesterday': row['Yesterday'],
                'Volume': row['Volume'],
                'Value': row['Value'],
                'TradeCount': row['TradeCount'],
                'Change': row['Change'],
                'ChangePct': row['ChangePct'],
                'MaxAllowed': row['MaxAllowed'],
                'MinAllowed': row['MinAllowed'],
            })

    result = pd.DataFrame(parsed_rows)

    # Filter by underlying if specified
    if underlying and not result.empty:
        result = result[result['Underlying'] == underlying].copy()
        if progress:
            print(f"Filtered to {len(result)} contracts for underlying '{underlying}'.")

    if progress:
        print(f"Done. {len(result)} options returned.")

    return result.reset_index(drop=True)


def get_options_chain(underlying, fetch_oi=False, progress=True):
    """Get a structured options chain for a specific underlying asset.

    Returns calls and puts separated, with the underlying's current price
    and all available expiry dates.

    Parameters
    ----------
    underlying : str
        Underlying symbol name (e.g. ``'اهرم'``, ``'شتران'``).
    fetch_oi : bool, default False
        If True, makes an additional API call per contract to fetch
        open interest (buyOP/sellOP), contract size, and date range.
        **Warning:** This is slow for many contracts due to rate limiting.
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    dict
        Keys:

        - ``calls`` — DataFrame of call options
        - ``puts`` — DataFrame of put options
        - ``underlying_name`` — str, underlying symbol name
        - ``underlying_price`` — int, current price of underlying (from market_watch)
        - ``expiry_dates`` — list of unique expiry dates (Jalali strings)
        - ``market_time`` — str, market time from snapshot

        If ``fetch_oi=True``, the DataFrames also contain:

        - ``OpenInterest`` — Open position count (buyOP)
        - ``ContractSize`` — Number of underlying shares per contract
        - ``BeginDate`` — Contract listing date (Gregorian int YYYYMMDD)
        - ``EndDate`` — Contract expiry date (Gregorian int YYYYMMDD)

    Examples
    --------
    >>> chain = att.get_options_chain('اهرم')
    >>> print(chain['calls'])
    >>> print(chain['puts'])
    >>> print(chain['underlying_price'])
    >>> print(chain['expiry_dates'])
    """
    # Get all options for this underlying
    all_options = list_options(underlying=underlying, progress=progress)

    if all_options.empty:
        return {
            'calls': pd.DataFrame(),
            'puts': pd.DataFrame(),
            'underlying_name': underlying,
            'underlying_price': None,
            'expiry_dates': [],
            'market_time': None,
        }

    # Get underlying price from market_watch
    data = market_watch()
    underlying_price = None
    market_time = data.get('market_time', '')

    # Search for underlying in stocks
    stocks_df = data['stocks']
    # Try exact symbol match first
    match = stocks_df[stocks_df['Symbol'] == underlying]
    if match.empty:
        # Try partial match in Name
        match = stocks_df[stocks_df['Symbol'].str.contains(underlying, na=False)]
    if not match.empty:
        underlying_price = int(match.iloc[0]['Last'])

    # Fetch open interest if requested
    if fetch_oi:
        if progress:
            print(f"Fetching open interest for {len(all_options)} contracts...")
        oi_data = []
        for i, (_, row) in enumerate(all_options.iterrows()):
            oi = _fetch_option_info(row['ISIN'])
            oi_data.append(oi)
            if progress and (i + 1) % 10 == 0:
                print(f"  ... {i + 1}/{len(all_options)} contracts fetched")
        oi_df = pd.DataFrame(oi_data)
        all_options = pd.concat([all_options, oi_df], axis=1)

    # Split into calls and puts
    calls = all_options[all_options['OptionType'] == 'call'].copy()
    puts = all_options[all_options['OptionType'] == 'put'].copy()

    # Sort by strike then expiry
    for df in [calls, puts]:
        if not df.empty:
            df.sort_values(['ExpiryJalali', 'Strike'], inplace=True)
            df.reset_index(drop=True, inplace=True)

    # Unique expiry dates
    expiry_dates = sorted(all_options['ExpiryJalali'].dropna().unique().tolist())

    return {
        'calls': calls,
        'puts': puts,
        'underlying_name': underlying,
        'underlying_price': underlying_price,
        'expiry_dates': expiry_dates,
        'market_time': market_time,
    }


def _fetch_option_info(isin):
    """Fetch option contract details (open interest, contract size, etc.).

    Calls ``GetInstrumentOptionByInstrumentID/{ISIN}`` on cdn.tsetmc.com.

    Parameters
    ----------
    isin : str
        The ISIN of the option instrument (e.g. ``'IRO9AHRM0631'``).

    Returns
    -------
    dict
        Keys: ``OpenInterest``, ``ContractSize``, ``StrikePrice``,
        ``UnderlyingInsCode``, ``BeginDate``, ``EndDate``.

    Example response from API::

        {
            "instrumentOption": {
                "buyOP": 55988,
                "sellOP": 55988,
                "contractSize": 1000,
                "strikePrice": 38000,
                "uaInsCode": "17914401175772326",
                "beginDate": 20251122,
                "endDate": 20260415
            }
        }
    """
    url = settings.url_option_info.format(isin)
    try:
        response = safe_get(url)
        if response is None or response.status_code != 200:
            return _empty_oi()
        data = response.json()
        opt = data.get('instrumentOption', {})
        return {
            'OpenInterest': opt.get('buyOP', 0),
            'ContractSize': opt.get('contractSize', 0),
            'StrikePrice_API': opt.get('strikePrice', 0),
            'UnderlyingInsCode': str(opt.get('uaInsCode', '')),
            'BeginDate': opt.get('beginDate', 0),
            'EndDate': opt.get('endDate', 0),
        }
    except Exception:
        return _empty_oi()


def _empty_oi():
    """Return an empty OI dict for failed fetches."""
    return {
        'OpenInterest': None,
        'ContractSize': None,
        'StrikePrice_API': None,
        'UnderlyingInsCode': None,
        'BeginDate': None,
        'EndDate': None,
    }


# ══════════════════════════════════════════════════════════════
#  ETFs
# ══════════════════════════════════════════════════════════════

def list_etfs(progress=True):
    """List all ETF/fund instruments with NAV and discount/premium.

    Fetches ``market_watch()`` and filters to ETF instruments
    (InstrumentType 305), then computes NAV discount or premium.

    Parameters
    ----------
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``InsCode`` — Instrument code
        - ``ISIN`` — International Securities ID
        - ``Symbol`` — Fund symbol
        - ``Name`` — Full name
        - ``Last`` — Last traded price
        - ``Close`` — Closing / weighted avg price
        - ``Yesterday`` — Yesterday reference price
        - ``Volume`` — Trading volume
        - ``Value`` — Trading value (Rials)
        - ``TradeCount`` — Number of trades
        - ``Low`` / ``High`` — Day's price range
        - ``NAV`` — Net Asset Value per unit
        - ``NAV_Discount`` — ``(Close - NAV) / NAV * 100``.
          Negative = trading at discount, Positive = at premium.
        - ``Change`` / ``ChangePct`` — Price change
        - ``MarketCode`` — Market identifier

    Examples
    --------
    >>> etfs = att.list_etfs()
    >>> discounted = etfs[etfs['NAV_Discount'] < -10]  # > 10% discount
    """
    if progress:
        print("Fetching market data...")

    data = market_watch()
    stocks_df = data['stocks']

    # Filter to ETFs (InstrumentType == 305)
    etfs = stocks_df[stocks_df['InstrumentType'] == 305].copy()

    if etfs.empty:
        if progress:
            print("No ETFs found.")
        return pd.DataFrame()

    # Compute NAV discount/premium
    etfs['NAV_Discount'] = np.nan
    mask = etfs['NAV'] > 0
    etfs.loc[mask, 'NAV_Discount'] = (
        (etfs.loc[mask, 'Close'] - etfs.loc[mask, 'NAV'])
        / etfs.loc[mask, 'NAV'] * 100
    ).round(2)

    # Select and reorder columns
    cols = [
        'InsCode', 'ISIN', 'Symbol', 'Name',
        'Last', 'Close', 'Yesterday',
        'Volume', 'Value', 'TradeCount',
        'Low', 'High',
        'NAV', 'NAV_Discount',
        'Change', 'ChangePct',
        'MarketCode',
    ]
    available_cols = [c for c in cols if c in etfs.columns]
    result = etfs[available_cols].copy()

    if progress:
        nav_count = (result['NAV'] > 0).sum() if 'NAV' in result.columns else 0
        print(f"Done. {len(result)} ETFs found ({nav_count} with NAV data).")

    return result.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════
#  Bonds & Treasury
# ══════════════════════════════════════════════════════════════

def list_bonds(progress=True):
    """List all bond and treasury instruments with parsed maturity dates.

    Fetches ``market_watch()`` and identifies bond/treasury instruments
    by parsing their Name field for maturity date patterns.

    Parameters
    ----------
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``InsCode`` — Instrument code
        - ``ISIN`` — International Securities ID
        - ``Symbol`` — Symbol
        - ``Name`` — Full name
        - ``BondType`` — ``'murabaha'``, ``'treasury'``, ``'ijara'``, ``'salaf'``, ``'other'``
        - ``Ticker`` — Short ticker (e.g. ``'اراد1754'``, ``'اخزا4024'``)
        - ``MaturityJalali`` — Maturity date (Jalali string)
        - ``MaturityGregorian`` — Maturity as datetime.date
        - ``DaysToMaturity`` — Days remaining to maturity
        - ``Last`` — Last traded price
        - ``Close`` — Closing / weighted avg price
        - ``Yesterday`` — Yesterday reference price
        - ``Volume`` — Trading volume
        - ``Value`` — Trading value (Rials)
        - ``TradeCount`` — Number of trades
        - ``Change`` / ``ChangePct`` — Price change

    Examples
    --------
    >>> bonds = att.list_bonds()
    >>> treasury = bonds[bonds['BondType'] == 'treasury']
    >>> active = bonds[bonds['DaysToMaturity'] > 0]
    """
    if progress:
        print("Fetching market data...")

    data = market_watch()
    stocks_df = data['stocks']

    if progress:
        print("Scanning for bonds and treasury instruments...")

    parsed_rows = []
    for _, row in stocks_df.iterrows():
        name = row['Name']
        parsed = None

        # Try treasury first (اسناد خزانه / اخزا)
        if any(kw in name for kw in ['اسناد', 'خزانه', 'اخزا']):
            parsed = parse_treasury_name(name)

        # Try bond (مرابحه, اجاره, etc.)
        if parsed is None and any(kw in name for kw in ['مرابحه', 'اجاره', 'سلف', 'اراد', 'ش.خ']):
            parsed = parse_bond_name(name)

        if parsed:
            days_to_mat = None
            if parsed.get('maturity_gregorian'):
                days_to_mat = _days_until(parsed['maturity_gregorian'])

            parsed_rows.append({
                'InsCode': row['InsCode'],
                'ISIN': row['ISIN'],
                'Symbol': row['Symbol'],
                'Name': name,
                'BondType': parsed['bond_type'],
                'Ticker': parsed.get('ticker') or row['Symbol'],
                'MaturityJalali': parsed['maturity_jalali'],
                'MaturityGregorian': parsed['maturity_gregorian'],
                'DaysToMaturity': days_to_mat,
                'Last': row['Last'],
                'Close': row['Close'],
                'Yesterday': row['Yesterday'],
                'Volume': row['Volume'],
                'Value': row['Value'],
                'TradeCount': row['TradeCount'],
                'Change': row['Change'],
                'ChangePct': row['ChangePct'],
            })

    result = pd.DataFrame(parsed_rows)

    if progress:
        if result.empty:
            print("No bonds/treasury instruments found.")
        else:
            bond_types = result['BondType'].value_counts().to_dict()
            summary = ', '.join(f'{v} {k}' for k, v in bond_types.items())
            print(f"Done. {len(result)} instruments found ({summary}).")

    return result.reset_index(drop=True) if not result.empty else result


# ══════════════════════════════════════════════════════════════
#  Funds — detailed fund data from TSETMC Fund API
# ══════════════════════════════════════════════════════════════

def list_funds(fund_type=None, progress=True):
    """List investment funds with NAV, returns, portfolio composition and manager info.

    Fetches data from the TSETMC Fund API which provides rich information
    not available in ``market_watch()`` or ``list_etfs()``.

    Parameters
    ----------
    fund_type : str or list of str, optional
        Filter by fund category. Valid values:

        - ``'equity'``       — صندوق سرمایه‌گذاری در سهام
        - ``'fixed_income'`` — صندوق درآمد ثابت
        - ``'mixed'``        — صندوق مختلط
        - ``'market_maker'`` — صندوق بازارگردانی
        - ``'venture'``      — صندوق جسورانه
        - ``'project'``      — صندوق پروژه
        - ``'real_estate'``  — صندوق زمین و ساختمان
        - ``'commodity'``    — صندوق کالایی (طلا، نقره، ...)
        - ``'private'``      — صندوق خصوصی
        - ``'fund_of_funds'``— صندوق در صندوق (ابر صندوق)

        If ``None`` (default), returns **all** fund types.
        If a string, returns only that type.
        If a list, returns the union of those types.

    progress : bool, default True
        Print progress messages.

    Returns
    -------
    pd.DataFrame
        Columns (all funds):

        **Identity:**
        - ``fund_name``         — Fund name in Persian (e.g. ``'آرمان آتیه درخشان مس'``)
        - ``fund_type``         — Category label (e.g. ``'equity'``, ``'fixed_income'``)
        - ``reg_no``            — Registration number

        **NAV & Assets:**
        - ``nav_redemption``    — NAV for redemption (per unit)
        - ``nav_subscription``  — NAV for subscription (per unit)
        - ``nav_statistical``   — Statistical NAV (per unit)
        - ``net_asset``         — Total net asset value (Rials)
        - ``units``             — Outstanding units
        - ``inception_date``    — Fund start date (ISO string)

        **Returns (%):**
        - ``return_1d``         — 1-day return
        - ``return_7d``         — 7-day return
        - ``return_30d``        — 30-day return
        - ``return_90d``        — 90-day return (≈ quarterly)
        - ``return_180d``       — 180-day return (≈ semi-annual)
        - ``return_365d``       — 365-day return (≈ annual)
        - ``return_inception``  — Return since inception

        **Portfolio Composition (%):**
        - ``pct_stock``         — Equity allocation
        - ``pct_bond``          — Bond allocation
        - ``pct_deposit``       — Bank deposit allocation
        - ``pct_cash``          — Cash & equivalents
        - ``pct_other``         — Other assets
        - ``pct_top5``          — Top-5 holding concentration

        **Managers & Service Providers:**
        - ``manager``           — Fund manager
        - ``investment_manager``— Investment manager
        - ``custodian``         — Custodian / auditor
        - ``guarantor``         — Guarantor (if any)
        - ``market_maker``      — Market maker (if any)

    Examples
    --------
    >>> import algotik_tse as att
    >>> all_funds = att.list_funds()                             # All funds
    >>> equity = att.list_funds(fund_type='equity')              # Equity only
    >>> fixed = att.list_funds(fund_type='fixed_income')         # Fixed income
    >>> multi = att.list_funds(fund_type=['equity', 'mixed'])    # Equity + Mixed
    >>> gold = att.list_funds(fund_type='commodity')             # Gold/commodity
    >>> top = all_funds.nlargest(10, 'return_365d')              # Best annual return
    """
    # ── Determine which fund types to fetch ───────────────────
    all_type_ids = settings.fund_type_ids
    type_labels = settings.fund_type_labels

    if fund_type is None:
        types_to_fetch = list(all_type_ids.values())
    elif isinstance(fund_type, str):
        if fund_type not in all_type_ids:
            valid = ', '.join(sorted(all_type_ids.keys()))
            print(f"Invalid fund_type '{fund_type}'. Valid types: {valid}")
            return None
        types_to_fetch = [all_type_ids[fund_type]]
    elif isinstance(fund_type, list):
        types_to_fetch = []
        for ft in fund_type:
            if ft not in all_type_ids:
                valid = ', '.join(sorted(all_type_ids.keys()))
                print(f"Invalid fund_type '{ft}'. Valid types: {valid}")
                continue
            types_to_fetch.append(all_type_ids[ft])
        if not types_to_fetch:
            return None
    else:
        print("fund_type must be None, a string, or a list of strings.")
        return None

    # ── Fetch data from API ───────────────────────────────────
    all_rows = []
    fetched = 0
    total = len(types_to_fetch)

    for type_id in types_to_fetch:
        label = type_labels.get(type_id, str(type_id))
        if progress:
            fetched += 1
            print(f"  [{fetched}/{total}] Fetching {label} funds...", flush=True)

        url = settings.url_fund_list.format(type_id)
        try:
            resp = safe_get(url)
            data = resp.json()
            funds_list = data.get('funds', [])
        except Exception as e:
            if progress:
                print(f"    Warning: failed to fetch {label}: {e}")
            continue

        for f in funds_list:
            all_rows.append({
                'fund_name': f.get('mfName', ''),
                'fund_type': label,
                'reg_no': int(f['regNo']) if f.get('regNo') else None,
                # NAV & Assets
                'nav_redemption': f.get('navRed'),
                'nav_subscription': f.get('navSub'),
                'nav_statistical': f.get('navStat'),
                'net_asset': f.get('netAsset'),
                'units': f.get('units'),
                'inception_date': f.get('initiationDate', '')[:10] if f.get('initiationDate') else None,
                # Returns
                'return_1d': f.get('day1Return'),
                'return_7d': f.get('day7Return'),
                'return_30d': f.get('day30Return'),
                'return_90d': f.get('day90Return'),
                'return_180d': f.get('day180Return'),
                'return_365d': f.get('day365Return'),
                'return_inception': f.get('dayFirstReturn'),
                # Portfolio composition
                'pct_stock': f.get('portfolioStock'),
                'pct_bond': f.get('portfolioBond'),
                'pct_deposit': f.get('portfolioDeposit'),
                'pct_cash': f.get('portfolioCash'),
                'pct_other': f.get('portfolioOther'),
                'pct_top5': f.get('portfolioFiveBest'),
                # Managers
                'manager': f.get('manager'),
                'investment_manager': f.get('investmentManager'),
                'custodian': f.get('custodian'),
                'guarantor': f.get('guarantor') if f.get('guarantor') != '----' else None,
                'market_maker': f.get('marketMaker'),
            })

        if progress and len(funds_list) > 0:
            print(f"    → {len(funds_list)} funds")

        # Rate-limit between requests
        if fetched < total:
            time.sleep(settings.rate_limit_delay)

    # ── Build DataFrame ───────────────────────────────────────
    if not all_rows:
        if progress:
            print("No funds found.")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # Sort by fund_type then fund_name
    df = df.sort_values(['fund_type', 'fund_name'], ignore_index=True)

    if progress:
        type_counts = df['fund_type'].value_counts()
        summary = ', '.join(f"{v} {k}" for k, v in type_counts.items())
        print(f"Done. {len(df)} funds total ({summary}).")

    return df
