import datetime
import requests
import warnings
import pandas as pd
from persiantools.jdatetime import JalaliDate

from algotik_tse.settings import settings
from algotik_tse.core.search import search_stock
from algotik_tse.core.helper import date_fix
from algotik_tse.http_client import safe_get

warnings.simplefilter(action='ignore', category=FutureWarning)

# ── Interval mapping (shared) ────────────────────────────────
_INTERVAL_MAP = {
    '1min': '1min', '1m': '1min', '1': '1min',
    '5min': '5min', '5m': '5min', '5': '5min',
    '15min': '15min', '15m': '15min', '15': '15min',
    '30min': '30min', '30m': '30min', '30': '30min',
    '1h': '1h', '1hour': '1h', '60min': '1h', '60m': '1h', '60': '1h',
    '4h': '4h', '4hour': '4h', '240min': '4h', '240m': '4h', '240': '4h',
    '12h': '12h', '12hour': '12h', '720min': '12h', '720m': '12h', '720': '12h',
    'tick': 'tick', 'ticks': 'tick', 'raw': 'tick',
}


def _parse_heven(heven):
    """Convert hEven integer (e.g. 90019) to hour, minute, second."""
    s = str(heven).zfill(6)
    return int(s[:2]), int(s[2:4]), int(s[4:6])


def _heven_to_time_str(heven):
    """Convert hEven integer to 'HH:MM:SS' string."""
    h, m, s = _parse_heven(heven)
    return "{:02d}:{:02d}:{:02d}".format(h, m, s)


def _validate_interval(interval):
    """Validate interval string and return the pandas resample frequency."""
    interval_key = str(interval).lower().strip()
    if interval_key not in _INTERVAL_MAP:
        print("Invalid interval '{}'. Supported: tick, 1min, 5min, 15min, 30min, 1h, 4h, 12h".format(interval))
        return None
    return _INTERVAL_MAP[interval_key]


def _resolve_web_id(symbol, progress=True):
    """Search for stock and return web_id, or None on failure."""
    web_id = search_stock(search_txt=symbol)
    if web_id is None or len(web_id) == 0:
        print("Stock Not Found, Please try again ...")
        return None
    if web_id.endswith("index") or web_id.endswith("industry"):
        print("Intraday data is not available for indices.")
        return None
    return web_id


def _resample_to_candles(df, resample_freq, price_col='Price', volume_col='Volume',
                         count_col=None):
    """Resample a time-indexed DataFrame into OHLCV candles."""
    ohlcv = df[price_col].resample(resample_freq).ohlc()
    ohlcv.columns = ['Open', 'High', 'Low', 'Close']
    ohlcv['Volume'] = df[volume_col].resample(resample_freq).sum()
    if count_col and count_col in df.columns:
        ohlcv['TradeCount'] = df[count_col].resample(resample_freq).count()
    else:
        ohlcv['TradeCount'] = df[price_col].resample(resample_freq).count()

    # Drop intervals with no data (NaN)
    ohlcv.dropna(subset=['Open'], inplace=True)

    # Convert types — match stock() output format (clean integers)
    for col in ['Open', 'High', 'Low', 'Close']:
        ohlcv[col] = ohlcv[col].astype(int)
    ohlcv['Volume'] = ohlcv['Volume'].astype(int)
    ohlcv['TradeCount'] = ohlcv['TradeCount'].astype(int)
    ohlcv.index.name = 'DateTime'

    return ohlcv


