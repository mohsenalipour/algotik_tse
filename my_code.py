from algotik_tse import stockdetail
from algotik_tse import stocklist
from algotik_tse import stock, stock_RL

# stock -> shakhes
# df = stock(stock="شاخص کل", values=100)
# df = stock(stock="شاخص کل", start="1401-01-01")
# df = stock(stock="شاخص کل", end="1400-01-01")
# df = stock(stock="شاخص کل", start="1400-01-01", end="1401-01-01")

# stock -> sahm
# df = stock(stock="مدیریت", values=100)
# df = stock(stock="مدیریت", start="1401-01-01")
# df = stock(stock="مدیریت", end="1401-01-01")
# df = stock(stock="مدیریت", start="1400-01-01", end="1401-01-01")

# stock_RL -> sahm
# df = stock_RL(stock="مدیریت", values=100)
# df = stock_RL(stock="مدیریت", start="1401-01-01")
# df = stock_RL(stock="مدیریت", end="1401-01-01")
df = stock_RL(stock="مدیریت", start="1400-01-01", end="1401-01-01")
# df = stock_RL(stock="مدیریت", values=100, start="1401-01-01", end="1402-01-01")


print(df.to_string())
