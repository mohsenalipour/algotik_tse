import io
import datetime
import requests
import warnings
import pandas as pd
from persiantools import characters

from algotik_tse.settings import settings
from algotik_tse.core.search import search_stock
from algotik_tse.core.helper import (
    date_fix,
    add_date_columns,
    apply_date_format,
    apply_return_type,
    filter_by_date_or_values,
)
from algotik_tse.http_client import safe_get

warnings.simplefilter(action="ignore", category=FutureWarning)


def stock(
    symbol="",
    start=None,
    end=None,
    limit=0,
    raw=False,
    auto_adjust=True,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    dropna=True,
    adjust_volume=False,
    return_type=None,
    ascending=True,
    save_path=None,
    **kwargs
):
    """
    Get symbol or symbols price history from tsetmc
    :param symbol:           symbol name in persian, or a list of symbol in
                                persian (['شتران', 'آریا'])
                            Default value is 'شتران'.
    :param start:           you can choose strat date (from) to get historical price.
                            enter date in jalali only in isoformat ('1401-10-01')
                                and gregorian in isoformat("2022-12-22") or
                                ("2022") or ("2022-12")
                            Default value is None.
                            if start=None and end=None, value can apply to price data.
    :param end:             you can choos end date (to) to get historical price.
                            enter date in jalali only in isoformat ('1401-10-01')
                                and gregorian in isoformat ("2022-12-22") or
                                ("2022") or ("2022-12")
                            Default value is None.
                            if start=None and end=None, 'values' can apply to price data.
    :param values:          Specifies the number of price data since today
                            Default value is 225.
                            'values' can be applied when start=None and end=None.
    :param tse_format:      if True you can get all historical data in tse .csv format
                            Default value is False.
                            if tse_format=True, ignore auto_adjust, output_type,
                                date_format, adjust_volume!
    :param auto_adjust:     if True, adjust all OHLC price, with symbol splits and dps.
                            Default value is True.
                            if False, show 'Adj Close' column in output
    :param output_type:     you can choose between 'standard' and 'complete'.
                            Default value is 'standard'.
                            if output_type='standard', you get OHLC and Volume
                                (and 'Adj Close' if auto_adjust=False) in output.
                            if output_type='complete', you get OHLC and Volume
                                (and 'Adj Close' if auto_adjust=False) and 'No.',
                                'Value', 'Weekday', 'Ticker' in output.
    :param date_format:     you can choose between 'jalali' and 'gregorian' and 'both'.
                            Default value is 'jalali'.
                            if date_format='jalali', you get historical price with
                                jalali date index and 'Weekday_fa' in complete mode
                                in output.
                            if output_type='gregorian', you get historical price
                                with gregorian date index and 'Weekday' in complete
                                mode in output.
                            if output_type='both', you get historical price with
                                gregorian date index and 'J-Date'(jalali date),
                                'Weekday', 'Weekday_fa' in complete mode in output.
    :param progress:        if True, show progress and report in console.
                            Default value is True.
    :param save_to_file:    if True, save symbol(s) historical data with customized
                                columns in .csv format.
                            Default value is False.
                            the file name is 'stock.csv' in same root that
                                tsemodule6 is there. for example: 'شتران.csv'
    :param multi_stock_drop:if True, when you enter stocks list, it will delete
                                rows of none data (dropna) in combined historical df.
                            Default value is True.
    :param adjust_volume:   if True, when output_type='complete' you can get
                                'Adj Volume' in output.
                            Default value is False.
    :param return_type:     you can choose between 'simple', 'log' and 'both', or enter ['simple', 'Close', 5] format.
                            if return_type='simple', you get simple return in 1 day on Adj Close.
                                with simple return 'returns' in complete mode in output.
                            if return_type='log', you get log return in 1 day on Adj Close.
                                with log return 'returns' in complete mode in output.
                            if return_type='both', you get simple and log return in 1 day on Adj Close.
                                with both return 'simple_returns' and 'log_returns' in complete mode in output.
                            if return_type=['simple', 'Close', 5], you get simple return in 5 day on Close.
                                with this 'returns' in complete mode in output.

    :return: pandas dataframe or None
    """
    # Backward compatibility: accept deprecated keyword names
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if "values" in kwargs:
        limit = kwargs.pop("values")
    if "tse_format" in kwargs:
        raw = kwargs.pop("tse_format")
    if "multi_stock_drop" in kwargs:
        dropna = kwargs.pop("multi_stock_drop")

    # Support legacy output_type value 'complete' → 'full'
    if output_type == "complete":
        output_type = "full"

    # Internal aliases for existing code
    values = limit
    tse_format = raw
    multi_stock_drop = dropna

    def _get_stock(
        stock_name,
        mstart,
        mend,
        mvalues,
        mtse_format,
        mauto_adjust,
        moutput_type,
        mdate_format,
    ):
        web_id = search_stock(search_txt=stock_name)
        _price_base_url = settings.url_price_history
        isIndex = False
        isIndustry = False
        if web_id[-5:] == "index":
            web_id = web_id[:-5]
            _price_base_url = settings.url_index_history
            isIndex = True
        elif web_id[-8:] == "industry":
            web_id = web_id[:-8]
            _price_base_url = settings.url_industry_history
            isIndustry = True
        new_start, new_end = date_fix(start=mstart, end=mend)
        if new_start is not None or new_end is not None:
            mvalues = 0
        if isIndustry:
            industry_name = {
                "32453344048876642": "Basic Metals",
                "70077233737515808": "Cement",
                "20213770409093165": "Automobile",
                "33626672012415176": "Chemical",
                "24733701189547084": "Communication",
                "25163959460949732": "Other Financial",
                "59288237226302898": "Textiles",
                "57616105980228781": "Tile and Ceramic",
                "25766336681098389": "Publishing",
                "62691002126902464": "Mines",
                "69306841376553334": "Leather Products",
            }
            try:
                data = {
                    "<TICKER>": [],
                    "<DTYYYYMMDD>": [],
                    "<HIGH>": [],
                    "<LOW>": [],
                    "<CLOSE>": [],
                    "<PER>": [],
                }
                fopen = safe_get(_price_base_url.format(web_id)).json()
                day_dict = {
                    value["dEven"]: {
                        "Close": value["xNivInuClMresIbs"],
                        "High": value["xNivInuPhMresIbs"],
                        "Low": value["xNivInuPbMresIbs"],
                    }
                    for value in fopen["indexB2"]
                }
                for key, value in day_dict.items():
                    data["<TICKER>"].append(industry_name[web_id])
                    date_str = str(key)
                    date_iso = date_str[:4] + "-" + date_str[4:6] + "-" + date_str[6:]
                    data["<DTYYYYMMDD>"].append(datetime.date.fromisoformat(date_iso))
                    data["<HIGH>"].append(value["High"])
                    data["<LOW>"].append(value["Low"])
                    data["<CLOSE>"].append(value["Close"])
                    data["<PER>"].append("D")

                df = pd.DataFrame(
                    data,
                    columns=data.keys(),
                    index=pd.DatetimeIndex(data["<DTYYYYMMDD>"]),
                )
                df.index.names = ["<DTYYYYMMDD>"]
                df.drop(columns=["<DTYYYYMMDD>"], inplace=True)

                if mvalues is not None or mstart is not None or mend is not None:
                    df = filter_by_date_or_values(df, mvalues, new_start, new_end)

                if mtse_format:
                    return df
                else:
                    df.index.rename("Date_base", inplace=True)
                    df.drop(["<TICKER>", "<PER>"], axis=1, inplace=True)
                    df.rename(
                        columns={"<HIGH>": "High", "<LOW>": "Low", "<CLOSE>": "Close"},
                        inplace=True,
                    )
                    df = df.loc[
                        :,
                        [
                            "High",
                            "Low",
                            "Close",
                        ],
                    ]
                    df = add_date_columns(df, stock_name)

                    df = apply_date_format(df, mdate_format)
                    if df is None:
                        return None
                    if moutput_type == "standard":
                        df = df.loc[
                            :,
                            [
                                "High",
                                "Low",
                                "Close",
                            ],
                        ]
                    elif moutput_type == "full":
                        pass
                    else:
                        print("output_type should select between 'standard' or 'full'")
                        return None

                    df = apply_return_type(df, return_type, default_price="Close")
                    if df is None:
                        return None

                    return df
            except requests.exceptions.RequestException:
                print("Connection Error!")
                return None
            except Exception as e:
                print("Error processing industry data: {}".format(e))
                return None
        if isIndex:
            index_names = {
                "32097828799138957": "Overall Index",
                "67130298613737946": "Total Equal Weighted Index",
                "5798407779416661": "Total Price Index",
                "8384385859414435": "Equal Weighted Price Index",
                "49579049405614711": "Free Float Index",
                "62752761908615603": "OTC Main Board Index",
                "71704845530629737": "OTC Secondary Board Index",
                "43754960038275285": "Industry Index",
                "10523825119011581": "Top 30 Index",
                "46342955726788357": "Top 50 Index",
            }
            try:
                data = {
                    "<TICKER>": [],
                    "<DTYYYYMMDD>": [],
                    "<FIRST>": [],
                    "<HIGH>": [],
                    "<LOW>": [],
                    "<CLOSE>": [],
                    "<VOL>": [],
                    "<PER>": [],
                    "<OPEN>": [],
                    "<LAST>": [],
                }
                fopen = safe_get(_price_base_url.format(web_id)).text.split(";")
                for dt in fopen:
                    dts = dt.split(",")
                    data["<TICKER>"].append(index_names[web_id])
                    date_iso = dts[0][:4] + "-" + dts[0][4:6] + "-" + dts[0][6:]
                    data["<DTYYYYMMDD>"].append(datetime.date.fromisoformat(date_iso))
                    data["<FIRST>"].append(float(dts[3]))
                    data["<HIGH>"].append(float(dts[1]))
                    data["<LOW>"].append(float(dts[2]))
                    data["<CLOSE>"].append(float(dts[6]))
                    data["<VOL>"].append(float(dts[5]))
                    data["<PER>"].append("D")
                    data["<OPEN>"].append(float(dts[3]))
                    data["<LAST>"].append(float(dts[4]))

                df = pd.DataFrame(
                    data,
                    columns=data.keys(),
                    index=pd.DatetimeIndex(data["<DTYYYYMMDD>"]),
                )
                df.index.names = ["<DTYYYYMMDD>"]
                df.drop(columns=["<DTYYYYMMDD>"], inplace=True)

                if mvalues is not None or mstart is not None or mend is not None:
                    df = filter_by_date_or_values(df, mvalues, new_start, new_end)

                if mtse_format:
                    return df
                else:
                    df.index.rename("Date_base", inplace=True)
                    df.drop(["<TICKER>", "<PER>", "<OPEN>"], axis=1, inplace=True)
                    df.rename(
                        columns={
                            "<FIRST>": "Open",
                            "<HIGH>": "High",
                            "<LOW>": "Low",
                            "<CLOSE>": "Adj Close",
                            "<VOL>": "Volume",
                            "<LAST>": "Close",
                        },
                        inplace=True,
                    )
                    df = df.loc[
                        :,
                        [
                            "Open",
                            "High",
                            "Low",
                            "Close",
                            "Adj Close",
                            "Volume",
                        ],
                    ]
                    df = add_date_columns(df, stock_name)

                    if mauto_adjust:
                        df.drop("Adj Close", axis=1, inplace=True)
                        df = apply_date_format(df, mdate_format)
                        if df is None:
                            return None
                        if moutput_type == "standard":
                            df = df.loc[:, ["Open", "High", "Low", "Close", "Volume"]]
                        elif moutput_type == "full":
                            pass
                        else:
                            print(
                                "output_type should select between 'standard' or 'full'"
                            )
                            return None
                    else:
                        df = apply_date_format(df, mdate_format)
                        if df is None:
                            return None
                        if moutput_type == "standard":
                            df = df.loc[
                                :,
                                ["Open", "High", "Low", "Close", "Adj Close", "Volume"],
                            ]
                        elif moutput_type == "full":
                            pass
                        else:
                            print(
                                "output_type should select between 'standard' or 'full'"
                            )
                            return None

                    price = "Close" if mauto_adjust else "Adj Close"
                    df = apply_return_type(df, return_type, default_price=price)
                    if df is None:
                        return None

                    return df
            except requests.exceptions.RequestException:
                print("Connection Error!")
                return None
            except Exception as e:
                print("Error processing index data: {}".format(e))
                return None
        else:
            try:
                fopen = safe_get(_price_base_url.format(web_id)).content
                df = pd.read_csv(
                    io.StringIO(fopen.decode("utf-8")),
                    index_col="<DTYYYYMMDD>",
                    parse_dates=True,
                )
                df = df[::-1]
                if mvalues is not None or mstart is not None or mend is not None:
                    df = filter_by_date_or_values(df, mvalues, new_start, new_end)

                if mtse_format:
                    return df
                else:
                    df.index.rename("Date_base", inplace=True)
                    df.drop(["<TICKER>", "<PER>"], axis=1, inplace=True)
                    df.rename(
                        columns={
                            "<FIRST>": "Open",
                            "<HIGH>": "High",
                            "<LOW>": "Low",
                            "<CLOSE>": "Final",
                            "<VALUE>": "Value",
                            "<VOL>": "Volume",
                            "<OPENINT>": "No.",
                            "<OPEN>": "Yesterday-Final",
                            "<LAST>": "Close",
                        },
                        inplace=True,
                    )
                    df = df.loc[
                        :,
                        [
                            "Open",
                            "High",
                            "Low",
                            "Close",
                            "Final",
                            "Volume",
                            "Yesterday-Final",
                            "No.",
                            "Value",
                        ],
                    ]
                    df["Final+1"] = df["Final"].shift(1)
                    df["pos"] = df.apply(
                        lambda x: (
                            x["Yesterday-Final"]
                            if (
                                (x["Yesterday-Final"] != 0)
                                and (x["Yesterday-Final"] != 1000)
                            )
                            else (
                                x["Yesterday-Final"]
                                if (pd.isnull(x["Final+1"]))
                                else x["Final+1"]
                            )
                        ),
                        axis=1,
                    )
                    df["Yesterday-Final"] = df["pos"]
                    df.drop(columns=["Final+1", "pos"], inplace=True)
                    df["coef"] = (df["Yesterday-Final"].shift(-1) / df["Final"]).fillna(
                        1.0
                    )
                    df["Adj coef"] = df.iloc[::-1]["coef"].cumprod().iloc[::-1]
                    df["Adj Vol coef"] = 1 / df["Adj coef"]
                    df["Adj Close"] = (df["Close"] * df["Adj coef"]).apply(
                        lambda x: int(x)
                    )
                    df["Adj Open"] = (df["Open"] * df["Adj coef"]).apply(
                        lambda x: int(x)
                    )
                    df["Adj High"] = (df["High"] * df["Adj coef"]).apply(
                        lambda x: int(x)
                    )
                    df["Adj Low"] = (df["Low"] * df["Adj coef"]).apply(lambda x: int(x))
                    df["Adj Final"] = (df["Final"] * df["Adj coef"]).apply(
                        lambda x: int(x)
                    )
                    df["Adj Volume"] = (df["Volume"] * df["Adj Vol coef"]).apply(
                        lambda x: int(x)
                    )
                    df.drop(columns=["coef", "Adj coef", "Adj Vol coef"], inplace=True)
                    df = add_date_columns(df, stock_name)
                    if mauto_adjust:
                        if adjust_volume:
                            df = df.loc[
                                :,
                                [
                                    "Adj Open",
                                    "Adj High",
                                    "Adj Low",
                                    "Adj Close",
                                    "Adj Final",
                                    "Volume",
                                    "Adj Volume",
                                    "No.",
                                    "Value",
                                    "Date",
                                    "J-Date",
                                    "Weekday",
                                    "Weekday_fa",
                                    "Ticker",
                                ],
                            ]
                        else:
                            df = df.loc[
                                :,
                                [
                                    "Adj Open",
                                    "Adj High",
                                    "Adj Low",
                                    "Adj Close",
                                    "Adj Final",
                                    "Volume",
                                    "No.",
                                    "Value",
                                    "Date",
                                    "J-Date",
                                    "Weekday",
                                    "Weekday_fa",
                                    "Ticker",
                                ],
                            ]
                        df.rename(
                            columns={
                                "Adj Open": "Open",
                                "Adj High": "High",
                                "Adj Low": "Low",
                                "Adj Close": "Close",
                                "Adj Final": "Final",
                            },
                            inplace=True,
                        )
                        df = apply_date_format(df, mdate_format)
                        if df is None:
                            return None
                        if moutput_type == "standard":
                            df = df.loc[:, ["Open", "High", "Low", "Close", "Volume"]]
                        elif moutput_type == "full":
                            pass
                        else:
                            print(
                                "output_type should select between 'standard' or 'full'"
                            )
                            return None
                    else:
                        if adjust_volume:
                            df = df.loc[
                                :,
                                [
                                    "Open",
                                    "High",
                                    "Low",
                                    "Close",
                                    "Final",
                                    "Adj Close",
                                    "Volume",
                                    "Adj Volume",
                                    "No.",
                                    "Value",
                                    "Date",
                                    "J-Date",
                                    "Weekday",
                                    "Weekday_fa",
                                    "Ticker",
                                ],
                            ]
                        else:
                            df = df.loc[
                                :,
                                [
                                    "Open",
                                    "High",
                                    "Low",
                                    "Close",
                                    "Final",
                                    "Adj Close",
                                    "Volume",
                                    "No.",
                                    "Value",
                                    "Date",
                                    "J-Date",
                                    "Weekday",
                                    "Weekday_fa",
                                    "Ticker",
                                ],
                            ]
                        df = apply_date_format(df, mdate_format)
                        if df is None:
                            return None
                        if moutput_type == "standard":
                            df = df.loc[
                                :,
                                ["Open", "High", "Low", "Close", "Adj Close", "Volume"],
                            ]
                        elif moutput_type == "full":
                            pass
                        else:
                            print(
                                "output_type should select between 'standard' or 'full'"
                            )
                            return None

                    price = "Close" if mauto_adjust else "Adj Close"
                    df = apply_return_type(df, return_type, default_price=price)
                    if df is None:
                        return None
                    return df
            except requests.exceptions.RequestException:
                print("Connection Error!")
                return None
            except Exception as e:
                print("Stock Not Found or data error: {}".format(e))
                return None

    import os

    def _save_csv(df, filename):
        """Save DataFrame to CSV, respecting save_path."""
        if save_path:
            os.makedirs(save_path, exist_ok=True)
            filepath = os.path.join(save_path, filename)
        else:
            filepath = filename
        df.to_csv(filepath, encoding="utf-8-sig")

    def _apply_ascending(df):
        """Sort by index ascending/descending based on user preference."""
        if df is not None and not ascending:
            return df.iloc[::-1]
        return df

    if symbol == "":
        symbol = "شتران"
        if progress:
            print("1/1: Getting historical price of {}".format(symbol))
        symbol = characters.ar_to_fa(symbol).strip("\u200c").strip()
        df = _get_stock(
            stock_name=symbol,
            mstart=start,
            mend=end,
            mvalues=values,
            mtse_format=tse_format,
            mauto_adjust=auto_adjust,
            moutput_type=output_type,
            mdate_format=date_format,
        )
        if progress and df is not None:
            print("1/1: Completed!")
        if save_to_file and df is not None:
            if progress:
                print("Saving to file: {}.csv".format(symbol))
            _save_csv(df, symbol + ".csv")
        return _apply_ascending(df)
    else:
        if isinstance(symbol, str):
            if progress:
                print("1/1: Getting historical price of {}".format(symbol))
            symbol = characters.ar_to_fa(symbol).strip("\u200c").strip()
            df = _get_stock(
                stock_name=symbol,
                mstart=start,
                mend=end,
                mvalues=values,
                mtse_format=tse_format,
                mauto_adjust=auto_adjust,
                moutput_type=output_type,
                mdate_format=date_format,
            )
            if progress and df is not None:
                print("1/1: Completed!")
            if save_to_file and df is not None:
                if progress:
                    print("Saving to file: {}.csv".format(symbol))
                _save_csv(df, symbol + ".csv")
            return _apply_ascending(df)
        elif isinstance(symbol, list):
            n = 1
            df_dict = {}
            file_name_str = ""
            for stk in symbol:
                if progress:
                    print(
                        "{}/{}: Getting historical price of {}".format(
                            n, len(symbol), stk
                        )
                    )
                stk = characters.ar_to_fa(stk).strip("\u200c").strip()
                df = _get_stock(
                    stock_name=stk,
                    mstart=start,
                    mend=end,
                    mvalues=values,
                    mtse_format=tse_format,
                    mauto_adjust=auto_adjust,
                    moutput_type=output_type,
                    mdate_format=date_format,
                )
                if df is not None:
                    file_name_str += "-" + stk
                    df_dict[stk] = df
                else:
                    print("{} not Found!".format(stk))
                n += 1
            if progress:
                print("{}/{} Completed!".format(len(symbol), len(symbol)))

            if len(list(df_dict.keys())) == 0:
                print("None of the entered stocks exist!!")
                return None
            elif len(list(df_dict.keys())) == 1:
                df = df_dict[list(df_dict.keys())[0]]
                if save_to_file and df is not None:
                    if progress:
                        print("Saving to file: {}.csv".format(file_name_str[1:]))
                    _save_csv(df, file_name_str[1:] + ".csv")
                return _apply_ascending(df)
            else:
                df = pd.concat(df_dict, axis=1)
                multi_assets_columns = df.columns
                reversed_multi_assets_columns = []
                for column_index in multi_assets_columns:
                    reversed_multi_assets_columns.append(column_index[::-1])
                new_index = pd.MultiIndex.from_tuples(reversed_multi_assets_columns)
                df.columns = new_index

                if multi_stock_drop:
                    df.dropna(inplace=True)
                if save_to_file and df is not None:
                    if progress:
                        print("Saving to file: {}.csv".format(file_name_str[1:]))
                    _save_csv(df, file_name_str[1:] + ".csv")
                return _apply_ascending(df)


