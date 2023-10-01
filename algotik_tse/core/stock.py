import io
import datetime
import requests
import warnings
import pandas as pd
from persiantools import characters
from persiantools.jdatetime import JalaliDate

from algotik_tse.settings import Settings
from algotik_tse.core.search import search_stock
from algotik_tse.core.helper import date_fix

warnings.simplefilter(action='ignore', category=FutureWarning)

settings = Settings()


def stock(stock="", start=None, end=None, values=0, tse_format=False, auto_adjust=True, output_type="standard",
          date_format="jalali", progress=True, save_to_file=False, multi_stock_drop=True, adjust_volume=False):
    """
    Get symbol or symbols price history from tsetmc
    :param stock:           stock name in persian, or a list of stock in
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
    :param auto_adjust:     if True, adjust all OHLC price, with stock splits and dps.
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
    :param save_to_file:    if True, save stock(s) historical data with customized
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

    :return: pandas dataframe or None
    """
    def _get_stock(stock_name, mstart, mend, mvalues, mtse_format, mauto_adjust, moutput_type, mdate_format, ):
        web_id = search_stock(search_txt=stock_name)
        _price_base_url = settings.url_price_history
        isIndex = False
        if web_id[-5:] == "index":
            web_id = web_id[:-5]
            _price_base_url = settings.url_index_history
            isIndex = True
        new_start, new_end = date_fix(start=mstart, end=mend)
        if new_start is not None or new_end is not None:
            mvalues = 0
        if isIndex:
            index_names = {'32097828799138957': 'Overall Index',
                           '67130298613737946': 'Total Equal Weighted Index',
                           '5798407779416661': 'Total Price Index',
                           '8384385859414435': 'Equal Weighted Price Index',
                           '49579049405614711': 'Free Float Index',
                           '62752761908615603': 'OTC Main Board Index',
                           '71704845530629737': 'OTC Secondary Board Index',
                           '43754960038275285': 'Industry Index',
                           '10523825119011581': 'Top 30 Index',
                           '46342955726788357': 'Top 50 Index'}
            try:
                data = {"<TICKER>": [], "<DTYYYYMMDD>": [], "<FIRST>": [], "<HIGH>": [], "<LOW>": [], "<CLOSE>": [],
                        "<VOL>": [], "<PER>": [], "<OPEN>": [], "<LAST>": []}
                fopen = requests.get(_price_base_url.format(web_id), headers=settings.headers).text.split(";")
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
                    data["<PER>"].append('D')
                    data["<OPEN>"].append(float(dts[3]))
                    data["<LAST>"].append(float(dts[4]))

                df = pd.DataFrame(data, columns=data.keys(), index=pd.DatetimeIndex(data["<DTYYYYMMDD>"]))
                df.index.names = ['<DTYYYYMMDD>']
                df.drop(columns=['<DTYYYYMMDD>'], inplace=True)
                df = df.iloc[::-1, :]
                if mvalues != 0:
                    df = df.iloc[:mvalues]
                    df = df.iloc[::-1, :]
                else:
                    if new_end is None:
                        df = df[new_start:]
                    else:
                        df = df[new_start:new_end]
                    df = df.iloc[::-1, :]
                if mtse_format:
                    return df
                else:
                    df.index.rename("Date_base", inplace=True)
                    df.drop(["<TICKER>", "<PER>", "<OPEN>"], axis=1, inplace=True)
                    df.rename(columns={"<FIRST>": "Open", "<HIGH>": "High", "<LOW>": "Low", "<CLOSE>": "Adj Close",
                                       "<VOL>": "Volume", "<LAST>": "Close"}, inplace=True)
                    df = df.loc[:, ["Open", "High", "Low", "Close", "Adj Close", "Volume", ]]
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

                    if mauto_adjust:
                        df.drop("Adj Close", axis=1, inplace=True)
                        if mdate_format == "jalali":
                            df.set_index("J-Date", drop=True, inplace=True)
                            df.drop(columns=["Date", "Weekday"], inplace=True)
                        elif mdate_format == "gregorian":
                            df.set_index("Date", drop=True, inplace=True)
                            df.drop(columns=["J-Date", "Weekday_fa"], inplace=True)
                        elif mdate_format == "both":
                            df.set_index("Date", drop=True, inplace=True)
                        else:
                            print("please select date_format between 'jalali', 'gregorian ', 'both' ")
                            return None
                        if moutput_type == "standard":
                            df = df.loc[:, ['Open', 'High', 'Low', 'Close', 'Volume']]
                        elif moutput_type == "complete":
                            pass
                        else:
                            print("output_type should select between 'standard' or 'complete'")
                            return None
                    else:
                        if mdate_format == "jalali":
                            df.set_index("J-Date", drop=True, inplace=True)
                            df.drop(columns=["Date", "Weekday"], inplace=True)
                        elif mdate_format == "gregorian":
                            df.set_index("Date", drop=True, inplace=True)
                            df.drop(columns=["J-Date", "Weekday_fa"], inplace=True)
                        elif mdate_format == "both":
                            df.set_index("Date", drop=True, inplace=True)
                        else:
                            print("please select date_format between 'jalali', 'gregorian', 'both' ")
                            return None
                        if moutput_type == "standard":
                            df = df.loc[:, ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']]
                        elif moutput_type == "complete":
                            pass
                        else:
                            print("output_type should select between 'standard' or 'complete'")
                            return None
                    return df
            except:
                print("Connection Error!")
                return None
        else:
            try:
                fopen = requests.get(_price_base_url.format(web_id), headers=settings.headers).content
                df = pd.read_csv(io.StringIO(fopen.decode("utf-8")), index_col="<DTYYYYMMDD>", parse_dates=True)
                if mvalues != 0:
                    df = df.iloc[:mvalues]
                    df = df.iloc[::-1, :]
                else:
                    if new_end is None:
                        df = df[new_start:]
                    else:
                        df = df[new_start:new_end]
                    df = df.iloc[::-1, :]
                if mtse_format:
                    return df
                else:
                    df.index.rename("Date_base", inplace=True)
                    df.drop(["<TICKER>", "<PER>"], axis=1, inplace=True)
                    df.rename(columns={"<FIRST>": "Open", "<HIGH>": "High", "<LOW>": "Low", "<CLOSE>": "Final",
                                       "<VALUE>": "Value", "<VOL>": "Volume", "<OPENINT>": "No.",
                                       "<OPEN>": "Yesterday-Final", "<LAST>": "Close"}, inplace=True)
                    df = df.loc[:,
                         ["Open", "High", "Low", "Close", "Final", "Volume", "Yesterday-Final", "No.", "Value"]]
                    df["Final+1"] = df["Final"].shift(1)
                    df['pos'] = df.apply(
                        lambda x: x['Yesterday-Final'] if (
                            (x['Yesterday-Final'] != 0) and (x['Yesterday-Final'] != 1000))
                        else (x['Yesterday-Final'] if (pd.isnull(x['Final+1'])) else x['Final+1']), axis=1)
                    df['Yesterday-Final'] = df['pos']
                    df.drop(columns=['Final+1', 'pos'], inplace=True)
                    df['coef'] = (df['Yesterday-Final'].shift(-1) / df['Final']).fillna(1.)
                    df['Adj coef'] = df.iloc[::-1]['coef'].cumprod().iloc[::-1]
                    df['Adj Vol coef'] = 1 / df['Adj coef']
                    df['Adj Close'] = (df['Close'] * df['Adj coef']).apply(lambda x: int(x))
                    df['Adj Open'] = (df['Open'] * df['Adj coef']).apply(lambda x: int(x))
                    df['Adj High'] = (df['High'] * df['Adj coef']).apply(lambda x: int(x))
                    df['Adj Low'] = (df['Low'] * df['Adj coef']).apply(lambda x: int(x))
                    df['Adj Final'] = (df['Final'] * df['Adj coef']).apply(lambda x: int(x))
                    df['Adj Volume'] = (df['Volume'] * df['Adj Vol coef']).apply(lambda x: int(x))
                    df.drop(columns=['coef', 'Adj coef', 'Adj Vol coef'], inplace=True)
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
                    if mauto_adjust:
                        if adjust_volume:
                            df = df.loc[:,
                                 ['Adj Open', 'Adj High', 'Adj Low', 'Adj Close', 'Adj Final', 'Volume', 'Adj Volume',
                                  'No.', 'Value', 'Date', 'J-Date', 'Weekday', 'Weekday_fa', 'Ticker']]
                        else:
                            df = df.loc[:, ['Adj Open', 'Adj High', 'Adj Low', 'Adj Close', 'Adj Final', 'Volume',
                                            'No.', 'Value', 'Date', 'J-Date', 'Weekday', 'Weekday_fa', 'Ticker']]
                        df.rename(columns={'Adj Open': 'Open', 'Adj High': 'High', 'Adj Low': 'Low',
                                           'Adj Close': 'Close', 'Adj Final': 'Final'}, inplace=True)
                        if mdate_format == "jalali":
                            df.set_index("J-Date", drop=True, inplace=True)
                            df.drop(columns=["Date", "Weekday"], inplace=True)
                        elif mdate_format == "gregorian":
                            df.set_index("Date", drop=True, inplace=True)
                            df.drop(columns=["J-Date", "Weekday_fa"], inplace=True)
                        elif mdate_format == "both":
                            df.set_index("Date", drop=True, inplace=True)
                        else:
                            print("please select date_format between 'jalali', 'gregorian ', 'both' ")
                            return None
                        if moutput_type == "standard":
                            df = df.loc[:, ['Open', 'High', 'Low', 'Close', 'Volume']]
                        elif moutput_type == "complete":
                            pass
                        else:
                            print("output_type should select between 'standard' or 'complete'")
                            return None
                    else:
                        if adjust_volume:
                            df = df.loc[:,
                                 ['Open', 'High', 'Low', 'Close', 'Final', 'Adj Close', 'Volume', 'Adj Volume',
                                  'No.', 'Value', 'Date', 'J-Date', 'Weekday', 'Weekday_fa', 'Ticker']]
                        else:
                            df = df.loc[:, ['Open', 'High', 'Low', 'Close', 'Final', 'Adj Close', 'Volume',
                                            'No.', 'Value', 'Date', 'J-Date', 'Weekday', 'Weekday_fa', 'Ticker']]
                        if mdate_format == "jalali":
                            df.set_index("J-Date", drop=True, inplace=True)
                            df.drop(columns=["Date", "Weekday"], inplace=True)
                        elif mdate_format == "gregorian":
                            df.set_index("Date", drop=True, inplace=True)
                            df.drop(columns=["J-Date", "Weekday_fa"], inplace=True)
                        elif mdate_format == "both":
                            df.set_index("Date", drop=True, inplace=True)
                        else:
                            print("please select date_format between 'jalali', 'gregorian', 'both' ")
                            return None
                        if moutput_type == "standard":
                            df = df.loc[:, ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']]
                        elif moutput_type == "complete":
                            pass
                        else:
                            print("output_type should select between 'standard' or 'complete'")
                            return None
                    return df

            except:
                print("Stock Not Found!")
                return None

    if stock == "":
        stock = "شتران"
        if progress:
            print("1/1: Getting historical price of {}".format(stock))
        stock = characters.ar_to_fa(stock).strip("\u200c").strip()
        df = _get_stock(stock_name=stock, mstart=start, mend=end, mvalues=values, mtse_format=tse_format,
                        mauto_adjust=auto_adjust, moutput_type=output_type, mdate_format=date_format)
        if progress and df is not None:
            print("1/1: Completed!")
        if save_to_file and df is not None:
            if progress:
                print("Saving to file: {}.csv".format(stock))
            df.to_csv(stock + ".csv", encoding="utf-8-sig")
        return df
    else:
        if isinstance(stock, str):
            if progress:
                print("1/1: Getting historical price of {}".format(stock))
            stock = characters.ar_to_fa(stock).strip("\u200c").strip()
            df = _get_stock(stock_name=stock, mstart=start, mend=end, mvalues=values, mtse_format=tse_format,
                            mauto_adjust=auto_adjust, moutput_type=output_type, mdate_format=date_format)
            if progress and df is not None:
                print("1/1: Completed!")
            if save_to_file and df is not None:
                if progress:
                    print("Saving to file: {}.csv".format(stock))
                df.to_csv(stock + ".csv", encoding="utf-8-sig")
            return df
        elif isinstance(stock, list):
            n = 1
            df_dict = {}
            file_name_str = ''
            for stk in stock:
                if progress:
                    print("{}/{}: Getting historical price of {}".format(n, len(stock), stk))
                stk = characters.ar_to_fa(stk).strip("\u200c").strip()
                df = _get_stock(stock_name=stk, mstart=start, mend=end, mvalues=values, mtse_format=tse_format,
                                mauto_adjust=auto_adjust, moutput_type=output_type, mdate_format=date_format)
                if df is not None:
                    file_name_str += "-" + stk
                    df_dict[stk] = df
                else:
                    print("{} not Found!".format(stk))
                n += 1
            if progress:
                print('{}/{} Completed!'.format(len(stock), len(stock)))

            if len(list(df_dict.keys())) == 0:
                print('None of the entered stocks exist!!')
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
                if multi_stock_drop:
                    df.dropna(inplace=True)
                if save_to_file and df is not None:
                    if progress:
                        print("Saving to file: {}.csv".format(file_name_str[1:]))
                    df.to_csv(file_name_str[1:] + ".csv", encoding="utf-8-sig")
                return df


def stock_RL(stock="", start=None, end=None, values=0, tse_format=False, output_type="standard", date_format="jalali",
             progress=True, save_to_file=False, multi_stock_drop=True):
    """
    Get symbol or symbols real/legal history from tsetmc
    :param stock:           stock name in persian, or a list of stock in
                                persian (['شتران', 'آریا'])
                            Default value is 'شتران'.
    :param start:           you can choose strat date (from) to get historical real/legal.
                            enter date in jalali only in isoformat ('1401-10-01')
                                and gregorian in isoformat("2022-12-22") or
                                ("2022") or ("2022-12")
                            Default value is None.
                            if start=None and end=None, value can apply to real/legal data.
    :param end:             you can choos end date (to) to get historical real/legal.
                            enter date in jalali only in isoformat ('1401-10-01')
                                and gregorian in isoformat ("2022-12-22") or
                                ("2022") or ("2022-12")
                            Default value is None.
                            if start=None and end=None, 'values' can apply to real/legal data.
    :param values:          Specifies the number of price data since today
                            Default value is 225.
                            'values' can be applied when start=None and end=None.
    :param tse_format:      if True you can get all historical real/legal data in tse .csv format
                            Default value is False.
                            if tse_format=True, ignore output_type, date_format!
    :param output_type:     you can choose between 'standard' and 'complete'.
                            Default value is 'standard'.
                            if output_type='standard', you get real/legal without per capitas
                                or powers in output.
                            if output_type='complete', you get real/legal with per capitas
                                and powers in output
    :param date_format:     you can choose between 'jalali' and 'gregorian' and 'both'.
                            Default value is 'jalali'.
                            if date_format='jalali', you get historical real/legal with
                                jalali date index and 'Weekday_fa' in complete mode
                                in output.
                            if output_type='gregorian', you get historical real/legal
                                with gregorian date index and 'Weekday' in complete
                                mode in output.
                            if output_type='both', you get historical real/legal with
                                gregorian date index and 'J-Date'(jalali date),
                                'Weekday', 'Weekday_fa' in complete mode in output.
    :param progress:        if True, show progress and report in console.
                            Default value is True.
    :param save_to_file:    if True, save stock(s) historical real/legal data with customized
                                columns in .csv format.
                            Default value is False.
                            the file name is 'stock.csv' in same root that
                                tsemodule6 is there. for example: 'شتران.csv'
    :param multi_stock_drop:if True, when you enter stocks list, it will delete
                                rows of none data (dropna) in combined historical df.
                            Default value is True.

    :return: pandas dataframe or None
    """
    def _get_stock_RL(stock_name, mstart, mend, mvalues, mtse_format, moutput_type, mdate_format):
        web_id = search_stock(search_txt=stock_name)
        client_type_base_url = settings.url_client_type
        if web_id[-5:] == "index":
            print("{} is an index, Please enter a valid stock name!".format(stock_name))
            return None
        new_start, new_end = date_fix(start=mstart, end=mend)
        if new_start is not None or new_end is not None:
            mvalues = 0
        try:
            fopen = requests.get(client_type_base_url.format(web_id)).text.split(";")
            data = {"<DTYYYYMMDD>": [], "<TICKER>": [], "<N_BUY_REAL>": [], "<N_BUY_LEGAL>": [], "<N_SELL_REAL>": [],
                    "<N_SELL_LEGAL>": [],
                    "<VOL_BUY_REAL>": [], "<VOL_BUY_LEGAL>": [], "<VOL_SELL_REAL>": [], "<VOL_SELL_LEGAL>": [],
                    "<VAL_BUY_REAL>": [], "<VAL_BUY_LEGAL>": [], "<VAL_SELL_REAL>": [], "<VAL_SELL_LEGAL>": [],
                    "<PER>": []}

            for dt in fopen:
                dts = dt.split(",")
                date_iso = dts[0][:4] + "-" + dts[0][4:6] + "-" + dts[0][6:]
                data["<DTYYYYMMDD>"].append(datetime.date.fromisoformat(date_iso))
                data['<TICKER>'].append(stock_name)
                data['<N_BUY_REAL>'].append(int(dts[1]))
                data['<N_BUY_LEGAL>'].append(int(dts[2]))
                data['<N_SELL_REAL>'].append(int(dts[3]))
                data['<N_SELL_LEGAL>'].append(int(dts[4]))
                data['<VOL_BUY_REAL>'].append(int(dts[5]))
                data['<VOL_BUY_LEGAL>'].append(int(dts[6]))
                data['<VOL_SELL_REAL>'].append(int(dts[7]))
                data['<VOL_SELL_LEGAL>'].append(int(dts[8]))
                data['<VAL_BUY_REAL>'].append(int(dts[9]))
                data['<VAL_BUY_LEGAL>'].append(int(dts[10]))
                data['<VAL_SELL_REAL>'].append(int(dts[11]))
                data['<VAL_SELL_LEGAL>'].append(int(dts[12]))
                data['<PER>'].append('D')

            df = pd.DataFrame(data, columns=data.keys(), index=pd.DatetimeIndex(data["<DTYYYYMMDD>"]))
            df.index.names = ['<DTYYYYMMDD>']
            df.drop(columns=['<DTYYYYMMDD>'], inplace=True)

            if mvalues != 0:
                df = df.iloc[:mvalues]
                df = df.iloc[::-1, :]
            else:
                if new_end is None:
                    df = df[new_start:]
                else:
                    df = df[new_start:new_end]
                df = df.iloc[::-1, :]
            if mtse_format:
                return df
            else:
                df.index.rename("Date_base", inplace=True)
                df.drop(["<TICKER>", "<PER>"], axis=1, inplace=True)
                df.rename(columns={"<N_BUY_REAL>": "N_buy_real", "<N_BUY_LEGAL>": "N_buy_legal",
                                   "<N_SELL_REAL>": "N_sell_real", "<N_SELL_LEGAL>": "N_sell_legal",
                                   "<VOL_BUY_REAL>": "Vol_buy_real", "<VOL_BUY_LEGAL>": "Vol_buy_legal",
                                   "<VOL_SELL_REAL>": "Vol_sell_real", "<VOL_SELL_LEGAL>": "Vol_sell_legal",
                                   "<VAL_BUY_REAL>": "Val_buy_real", "<VAL_BUY_LEGAL>": "Val_buy_legal",
                                   "<VAL_SELL_REAL>": "Val_sell_real", "<VAL_SELL_LEGAL>": "Val_sell_legal"},
                          inplace=True)

                df['Per_capita_buy_real'] = round(df['Val_buy_real'] / df['N_buy_real'])
                df['Per_capita_sell_real'] = round(df['Val_sell_real'] / df['N_sell_real'])
                df['Per_capita_buy_legal'] = round(df['Val_buy_legal'] / df['N_buy_legal'])
                df['Per_capita_sell_legal'] = round(df['Val_sell_legal'] / df['N_sell_legal'])
                df['Power_real'] = round(df['Per_capita_buy_real'] / df['Per_capita_sell_real'], 3)
                df['Power_legal'] = round(df['Per_capita_buy_legal'] / df['Per_capita_sell_legal'], 3)

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
                df.fillna(value=0, inplace=True)

                if mdate_format == "jalali":
                    df.set_index("J-Date", drop=True, inplace=True)
                    df.drop(columns=["Date", "Weekday"], inplace=True)
                elif mdate_format == "gregorian":
                    df.set_index("Date", drop=True, inplace=True)
                    df.drop(columns=["J-Date", "Weekday_fa"], inplace=True)
                elif mdate_format == "both":
                    df.set_index("Date", drop=True, inplace=True)
                else:
                    print("please select date_format between 'jalali', 'gregorian ', 'both' ")
                    return None
                if moutput_type == "standard":
                    df = df.loc[:, ["N_buy_real", "N_buy_legal", "N_sell_real", "N_sell_legal", "Vol_buy_real",
                                    "Vol_buy_legal", "Vol_sell_real", "Vol_sell_legal", "Val_buy_real", "Val_buy_legal",
                                    "Val_sell_real", "Val_sell_legal", ]]
                elif moutput_type == "complete":
                    pass
                else:
                    print("output_type should select between 'standard' or 'complete'")
                    return None
                return df
        except:
            print("Stock Not Found!")
            return None

    if stock == "":
        stock = "شتران"
        if progress:
            print("1/1: Getting historical real/legal of {}".format(stock))
        stock = characters.ar_to_fa(stock).strip("\u200c").strip()
        df = _get_stock_RL(stock_name=stock, mstart=start, mend=end, mvalues=values, mtse_format=tse_format,
                           moutput_type=output_type, mdate_format=date_format)
        if progress and df is not None:
            print("1/1: Completed!")
        if save_to_file and df is not None:
            if progress:
                print("Saving to file: {}-حقیقی-حقوقی.csv".format(stock))
            df.to_csv(stock + "-حقیقی-حقوقی.csv", encoding="utf-8-sig")
        return df
    else:
        if isinstance(stock, str):
            if progress:
                print("1/1: Getting historical real/legal of {}".format(stock))
            stock = characters.ar_to_fa(stock).strip("\u200c").strip()
            df = _get_stock_RL(stock_name=stock, mstart=start, mend=end, mvalues=values, mtse_format=tse_format,
                               moutput_type=output_type, mdate_format=date_format)
            if progress and df is not None:
                print("1/1: Completed!")
            if save_to_file and df is not None:
                if progress:
                    print("Saving to file: {}-حقیقی-حقوقی.csv".format(stock))
                df.to_csv(stock + "-حقیقی-حقوقی.csv", encoding="utf-8-sig")
            return df
        elif isinstance(stock, list):
            n = 1
            df_dict = {}
            file_name_str = ''
            for stk in stock:
                if progress:
                    print("{}/{}: Getting historical real/legal of {}".format(n, len(stock), stk))
                stk = characters.ar_to_fa(stk).strip("\u200c").strip()
                df = _get_stock_RL(stock_name=stk, mstart=start, mend=end, mvalues=values, mtse_format=tse_format,
                                   moutput_type=output_type, mdate_format=date_format)
                if df is not None:
                    file_name_str += "-" + stk
                    df_dict[stk] = df
                else:
                    print("{} not Found!".format(stk))
                n += 1
            if progress:
                print('{}/{} Completed!'.format(len(stock), len(stock)))

            if len(list(df_dict.keys())) == 0:
                print('None of the entered stocks exist!!')
                return None
            elif len(list(df_dict.keys())) == 1:
                df = df_dict[list(df_dict.keys())[0]]
                if save_to_file and df is not None:
                    if progress:
                        print("Saving to file: {}-حقیقی-حقوقی.csv".format(file_name_str[1:]))
                    df.to_csv(file_name_str[1:] + "-حقیقی-حقوقی.csv", encoding="utf-8-sig")
                return df
            else:
                df = pd.concat(df_dict, axis=1)
                if multi_stock_drop:
                    df.dropna(inplace=True)
                if save_to_file and df is not None:
                    if progress:
                        print("Saving to file: {}-حقیقی-حقوقی.csv".format(file_name_str[1:]))
                    df.to_csv(file_name_str[1:] + "-حقیقی-حقوقی.csv", encoding="utf-8-sig")
                return df
