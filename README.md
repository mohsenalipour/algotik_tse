# AlgoTik TSE

[![PyPI](https://img.shields.io/pypi/v/algotik-tse.svg)](https://pypi.org/project/algotik-tse/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/algotik-tse.svg)](https://pypi.org/project/algotik-tse/)
[![downloads](https://static.pepy.tech/personalized-badge/algotik-tse?period=total&units=international_system&left_color=black&right_color=green&left_text=Downloads)](https://pepy.tech/project/algotik-tse)
[![PyPI - License](https://img.shields.io/pypi/l/algotik-tse.svg)](https://pypi.org/project/algotik-tse/)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mohsenalipour/algotik_tse/master.svg)](https://results.pre-commit.ci/latest/github/mohsenalipour/algotik_tse/master)

**A comprehensive Python library for fetching market data from the Tehran Stock Exchange (TSETMC) and currency/coin prices (TGJU).** Supports stocks, options, ETFs, bonds, and treasury bills.

All outputs are returned as **Pandas DataFrames** with Jalali (Shamsi) date support.

<div dir="rtl" align="right">

### 🇮🇷 فارسی

این کتابخانه جهت دریافت اطلاعات بازار بورس تهران و قیمت ارز و سکه توسعه یافته است. خروجی تمامی توابع با فرمت **دیتافریم پانداز** و با پشتیبانی از **تاریخ شمسی** ارائه می‌شود.

#### ویژگی‌ها:
- دسترسی به داده‌ها با استفاده از **نماد فارسی** سهم
- **تعدیل قیمت** خودکار (افزایش سرمایه + سود نقدی)
- تشخیص هوشمند **جابجایی نماد** بین بازارها
- دسترسی به **همه شاخص‌های بازار** (صنایع و کل) — پشتیبانی از **۴۵ شاخص صنعت**
- لیست **شاخص‌های بورس** و شرکت‌های هر شاخص صنعت
- قابلیت دانلود **دسته‌جمعی** سابقه قیمت
- دریافت اطلاعات **حقیقی‌/حقوقی**
- دریافت لیست **سهامداران عمده**
- دریافت سابقه **افزایش سرمایه**
- دریافت قیمت **ارز و سکه** (دلار، یورو، سکه امامی و ...)
- دریافت **اطلاعات لحظه‌ای کل بازار** در یک درخواست (Market Watch)
- دریافت **داده‌های اینترادی** (کندل و تیک دقیقه‌ای، بازه‌ها: ۱ دقیقه تا ۱۲ ساعت)
- لیست **اختیارمعامله‌ها** با تجزیه خودکار (نوع، دارایی پایه، قیمت اعمال، سررسید)
- دریافت **زنجیره اختیارمعامله** با Open Interest
- لیست **صندوق‌های ETF** با محاسبه تخفیف/حباب NAV
- لیست **اوراق مرابحه و خزانه** با استخراج تاریخ سررسید
- **نام‌گذاری استاندارد** (`get_*`) در کنار نام‌های اصلی
- پشتیبانی از تاریخ **شمسی، میلادی و نام روز هفته**
- تنظیمات قابل پیکربندی: SSL، Timeout، Rate Limiting، Retry
- مدیریت خودکار خطا و Rate Limiting برای جلوگیری از بلاک شدن

##### 🌐 وبسایت: [algotik.com](https://algotik.com) | 📱 تلگرام: [t.me/algotik](https://t.me/algotik)

</div>

---

## Table of Contents

- [AlgoTik TSE](#algotik-tse)
    - [🇮🇷 فارسی](#-فارسی)
      - [ویژگی‌ها:](#ویژگیها)
        - [🌐 وبسایت: algotik.com | 📱 تلگرام: t.me/algotik](#-وبسایت-algotikcom---تلگرام-tmealgotik)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
  - [Quick Start](#quick-start)
      - [📖 شروع سریع — توضیحات فارسی](#-شروع-سریع--توضیحات-فارسی)
  - [API Reference](#api-reference)
    - [`get_history()`](#get_history)
      - [📖 توضیحات فارسی — `get_history()`](#-توضیحات-فارسی--get_history)
      - [Standard output (default)](#standard-output-default)
      - [Full output](#full-output)
      - [Gregorian dates](#gregorian-dates)
      - [Auto-adjust off](#auto-adjust-off)
      - [TSE format](#tse-format)
      - [Return calculation](#return-calculation)
      - [Multi-stock](#multi-stock)
      - [Index support](#index-support)
    - [`get_client_type()`](#get_client_type)
      - [📖 توضیحات فارسی — `get_client_type()`](#-توضیحات-فارسی--get_client_type)
      - [Standard output (12 columns)](#standard-output-12-columns)
      - [Full output (20 columns)](#full-output-20-columns)
      - [Date range \& Gregorian](#date-range--gregorian)
    - [`get_capital_increase()`](#get_capital_increase)
      - [📖 توضیحات فارسی — `get_capital_increase()`](#-توضیحات-فارسی--get_capital_increase)
    - [`get_detail()`](#get_detail)
      - [📖 توضیحات فارسی — `get_detail()`](#-توضیحات-فارسی--get_detail)
    - [`get_info()`](#get_info)
      - [📖 توضیحات فارسی — `get_info()`](#-توضیحات-فارسی--get_info)
    - [`get_stats()`](#get_stats)
      - [📖 توضیحات فارسی — `get_stats()`](#-توضیحات-فارسی--get_stats)
    - [`get_introduction()`](#get_introduction)
      - [📖 توضیحات فارسی — `get_introduction()`](#-توضیحات-فارسی--get_introduction)
    - [`get_shareholders()`](#get_shareholders)
      - [📖 توضیحات فارسی — `get_shareholders()`](#-توضیحات-فارسی--get_shareholders)
      - [Current shareholders](#current-shareholders)
      - [Historical shareholders](#historical-shareholders)
      - [With shareholder IDs](#with-shareholder-ids)
    - [`get_symbols()`](#get_symbols)
      - [📖 توضیحات فارسی — `get_symbols()`](#-توضیحات-فارسی--get_symbols)
      - [Default: all regular stocks](#default-all-regular-stocks)
      - [Filter by market](#filter-by-market)
      - [Filter Payeh by color (تابلو)](#filter-payeh-by-color-تابلو)
      - [Include additional asset types](#include-additional-asset-types)
      - [Output as list](#output-as-list)
    - [`get_currency()`](#get_currency)
      - [📖 توضیحات فارسی — `get_currency()`](#-توضیحات-فارسی--get_currency)
      - [Supported names](#supported-names)
      - [Standard output](#standard-output)
      - [Persian names work too](#persian-names-work-too)
      - [With Gregorian dates](#with-gregorian-dates)
      - [With return calculation](#with-return-calculation)
      - [Multiple currencies](#multiple-currencies)
      - [Date range](#date-range)
    - [`get_intraday()`](#get_intraday)
      - [📖 توضیحات فارسی — `get_intraday()`](#-توضیحات-فارسی--get_intraday)
      - [Today's candles (no start/end)](#todays-candles-no-startend)
      - [4-hour \& 12-hour candles (new intervals)](#4-hour--12-hour-candles-new-intervals)
      - [Today's raw ticks](#todays-raw-ticks)
      - [Historical candles (with start/end)](#historical-candles-with-startend)
      - [Historical raw snapshots](#historical-raw-snapshots)
    - [`get_market_snapshot()`](#get_market_snapshot)
      - [📖 توضیحات فارسی — `get_market_snapshot()`](#-توضیحات-فارسی--get_market_snapshot)
      - [Full output](#full-output-1)
      - [Stocks DataFrame columns (25 columns)](#stocks-dataframe-columns-25-columns)
      - [Filter by instrument type](#filter-by-instrument-type)
      - [Practical examples](#practical-examples)
    - [`get_market_client_type()`](#get_market_client_type)
      - [📖 توضیحات فارسی — `get_market_client_type()`](#-توضیحات-فارسی--get_market_client_type)
      - [Join with get\_market\_snapshot](#join-with-get_market_snapshot)
    - [`list_options()`](#list_options)
      - [📖 توضیحات فارسی — `list_options()`](#-توضیحات-فارسی--list_options)
    - [`get_options_chain()`](#get_options_chain)
      - [📖 توضیحات فارسی — `get_options_chain()`](#-توضیحات-فارسی--get_options_chain)
    - [`list_etfs()`](#list_etfs)
      - [📖 توضیحات فارسی — `list_etfs()`](#-توضیحات-فارسی--list_etfs)
    - [`list_bonds()`](#list_bonds)
      - [📖 توضیحات فارسی — `list_bonds()`](#-توضیحات-فارسی--list_bonds)
      - [Bonds expiring soon](#bonds-expiring-soon)
    - [`list_funds()`](#list_funds)
      - [📖 توضیحات فارسی — `list_funds()`](#-توضیحات-فارسی--list_funds)
      - [All funds](#all-funds)
      - [Filter by fund type](#filter-by-fund-type)
      - [Top performers](#top-performers)
      - [Portfolio analysis](#portfolio-analysis)
      - [Compare NAVs](#compare-navs)
  - [Legacy Aliases](#legacy-aliases)
      - [📖 توضیحات فارسی — نام‌های قدیمی](#-توضیحات-فارسی--نامهای-قدیمی)
    - [Legacy Parameter Names](#legacy-parameter-names)
  - [Configuration](#configuration)
      - [📖 توضیحات فارسی — تنظیمات](#-توضیحات-فارسی--تنظیمات)
  - [Examples](#examples)
    - [Market Screening](#market-screening)
    - [ETF Discount/Premium Analysis](#etf-discountpremium-analysis)
    - [Currency \& Gold Prices](#currency--gold-prices)
    - [Options Overview](#options-overview)
    - [Fund Comparison](#fund-comparison)
    - [Bond Maturity Analysis](#bond-maturity-analysis)
    - [Institutional Money Flow](#institutional-money-flow)
    - [All Asset Types Overview](#all-asset-types-overview)
    - [Intraday Candle Analysis](#intraday-candle-analysis)
    - [Stock Detail \& Shareholders](#stock-detail--shareholders)
  - [Data Sources](#data-sources)
  - [Contributing](#contributing)
  - [License](#license)
  - [Credits](#credits)

---

## Installation

```bash
pip install algotik-tse
```

**Upgrade to latest version:**

```bash
pip install algotik-tse --upgrade
```

**Requirements:** Python 3.8+ &nbsp;|&nbsp; pandas &nbsp;|&nbsp; requests &nbsp;|&nbsp; persiantools &nbsp;|&nbsp; lxml &nbsp;|&nbsp; numpy &nbsp;|&nbsp; openpyxl

---

## Quick Start

<div dir="rtl" align="right">

#### 📖 شروع سریع — توضیحات فارسی

| کد | توضیح |
|---|---|
| `att.get_history('شتران')` | دریافت سابقه قیمت تعدیل شده سهم |
| `att.get_client_type('شتران')` | دریافت اطلاعات حقیقی/حقوقی |
| `att.get_introduction('شتران')` | معرفی/شناسنامه شرکت (مدیرعامل، موضوع فعالیت، سرمایه و ...) |
| `att.get_symbols()` | لیست تمام نمادهای بازار (سهام، اوراق، اختیار، صندوق و ...) |
| `att.get_currency('dollar')` | قیمت دلار آمریکا |
| `att.get_intraday('شتران')` | کندل‌های ۱ دقیقه‌ای امروز |
| `att.get_market_snapshot()` | اطلاعات لحظه‌ای کل بازار |
| `att.list_options()` | لیست تمام اختیارمعامله‌های فعال |
| `att.get_options_chain('اهرم')` | زنجیره اختیارمعامله با Open Interest |
| `att.list_etfs()` | لیست صندوق‌های ETF با تخفیف/حباب NAV |
| `att.list_bonds()` | لیست اوراق بدهی (مرابحه، اجاره، خزانه) با سررسید |
| `att.list_funds()` | لیست صندوق‌های سرمایه‌گذاری با NAV، بازدهی و ترکیب پرتفوی |
| `att.list_indices()` | لیست همه شاخص‌های بازار (صنایع و کل) با مقادیر لحظه‌ای |
| `att.get_index_companies('فلزات اساسی')` | لیست شرکت‌های عضو یک شاخص صنعت |

</div>

```python
import algotik_tse as att

# Get adjusted stock price history
df = att.get_history('شتران', start='1404-06-01', end='1404-08-01')
print(df.head())
```
```
            Open  High   Low  Close     Volume
J-Date
1404-06-01  2008  2028  1969   2020   58693215
1404-06-03  1995  2011  1932   1932   56282643
1404-06-04  1888  1944  1888   1912  128242492
1404-06-05  1889  1965  1885   1897   80085551
1404-06-08  1875  1898  1875   1897  161293403
```

```python
# Get retail/institutional data
df_ri = att.get_client_type('شتران', limit=100)

# List all stocks in the market
all_stocks = att.get_symbols()

# Get US Dollar price history
usd = att.get_currency('dollar', limit=365)

# Intraday 1-minute candles (today's data)
intraday = att.get_intraday('شتران', interval='1min')

# Historical intraday (multi-day)
hist = att.get_intraday('شتران', interval='5min',
                        start='1404-11-01', end='1404-11-06')

# Live market data for ALL instruments in one call
data = att.get_market_snapshot()
print(data['stocks'].shape)                       # DataFrame of all instruments
print(data['market_time'])                        # '04/11/29 15:04:05'
print(data['index_value'])                        # 3806743.94

# Options chain for a specific underlying
chain = att.get_options_chain('اهرم')
print(chain['calls'].head())                      # Calls DataFrame
print(chain['underlying_price'])                  # Current underlying price

# List all ETFs with NAV discount
etfs = att.list_etfs()
print(etfs[['Symbol', 'Close', 'NAV', 'NAV_Discount']].head())

# List all bonds with maturity info
bonds = att.list_bonds()
print(bonds[['Symbol', 'Ticker', 'BondType', 'MaturityJalali', 'DaysToMaturity']].head())

# Investment funds — NAV, returns, portfolio composition
funds = att.list_funds()
equity_funds = att.list_funds(fund_type='equity')

# All market indices (45 industry sectors + general indices)
indices = att.list_indices()

# Companies in an industry index
companies = att.get_index_companies('فلزات اساسی')
companies = att.get_index_companies('بانک')
```

---

## API Reference

### `get_history()`

Get historical price data for one or more symbols. Prices are **auto-adjusted** for splits & dividends by default.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_history()`

تابع `get_history()` برای دریافت **سابقه قیمت سهام** از سایت TSETMC استفاده می‌شود. قیمت‌ها به‌صورت پیش‌فرض **تعدیل‌شده** (برای افزایش سرمایه و سود نقدی) ارائه می‌شوند.

**پارامترها:**

| پارامتر | نوع | پیش‌فرض | توضیح |
|---|---|---|---|
| `symbol` | `str` یا `list` | — | نماد فارسی سهم (مثلاً `'شتران'`) یا لیست نمادها |
| `start` | `str` | `None` | تاریخ شروع شمسی (مثلاً `'1402-01-01'`) |
| `end` | `str` | `None` | تاریخ پایان شمسی |
| `limit` | `int` | `0` | تعداد آخرین روزهای معاملاتی (`0` = کل تاریخچه) |
| `auto_adjust` | `bool` | `True` | تعدیل خودکار قیمت (افزایش سرمایه + سود نقدی) |
| `output_type` | `str` | `'standard'` | `'standard'` (فقط OHLCV) یا `'full'` (همه ستون‌ها) |
| `date_format` | `str` | `'jalali'` | `'jalali'` (شمسی)، `'gregorian'` (میلادی)، یا `'both'` (هر دو) |
| `raw` | `bool` | `False` | فرمت TSETMC برای وارد کردن در نرم‌افزارهای معاملاتی |
| `return_type` | `str/list` | `None` | محاسبه بازده: `'simple'`، `'log'`، `'both'`، یا `['simple','Close',5]` |
| `save_to_file` | `bool` | `False` | ذخیره نتیجه در فایل CSV |
| `adjust_volume` | `bool` | `False` | تعدیل حجم معاملات برای افزایش سرمایه |
| `dropna` | `bool` | `True` | حذف ستون‌های اضافی در حالت چند نمادی |
| `ascending` | `bool` | `True` | مرتب‌سازی صعودی (`True`) یا نزولی (`False`) بر اساس تاریخ |
| `save_path` | `str` | `None` | مسیر فایل CSV برای ذخیره (مثلاً `'output.csv'`) |
| `progress` | `bool` | `True` | نمایش نوار پیشرفت |

**خروجی‌های مختلف:**

- **حالت عادی (`standard`):** ۵ ستون — `Open` (باز)، `High` (بیشترین)، `Low` (کمترین)، `Close` (پایانی)، `Volume` (حجم) — همه `int64`
- **حالت کامل (`full`):** ۱۰ ستون — علاوه بر موارد بالا: `Final` (قیمت پایانی میانگین وزنی)، `No.` (تعداد معاملات)، `Value` (ارزش معاملات ریالی)، `Weekday_fa` (نام روز هفته فارسی)، `Ticker` (نماد)
- **بدون تعدیل (`auto_adjust=False`):** ستون `Adj Close` (قیمت تعدیل‌شده) اضافه می‌شود و قیمت‌های OHLC خام (بدون تعدیل) هستند
- **فرمت TSE:** نام ستون‌ها مطابق TSETMC مثل `<TICKER>`، `<HIGH>`، `<CLOSE>` و...
- **تاریخ میلادی:** ایندکس `Date` از نوع `datetime64` به‌جای رشته شمسی
- **بازده:** ستون `returns` اضافه می‌شود — ساده، لگاریتمی، یا هر دو
- **چند نمادی:** ستون‌ها `MultiIndex` می‌شوند: `(Column, Symbol)`

**نکات مهم:**
- برای دریافت **شاخص کل** یا **شاخص‌های صنایع**، نام شاخص را به‌عنوان نماد وارد کنید (مثلاً `'شاخص کل'`، `'شاخص صنعت فلزات اساسی'`)
- با `save_to_file=True` خروجی به‌صورت فایل CSV ذخیره می‌شود
- در حالت چند نمادی، فقط روزهای مشترک معاملاتی بین نمادها نمایش داده می‌شود

</div>

```python
att.get_history(
    symbol='شتران',            # str or list — symbol name(s) in Persian
    start=None,                # str — start date in Jalali 'YYYY-MM-DD' (e.g. '1402-01-01')
    end=None,                  # str — end date in Jalali 'YYYY-MM-DD'
    limit=0,                   # int — number of last trading days (0 = all history)
    raw=False,                 # bool — use TSETMC column names
    auto_adjust=True,          # bool — adjust for splits & dividends
    output_type='standard',    # str — 'standard' (OHLCV) or 'full' (all columns)
    date_format='jalali',      # str — 'jalali', 'gregorian', or 'both'
    progress=True,             # bool — show download progress bar
    save_to_file=False,        # bool — save result to CSV file
    dropna=True,               # bool — drop extra columns in multi-stock mode
    adjust_volume=False,       # bool — adjust volume for capital increases
    return_type=None,          # str/list — 'simple', 'log', 'both', or ['simple','Close',5]
    ascending=True,            # bool — sort by date ascending (True) or descending (False)
    save_path=None,            # str — file path to save CSV (e.g. 'output.csv')
)
```

#### Standard output (default)

```python
df = att.get_history('شتران', limit=10)
```
```
            Open  High   Low  Close      Volume
J-Date
1404-10-14  3960  3996  3810   3996  1272346113
1404-10-15  4098  4098  4098   4098   450168956
1404-10-16  4220  4220  4220   4220   326395132
1404-10-17  4346  4346  4346   4346   892210289
1404-10-20  4216  4476  4216   4218  1862610980
```
- **Index:** `J-Date` (Jalali string, e.g. `1404-10-14`)
- **Columns:** `Open`, `High`, `Low`, `Close`, `Volume` — all `int64`

#### Full output
```python
df = att.get_history('شتران', limit=5, output_type='full')
```
```
            Open  High   Low  Close  Final     Volume    No.          Value Weekday_fa Ticker
J-Date
1404-11-25  4400  4475  4218   4218   4308  238550890   4846  1027754207785       شنبه  شتران
1404-11-26  4179  4179  4179   4179   4179   39453982    748   164878190778     یکشنبه  شتران
1404-11-27  4054  4109  4054   4064   4056  430020598   7394  1744313323314     دوشنبه  شتران
1404-11-28  4010  4100  3958   4066   4037  164209800   4199   662877646216    سه شنبه  شتران
```

| Column | Description |
|---|---|
| `Open, High, Low, Close` | Adjusted OHLC prices (int) |
| `Final` | Weighted average closing price — قیمت پایانی |
| `Volume` | Trade volume |
| `No.` | Number of trades |
| `Value` | Total trade value (Rials) |
| `Weekday_fa` | Day of week in Persian (شنبه, یکشنبه, …) |
| `Ticker` | Symbol name |

#### Gregorian dates

```python
df = att.get_history('شتران', limit=5, date_format='gregorian')
```
```
            Open  High   Low  Close     Volume
Date
2026-02-14  4400  4475  4218   4218  238550890
2026-02-15  4179  4179  4179   4179   39453982
2026-02-16  4054  4109  4054   4064  430020598
2026-02-17  4010  4100  3958   4066  164209800
```
- **Index:** `Date` (`datetime64`)
- Use `date_format='both'` to get both Jalali & Gregorian columns.
- Full mode with Gregorian shows `Weekday` (Monday, Tuesday, …) instead of `Weekday_fa`.

#### Auto-adjust off

```python
df = att.get_history('شتران', limit=5, auto_adjust=False)
```
```
              Open    High     Low   Close  Adj Close     Volume
J-Date
1404-11-25  4400.0  4475.0  4218.0  4218.0       4218  238550890
1404-11-26  4179.0  4179.0  4179.0  4179.0       4179   39453982
1404-11-27  4054.0  4109.0  4054.0  4064.0       4064  430020598
1404-11-28  4010.0  4100.0  3958.0  4066.0       4066  164209800
```
- Adds `Adj Close` column. OHLC are raw (unadjusted) and `float64`.

#### TSE format

```python
df = att.get_history('شتران', limit=3, raw=True)
```
```
                     <TICKER>  <FIRST>  <HIGH>   <LOW>  <CLOSE>        <VALUE>      <VOL>  <OPENINT> <PER>  <OPEN>  <LAST>
<DTYYYYMMDD>
2026-02-15    Palayesh.Tehran   4179.0  4179.0  4179.0   4179.0   164878190778   39453982        748     D  4308.0  4179.0
2026-02-16    Palayesh.Tehran   4054.0  4109.0  4054.0   4056.0  1744313323314  430020598       7394     D  4179.0  4064.0
2026-02-17    Palayesh.Tehran   4010.0  4100.0  3958.0   4037.0   662877646216  164209800       4199     D  4056.0  4066.0
```
- TSETMC-compatible column names for import into trading software.

#### Return calculation

```python
# Simple 1-day returns
df = att.get_history('شتران', limit=10, return_type='simple')
# Adds 'returns' column:  (Close[t] - Close[t-1]) / Close[t-1]

# Log returns
df = att.get_history('شتران', limit=10, return_type='log')
# Adds 'returns' column:  ln(Close[t] / Close[t-1])

# Both simple & log returns
df = att.get_history('شتران', limit=10, return_type='both')
# Adds 'simple_returns' and 'log_returns' columns

# Custom: simple 5-day returns on Close
df = att.get_history('شتران', limit=15, return_type=['simple', 'Close', 5])
```
```
            Open  High   Low  Close      Volume   returns
J-Date
1404-11-06  4490  4490  4490   4490    16195770       NaN
1404-11-07  4356  4356  4356   4356   276970553 -0.029844
1404-11-08  4226  4356  4226   4259  1731947316 -0.022268
1404-11-11  4240  4330  4110   4110   379107775 -0.034985
1404-11-12  4110  4278  4087   4278   700763528  0.040876
```

#### Multi-stock

```python
df = att.get_history(['شتران', 'فملی'], limit=5)
```
```
            Open  High   Low Close     Volume   Open   High    Low  Close     Volume
           شتران شتران شتران شتران      شتران   فملی   فملی   فملی   فملی       فملی
J-Date
1404-11-25  4400  4475  4218  4218  238550890  14890  15080  14310  14310  306133075
1404-11-26  4179  4179  4179  4179   39453982  14020  14100  14020  14020  185179129
1404-11-27  4054  4109  4054  4064  430020598  13600  13970  13600  13900  214659584
1404-11-28  4010  4100  3958  4066  164209800  14030  14120  13790  14030  139758819
```
- Returns a `MultiIndex` column structure: `(Column, Symbol)`.

#### Index support

```python
# شاخص کل (Total Market Index)
idx = att.get_history('شاخص کل', limit=10)

# Industry indices
idx = att.get_history('شاخص صنعت فلزات اساسی', limit=10)
```
```
                 Open       High        Low      Close        Volume
J-Date
1404-11-25  4081300.0  4090060.0  3986100.0  3986106.0  2.184455e+10
1404-11-26  3898000.0  3898000.0  3881860.0  3881867.0  2.381066e+10
1404-11-27  3800290.0  3822580.0  3799820.0  3822568.0  2.270925e+10
```

---

### `get_client_type()`

Get historical **Retail / Institutional** (حقیقی / حقوقی) trading data.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_client_type()`

تابع `get_client_type()` برای دریافت **اطلاعات معامله‌گران حقیقی و حقوقی** استفاده می‌شود.

**خروجی عادی (۱۲ ستون):**

| ستون | توضیح |
|---|---|
| `N_buy_retail` | تعداد معاملات خرید حقیقی |
| `N_buy_institutional` | تعداد معاملات خرید حقوقی |
| `N_sell_retail` | تعداد معاملات فروش حقیقی |
| `N_sell_institutional` | تعداد معاملات فروش حقوقی |
| `Vol_buy_retail` | حجم خرید حقیقی |
| `Vol_buy_institutional` | حجم خرید حقوقی |
| `Vol_sell_retail` | حجم فروش حقیقی |
| `Vol_sell_institutional` | حجم فروش حقوقی |
| `Val_buy_retail` | ارزش خرید حقیقی (ریالی) |
| `Val_buy_institutional` | ارزش خرید حقوقی (ریالی) |
| `Val_sell_retail` | ارزش فروش حقیقی (ریالی) |
| `Val_sell_institutional` | ارزش فروش حقوقی (ریالی) |

**خروجی کامل (۲۰ ستون):** علاوه بر ۱۲ ستون بالا:

| ستون اضافی | توضیح |
|---|---|
| `Per_capita_buy_retail` | سرانه خرید حقیقی |
| `Per_capita_sell_retail` | سرانه فروش حقیقی |
| `Per_capita_buy_institutional` | سرانه خرید حقوقی |
| `Per_capita_sell_institutional` | سرانه فروش حقوقی |
| `Power_retail` | قدرت خریدار به فروشنده حقیقی |
| `Power_institutional` | قدرت خریدار به فروشنده حقوقی |
| `Weekday_fa` | نام روز هفته فارسی |
| `Ticker` | نماد |

</div>

```python
att.get_client_type(
    symbol='شتران',            # str or list — symbol name(s) in Persian
    start=None,                # str — start date in Jalali
    end=None,                  # str — end date in Jalali
    limit=0,                   # int — number of last trading days
    raw=False,                 # bool — use TSETMC column names
    output_type='standard',    # str — 'standard' or 'full'
    date_format='jalali',      # str — 'jalali', 'gregorian', or 'both'
    progress=True,             # bool — show progress bar
    save_to_file=False,        # bool — save to CSV
    dropna=True,               # bool — drop extra cols in multi-stock
    ascending=True,            # bool — sort ascending (True) or descending (False)
    save_path=None,            # str — file path to save CSV
)
```

#### Standard output (12 columns)

```python
df = att.get_client_type('شتران', limit=5)
```
```
            N_buy_retail  N_buy_institutional  N_sell_retail  N_sell_institutional  Vol_buy_retail  Vol_buy_institutional  Vol_sell_retail  Vol_sell_institutional  Val_buy_retail  Val_buy_institutional  Val_sell_retail  Val_sell_institutional
J-Date
1404-11-25          1499                   12            883                    10        95906966             142643924       216933695                21617195    414366661677           613387546108     935110119463             92644088322
1404-11-26           531                    3             47                     4        14403982              25050000        28630968                10823014     60194240778           104683950000     119648815272             45229375506
1404-11-27          2465                   10           1969                    27       319021634             110998964       277392757               152627841   1294256635847           450056687467    1125177802472            619135520842
1404-11-28          1260                   11           1171                     9       112375538              51834262       156350833                 7858967    453981687814           208895958402     631059614604             31818031612
```

| Column | Description |
|---|---|
| `N_buy_retail` | Number of individual (حقیقی) buy trades |
| `N_buy_institutional` | Number of institutional (حقوقی) buy trades |
| `N_sell_retail` | Number of individual sell trades |
| `N_sell_institutional` | Number of institutional sell trades |
| `Vol_buy_retail` | Individual buy volume |
| `Vol_buy_institutional` | Institutional buy volume |
| `Vol_sell_retail` | Individual sell volume |
| `Vol_sell_institutional` | Institutional sell volume |
| `Val_buy_retail` | Individual buy value (Rials) |
| `Val_buy_institutional` | Institutional buy value (Rials) |
| `Val_sell_retail` | Individual sell value (Rials) |
| `Val_sell_institutional` | Institutional sell value (Rials) |

#### Full output (20 columns)

```python
df = att.get_client_type('شتران', limit=5, output_type='full')
```

Adds 8 extra columns to the standard 12:

| Extra Column | Description |
|---|---|
| `Per_capita_buy_retail` | Average buy value per individual trade |
| `Per_capita_sell_retail` | Average sell value per individual trade |
| `Per_capita_buy_institutional` | Average buy value per institutional trade |
| `Per_capita_sell_institutional` | Average sell value per institutional trade |
| `Power_retail` | Individual buyer/seller power ratio |
| `Power_institutional` | Institutional buyer/seller power ratio |
| `Weekday_fa` | Day name in Persian |
| `Ticker` | Symbol name |

#### Date range & Gregorian

```python
# Jalali date range
df = att.get_client_type('شتران', start='1404-06-01', end='1404-08-01')

# Gregorian index
df = att.get_client_type('شتران', limit=10, date_format='gregorian')
# Index: 'Date' (datetime64)
```

---

### `get_capital_increase()`

Get the full history of capital increases for a stock.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_capital_increase()`

تابع `get_capital_increase()` **سابقه کامل افزایش سرمایه** یک نماد را برمی‌گرداند.

| ستون | توضیح |
|---|---|
| `old_shares_amount` | تعداد سهام قبل از افزایش سرمایه |
| `new_shares_amount` | تعداد سهام بعد از افزایش سرمایه |

- ایندکس: تاریخ میلادی (`datetime64`)
- داده‌ها از قدیمی‌ترین به جدیدترین مرتب شده‌اند

</div>

```python
df = att.get_capital_increase('شتران')
```
```
            old_shares_amount  new_shares_amount
date
2025-03-02       3.900000e+11       5.395000e+11
2024-02-17       2.750000e+11       3.900000e+11
2022-11-02       1.700000e+11       2.750000e+11
2021-10-17       7.500000e+10       1.700000e+11
2020-10-04       4.400000e+10       7.500000e+10
2019-08-07       2.400000e+10       4.400000e+10
2018-07-24       1.600000e+10       2.400000e+10
2017-02-04       1.200000e+10       1.600000e+10
```
- **Index:** `date` (`datetime64` — Gregorian)
- **Columns:** `old_shares_amount`, `new_shares_amount`

---

### `get_detail()`

Get comprehensive detail for a stock (ISIN, company name, market, sector, etc.).

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_detail()`

تابع `get_detail()` **اطلاعات جامع نماد** شامل کد ISIN، نام شرکت، نام لاتین، بازار، کد تابلو و سایر مشخصات را برمی‌گرداند.

- خروجی: دیتافریم با ۱۵ ردیف (کلید-مقدار)
- ایندکس: نام فیلد به فارسی (مثلاً `کد 12 رقمی نماد`، `نماد فارسی`، `بازار`)
- ستون: `value` — مقدار هر فیلد

</div>

```python
df = att.get_detail('شتران')
```
```
                                           value
key
کد 12 رقمی نماد                     IRO1PTEH0001
کد 5 رقمی نماد                             PTEH1
نام لاتین شرکت                   Palayesh Tehran
کد 4 رقمی شرکت                              PTEH
نام شرکت                        پالايش نفت تهران
نماد فارسی                                 شتران
نماد 30 رقمی فارسی              پالايش نفت تهران
کد 12 رقمی شرکت                     IRO1PTEH0007
بازار               بازار اول (تابلوي اصلي) بورس
کد تابلو                                       1
```
- **Shape:** (15, 1) — 15 key-value rows
- **Index:** `key` (str) — Persian field names
- **Column:** `value`

---

### `get_info()`

Get instrument information (EPS, sector PE, PSR, sector name, threshold data, etc.).

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_info()`

تابع `get_info()` **اطلاعات ابزار مالی** شامل EPS تخمینی، P/E گروه صنعت، PSR، نام گروه صنعت، و اطلاعات آستانه قیمتی را برمی‌گرداند.

- خروجی: دیتافریم با ۴۶ ردیف (کلید-مقدار)
- ایندکس: شناسه فیلد (مثلاً `eps_estimatedEPS`، `eps_sectorPE`، `sector_lSecVal`)
- ستون: `value` — مقدار هر فیلد

</div>

```python
df = att.get_info('شتران')
```
```
                                                       value
key
eps_estimatedEPS                                        1018
eps_sectorPE                                            4.58
eps_psr                                             5933.701
sector_cSecVal                                           23
sector_lSecVal           فراورده هاي نفتي، كك و سوخت هسته اي
```
- **Shape:** (46, 1) — 46 key-value rows
- **Index:** `key` (str) — field identifiers (e.g. `eps_estimatedEPS`, `sector_lSecVal`)
- **Column:** `value`

---

### `get_stats()`

Get trading statistics for a stock (averages, rankings over 3 and 12 months).

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_stats()`

تابع `get_stats()` **آمار معاملاتی نماد** شامل میانگین و رتبه ارزش، حجم و تعداد معاملات در بازه‌های ۳ ماهه و ۱۲ ماهه را برمی‌گرداند.

- خروجی: دیتافریم با ۸۸ ردیف (کلید-مقدار)
- ایندکس: نام آماره به فارسی (مثلاً `میانگین ارزش معاملات در 3 ماه گذشته`)
- ستون: `value` — مقدار عددی هر آماره
- شامل: رتبه‌بندی نماد از نظر حجم، ارزش و دفعات معاملات نسبت به کل بازار

</div>

```python
df = att.get_stats('شتران')
```
```
                                                     value
key
میانگین ارزش معاملات در 3 ماه گذشته           2.443327e+12
میانگین ارزش معاملات در 12 ماه گذشته          1.461746e+12
رتبه ارزش معاملات در 3 ماه گذشته              4.500000e+01
رتبه ارزش معاملات در 12 ماه گذشته             5.200000e+01
میانگین حجم معاملات در 3 ماه گذشته            6.053144e+08
میانگین حجم معاملات در 12 ماه گذشته           4.740798e+08
رتبه حجم معاملات در 3 ماه گذشته               1.200000e+01
رتبه حجم معاملات در 12 ماه گذشته              1.100000e+01
میانگین دفعات معاملات روزانه در 3 ماه گذشته   8.543000e+03
میانگین دفعات معاملات روزانه در 12 ماه گذشته  6.474000e+03
```
- **Shape:** (88, 1) — 88 key-value rows
- **Index:** `key` (str) — Persian statistic names
- **Column:** `value`

---

### `get_introduction()`

Get the **company introduction / profile** (معرفی شرکت) — the Codal *publisher*
record from TSETMC. Contains company identity data: full name, ISIC code,
executive & financial managers, activity subject, addresses, contact info,
auditor, listed capital, financial year-end, and national ID.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_introduction()`

تابع `get_introduction()` **معرفی/شناسنامه‌ی شرکت** را از سرویس کدال سایت TSETMC برمی‌گرداند — همان بخش «معرفی» در صفحه‌ی نماد.

**نکته‌ی فنی:** این endpoint با **خودِ نماد** کار می‌کند (نه `web_id`)، بنابراین نماد ابتدا از طریق جست‌وجوی TSETMC به شکل استاندارد (کاراکتر عربی) تبدیل می‌شود؛ پس هم `'فملی'` و هم `'فملي'` کار می‌کنند.

**فیلدهای مهم خروجی:**

| کلید | توضیح |
|---|---|
| `name` | نام کامل شرکت |
| `symbol` / `displaySymbol` | نماد |
| `isic` | کد آیسیک (ISIC) |
| `executiveManager` | مدیرعامل |
| `financialManager` | مدیر مالی |
| `activitySubject` | موضوع فعالیت |
| `address` | نشانی مجتمع/کارخانه |
| `officeAddress` | نشانی دفتر مرکزی |
| `shareOfficeAddress` | نشانی امور سهام |
| `telNo` / `faxNo` | تلفن / فکس |
| `website` / `email` | وبسایت / ایمیل |
| `inspector` | بازرس قانونی |
| `auditorName` | حسابرس |
| `listedCapital` | سرمایه ثبت‌شده |
| `financialYear` | پایان سال مالی (مثلاً `12/29`) |
| `nationalCode` | شناسه ملی |

- خروجی: دیتافریم کلید-مقدار (ایندکس `key`، ستون `value`) — تمام فیلدها با نام خام انگلیسی، هم‌شکل `get_info()`
- برای **شاخص‌ها** یا نمادهایی که رکورد ناشر ندارند، مقدار `None` برمی‌گردد

</div>

```python
df = att.get_introduction('فملی')
```
```
                                                             value
key
id                                                            8954
symbol                                                        فملي
displaySymbol                                                 فملي
name                                            ملی صنایع مس ایران
isic                                                        272006
executiveManager                             سيدمصطفي فيض اردکاني
financialManager                                    بهنام عبادی ابلی
telNo                                                 021-88724410
website                                             www.nicico.com
email                                            office@nicico.com
listedCapital                                          1050000000
financialYear                                                12/29
nationalCode                                          10100582059
...
```
- **Index:** `key` (str) — raw Codal field names
- **Column:** `value`
- Works with either Persian (`'فملی'`) or Arabic (`'فملي'`) spelling.

---

### `get_shareholders()`

Get major shareholders of a stock (current or historical).

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_shareholders()`

تابع `get_shareholders()` **لیست سهامداران عمده** یک نماد را برمی‌گرداند — هم فعلی و هم تاریخی.

**پارامترها:**

| پارامتر | توضیح |
|---|---|
| `symbol` | نماد فارسی سهم |
| `date` | تاریخ شمسی به فرمت `YYYYMMDD` برای دریافت سهامداران در تاریخ خاص (`None` = آخرین اطلاعات) |
| `include_id` | اگر `True` باشد، شناسه سهامدار (`share_holder_id`) نیز اضافه می‌شود |

**ستون‌های خروجی:**

| ستون | توضیح |
|---|---|
| `share_holder_name` | نام سهامدار |
| `number_of_shares` | تعداد سهام |
| `percentage_of_shares` | درصد مالکیت |
| `change_state` | وضعیت تغییر (۱ = بدون تغییر، ۳ = تغییر یافته) |
| `change_amount` | مقدار تغییر |
| `date` | تاریخ ثبت (میلادی YYYYMMDD) |
| `share_holder_id` | شناسه عددی سهامدار (فقط با `include_id=True`) |

</div>

```python
att.get_shareholders(
    symbol='شتران',   # str — symbol name in Persian
    date=None,        # str — Jalali date 'YYYYMMDD' for historical data (None = latest)
    include_id=False,     # bool — include shareholder IDs
)
```

#### Current shareholders

```python
df = att.get_shareholders('شتران')
```
```
                                       share_holder_name  number_of_shares  percentage_of_shares  change_state  change_amount      date
0                                      بانك صادرات ايران      3.234498e+10                 5.995             1            0.0  20260218
1                شركت سرمايه گذاري ايرانيان -سهامي خاص -      2.569312e+10                 4.762             1            0.0  20260218
2    شركت سرمايه گذاري .ا.تهران -سهامي عام --م ك م ف ع -      2.169540e+10                 4.021             1            0.0  20260218
3  شركت .س .سهام عدالت .ا.خراسان رضوي -س ع --م ك م ف ع -      2.092901e+10                 3.879             1            0.0  20260218
4                             PRXسبد-شرك76894--موس33322-      1.797408e+10                 3.331             1            0.0  20260218
```

| Column | Description |
|---|---|
| `share_holder_name` | Shareholder name |
| `number_of_shares` | Number of shares held |
| `percentage_of_shares` | Ownership percentage |
| `change_state` | Change indicator (1=unchanged, 3=changed) |
| `change_amount` | Amount of change |
| `date` | Date of record (YYYYMMDD) |

#### Historical shareholders

```python
df = att.get_shareholders('داتام', date='14021006')
```
```
                              share_holder_name  number_of_shares  percentage_of_shares  change_state  change_amount      date
0           شركت توسعه تجارت داتام -سهامي خاص -      6.732833e+09                 67.32             3   6.232833e+09  20231230
1        BFMصندوق سرمايه گذاري .ا.ب .افتخارحافظ      1.500000e+09                 15.00             0   6.232833e+09  20231230
```

#### With shareholder IDs

```python
df = att.get_shareholders('شتران', include_id=True)
# Adds 'share_holder_id' column (7 columns total)
```

---

### `get_symbols()`

Get a list of all symbols in Tehran Stock Exchange markets — including stocks, ETFs, bonds, options, and more.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_symbols()`

تابع `get_symbols()` فهرست **تمام نمادهای بازار سرمایه** را برمی‌گرداند. علاوه بر سهام و حق‌تقدم و صندوق‌ها، اکنون می‌توانید **اوراق بدهی، اختیار معامله، تسهیلات مسکن، گواهی‌های کالایی و گواهی‌های انرژی** را هم دریافت کنید.

**پارامترهای فیلتر بازار (سهام):**

| پارامتر | مقدار پیش‌فرض | توضیح |
|---|---|---|
| `bourse` / `main_market` | `True` | شامل نمادهای **بورس** |
| `farabourse` / `otc` | `True` | شامل نمادهای **فرابورس** (شامل نوآفرین) |
| `payeh` / `base_market` | `True` | شامل نمادهای **بازار پایه** |
| `payeh_color` / `base_market_tier` | `None` | فیلتر رنگ بازار پایه: `'زرد'`، `'نارنجی'`، `'قرمز'` |

**پارامترهای نوع دارایی:**

| پارامتر | مقدار پیش‌فرض | توضیح |
|---|---|---|
| `haghe_taqadom` / `rights` | `False` | شامل نمادهای **حق تقدم** |
| `sandogh` / `funds` | `False` | شامل **صندوق‌های ETF و سرمایه‌گذاری** |
| `bonds` | `False` | شامل **اوراق بدهی**: اخزا، اراد، صکوک، اسناد شهری |
| `options` | `False` | شامل **اختیار معامله**: خرید و فروش سهام و صندوق |
| `mortgage` | `False` | شامل **تسهیلات مسکن** |
| `commodity` | `False` | شامل **گواهی‌های کالایی**: گواهی سپرده، زعفران |
| `energy` | `False` | شامل **گواهی‌های انرژی**: گواهی ظرفیت برق |
| `output` | `'dataframe'` | فرمت خروجی: `'dataframe'` یا `'list'` |

**ستون‌های خروجی (هنگام `output='dataframe'`):**

| ستون | توضیح |
|---|---|
| `symbol` | نماد (ایندکس DataFrame) |
| `name` | نام کامل فارسی |
| `instrument_isin` | کد ISIN |
| `english_name` | نام انگلیسی |
| `company_code` | کد ۴ رقمی شرکت |
| `company_isin` | ISIN شرکت |
| `market` | نوع بازار |
| `industry_group` | گروه صنعت |
| `asset_type` | **نوع دارایی**: `stock`, `right`, `fund`, `bond`, `option`, `mortgage`, `commodity`, `energy` |
| `instrument_id` | شناسه عددی نماد |

**مثال‌های فیلتر:**

- `att.get_symbols()` → فقط سهام (پیش‌فرض)
- `att.get_symbols(bonds=True)` → سهام + اوراق بدهی
- `att.get_symbols(bourse=False, farabourse=False, payeh=False, options=True)` → فقط اختیار معامله
- `att.get_symbols(sandogh=True, bonds=True, options=True)` → سهام + صندوق + اوراق + اختیار
- `att.get_symbols(output='list')` → خروجی به صورت لیست نمادها

</div>

```python
att.get_symbols(
    bourse=True,          # bool — include Bourse stocks (alias: main_market)
    farabourse=True,      # bool — include Fara Bourse stocks (alias: otc)
    payeh=True,           # bool — include Payeh market stocks (alias: base_market)
    haghe_taqadom=False,  # bool — include subscription rights (alias: rights)
    sandogh=False,        # bool — include ETFs/funds (alias: funds)
    bonds=False,          # bool — include bonds, sukuk, treasury bills
    options=False,        # bool — include stock & fund options (calls + puts)
    mortgage=False,       # bool — include housing facility certificates
    commodity=False,      # bool — include commodity certificates
    energy=False,         # bool — include energy certificates
    payeh_color=None,     # str or list — filter Payeh by tier (alias: base_market_tier)
    output='dataframe',   # str — 'dataframe' or 'list'
    progress=True,        # bool — show progress messages
)
```

#### Default: all regular stocks

```python
df = att.get_symbols()
```
```
                                  name instrument_isin      english_name company_code  company_isin                        market         industry_group asset_type      instrument_id
symbol
آباد     توریستی ورفاهی آبادگران ایران    IRO1ABAD0001         Abadgaran         ABAD  IRO1ABAD0002                بازار دوم بورس          هتل و رستوران      stock  59612098290740355
دعبید     لابراتوارداروسازی  دکترعبیدی    IRO1ABDI0001    Dr. Abidi Lab.         ABDI  IRO1ABDI0004                بازار دوم بورس  مواد و محصولات دارویی      stock  49054891736433700
سآبیک                       سیمان آبیک    IRO1ABIK0001      Abiak Cement         ABIK  IRO1ABIK0005  بازار اول (تابلوی اصلی) بورس        سیمان، آهک و گچ      stock  70883594945615893
```
- **Shape:** DataFrame of all symbols in selected mode
- **Index:** `symbol` (str) — Persian ticker symbol

| Column | Description |
|---|---|
| `name` | Full company/instrument name |
| `instrument_isin` | ISIN code (e.g. `IRO1ABAD0001`) |
| `english_name` | English name |
| `company_code` | 4-character company code |
| `company_isin` | Company-level ISIN |
| `market` | Market name (بورس / فرابورس / پایه) |
| `industry_group` | Industry sector name |
| `asset_type` | Asset class: `stock`, `right`, `fund`, `bond`, `option`, `mortgage`, `commodity`, `energy` |
| `instrument_id` | Numeric instrument identifier |

#### Filter by market

```python
# Bourse only
att.get_symbols(farabourse=False, payeh=False)

# Fara Bourse only
att.get_symbols(bourse=False, payeh=False)

# Payeh market only
att.get_symbols(bourse=False, farabourse=False)
```

#### Filter Payeh by color (تابلو)

```python
# زرد (yellow) only
att.get_symbols(bourse=False, farabourse=False, payeh_color='زرد')

# نارنجی (orange) only
att.get_symbols(bourse=False, farabourse=False, payeh_color='نارنجی')

# قرمز (red) only
att.get_symbols(bourse=False, farabourse=False, payeh_color='قرمز')
```

#### Include additional asset types

```python
# With subscription rights
att.get_symbols(haghe_taqadom=True)

# With ETFs/funds
att.get_symbols(sandogh=True)

# Bonds only (no stocks)
att.get_symbols(bourse=False, farabourse=False, payeh=False, bonds=True)

# Options only (no stocks)
att.get_symbols(bourse=False, farabourse=False, payeh=False, options=True)

# All asset types at once
att.get_symbols(
    haghe_taqadom=True, sandogh=True, bonds=True,
    options=True, mortgage=True, commodity=True, energy=True,
)

# Filter by asset_type column
df = att.get_symbols(sandogh=True, bonds=True)
only_bonds = df[df['asset_type'] == 'bond']
only_funds = df[df['asset_type'] == 'fund']
```

#### Output as list

```python
symbols = att.get_symbols(output='list')
# Returns: ['آباد', 'دعبید', 'سآبیک', ...]
```

---

### `get_currency()`

Get historical price data for currencies and coins from TGJU.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_currency()`

تابع `get_currency()` داده‌های تاریخی **ارز و سکه** را از سایت TGJU دریافت می‌کند.

**پارامترها:**

| پارامتر | مقدار پیش‌فرض | توضیح |
|---|---|---|
| `name` | — | نام ارز/سکه به **فارسی** یا **انگلیسی** (رشته یا لیست) |
| `start` | `None` | تاریخ شروع شمسی به فرمت `YYYY-MM-DD` |
| `end` | `None` | تاریخ پایان شمسی به فرمت `YYYY-MM-DD` |
| `limit` | `0` | تعداد آخرین روزهای معاملاتی (۰ = همه) |
| `output_type` | `'standard'` | نوع خروجی: `'standard'` یا `'full'` |
| `date_format` | `'jalali'` | فرمت تاریخ: `'jalali'`، `'gregorian'` یا `'both'` |
| `progress` | `True` | نمایش نوار پیشرفت |
| `save_to_file` | `False` | ذخیره خروجی در فایل CSV |
| `dropna` | `True` | حذف ستون‌های اضافی در حالت چند ارزه |
| `return_type` | `None` | محاسبه بازدهی: `'simple'`، `'log'`، `'both'` |
| `ascending` | `True` | مرتب‌سازی صعودی (`True`) یا نزولی (`False`) بر اساس تاریخ |
| `save_path` | `None` | مسیر فایل CSV برای ذخیره (مثلاً `'output.csv'`) |

**ارزها و سکه‌های پشتیبانی شده (۱۴ مورد):**

| نام انگلیسی | نام فارسی | توضیح |
|---|---|---|
| `dollar` | `دلار` | دلار آمریکا |
| `euro` | `یورو` | یورو اروپا |
| `derham` | `درهم` | درهم امارات |
| `lira` | `لیر` | لیر ترکیه |
| `pond` | `پوند` | پوند انگلیس |
| `yuan` | `یوان` | یوان چین |
| `sekeh` | `سکه امامی` | سکه طلا تمام بهار آزادی (امامی) |
| `nim_sekeh` | `نیم سکه` | نیم سکه بهار آزادی |
| `rob_sekeh` | `ربع سکه` | ربع سکه بهار آزادی |
| `sekeh_gerami` | `سکه گرمی` | سکه گرمی |
| `ons` | `انس` | انس جهانی طلا |
| `mesghal` | `مثقال` | مثقال طلا |
| `gold_18` | `طلای ۱۸ عیار` | طلای ۱۸ عیار |
| `gold_24` | `طلای ۲۴ عیار` | طلای ۲۴ عیار |

**ستون‌های خروجی (حالت استاندارد):**

| ستون | توضیح |
|---|---|
| `Open` | قیمت باز شدن |
| `High` | بالاترین قیمت |
| `Low` | پایین‌ترین قیمت |
| `Close` | قیمت بسته شدن |

**نکات مهم:**
- می‌توان از نام **فارسی** یا **انگلیسی** استفاده کرد (مثلاً `'دلار'` = `'dollar'`)
- برای دریافت **چند ارز همزمان**، لیست ارسال کنید: `['dollar', 'euro']` → ستون‌ها `MultiIndex` خواهند بود
- با `date_format='gregorian'` ایندکس به `datetime64` تغییر می‌کند
- با `return_type='log'` بازدهی لگاریتمی اضافه می‌شود

</div>

```python
att.get_currency(
    name='dollar',               # str or list — name in Persian or English
    start=None,                  # str — start date in Jalali
    end=None,                    # str — end date in Jalali
    limit=0,                     # int — number of last trading days
    output_type='standard',      # str — 'standard' or 'full'
    date_format='jalali',        # str — 'jalali', 'gregorian', or 'both'
    progress=True,               # bool — show progress bar
    save_to_file=False,          # bool — save to CSV
    dropna=True,                 # bool — drop extra cols in multi-currency
    return_type=None,            # str/list — 'simple', 'log', 'both', or ['simple','Close',5]
    ascending=True,              # bool — sort ascending (True) or descending (False)
    save_path=None,              # str — file path to save CSV
)
```

#### Supported names

| English | فارسی | Description |
|---|---|---|
| `dollar` | `دلار` | US Dollar |
| `euro` | `یورو` | Euro |
| `derham` | `درهم` | UAE Dirham |
| `lira` | `لیر` | Turkish Lira |
| `pond` | `پوند` | British Pound |
| `yuan` | `یوان` | Chinese Yuan |
| `sekeh` | `سکه امامی` | Gold Coin (Emami) |
| `nim_sekeh` | `نیم سکه` | Half Coin |
| `rob_sekeh` | `ربع سکه` | Quarter Coin |
| `sekeh_gerami` | `سکه گرمی` | Gram Coin |
| `ons` | `انس` | Gold Ounce |
| `mesghal` | `مثقال` | Mesghal |
| `gold_18` | `طلای ۱۸ عیار` | 18K Gold |
| `gold_24` | `طلای ۲۴ عیار` | 24K Gold |

#### Standard output

```python
df = att.get_currency('dollar', limit=10)
```
```
                 Open       High        Low      Close
J-Date
1404-11-16  1609350.0  1624700.0  1572300.0  1622400.0
1404-11-18  1619350.0  1619700.0  1564300.0  1564700.0
1404-11-19  1554450.0  1591700.0  1554300.0  1589500.0
1404-11-20  1592600.0  1617700.0  1592300.0  1612300.0
1404-11-21  1613600.0  1637700.0  1613300.0  1632400.0
1404-11-23  1624550.0  1627700.0  1617300.0  1625500.0
1404-11-25  1621350.0  1621700.0  1583800.0  1583900.0
1404-11-26  1586600.0  1603700.0  1586300.0  1597300.0
1404-11-27  1598550.0  1603700.0  1591300.0  1599600.0
1404-11-28  1599900.0  1629700.0  1599800.0  1608600.0
```
- **Columns:** `Open`, `High`, `Low`, `Close` (all `float64`)
- **Index:** `J-Date` (str — Jalali date)

#### Persian names work too

```python
df = att.get_currency('دلار', limit=10)      # Same result as 'dollar'
df = att.get_currency('سکه', limit=10)       # Emami gold coin
df = att.get_currency('ربع سکه', limit=10)   # Quarter coin
```

#### With Gregorian dates

```python
df = att.get_currency('dollar', limit=10, date_format='gregorian')
# Index: 'Date' (datetime64)
```

#### With return calculation

```python
df = att.get_currency('dollar', limit=15, return_type='log')
```
```
                 Open       High        Low      Close   returns
J-Date
1404-11-09  1609450.0  1649700.0  1564300.0  1584400.0       NaN
1404-11-11  1599650.0  1649700.0  1582300.0  1629600.0  0.028129
1404-11-12  1624300.0  1624700.0  1574300.0  1589550.0 -0.024884
1404-11-13  1586600.0  1586700.0  1532300.0  1544400.0 -0.028815
1404-11-14  1544650.0  1571700.0  1534300.0  1568500.0  0.015484
```

#### Multiple currencies

```python
df = att.get_currency(['ربع سکه', 'euro'], limit=10)
```
```
                   Open         High          Low        Close       Open       High        Low      Close
               rob-seke     rob-seke     rob-seke     rob-seke       euro       euro       euro       euro
J-Date
1404-11-16  550000000.0  565500000.0  550000000.0  560000000.0  1856100.0  1917900.0  1856100.0  1915600.0
1404-11-18  540000000.0  540000000.0  520000000.0  520000000.0  1914100.0  1914400.0  1849000.0  1849000.0
1404-11-19  524900000.0  550700000.0  524900000.0  549500000.0  1837300.0  1881300.0  1837200.0  1878600.0
```
- Returns a `MultiIndex` column structure: `(Column, Currency)`.

#### Date range

```python
df = att.get_currency('dollar', start='1404-06-01', end='1404-08-01')
# Returns 51 trading days of dollar price history
```

---

### `get_intraday()`

Get intraday (tick-level or candle) trade data for a symbol — today or historical.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_intraday()`

تابع `get_intraday()` داده‌های **معاملات درون‌روزی** (تیک یا کندل) یک نماد را برمی‌گرداند — امروز یا تاریخی.

**پارامترها:**

| پارامتر | مقدار پیش‌فرض | توضیح |
|---|---|---|
| `symbol` | — | نماد فارسی سهم |
| `interval` | `'1min'` | بازه زمانی کندل (جدول زیر) |
| `start` | `None` | تاریخ شروع (شمسی یا میلادی) برای داده تاریخی |
| `end` | `None` | تاریخ پایان (شمسی یا میلادی) برای داده تاریخی |
| `progress` | `True` | نمایش گزارش پیشرفت |

**بازه‌های زمانی پشتیبانی شده:**

| مقدار | توضیح |
|---|---|
| `'tick'` | داده خام تیک/اسنپ‌شات (بدون تجمیع) |
| `'1min'` | کندل ۱ دقیقه‌ای |
| `'5min'` | کندل ۵ دقیقه‌ای |
| `'15min'` | کندل ۱۵ دقیقه‌ای |
| `'30min'` | کندل ۳۰ دقیقه‌ای |
| `'1h'` | کندل ۱ ساعته |
| `'4h'` | کندل ۴ ساعته |
| `'12h'` | کندل ۱۲ ساعته |

**ستون‌های خروجی (حالت کندل):**

| ستون | توضیح |
|---|---|
| `Open` | قیمت باز شدن (`int`) |
| `High` | بالاترین قیمت (`int`) |
| `Low` | پایین‌ترین قیمت (`int`) |
| `Close` | قیمت بسته شدن (`int`) |
| `Volume` | حجم معاملات (`int`) |
| `TradeCount` | تعداد معاملات (`int`) |

**ستون‌های خروجی (حالت تیک — امروز):**

| ستون | توضیح |
|---|---|
| `TradeNo` | شماره معامله |
| `Price` | قیمت معامله (`float`) |
| `Volume` | حجم معامله |
| `J-Date` | تاریخ شمسی |

**ستون‌های خروجی (حالت تیک — تاریخی):**

| ستون | توضیح |
|---|---|
| `Price` | قیمت (`float`) |
| `Volume` | حجم |
| `TradeCount` | تعداد معاملات |

**نکات مهم:**
- **بدون `start`/`end`**: داده‌های **امروز** برگردانده می‌شود
- **با `start`/`end`**: داده‌های **تاریخی** از آرشیو TSE دریافت می‌شود
- ایندکس همیشه `DateTime` از نوع `datetime64` است
- برای تیک امروز: معاملات تکی
- برای تیک تاریخی: اسنپ‌شات‌های هر روز
- این تابع **فقط برای سهام** کار می‌کند، نه شاخص‌ها

</div>

```python
att.get_intraday(
    symbol='شتران',        # str — Stock symbol name in Persian
    interval='1min',        # str — Candle interval (see below)
    start=None,             # str — Start date (Jalali or Gregorian) for historical data
    end=None,               # str — End date (Jalali or Gregorian) for historical data
    progress=True,          # bool — Show progress messages
)
```

**Supported intervals:**

| Value | Description |
|---|---|
| `'tick'` | Raw tick/snapshot data (no aggregation) |
| `'1min'` | 1-minute candles |
| `'5min'` | 5-minute candles |
| `'15min'` | 15-minute candles |
| `'30min'` | 30-minute candles |
| `'1h'` | 1-hour candles |
| `'4h'` | 4-hour candles |
| `'12h'` | 12-hour candles |

#### Today's candles (no start/end)

```python
df = att.get_intraday('شتران', interval='1min')
```
```
                     Open  High   Low  Close   Volume  TradeCount
DateTime
2026-02-18 09:00:00  4079  4089  4067   4070  3687191          53
2026-02-18 09:01:00  4071  4089  4070   4089   952191          18
2026-02-18 09:02:00  4089  4089  4080   4089   475747          17
2026-02-18 09:03:00  4089  4117  4089   4117  1025581          30
2026-02-18 09:04:00  4116  4118  4090   4100  1307914          32
```
- **Columns:** `Open`, `High`, `Low`, `Close` (int), `Volume` (int), `TradeCount` (int)
- **Index:** `DateTime` (`datetime64`)

```python
# 5-minute candles
df = att.get_intraday('شتران', interval='5min')
```
```
                     Open  High   Low  Close   Volume  TradeCount
DateTime
2026-02-18 09:00:00  4079  4118  4067   4100  7448624         150
2026-02-18 09:05:00  4100  4100  4037   4050  5321877         147
2026-02-18 09:10:00  4043  4049  4010   4032  9777574         220
```

```python
# 1-hour candles
df = att.get_intraday('شتران', interval='1h')
```
```
                     Open  High   Low  Close     Volume  TradeCount
DateTime
2026-02-18 09:00:00  4079  4118  3966   3966   70752848        1993
2026-02-18 10:00:00  3965  3988  3916   3916  163093506        3051
2026-02-18 11:00:00  3916  3916  3916   3916    8004606         330
2026-02-18 12:00:00  3916  3917  3916   3916   85675975        1018
```

#### 4-hour & 12-hour candles (new intervals)

```python
# 4-hour candles
df = att.get_intraday('شتران', interval='4h')
```
```
                     Open  High   Low  Close     Volume  TradeCount
DateTime
2026-02-18 08:00:00  4079  4118  3916   3916  241850960        5374
2026-02-18 12:00:00  3916  3917  3916   3916   85675975        1018
```

```python
# 12-hour candles
df = att.get_intraday('شتران', interval='12h')
```
```
                     Open  High   Low  Close     Volume  TradeCount
DateTime
2026-02-18 00:00:00  4079  4118  3916   3916  241850960        5374
2026-02-18 12:00:00  3916  3917  3916   3916   85675975        1018
```

#### Today's raw ticks

```python
df = att.get_intraday('شتران', interval='tick')
```
```
                     TradeNo   Price  Volume      J-Date
DateTime
2026-02-18 09:00:17        1  4079.0  400000  1404-11-29
2026-02-18 09:00:17        2  4079.0  240000  1404-11-29
2026-02-18 09:00:17        3  4079.0  200000  1404-11-29
2026-02-18 09:00:17        4  4079.0  177119  1404-11-29
2026-02-18 09:00:17        5  4079.0  119805  1404-11-29
```
- **Columns:** `TradeNo`, `Price`, `Volume`, `J-Date`
- **Shape:** ~6000+ rows per day (individual trades)

#### Historical candles (with start/end)

```python
# Single day
df = att.get_intraday('شتران', interval='5min', start='1404-11-06')
```
```
                     Open  High   Low  Close   Volume  TradeCount
DateTime
2026-01-26 09:00:00  4490  4490  4490   4490  4510224          17
2026-01-26 09:05:00  4490  4490  4490   4490  3264852          32
2026-01-26 09:10:00  4490  4490  4490   4490   655961          27
```

```python
# Multi-day range
df = att.get_intraday('شتران', interval='1min',
                        start='1404-11-01', end='1404-11-06')
# Shape: (838, 6) — 838 one-minute candles across 5 trading days
```

#### Historical raw snapshots

```python
df = att.get_intraday('شتران', interval='tick', start='1404-11-06')
```
```
                      Price   Volume  TradeCount
DateTime
2026-01-26 09:00:40  4490.0  1237786          88
2026-01-26 09:01:07  4490.0    75473           2
2026-01-26 09:01:16  4490.0    13313           1
```
- **Columns:** `Price`, `Volume`, `TradeCount` (no TradeNo or J-Date for historical)
- **Shape:** ~400 snapshots per day (~725 price points from ClosingPriceHistory)

> **Note:** This function works for individual stocks only — not for indices.

---

### `get_market_snapshot()`

Get comprehensive real-time market data for **all** instruments in one API call — stocks, ETFs, options, bonds, and more.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_market_snapshot()`

تابع `get_market_snapshot()` اطلاعات **لحظه‌ای کل بازار** را در یک فراخوانی برمی‌گرداند — سهام، صندوق‌های ETF، اختیارمعامله، اوراق و غیره.

**خروجی:** دیکشنری با سه کلید:

| کلید | نوع | توضیح |
|---|---|---|
| `stocks` | `DataFrame` | دیتافریم تمام نمادها با ۲۵ ستون |
| `market_time` | `str` | ساعت و تاریخ بازار (شمسی، مثلاً `"04/11/29 15:04:05"`) |
| `index_value` | `float` | مقدار **شاخص کل** بازار |

**ستون‌های دیتافریم (۲۵ ستون):**

| ستون | نوع | توضیح |
|---|---|---|
| `InsCode` | `str` | کد ابزار (شناسه یکتا — کلید اتصال با سایر داده‌ها) |
| `ISIN` | `str` | شناسه بین‌المللی اوراق بهادار |
| `Symbol` | `str` | نماد (مثلاً `نوری`، `شتران`) |
| `Name` | `str` | نام کامل شرکت |
| `Time` | `str` | زمان آخرین معامله (`HH:MM:SS`) |
| `Yesterday` | `int64` | قیمت دیروز (مرجع) |
| `Close` | `int64` | قیمت پایانی (میانگین وزنی) |
| `Last` | `int64` | آخرین قیمت معامله شده |
| `TradeCount` | `int64` | تعداد معاملات |
| `Volume` | `int64` | حجم معاملات |
| `Value` | `int64` | ارزش معاملات (ریال) |
| `Low` | `int64` | پایین‌ترین قیمت روز |
| `High` | `int64` | بالاترین قیمت روز |
| `EPS` | `int64` | سود هر سهم |
| `PriceYesterday` | `int64` | قیمت دیروز (آخرین معامله) |
| `Flow` | `int64` | کد جریان بازار |
| `SectorCode` | `str` | کد گروه صنعت |
| `MaxAllowed` | `int64` | سقف مجاز قیمت |
| `MinAllowed` | `int64` | کف مجاز قیمت |
| `BaseVolume` | `int64` | حجم مبنا |
| `InstrumentType` | `int64` | کد نوع ابزار (جدول زیر) |
| `NAV` | `int64` | ارزش خالص دارایی (برای ETF‌ها، بقیه صفر) |
| `MarketCode` | `str` | شناسه بازار: `N1`، `N2`، `Z1`، `P1`، `B1`، … |
| `Change` | `int64` | تغییر = پایانی − دیروز |
| `ChangePct` | `float64` | درصد تغییر |

**کدهای نوع ابزار (`InstrumentType`):**

| کد | نوع |
|---|---|
| `200` | شاخص |
| `208` | صکوک |
| `300` | سهام بورس |
| `301` | حق تقدم بورس |
| `303` | سهام بورس (تابلوی فرعی) |
| `305` | صندوق ETF |
| `306` | اوراق بدهی (مرابحه/اجاره/خزانه) |
| `309` | فرابورس |
| `311` / `312` | اختیارمعامله (خرید/فروش) |
| `400` / `403` | حق تقدم فرابورس |
| `706` | اوراق دولتی |

**مثال فیلتر:**
- `InstrumentType.isin([300, 303, 309])` → فقط سهام عادی
- `InstrumentType == 305` → فقط صندوق‌های ETF
- `InstrumentType.isin([311, 312])` → فقط اختیارمعامله

</div>

```python
data = att.get_market_snapshot()

stocks_df    = data['stocks']       # DataFrame — all instruments with full data
market_time  = data['market_time']  # str — Jalali date/time (e.g. "04/11/29 15:04:05")
index_value  = data['index_value']  # float — شاخص کل (total market index)
```

#### Full output

```python
data = att.get_market_snapshot()
print(data['stocks'].shape)       # DataFrame of all instruments
print(data['market_time'])        # '04/11/29 15:04:05'
print(data['index_value'])        # 3806743.94
```
```
             InsCode          ISIN    Symbol                           Name      Time  Yesterday  Close   Last  TradeCount   Volume         Value    Low   High  EPS  PriceYesterday  Flow SectorCode  MaxAllowed  MinAllowed  BaseVolume  InstrumentType  NAV MarketCode  Change  ChangePct
0   9538218081776543  IRO9AHRM0281  ضهرم1116  اختيارخ اهرم-14000-1404/11/29  12:25:07      15803  15407  15210          14       66    1016851000  14641  15803    0         68           0           0        1000             311         3A    -396      -2.51
1  63185775846688586  IRO9AHRM0331  ضهرم1121  اختيارخ اهرم-22000-1404/11/29  12:28:48       8000   7454   7220          48     2388   17800942000   6910   8200    0         68           0           0        1000             311         3A    -546      -6.82
2    358972276573533  IRO9AHRM0341  ضهرم1122  اختيارخ اهرم-24000-1404/11/29  12:29:12       6051   5354   5230         161     6819   36508070000   4755   6200    0         68           0           0        1000             311         3A    -697     -11.52
```

#### Stocks DataFrame columns (25 columns)

| Column | Type | Description |
|---|---|---|
| `InsCode` | str | Instrument code (unique ID, used for joining with other data) |
| `ISIN` | str | International Securities ID (e.g. `IRO1NORI0001`) |
| `Symbol` | str | نماد (e.g. `نوری`, `شتران`) |
| `Name` | str | Full company name (e.g. `پتروشيمي نوري`) |
| `Time` | str | Last trade time (HH:MM:SS) |
| `Yesterday` | int64 | Yesterday's reference/closing price (دیروز) |
| `Close` | int64 | Today's closing / weighted avg price (قیمت پایانی) |
| `Last` | int64 | Last traded price (آخرین معامله) |
| `TradeCount` | int64 | Number of trades |
| `Volume` | int64 | Total volume |
| `Value` | int64 | Total value (Rials) |
| `Low` | int64 | Day's lowest price |
| `High` | int64 | Day's highest price |
| `EPS` | int64 | Earnings per share |
| `PriceYesterday` | int64 | Yesterday’s last traded price (قیمت دیروز - آخرین معامله) |
| `Flow` | int64 | Market flow code (جریان بازار) |
| `SectorCode` | str | Industry/sector group code (کد گروه صنعت) |
| `MaxAllowed` | int64 | Upper price limit (سقف مجاز) |
| `MinAllowed` | int64 | Lower price limit (کف مجاز) |
| `BaseVolume` | int64 | Base volume / total shares (حجم مبنا) |
| `InstrumentType` | int64 | Type code: `300`=stock, `305`=ETF, `306`=bond, `309`=OTC, `311`/`312`=option, `706`=govt bond, … |
| `NAV` | int64 | Net Asset Value (for ETFs, 0 for stocks) |
| `MarketCode` | str | Market identifier: `N1`, `N2`, `Z1`, `P1`, `B1`, … |
| `Change` | int64 | Close − Yesterday |
| `ChangePct` | float64 | Change as percentage |

#### Filter by instrument type

```python
data = att.get_market_snapshot()

# Regular stocks only (300=Bourse, 303=Bourse secondary, 309=FaraBourse)
stocks = data['stocks'][data['stocks']['InstrumentType'].isin([300, 303, 309])]
print(stocks.shape)    # (941, 25)

# ETFs only (305)
etfs = data['stocks'][data['stocks']['InstrumentType'] == 305]
print(etfs.shape)      # ETF instruments

# Options only (311/312)
options = data['stocks'][data['stocks']['InstrumentType'].isin([311, 312])]
print(options.shape)   # option contracts
```

#### Practical examples

```python
# Top volume stocks
stocks = data['stocks'][data['stocks']['InstrumentType'].isin([300, 303, 309])]
top = stocks.nlargest(10, 'Volume')[['Symbol', 'Last', 'Volume', 'ChangePct']]

# Stocks up > 3%
gainers = stocks[stocks['ChangePct'] > 3][['Symbol', 'Last', 'ChangePct']]

# Filter by sector
sector = stocks[stocks['SectorCode'] == '27'][['Symbol', 'Name', 'Last', 'EPS']]
```

---

### `get_market_client_type()`

Get individual (حقیقی) vs institutional (حقوقی) trade data for **all** instruments in one call.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_market_client_type()`

تابع `get_market_client_type()` اطلاعات **حقیقی/حقوقی** تمام نمادهای بازار را در یک فراخوانی برمی‌گرداند.

**ستون‌های خروجی (۱۱ ستون):**

| ستون | توضیح |
|---|---|
| `InsCode` | کد ابزار (کلید اتصال با `get_market_snapshot`) |
| `Buy_I_Count` | تعداد معاملات خرید **حقیقی** |
| `Buy_N_Count` | تعداد معاملات خرید **حقوقی** |
| `Buy_I_Volume` | حجم خرید **حقیقی** |
| `Buy_N_Volume` | حجم خرید **حقوقی** |
| `Sell_I_Count` | تعداد معاملات فروش **حقیقی** |
| `Sell_N_Count` | تعداد معاملات فروش **حقوقی** |
| `Sell_I_Volume` | حجم فروش **حقیقی** |
| `Sell_N_Volume` | حجم فروش **حقوقی** |
| `Net_I_Volume` | خالص حجم حقیقی (خرید − فروش) |
| `Net_N_Volume` | خالص حجم حقوقی (خرید − فروش) |

**ابعاد خروجی:** یک سطر به ازای هر نماد × ۱۱ ستون

**ترکیب با `get_market_snapshot()`:**

برای ساخت فیلتر بازار کامل، این دو تابع را با `merge` ترکیب کنید:
```python
merged = data['stocks'].merge(ct, on='InsCode', how='left')
```
اکنون هم داده قیمتی و هم اطلاعات حقیقی/حقوقی در یک دیتافریم دارید!

**کاربردها:**
- شناسایی نمادهایی با **خرید سنگین حقوقی**: `Net_N_Volume > 1_000_000`
- شناسایی نمادهایی با **خروج حقیقی**: `Net_I_Volume < 0`
- محاسبه **نسبت حقیقی به حقوقی** در خرید و فروش

</div>

```python
df = att.get_market_client_type()
```
```
             InsCode  Buy_I_Count  Buy_N_Count  Buy_I_Volume  Buy_N_Volume  Sell_I_Count  Sell_N_Count  Sell_I_Volume  Sell_N_Volume  Net_I_Volume  Net_N_Volume
0  39453972158399542          502           10      66409668     119990996           176             8       27770768      158629896      38638900     -38638900
1  65249046611427924          168           13      12411142      58529003           127            11        7625574       63314571       4785568      -4785568
2  34718633636164421          441            4     127933422      25586667           255             4       54682505       98837584      73250917     -73250917
```
- **Shape:** (~1880, 11)

| Column | Description |
|---|---|
| `InsCode` | Instrument code (join key with `get_market_snapshot`) |
| `Buy_I_Count` | Individual buy trade count |
| `Buy_N_Count` | Institutional buy trade count |
| `Buy_I_Volume` | Individual buy volume |
| `Buy_N_Volume` | Institutional buy volume |
| `Sell_I_Count` | Individual sell trade count |
| `Sell_N_Count` | Institutional sell trade count |
| `Sell_I_Volume` | Individual sell volume |
| `Sell_N_Volume` | Institutional sell volume |
| `Net_I_Volume` | Net individual volume (buy − sell) |
| `Net_N_Volume` | Net institutional volume (buy − sell) |

#### Join with get_market_snapshot

```python
data = att.get_market_snapshot()
ct = att.get_market_client_type()

merged = data['stocks'].merge(ct, on='InsCode', how='left')
# Now you have price data + client type data in one DataFrame!

# Find stocks with strong institutional buying
inst_buy = merged[merged['Net_N_Volume'] > 1_000_000]
print(inst_buy[['Symbol', 'Last', 'Volume', 'Net_N_Volume', 'Net_I_Volume']])
```

---

### `list_options()`

List all active option contracts from the live market. Automatically parses option names to extract structured metadata (type, underlying, strike, expiry).

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `list_options()`

تابع `list_options()` لیست تمام **اختیارمعامله‌های فعال** بازار را برمی‌گرداند و نام اختیارمعامله را به‌صورت خودکار تجزیه می‌کند.

**خروجی:** دیتافریم شامل تمام قراردادهای اختیار خرید و فروش فعال بازار

**پارامترها:**

| پارامتر | پیش‌فرض | توضیح |
|---|---|---|
| `underlying` | `None` | فیلتر بر اساس نام دارایی پایه (مثلاً `'اهرم'`) |
| `progress` | `True` | نمایش گزارش پیشرفت |

**ستون‌های خروجی:**

| ستون | توضیح |
|---|---|
| `OptionType` | نوع: `'call'` (اختیار خرید) یا `'put'` (اختیار فروش) |
| `Underlying` | نام دارایی پایه |
| `Strike` | قیمت اعمال |
| `ExpiryJalali` | تاریخ سررسید شمسی |
| `DaysToExpiry` | روزهای باقیمانده تا سررسید |

</div>

```python
att.list_options(
    underlying=None,   # str or None — filter by underlying name (e.g. 'اهرم')
    progress=True,     # bool — show progress messages
)
```

```python
# All active options
options = att.list_options()
print(options.shape)
```
```
Calls: 757, Puts: 716
Unique underlyings (20): ['اخابر', 'اهرم', 'تاصيكو', 'جهش', 'خبهمن', 'خساپا',
       'خودران', 'خودرو', 'خگستر', 'ذوب', 'شستا', 'شپنا',
       'فارس', 'فملي', 'فولاد', 'هم تراز', 'وبصادر', 'وبملت', 'وتجارت', 'وغدير']

Sample:
  Symbol OptionType Underlying  Strike ExpiryJalali  DaysToExpiry  Close  Volume
ضهرم1114       call       اهرم   12000   1404/11/29             0  17024     229
ضهرم1115       call       اهرم   13000   1404/11/29             0  16103     536
ضهرم1116       call       اهرم   14000   1404/11/29             0  15407      66
ضهرم1117       call       اهرم   15000   1404/11/29             0  13988     359
ضهرم1118       call       اهرم   16000   1404/11/29             0  13421      73
```

| Column | Type | Description |
|---|---|---|
| Column | Type | Description |
|---|---|---|
| `OptionType` | str | `'call'` or `'put'` |
| `Underlying` | str | Underlying asset name (e.g. `اهرم`) |
| `Strike` | int | Strike price |
| `ExpiryJalali` | str | Expiry date in Jalali (e.g. `1404/11/29`) |
| `ExpiryGregorian` | date | Expiry date in Gregorian |
| `DaysToExpiry` | int | Trading days until expiry |
| `Yesterday` | int | Yesterday's reference price |
| `Change`, `ChangePct` | int/float | Price change and percentage |
| `MaxAllowed`, `MinAllowed` | int | Price limits |
| `Close`, `Last`, `Volume`, `Value`, `TradeCount` | int | Market data from `market_watch` |

```python
# Filter by underlying
ahrm = att.list_options(underlying='اهرم')
print(ahrm[['Symbol', 'OptionType', 'Strike', 'ExpiryJalali', 'Close', 'Volume']])
```

---

### `get_options_chain()`

Get a structured options chain for a specific underlying asset, optionally with Open Interest data from the TSETMC API.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_options_chain()`

تابع `get_options_chain()` **زنجیره اختیارمعامله** یک دارایی پایه خاص را برمی‌گرداند.

**پارامترها:**

| پارامتر | پیش‌فرض | توضیح |
|---|---|---|
| `underlying` | — | نام دارایی پایه (مثلاً `'اهرم'`) |
| `fetch_oi` | `False` | دریافت Open Interest (کندتر — یک درخواست API به ازای هر قرارداد) |
| `progress` | `True` | نمایش گزارش پیشرفت |

**خروجی:** دیکشنری با کلیدهای:
- `calls` — دیتافریم اختیارهای **خرید**
- `puts` — دیتافریم اختیارهای **فروش**
- `underlying_price` — قیمت فعلی دارایی پایه
- `expiry_dates` — لیست تاریخ‌های سررسید

**ستون‌های اضافی با `fetch_oi=True`:**

| ستون | توضیح |
|---|---|
| `OpenInterest` | تعداد موقعیت باز |
| `ContractSize` | اندازه قرارداد |

</div>

```python
att.get_options_chain(
    underlying='اهرم',   # str — underlying asset name
    fetch_oi=False,       # bool — fetch Open Interest (slower, per-contract API call)
    progress=True,        # bool — show progress messages
)
```

Returns a **dict** with the following keys:

| Key | Type | Description |
|---|---|---|
| `calls` | DataFrame | All call option contracts |
| `puts` | DataFrame | All put option contracts |
| `underlying_name` | str | Underlying asset name |
| `underlying_price` | int | Current price of the underlying |
| `expiry_dates` | list | List of unique expiry dates (Jalali) |
| `market_time` | str | Market snapshot timestamp |

```python
chain = att.get_options_chain('اهرم')
print(chain['underlying_price'])  # 29300
print(chain['expiry_dates'])      # ['1404/11/29', '1404/12/26', '1405/01/26', '1405/02/30', '1405/03/27']
print(f"Calls: {len(chain['calls'])}, Puts: {len(chain['puts'])}")  # Calls: 69, Puts: 69
print(chain['calls'][['Symbol', 'Strike', 'Close', 'Volume', 'DaysToExpiry']].head())
```
```
  Symbol  Strike  Close  Volume  DaysToExpiry
ضهرم1114   12000  17024     229             0
ضهرم1115   13000  16103     536             0
ضهرم1116   14000  15407      66             0
ضهرم1117   15000  13988     359             0
ضهرم1118   16000  13421      73             0
```

**With Open Interest** (requires additional API calls per contract):

```python
chain = att.get_options_chain('اهرم', fetch_oi=True)
print(chain['calls'][['Symbol', 'Strike', 'Close', 'OpenInterest', 'ContractSize']].head())
```
```
  Symbol  Strike  Close  OpenInterest  ContractSize
ضهرم1114   12000  17024          3892          1000
ضهرم1115   13000  16103          3575          1000
ضهرم1116   14000  15407          2272          1000
ضهرم1117   15000  13988          2180          1000
ضهرم1118   16000  13421          1618          1000
```

| Extra Column (with `fetch_oi=True`) | Description |
|---|---|
| `OpenInterest` | Open Interest (تعداد موقعیت باز) |
| `ContractSize` | Contract size (اندازه قرارداد) |
| `BeginDate` | Contract begin date |
| `EndDate` | Contract end date |

---

### `list_etfs()`

List all active ETFs (Exchange-Traded Funds) with NAV and discount/premium calculation.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `list_etfs()`

تابع `list_etfs()` لیست تمام **صندوق‌های ETF** فعال بازار را با محاسبه تخفیف/حباب NAV برمی‌گرداند.

**ستون‌های اضافی:**

| ستون | توضیح |
|---|---|
| `NAV` | ارزش خالص دارایی هر واحد |
| `NAV_Discount` | درصد تخفیف/حباب: `(پایانی − NAV) / NAV × 100` — منفی = تخفیف، مثبت = حباب |

**کاربردها:**
- شناسایی صندوق‌های با **تخفیف بالا** (فرصت خرید)
- شناسایی صندوق‌های با **حباب** (ریسک بالا)
- مقایسه NAV و قیمت بازار

</div>

```python
att.list_etfs(
    progress=True,   # bool — show progress messages
)
```

```python
etfs = att.list_etfs()
print(etfs.shape)
print(etfs[['Symbol', 'Close', 'NAV', 'NAV_Discount', 'Volume']].head(10))
```
```
  Symbol  Close   NAV NAV_Discount    Volume
پاسارگاد  14290 14292        -0.01 733611397
    آوند  25146 25190        -0.17 718737652
    كارا  30540 30495         0.15 511193722
  اركيده  16122 16058          0.4 339753042
   ياقوت  38927 38861         0.17 329479400
   توسكا  20080 20095        -0.07 316921179
   افران  44391 44355         0.08 277853594
   لبخند  25446 25425         0.08 276491840
    هماي  10259 10248         0.11 205012592
    اهرم  29850 34792        -14.2 197467929
```



| Column | Type | Description |
|---|---|---|
| `NAV` | int64 | Net Asset Value per share (ارزش خالص دارایی) |
| `NAV_Discount` | float64 | `(Close − NAV) / NAV × 100` — negative = discount, positive = premium |
| All `market_watch` columns | — | Full market data (Close, Last, Volume, etc.) |

> **Note:** NAV is parsed from `get_market_snapshot()` data and is broadcast by TSETMC for ETFs. For non-ETF instruments, NAV is 0. Not all ETFs have a non-zero NAV value.

---

### `list_bonds()`

List all active bonds (اوراق مرابحه) and treasury bills (اسناد خزانه) with maturity date parsing.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `list_bonds()`

تابع `list_bonds()` لیست تمام **اوراق مرابحه** و **اسناد خزانه** فعال بازار را با تجزیه تاریخ سررسید برمی‌گرداند.

**ستون‌های اضافی:**

| ستون | توضیح |
|---|---|
| `BondType` | نوع اوراق: `'murabaha'` (مرابحه)، `'ijara'` (اجاره) یا `'treasury'` (خزانه) |
| `Ticker` | نماد کوتاه (مثلاً `اراد1754`، `اخزا4024`) |
| `MaturityJalali` | تاریخ سررسید شمسی |
| `DaysToMaturity` | روزهای باقیمانده تا سررسید |

**نحوه تجزیه سررسید:**
- **مرابحه:** از `ش.خ060327` تاریخ `1406/03/27` استخراج می‌شود
- **خزانه:** ۶ رقم آخر قبل از پرانتز (مثلاً `070614` → `1407/06/14`)
- **اجاره:** بر اساس کلمه `اجاره` در نام ابزار شناسایی می‌شود

**انواع اوراق:** مرابحه، اجاره، خزانه

**کاربردها:**
- مشاهده **سررسید نزدیک** اوراق
- مقایسه بازدهی اوراق بر اساس **روزهای باقیمانده**
- شناسایی اوراق **نزدیک به سررسید** (فرصت آربیتراژ)
- فیلتر بر اساس **نوع اوراق** (مرابحه، اجاره، خزانه)

</div>

```python
att.list_bonds(
    progress=True,   # bool — show progress messages
)
```

```python
bonds = att.list_bonds()
print(bonds.shape)
print(bonds[['Symbol', 'Ticker', 'BondType', 'MaturityJalali', 'DaysToMaturity', 'Close']])
```
```
  Symbol     Ticker BondType MaturityJalali  DaysToMaturity    Close
 اراد235    اراد235 murabaha     1406/09/15             656   837740
كارون072  كارون072  murabaha     1407/05/20             904  1000000
 اخزا210   اخزا210 treasury     1405/11/12             348   726120
 اخزا402   اخزا402 treasury     1407/06/14             929   425000
ايرتور07  ايرتور07    ijara     1407/10/15            1051  1000000
 تابان15   تابان15    ijara     1406/12/22             753  1000000
```

Bond types: `murabaha` (مرابحه), `ijara` (اجاره), `treasury` (خزانه)

| Column | Type | Description |
|---|---|---|
| `BondType` | str | `'murabaha'` (مرابحه), `'ijara'` (اجاره), or `'treasury'` (خزانه) |
| `Ticker` | str | Short ticker from parenthetical (e.g. `اراد1754`, `اخزا4024`) |
| `MaturityJalali` | str | Maturity date in Jalali (e.g. `1406/03/27`) |
| `MaturityGregorian` | date | Maturity date in Gregorian |
| `DaysToMaturity` | int | Days until maturity |
| All `market_watch` columns | — | Full market data (Close, Last, Volume, etc.) |

#### Bonds expiring soon

```python
# Find bonds/treasury bills expiring within 90 days
soon = bonds[bonds['DaysToMaturity'] < 90]
print(soon[['Symbol', 'Ticker', 'BondType', 'MaturityJalali', 'DaysToMaturity', 'Close']])
```
```
  Symbol   Ticker BondType MaturityJalali  DaysToMaturity    Close
 اخزا208  اخزا208 treasury     1404/12/11              12   997710
اخزا2084 اخزا2084 treasury     1404/12/11              12   989017
 اراد184  اراد184 murabaha     1404/12/24              25   991510
  مقدم05   مقدم05 murabaha     1405/02/01              62  1000000
 اراد904  اراد904 murabaha     1405/02/17              78   971110
```

> **Maturity parsing:** Bond names contain `ش.خ{YYMMDD}` where `YYMMDD` maps to `14YY/MM/DD`. Treasury names have the maturity date as the last 6 digits before the parenthetical ticker. Ijara bonds (اجاره) are identified by the keyword `اجاره` in the instrument name.

---

### `list_funds()`

List all investment funds with detailed NAV, returns, portfolio composition and manager info.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `list_funds()`

تابع `list_funds()` اطلاعات کامل **تمام صندوق‌های سرمایه‌گذاری** را از API رسمی TSETMC دریافت می‌کند — شامل NAV، بازدهی، ترکیب پرتفوی، مدیر صندوق و متولی.

**دسته‌بندی صندوق‌ها:**

| نوع | پارامتر | توضیح |
|---|---|---|
| صندوق سهامی | `'equity'` | سرمایه‌گذاری در سهام |
| صندوق درآمد ثابت | `'fixed_income'` | سپرده و اوراق با سود تضمینی |
| صندوق مختلط | `'mixed'` | ترکیب سهام و اوراق |
| صندوق بازارگردانی | `'market_maker'` | بازارگردانی نمادها |
| صندوق جسورانه | `'venture'` | سرمایه‌گذاری خطرپذیر |
| صندوق پروژه | `'project'` | مبتنی بر پروژه |
| صندوق زمین و ساختمان | `'real_estate'` | املاک و مستغلات |
| صندوق کالایی | `'commodity'` | طلا، نقره، زعفران |
| صندوق خصوصی | `'private'` | سرمایه‌گذاری خصوصی |
| ابر صندوق | `'fund_of_funds'` | صندوق در صندوق |

**ستون‌های NAV و بازدهی:**

| ستون | توضیح |
|---|---|
| `nav_redemption` | NAV ابطال (هر واحد) |
| `nav_subscription` | NAV صدور (هر واحد) |
| `return_1d` / `return_7d` / `return_30d` | بازدهی کوتاه‌مدت (درصد) |
| `return_90d` / `return_180d` / `return_365d` | بازدهی بلندمدت (درصد) |
| `return_inception` | بازدهی از ابتدا (درصد) |

**ستون‌های ترکیب پرتفوی:**

| ستون | توضیح |
|---|---|
| `pct_stock` | درصد سهام |
| `pct_bond` | درصد اوراق |
| `pct_deposit` | درصد سپرده بانکی |
| `pct_cash` | درصد نقد |
| `pct_other` | درصد سایر |
| `pct_top5` | غلظت ۵ دارایی برتر |

**مثال‌ها:**

- `att.list_funds()` → همه صندوق‌ها
- `att.list_funds(fund_type='equity')` → فقط صندوق‌های سهامی
- `att.list_funds(fund_type='commodity')` → صندوق‌های کالایی (طلا، نقره)
- `att.list_funds(fund_type=['equity', 'mixed'])` → سهامی + مختلط

</div>

```python
att.list_funds(
    fund_type=None,     # str or list — fund category filter (default: all)
    progress=True,      # bool — show progress messages
)
```

#### All funds

```python
df = att.list_funds()
```
```
                      fund_name    fund_type  reg_no  nav_redemption  nav_subscription  return_365d  pct_stock  pct_bond  pct_deposit       manager
0   آرمان آتیه درخشان مس         equity       11378      569066          573967        50.47       75.10      0.00        15.41   تامین سرمایه تمدن
1   آرمان رایا یکم               equity       12061     2020046         2040493        33.33       96.36      1.75         2.69   سبدگردان رایا سهم
...
```

| Column | Type | Description |
|---|---|---|
| `fund_name` | str | Fund name in Persian |
| `fund_type` | str | Category: `equity`, `fixed_income`, `mixed`, `market_maker`, `venture`, `project`, `commodity`, `private`, `fund_of_funds` |
| `reg_no` | int | Registration number |
| `nav_redemption` | float | NAV for redemption (per unit) |
| `nav_subscription` | float | NAV for subscription (per unit) |
| `nav_statistical` | float | Statistical NAV |
| `net_asset` | float | Total net asset value (Rials) |
| `units` | float | Outstanding units |
| `inception_date` | str | Fund start date (ISO) |
| `return_1d` … `return_365d` | float | Returns at various horizons (%) |
| `return_inception` | float | Return since inception (%) |
| `pct_stock` | float | Equity allocation (%) |
| `pct_bond` | float | Bond allocation (%) |
| `pct_deposit` | float | Bank deposit allocation (%) |
| `pct_cash` | float | Cash allocation (%) |
| `pct_other` | float | Other assets (%) |
| `pct_top5` | float | Top-5 holding concentration (%) |
| `manager` | str | Fund manager name |
| `investment_manager` | str | Investment manager |
| `custodian` | str | Custodian / auditor |
| `guarantor` | str | Guarantor (or None) |
| `market_maker` | str | Market maker (or None) |

#### Filter by fund type

```python
# Equity funds only
equity = att.list_funds(fund_type='equity')

# Fixed income funds
fixed = att.list_funds(fund_type='fixed_income')

# Commodity (gold, silver, saffron)
gold = att.list_funds(fund_type='commodity')

# Multiple types
mix = att.list_funds(fund_type=['equity', 'mixed', 'venture'])
```

#### Top performers

```python
# Best annual return across all funds
df = att.list_funds()
top10 = df.nlargest(10, 'return_365d')[['fund_name', 'fund_type', 'return_365d', 'pct_stock']]
print(top10)
```

#### Portfolio analysis

```python
# Equity funds with highest stock concentration
eq = att.list_funds(fund_type='equity')
high_stock = eq[eq['pct_stock'] > 80].sort_values('return_365d', ascending=False)
print(high_stock[['fund_name', 'pct_stock', 'pct_top5', 'return_365d']])
```

#### Compare NAVs

```python
# All fixed income funds sorted by redemption NAV
fixed = att.list_funds(fund_type='fixed_income')
print(fixed.sort_values('nav_redemption', ascending=False)[['fund_name', 'nav_redemption', 'return_365d', 'net_asset']])
```

---

### `list_indices()`

Get all market indices with their current values — both industry-sector and general market indices.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `list_indices()`

تابع `list_indices()` **تمام شاخص‌های بازار** (شاخص‌های صنایع و شاخص‌های کلی) را با مقادیر لحظه‌ای برمی‌گرداند.

**ستون‌های خروجی:**

| ستون | توضیح |
|---|---|
| `Name` | نام شاخص به فارسی |
| `InsCode` | کد شناسه منحصربه‌فرد |
| `Value` | مقدار فعلی شاخص |
| `High` | بیشترین مقدار امروز |
| `Low` | کمترین مقدار امروز |
| `Change` | تغییر مقدار شاخص |
| `ChangePct` | درصد تغییر |

</div>

```python
att.list_indices(
    progress=True,      # bool — show progress messages
)
```

```python
import algotik_tse as att

indices = att.list_indices()
print(indices.head(10))
```
```
                        Name             InsCode       Value        High         Low     Change  ChangePct
0                  شاخص کل   32097828799138957  3806743.94  3821044.37  3800000.12  -15301.06      -0.40
1            شاخص کل هم وزن   67130298613737946   863421.32   868912.54   862100.00   -5491.22      -0.63
2              27-فلزات اساسی  32453344048876642  4090060.00  4090060.00  3986100.00  -96194.00      -2.36
3                   28-سیمان  70077233737515808    19350.50    19387.20    19200.10     -37.30      -0.19
4   30-محصولات شیمیایی         33626672012415176   142530.00   143200.00   141800.00    -670.00      -0.47
```

```python
# Filter for industry indices
industry = indices[indices['Name'].str.match(r'^\d{2}-')]
print(f"Industry indices: {len(industry)}")

# Find a specific index
metal = indices[indices['Name'].str.contains('فلزات')]
print(metal[['Name', 'Value', 'ChangePct']])
```

---

### `get_index_companies()`

Get the list of companies belonging to a specific industry index.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — `get_index_companies()`

تابع `get_index_companies()` لیست **شرکت‌های عضو** یک شاخص صنعت را برمی‌گرداند.

**ورودی:** نام شاخص صنعت به فارسی — انعطاف‌پذیر:
- نام ساده: `'فلزات اساسی'`، `'بانک'`، `'دارو'`
- با پیشوند شاخص: `'شاخص فلزات اساسی'`
- با پیشوند شاخص صنعت: `'شاخص صنعت فلزات اساسی'`
- با حروف عربی: `'شيميايي'`، `'بانك'` — تبدیل خودکار انجام می‌شود
- با کد مستقیم: `'32453344048876642'`

**۴۵ صنعت پشتیبانی‌شده:** زراعت، ذغال سنگ، استخراج نفت، کانه فلزی، سایر معادن، منسوجات، محصولات چرمی، محصولات چوبی، محصولات کاغذ، انتشار و چاپ، فراورده نفتی، لاستیک، فلزات اساسی، محصولات فلزی، ماشین آلات، دستگاههای برقی، وسایل ارتباطی، ابزار پزشکی، خودرو، حمل و نقل، مبلمان، قند و شکر، چند رشته ای صنعتی، آب/برق/گاز، غذایی، دارویی، شیمیایی، پیمانکاری، خرده فروشی، کاشی و سرامیک، سیمان، کانی غیرفلزی، هتل و رستوران، سرمایه‌گذاری، بانک، سایرمالی، حمل و نقل آبی، رادیویی/مخابرات، مالی، بیمه، اداره بازارهای مالی، انبوه‌سازی، رایانه، اطلاعات و ارتباطات، فنی مهندسی

**ستون‌های خروجی:**

| ستون | توضیح |
|---|---|
| `Symbol` | نماد فارسی (مثلاً `'فولاد'`) |
| `Name` | نام کامل شرکت |
| `InsCode` | کد شناسه نماد |
| `Close` | قیمت پایانی |
| `Yesterday` | قیمت دیروز |
| `Last` | آخرین قیمت معامله |

</div>

```python
att.get_index_companies(
    index_name='فلزات اساسی',  # str — industry name or InsCode
    progress=True,              # bool — show progress messages
)
```

```python
import algotik_tse as att

# By bare name
companies = att.get_index_companies('فلزات اساسی')
print(companies)
```
```
   Symbol                    Name             InsCode   Close  Yesterday   Last
0   فولاد        فولاد مباركه اصفهان   46348559193224090   19990      20510  19780
1   فملی     ملی صنایع مس ایران        35425587644337450   14030      14310  14030
2   کاوه    فولاد کاوه جنوب کیش         7745894403636165   18150      18870  17890
...
```

```python
# Different name formats — all equivalent
att.get_index_companies('بانک')                      # bare alias
att.get_index_companies('شاخص بانکها')               # with شاخص prefix
att.get_index_companies('شاخص صنعت بانکها')          # with شاخص صنعت prefix
att.get_index_companies('بانك')                      # Arabic ك — auto-normalized

# More examples
att.get_index_companies('دارو')                      # Pharmaceutical
att.get_index_companies('سیمان')                     # Cement
att.get_index_companies('شیمیایی')                   # Chemical
att.get_index_companies('رایانه')                    # Computer
att.get_index_companies('32453344048876642')          # By InsCode directly
```

#### Industry index history + member companies

```python
import algotik_tse as att

# Get industry index price history
idx = att.get_history('شاخص صنعت فلزات اساسی', limit=30)
print(idx.tail())

# Get companies in that index
companies = att.get_index_companies('فلزات اساسی')
print(f"\n{len(companies)} companies in Basic Metals index:")
print(companies[['Symbol', 'Close', 'Last']])
```

---

## Legacy Aliases

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — نام‌های قدیمی

برای **سازگاری با گذشته** (backward compatibility)، نام‌های قدیمی توابع همچنان کار می‌کنند. هم نام‌های قدیمی و هم نام‌های جدید به‌طور یکسان عمل می‌کنند و نام‌های قدیمی هرگز حذف نخواهند شد.

</div>

For **backward compatibility**, the original function names are still available as aliases. Both old and new names work identically — the old names will never be removed.

| Standard Name | Legacy Alias | Description |
|---|---|---|
| `get_history()` | `stock()` | Historical price data |
| `get_client_type()` | `stock_RI()`, `stock_RL()` | Retail / institutional data |
| `get_capital_increase()` | `stock_capital_increase()` | Capital increase history |
| `get_intraday()` | `stock_intraday()` | Intraday tick & candle data |
| `get_detail()` | `stockdetail()` | Full stock detail |
| `get_info()` | `stock_information()` | Instrument information |
| `get_stats()` | `stock_statistics()` | Instrument statistics |
| `get_introduction()` | `stock_introduction()` | Company introduction / profile |
| `get_symbols()` | `stocklist()` | List all symbols |
| `get_shareholders()` | `shareholders()` | Major shareholders |
| `get_currency()` | `currency_coin()` | Currency & coin prices |
| `get_market_snapshot()` | `market_watch()` | Live market snapshot |
| `get_market_client_type()` | `market_client_type()` | Bulk individual/institutional |

```python
import algotik_tse as att

# These are identical:
df = att.get_history('شتران', limit=100)
df = att.stock('شتران', limit=100)          # legacy — still works

# Legacy names for all functions:
att.stock_intraday('شتران', interval='4h')    # same as att.get_intraday(...)
att.market_watch()                             # same as att.get_market_snapshot()
att.currency_coin('dollar', limit=30)         # same as att.get_currency(...)
```

### Legacy Parameter Names

<div dir="rtl" align="right">

نام‌های قدیمی پارامترها نیز همچنان پشتیبانی می‌شوند:

</div>

Old parameter names are also still supported for backward compatibility:

| New Name | Old Name | Functions |
|---|---|---|
| `symbol` | `stock` | `get_history()`, `get_client_type()`, `get_capital_increase()`, `get_shareholders()` |
| `name` | `currency_coin_name` | `get_currency()` |
| `limit` | `values` | `get_history()`, `get_client_type()`, `get_currency()` |
| `raw` | `tse_format` | `get_history()`, `get_client_type()` |
| `dropna` | `multi_stock_drop` | `get_history()`, `get_client_type()` |
| `dropna` | `multi_currencies_drop` | `get_currency()` |
| `include_id` | `shh_id` | `get_shareholders()` |
| `output_type='full'` | `output_type='complete'` | `get_history()`, `get_client_type()`, `get_currency()` |

```python
# Old parameter names still work:
df = att.get_history(stock='شتران', values=100, tse_format=True)
# is the same as:
df = att.get_history(symbol='شتران', limit=100, raw=True)
```

---

## Configuration

All settings are accessible via the global `settings` object:

```python
import algotik_tse as att

# SSL verification (default: False)
att.settings.ssl_verify = True

# Request timeout in seconds (default: 10)
att.settings.timeout = 15

# Maximum retry attempts on failure (default: 3)
att.settings.max_retries = 5

# Delay between requests in seconds — prevents TSETMC rate-limiting (default: 0.3)
att.settings.rate_limit_delay = 0.5
```

| Setting | Default | Description |
|---|---|---|
| `ssl_verify` | `False` | Enable/disable SSL certificate verification |
| `timeout` | `10` | Request timeout in seconds |
| `max_retries` | `3` | Maximum retry attempts on HTTP failure |
| `rate_limit_delay` | `0.3` | Delay between consecutive requests (seconds) |

> **Note:** TSETMC may temporarily block your IP if you send too many requests.
> The `rate_limit_delay` setting adds a pause between requests to avoid this.
> If you are downloading data for many symbols, keep this value at `0.3` or higher.

<div dir="rtl" align="right">

#### 📖 توضیحات فارسی — تنظیمات

تنظیمات از طریق شیء سراسری `settings` قابل دسترسی هستند:

| تنظیم | پیش‌فرض | توضیح |
|---|---|---|
| `ssl_verify` | `False` | فعال/غیرفعال کردن تأیید گواهی SSL |
| `timeout` | `10` | زمان انتظار درخواست (ثانیه) |
| `max_retries` | `3` | حداکثر تعداد تلاش مجدد در صورت خطا |
| `rate_limit_delay` | `0.3` | تأخیر بین درخواست‌های متوالی (ثانیه) |

**⚠️ هشدار:** سایت TSETMC ممکن است در صورت ارسال درخواست‌های زیاد، IP شما را مسدود کند.
تنظیم `rate_limit_delay` یک مکث بین درخواست‌ها اضافه می‌کند.
اگر برای نمادهای زیادی داده دانلود می‌کنید، این مقدار را `0.3` یا بیشتر نگه دارید.

</div>

---

## Examples

### Market Screening

<div dir="rtl" align="right">
📖 شناسایی نمادهای پرحجم، بیشترین رشد و بیشترین افت با <code>get_market_snapshot</code>
</div>

```python
import algotik_tse as att

data = att.get_market_snapshot()
stocks = data['stocks']

# Filter real stocks only
real = stocks[stocks['InstrumentType'].isin([300, 303, 309])].copy()

# Top 10 by volume
top_vol = real.nlargest(10, 'Volume')[['Symbol', 'Last', 'ChangePct', 'Volume']]
print(top_vol)
```

<details>
<summary>Output (بیشترین حجم)</summary>

```
 Symbol   Last  ChangePct      Volume
  خودرو    502         -3  4753792093
   ودي4   6988          0  3700000000
  خساپا    515         -0  3631847572
  وبملت   1257         -3  2230874402
وتجارت    407         -4  1025392677
    ذوب    342         -4   595614448
  اخابر    404         -0   435798815
  وساپا   6430         -0   397605094
وبصادر    504         -3   363823141
  شبندر   7540         -4   343240547
```

</details>

```python
# Top 10 gainers / losers
top_gain = real.nlargest(10, 'ChangePct')[['Symbol', 'Last', 'ChangePct', 'Volume']]
top_loss = real.nsmallest(10, 'ChangePct')[['Symbol', 'Last', 'ChangePct', 'Volume']]
print(top_gain)
print(top_loss)
```

<details>
<summary>Output (بیشترین رشد و افت)</summary>

```
# Top 10 gainers:
  Symbol   Last  ChangePct    Volume
آلومينا4 199797         62 319963504
    وپسا   1444          6   9850557
   فبيرا    920          6   2755408
    خفنر   1062          5  11698640
   سفاسي   2595          5   5083029
   وگستر   4645          5   3673013
   ولشرق   3307          5   7461884
   آبادا   7150          4    368174
   آريان   3965          4  12709430
    وآوا   2060          4    308651

# Top 10 losers:
Symbol   Last  ChangePct  Volume
 شكبير 140400         -6   65799
 پلاسك   3629         -6 1229688
 شيراز  60340         -5 3996087
 دشيمي  14810         -5  450580
 پارتا  10900         -5 2287467
غبهنوش  79120         -5   96995
 پاكشو   4499         -5 8029618
 خنصير   2596         -5 3257908
 شسينا   2566         -5 9626376
  شدوص   4400         -5  105105
```

</details>

---

### ETF Discount/Premium Analysis

<div dir="rtl" align="right">
📖 شناسایی صندوق‌های ETF با بیشترین تخفیف یا حباب نسبت به NAV — فرصت‌های آربیتراژ
</div>

```python
import algotik_tse as att

etfs = att.list_etfs()
active = etfs[etfs['NAV'] > 0].copy()
print(f"Total ETFs: {len(etfs)}, with NAV data: {len(active)}")

# Most discounted (buying opportunity)
discounted = active.nsmallest(5, 'NAV_Discount')
print(discounted[['Symbol', 'Close', 'NAV', 'NAV_Discount', 'Volume']])

# Most premium (overvalued)
premium = active.nlargest(5, 'NAV_Discount')
print(premium[['Symbol', 'Close', 'NAV', 'NAV_Discount', 'Volume']])
```

<details>
<summary>Output</summary>

```
Total ETFs: 328, with NAV data: 247

# Top 5 most discounted ETFs (vs NAV):
  Symbol  Close    NAV  NAV_Discount   Volume
دارا يكم 303890 453363           -33  6236158
  پالايش 280500 385211           -27  5522069
   بيدار  20730  25176           -18 85301838
    شتاب  18990  22627           -16 43573177
     جهش  15080  17864           -16 35709297

# Top 5 most premium ETFs (vs NAV):
   Symbol  Close   NAV  NAV_Discount  Volume
  گارانتي  23642 19240            23  496071
      عرش  16039 14293            12  200159
     آسام  44280 39792            11   78547
مالك آتيه  12193 11034            10 5111640
      رخش  20435 18508            10   62216
```

</details>

---

### Currency & Gold Prices

<div dir="rtl" align="right">
📖 دریافت قیمت لحظه‌ای دلار و یورو
</div>

```python
import algotik_tse as att

usd = att.get_currency('dollar', limit=5)
print(usd)

eur = att.get_currency('euro', limit=5)
print(eur)
```

<details>
<summary>Output</summary>

```
# Dollar (last 5 days):
                Open      High       Low     Close
J-Date
1404-11-25 1,621,350 1,621,700 1,583,800 1,583,900
1404-11-26 1,586,600 1,603,700 1,586,300 1,597,300
1404-11-27 1,598,550 1,603,700 1,591,300 1,599,600
1404-11-28 1,599,900 1,629,700 1,599,800 1,608,600
1404-11-29 1,610,300 1,629,700 1,610,300 1,623,350

# Euro (last 5 days):
                Open      High       Low     Close
J-Date
1404-11-25 1,685,200 1,685,200 1,646,000 1,646,100
1404-11-26 1,643,700 1,669,300 1,643,700 1,669,100
1404-11-27 1,670,600 1,692,200 1,670,600 1,682,600
1404-11-28 1,682,700 1,714,000 1,682,700 1,689,700
1404-11-29 1,692,400 1,714,600 1,692,400 1,706,500
```

</details>

---

### Options Overview

<div dir="rtl" align="right">
📖 آمار کلی بازار اختیار معامله — تعداد قراردادها، دارایی‌های پایه و پرمعامله‌ترین آپشن‌ها
</div>

```python
import algotik_tse as att

options = att.list_options()
print(f"Total active options: {len(options)}")
print(f"Unique underlyings: {options['Underlying'].nunique()}")

# Top underlyings by option count
top = options.groupby('Underlying').size().nlargest(10).reset_index(name='Count')
print(top)

# Most traded options today
top_vol = options.nlargest(10, 'Volume')
print(top_vol[['Symbol', 'Underlying', 'OptionType', 'Strike', 'ExpiryJalali', 'Volume', 'Close']])
```

<details>
<summary>Output</summary>

```
Total active options: 1473
Unique underlyings: 20

# Top 10 underlyings by number of options:
Underlying  Count
      اهرم    138
      شستا    133
     خودرو    128
     وبملت    128
       ذوب    126
     خساپا    119
     فولاد     98
       جهش     74
    تاصيكو     56
      فملي     56

# Top 10 most traded options:
  Symbol Underlying OptionType  Strike ExpiryJalali   Volume  Close
ضسپا1138      خساپا       call     500   1404/11/29 12385699      7
ضخود1250      خودرو       call     550   1404/12/06 10291618      5
ضهرم1125       اهرم       call   30000   1404/11/29  3331288    174
ضخود1249      خودرو       call     500   1404/12/06  3270106     21
ضسپا1247      خساپا       call     500   1404/12/26  3085993     37
ضجار1235     وتجارت       call     550   1404/12/19  2591303      1
طخود1249      خودرو        put     500   1404/12/06  2475166     14
طهرم1125       اهرم        put   30000   1404/11/29  2348106    625
ضملت1205      وبملت       call    1300   1404/12/19  1668000     57
طستا1242       شستا        put    1610   1404/12/13  1457739     60
```

</details>

---

### Fund Comparison

<div dir="rtl" align="right">
📖 مقایسه صندوق‌های سهامی و درآمد ثابت — تعداد صندوق‌ها و ستون‌های خروجی
</div>

```python
import algotik_tse as att

# Equity vs Fixed Income funds
equity_funds = att.list_funds(fund_type='equity')
fi_funds = att.list_funds(fund_type='fixed_income')

print(f"Equity funds: {len(equity_funds)}")
print(f"Fixed income funds: {len(fi_funds)}")
print(f"Columns: {list(equity_funds.columns)}")

# Get ALL fund types at once
all_funds = att.list_funds()
print(f"All funds: {len(all_funds)}")
print(all_funds.groupby('fund_type').size())
```

<details>
<summary>Output</summary>

```
Equity funds: 122
Fixed income funds: 165

Columns: ['fund_name', 'fund_type', 'reg_no', 'nav_redemption',
  'nav_subscription', 'nav_statistical', 'net_asset', 'units',
  'inception_date', 'return_1d', 'return_7d', 'return_30d',
  'return_90d', 'return_180d', 'return_365d', 'return_inception',
  'pct_stock', 'pct_bond', 'pct_deposit', 'pct_cash', 'pct_other',
  'pct_top5', 'manager', 'investment_manager', 'custodian',
  'guarantor', 'market_maker']
```

</details>

---

### Bond Maturity Analysis

<div dir="rtl" align="right">
📖 تحلیل سررسید اوراق بدهی — تفکیک بر اساس نوع و نزدیک‌ترین سررسیدها
</div>

```python
import algotik_tse as att

bonds = att.list_bonds()
print(f"Total bonds/sukuk: {len(bonds)}")
print(bonds['BondType'].value_counts())

# 10 bonds with nearest maturity
near = bonds[bonds['DaysToMaturity'] > 0].nsmallest(10, 'DaysToMaturity')
print(near[['Symbol', 'Ticker', 'BondType', 'MaturityJalali', 'DaysToMaturity', 'Close']])
```

<details>
<summary>Output</summary>

```
Total bonds/sukuk: 349

BondType
murabaha    283
ijara        45
treasury     21

# 10 bonds with nearest maturity:
     Symbol      Ticker BondType MaturityJalali  DaysToMaturity   Close
   اخزا2084    اخزا2084 treasury     1404/12/11              11  989017
    اخزا208     اخزا208 treasury     1404/12/11              11  997710
    اراد184     اراد184 murabaha     1404/12/24              24  991510
     مقدم05      مقدم05 murabaha     1405/02/01              61 1000000
    اراد904     اراد904 murabaha     1405/02/17              77  971110
    اخزا201     اخزا201 treasury     1405/03/25             116  898210
   كرمان531    كرمان531 murabaha     1405/03/27             118 1000000
   كرمان532    كرمان532 murabaha     1405/03/27             118 1000000
ماريناسان05 ماريناسان05    ijara     1405/04/05             127 1000000
   اراد1664    اراد1664 murabaha     1405/04/19             141  962402
```

</details>

### Institutional Money Flow

<div dir="rtl" align="right">
📖 خالص خرید و فروش حقوقی — شناسایی نمادهایی که حقوقی‌ها در حال خرید یا فروش هستند
</div>

```python
import algotik_tse as att

ct = att.get_market_client_type()
data = att.get_market_snapshot()

# Merge for symbol names
stocks = data['stocks'][data['stocks']['InstrumentType'].isin([300, 303, 309])][['InsCode', 'Symbol']]
merged = ct.merge(stocks, on='InsCode', how='inner')

# Top institutional buyers & sellers
top_buy = merged.nlargest(10, 'Net_N_Volume')[['Symbol', 'Net_N_Volume']]
top_sell = merged.nsmallest(10, 'Net_N_Volume')[['Symbol', 'Net_N_Volume']]
print(top_buy)
print(top_sell)
```

<details>
<summary>Output</summary>

```
# Top 10 institutional net buyers:
Symbol  Net_N_Volume
 خودرو    2770366877
 خساپا    2082818640
 وبملت     366854539
 شتران     181253875
 شبندر     152961055
 فولاد     146242076
وبصادر     102337120
 ونوين      63769330
  شپنا      58828670
وتجارت      33587581

# Top 10 institutional net sellers:
Symbol  Net_N_Volume
  فاذر    -175200000
وسبحان    -133683202
   ذوب    -123021255
  ورنا     -74580959
  كسرا     -60574000
 اخابر     -58559183
 وساپا     -35444977
  تپكو     -31000000
 شگستر     -22456287
هاي وب     -22145336
```

</details>

---

### All Asset Types Overview

<div dir="rtl" align="right">
📖 نمایش تمام انواع ابزارهای بازار — سهام، حق تقدم، صندوق، اوراق، اختیار، تسهیلات مسکن، کالا و انرژی
</div>

```python
import algotik_tse as att

all_syms = att.get_symbols(
    bourse=True, farabourse=True, payeh=True,
    haghe_taqadom=True, sandogh=True,
    bonds=True, options=True, mortgage=True,
    commodity=True, energy=True
)
print(f"Total instruments: {len(all_syms)}")
print(all_syms['asset_type'].value_counts())
```

<details>
<summary>Output</summary>

```
Total instruments: 5086

asset_type
option       2498
stock         901
bond          728
right         482
fund          321
mortgage       87
commodity      48
energy         21
```

</details>

---

### Intraday Candle Analysis

<div dir="rtl" align="right">
📖 کندل‌های ۵ دقیقه‌ای و ۱ ساعته — مشاهده حرکات قیمت در طول روز
</div>

```python
import algotik_tse as att

# 5-minute candles
candles = att.get_intraday('شتران', interval='5min')
print(f"5-min candles: {len(candles)} rows")
print(candles.tail(5))

# 1-hour candles
candles_1h = att.get_intraday('شتران', interval='1h')
print(candles_1h)
```

<details>
<summary>Output</summary>

```
# 5-min candles (last 5):
                     Open  High   Low  Close    Volume  TradeCount
DateTime
2026-02-19 12:05:00  3916  3916  3916   3916    609524          43
2026-02-19 12:10:00  3916  3916  3916   3916    742435          27
2026-02-19 12:15:00  3916  3916  3916   3916  30783482         293
2026-02-19 12:20:00  3916  3916  3916   3916  39369865         428
2026-02-19 12:25:00  3916  3917  3916   3916  13706189         205

# 1-hour candles:
                     Open  High   Low  Close     Volume  TradeCount
DateTime
2026-02-19 09:00:00  4079  4118  3966   3966   70752848        1993
2026-02-19 10:00:00  3965  3988  3916   3916  163093506        3051
2026-02-19 11:00:00  3916  3916  3916   3916    8004606         330
2026-02-19 12:00:00  3916  3917  3916   3916   85675975        1018
```

</details>

---

### Stock Detail & Shareholders

<div dir="rtl" align="right">
📖 اطلاعات کامل شرکت و سهامداران عمده
</div>

```python
import algotik_tse as att

info = att.get_info('شتران')
holders = att.get_shareholders('شتران')
print(info)
print(holders.head(5))
```

<details>
<summary>Output</summary>

```
# Stock info for شتران:
                                          value
key
lVal18AFC                                شتران
lVal30                         پالايش نفت تهران
lVal18                          Palayesh Tehran
cIsin                            IRO1PTEH0007
flowTitle                          بازار بورس
cgrValCotTitle     بازار اول (تابلوی اصلی) بورس
eps_estimatedEPS                          1018
eps_sectorPE                                 5
zTitad                        539,500,000,000
minYear                                 1,875
maxYear                                 4,938

# Major shareholders (top 5):
                                    share_holder_name  number_of_shares  percentage
0                                   بانك صادرات ايران    32,344,984,668           6
1             شركت سرمايه گذاري ايرانيان -سهامي خاص -    25,693,117,937           5
2 شركت سرمايه گذاري .ا.تهران -سهامي عام --م ك م ف ع -    21,695,397,397           4
3 شركت .س .سهام عدالت .ا.خراسان رضوي -س ع --م ك م ف ع -  20,929,007,165           4
4                          PRXسبد-شرك76894--موس33322-    17,974,075,372           3
```

</details>

---

## Data Sources

| Source | URL | Data |
|---|---|---|
| TSETMC | `old.tsetmc.com` / `cdn.tsetmc.com` | Stock prices, indices, shareholders, capital increases, intraday, market watch |
| TGJU | `api.tgju.org` | Currency & coin prices |

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.rst](CONTRIBUTING.rst) for guidelines.

---

## License

This project is licensed under the **GNU General Public License v3 (GPLv3)**.
See [LICENSE](LICENSE) for the full license text.

---

## Credits

- **Author:** Mohsen Alipour ([alipour@algotik.ir](mailto:alipour@algotik.ir))
- **Website:** [algotik.com](https://algotik.com)
- **Telegram:** [@algotik](https://t.me/algotik)
- Inspired by [finpy-tse](https://github.com/FinPy-TSE/finpy_tse) and tsemodule5
