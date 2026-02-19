import requests
import pandas as pd
from algotik_tse.core.search import search_stock
from algotik_tse.settings import settings
from algotik_tse.core.helper import date_fix
from algotik_tse.http_client import safe_get


def shareholders(symbol="", date=None, include_id=False, **kwargs):
    """
    Get all shareholders of an instrument (company)
    :param symbol: symbol name in Persian
                  Default value is 'شتران'.
    :param date: date for get shareholders in specific date, if None the function return last shareholders
                  Default value is None
    :param include_id: if is True, shareholder id will be shown in df and if is False, shareholder not show
                  Default value is False

    :return: pandas dataframe
    """
    # Backward compatibility: accept deprecated keyword names
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if "shh_id" in kwargs:
        include_id = kwargs.pop("shh_id")
    web_id = search_stock(search_txt=symbol)
    if web_id is not None and len(web_id) != 0:
        try:
            if date is None:
                share_holder_id_name = "shareHolderShareID"
                _shareholders_base_url = settings.url_last_share_holders
                response = safe_get(_shareholders_base_url.format(web_id))
            else:
                share_holder_id_name = "shareHolderID"
                new_start, new_end = date_fix(start=date)
                new_start = new_start.replace("-", "")
                _shareholders_base_url = settings.url_share_holders_history
                url = _shareholders_base_url.format(web_id, new_start)
                response = safe_get(url)
            if response.status_code == 200:
                share_holders = (
                    response.json()["shareHolder"]
                    if date is None
                    else response.json()["shareShareholder"]
                )
                share_holders_df = pd.DataFrame(share_holders)
                share_holders_columns = [
                    "shareHolderName",
                    "numberOfShares",
                    "perOfShares",
                    "change",
                    "changeAmount",
                    "dEven",
                ]

                share_holders_columns.append(share_holder_id_name)
                share_holders_df = share_holders_df.loc[:, share_holders_columns]
                share_holders_df.rename(
                    columns={
                        "shareHolderName": "share_holder_name",
                        "numberOfShares": "number_of_shares",
                        "perOfShares": "percentage_of_shares",
                        "change": "change_state",
                        "changeAmount": "change_amount",
                        "dEven": "date",
                        share_holder_id_name: "share_holder_id",
                    },
                    inplace=True,
                )

                if date is not None:
                    share_holders_df["first_row"] = share_holders_df.groupby(
                        "share_holder_id"
                    )["number_of_shares"].transform("first")
                    share_holders_df["last_row"] = share_holders_df.groupby(
                        "share_holder_id"
                    )["number_of_shares"].transform("last")
                    share_holders_df["change_amount"] = (
                        share_holders_df["first_row"] - share_holders_df["last_row"]
                    )
                    share_holders_df = share_holders_df.drop(
                        ["first_row", "last_row"], axis=1
                    )
                    share_holders_df = share_holders_df.loc[
                        share_holders_df["date"] == share_holders_df["date"].max(), :
                    ]
                else:
                    share_holders_df["date"] = settings.today.replace("-", "")
                if not include_id:
                    share_holders_df.drop(columns=["share_holder_id"], inplace=True)
                return share_holders_df
        except requests.exceptions.RequestException:
            print("Connection Error!!!")
            return None
        except Exception as e:
            print("Error processing shareholders: {}".format(e))
            return None
    else:
        print("Stock Not Found, Please try again ...")
        return None
