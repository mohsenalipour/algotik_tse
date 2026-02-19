import pandas as pd
from algotik_tse.settings import settings
from algotik_tse.providers.tgju_convertor import tgju_convertor
from algotik_tse.core.helper import date_fix, apply_date_format, apply_return_type, filter_by_date_or_values
from algotik_tse.http_client import safe_get


def currency_coin(name="", start=None, end=None, limit=0, output_type="standard",
                  date_format="jalali", progress=True, save_to_file=False, dropna=True,
                  return_type=None, ascending=True, save_path=None, **kwargs):
    """
        Get symbol or symbols price history from tsetmc
        :param name:currency or coin name in persian or english, or a list of currency or  in
                                    persian (['euro', 'سکه امامی'])
                                Default value is 'dollar'.
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
        :param output_type:     you can choose between 'standard' and 'complete'.
                                Default value is 'standard'.
                                if output_type='standard', you get OHLC in output.
                                if output_type='complete', you get OHLC and 'Weekday', 'Ticker' in output.
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
        :param save_to_file:    if True, save currency(ies) or coin(s) historical data with customized
                                    columns in .csv format.
                                Default value is False.
                                the file name is 'currency.csv' in same root that
                                    your file is there. for example: 'dollar.csv'
        :param multi_currencies_drop:if True, when you enter currency or coin list, it will delete
                                    rows of none data (dropna) in combined historical df.
                                Default value is True.
        :param return_type:     you can choose between 'simple', 'log' and 'both', or enter ['simple', 'Close', 5] format.
                                if return_type='simple', you get simple return in 1 day on Close.
                                    with simple return 'returns' in complete mode in output.
                                if return_type='log', you get log return in 1 day on Close.
                                    with log return 'returns' in complete mode in output.
                                if return_type='both', you get simple and log return in 1 day onClose.
                                    with both return 'simple_returns' and 'log_returns' in complete mode in output.
                                if return_type=['simple', 'Close', 5], you get simple return in 5 day on Close.
                                    with this 'returns' in complete mode in output.

        :return: pandas dataframe or None
        """
    # Backward compatibility: accept deprecated keyword names
    if not name and 'currency_coin_name' in kwargs:
        name = kwargs.pop('currency_coin_name')
    if 'values' in kwargs:
        limit = kwargs.pop('values')
    if 'multi_currencies_drop' in kwargs:
        dropna = kwargs.pop('multi_currencies_drop')

    # Support legacy output_type value 'complete' → 'full'
    if output_type == 'full':
        output_type = 'full'

    # Internal aliases for existing code
    values = limit
    multi_currencies_drop = dropna

    import os

    def _save_csv(df, filename):
        if save_path:
            os.makedirs(save_path, exist_ok=True)
            filepath = os.path.join(save_path, filename)
        else:
            filepath = filename
        df.to_csv(filepath, encoding="utf-8-sig")

    def _apply_ascending(df):
        if df is not None and not ascending:
            return df.iloc[::-1]
        return df

    def __get_currency_history(currency__name):
        url_word = settings.currency_web_word[currency__name]['web_word']
        new_start, new_end = date_fix(start=start, end=end)
        detail = safe_get(settings.url_currency_from_tgju.format(url_word))
        if detail.status_code == 200:
            df = tgju_convertor(detail.json()['data'])
            if values is not None or start is not None or end is not None:
                df = filter_by_date_or_values(df, values, new_start, new_end)

            df["Weekday_No"] = df["Date"].dt.weekday
            df["Weekday"] = df["Weekday_No"].apply(lambda x: settings.en_weekdays[x])
            df["Weekday_fa"] = df["Weekday_No"].apply(lambda x: settings.fa_weekdays[x])
            df.drop("Weekday_No", axis=1, inplace=True)
            df['Ticker'] = settings.currency_web_word[currency__name]['persian_word']

            df = apply_date_format(df, date_format)
            if df is None:
                return None

            if output_type == "standard":
                df = df.loc[:, "Open High Low Close".split()]
            elif output_type == 'full':
                pass
            else:
                print("output_type should select between 'standard' or 'full'")
                return None

            df = apply_return_type(df, return_type, default_price='Close')
            if df is None:
                return None
            return df
        else:
            print("Connection Error!!!")
            return None

    if name == "":
        name = "dollar"
        if progress:
            print("1/1: Getting historical price of {}".format(name))
        df = __get_currency_history(currency__name=name)
        if progress and df is not None:
            print("1/1: Completed!")
        if save_to_file and df is not None:
            if progress:
                print("Saving to file: {}.csv".format(name))
            _save_csv(df, name + ".csv")
        return _apply_ascending(df)
    else:
        if isinstance(name, str):
            name = name if name.isascii() else settings.currency_persian[
                name]
            if progress:
                print("1/1: Getting historical price of {}".format(name))
            df = __get_currency_history(currency__name=name)
            if progress and df is not None:
                print("1/1: Completed!")
            if save_to_file and df is not None:
                if progress:
                    print("Saving to file: {}.csv".format(name))
                _save_csv(df, name + ".csv")
            return _apply_ascending(df)
        elif isinstance(name, list):
            n = 1
            df_dict = {}
            file_name_str = ''
            for cur in name:
                cur = cur if cur.isascii() else settings.currency_persian[cur]
                if progress:
                    print("{}/{}: Getting historical price of {}".format(n, len(name), cur))
                df = __get_currency_history(currency__name=cur)
                if df is not None:
                    file_name_str += "-" + cur
                    df_dict[cur] = df
                else:
                    print("{} not Found!".format(cur))
                n += 1
            if progress:
                print('{}/{} Completed!'.format(len(name), len(name)))

            if len(list(df_dict.keys())) == 0:
                print('None of the entered currencies exist!!')
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

                if multi_currencies_drop:
                    df.dropna(inplace=True)
                if save_to_file and df is not None:
                    if progress:
                        print("Saving to file: {}.csv".format(file_name_str[1:]))
                    _save_csv(df, file_name_str[1:] + ".csv")
                return _apply_ascending(df)
