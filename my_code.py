from algotik_tse import stockdetail
from algotik_tse import stocklist
from algotik_tse import stock, stock_RL


df = stock(start="1401-01-01")
print(df.to_string())
