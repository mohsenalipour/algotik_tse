import pandas as pd


def tgju_convertor(json_input):
    price = {
        'J-Date': [],
        'Date': [],
        'Open': [],
        'High': [],
        'Low': [],
        'Close': [],
    }
    for date_price in json_input:
        price['J-Date'].append(date_price[7].replace("/", "-"))
        price['Date'].append(date_price[6].replace("/", "-"))
        price['Open'].append(float(date_price[0].replace(",", "")))
        price['High'].append(float(date_price[2].replace(",", "")))
        price['Low'].append(float(date_price[1].replace(",", "")))
        price['Close'].append(float(date_price[3].replace(",", "")))

    df = pd.DataFrame(price)
    df = df[::-1]
    df.dropna(inplace=True)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True, drop=False)
    return df