# ──────────────────────────────────────────────────────────────
# Today's tick data (GetTrade endpoint)
# ──────────────────────────────────────────────────────────────
def _fetch_today_trades(web_id):
    """Fetch today's individual trades from GetTrade API."""
    try:
        url = settings.url_intraday_trades.format(web_id)
        resp = safe_get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return None

    trades = data.get('trade', [])
    if not trades:
        return None

    df = pd.DataFrame(trades)

    # Filter out canceled trades
    if 'canceled' in df.columns:
        df = df[df['canceled'] != 1].copy()

    required_cols = ['nTran', 'hEven', 'qTitTran', 'pTran']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return None

    df = df[required_cols].copy()
    df.rename(columns={
        'nTran': 'TradeNo',
        'hEven': 'Time_raw',
        'qTitTran': 'Volume',
        'pTran': 'Price',
    }, inplace=True)

    df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce').fillna(0).astype(int)
    df['Price'] = pd.to_numeric(df['Price'], errors='coerce')
    df = df[df['Price'] > 0].copy()

    if df.empty:
        return None

    df['Time'] = df['Time_raw'].apply(_heven_to_time_str)
    today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
    df['DateTime'] = pd.to_datetime(today_str + ' ' + df['Time'])
    df.sort_values('TradeNo', inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df


# ──────────────────────────────────────────────────────────────
# Historical intraday data (ClosingPriceHistory endpoint)
# ──────────────────────────────────────────────────────────────
def _fetch_historical_day(web_id, greg_date_str):
    """Fetch intraday snapshots for one historical date.

    Parameters
    ----------
    web_id : str
        Instrument code.
    greg_date_str : str
        Gregorian date in 'YYYYMMDD' format.

    Returns
    -------
    pd.DataFrame or None
        DataFrame with columns [DateTime, Price, Volume, TradeCount].
        Volume is incremental (per snapshot), not cumulative.
    """
    try:
        url = settings.url_intraday_history.format(web_id, greg_date_str)
        resp = safe_get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return None

    snapshots = data.get('closingPriceHistory', [])
    if not snapshots:
        return None

    df = pd.DataFrame(snapshots)

    required_cols = ['hEven', 'pDrCotVal', 'qTotTran5J', 'zTotTran']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return None

    df = df[required_cols].copy()
    df.rename(columns={
        'hEven': 'Time_raw',
        'pDrCotVal': 'Price',
        'qTotTran5J': 'CumVolume',
        'zTotTran': 'CumTradeCount',
    }, inplace=True)

    df['Price'] = pd.to_numeric(df['Price'], errors='coerce')
    df['CumVolume'] = pd.to_numeric(df['CumVolume'], errors='coerce').fillna(0)
    df['CumTradeCount'] = pd.to_numeric(df['CumTradeCount'], errors='coerce').fillna(0)

    # Remove zero-price rows
    df = df[df['Price'] > 0].copy()
    if df.empty:
        return None

    # Sort by time
    df.sort_values('Time_raw', inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Calculate incremental volume and trade count from cumulative values
    df['Volume'] = df['CumVolume'].diff().fillna(df['CumVolume'].iloc[0]).clip(lower=0).astype(int)
    df['TradeCount'] = df['CumTradeCount'].diff().fillna(df['CumTradeCount'].iloc[0]).clip(lower=0).astype(int)

    # Parse time and build DateTime
    df['Time'] = df['Time_raw'].apply(_heven_to_time_str)

    # Convert greg_date_str (YYYYMMDD) to date string
    date_str = "{}-{}-{}".format(greg_date_str[:4], greg_date_str[4:6], greg_date_str[6:8])
    df['DateTime'] = pd.to_datetime(date_str + ' ' + df['Time'])

    return df[['DateTime', 'Price', 'Volume', 'TradeCount']].copy()


def _generate_date_range(start_greg, end_greg):
    """Generate list of date strings (YYYYMMDD) between start and end (inclusive),
    excluding Thursdays (weekday=3) and Fridays (weekday=4) — Iranian weekend."""
    start_dt = datetime.date.fromisoformat(start_greg)
    end_dt = datetime.date.fromisoformat(end_greg)
    dates = []
    current = start_dt
    while current <= end_dt:
        # Skip Iranian weekends: Thursday=3, Friday=4
        if current.weekday() not in (3, 4):
            dates.append(current.strftime('%Y%m%d'))
        current += datetime.timedelta(days=1)
    return dates


# ──────────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────────
def stock_intraday(symbol='شتران', interval='1min', start=None, end=None,
                   progress=True, **kwargs):
    """
    Get intraday trade data for a symbol and aggregate into OHLCV candles.

    - **No dates** (start=None, end=None): fetches today's live tick data
      using the GetTrade endpoint (individual trades).
    - **With dates**: fetches historical intraday snapshots using the
      ClosingPriceHistory endpoint. Supports single-day or multi-day ranges.

    :param symbol:  Stock symbol name in Persian.
                        Default value is 'شتران'.
    :param interval:    Candle interval for resampling. Supported values:
                            'tick'  — raw tick/snapshot data (no aggregation)
                            '1min'  — 1-minute candles
                            '5min'  — 5-minute candles
                            '15min' — 15-minute candles
                            '30min' — 30-minute candles
                            '1h'    — 1-hour candles
                        Default value is '1min'.
    :param start:       Start date for historical intraday data.
                        Accepts Jalali ('1404-11-06') or Gregorian ('2026-01-26').
                        If only start is given, fetches that single day.
                        Default value is None (today's data).
    :param end:         End date for historical intraday data.
                        Same format as start.
                        Default value is None.
    :param progress:    if True, show progress messages in console.
                        Default value is True.

    :return: pandas DataFrame with OHLCV candles indexed by DateTime,
             or raw data if interval='tick'.
             Returns None on error.

    Example usage::

        import algotik_tse as att

        # Today's 1-minute candles
        df = att.stock_intraday('شتران')

        # Today's raw tick data
        ticks = att.stock_intraday('شتران', interval='tick')

        # Historical single day — 5-minute candles
        df = att.stock_intraday('شتران', interval='5min', start='1404-11-06')

        # Historical multi-day — 1-minute candles
        df = att.stock_intraday('شتران', interval='1min',
                                start='1404-11-01', end='1404-11-06')
    """
    # Backward compatibility: accept deprecated 'stock_name' keyword
    if symbol == 'شتران' and 'stock_name' in kwargs:
        symbol = kwargs.pop('stock_name')

    # ── Validate interval ─────────────────────────────────────────
    resample_freq = _validate_interval(interval)
    if resample_freq is None:
        return None

    # ── Resolve stock ─────────────────────────────────────────────
    if progress:
        if start is not None:
            msg = "Getting historical intraday data for {}...".format(symbol)
        else:
            msg = "Getting intraday data for {}...".format(symbol)
        print(msg, flush=True)

    web_id = _resolve_web_id(symbol, progress)
    if web_id is None:
        return None

    # ══════════════════════════════════════════════════════════════
    # PATH A: Historical intraday (start/end provided)
    # ══════════════════════════════════════════════════════════════
    if start is not None:
        # Convert dates to Gregorian
        start_greg, end_greg = date_fix(start, end)
        if start_greg is None:
            print("Invalid start date: {}".format(start))
            return None
        if end_greg is None:
            end_greg = start_greg  # Single day

        # Generate list of potential trading days
        date_list = _generate_date_range(start_greg, end_greg)
        if not date_list:
            print("No trading days in the specified range.")
            return None

        if progress:
            print("Fetching {} day(s) of intraday data...".format(len(date_list)), flush=True)

        all_frames = []
        fetched_days = 0
        for i, date_str in enumerate(date_list):
            df_day = _fetch_historical_day(web_id, date_str)
            if df_day is not None and not df_day.empty:
                all_frames.append(df_day)
                fetched_days += 1
                if progress:
                    jdate = JalaliDate(
                        datetime.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
                    )
                    print("  Day {}/{}: {} ({}) — {} snapshots".format(
                        i + 1, len(date_list), date_str, jdate, len(df_day)), flush=True)

        if not all_frames:
            print("No intraday data found for {} in the specified date range.".format(symbol))
            return None

        df = pd.concat(all_frames, ignore_index=True)
        df.sort_values('DateTime', inplace=True)
        df.reset_index(drop=True, inplace=True)

        # ── Return raw snapshot data if tick requested ────────────
        if resample_freq == 'tick':
            df.set_index('DateTime', inplace=True)
            df.index.name = 'DateTime'
            if progress:
                print("Historical snapshot data ready! {} snapshots across {} day(s) for {}".format(
                    len(df), fetched_days, symbol))
            return df

        # ── Resample into candles ─────────────────────────────────
        df.set_index('DateTime', inplace=True)
        ohlcv = _resample_to_candles(df, resample_freq, price_col='Price',
                                     volume_col='Volume', count_col='TradeCount')

        if progress:
            print("Historical {} candles ready! {} candles across {} day(s) for {}".format(
                interval, len(ohlcv), fetched_days, symbol))
        return ohlcv

    # ══════════════════════════════════════════════════════════════
    # PATH B: Today's live data (no start/end)
    # ══════════════════════════════════════════════════════════════
    df = _fetch_today_trades(web_id)
    if df is None:
        print("No trade data available for {} today.".format(symbol))
        return None

    # ── Return raw tick data if requested ─────────────────────────
    if resample_freq == 'tick':
        df_tick = df[['DateTime', 'TradeNo', 'Price', 'Volume']].copy()
        df_tick.set_index('DateTime', inplace=True)
        df_tick.index.name = 'DateTime'

        try:
            jdate = JalaliDate.today()
            df_tick['J-Date'] = str(jdate)
        except Exception:
            pass

        if progress:
            print("Tick data ready! {} trades for {}".format(len(df_tick), symbol))
        return df_tick

    # ── Resample into OHLCV candles ───────────────────────────────
    df.set_index('DateTime', inplace=True)
    ohlcv = _resample_to_candles(df, resample_freq, price_col='Price',
                                 volume_col='Volume', count_col='TradeNo')

    if progress:
        print("Intraday {} candles ready! {} candles for {}".format(
            interval, len(ohlcv), symbol))

    return ohlcv