def stock_RI(
    symbol="",
    start=None,
    end=None,
    limit=0,
    raw=False,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    dropna=True,
    ascending=True,
    save_path=None,
    **kwargs
):
    """
    Get symbol or symbols retail/institutional history from tsetmc
    :param symbol:           symbol name in persian, or a list of symbol in
                                persian (['شتران', 'آریا'])
                            Default value is 'شتران'.
    :param start:           you can choose strat date (from) to get historical RETAIL/institutional.
                            enter date in jalali only in isoformat ('1401-10-01')
                                and gregorian in isoformat("2022-12-22") or
                                ("2022") or ("2022-12")
                            Default value is None.
                            if start=None and end=None, value can apply to RETAIL/institutional data.
    :param end:             you can choos end date (to) to get historical RETAIL/institutional.
                            enter date in jalali only in isoformat ('1401-10-01')
                                and gregorian in isoformat ("2022-12-22") or
                                ("2022") or ("2022-12")
                            Default value is None.
                            if start=None and end=None, 'values' can apply to RETAIL/institutional data.
    :param values:          Specifies the number of price data since today
                            Default value is 225.
                            'values' can be applied when start=None and end=None.
    :param tse_format:      if True you can get all historical RETAIL/institutional data in tse .csv format
                            Default value is False.
                            if tse_format=True, ignore output_type, date_format!
    :param output_type:     you can choose between 'standard' and 'complete'.
                            Default value is 'standard'.
                            if output_type='standard', you get RETAIL/institutional without per capitas
                                or powers in output.
                            if output_type='complete', you get RETAIL/institutional with per capitas
                                and powers in output
    :param date_format:     you can choose between 'jalali' and 'gregorian' and 'both'.
                            Default value is 'jalali'.
                            if date_format='jalali', you get historical RETAIL/institutional with
                                jalali date index and 'Weekday_fa' in complete mode
                                in output.
                            if output_type='gregorian', you get historical RETAIL/institutional
                                with gregorian date index and 'Weekday' in complete
                                mode in output.
                            if output_type='both', you get historical RETAIL/institutional with
                                gregorian date index and 'J-Date'(jalali date),
                                'Weekday', 'Weekday_fa' in complete mode in output.
    :param progress:        if True, show progress and report in console.
                            Default value is True.
    :param save_to_file:    if True, save symbol(s) historical RETAIL/institutional data with customized
                                columns in .csv format.
                            Default value is False.
                            the file name is 'stock.csv' in same root that
                                tsemodule6 is there. for example: 'شتران.csv'
    :param multi_stock_drop:if True, when you enter stocks list, it will delete
                                rows of none data (dropna) in combined historical df.
                            Default value is True.

    :return: pandas dataframe or None
    """
    # Backward compatibility: accept deprecated keyword names
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if "values" in kwargs:
        limit = kwargs.pop("values")
    if "tse_format" in kwargs:
        raw = kwargs.pop("tse_format")
    if "multi_stock_drop" in kwargs:
        dropna = kwargs.pop("multi_stock_drop")

    # Support legacy output_type value 'complete' → 'full'
    if output_type == "complete":
        output_type = "full"

    # Internal aliases for existing code
    values = limit
    tse_format = raw
    multi_stock_drop = dropna

    def _get_stock_RI(
        stock_name, mstart, mend, mvalues, mtse_format, moutput_type, mdate_format
    ):
        web_id = search_stock(search_txt=stock_name)
        client_type_base_url = settings.url_client_type
        if web_id[-5:] == "index" or web_id[-8:] == "industry":
            print("{} is an index, Please enter a valid stock name!".format(stock_name))
            return None
        new_start, new_end = date_fix(start=mstart, end=mend)
        if new_start is not None or new_end is not None:
            mvalues = 0
        try:
            fopen = safe_get(client_type_base_url.format(web_id)).text.split(";")
            data = {
                "<DTYYYYMMDD>": [],
                "<TICKER>": [],
                "<N_BUY_RETAIL>": [],
                "<N_BUY_INSTITUTIONAL>": [],
                "<N_SELL_RETAIL>": [],
                "<N_SELL_INSTITUTIONAL>": [],
                "<VOL_BUY_RETAIL>": [],
                "<VOL_BUY_INSTITUTIONAL>": [],
                "<VOL_SELL_RETAIL>": [],
                "<VOL_SELL_INSTITUTIONAL>": [],
                "<VAL_BUY_RETAIL>": [],
                "<VAL_BUY_INSTITUTIONAL>": [],
                "<VAL_SELL_RETAIL>": [],
                "<VAL_SELL_INSTITUTIONAL>": [],
                "<PER>": [],
            }

            for dt in fopen:
                dts = dt.split(",")
                date_iso = dts[0][:4] + "-" + dts[0][4:6] + "-" + dts[0][6:]
                data["<DTYYYYMMDD>"].append(datetime.date.fromisoformat(date_iso))
                data["<TICKER>"].append(stock_name)
                data["<N_BUY_RETAIL>"].append(int(dts[1]))
                data["<N_BUY_INSTITUTIONAL>"].append(int(dts[2]))
                data["<N_SELL_RETAIL>"].append(int(dts[3]))
                data["<N_SELL_INSTITUTIONAL>"].append(int(dts[4]))
                data["<VOL_BUY_RETAIL>"].append(int(dts[5]))
                data["<VOL_BUY_INSTITUTIONAL>"].append(int(dts[6]))
                data["<VOL_SELL_RETAIL>"].append(int(dts[7]))
                data["<VOL_SELL_INSTITUTIONAL>"].append(int(dts[8]))
                data["<VAL_BUY_RETAIL>"].append(int(dts[9]))
                data["<VAL_BUY_INSTITUTIONAL>"].append(int(dts[10]))
                data["<VAL_SELL_RETAIL>"].append(int(dts[11]))
                data["<VAL_SELL_INSTITUTIONAL>"].append(int(dts[12]))
                data["<PER>"].append("D")

            df = pd.DataFrame(
                data, columns=data.keys(), index=pd.DatetimeIndex(data["<DTYYYYMMDD>"])
            )
            df.index.names = ["<DTYYYYMMDD>"]
            df.drop(columns=["<DTYYYYMMDD>"], inplace=True)

            df = df[::-1]
            if mvalues is not None or mstart is not None or mend is not None:
                df = filter_by_date_or_values(df, mvalues, new_start, new_end)

            if mtse_format:
                return df
            else:
                df.index.rename("Date_base", inplace=True)
                df.drop(["<TICKER>", "<PER>"], axis=1, inplace=True)
                df.rename(
                    columns={
                        "<N_BUY_RETAIL>": "N_buy_retail",
                        "<N_BUY_INSTITUTIONAL>": "N_buy_institutional",
                        "<N_SELL_RETAIL>": "N_sell_retail",
                        "<N_SELL_INSTITUTIONAL>": "N_sell_institutional",
                        "<VOL_BUY_RETAIL>": "Vol_buy_retail",
                        "<VOL_BUY_INSTITUTIONAL>": "Vol_buy_institutional",
                        "<VOL_SELL_RETAIL>": "Vol_sell_retail",
                        "<VOL_SELL_INSTITUTIONAL>": "Vol_sell_institutional",
                        "<VAL_BUY_RETAIL>": "Val_buy_retail",
                        "<VAL_BUY_INSTITUTIONAL>": "Val_buy_institutional",
                        "<VAL_SELL_RETAIL>": "Val_sell_retail",
                        "<VAL_SELL_INSTITUTIONAL>": "Val_sell_institutional",
                    },
                    inplace=True,
                )

                df["Per_capita_buy_retail"] = round(
                    df["Val_buy_retail"] / df["N_buy_retail"]
                )
                df["Per_capita_sell_retail"] = round(
                    df["Val_sell_retail"] / df["N_sell_retail"]
                )
                df["Per_capita_buy_institutional"] = round(
                    df["Val_buy_institutional"] / df["N_buy_institutional"]
                )
                df["Per_capita_sell_institutional"] = round(
                    df["Val_sell_institutional"] / df["N_sell_institutional"]
                )
                df["Power_retail"] = round(
                    df["Per_capita_buy_retail"] / df["Per_capita_sell_retail"], 3
                )
                df["Power_institutional"] = round(
                    df["Per_capita_buy_institutional"]
                    / df["Per_capita_sell_institutional"],
                    3,
                )

                df = add_date_columns(df, stock_name)
                df.fillna(value=0, inplace=True)

                df = apply_date_format(df, mdate_format)
                if df is None:
                    return None
                if moutput_type == "standard":
                    df = df.loc[
                        :,
                        [
                            "N_buy_retail",
                            "N_buy_institutional",
                            "N_sell_retail",
                            "N_sell_institutional",
                            "Vol_buy_retail",
                            "Vol_buy_institutional",
                            "Vol_sell_retail",
                            "Vol_sell_institutional",
                            "Val_buy_retail",
                            "Val_buy_institutional",
                            "Val_sell_retail",
                            "Val_sell_institutional",
                        ],
                    ]
                elif moutput_type == "full":
                    pass
                else:
                    print("output_type should select between 'standard' or 'full'")
                    return None
                return df
        except requests.exceptions.RequestException:
            print("Connection Error!")
            return None
        except Exception as e:
            print("Stock Not Found or data error: {}".format(e))
            return None

    import os

    def _save_csv_ri(df, filename):
        """Save DataFrame to CSV, respecting save_path."""
        if save_path:
            os.makedirs(save_path, exist_ok=True)
            filepath = os.path.join(save_path, filename)
        else:
            filepath = filename
        df.to_csv(filepath, encoding="utf-8-sig")

    def _apply_ascending_ri(df):
        """Sort by index ascending/descending based on user preference."""
        if df is not None and not ascending:
            return df.iloc[::-1]
        return df

    if symbol == "":
        symbol = "شتران"
        if progress:
            print("1/1: Getting historical retail/institutional of {}".format(symbol))
        symbol = characters.ar_to_fa(symbol).strip("\u200c").strip()
        df = _get_stock_RI(
            stock_name=symbol,
            mstart=start,
            mend=end,
            mvalues=values,
            mtse_format=tse_format,
            moutput_type=output_type,
            mdate_format=date_format,
        )
        if progress and df is not None:
            print("1/1: Completed!")
        if save_to_file and df is not None:
            if progress:
                print("Saving to file: {}-حقیقی-حقوقی.csv".format(symbol))
            _save_csv_ri(df, symbol + "-حقیقی-حقوقی.csv")
        return _apply_ascending_ri(df)
    else:
        if isinstance(symbol, str):
            if progress:
                print(
                    "1/1: Getting historical retail/institutional of {}".format(symbol)
                )
            symbol = characters.ar_to_fa(symbol).strip("\u200c").strip()
            df = _get_stock_RI(
                stock_name=symbol,
                mstart=start,
                mend=end,
                mvalues=values,
                mtse_format=tse_format,
                moutput_type=output_type,
                mdate_format=date_format,
            )
            if progress and df is not None:
                print("1/1: Completed!")
            if save_to_file and df is not None:
                if progress:
                    print("Saving to file: {}-حقیقی-حقوقی.csv".format(symbol))
                _save_csv_ri(df, symbol + "-حقیقی-حقوقی.csv")
            return _apply_ascending_ri(df)
        elif isinstance(symbol, list):
            n = 1
            df_dict = {}
            file_name_str = ""
            for stk in symbol:
                if progress:
                    print(
                        "{}/{}: Getting historical retail/institutional of {}".format(
                            n, len(symbol), stk
                        )
                    )
                stk = characters.ar_to_fa(stk).strip("\u200c").strip()
                df = _get_stock_RI(
                    stock_name=stk,
                    mstart=start,
                    mend=end,
                    mvalues=values,
                    mtse_format=tse_format,
                    moutput_type=output_type,
                    mdate_format=date_format,
                )
                if df is not None:
                    file_name_str += "-" + stk
                    df_dict[stk] = df
                else:
                    print("{} not Found!".format(stk))
                n += 1
            if progress:
                print("{}/{} Completed!".format(len(symbol), len(symbol)))

            if len(list(df_dict.keys())) == 0:
                print("None of the entered stocks exist!!")
                return None
            elif len(list(df_dict.keys())) == 1:
                df = df_dict[list(df_dict.keys())[0]]
                if save_to_file and df is not None:
                    if progress:
                        print(
                            "Saving to file: {}-حقیقی-حقوقی.csv".format(
                                file_name_str[1:]
                            )
                        )
                    _save_csv_ri(df, file_name_str[1:] + "-حقیقی-حقوقی.csv")
                return _apply_ascending_ri(df)
            else:
                df = pd.concat(df_dict, axis=1)
                multi_assets_columns = df.columns
                reversed_multi_assets_columns = []
                for column_index in multi_assets_columns:
                    reversed_multi_assets_columns.append(column_index[::-1])
                new_index = pd.MultiIndex.from_tuples(reversed_multi_assets_columns)
                df.columns = new_index

                if multi_stock_drop:
                    df.dropna(inplace=True)
                if save_to_file and df is not None:
                    if progress:
                        print(
                            "Saving to file: {}-حقیقی-حقوقی.csv".format(
                                file_name_str[1:]
                            )
                        )
                    _save_csv_ri(df, file_name_str[1:] + "-حقیقی-حقوقی.csv")
                return _apply_ascending_ri(df)


