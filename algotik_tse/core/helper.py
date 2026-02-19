import datetime
import numpy as np
import pandas as pd
from persiantools.jdatetime import JalaliDate
from typing import Optional, Union, List, Tuple

from algotik_tse.settings import settings


def date_fix(start: Optional[str] = None, end: Optional[str] = None,
             start_delta: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Convert start/end date strings (Jalali or Gregorian) to Gregorian ISO format.

    Parameters
    ----------
    start : str, optional
        Start date. Jalali dates (starting with '13', '14', '15') are auto-converted.
        Accepts 'YYYY-MM-DD' or 'YYYYMMDD' format.
    end : str, optional
        End date. Same format rules as ``start``.
    start_delta : str, optional
        Reserved for future use.

    Returns
    -------
    tuple of (str or None, str or None)
        A tuple of ``(new_start, new_end)`` in Gregorian ISO format.
    """
    new_start = None
    new_end = None
    if start is not None and '-' not in start:
        start = start[:4] + "-" + start[4:6] + "-" + start[6:]
    if end is not None and '-' not in end:
        end = end[:4] + "-" + end[4:6] + "-" + end[6:]

    if start is not None:
        two_left_char_start = start[:2]
        if two_left_char_start in ["13", "14", "15"]:
            new_start = JalaliDate.to_gregorian(JalaliDate.fromisoformat(start)).isoformat()
        else:
            new_start = start
    if end is not None:
        two_left_char_end = end[:2]
        if two_left_char_end in ["13", "14", "15"]:
            new_end = JalaliDate.to_gregorian(JalaliDate.fromisoformat(end)).isoformat()
        else:
            new_end = end
    else:
        new_end = end
    return new_start, new_end


def add_date_columns(df: pd.DataFrame, stock_name: str) -> pd.DataFrame:
    """Add Date, J-Date, Weekday, Weekday_fa, and Ticker columns to a DataFrame.

    Assumes the DataFrame index is a DatetimeIndex (named 'Date_base' or similar).

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with DatetimeIndex.
    stock_name : str
        The ticker name to add as a column.

    Returns
    -------
    pd.DataFrame
        DataFrame with added date-related columns.
    """
    df["Date"] = df.index
    df["J-Date"] = df["Date"]
    df['J-Date'] = df['J-Date'].apply(lambda x: x.strftime("%Y-%m-%d"))
    df['J-Date'] = df['J-Date'].apply(
        lambda x: JalaliDate.to_jalali(datetime.datetime.fromisoformat(x)).isoformat())
    df["Weekday_No"] = df["Date"].dt.weekday
    df["Weekday"] = df["Weekday_No"].apply(lambda x: settings.en_weekdays[x])
    df["Weekday_fa"] = df["Weekday_No"].apply(lambda x: settings.fa_weekdays[x])
    df.drop("Weekday_No", axis=1, inplace=True)
    df['Ticker'] = stock_name
    return df


def apply_date_format(df: pd.DataFrame, date_format: str) -> Optional[pd.DataFrame]:
    """Set the DataFrame index based on the chosen date format and drop extra columns.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame that already has 'Date', 'J-Date', 'Weekday', 'Weekday_fa' columns.
    date_format : str
        One of ``'jalali'``, ``'gregorian'``, or ``'both'``.

    Returns
    -------
    pd.DataFrame or None
        The reindexed DataFrame, or ``None`` if an invalid ``date_format`` is given.
    """
    if date_format == "jalali":
        df.set_index("J-Date", drop=True, inplace=True)
        df.drop(columns=["Date", "Weekday"], inplace=True)
    elif date_format == "gregorian":
        df.set_index("Date", drop=True, inplace=True)
        df.drop(columns=["J-Date", "Weekday_fa"], inplace=True)
    elif date_format == "both":
        df.set_index("Date", drop=True, inplace=True)
    else:
        print("please select date_format between 'jalali', 'gregorian', 'both' ")
        return None
    return df


def apply_return_type(df: pd.DataFrame, return_type: Union[str, List, None],
                      default_price: str = 'Close') -> Optional[pd.DataFrame]:
    """Calculate and add return columns to the DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Price DataFrame with at least a column named ``default_price``.
    return_type : str or list or None
        - ``'simple'``: simple 1-day return on ``default_price``.
        - ``'log'``: logarithmic 1-day return on ``default_price``.
        - ``'both'``: both simple and log returns.
        - ``['simple', 'Close', 5]``: simple 5-day return on 'Close' column.
        - ``['log', 'Close', 5]``: log 5-day return on 'Close' column.
        - ``['both', 'Close', 5]``: both 5-day returns on 'Close' column.
        - ``None``: no return columns added.
    default_price : str
        Column name to use for return calculation when ``return_type`` is a string.
        Default is ``'Close'``.

    Returns
    -------
    pd.DataFrame or None
        DataFrame with return columns added, or ``None`` on invalid input.
    """
    if return_type is None:
        return df

    price = default_price
    if isinstance(return_type, str):
        if return_type == 'simple':
            df['returns'] = df[price].pct_change()
        elif return_type == 'log':
            df['returns'] = np.log(df[price] / df[price].shift(1))
        elif return_type == 'both':
            df['simple_returns'] = df[price].pct_change()
            df['log_returns'] = np.log(df[price] / df[price].shift(1))
        else:
            print("return_type should select between 'simple', 'log' or 'both'")
            return None
    elif isinstance(return_type, list) and len(return_type) == 3:
        rt_type, rt_col, rt_period = return_type[0], return_type[1], return_type[2]
        if rt_type == 'simple':
            df['returns'] = df[rt_col].pct_change(rt_period)
        elif rt_type == 'log':
            df['returns'] = np.log(df[rt_col] / df[rt_col].shift(rt_period))
        elif rt_type == 'both':
            df['simple_returns'] = df[rt_col].pct_change(rt_period)
            df['log_returns'] = np.log(df[rt_col] / df[rt_col].shift(rt_period))
        else:
            print("return_type[0] should select between 'simple', 'log' or 'both'")
            return None
    else:
        print("return_type should select between 'simple', 'log' or 'both' "
              "or enter a list like this: ['simple', 'Close', 3]")
        return None
    return df


def filter_by_date_or_values(df: pd.DataFrame, values: int, new_start: Optional[str],
                              new_end: Optional[str]) -> pd.DataFrame:
    """Filter a DataFrame by number of trailing rows or date range.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with a DatetimeIndex.
    values : int
        Number of trailing rows to keep (when > 0 and no date range).
    new_start : str or None
        Start date in Gregorian ISO format.
    new_end : str or None
        End date in Gregorian ISO format.

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame.
    """
    if values != 0:
        df = df.iloc[-values:]
    else:
        if new_end is None:
            df = df.loc[new_start:]
        else:
            df = df.loc[new_start:new_end]
    return df
