from io import StringIO
import pandas as pd
from persiantools import characters
from algotik_tse.settings import settings
from algotik_tse.core.search import search_stock
from algotik_tse.exceptions import UnsupportedDataSourceError
from algotik_tse.http_client import safe_get


def stockdetail(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
    """
    Get all symbol detail
    :param symbol: symbol name in Persian
                  Default value is 'شتران'.

    :return: pandas dataframe
    """
    # Backward compatibility: accept deprecated 'stock' keyword
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if not symbol and ins_code is not None:
        symbol = str(ins_code)
    web_id = search_stock(search_txt=symbol, ins_code=ins_code, asset_type=asset_type)
    if web_id is not None and len(web_id) != 0:
        if web_id[-5:] == "index":
            print("This is an index, no information found!")
            return None
        else:
            detail = safe_get(settings.url_detail.format(web_id))
            if detail.status_code == 200:
                df = pd.read_html(StringIO(detail.text))[0]
                df.rename(columns={0: "key", 1: "value"}, inplace=True)
                df.set_index("key", drop=True, inplace=True)
                df.loc["id"] = str(web_id)
                return df
            else:
                print("Connection Error!!!")
                return None
    else:
        print("Stock Not Found, Please try again ...")
        return None


def __flatten_dict(dd, separator="_", prefix=""):
    return (
        {
            prefix + separator + k if prefix else k: v
            for kk, vv in dd.items()
            for k, v in __flatten_dict(vv, separator, kk).items()
        }
        if isinstance(dd, dict)
        else {prefix: dd}
    )


def stock_information(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
    """
    Get all stock information
    :param symbol: symbol name in Persian
                  Default value is 'شتران'.

    :return: pandas dataframe
    """
    # Backward compatibility: accept deprecated 'stock' keyword
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if not symbol and ins_code is not None:
        symbol = str(ins_code)
    web_id = search_stock(search_txt=symbol, ins_code=ins_code, asset_type=asset_type)
    if web_id is not None and len(web_id) != 0:
        if web_id[-5:] == "index":
            print("This is an index, no information found!")
            return None
        else:
            detail = safe_get(settings.url_instrument_information.format(web_id))
            if detail.status_code == 200:
                raw = __flatten_dict(detail.json()["instrumentInfo"])
                df = pd.DataFrame([raw]).T
                df.reset_index(inplace=True)
                df.rename(columns={"index": "key", 0: "value"}, inplace=True)
                df.set_index("key", inplace=True)
                return df
            else:
                print("Connection Error!!!")
                return None
    else:
        print("Stock Not Found, Please try again ...")
        return None


def stock_statistics(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
    """
    Get all stock statistics
    :param symbol: symbol name in Persian
                  Default value is 'شتران'.

    :return: pandas dataframe
    """
    # Backward compatibility: accept deprecated 'stock' keyword
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if not symbol and ins_code is not None:
        symbol = str(ins_code)
    web_id = search_stock(search_txt=symbol, ins_code=ins_code, asset_type=asset_type)
    if web_id is not None and len(web_id) != 0:
        if web_id[-5:] == "index":
            print("This is an index, no statistics found!")
            return None
        else:
            detail = safe_get(settings.url_instrument_statistics.format(web_id))
            if detail.status_code == 200:
                js = detail.json()["instrumentStatistic"]
                statistics_dict = {
                    characters.ar_to_fa(x["dataTypeDesc"]): (
                        float(x["dataValue"])
                        if "." in x["dataValue"]
                        else int(x["dataValue"])
                    )
                    for x in js
                }
                raw = __flatten_dict(statistics_dict)
                df = pd.DataFrame([raw]).T
                df.reset_index(inplace=True)
                df.rename(columns={"index": "key", 0: "value"}, inplace=True)
                df.set_index("key", inplace=True)
                return df
            else:
                print("Connection Error!!!")
                return None
    else:
        print("Stock Not Found, Please try again ...")
        return None


def stock_introduction(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
    """Legacy introduction API retained without crossing into Codal.

    ``algotik-tse`` is a TSETMC market-data package.  Company-publisher
    profiles are a Codal data product, even when proxied under a TSETMC host,
    and therefore sit outside this package's source boundary.  The legacy
    signature remains importable so existing applications fail explicitly
    instead of making a hidden cross-provider request.
    """
    raise UnsupportedDataSourceError(
        "get_introduction/stock_introduction requires Codal data, which is "
        "outside algotik-tse's TSETMC market-data source boundary"
    )
