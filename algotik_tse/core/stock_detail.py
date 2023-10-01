import requests
import warnings
import pandas as pd
from algotik_tse.settings import Settings
from algotik_tse.core.search import search_stock
warnings.simplefilter(action='ignore', category=FutureWarning)

settings = Settings()


def stockdetail(stock):
    """
    Get all symbol detail
    :param stock: name of stock
                  Default value is 'شتران'.

    :return: pandas dataframe
    """
    web_id = search_stock(search_txt=stock)
    if len(web_id) != 0:
        if web_id[-5:] == "index":
            print("This is an index, no information found!")
            return None
        else:
            detail = requests.get(settings.url_detail.format(web_id), headers=settings.headers)
            if detail.status_code == 200:
                df = pd.read_html(detail.content, encoding='utf8')[0]
                df.rename(columns={0: 'key', 1: 'value'}, inplace=True)
                df.set_index('key', drop=True, inplace=True)
                df.loc['id'] = str(web_id)
                return df
            else:
                print("Connection Error!!!")
                return None
    else:
        print("Stock Not Found, Please try again ...")
        return None
