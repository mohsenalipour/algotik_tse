import requests
import pandas as pd
import numpy as np
from algotik_tse.settings import settings
from algotik_tse.providers.tgju_convertor import tgju_convertor
from algotik_tse.core.helper import date_fix


def currency_coin(currency_coin_name="", start=None, end=None, values=0, output_type="standard",
                  date_format="jalali", progress=True, save_to_file=False, multi_currencies_drop=True,
                  return_type=None):
    """
        Get symbol or symbols price history from tsetmc
        :param currency_coin_name:currency or coin name in persian or english, or a list of currency or  in
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

    def __get_currency_history(currency__name):
        url_word = settings.currency_web_word[currency__name]['web_word']
        new_start, new_end = date_fix(start=start, end=end)
        detail = requests.get(settings.url_currency_from_tgju.format(url_word), headers=settings.headers)
        if detail.status_code == 200:
            df = tgju_convertor(detail.json()['data'])
            if values is not None or start is not None or end is not None:
                if values != 0:
                    df = df.iloc[-values:]
                else:
                    if end is None:
                        df = df.loc[new_start:]
                    else:
                        df = df.loc[new_start:new_end]

            df["Weekday_No"] = df["Date"].dt.weekday
            df["Weekday"] = df["Weekday_No"].apply(lambda x: settings.en_weekdays[x])
            df["Weekday_fa"] = df["Weekday_No"].apply(lambda x: settings.fa_weekdays[x])
            df.drop("Weekday_No", axis=1, inplace=True)
            df['Ticker'] = settings.currency_web_word[currency__name]['persian_word']

            if date_format == 'jalali':
                df.set_index('J-Date', drop=True, inplace=True)
                df.drop(columns=["Date", "Weekday"], inplace=True)
            elif date_format == 'gregorian':
                df.set_index('Date', drop=True, inplace=True)
                df.drop(columns=["J-Date", 'Weekday_fa'], inplace=True)
            elif date_format == 'both':
                df.set_index('Date', drop=True, inplace=True)
            else:
                print("please select date_format between 'jalali', 'gregorian ', 'both' ")
                return None

            if output_type == "standard":
                df = df.loc[:, "Open High Low Close".split()]
            elif output_type == 'complete':
                pass
            else:
                print("output_type should select between 'standard' or 'complete'")
                return None

            if return_type is not None:
                price = 'Close'
                if isinstance(return_type, str):
                    if return_type == 'simple':
                        df['returns'] = df[price].pct_change()
                    elif return_type == 'log':
                        df['returns'] = np.log(df[price] / df[price].shift(1))
                    elif return_type == 'both':
                        df['simple_returns'] = df[price].pct_change()
                        df['log_returns'] = np.log(df[price] / df[price].shift(1))
                    else:
                        print("return_type should select between 'simple', 'log' or ''both")
                        return None
                elif isinstance(return_type, list) and len(return_type) == 3:
                    # ['simple', 'Close', 2]
                    if return_type[0] == 'simple':
                        df['returns'] = df[return_type[1]].pct_change(return_type[2])
                    elif return_type[0] == 'log':
                        df['returns'] = np.log(
                            df[return_type[1]] / df[return_type[1]].shift(return_type[2]))
                    elif return_type[0] == 'both':
                        df['simple_returns'] = df[return_type[1]].pct_change(return_type[2])
                        df['log_returns'] = np.log(
                            df[return_type[1]] / df[return_type[1]].shift(return_type[2]))
                    else:
                        print("return_type[0] should select between 'simple', 'log' or ''both")
                        return None
                else:
                    print(
                        "return_type should select between 'simple', 'log' or 'both' or enter a list like this: ['simple', 'Close', 3]")
                    return None
            return df
        else:
            print("Connection Error!!!")
            return None

    if currency_coin_name == "":
        currency_coin_name = "dollar"
        if progress:
            print("1/1: Getting historical price of {}".format(currency_coin_name))
        df = __get_currency_history(currency__name=currency_coin_name)
        if progress and df is not None:
            print("1/1: Completed!")
        if save_to_file and df is not None:
            if progress:
                print("Saving to file: {}.csv".format(currency_coin_name))
            df.to_csv(currency_coin_name + ".csv", encoding="utf-8-sig")
        return df
    else:
        if isinstance(currency_coin_name, str):
            currency_coin_name = currency_coin_name if currency_coin_name.isascii() else settings.currency_persian[
                currency_coin_name]
            if progress:
                print("1/1: Getting historical price of {}".format(currency_coin_name))
            df = __get_currency_history(currency__name=currency_coin_name)
            if progress and df is not None:
                print("1/1: Completed!")
            if save_to_file and df is not None:
                if progress:
                    print("Saving to file: {}.csv".format(currency_coin_name))
                df.to_csv(currency_coin_name + ".csv", encoding="utf-8-sig")
            return df
        elif isinstance(currency_coin_name, list):
            n = 1
            df_dict = {}
            file_name_str = ''
            for cur in currency_coin_name:
                cur = cur if cur.isascii() else settings.currency_persian[cur]
                if progress:
                    print("{}/{}: Getting historical price of {}".format(n, len(currency_coin_name), cur))
                df = __get_currency_history(currency__name=cur)
                if df is not None:
                    file_name_str += "-" + cur
                    df_dict[cur] = df
                else:
                    print("{} not Found!".format(cur))
                n += 1
            if progress:
                print('{}/{} Completed!'.format(len(currency_coin_name), len(currency_coin_name)))

            if len(list(df_dict.keys())) == 0:
                print('None of the entered currencies exist!!')
                return None
            elif len(list(df_dict.keys())) == 1:
                df = df_dict[list(df_dict.keys())[0]]
                if save_to_file and df is not None:
                    if progress:
                        print("Saving to file: {}.csv".format(file_name_str[1:]))
                    df.to_csv(file_name_str[1:] + ".csv", encoding="utf-8-sig")
                return df
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
                    df.to_csv(file_name_str[1:] + ".csv", encoding="utf-8-sig")
                return df
