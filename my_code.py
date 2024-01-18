from algotik_tse import stockdetail, stock_information
from algotik_tse import stocklist
from algotik_tse import stock, stock_RL, stock_RI, stock_capital_increase
from algotik_tse import shareholders

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
# df = stock_RL(stock="مدیریت", start="1400-01-01", end="1401-01-01")
# df = stock_RL(stock="مدیریت", values=100, start="1401-01-01", end="1402-01-01")

# df = stock(stock='شتران', output_type='complete', auto_adjust=False, return_type='simple', date_format='gregorian')
# df = shareholders(stock='داتام', date='14021006', shh_id=True)

# df = stock_capital_increase(stock='شپنا')

df = stock_information(stock='خودرو')
print(df.to_string())

# df.to_excel('test.xlsx')