def stock_RL(
    symbol="",
    start=None,
    end=None,
    limit=0,
    raw=False,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    dropna=True,
    ascending=True,
    save_path=None,
    **kwargs
):
    # Backward compat
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if "values" in kwargs:
        limit = kwargs.pop("values")
    if "tse_format" in kwargs:
        raw = kwargs.pop("tse_format")
    if "multi_stock_drop" in kwargs:
        dropna = kwargs.pop("multi_stock_drop")
    return stock_RI(
        symbol=symbol,
        start=start,
        end=end,
        limit=limit,
        raw=raw,
        output_type=output_type,
        date_format=date_format,
        progress=progress,
        save_to_file=save_to_file,
        dropna=dropna,
        ascending=ascending,
        save_path=save_path,
    )


# symbol capital increase version 1
def stock_capital_increase(symbol="", **kwargs):
    """
    Get every capital increase in selected asset.
    :param symbol:   symbol name in persian, or a list of symbol in
                                persian (['شتران', 'آریا'])
                    Default value is 'شتران'.
    :return: pandas DataFrame or None
    """
    # Backward compatibility: accept deprecated 'stock' keyword
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    web_id = search_stock(search_txt=symbol)
    _capital_increase_url = settings.url_capital_increase
    if web_id[-5:] == "index":
        print("Indexes don't have capital increase!")
        return None
    else:
        try:
            response = safe_get(_capital_increase_url.format(web_id))
            if response.status_code == 200:
                data_dict = response.json()["instrumentShareChange"]
                df = pd.DataFrame(data_dict)
                df.rename(
                    columns={
                        "dEven": "date",
                        "numberOfShareNew": "new_shares_amount",
                        "numberOfShareOld": "old_shares_amount",
                    },
                    inplace=True,
                )
                df["date"] = df["date"].astype(str)
                df.set_index("date", inplace=True)
                df.index = pd.to_datetime(df.index)
                df = df.loc[:, ["old_shares_amount", "new_shares_amount"]]
                return df
            else:
                return None
        except requests.exceptions.RequestException:
            return None
        except Exception:
            return None
