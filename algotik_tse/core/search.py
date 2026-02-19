import requests
from algotik_tse.settings import settings
from algotik_tse.http_client import safe_get


def search_stock(search_txt="شتران"):
    index_names = settings.index_names
    industry_index = settings.industry_index
    stock_id = ""
    if search_txt in index_names:
        webid_dict = {
            index_names[0]: 32097828799138957,
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
    elif search_txt in industry_index:
        industry_dict = {
            industry_index[0]: 32453344048876642,
            industry_index[1]: 32453344048876642,
            industry_index[2]: 70077233737515808,
            industry_index[3]: 70077233737515808,
            industry_index[4]: 20213770409093165,
            industry_index[5]: 20213770409093165,
            industry_index[6]: 33626672012415176,
            industry_index[7]: 33626672012415176,
            industry_index[8]: 24733701189547084,
            industry_index[9]: 24733701189547084,
            industry_index[10]: 25163959460949732,
            industry_index[11]: 25163959460949732,
            industry_index[12]: 59288237226302898,
            industry_index[13]: 59288237226302898,
            industry_index[14]: 57616105980228781,
            industry_index[15]: 57616105980228781,
            industry_index[16]: 25766336681098389,
            industry_index[17]: 25766336681098389,
            industry_index[18]: 62691002126902464,
            industry_index[19]: 62691002126902464,
            industry_index[20]: 69306841376553334,
            industry_index[21]: 69306841376553334,
        }
        return str(industry_dict[search_txt]) + "industry"
    else:
        try:
            res_search = safe_get(settings.url_search.format(search_txt)).json()[
                "instrumentSearch"
            ]

            if len(res_search) > 0:
                stock_id = res_search[0]["insCode"]
            else:
                return None
        except requests.exceptions.RequestException:
            print("Connection Error!")
            return None
        except (ValueError, KeyError, IndexError, TypeError) as e:
            print("Search Error: {}".format(e))
            return None
        return stock_id
