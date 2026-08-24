import io
import datetime
import requests
import warnings
import numpy as np
import pandas as pd
from persiantools import characters
from persiantools.jdatetime import JalaliDate

from algotik_tse.settings import settings
from algotik_tse.core.search import search_stock, INDUSTRY_NAMES
from algotik_tse.core.helper import (
    date_fix,
    add_date_columns,
    apply_date_format,
    apply_return_type,
    filter_by_date_or_values,
)
from algotik_tse.http_client import safe_get
from algotik_tse.exceptions import (
    AlgotikTSEError,
    AmbiguousSymbolError,
    InvalidParameterError,
)


def _tehran_today():
    return pd.Timestamp.now(tz="Asia/Tehran").date()


def _index_contains_date(index, value):
    """Check Gregorian/Jalali output indices after final filtering."""
    if value is None:
        return False
    if isinstance(index, pd.DatetimeIndex):
        return any(item.date() == value for item in index)
    gregorian = value.isoformat()
    jalali = JalaliDate.to_jalali(value).isoformat()
    return any(str(item) in {gregorian, jalali} for item in index)


def _canonical_live_row(inscode, snapshot):
    """Resolve exactly one current snapshot row by canonical InsCode."""
    from algotik_tse.core.market_data import _is_current_snapshot

    if not _is_current_snapshot(snapshot):
        return None
    matches = snapshot["stocks"].loc[
        snapshot["stocks"]["InsCode"].astype(str).eq(str(inscode))
    ]
    if matches.empty:
        return None
    if len(matches) != 1:
        raise AmbiguousSymbolError(
            f"Canonical InsCode {inscode!r} matched {len(matches)} live rows"
        )
    item = matches.iloc[0]
    required_positive = [
        "TradeCount",
        "Volume",
        "FirstPrice",
        "High",
        "Low",
        "Close",
        "Last",
    ]
    values = pd.to_numeric(item[required_positive], errors="coerce")
    if values.isna().any() or values.le(0).any():
        return None
    return item


def _live_price_history_row(stock_name, inscode, snapshot):
    """Build one TSETMC-compatible partial daily row from the live feed."""
    item = _canonical_live_row(inscode, snapshot)
    if item is None:
        return None
    values = {
        "<TICKER>": item["Symbol"],
        "<FIRST>": item["FirstPrice"],
        "<HIGH>": item["High"],
        "<LOW>": item["Low"],
        "<CLOSE>": item["Close"],
        "<VALUE>": item["Value"],
        "<VOL>": item["Volume"],
        "<OPENINT>": item["TradeCount"],
        "<OPEN>": item["PreviousClose"],
        "<LAST>": item["Last"],
        "<PER>": "D",
    }
    return pd.DataFrame(
        [values],
        index=pd.DatetimeIndex([snapshot["trade_date"]], name="<DTYYYYMMDD>"),
    )


