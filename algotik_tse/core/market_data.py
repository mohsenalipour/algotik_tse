import requests
import pandas as pd
from algotik_tse.settings import Settings

settings = Settings()


def market_data():
    response = requests.get(url=settings.url_market_data_live, headers=settings.headers, verify=False)
    if response.status_code == 200:
        txt = response.text
        txt_at = txt.split('@')
        txt_list = txt_at[2].split(";")

        data = [x.split(",") for x in txt_list]

        df = pd.DataFrame(data)

        df = df.loc[:, ['']]

        df.rename(columns={
            '0': 'instrument_id',
            '1': 'instrument_isin',
            '2': 'symbol',
            '3': 'name',
            '4': 'last_trade_hour',
            '5': 'Open',
            '6': 'Final',
            '7': 'Close',
            '8': 'No.',
            '9': 'Volume',
            '10': 'Value',
            '11': 'Low',
            '12': 'High',
            '13': 'Yesterday-Final',
            '14': 'EPS',
            '15': 'Base_volume',
            # '16': '??',
            '17': 'flow',
            '18': 'sector_value',
            '19': 'Threshold_max',
            '20': 'Threshold_min',
            '21': 'number_of_shares',
            '22': 'yVal',
            '23': 'nav',
            '24': 'open_interest'
        }, inplace=True)


    else:
        pass
