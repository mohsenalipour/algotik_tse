import requests
import warnings
import pandas as pd
from persiantools import characters
from algotik_tse.settings import Settings

warnings.simplefilter(action='ignore', category=FutureWarning)

settings = Settings()


def stocklist(bourse=True, farabourse=True, payeh=True, haghe_taqadom=False, sandogh=False, output="dataframe",
              progress=True):
    """
    Get all symbols in bourse, farabourse, payeh, haghe_taqadom from tsetmc
    :param bourse:          if True you can get all bourse symbols in output.
                            Default value is True.
    :param farabourse:      if True you can get all farabourse symbols in output.
                            Default value is True.
    :param payeh:           if True you can get all payeh symbols in output.
                            Default value is True.
    :param haghe_taqadom:   if True you can get all payeh symbols in output.
                            Default value is False.
    :param sandogh:         if True you can get all sandogh symbols in output.
                            Default value is False.
    :param output:          you can choose output format between :
                                dataftame(stock with detal) and
                                list(stocks name only)
                            Default value is False.
    :param progress:        if True, show progress and report in console.
                            Default value is True.

    :return: pandas dataframe or list
    """
    if not bourse and not farabourse and not payeh and not haghe_taqadom and not sandogh:
        print("You should select at least one market!")
        return None
    else:
        markets_text_list = []
        if bourse:
            markets_text_list.append('bourse')
        if farabourse:
            markets_text_list.append('farabourse')
        if payeh:
            markets_text_list.append('payeh')
        if haghe_taqadom:
            markets_text_list.append('haghe taqadom')
        if sandogh:
            markets_text_list.append('sandogh')

        markets_text = ""
        for n in range(len(markets_text_list)):
            if n == 0:
                markets_text += markets_text_list[n]
            else:
                markets_text += (", " + markets_text_list[n])
        if progress:
            print("Getting all of {} symbols...".format(markets_text), flush=True)

        try:
            req = requests.get(settings.url_stock_list)
            df = pd.read_html(req.content, encoding='utf8', extract_links='body')[0]

            df.rename(columns={'کد 12 رقمی نماد [Instrument ISIN]': 'instrument_isin',
                               'کد 4 رقمی شرکت [Company Code]': 'company_code',
                               'نام انگلیسی [English Name]': 'english_name',
                               'کد 12 رقمی شرکت [Company ISIN]': 'company_isin', 'بازار': 'market',
                               'گروه صنعت': 'industry_group', 'نوع [Type]': 'type'}, inplace=True)
            df['name'] = df['نماد [Name]'].str[0]
            df['instrument_isin'] = df['instrument_isin'].str[0]
            df['company_code'] = df['company_code'].str[0]
            df['english_name'] = df['english_name'].str[0]
            df['company_isin'] = df['company_isin'].str[0]
            df['market'] = df['market'].str[0]
            df['industry_group'] = df['industry_group'].str[0]
            df['instrument_id'] = df['نماد [Name]'].str[-1]
            df['instrument_id'] = df['instrument_id'].str.strip().str.split('=').str[-1]
            df['instrument_id'] = df['instrument_id'].str.split('/').str[-1]

            df.drop(columns=['نماد [Name]', 'type'], inplace=True)

            def split_symbol(group):
                dd = group.split('(')
                if 'هلد' in dd[1] or 'سهامی' in dd[1]:
                    xx = dd[2].split(")")[0].strip()
                else:
                    xx = dd[1].split(")")[0].strip()
                return xx

            allowed_markets = []

            group_not_allowed = ['اوراق حق تقدم استفاده از تسهيلات مسكن']
            not_all = ['بازار سوم فرابورس', '-', 'بازار عادي آتي']

            df_final = pd.DataFrame()

            if bourse or farabourse or payeh:
                allowed_pre_instrument_isin = ['IRO1', 'IRO2', 'IRO3', 'IRO4', 'IRO5', 'IRO7']
                if bourse:
                    allowed_markets.extend(
                        ['بازار دوم بورس', 'بازار اول (تابلوي فرعي) بورس', 'بازار اول (تابلوي اصلي) بورس'])
                if farabourse:
                    allowed_markets.extend(['بازار اول فرابورس', 'شرکتهاي کوچک و متوسط فرابورس', 'بازار دوم فرابورس'])
                if payeh:
                    allowed_markets.extend(
                        ['بازار پايه نارنجي فرابورس', 'بازار پایه قرمز فرابورس', 'بازار پايه زرد فرابورس',
                         'بازار پايه قرمز فرابورس'])

                df_filtered = df[(df['instrument_isin'].str.slice(stop=4).isin(allowed_pre_instrument_isin)) & (
                    ~df['industry_group'].isin(group_not_allowed)) & (df['instrument_isin'].str.slice(-1) == '1')]
                df_filtered = df_filtered[~df_filtered['market'].isin(not_all)]
                df_filtered = df_filtered[df_filtered['market'].isin(allowed_markets)]
                df_final = pd.concat([df_final, df_filtered])

            if haghe_taqadom:
                allowed_pre_instrument_isin = ['IRR1', 'IRR3', 'IRR5', 'IRR7']
                df_filtered = df[(df['instrument_isin'].str.slice(stop=4).isin(allowed_pre_instrument_isin)) & (
                    ~df['industry_group'].isin(group_not_allowed)) & (df['instrument_isin'].str.slice(-1) == '1')]
                df_filtered = df_filtered[~df_filtered['market'].isin(not_all)]
                df_final = pd.concat([df_final, df_filtered])

            if sandogh:
                allowed_pre_instrument_isin = ['IRT1', 'IRT3', 'IRTE', 'IRTK']
                df_filtered = df[(df['instrument_isin'].str.slice(stop=4).isin(allowed_pre_instrument_isin) & (
                    df['instrument_isin'].str.slice(-1) == '1'))]
                df_final = pd.concat([df_final, df_filtered])
        except:
            df_final = pd.DataFrame()

        if df_final.shape[0] != 0:
            df_final['name'] = df_final['name'].str.strip().apply(characters.ar_to_fa)
            df_final['symbol'] = df_final['name'].apply(split_symbol)
            df_final.set_index('symbol', drop=True, inplace=True)
            df_final['name'] = df_final['name'].str.split('(').str[0]
            df_final['name'] = df_final['name'].str.replace('\u200c', ' ').str.strip()
            df_final['market'] = df_final['market'].str.strip().apply(characters.ar_to_fa)
            df_final['market'] = df_final['market'].str.replace('\u200c', ' ').str.strip()
            df_final['industry_group'] = df_final['industry_group'].str.strip().apply(characters.ar_to_fa)
            df_final['industry_group'] = df_final['industry_group'].str.replace('\u200c', ' ').str.strip()
            df_final = df_final.loc[:,
                       ['name', 'instrument_isin', 'english_name', 'company_code', 'company_isin', 'market',
                        'industry_group', 'instrument_id']]

            if output == "dataframe":
                if progress:
                    print("The dataframe of all {} symbols is ready!".format(markets_text))
                return df_final
            elif output == "list":
                if progress:
                    print("The list of all {} symbols is ready!".format(markets_text))
                symbols_list = df_final.index.to_list()
                return symbols_list
            else:
                print("You should select output only in 'dataframe' or 'list'!!!")
                return None
        else:
            print("Connection Error!!!")
            return None