def _live_client_type_history_row(stock_name, inscode, snapshot, client_type):
    """Build one history-compatible client-type row for partial today data."""
    from algotik_tse.core.market_data import _client_volume_audit, _safe_divide

    price = _canonical_live_row(inscode, snapshot)
    if price is None or client_type is None:
        return None
    matches = client_type.loc[client_type["InsCode"].astype(str).eq(str(inscode))]
    if matches.empty:
        return None
    if len(matches) != 1:
        raise AmbiguousSymbolError(
            f"Canonical InsCode {inscode!r} matched {len(matches)} client rows"
        )
    item = matches.iloc[0]
    audit = _client_volume_audit(
        pd.Series([item["Buy_I_Volume"]]),
        pd.Series([item["Buy_N_Volume"]]),
        pd.Series([item["Sell_I_Volume"]]),
        pd.Series([item["Sell_N_Volume"]]),
        pd.Series([price["Volume"]]),
    )
    if not bool(audit["client_snapshot_consistent"].iloc[0]):
        raise ValueError(
            f"inconsistent live client volumes for canonical InsCode {inscode}"
        )
    vwap = _safe_divide(pd.Series([price["Value"]]), pd.Series([price["Volume"]])).iloc[
        0
    ]
    values = {
        "<TICKER>": price["Symbol"],
        "<N_BUY_RETAIL>": item["Buy_I_Count"],
        "<N_BUY_INSTITUTIONAL>": item["Buy_N_Count"],
        "<N_SELL_RETAIL>": item["Sell_I_Count"],
        "<N_SELL_INSTITUTIONAL>": item["Sell_N_Count"],
        "<VOL_BUY_RETAIL>": item["Buy_I_Volume"],
        "<VOL_BUY_INSTITUTIONAL>": item["Buy_N_Volume"],
        "<VOL_SELL_RETAIL>": item["Sell_I_Volume"],
        "<VOL_SELL_INSTITUTIONAL>": item["Sell_N_Volume"],
        # ClientTypeAll does not provide exact value split. Never place an
        # estimate in the raw/actual TSETMC value fields.
        "<VAL_BUY_RETAIL>": pd.NA,
        "<VAL_BUY_INSTITUTIONAL>": pd.NA,
        "<VAL_SELL_RETAIL>": pd.NA,
        "<VAL_SELL_INSTITUTIONAL>": pd.NA,
        "<EST_VAL_BUY_RETAIL>": item["Buy_I_Volume"] * vwap,
        "<EST_VAL_BUY_INSTITUTIONAL>": item["Buy_N_Volume"] * vwap,
        "<EST_VAL_SELL_RETAIL>": item["Sell_I_Volume"] * vwap,
        "<EST_VAL_SELL_INSTITUTIONAL>": item["Sell_N_Volume"] * vwap,
        "<VALUE_SOURCE>": "estimated_from_market_vwap",
        "<IS_ESTIMATED>": True,
        "<IS_PARTIAL>": snapshot.get("is_partial", pd.NA),
        "<CLIENT_SNAPSHOT_CONSISTENT>": True,
        "<CLIENT_BUY_VOLUME_DIFFERENCE>": audit["client_buy_volume_difference"].iloc[0],
        "<CLIENT_SELL_VOLUME_DIFFERENCE>": audit["client_sell_volume_difference"].iloc[
            0
        ],
        "<CLIENT_BUY_VOLUME_RATIO>": audit["client_buy_volume_ratio"].iloc[0],
        "<CLIENT_SELL_VOLUME_RATIO>": audit["client_sell_volume_ratio"].iloc[0],
        "<PER>": "D",
    }
    return pd.DataFrame(
        [values],
        index=pd.DatetimeIndex([snapshot["trade_date"]], name="<DTYYYYMMDD>"),
    )


def _live_index_history_row(stock_name, inscode, snapshot, index_rows, industry):
    """Build a partial index row from the bulk live index endpoint."""
    from algotik_tse.core.market_data import _is_current_snapshot

    if not _is_current_snapshot(snapshot) or index_rows is None:
        return None
    matches = [row for row in index_rows if str(row.get("insCode")) == str(inscode)]
    if not matches:
        return None
    if len(matches) != 1:
        raise AmbiguousSymbolError(
            f"Canonical index InsCode {inscode!r} matched {len(matches)} rows"
        )
    item = matches[0]
    raw_trade_date = item.get("dEven")
    date_text = str(raw_trade_date).strip()
    if len(date_text) != 8 or not date_text.isdigit():
        raise ValueError(
            f"live index date provenance unavailable for canonical InsCode {inscode}"
        )
    try:
        source_trade_date = datetime.date(
            int(date_text[:4]), int(date_text[4:6]), int(date_text[6:])
        )
    except ValueError as exc:
        raise ValueError(
            f"invalid live index dEven for canonical InsCode {inscode}"
        ) from exc
    if source_trade_date != snapshot.get("trade_date"):
        raise ValueError(
            f"live index dEven {source_trade_date} does not match "
            f"MarketWatch trade_date {snapshot.get('trade_date')}"
        )
    raw_trade_time = item.get("hEven")
    if raw_trade_time is not None:
        time_text = str(raw_trade_time).strip().zfill(6)
        if (
            len(time_text) != 6
            or not time_text.isdigit()
            or int(time_text[:2]) > 23
            or int(time_text[2:4]) > 59
            or int(time_text[4:]) > 59
        ):
            raise ValueError(
                f"invalid live index hEven for canonical InsCode {inscode}"
            )
    numeric = pd.to_numeric(
        pd.Series(
            {
                "current": item.get("xDrNivJIdx004", np.nan),
                "high": item.get("xPhNivJIdx004", np.nan),
                "low": item.get("xPbNivJIdx004", np.nan),
            }
        ),
        errors="coerce",
    )
    if (
        numeric.isna().any()
        or not np.isfinite(numeric.to_numpy(dtype=float)).all()
        or numeric.le(0).any()
    ):
        raise ValueError(f"invalid live index OHLC for canonical InsCode {inscode}")
    current, high, low = numeric["current"], numeric["high"], numeric["low"]
    common = {
        "<TICKER>": stock_name,
        "<HIGH>": high,
        "<LOW>": low,
        "<CLOSE>": current,
        "<LIVE_SOURCE_TRADE_DATE>": source_trade_date,
        "<LIVE_SOURCE_TIME>": raw_trade_time,
        "<LIVE_SOURCE_DATE_PROVENANCE>": "indexB1.dEven",
        "<PER>": "D",
    }
    if not industry:
        absolute_change = pd.to_numeric(
            pd.Series([item.get("indexChange")]), errors="coerce"
        ).iloc[0]
        previous_close = (
            current - absolute_change
            if pd.notna(current) and pd.notna(absolute_change)
            else np.nan
        )
        common.update(
            {
                "<FIRST>": np.nan,
                "<VOL>": np.nan,
                "<OPEN>": np.nan,
                "<PREVIOUS_CLOSE>": previous_close,
                "<LAST>": current,
            }
        )
    return pd.DataFrame(
        [common],
        index=pd.DatetimeIndex([snapshot["trade_date"]], name="<DTYYYYMMDD>"),
    )


