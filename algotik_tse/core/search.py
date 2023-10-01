import requests
from algotik_tse.settings import Settings

settings = Settings()


def search_stock(search_txt='شتران'):
    index_names = settings.index_names
    headers = settings.headers
    stock_id = ''
    if search_txt in index_names:
        webid_dict = {index_names[0]: 32097828799138957,
                      index_names[1]: 67130298613737946,
                      index_names[2]: 67130298613737946,
                      index_names[3]: 67130298613737946,
                      index_names[4]: 67130298613737946,
                      index_names[5]: 67130298613737946,
                      index_names[6]: 5798407779416661,
                      index_names[7]: 8384385859414435,
                      index_names[8]: 8384385859414435,
                      index_names[9]: 8384385859414435,
                      index_names[10]: 49579049405614711,
                      index_names[11]: 49579049405614711,
                      index_names[12]: 62752761908615603,
                      index_names[13]: 71704845530629737,
                      index_names[14]: 43754960038275285,
                      index_names[15]: 10523825119011581,
                      index_names[16]: 10523825119011581,
                      index_names[17]: 10523825119011581,
                      index_names[18]: 46342955726788357,
                      index_names[19]: 46342955726788357,
                      index_names[20]: 46342955726788357,
                      index_names[21]: 46342955726788357,
                      index_names[22]: 46342955726788357,
                      index_names[23]: 46342955726788357,
                      }
        return str(webid_dict[search_txt]) + "index"
    else:
        try:
            res_search = requests.get(settings.url_search.format(search_txt), headers=headers).json()[
                'instrumentSearch']

            if len(res_search) > 0:
                stock_id = res_search[0]['insCode']
            else:
                return None
        except:
            print("Connection Error!")
        return stock_id
