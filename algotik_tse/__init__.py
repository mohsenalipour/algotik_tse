"""
version 0.3.3
Main module code by @Python4finance
New version code by Mohsen Alipour alipour@algotik.ir
last Edit: 2024-01-05
* Base: old.tsetmc.com

Sample:
import algotik_tse as att

att.stockdetail(stock='شبندر')
you get all detail information of the stock!

att.stocklist(bourse=True, farabourse=True, payeh=True, haghe_taqadom=False, output="dataframe"):
show all stock data in dataframe or list format (you can choose bourse, farabourse, payeh and haghe_taqadom)

att.stock(stock="شبندر", start=None, end=None, values=0, tse_format=False, auto_adjust=True, output_type="standard",
 progress=True, date_format="jalali", save_to_file=False, multi_stock_drop=True, adjust_volume=False)
you can get historical price data, in customized way with set the function parameters!

att.stock_RI(stock="شبندر", start=None, end=None, values=0, tse_format=False, auto_adjust=True, output_type="standard",
 progress=True, date_format="jalali", save_to_file=False, multi_stock_drop=True, adjust_volume=False)
you can get historical retail/institutional data, in customized way with set the function parameters!

att.shareholders(stock="شبندر", date="14020812", shh_id=False)
you can get last and historical shareholders data for stock, in customized way with set the function parameters!
"""

__author__ = """Mohsen Alipour"""
__email__ = 'alipour@algotik.ir'
__version__ = '0.3.3'

from algotik_tse.core.stock_detail import stockdetail
from algotik_tse.core.stock_list import stocklist
from algotik_tse.core.stock import stock, stock_RI, stock_RL
from algotik_tse.core.shareholders import shareholders