def _append_partial_today(df, live_row):
    """Append or source-aware merge today's row without losing actual data."""
    result = df.copy(deep=True)
    if live_row is None or live_row.empty:
        return result
    live_row = live_row.copy(deep=True)
    today = live_row.index[0]
    # Raw endpoints may gain columns over time.  Preserve their established
    # schema and fill only the columns represented by the live contract.
    for column in result.columns:
        if column not in live_row.columns:
            live_row[column] = pd.NA
    for column in live_row.columns:
        if column not in result.columns:
            result[column] = pd.NA
    if today in result.index:
        existing = result.loc[[today]].iloc[-1].copy()
        incoming = live_row.iloc[-1]
        actual_value_columns = [
            "<VAL_BUY_RETAIL>",
            "<VAL_BUY_INSTITUTIONAL>",
            "<VAL_SELL_RETAIL>",
            "<VAL_SELL_INSTITUTIONAL>",
        ]
        has_historical_actual_values = all(
            column in existing.index and pd.notna(existing[column])
            for column in actual_value_columns
        )
        if has_historical_actual_values:
            # Client-type rows are an atomic snapshot. Mixing historical
            # actual values with live counts/volumes would create powers and
            # per-capita values that never existed at either source time.
            # Preserve the complete historical row and only add truthful
            # provenance. Today alone is not evidence that the row is final.
            if "<VALUE_SOURCE>" in existing.index:
                existing["<VALUE_SOURCE>"] = "tsetmc_actual"
            if "<IS_ESTIMATED>" in existing.index:
                existing["<IS_ESTIMATED>"] = False
            if "<IS_PARTIAL>" in existing.index and pd.isna(existing["<IS_PARTIAL>"]):
                existing["<IS_PARTIAL>"] = pd.NA
            merged = pd.DataFrame([existing], index=pd.DatetimeIndex([today]))
            merged.index.name = result.index.name
            result = result.drop(index=today, errors="ignore")
            result = pd.concat([result, merged.loc[:, result.columns]]).sort_index()
            result.attrs.update(df.attrs)
            return result
        for column in result.columns:
            incoming_value = incoming.get(column, pd.NA)
            if pd.isna(incoming_value):
                continue
            if has_historical_actual_values and column in actual_value_columns:
                continue
            existing[column] = incoming_value
        merged = pd.DataFrame([existing], index=pd.DatetimeIndex([today]))
        merged.index.name = result.index.name
        result = result.drop(index=today, errors="ignore")
        result = pd.concat([result, merged.loc[:, result.columns]]).sort_index()
    else:
        result = pd.concat([result, live_row.loc[:, result.columns]]).sort_index()
    result.attrs.update(df.attrs)
    return result


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
    include_today=False,
    *,
    ins_code=None,
    asset_type="auto",
    **kwargs,
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
    :param include_today:   if True, append/replace today's partial live row.
                            Default is False, preserving historical behaviour.
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
    # Private, canonical resolver hook used by APIs that already obtained an
    # authoritative TSETMC InsCode and must not re-run fuzzy symbol search.
    _resolved_inscode = kwargs.pop("_resolved_inscode", None)
    if _resolved_inscode is not None:
        _resolved_inscode = str(_resolved_inscode).strip()
        if not _resolved_inscode.isdigit():
            raise ValueError("_resolved_inscode must be a canonical numeric InsCode")
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if not symbol and (ins_code is not None or _resolved_inscode is not None):
        symbol = str(ins_code if ins_code is not None else _resolved_inscode)
    if ins_code is not None and not isinstance(symbol, str):
        raise InvalidParameterError("ins_code can only be used with one symbol")
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

    live_cache = {
        "market_attempted": False,
        "market": None,
        "index_attempted": False,
        "indices": None,
    }
    include_status = {
        "include_today_requested": bool(include_today),
        "include_today_appended": [],
        "include_today_warning": None,
        "live_trade_date": None,
        "live_is_partial": None,
        "live_is_history_eligible": None,
        "live_is_realtime_fresh": None,
        "live_snapshot_age_seconds": None,
    }
    append_candidates = {}

    def _warn_live_fallback(message):
        include_status["include_today_warning"] = message
        warnings.warn(message, RuntimeWarning, stacklevel=3)

    def _market_snapshot_once():
        if live_cache["market_attempted"]:
            return live_cache["market"]
        live_cache["market_attempted"] = True
        try:
            from algotik_tse.core.market_data import market_watch

            live_cache["market"] = market_watch()
            include_status["live_trade_date"] = live_cache["market"].get("trade_date")
            include_status["live_is_partial"] = live_cache["market"].get("is_partial")
            include_status["live_is_history_eligible"] = live_cache["market"].get(
                "is_history_eligible"
            )
            include_status["live_is_realtime_fresh"] = live_cache["market"].get(
                "is_realtime_fresh"
            )
            include_status["live_snapshot_age_seconds"] = live_cache["market"].get(
                "snapshot_age_seconds"
            )
            from algotik_tse.core.market_data import _is_current_snapshot

            if not _is_current_snapshot(live_cache["market"]):
                _warn_live_fallback(
                    "include_today skipped; MarketWatch snapshot is stale or "
                    "does not represent Tehran today"
                )
        except (AlgotikTSEError, requests.exceptions.RequestException) as exc:
            _warn_live_fallback(
                f"include_today skipped; live market unavailable: {exc}"
            )
        return live_cache["market"]

    def _index_snapshot_once():
        if live_cache["index_attempted"]:
            return live_cache["indices"]
        live_cache["index_attempted"] = True
        try:
            response = safe_get(settings.url_all_indices)
            live_cache["indices"] = response.json()["indexB1"]
        except (
            requests.exceptions.RequestException,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            _warn_live_fallback(
                f"include_today skipped; live index feed unavailable: {exc}"
            )
        return live_cache["indices"]

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
        if _resolved_inscode is not None:
            web_id = _resolved_inscode
        elif ins_code is None and asset_type == "auto":
            web_id = search_stock(search_txt=stock_name)
        else:
            web_id = search_stock(
                search_txt=stock_name,
                ins_code=ins_code,
                asset_type=asset_type,
            )
        if web_id is None or len(str(web_id)) == 0:
            print("Stock Not Found, Please try again ...")
            return None
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
                    data["<TICKER>"].append(
                        INDUSTRY_NAMES.get(web_id, "Unknown Industry")
                    )
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
                if include_today:
                    market_snapshot = _market_snapshot_once()
                    from algotik_tse.core.market_data import _is_current_snapshot

                    try:
                        live_row = (
                            _live_index_history_row(
                                stock_name,
                                web_id,
                                market_snapshot,
                                _index_snapshot_once(),
                                industry=True,
                            )
                            if _is_current_snapshot(market_snapshot)
                            else None
                        )
                    except AmbiguousSymbolError:
                        raise
                    except (KeyError, TypeError, ValueError, AttributeError) as exc:
                        _warn_live_fallback(
                            f"include_today skipped; invalid live index schema: {exc}"
                        )
                        live_row = None
                    df = _append_partial_today(df, live_row)
                    if live_row is not None:
                        append_candidates[stock_name] = live_row.index[0].date()
                    elif include_status["include_today_warning"] is None:
                        _warn_live_fallback(
                            f"include_today skipped; canonical index {web_id} "
                            "was not present in the live index feed"
                        )

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
            except AmbiguousSymbolError:
                raise
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
                if include_today:
                    market_snapshot = _market_snapshot_once()
                    from algotik_tse.core.market_data import _is_current_snapshot

                    try:
                        live_row = (
                            _live_index_history_row(
                                stock_name,
                                web_id,
                                market_snapshot,
                                _index_snapshot_once(),
                                industry=False,
                            )
                            if _is_current_snapshot(market_snapshot)
                            else None
                        )
                    except AmbiguousSymbolError:
                        raise
                    except (KeyError, TypeError, ValueError, AttributeError) as exc:
                        _warn_live_fallback(
                            f"include_today skipped; invalid live index schema: {exc}"
                        )
                        live_row = None
                    df = _append_partial_today(df, live_row)
                    if live_row is not None:
                        append_candidates[stock_name] = live_row.index[0].date()
                    elif include_status["include_today_warning"] is None:
                        _warn_live_fallback(
                            f"include_today skipped; canonical index {web_id} "
                            "was not present in the live index feed"
                        )

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
            except AmbiguousSymbolError:
                raise
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
                if include_today:
                    try:
                        live_row = _live_price_history_row(
                            stock_name, web_id, _market_snapshot_once()
                        )
                    except AmbiguousSymbolError:
                        raise
                    except (KeyError, TypeError, ValueError, AttributeError) as exc:
                        _warn_live_fallback(
                            f"include_today skipped; invalid live schema: {exc}"
                        )
                        live_row = None
                    df = _append_partial_today(df, live_row)
                    if live_row is not None:
                        append_candidates[stock_name] = live_row.index[0].date()
                    elif include_status["include_today_warning"] is None:
                        _warn_live_fallback(
                            f"include_today skipped; canonical InsCode {web_id} "
                            "was not present in MarketWatch"
                        )
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
            except AmbiguousSymbolError:
                raise
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
        if df is not None and include_today:
            include_status["include_today_appended"] = [
                name
                for name, trade_date in append_candidates.items()
                if _index_contains_date(df.index, trade_date)
            ]
            df.attrs.update(include_status)
        if df is not None and not ascending:
            result = df.iloc[::-1]
            if include_today:
                result.attrs.update(include_status)
            return result
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
    include_today=False,
    *,
    ins_code=None,
    asset_type="auto",
    **kwargs,
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
    :param include_today:   if True, append/replace today's partial live row.
                            Value fields for today are estimated using live VWAP.
                            Default is False, preserving historical behaviour.

    :return: pandas dataframe or None
    """
    # Backward compatibility: accept deprecated keyword names
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if not symbol and ins_code is not None:
        symbol = str(ins_code)
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

    # One bulk snapshot per public call, reused by every requested symbol.
    live_cache = {
        "market_attempted": False,
        "market": None,
        "client_attempted": False,
        "client": None,
    }
    include_status = {
        "include_today_requested": bool(include_today),
        "include_today_appended": [],
        "include_today_warning": None,
        "live_trade_date": None,
        "live_is_partial": None,
        "live_is_history_eligible": None,
        "live_is_realtime_fresh": None,
        "live_snapshot_age_seconds": None,
    }
    append_candidates = {}

    def _warn_ri_fallback(message):
        include_status["include_today_warning"] = message
        warnings.warn(message, RuntimeWarning, stacklevel=3)

    def _ri_market_snapshot_once():
        if live_cache["market_attempted"]:
            return live_cache["market"]
        live_cache["market_attempted"] = True
        try:
            from algotik_tse.core.market_data import market_watch, _is_current_snapshot

            live_cache["market"] = market_watch()
            include_status["live_trade_date"] = live_cache["market"].get("trade_date")
            include_status["live_is_partial"] = live_cache["market"].get("is_partial")
            include_status["live_is_history_eligible"] = live_cache["market"].get(
                "is_history_eligible"
            )
            include_status["live_is_realtime_fresh"] = live_cache["market"].get(
                "is_realtime_fresh"
            )
            include_status["live_snapshot_age_seconds"] = live_cache["market"].get(
                "snapshot_age_seconds"
            )
            if not _is_current_snapshot(live_cache["market"]):
                _warn_ri_fallback(
                    "include_today skipped; MarketWatch snapshot is stale or "
                    "does not represent Tehran today"
                )
        except (AlgotikTSEError, requests.exceptions.RequestException) as exc:
            _warn_ri_fallback(f"include_today skipped; live market unavailable: {exc}")
        return live_cache["market"]

    def _ri_client_snapshot_once():
        if live_cache["client_attempted"]:
            return live_cache["client"]
        live_cache["client_attempted"] = True
        try:
            from algotik_tse.core.market_data import market_client_type

            live_cache["client"] = market_client_type()
        except (AlgotikTSEError, requests.exceptions.RequestException) as exc:
            _warn_ri_fallback(
                f"include_today skipped; live client feed unavailable: {exc}"
            )
        return live_cache["client"]

    def _get_stock_RI(
        stock_name, mstart, mend, mvalues, mtse_format, moutput_type, mdate_format
    ):
        selector_ins_code = ins_code if isinstance(symbol, str) else None
        if ins_code is not None and not isinstance(symbol, str):
            raise InvalidParameterError("ins_code can only be used with one symbol")
        if selector_ins_code is None and asset_type == "auto":
            web_id = search_stock(search_txt=stock_name)
        else:
            web_id = search_stock(
                search_txt=stock_name,
                ins_code=selector_ins_code,
                asset_type=asset_type,
            )
        if web_id is None or len(str(web_id)) == 0:
            print("Stock Not Found, Please try again ...")
            return None
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
            if include_today:
                market_snapshot = _ri_market_snapshot_once()
                from algotik_tse.core.market_data import _is_current_snapshot

                if _is_current_snapshot(market_snapshot):
                    try:
                        live_row = _live_client_type_history_row(
                            stock_name,
                            web_id,
                            market_snapshot,
                            _ri_client_snapshot_once(),
                        )
                    except AmbiguousSymbolError:
                        raise
                    except (KeyError, TypeError, ValueError, AttributeError) as exc:
                        _warn_ri_fallback(
                            f"include_today skipped; invalid live schema: {exc}"
                        )
                        live_row = None
                else:
                    live_row = None
                df = _append_partial_today(df, live_row)
                if live_row is not None:
                    append_candidates[stock_name] = live_row.index[0].date()
                elif include_status["include_today_warning"] is None:
                    _warn_ri_fallback(
                        f"include_today skipped; canonical InsCode {web_id} was "
                        "not present in both live feeds"
                    )
            if mvalues is not None or mstart is not None or mend is not None:
                df = filter_by_date_or_values(df, mvalues, new_start, new_end)

            if mtse_format:
                if include_today:
                    raw_provenance_defaults = {
                        "<EST_VAL_BUY_RETAIL>": np.nan,
                        "<EST_VAL_BUY_INSTITUTIONAL>": np.nan,
                        "<EST_VAL_SELL_RETAIL>": np.nan,
                        "<EST_VAL_SELL_INSTITUTIONAL>": np.nan,
                        "<VALUE_SOURCE>": pd.NA,
                        "<IS_ESTIMATED>": pd.NA,
                        "<IS_PARTIAL>": pd.NA,
                        "<CLIENT_SNAPSHOT_CONSISTENT>": pd.NA,
                        "<CLIENT_BUY_VOLUME_DIFFERENCE>": np.nan,
                        "<CLIENT_SELL_VOLUME_DIFFERENCE>": np.nan,
                        "<CLIENT_BUY_VOLUME_RATIO>": np.nan,
                        "<CLIENT_SELL_VOLUME_RATIO>": np.nan,
                    }
                    for column, default in raw_provenance_defaults.items():
                        if column not in df:
                            df[column] = default
                    historical_mask = df["<VALUE_SOURCE>"].isna()
                    for column in [
                        "<VAL_BUY_RETAIL>",
                        "<VAL_BUY_INSTITUTIONAL>",
                        "<VAL_SELL_RETAIL>",
                        "<VAL_SELL_INSTITUTIONAL>",
                    ]:
                        df[column] = pd.to_numeric(df[column], errors="coerce").astype(
                            "Int64"
                        )
                    df["<VALUE_SOURCE>"] = df["<VALUE_SOURCE>"].where(
                        df["<VALUE_SOURCE>"].notna(), "tsetmc_actual"
                    )
                    df["<IS_ESTIMATED>"] = (
                        df["<IS_ESTIMATED>"]
                        .where(~historical_mask, False)
                        .astype("boolean")
                    )
                    df.loc[historical_mask, "<IS_PARTIAL>"] = False
                    df["<IS_PARTIAL>"] = df["<IS_PARTIAL>"].astype("boolean")
                    df["<CLIENT_SNAPSHOT_CONSISTENT>"] = df[
                        "<CLIENT_SNAPSHOT_CONSISTENT>"
                    ].astype("boolean")
                    for column in [
                        "<CLIENT_BUY_VOLUME_DIFFERENCE>",
                        "<CLIENT_SELL_VOLUME_DIFFERENCE>",
                        "<CLIENT_BUY_VOLUME_RATIO>",
                        "<CLIENT_SELL_VOLUME_RATIO>",
                    ]:
                        df[column] = pd.to_numeric(df[column], errors="coerce").astype(
                            "Float64"
                        )
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
                        "<EST_VAL_BUY_RETAIL>": "Estimated_val_buy_retail",
                        "<EST_VAL_BUY_INSTITUTIONAL>": (
                            "Estimated_val_buy_institutional"
                        ),
                        "<EST_VAL_SELL_RETAIL>": "Estimated_val_sell_retail",
                        "<EST_VAL_SELL_INSTITUTIONAL>": (
                            "Estimated_val_sell_institutional"
                        ),
                        "<VALUE_SOURCE>": "Value_source",
                        "<IS_ESTIMATED>": "Is_estimated",
                        "<IS_PARTIAL>": "Is_partial",
                        "<CLIENT_SNAPSHOT_CONSISTENT>": ("Client_snapshot_consistent"),
                        "<CLIENT_BUY_VOLUME_DIFFERENCE>": (
                            "Client_buy_volume_difference"
                        ),
                        "<CLIENT_SELL_VOLUME_DIFFERENCE>": (
                            "Client_sell_volume_difference"
                        ),
                        "<CLIENT_BUY_VOLUME_RATIO>": "Client_buy_volume_ratio",
                        "<CLIENT_SELL_VOLUME_RATIO>": "Client_sell_volume_ratio",
                    },
                    inplace=True,
                )

                if include_today:
                    from algotik_tse.core.market_data import _safe_divide

                    provenance_columns = {
                        "Estimated_val_buy_retail": np.nan,
                        "Estimated_val_buy_institutional": np.nan,
                        "Estimated_val_sell_retail": np.nan,
                        "Estimated_val_sell_institutional": np.nan,
                        "Value_source": pd.NA,
                        "Is_estimated": pd.NA,
                        "Is_partial": pd.NA,
                        "Client_snapshot_consistent": pd.NA,
                        "Client_buy_volume_difference": np.nan,
                        "Client_sell_volume_difference": np.nan,
                        "Client_buy_volume_ratio": np.nan,
                        "Client_sell_volume_ratio": np.nan,
                    }
                    for column, default in provenance_columns.items():
                        if column not in df:
                            df[column] = default
                    historical_mask = df["Value_source"].isna()
                    df["Value_source"] = df["Value_source"].where(
                        ~historical_mask, "tsetmc_actual"
                    )
                    df["Is_estimated"] = df["Is_estimated"].where(
                        ~historical_mask, False
                    )
                    df.loc[historical_mask, "Is_partial"] = False
                    effective_buy_retail = df["Val_buy_retail"].combine_first(
                        df["Estimated_val_buy_retail"]
                    )
                    effective_sell_retail = df["Val_sell_retail"].combine_first(
                        df["Estimated_val_sell_retail"]
                    )
                    effective_buy_institutional = df[
                        "Val_buy_institutional"
                    ].combine_first(df["Estimated_val_buy_institutional"])
                    effective_sell_institutional = df[
                        "Val_sell_institutional"
                    ].combine_first(df["Estimated_val_sell_institutional"])
                    df["Per_capita_buy_retail"] = _safe_divide(
                        effective_buy_retail, df["N_buy_retail"]
                    ).round()
                    df["Per_capita_sell_retail"] = _safe_divide(
                        effective_sell_retail, df["N_sell_retail"]
                    ).round()
                    df["Per_capita_buy_institutional"] = _safe_divide(
                        effective_buy_institutional, df["N_buy_institutional"]
                    ).round()
                    df["Per_capita_sell_institutional"] = _safe_divide(
                        effective_sell_institutional, df["N_sell_institutional"]
                    ).round()
                    df["Power_retail"] = _safe_divide(
                        df["Per_capita_buy_retail"],
                        df["Per_capita_sell_retail"],
                    ).round(3)
                    df["Power_institutional"] = _safe_divide(
                        df["Per_capita_buy_institutional"],
                        df["Per_capita_sell_institutional"],
                    ).round(3)
                    df.replace([np.inf, -np.inf], np.nan, inplace=True)
                    integer_columns = [
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
                    ]
                    for column in integer_columns:
                        df[column] = pd.to_numeric(df[column], errors="coerce").astype(
                            "Int64"
                        )
                    for column in provenance_columns:
                        if (
                            column.startswith("Estimated_")
                            or column.startswith("Client_")
                            and column != "Client_snapshot_consistent"
                        ):
                            df[column] = pd.to_numeric(
                                df[column], errors="coerce"
                            ).astype("Float64")
                    df["Value_source"] = df["Value_source"].astype("string")
                    df["Is_estimated"] = df["Is_estimated"].astype("boolean")
                    df["Is_partial"] = df["Is_partial"].astype("boolean")
                    df["Client_snapshot_consistent"] = df[
                        "Client_snapshot_consistent"
                    ].astype("boolean")
                else:
                    # Preserve the pre-1.1 full-mode calculations and fill
                    # behaviour exactly when live augmentation is not opted in.
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
                        df["Per_capita_buy_retail"] / df["Per_capita_sell_retail"],
                        3,
                    )
                    df["Power_institutional"] = round(
                        df["Per_capita_buy_institutional"]
                        / df["Per_capita_sell_institutional"],
                        3,
                    )

                df = add_date_columns(df, stock_name)
                if not include_today:
                    df.fillna(value=0, inplace=True)

                df = apply_date_format(df, mdate_format)
                if df is None:
                    return None
                if moutput_type == "standard":
                    standard_columns = [
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
                    ]
                    df = df.loc[:, standard_columns]
                elif moutput_type == "full":
                    pass
                else:
                    print("output_type should select between 'standard' or 'full'")
                    return None
                return df
        except requests.exceptions.RequestException:
            print("Connection Error!")
            return None
        except AmbiguousSymbolError:
            raise
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
        if df is not None and include_today:
            include_status["include_today_appended"] = [
                name
                for name, trade_date in append_candidates.items()
                if _index_contains_date(df.index, trade_date)
            ]
            df.attrs.update(include_status)
        if df is not None and not ascending:
            result = df.iloc[::-1]
            if include_today:
                result.attrs.update(include_status)
            return result
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
                    if include_today:
                        structural = [
                            column
                            for column in df.columns
                            if str(column[0]).startswith(("N_", "Vol_"))
                        ]
                        if structural:
                            df.dropna(subset=structural, inplace=True)
                    else:
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
    include_today=False,
    *,
    ins_code=None,
    asset_type="auto",
    **kwargs,
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
        include_today=include_today,
        ins_code=ins_code,
        asset_type=asset_type,
    )


# symbol capital increase version 1
def stock_capital_increase(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
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
    if not symbol and ins_code is not None:
        symbol = str(ins_code)
    web_id = search_stock(search_txt=symbol, ins_code=ins_code, asset_type=asset_type)
    if web_id is None or len(str(web_id)) == 0:
        print("Stock Not Found, Please try again ...")
        return None
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
