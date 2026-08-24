# AlgoTik TSE

[![PyPI](https://img.shields.io/pypi/v/algotik-tse.svg?cacheSeconds=300)](https://pypi.org/project/algotik-tse/)
[![Downloads](https://static.pepy.tech/personalized-badge/algotik-tse?period=total&units=international_system&left_color=black&right_color=green&left_text=Downloads)](https://pepy.tech/project/algotik-tse)
[![Python](https://img.shields.io/pypi/pyversions/algotik-tse.svg)](https://pypi.org/project/algotik-tse/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

کتابخانهٔ پایتونی داده و تحلیل بازار سرمایهٔ ایران با تمرکز بر TSETMC. این پکیج دادهٔ تاریخی و زندهٔ قیمت، حقیقی/حقوقی، معاملات، پنج سطح سفارش، صف، پیام و وضعیت بازار، صندوق و اوراق بدهی را دریافت می‌کند و ابزارهای تحلیل اخزا و اختیار معامله را در اختیار پژوهشگر و معامله‌گر الگوریتمی می‌گذارد.

`README.md` سند مرجع واحد پروژه است. مثال‌هایی که به شبکه وابسته‌اند با برچسب «خروجی نماینده» آمده‌اند؛ مقدار واقعی آن‌ها با زمان بازار تغییر می‌کند. مثال‌های ریاضی deterministic هستند و خروجی آن‌ها در تست‌های آفلاین کنترل می‌شود.

> این کتابخانه توصیهٔ سرمایه‌گذاری نیست. timestamp، freshness، partial بودن داده و `DataFrame.attrs` را پیش از تصمیم معاملاتی بررسی کنید.

## ویژگی‌ها

- تاریخچهٔ قیمت و حقیقی/حقوقی با تاریخ شمسی/میلادی، تعدیل، بازده، چندنمادی و `include_today=True`
- نمای زندهٔ کل بازار یا یک نماد، قدرت خریدار حقیقی/حقوقی، جریان پول، spread و imbalance سفارش
- معاملات ریز زنده و تاریخی با بودجهٔ درخواست، تشخیص رکورد ابطالی و provenance
- پنج سطح سفارش و صف خرید/فروش زنده و تاریخچهٔ بازسازی‌شده
- watcher افزایشی بازار، پیام‌ها، تغییر وضعیت، breadth و جریان صنایع
- تاریخچهٔ محلی opt-in روی SQLite برای snapshot، event و archive
- EPS و P/E زنده/تاریخی بدون look-ahead و فهرست دقیق صندوق‌های قابل معامله
- رخدادهای تعدیل قیمت با هویت دقیق؛ بدون ساخت DPS از اختلاف قیمت‌ها
- اخزا: YTM، بازده ساده/پیوسته، duration، convexity، DV01 و منحنی بازده زنده/تاریخی
- اختیار معامله: قیمت و Greeks بلک–شولز اروپایی، IV سمت bid/mid/ask، parity، PCR، نقدشوندگی و snapshot history
- APIهای قدیمی قیمت، intraday، اطلاعات نماد، سهامداران، ارز/سکه، ETF، صندوق، اوراق و شاخص‌ها
- ارتباط HTTPS، اعتبارسنجی TLS به‌صورت پیش‌فرض، retry، rate limiting و کنترل سخت redirect/source boundary

## فهرست

- [نصب](#نصب)
- [شروع سریع](#شروع-سریع)
- [قراردادهای مهم داده](#قراردادهای-مهم-داده)
- [حل دقیق هویت نماد](#حل-دقیق-هویت-نماد)
- [قیمت و حقیقیحقوقی؛ تاریخچه و زنده](#قیمت-و-حقیقیحقوقی-تاریخچه-و-زنده)
- [معاملات ریز](#معاملات-ریز)
- [سفارش و صف](#سفارش-و-صف)
- [Watcher و تحلیل کل بازار](#watcher-و-تحلیل-کل-بازار)
- [تاریخچهٔ محلی SQLite](#تاریخچهٔ-محلی-sqlite)
- [فاندامنتال بازار، صندوق و تعدیل قیمت](#فاندامنتال-بازار-صندوق-و-تعدیل-قیمت)
- [اخزا و درآمد ثابت](#اخزا-و-درآمد-ثابت)
- [اختیار معامله](#اختیار-معامله)
- [سایر APIهای بازار](#سایر-apiهای-بازار)
- [تنظیمات و خطاها](#تنظیمات-و-خطاها)
- [فهرست API عمومی و نام‌های قدیمی](#فهرست-api-عمومی-و-نامهای-قدیمی)
- [تست و مشارکت](#تست-و-مشارکت)

## نصب

```bash
pip install algotik-tse
```

برای توسعه:

```bash
git clone https://github.com/mohsenalipour/algotik_tse.git
cd algotik_tse
python -m pip install -e ".[dev]"
```

Python `3.8` تا `3.14` پشتیبانی می‌شود.

## شروع سریع

```python
import algotik_tse as att

# تاریخچهٔ قیمت؛ رفتار قدیمی بدون ردیف زنده حفظ شده است.
prices = att.get_history("فملی", start="1403-01-01", progress=False)

# ردیف امروز فقط با opt-in؛ در زمان بازار می‌تواند آخرین مشاهدهٔ همین لحظه باشد.
prices_today = att.get_history(
    "فملی", limit=20, include_today=True, progress=False
)

# نمای زندهٔ یک نماد و قدرت حقیقی/حقوقی
live = att.get_live_symbol("فملی", fallback="none")
print(live[["Symbol", "Last", "Close", "IndividualPower", "EstimatedNetIndividualFlow"]])

# پنج سطح سفارش و صف
book = att.get_order_book("فملی")
queue = att.get_queue("فملی", side="both", strict=True)

# معاملات امروز و چند روز تاریخی
today_trades = att.get_live_trades("فملی")
trades = att.get_trades("فملی", start="1403-05-01", end="1403-05-03")

# اخزا و منحنی بازده
treasuries = att.get_treasury_yields(min_volume=1)
curve = att.get_yield_curve(min_nodes=3)

# بازار اختیار و تحلیل زنجیره
options = att.get_option_market(underlying="خودرو")
analytics = att.analyze_option_chain(options, risk_free_rate=0.30)
```

خروجی نمایندهٔ `get_live_symbol` در زمان بازار:

```text
  Symbol   Last  Close  IndividualPower  EstimatedNetIndividualFlow
0   فملی  74200  73950             1.31          2.84e+10
```

ستون‌های `Last` و `Close` در feed زنده به‌ترتیب «آخرین معامله» و «قیمت پایانی» هستند؛ این قرارداد با نام‌گذاری تاریخچه در بخش بعد توضیح داده شده است.

## قراردادهای مهم داده

### نوع خروجی

همهٔ خروجی‌ها DataFrame نیستند:

| خانواده | نوع خروجی |
|---|---|
| قیمت، حقیقی/حقوقی، trades، order book، fundamentals و فهرست ابزارها | `pandas.DataFrame` یا در APIهای legacy گاهی `None` هنگام خطا |
| `market_watch()` / `get_market_snapshot()` | `dict` شامل `stocks`، `order_book`، metadata و زمان مشاهده |
| `get_options_chain()` | `dict` شامل `calls` و `puts` |
| `resolve_instrument()` | شیء immutable از نوع `InstrumentRef` |
| `watch_market()` / `MarketWatcher` | iterator از `MarketEvent` |
| `get_yield_curve()` / `build_yield_curve()` | شیء `YieldCurve` |
| توابع Black–Scholes | عدد، tuple یا `dict` مطابق تابع |

برای DataFrameهای جدید، خروجی خالی همان columns و dtypes خروجی غیرخالی را نگه می‌دارد. metadataهای مهم مانند منبع، freshness، پوشش، partial بودن و بودجهٔ درخواست در `df.attrs` قرار می‌گیرند:

```python
df = att.get_live_market("فملی")
print(df.attrs)
```

```text
{
  'trade_date': datetime.date(...),
  'exchange_time': '12:28:41',
  'fetched_at': Timestamp(..., tz='Asia/Tehran'),
  'is_realtime_fresh': True,
  'is_partial': False,
  'missing_selectors': []
}
```

### قیمت پایانی و آخرین معامله

- در feed زنده: `Last` آخرین قیمت معامله و `Close` قیمت پایانی TSETMC است.
- در تاریخچهٔ سهام: `Close` آخرین قیمت معاملهٔ روز است؛ `Final` قیمت پایانی است و فقط در `output_type="full"` دیده می‌شود.
- با `auto_adjust=True` (پیش‌فرض)، OHLC و `Final` در صورت حضور، تعدیل‌شده‌اند.
- با `auto_adjust=False`، `Close` و `Final` خام‌اند و `Adj Close` نیز ارائه می‌شود.
- هنگام `include_today=True`، `Last` زنده به `Close` تاریخچه و `Close` زنده به `Final` تاریخچه نگاشت می‌شود. بنابراین صرفاً بر اساس نام ستون بین live و history join نزنید.

### تاریخ، ردیف امروز و freshness

- `start` و `end` شامل دو سر بازه‌اند و تاریخ ISO شمسی (`1403-05-01`) یا میلادی (`2024-07-22`) می‌پذیرند.
- رفتار قبلی حفظ شده است: `include_today=False` هیچ درخواست زندهٔ اضافه‌ای انجام نمی‌دهد.
- `include_today=True` فقط observation معتبر همان روز معاملاتی را append/replace می‌کند. snapshot قدیمی همان روز ممکن است برای تکمیل تاریخچه پذیرفته شود ولی `live_is_realtime_fresh=False` خواهد داشت.
- توقف نماد، نبود معامله، نبود هویت قطعی یا شکست live باعث جعل ردیف امروز نمی‌شود؛ تاریخچهٔ موفق برمی‌گردد و هشدار/attrs دلیل را نشان می‌دهند.
- history محلی فقط از زمان ضبط شما پوشش دارد و backfill ادعا نمی‌کند. تاریخچهٔ server-side مانند price/trades/order-book قرارداد جداگانه دارد.

تقارن API زنده/تاریخی:

| داده | زنده | تاریخی |
|---|---|---|
| قیمت و نمای نماد | `get_live_symbol`, `get_live_market` | `get_history(include_today=...)` |
| حقیقی/حقوقی | `get_live_market`, `get_market_client_type` | `get_client_type(include_today=...)` |
| معاملات ریز | `get_live_trades` | `get_trades` |
| پنج سطح سفارش | `get_order_book` | `get_order_book_history` |
| صف | `get_queue` | `get_queue_history` |
| فاندامنتال snapshot | `get_market_fundamentals` | `get_market_fundamentals_history` |
| اخزا و YTM | `get_treasury_yields` | `get_treasury_yield_history` |
| منحنی بازده | `get_yield_curve` | `get_yield_curve_history` |
| اختیار | `get_option_market` | `get_option_history` و snapshotهای `save_option_snapshot` / `load_option_snapshots` |
| overview/breadth/sector/message/state | helperهای live متناظر | helperهای `*_history` پس از `archive_to` یا snapshot |

تقارن به معنی یکسان‌بودن منبع نیست: بعضی historyها server-side هستند و بعضی فقط observationهای ذخیره‌شدهٔ کاربر را می‌خوانند. `Source`, `NoBackfill` و coverage را بررسی کنید.

### ذخیره در CSV

در APIهای تاریخی legacy، `save_path` **مسیر پوشه** است، نه نام فایل. نام فایل از نماد/دارایی ساخته می‌شود:

```python
att.get_history(
    "فملی", save_to_file=True, save_path="exports", progress=False
)
# exports/فملی.csv
```

### source boundary

درخواست‌های runtime فقط به providerهای پشتیبانی‌شدهٔ TSETMC، صفحهٔ مرجع YTM فرابورس ایران (`ifb.ir`) و API قدیمی ارز/سکهٔ TGJU محدودند. redirect به origin دیگر پیش از درخواست دوم رد می‌شود. هیچ API کدال در این پکیج وجود ندارد.

TSETMC برای رخداد تعدیل قیمت، DPS قطعی و قابل استناد منتشر نمی‌کند. اختلاف قیمت تعدیل‌شده و تعدیل‌نشده **معادل سود نقدی نیست** و کتابخانه از آن DPS استنتاج نمی‌کند.

## حل دقیق هویت نماد

نمادهای تکراری، ابزار منقضی، حق‌تقدم، اختیار و اوراق می‌توانند نام مشابه داشته باشند. APIهای جدید از `InstrumentRef` و `InsCode` استفاده می‌کنند:

```python
ref = att.resolve_instrument("فملی", asset_type="equity")
print(ref)
```

خروجی نماینده:

```text
InstrumentRef(
    ins_code='35425587644337450', symbol='فملی',
    name='ملی صنایع مس ایران', asset_type='equity',
    is_active=True, provenance='tsetmc_search_exact', selector='فملی'
)
```

برای اجرای قطعی در production، `ins_code` بدهید:

```python
prices = att.get_history(
    ins_code="35425587644337450", asset_type="equity", progress=False
)
live = att.get_live_symbol(ins_code="35425587644337450")
```

`validate_ins_code()` عدد صحیح مثبت دقیق یا رشتهٔ ۱ تا ۲۰ رقم ASCII را می‌پذیرد و نتیجه را به‌صورت رشته برمی‌گرداند؛ `float`، `bool`، رقم فارسی/عربی، صفر و مقدار مبهم پذیرفته نمی‌شوند. اگر selector بیش از یک نتیجهٔ معتبر داشته باشد، کتابخانه حدس نمی‌زند:

```python
try:
    att.resolve_instrument("نماد تکراری")
except att.AmbiguousSymbolError as exc:
    print(exc)
```

```text
AmbiguousSymbolError: selector matched more than one instrument; pass ins_code
```

گزینه‌های اصلی:

```python
att.resolve_instrument(
    selector=None,
    ins_code=None,
    asset_type="auto",
    snapshot=None,
    require_active=True,
)
```

- `snapshot` امکان resolve بدون fetch دوباره را می‌دهد.
- `require_active=False` برای تاریخچهٔ ابزار منقضی مناسب است.
- `normalize_instrument_text()` اختلاف `ی/ي`، `ک/ك` و فاصله‌های متداول را یکسان می‌کند، اما fuzzy join هویتی انجام نمی‌دهد.

## قیمت و حقیقی/حقوقی؛ تاریخچه و زنده

### `get_history()`

```python
att.get_history(
    symbol="فملی", start=None, end=None, limit=0,
    raw=False, auto_adjust=True, output_type="standard",
    date_format="jalali", progress=True, save_to_file=False,
    dropna=True, adjust_volume=False, return_type=None,
    ascending=True, save_path=None, include_today=False,
    ins_code=None, asset_type="auto",
)
```

```python
history = att.get_history(
    "فملی", limit=10, include_today=True,
    output_type="full", progress=False,
)
print(history.tail(2))
print(history.attrs["include_today_appended"])
```

خروجی نماینده:

```text
              Open   High    Low  Close  Final   Volume  No.       Value
Date
1405-06-02   73100  74600  72800  74200  73950  1820043  3912  1.35e+11
1405-06-03   74000  74900  73600  74700  74420   814220  1830  6.06e+10
['فملی']
```

در `standard` ستون‌ها `Open, High, Low, Close, Volume` هستند. `full` ستون‌های `Final, No., Value` و اطلاعات تقویم/Ticker را نیز اضافه می‌کند. `raw=True` فرمت TSE را برمی‌گرداند. `return_type` یکی از `simple`، `log`، `both` یا فرم سفارشی مانند `['simple', 'Close', 5]` است. برای چند نماد، DataFrame با MultiIndex ستونی برمی‌گردد.

### `get_client_type()`

```python
client = att.get_client_type(
    "فملی", limit=30, include_today=True,
    output_type="full", progress=False,
)
print(client.tail(1))
```

خروجی نمایندهٔ ردیف امروز:

```text
            No_buy_retail  Vol_buy_retail  No_sell_retail  Vol_sell_retail  Power_retail  Is_partial
Date
1403-05-07           1284         920000             991          701000          1.24        True
```

ردیف امروز volume/count را از `ClientTypeAll` می‌گیرد. valueهای امروز در صورت نیاز با VWAP بازار برآورد می‌شوند و ستون‌های `Value_source` / `Is_estimated` در خروجی opt-in مشخص می‌کنند که مقدار رسمی یا برآوردی است. رفتار پیش‌فرض و schema قدیمی بدون `include_today` تغییر نکرده است.

### live کل بازار و یک نماد

```python
snapshot = att.get_market_snapshot()       # dict سازگار با market_watch()
live_all = att.get_live_market()           # DataFrame ادغام‌شده
live_one = att.get_live_market("فملی")
point = att.get_live_symbol("فملی", fallback="none")
```

`get_live_market()` قیمت، client type و بهترین سفارش‌ها را join می‌کند. ستون‌های کلیدی:

```text
InsCode, Symbol, Name, Last, Close, PreviousClose, Volume, Value,
IndividualBuyVolume, IndividualSellVolume, LegalBuyVolume, LegalSellVolume,
IndividualPower, NetIndividualVolume, EstimatedNetIndividualFlow,
BidPrice1, AskPrice1, Spread, SpreadBps, L1Imbalance, L5Imbalance,
trade_date, exchange_time, fetched_at, is_realtime_fresh, is_partial
```

freshness در `get_live_market()` ستون row-wise است، نه attr عمومی. attrs واقعی برای
audit schema/selection هستند:

```python
print(live_all.attrs.keys())
print(live_all.attrs["missing_selectors"])
```

```text
dict_keys(['field_validity', 'source_schema_presence', 'migration', 'missing_selectors'])
[]
```

`get_live_symbol(..., fallback="none")` در نبود نماد در MarketWatch،
`StockNotFoundError` می‌دهد. `fallback="point"` فقط در آن حالت endpoint نقطه‌ای
TSETMC را امتحان می‌کند؛ ستون `SnapshotSource` دقیقاً یکی از `market_watch` یا
`closing_price_info_fallback` است. `PresentInMarketWatch`, `FallbackReason`,
`IdentityVerified`, `has_trade_today` و `PriceActionable` قابلیت استفادهٔ قیمت را
شفاف می‌کنند.

`get_order_book()` خروجی long پنج‌سطحی دارد:

```text
InsCode Symbol Level BidOrderCount BidVolume BidPrice AskPrice AskVolume AskOrderCount
...     فملی      1            42    180000    74100    74200    124000            31
```

ستون‌های metadata آن شامل `trade_date`, `exchange_time`, `fetched_at`, `snapshot_age_seconds`, `is_realtime_fresh`, `is_stale` و `is_partial` است.

## معاملات ریز

`get_trades()` برای هر روز از endpoint تاریخچهٔ معاملات TSETMC استفاده می‌کند و `get_live_trades()` همان قرارداد را برای روز جاری ارائه می‌دهد:

```python
trades = att.get_trades(
    "فملی",
    start="1403-05-01",
    end="1403-05-03",
    include_canceled=False,
    max_requests=10,
    raw=False,
    progress=False,
)

live_trades = att.get_live_trades(
    ins_code="35425587644337450",
    include_canceled=False,
    max_requests=1,
    progress=False,
)
```

schema استاندارد:

```text
InsCode, Symbol, GregorianDate, JalaliDate, TradeNo, Time, Timestamp,
Price, Volume, Value, Canceled, Source
```

خروجی نماینده:

```text
             TradeNo      Time  Price  Volume      Value  Canceled                         Source
Timestamp
...                 1  09:01:01  50000     100    5000000     False  tsetmc_trade_history_lossless
...                 2  09:01:01  50010      50    2500500     False  tsetmc_trade_history_lossless
```

`raw=True` فیلدهای خام provider مانند `qTitNgJ`, `iSensVarP`, `RawInsCode`, `RawDate` و `RawCanceled` را نیز نگه می‌دارد. attrsهای مهم:

```text
request_count, trade_request_count, max_requests, request_budget_scope,
partial, failures, source_coverage, reconciliation,
resolved_ins_code, resolved_symbol
```

- `max_requests` سقف سخت درخواست‌های trade endpoint است؛ resolver ممکن است هزینهٔ جداگانه داشته باشد و attrs مشخص می‌کند شمارش کل شناخته‌شده است یا نه.
- شکست بخشی از روزها با `partial=True` و جزئیات `failures` برمی‌گردد؛ دادهٔ موجود دور ریخته نمی‌شود.
- mismatch در `InsCode` پاسخ، تاریخ یا فیلدهای عددی با `DataParsingError` رد می‌شود.
- رکورد ابطالی فقط با `include_canceled=True` نگه داشته می‌شود.

## سفارش و صف

### سفارش زنده

```python
book = att.get_order_book("فملی")
queue = att.get_queue("فملی", side="both", strict=True)
```

`get_queue()` صف را سه‌حالته گزارش می‌کند؛ نبود شواهد کافی `NA` است، نه `False` قطعی. `strict=True` قیمت صف را با دامنهٔ مجاز و state بازار تطبیق می‌دهد.

```text
InsCode Symbol Side QueuePrice QueueVolume QueueOrders QueueValue
...     فملی   buy       73500      820000         163  6.027e+10

is_queue=True, is_strict=True, is_partial=False,
threshold_source='market_watch_price_limits', book_source='market_watch_live_snapshot'
```

### تاریخچهٔ پنج سطح سفارش

```python
books = att.get_order_book_history(
    "فملی",
    limit=20,
    output_type="standard",   # long؛ یک ردیف در هر level
    include_today=True,
    complete_only=True,
    max_requests=25,
    progress=False,
)

wide = att.get_order_book_history(
    "فملی", limit=10, output_type="wide", max_requests=25, progress=False
)
```

دادهٔ تاریخی `BestLimits` یک delta stream روزانه است. کتابخانه state هر روز را مستقل و به ترتیب `hEven/refID` بازسازی می‌کند؛ مقدار صفر پاک‌شدن level است. schema long:

```text
InsCode, Symbol, Name, Date, GregorianDate, JalaliDate, Time, Timestamp,
DEven, hEven, refID, _sequence, Level,
BidOrderCount, BidVolume, BidPrice, AskPrice, AskVolume, AskOrderCount,
is_partial, is_complete, market_partial_status, is_reconstructed,
is_stale, record_type, source
```

خروجی نماینده:

```text
Timestamp                 Level BidPrice BidVolume AskPrice AskVolume is_complete source
2024-07-22 09:05:01+03:30     1    74100    180000    74200    124000        True tsetmc_best_limits_history_reconstructed
2024-07-22 09:05:01+03:30     2    74050     95000    74250     88000        True tsetmc_best_limits_history_reconstructed
```

`complete_only=True` snapshot ناقص را حذف می‌کند. `include_today=True` snapshot زندهٔ معتبر را با source برابر `market_watch_live_snapshot` اضافه یا جایگزین می‌کند. `max_requests` سقف سخت است و `attrs['failed_requests']` و `attrs['request_count']` پوشش ناقص را توضیح می‌دهند.

نام `get_orderbook_history` alias عینی `get_order_book_history` است.

### تاریخچهٔ صف

```python
queues = att.get_queue_history(
    "فملی",
    limit=20,
    include_today=True,
    complete_only=True,
    side="both",
    strict=True,
    max_requests=25,
    progress=False,
)
```

schema:

```text
InsCode, Symbol, Name, Date, GregorianDate, JalaliDate, Time, Timestamp,
DEven, hEven, Side, QueuePrice, QueueVolume, QueueOrders, QueueValue,
PriceLimit, is_strict, is_queue, is_partial, is_complete,
market_partial_status, book_state, is_crossed, is_preopen_or_stopped,
threshold_hEven, threshold_source, book_source, source
```

اگر static threshold تاریخی در دسترس نباشد، `threshold_source='unavailable'` و `is_queue=NA` می‌ماند. این رفتار برای backtest مهم است: نبود داده به «صف نبود» تبدیل نمی‌شود.

## Watcher و تحلیل کل بازار

### iterator بازار

```python
for event in att.watch_market(
    symbol="فملی",
    interval=2,
    max_updates=5,
    notifications=("messages", "state"),
):
    print(event.kind, event.sequence, event.fetched_at, event.changed_inscodes)
```

`MarketEvent.kind` یکی از `initial`, `delta`, `heartbeat`, `resync` است. `kind="update"` وجود ندارد. event شامل snapshot، فهرست InsCodeهای تغییرکرده، levelهای تغییرکرده، cursor، retry و وضعیت persistence است.

برای کنترل کامل:

```python
watcher = att.MarketWatcher(
    symbol=None,
    interval=2,
    max_updates=None,
    include_initial=True,
    emit_heartbeats=True,
    notifications=("messages", "state"),
    notification_top=50,
    error_policy="retry",
    max_consecutive_retries=5,
    max_backoff=30,
    callback_error_policy="raise",
)
```

Watcher از `MarketWatchInit/Plus` استفاده می‌کند، cursor را نگه می‌دارد و در قطع ارتباط با backoff محدود resync می‌شود. notificationها فقط `messages` و `state` هستند.

### پیام، وضعیت و نمای بازار

```python
messages = att.get_market_messages(flow=0, top=20, since_id=None)
states = att.get_instrument_state_changes(top=20, since_id=None)
overview = att.get_market_overview(flow=0)
```

schema پیام:

```text
message_id, date, time, timestamp, title, description, flow
```

schema وضعیت:

```text
event_id, date, time, timestamp, InsCode, Symbol, Name,
state_code, state, real_time, under_supervision, state_title
```

`get_market_overview()` فیلدهای raw رسمی overview را با ستون `flow` برمی‌گرداند؛ مجموعهٔ ستون‌ها به payload رسمی provider وابسته است و به تعداد ثابتی از ستون‌ها متعهد نیست.

### breadth و جریان صنایع

```python
breadth = att.get_market_breadth(traded_only=True)
sectors = att.get_sector_flow(traded_only=True)
```

خروجی نمایندهٔ breadth:

```text
 instrument_count advances declines unchanged ad_difference ad_ratio total_volume upper_limit_count lower_limit_count
              612      318      241        53            77     1.32   8.91e+09                42                18
```

ستون‌های breadth علاوه بر موارد بالا شامل `no_trade`, `missing_previous`, `missing_current_price`, درصد صعود/نزول، `total_value`, `trade_date`, `exchange_time`, `fetched_at`, `is_realtime_fresh` است.

`get_sector_flow()` همین breadth را برای هر `SectorCode` همراه با پوشش حقیقی/حقوقی ارائه می‌کند:

```text
SectorCode instrument_count advances declines client_coverage net_individual_volume estimated_net_individual_value value_method is_stale
      27               43       25       13            0.91              820000                     5.8e+10 market_vwap    False
```

`estimated_net_individual_value` برآورد است؛ `value_available`, `value_method`, `client_coverage` و freshness را در استراتژی لحاظ کنید.

فیلترهای مشترک عبارت‌اند از `symbol`, `flow`, `sector`, `traded_only`, `include_base_market` و `instrument_types`. برای محاسبهٔ چند خروجی روی یک مشاهده، snapshot را یک‌بار دریافت و به مسیر خصوصی `_snapshot` ندهید؛ API عمومی `save_market_snapshot()` یک snapshot اتمیک می‌سازد و history derivationها را هم‌زمان نگه می‌دارد.

## تاریخچهٔ محلی SQLite

ذخیره‌سازی کاملاً opt-in است؛ بدون path صریح هیچ فایلی نوشته نمی‌شود.

### snapshotهای بازار

```python
db = "market-history.sqlite"

snapshot_id = att.save_market_snapshot(db)
history = att.load_market_snapshots(db, symbol="فملی", limit=500)

# alias معنایی برای همان نمای live ذخیره‌شده
live_history = att.get_live_market_history(db, symbol="فملی", limit=500)
breadth_history = att.get_market_breadth_history(db, limit=100)
sector_history = att.get_sector_flow_history(db, limit=100)
overview_history = att.get_market_snapshot_summary_history(db, limit=100)
```

خروجی نماینده:

```text
AsOf                         InsCode Symbol Last Close Volume NoBackfill SnapshotAtomic
2026-08-25 10:11:12+03:30   ...     فملی  74200 73950 812200       True           True
```

attrsهایی مانند `CoverageStart`, `CoverageEnd`, `SnapshotFrameAttrs`, `NoBackfill`, `SnapshotAtomic` و `SourceAtomic` محدوده و کیفیت archive را توضیح می‌دهند. SQLite دارای application-id، schema version، transaction و کنترل دیتابیس بیگانه/خراب است.

### `record_to` برای replay eventها

```python
watcher = att.MarketWatcher(
    interval=2,
    max_updates=3,
    record_to=db,
    checkpoint_interval=100,
    record_max_records=10_000,
    record_retention_seconds=7 * 24 * 3600,
    storage_error_policy="raise",
)
for _ in watcher:
    pass

events = att.get_market_event_history(db, kind="delta", limit=1000)
```

اولین event هر session یک checkpoint کامل است؛ deltaها پس از آن replay می‌شوند و pruning فقط از مرز checkpoint معتبر انجام می‌شود. `storage_error_policy="raise"` انتخاب امن پیش‌فرض است. `record_market_event()` برای ثبت مستقیم `MarketEvent` موجود است.

### `archive_to` برای رکوردهای مستقل

`record_to` و `archive_to` دو مسیر مستقل‌اند:

```python
att.get_market_overview(flow=0, archive_to=db)
att.get_market_messages(flow=0, top=20, archive_to=db)
att.get_instrument_state_changes(top=20, archive_to=db)

overview = att.get_market_overview_history(db, flow=0, limit=100)
messages = att.get_market_messages_history(db, flow=0, limit=100)
states = att.get_instrument_state_changes_history(db, symbol="فملی", limit=100)
```

`archive_market_records(path, kind, frame, source=...)` API سطح پایین برای kindهای پشتیبانی‌شده است. selector و `source` بخشی از هویت archive هستند؛ `start/end`, `limit/offset` قبل از pagination در SQL اعمال می‌شوند.

توابع مهم نگهداری:

```python
info = att.check_market_history(db)
att.record_market_event(db, event, session_id="strategy-a")
```

`MARKET_HISTORY_SCHEMA_VERSION` و `MARKET_HISTORY_APPLICATION_ID` برای migration/inspection عمومی‌اند.

## فاندامنتال بازار، صندوق و تعدیل قیمت

### EPS و P/E زنده

```python
fundamentals = att.get_market_fundamentals(
    symbols=["فملی", "شتران"],
    pe_min=None,
    pe_max=None,
    positive_pe=False,   # ردیف unavailable را هم برای audit نگه دار
    strict=False,
    allow_stale=False,
    archive_to="market-history.sqlite",
    max_requests=1,
    progress=False,
)
```

این تابع یک snapshot bulk می‌گیرد و EPS/P/E را از همان مشاهده می‌سازد؛ برای هر نماد سراغ منبع دیگری نمی‌رود. schema ثابت:

```text
InsCode, Symbol, Name, SectorCode, InstrumentType, Close, Last,
EPS, PE, PECalculated, EPSSource, PriceSource, PEStatus,
TradeDate, ExchangeTime, AsOf, SnapshotAgeSeconds,
IsRealtimeFresh, IsStale, Source, NoLookahead
```

خروجی نماینده:

```text
Symbol Close   EPS    PE PECalculated EPSSource               PriceSource PEStatus     NoLookahead
فملی   73950  7395  10.0          True market_watch           Close       ok           True
شتران  42100  <NA>  <NA>          True missing_in_market_watch Close      eps_missing  True
```

EPS صفر/خالی به مقدار جعلی تبدیل نمی‌شود. `PEStatus` یکی از `ok`,
`price_missing`, `price_nonfinite`, `price_nonpositive`, `eps_missing`,
`eps_nonfinite`, `eps_nonpositive` است؛ stale بودن در `IsStale` جداست.
`positive_pe=True` فقط P/E مثبت را نگه می‌دارد و `strict=True` selector مفقود
را به خطا تبدیل می‌کند. snapshot stale با `allow_stale=False` exception نیست:
خروجی تهی و `attrs['stale_rejected']=True` می‌شود. attrs زنده دقیقاً شامل
`request_count,max_requests,missing_selectors,strict,stale_rejected,source,price_source,eps_source,no_lookahead,no_backfill,archive_path`
است.

### تاریخچهٔ fundamentals

```python
history = att.get_market_fundamentals_history(
    "market-history.sqlite",
    start="1403-05-01",
    end="1403-05-07",
    symbols="فملی",
    limit=1000,
)
print(history.attrs["no_lookahead"], history.attrs["current_eps_used"])
```

```text
AsOf                         Symbol Close  EPS   PE  EPSSource    Source                  NoLookahead
2026-08-24 10:00:00+03:30   فملی   73500 7350 10.0 market_watch local_market_snapshot   True
2026-08-25 10:00:00+03:30   فملی   74200 7420 10.0 market_watch local_market_snapshot   True
```

این history فقط از snapshotهای ذخیره‌شدهٔ شما ساخته می‌شود:
`attrs['no_backfill']=True` و `attrs['current_eps_used']=False`. attrs دیگر
`missing_selectors,strict,source,price_source,eps_source,no_lookahead,coverage_start,coverage_end`
هستند. EPS فعلی برای گذشته forward-fill نمی‌شود.

### صندوق‌های قابل معامله

```python
listed = att.list_listed_funds(progress=False)
# معادل صریح:
listed2 = att.list_funds(listed_only=True, progress=False)
```

`list_listed_funds()` یک bulk call بازار دارد و join fuzzy با registry صندوق‌ها انجام نمی‌دهد. schema:

```text
InsCode, ISIN, Symbol, Name, Last, Close, Yesterday, Volume, Value,
TradeCount, Low, High, NAV, NAV_Discount, Change, ChangePct, MarketCode
```

```text
Symbol InsCode ISIN          Last Close NAV NAV_Discount Volume
افران  ...     IRO3AFRZ0001  21650 21620 ... ...          1250040
```

attrsهای `no_fuzzy_join=True` و `registry_joined=False` قرارداد هویتی را روشن می‌کنند. `list_funds()` بدون `listed_only` همان API قدیمی registry صندوق‌هاست و ستون/منبع متفاوتی دارد.

### رخدادهای تعدیل قیمت

```python
adjustments = att.get_price_adjustments(
    "فملی", start="1402-01-01", end="1403-12-29", progress=False
)
latest = att.get_latest_price_adjustment("فملی", progress=False)
```

schema ثابت و typed:

```text
InsCode, Symbol, GregorianDate, JalaliDate,
AdjustedClosingPrice, UnadjustedClosingPrice, AdjustmentAmount,
CorporateTypeCode, CorporateActionType, IsConfirmedDPS,
IdentityVerified, Source, FetchedAt
```

خروجی نماینده:

```text
GregorianDate JalaliDate AdjustedClosingPrice UnadjustedClosingPrice AdjustmentAmount CorporateTypeCode CorporateActionType IsConfirmedDPS IdentityVerified
2024-01-01    1402-10-11                 8000                  10000             2000                 7                <NA>          False             True
```

قرارداد مهم:

- `AdjustmentAmount = UnadjustedClosingPrice - AdjustedClosingPrice` فقط اختلاف ریاضی قیمت‌هاست.
- `IsConfirmedDPS` همیشه `False` و `CorporateActionType` nullable است؛ `CorporateTypeCode` خام provider بدون تفسیر نگه داشته می‌شود.
- `attrs['dps_available'] == False` و دلیل در `attrs['dps_reason']` ثبت می‌شود.
- رکورد با InsCode متفاوت رد می‌شود؛ نبود InsCode در خود رکورد با `IdentityVerified=False` و InsCode حل‌شده گزارش می‌شود.
- `get_latest_price_adjustment()` DataFrame صفر یا یک‌ردیفی با همان schema/dtypes/attrs می‌دهد.

```python
assert adjustments["IsConfirmedDPS"].eq(False).all()
assert adjustments.attrs["dps_available"] is False
```

از این API برای ساخت «سری DPS» استفاده نکنید. TSETMC در این endpoint طبقه‌بندی قطعی سود نقدی ارائه نمی‌دهد.

## اخزا و درآمد ثابت

### قاعدهٔ تاریخ در نماد اخزا

شش رقم انتهای نماد به‌صورت تاریخ شمسی `YYMMDD` تفسیر می‌شود؛ دو رقم سال با `13` یا `14` تکمیل می‌شود:

```python
att.parse_treasury_maturity("اخزا020322")
```

```text
{
  'maturity_jalali': '1402/03/22',
  'maturity_gregorian': datetime.date(2023, 6, 12),
  'maturity_source': 'user_confirmed_symbol_jalali_yymmdd'
}
```

```python
att.parse_treasury_maturity("اخزا991117")
```

```text
{
  'maturity_jalali': '1399/11/17',
  'maturity_gregorian': datetime.date(2021, 2, 5),
  'maturity_source': 'user_confirmed_symbol_jalali_yymmdd'
}
```

برای نماد non-match یا تاریخ شمسی نامعتبر، تابع exception نمی‌دهد و `None`
برمی‌گرداند. در صورت تعارض یا نماد غیرقابل‌تفسیر، `maturity_date` یا
`maturity_map` صریح بدهید؛ provenance ستون `MaturitySource` را بررسی کنید.

### محاسبات deterministic

```python
result = att.treasury_yield(
    price=800_000,
    maturity_date="2028-01-01",
    settlement_date="2026-01-01",
    face_value=1_000_000,
)
```

خروجی واقعی این مثال:

```text
EffectiveAnnualYield  0.1180339887
SimpleAnnualYield     0.125
ContinuousYield       0.1115717757
BankDiscountYield     0.0986301370
MacaulayDuration      2.0
ModifiedDuration      1.7888543820
Convexity             4.8
DV01                   143.10835056
DiscountFactor        0.8
Status                ok
```

برای اوراق کوپنی:

```python
cashflows = [
    ("2027-01-01", 80_000),
    ("2028-01-01", 80_000),
    ("2029-01-01", 1_080_000),
]
price = att.bond_price(0.08, cashflows, settlement_date="2026-01-01")
ytm = att.yield_to_maturity(price, cashflows, settlement_date="2026-01-01")
risk = att.bond_analytics(price, cashflows, settlement_date="2026-01-01")
```

`day_count_fraction()` از قراردادهایی مانند `ACT/365F`, `ACT/360`, `30/360` پشتیبانی می‌کند. `bond_price`, `yield_to_maturity` و `bond_analytics` پارامترهای compounding/frequency، clean/dirty price و accrued interest دارند؛ cashflowهای مبهم یا sign-changing رد می‌شوند.

### اخزای زنده

```python
ytm = att.get_treasury_yields(
    symbol=None,
    settlement_date=None,
    face_value=1_000_000,
    include_stale=False,
    min_volume=1,
    price_source="auto",   # auto/bid/ask/last/close
    strict=False,
    source="tsetmc",      # یا hybrid برای join مرجع IFB
)
```

ستون‌های اصلی:

```text
InsCode, ISIN, Symbol, MaturityJalali, Maturity, MaturitySource,
MaturityConflict, SettlementDate, DaysToMaturity, Tenor,
Price, PriceSource, NoTrade, InstrumentPriceAsOf, IsInstrumentStale,
BidPrice, AskPrice, DiscountFactor,
EffectiveAnnualYield, ContinuousYield, SimpleAnnualYield, BankDiscountYield,
MacaulayDuration, ModifiedDuration, Convexity, DV01,
Volume, Value, TradeCount, FaceValue, FaceValueSource,
DayCount, IsStale, SnapshotAgeSeconds, FetchedAt, Status
```

`source="hybrid"` دادهٔ معاملاتی TSETMC را با جدول مرجع مجاز فرابورس ایران در `https://ifb.ir/ytm.aspx` مقایسه می‌کند؛ IFB جای قیمت ابزار را نمی‌گیرد و اختلاف در bps با provenance گزارش می‌شود.

```python
ifb = att.get_ifb_yield_table(category="treasury")
print(ifb.attrs["reference_url"])
```

schema IFB:

```text
Symbol, Price, LastTradeJalali, LastTradeDate, PublishJalali, PublishDate,
MaturityJalali, Maturity, Volume, ReferenceYTM,
ReferenceSimpleYield, ReferenceSource
```

### تاریخچهٔ YTM

```python
history = att.get_treasury_yield_history(
    "اخزا090101",
    limit=20,
    include_today=True,
    price_source="close",
    max_requests=25,
    progress=False,
)
```

`get_treasury_yields_history` alias عینی همین تابع است. هر ردیف از قیمت همان روز ساخته می‌شود و `auto_adjust=False` است؛ قیمت تعدیل‌شده برای YTM مناسب نیست. ستون‌های تاریخچه شامل OHLC، `Close`, `Final`, analytics بالا، `IsPartial`, `FetchedAt`, `Status` و provenance سررسید/قیمت است. `include_today` از همان price-source متناظر live استفاده می‌کند.

### منحنی بازده

```python
curve = att.get_yield_curve(
    min_nodes=3,
    interpolation="log_discount",
    duplicate_policy="volume_weighted",
    extrapolate=False,
)

df_18m = curve.discount_factor(1.5)
zero_18m = curve.zero_rate(1.5)
fwd = curve.forward_rate(1.0, 2.0)
```

`YieldCurve` شامل `settlement_date`, `maturities`, `times`, `discount_factors`, `continuous_zero_rates`, `node_metadata` و `diagnostics` است. `extrapolate=False` جلوی استفادهٔ خارج از دامنه را می‌گیرد.

ساخت مستقیم:

```python
nodes = [
    {"Maturity": "2027-01-01", "DiscountFactor": 0.90},
    {"Maturity": "2028-01-01", "DiscountFactor": 0.80},
    {"Maturity": "2029-01-01", "DiscountFactor": 0.70},
]
curve = att.build_yield_curve(nodes, settlement_date="2026-01-01")
```

`curve.diagnostics` دقیقاً کلیدهای `input_node_count`, `node_count`,
`duplicate_count`, `duplicate_policy` و `monotonic_discount_enforced` را دارد؛
این metadata برای audit ورودی، dedupe و guard نزولی‌بودن discount factor است.

تاریخچهٔ منحنی:

```python
curves = att.get_yield_curve_history(
    limit=10,
    min_nodes=3,
    include_today=True,
    max_requests=50,
    progress=False,
)
```

هر node دارای `CurveID`, `CurveStatus`, `CurveNodeCount`, `CurveInterpolation` و flagهای `CurvePricesNoLookahead`, `CurveUniverseNoLookahead`, `CurveNoLookahead` است. اگر universe تاریخی از catalog امروز بازیابی شود، survivor-bias در diagnostics صریح است و `CurveUniverseNoLookahead=False` می‌شود.

## اختیار معامله

تحلیل‌های قیمت‌گذاری این بخش برای اختیار **اروپایی** هستند. مشخصات واقعی اعمال قرارداد، تعدیلات شرکتی و dividend yield از TSETMC حدس زده نمی‌شود.

### ریاضی Black–Scholes

```python
call = att.black_scholes_price(
    spot=100, strike=100, time_to_expiry=1,
    rate=0.05, volatility=0.20,
    option_type="call", dividend_yield=0.0,
)
greeks = att.black_scholes_greeks(100, 100, 1, 0.05, 0.20, "call")
bounds = att.option_price_bounds(100, 100, 1, 0.05, "call")
iv = att.implied_volatility(10.4505835722, 100, 100, 1, 0.05, "call")
```

خروجی واقعی و deterministic:

```text
call = 10.4505835722

greeks = {
  'Delta': 0.6368306512,
  'Gamma': 0.0187620173,
  'Vega': 37.5240346917,
  'Vega1Pct': 0.3752403469,
  'ThetaPerYear': -6.4140275464,
  'ThetaPerDay': -0.0175726782,
  'Rho': 53.2324815454,
  'Rho100bp': 0.5323248155,
  'Status': 'ok'
}

bounds = (4.8770575499, 100.0)
iv = {'ImpliedVolatility': 0.1999999955, 'Status': 'ok', 'Iterations': 27}
```

واحدها مهم‌اند: `Vega` تغییر قیمت برای یک واحد volatility و `Vega1Pct` برای یک واحد درصد است؛ `ThetaPerYear/Day` و `Rho/Rho100bp` جدا گزارش می‌شوند. خروجی Greeks همیشه کلید `Status` دارد. `implied_volatility()` همواره `dict` می‌دهد و کلیدهای پایهٔ آن `ImpliedVolatility, Status, Iterations` هستند؛ status یکی از `ok`, `missing`, `expiry`, `out_of_bounds`, `no_bracket`, `non_converged` است. out-of-bounds/no-bracket ممکن است `LowerBound/UpperBound` و non-converged مقدار تشخیصی `CandidateVolatility` داشته باشد؛ عدم همگرایی exception نیست. فقط constraintهای ورودی مانند bracket/tolerance/style نامعتبر `ValueError` می‌دهند.

### snapshot اتمیک بازار اختیار

```python
options = att.get_option_market(
    exchange=0,
    underlying="خودرو",
    max_requests=1,
    progress=False,
)
```

هر جفت call/put فقط وقتی metadata کافی و هویت سازگار داشته باشد وارد snapshot می‌شود. ستون‌های اصلی:

```text
InsCode, PairID, PairSequence, ISIN, Symbol, Name, OptionType,
UnderlyingInsCode, UnderlyingSymbol, ContractSize, Strike,
BeginDate, EndDate, DaysToExpiry,
Last, Close, Yesterday, Volume, Value, TradeCount, NotionalValue,
OpenInterest, YesterdayOpenInterest, BidPrice, AskPrice, BidVolume, AskVolume,
UnderlyingLast, UnderlyingClose, Price, PriceSource,
AsOf, AsOfSource, SnapshotFreshnessKnown, PriceFreshnessKnown,
Stale, NoTrade, AnalyticsEligible, AnalyticsEligibilityReason,
MetadataConflict, Source
```

attrsهای `atomic_snapshot`, `duplicate_pairs_dropped`, `incomplete_pairs_quarantined`, `exchange_event_freshness_known` و `malformed_pair_status` کیفیت snapshot را توضیح می‌دهند.

API قدیمی `list_options(underlying=None)` فهرست قراردادها را می‌دهد و
`get_options_chain(underlying, fetch_oi=False)` یک `dict` با کلیدهای دقیق
`calls`, `puts`, `underlying_name`, `underlying_price`, `expiry_dates` و
`market_time` برمی‌گرداند؛ کلید `price` وجود ندارد. برای analytics حرفه‌ای
`get_option_market()` پیشنهاد می‌شود.

### IV، Greeks، parity و نقدشوندگی

```python
analysis = att.analyze_option_chain(
    options=options,
    spot=None,                    # از snapshot اگر معتبر باشد
    risk_free_rate=0.30,          # یا yield_curve=curve
    dividend_yield=0.0,
    valuation_date=None,
    exercise_style="european",
    parity_tolerance=None,
    allow_unverified_freshness=True,
)
```

ستون‌های تحلیلی افزوده‌شده:

```text
TimeToExpiry, Spot, SpotSource, RiskFreeRate, RiskFreeRateSource,
DividendYield, DividendYieldSource,
ImpliedVolatility, ImpliedVolatilityBid, ImpliedVolatilityMid, ImpliedVolatilityAsk,
IVStatus, IVStatusBid, IVStatusMid, IVStatusAsk,
Delta, Gamma, Vega, Vega1Pct, ThetaPerYear, ThetaPerDay, Rho, Rho100bp,
PremiumContract, DeltaContract, GammaContract, VegaContract,
Vega1PctContract, ThetaPerYearContract, ThetaPerDayContract,
RhoContract, Rho100bpContract,
SpreadAbs, SpreadPct, QuotedDepth, LiquidityScore,
ParityResidual, ParityToleranceBand, ParityStatus, ImpliedForward,
GreeksStatus, AnalyticsReliability, AnalyticsWarning, AnalyticsComputed
```

خروجی نماینده:

```text
Symbol OptionType Strike Price ImpliedVolatility Delta Vega1PctContract SpreadPct LiquidityScore ParityStatus AnalyticsReliability
ضخود... call       3000  420.0             0.41   0.62          18320.0      0.03          0.81           ok verified_inputs
طخود... put        3000  265.0             0.39  -0.38          17790.0      0.04          0.76           ok verified_inputs
```

`ParityStatus` فقط diagnostic است و توصیهٔ آربیتراژ نیست؛ محدودیت وجه تضمین، سبک اعمال، کارمزد و امکان معامله را مدل نمی‌کند. اگر `risk_free_rate` ندهید و curve معتبر نداشته باشید analytics قابل اتکا ساخته نمی‌شود. `DividendYieldSource='user_supplied'` فقط زمانی ثبت می‌شود که کاربر مقدار را تعیین کرده باشد؛ مقدار صفر پیش‌فرض به معنی کشف DPS نیست.

### PCR

```python
pcr = att.option_put_call_ratios(analysis, group_by="underlying")
```

```text
UnderlyingInsCode CallVolume PutVolume PCRVolume PCRVolumeStatus CallValue PutValue PCRValue PCRValueStatus CallOpenInterest PutOpenInterest PCROpenInterest PCROpenInterestStatus
65883838195688438      20000     13000      0.65 ok              9.2e9     5.1e9    0.55     ok                         40000           20000            0.50 ok
```

`group_by` دقیقاً یکی از `market`, `underlying`, `expiry` یا
`underlying_expiry` است. خروجی برای هر معیار علاوه بر نسبت، status متناظر
`PCRVolumeStatus`, `PCRValueStatus` و `PCROpenInterestStatus` را می‌دهد؛ نسبت با
denominator صفر nullable و status برابر `zero_denominator` است.

### تاریخچهٔ اختیار و snapshot محلی

```python
# تاریخچهٔ server-side قیمت قرارداد؛ ردیف امروز opt-in
history = att.get_option_history(
    "ضخود...", limit=10,
    include_today=True, max_requests=3, progress=False,
)

# snapshot بازار اختیار فقط با درخواست صریح کاربر روی فایل نوشته می‌شود.
path = "option-snapshots.json"
att.save_option_snapshot(path, options=options)
saved = att.load_option_snapshots(path)
```

schema history:

```text
Timestamp, InsCode, Symbol, Open, High, Low, Close, Last,
Volume, Value, TradeCount, OpenInterest,
BidPrice, AskPrice, BidVolume, AskVolume,
UnderlyingLast, UnderlyingClose, ContractSize, Strike, EndDate,
Price, PriceSource, Source, AsOf, Stale, NoTrade, AnalyticsEligible
```

attrsهایی مانند `prices_no_lookahead`, `underlying_prices_no_lookahead`, `rates_no_lookahead`, `valuation_date_source`, `curve_applied` و `source_coverage` را برای backtest بررسی کنید. فایل snapshot دارای `OPTION_SNAPSHOT_SCHEMA_VERSION`، قفل writer، write اتمیک و dedupe است.

## سایر APIهای بازار

این بخش قابلیت‌های قدیمی را در همان مرجع واحد نگه می‌دارد. APIهای legacy برای backward compatibility در دسترس‌اند و در بسیاری از خطاهای قدیمی `None`/پیام کنسول می‌دهند؛ APIهای جدید بیشتر از exceptionهای typed استفاده می‌کنند.

### intraday

```python
ticks_or_candles = att.get_intraday(
    "فملی",
    interval="1min",       # tick, 1min, 5min, 15min, 30min, 1h, 4h, 12h
    start="1403-05-01",    # حذف start/end برای امروز
    end="1403-05-03",
    progress=False,
)
```

خروجی candle معمولاً `Open, High, Low, Close, Volume` با index زمانی است. `tick` snapshot خام معاملات/قیمت را می‌دهد. interval بزرگ‌تر از دادهٔ پایه resample می‌شود؛ تعطیلی و وقفهٔ بازار را در محاسبه لحاظ کنید.
نام‌های canonical بازه `tick`, `1min`, `5min`, `15min`, `30min`, `1h`, `4h`
و `12h` هستند؛ aliasهای عددی/کوتاه مانند `1m`, `60min`, `4hour`, `240m`,
`12hour`, `720` و نیز `ticks`/`raw` پشتیبانی می‌شوند. این API رفتار legacy دارد:
interval نامعتبر یا تاریخی که validator قدیمی نامعتبر تشخیص دهد را روی کنسول اعلام
می‌کند و `None` برمی‌گرداند، نه اینکه عمداً `ValueError` قراردادشده‌ای بدهد.

### اطلاعات نماد و سهامدار

```python
detail = att.get_detail("فملی")
info = att.get_info("فملی")
stats = att.get_stats("فملی")
shareholders = att.get_shareholders("فملی", include_id=True)
capital = att.get_capital_increase("فملی")
```

- `get_detail()` یک `DataFrame|None` کلید–مقدار با index برابر `key`، ستون `value` و ردیف `id` می‌دهد.
- `get_info()` و `get_stats()` DataFrame کلید–مقدار با index برابر `key` می‌دهند.
- `get_shareholders(date=None)` سهامداران فعلی و با `date` تاریخچهٔ روز را می‌دهد؛ `include_id=True` شناسه را اضافه می‌کند.
- `get_capital_increase()` تاریخچهٔ تغییر تعداد سهام/سرمایه را می‌دهد.
- این توابع `ins_code` و `asset_type` keyword-only را نیز می‌پذیرند.

### معرفی شرکت؛ API قدیمیِ unsupported

`get_introduction()` و `stock_introduction()` فقط برای حفظ import/signature قدیمی مانده‌اند. معرفی ناشر دادهٔ کدال است و خارج از source boundary این پکیج قرار دارد؛ تابع **همیشه پیش از resolver یا شبکه** خطای زیر را می‌دهد:

```python
try:
    att.get_introduction("فملی")
except att.UnsupportedDataSourceError as exc:
    print(exc)
```

```text
UnsupportedDataSourceError: get_introduction/stock_introduction requires Codal data, which is outside algotik-tse's TSETMC market-data source boundary
```

برای اطلاعات TSETMC از `get_info()` و `get_detail()` استفاده کنید. helper افشای ناشر یا history آن در این پکیج وجود ندارد.

### فهرست نمادها و ابزارها

```python
symbols = att.get_symbols(
    bourse=True, farabourse=True, payeh=True,
    haghe_taqadom=False, sandogh=False, bonds=False, options=False,
    mortgage=False, commodity=False, energy=False,
    payeh_color=None, output="dataframe", progress=False,
)

etfs = att.list_etfs(progress=False)
bonds = att.list_bonds(progress=False)
funds = att.list_funds(fund_type="fixed_income", progress=False)
listed_funds = att.list_listed_funds(progress=False)
options = att.list_options(underlying="خودرو", progress=False)
indices = att.list_indices(progress=False)
members = att.get_index_companies("شاخص صنعت بانکها", progress=False)
```

`get_symbols(output="list")` فقط نام نمادها را می‌دهد؛ `dataframe` metadata بازار/نوع ابزار را نگه می‌دارد. `payeh_color` یکی از `زرد`, `نارنجی`, `قرمز` است. برای جلوگیری از universe اشتباه، asset-type flagها را صریح تنظیم کنید.

`list_etfs()` اطلاعات معامله و NAV/discount را می‌دهد. `list_bonds()` metadata اوراق و سررسید را فهرست می‌کند ولی analytics دقیق اخزا در APIهای fixed-income بالاست. `list_funds()` registry صندوق‌هاست؛ `list_listed_funds()` فقط ابزارهای واقعاً قابل معامله در feed بازار را با InsCode/ISIN دقیق می‌دهد.

### شاخص‌ها

```python
index_history = att.get_history("شاخص کل", limit=100, progress=False)
industry_history = att.get_history("شاخص صنعت بانکها", limit=100, progress=False)
members = att.get_index_companies("بانک", progress=False)
```

schema شاخص عمومی و شاخص صنعت می‌تواند با سهام فرق کند؛ شاخص صنعت معمولاً `High, Low, Close` دارد و volume جعلی ساخته نمی‌شود.

### ارز و سکه

این API legacy از TGJU استفاده می‌کند و برای backward compatibility حفظ شده است:

```python
fx = att.get_currency(
    "dollar", start="1403-01-01",
    output_type="standard", date_format="jalali", progress=False,
)

coins = att.get_currency(["seke", "nim-seke"], limit=10, progress=False)
```

نام‌های انگلیسی دقیق:

```text
dollar, euro, yuan, dirham, pound, lira,
dollar-sana-sell, dollar-sana-buy,
dollar-nima-buy, dollar-nima-sell,
dollar-sarafimelli-buy,
seke, seke-bahar-azadi, nim-seke, rob-seke, seke-gerami
```

نام‌های فارسی پشتیبانی‌شده شامل `دلار`, `یورو`, `یوان`, `درهم`, `پوند`, `لیر`, `سکه`, `سکه بهار آزادی`, `نیم سکه`, `ربع سکه`, `سکه گرمی` و صورت‌های سنا/نیما در settings است. spelling کلیدها را دقیق رعایت کنید؛ نام سکه در API انگلیسی `seke` است، نه `sekke`.

خروجی standard ستون‌های `Open, High, Low, Close` دارد. multi-currency یک DataFrame با MultiIndex ستونی می‌دهد. `save_path` در اینجا نیز پوشه است.

## تنظیمات و خطاها

singleton تنظیمات:

```python
from algotik_tse import settings

settings.ssl_verify = True           # پیش‌فرض و توصیه‌شده
settings.timeout = 10                # ثانیه
settings.max_retries = 3
settings.retry_backoff_factor = 0.3
settings.rate_limit_delay = 0.3      # فاصلهٔ حداقل شروع درخواست‌ها

settings.market_snapshot_freshness_seconds = 120.0
settings.market_clock_skew_tolerance_seconds = 5.0
settings.client_volume_consistency_tolerance = 0.05
settings.order_book_max_requests = 250
settings.trade_max_requests = 250
```

TLS verification پیش‌فرض `True` است. opt-out فقط برای محیط کنترل‌شده با CA خراب:

```python
from algotik_tse.http_client import safe_get

response = safe_get("https://cdn.tsetmc.com/...", verify=False)
```

این opt-out را سراسری نکنید. URLهای TSETMC همگی HTTPS هستند.

قرارداد دقیق `safe_get(url, **kwargs)`:

- `url: str` باید HTTP(S) و داخل providerهای مجاز باشد؛ URL/Codal path نامجاز با
  `UnsupportedDataSourceError` پیش از rate-limit، session و I/O رد می‌شود.
- defaultهای `headers=settings.headers`, `timeout=settings.timeout` و
  `verify=settings.ssl_verify` فقط وقتی caller override نداده باشد اعمال می‌شوند.
- `allow_redirects: bool=True` و `max_redirects: int=5` پارامترهای خود wrapper
  هستند. نوع نادرست اولی/دومی `TypeError` و `max_redirects<0`، `ValueError` است.
- درخواست زیرین همیشه `allow_redirects=False` دارد. redirect فقط same-origin
  (`scheme,host,effective-port`) و hop-by-hop است؛ cross-origin
  `UnsupportedDataSourceError` و loop/عبور از سقف
  `requests.exceptions.TooManyRedirects` می‌دهد.
- `params` فقط روی درخواست اول اعمال می‌شود و روی redirect دوباره فرستاده
  نمی‌شود؛ headerهای caller در redirect same-origin حفظ می‌شوند.
- خطاهای transport خود `requests` بعد از retry propagate می‌شوند. `safe_get`
  به‌تنهایی روی status 4xx/5xx `raise_for_status()` نمی‌کند؛ API مصرف‌کننده باید
  پیش از parse آن را به خطای typed خود تبدیل کند.

سلسله‌مراتب خطا:

```text
AlgotikTSEError
├── AmbiguousSymbolError
├── ConnectionError
├── DataParsingError
├── InvalidParameterError
├── StockNotFoundError
└── UnsupportedDataSourceError
```

`RateLimitError` در ماژول exceptions برای سازگاری داخلی وجود دارد ولی export سطح بالای پکیج نیست. توابع legacy ممکن است به‌جای exception، `None` و پیام کنسول بدهند؛ قرارداد هر تابع را بررسی کنید.

الگوی امن:

```python
try:
    df = att.get_price_adjustments(ins_code="35425587644337450")
except att.InvalidParameterError as exc:
    print("bad input", exc)
except att.AmbiguousSymbolError as exc:
    print("pass ins_code", exc)
except att.ConnectionError as exc:
    print("provider unavailable", exc)
except att.DataParsingError as exc:
    print("provider schema changed", exc)
except att.UnsupportedDataSourceError as exc:
    print("outside supported sources", exc)
```

## فهرست API عمومی و نام‌های قدیمی

جدول زیر inventory کامل exportهای `algotik_tse.__all__` است. جزئیات خروجی در بخش موضوعی مربوط آمده است.

### هویت، تنظیمات و خطا

| Export | کاربرد |
|---|---|
| `settings` | singleton تنظیمات شبکه/بازار |
| `InstrumentRef` | هویت immutable ابزار |
| `normalize_instrument_text`, `validate_ins_code`, `resolve_instrument` | نرمال‌سازی و حل دقیق هویت |
| `AlgotikTSEError`, `AmbiguousSymbolError`, `ConnectionError`, `DataParsingError`, `InvalidParameterError`, `StockNotFoundError`, `UnsupportedDataSourceError` | خطاهای عمومی |

### قیمت، client type، trades و اطلاعات نماد

| Export canonical | Alias/legacy عمومی |
|---|---|
| `get_history` | `stock` |
| `get_client_type` | `stock_RI`, `stock_RL` |
| `get_capital_increase` | `stock_capital_increase` |
| `get_intraday` | `stock_intraday` |
| `get_trades`, `get_live_trades` | — |
| `get_detail` | `stockdetail` |
| `get_info` | `stock_information` |
| `get_stats` | `stock_statistics` |
| `get_introduction` (همیشه unsupported) | `stock_introduction` (همیشه unsupported) |
| `get_shareholders` | `shareholders` |
| `get_symbols` | `stocklist` |
| `get_currency` | `currency_coin` |

پارامترهای قدیمی نیز پذیرفته می‌شوند: `stock` → `symbol`، `values` → `limit`، `tse_format` → `raw`، `multi_stock_drop`/`multi_currencies_drop` → `dropna` و `output_type="complete"` → `"full"` در مسیرهای مربوط. برای کد جدید نام canonical را به‌کار ببرید.

### live، سفارش، watcher و history محلی

| Exportها |
|---|
| `get_market_snapshot`, `get_market_client_type`, `get_order_book`, `get_live_market`, `get_live_symbol` |
| `get_order_book_history`, `get_orderbook_history`, `get_queue`, `get_queue_history` |
| `MarketEvent`, `MarketWatcher`, `watch_market` |
| `get_market_messages`, `get_instrument_state_changes`, `get_market_overview`, `get_market_breadth`, `get_sector_flow` |
| `MARKET_HISTORY_SCHEMA_VERSION`, `MARKET_HISTORY_APPLICATION_ID`, `check_market_history` |
| `save_market_snapshot`, `load_market_snapshots`, `get_live_market_history` |
| `get_market_overview_history`, `get_market_snapshot_summary_history`, `get_market_breadth_history`, `get_sector_flow_history` |
| `record_market_event`, `get_market_event_history`, `archive_market_records` |
| `get_market_messages_history`, `get_instrument_state_changes_history` |

سه wrapper صفرآرگومان legacy نیز عمومی‌اند: `market_watch()`, `market_client_type()`, `market_data()`. `market_data()` wrapper deprecated است؛ برای کد جدید `get_market_snapshot()` یا `get_live_market()` را انتخاب کنید.

### fundamentals، تعدیل قیمت و ابزارها

| Exportها |
|---|
| `get_market_fundamentals`, `get_market_fundamentals_history` |
| `get_price_adjustments`, `get_latest_price_adjustment` |
| `list_options`, `get_options_chain`, `list_etfs`, `list_bonds`, `list_funds`, `list_listed_funds` |
| `list_indices`, `get_index_companies` |

### درآمد ثابت

| Exportها |
|---|
| `IRAN_TREASURY_FACE_VALUE`, `YieldCurve` |
| `parse_treasury_maturity`, `day_count_fraction`, `treasury_yield` |
| `bond_price`, `yield_to_maturity`, `bond_analytics`, `build_yield_curve` |
| `get_ifb_yield_table`, `get_treasury_yields` |
| `get_treasury_yield_history`, `get_treasury_yields_history` |
| `get_yield_curve`, `get_yield_curve_history` |

### اختیار معامله

| Exportها |
|---|
| `OPTION_SNAPSHOT_SCHEMA_VERSION` |
| `black_scholes_price`, `black_scholes_greeks`, `option_price_bounds`, `implied_volatility` |
| `get_option_market`, `analyze_option_chain`, `option_put_call_ratios` |
| `get_option_history`, `save_option_snapshot`, `load_option_snapshots` |

### signatureهای پرکاربرد

```text
get_live_market(symbol=None, *, strict=False)
get_live_symbol(symbol=None, *, ins_code=None, fallback="none")
get_order_book(symbol=None, *, selector_strict=False)
get_queue(symbol=None, side="both", strict=True, *, selector_strict=False)
get_trades(symbol=None, *, ins_code=None, start=None, end=None,
           include_canceled=False, max_requests=None, raw=False, progress=True)
get_market_messages(flow=0, top=20, since_id=None, *, archive_to=None)
get_instrument_state_changes(top=20, since_id=None, *, archive_to=None)
get_market_overview(flow=0, *, archive_to=None)
```

پارامترهایی که با `_` شروع می‌شوند seam داخلی تست‌اند و API کاربر محسوب نمی‌شوند، حتی اگر در `inspect.signature` دیده شوند.

### روش خواندن مرجع تفصیلی

هر signature زیر عین خروجی پایدارشدهٔ `inspect.signature` است؛ فقط آدرس حافظهٔ
`safe_get` به خود نام `safe_get` نرمال شده است. نوع‌هایی که در signature قدیمی
annotation ندارند در جدول پارامترها مشخص شده‌اند. مقدار `None` معمولاً یعنی
«فیلتر/override اعمال نشود»، نه رشتهٔ `"None"`. پارامترهای مشترک فقط یک‌بار در
واژه‌نامهٔ زیر توضیح داده می‌شوند و هر مدخل API علاوه بر آن، override و constraint
خاص خود را می‌گوید. «خطاها» خطاهای اصلی قرارداد است، نه فهرست همهٔ خطاهای ممکن
Python/pandas.

#### پارامترهای مشترک هویت، تاریخچه و خروجی

| نام | type و default معمول | معنا و constraint |
|---|---|---|
| `symbol` / `symbols` | `str | Iterable[str] | None`؛ بسته به API `''` یا `None` | نماد فارسی، `InsCode` یا مجموعهٔ آن‌ها؛ برای هویت مبهم `ins_code` بدهید. `symbols=None` یعنی کل universe. |
| `ins_code` / `inscode` | `str | int | None = None` | شناسهٔ دقیق ۱ تا ۲۰ رقم ASCII؛ با selector متناقض مجاز نیست. `inscode` فقط spelling تاریخی reader وضعیت است. |
| `asset_type` | `str = 'auto'` | hint حل هویت؛ `auto` نوع را از provider تعیین می‌کند. |
| `start`, `end`, `date` | `str | date | datetime | None` | مرز شامل ابتدا/انتها؛ ISO شمسی یا میلادی در APIهای بازار. `date` سهامداران `None` یعنی آخرین مشاهده. |
| `limit` | `int = 0` یا readerها `1000` | `0` در historyهای provider یعنی بدون محدودیت بعد از فیلتر؛ در SQLite حداکثر صفحه. منفی نامعتبر است. |
| `offset` | `int = 0` | offset SQL بعد از فیلترها؛ نامنفی. |
| `include_today` | `bool = False` | opt-in ردیف زندهٔ امروز؛ ممکن است در ساعات بازار آخرین مشاهدهٔ همین لحظه باشد و provenance زنده دارد. |
| `raw` | `bool = False` | schema نزدیک provider؛ در order-book ممکن است delta/raw-mixed باشد. |
| `output_type` | `str = 'standard'` | schema خروجی؛ مقادیر دقیق تابعی‌اند (`standard`/`full` یا `long`/`wide`). `complete` alias قدیمی `full` است. |
| `date_format` | `str = 'jalali'` | شکل index/ستون تاریخ؛ `jalali`, `gregorian`, `both` در مسیرهای پشتیبانی‌شده. |
| `ascending` | `bool = True` | ترتیب زمانی خروجی بعد از فیلتر. |
| `progress` | `bool = True` | فقط پیام پیشرفت؛ در داده و schema اثر ندارد. |
| `save_to_file` | `bool = False` | ذخیرهٔ opt-in CSV. |
| `save_path` | `str | Path | None` | **پوشه**ٔ مقصد، نه نام فایل؛ بدون `save_to_file=True` نوشته نمی‌شود. |
| `dropna` | `bool = True` | حذف ردیف/ستون کاملاً تهی طبق قرارداد همان API؛ ردیف partial معنادار order-book حفظ می‌شود. |
| `return_type` | `str | None` | alias سازگاری برای انتخاب نوع خروجی در history قیمت/ارز؛ برای کد جدید `output_type` را ترجیح دهید. |
| `max_requests` | `int | None` | سقف سخت fan-out قبل/حین I/O؛ معنای دقیق شمارش در مدخل تابع آمده است. |
| `strict` / `selector_strict` | `bool` | strict خطای داده/فیلتر بدون match را فعال می‌کند؛ `selector_strict` انتخاب scalar مبهم/گم‌شده را خطا می‌کند. |
| `allow_stale` / `include_stale` | `bool` | اجازهٔ نگه‌داشتن snapshot/اوراق stale؛ stale بودن همچنان در ستون/attrs گزارش می‌شود. |
| `archive_to`, `record_to`, `snapshot_path`, `path` | `str | Path | None` | فایل SQLite/JSON صریح؛ نوشتن فقط با opt-in. `path` در reader/writer اجباری است. |
| `kwargs` | keywordهای سازگاری | فقط aliasهای مستند مانند `stock`, `values`, `tse_format` و نام‌های انگلیسی `stocklist`; keyword ناشناخته قرارداد عمومی نیست. |
| `_request`, `_snapshot`, `_client_type`, `_clock`, `_wait`, `_random`, `_recorded_at`, `_live_fetch`, `_request_budget_state` | seam داخلی | فقط تزریق deterministic در تست؛ برای مصرف عادی استفاده نشود و BC عمومی برای آن تضمین نمی‌شود. |

#### پارامترهای مشترک live، watcher و SQLite

| نام | type/default | معنا و constraint |
|---|---|---|
| `flow` | `int | None = 0` | بازار/جریان provider؛ `None` در analytics یعنی بدون فیلتر. |
| `sector` | `str | Iterable | None` | فیلتر `SectorCode`. |
| `instrument_types` | `Iterable[int] | None` | universe ابزار؛ پیش‌فرض تحلیلی سهام `300,303,309`. |
| `traded_only` | `bool = False` | فقط ابزار دارای معامله را در denominator نگه می‌دارد. |
| `include_base_market` | `bool = True` | نوع 309 بازار پایه را در universe پیش‌فرض نگه می‌دارد. |
| `side` | `str = 'both'` | `buy`, `sell` یا `both` برای صف. |
| `complete_only` | `bool = False` | فقط snapshotهای پنج‌سطح کامل. |
| `top` | `int = 20` | تعداد پیام/وضعیت در درخواست؛ مثبت و bounded. |
| `since_id` | `int | str | None` | فیلتر client-side رکوردهای پس از شناسه؛ cursor provider نیست. |
| `source` | `str = 'tsetmc'` | provenance/هویت archive؛ در fixed-income می‌تواند `tsetmc` یا حالت مستند hybrid باشد. |
| `session_id` | `str | None` | شناسهٔ session watcher برای نوشتن/فیلتر replay. |
| `kind` | `str | None` | eventهای `initial/delta/heartbeat/resync` یا kind archive پشتیبانی‌شده. |
| `recorded_at`, `as_of` | timestamp-like یا `None` | زمان مشاهده؛ `None` یعنی ساعت تهران/UTC داخلی معتبر تابع. |
| `max_records`, `record_max_records` | `int = 10000` | retention بر اساس تعداد؛ مثبت. |
| `retention_seconds`, `record_retention_seconds` | `float | None` | retention زمانی؛ `None` یعنی غیرفعال. |
| `interval` | `str` در intraday؛ `float=1.0` در watcher | candle interval (`tick/1min/5min/15min/30min/1h`) یا فاصلهٔ polling بر حسب ثانیه. |
| `max_updates` | `int | None` | سقف eventهای iterator؛ `None` یعنی تا stop. |
| `notifications` | iterable، پیش‌فرض `('messages','state')` | فقط این دو notification پشتیبانی می‌شوند؛ Codal وجود ندارد. |
| `error_policy`, `callback_error_policy`, `storage_error_policy` | `str` | enumهای دقیق: `error_policy∈{retry,raise,stop}`، `callback_error_policy∈{raise,ignore,stop}` و `storage_error_policy∈{raise,ignore}`؛ مقدار نامعتبر پیش از I/O خطا است. |
| `max_backoff`, `jitter`, `request_timeout` | `float | None` | backoff سقف، jitter و timeout هر درخواست؛ نامنفی/مثبت طبق کلاس. |
| `max_consecutive_retries`, `max_retries` | `int | None` | سقف retry؛ `max_retries` نام قدیمی سازگار است. |
| `include_initial`, `emit_heartbeats`, `copy_snapshot`, `record_heartbeats` | `bool` | کنترل emission/copy/persistence eventها. |
| `notification_top`, `max_seen_notifications`, `checkpoint_interval` | `int` | `notification_top` بین ۱ و ۱۰۰۰؛ دو مقدار دیگر مثبت. `record_max_records` بین ۱ و ۱۰۰۰۰ است. |

#### پارامترهای درآمد ثابت و اختیار

| نام | type/default | معنا و constraint |
|---|---|---|
| `settlement_date`, `maturity_date`, `issue_date`, `valuation_date` | date-like یا `None` | تاریخ تسویه/سررسید/انتشار/ارزش‌گذاری؛ `None` در live یعنی امروز تهران. |
| `face_value` | `float`؛ اخزا `1_000_000.0` | ارزش اسمی مثبت؛ `IRAN_TREASURY_FACE_VALUE` همین default است. |
| `day_count` / `convention` | `str='ACT/365F'` | convention پشتیبانی‌شده؛ تاریخ پایان باید بعد از شروع باشد. |
| `price`, `annual_yield`, `coupon_rate`, `accrued_interest` | `float` | قیمت/بازده/کوپن/بهرهٔ تحقق‌یافته؛ bounds در تابع math اعتبارسنجی می‌شود. |
| `cashflows` | iterable `(date, amount)` یا `None` | جریان‌های نقدی؛ در حالت `None` از maturity/face/coupon ساخته می‌شود. |
| `compounding`, `frequency`, `price_type` | `str`, `int`, `str` | نوع مرکب، دفعات سالانه و `dirty/clean`. |
| `nodes` | DataFrame/iterable mapping | nodeهای curve شامل maturity و rate/discount؛ duplicate policy تعیین‌کنندهٔ تکرار است. |
| `interpolation`, `extrapolate`, `duplicate_policy` | `log_discount`, `False`, تابعی | interpolation discount؛ extrapolation opt-in؛ سیاست duplicate `error` یا policy مستند. |
| `price_source` | `str='auto'` | انتخاب `Last/Close/Final/bid/ask` با provenance. |
| `maturity_map` | mapping یا `None` | override صریح نماد→سررسید؛ از حدس fuzzy جلوگیری می‌کند. |
| `spot`, `strike`, `option_price`, `volatility` | `float` | spot/strike مثبت، premium نامنفی و volatility نامنفی. |
| `time_to_expiry`, `rate`, `dividend_yield` | `float` | سال تا سررسید، نرخ بدون ریسک و yield پیوسته. |
| `option_type`, `exercise_style` | `str='call'`, `str='european'` | `call/put`؛ math فعلی فقط European را می‌پذیرد. |
| `lower_volatility`, `upper_volatility`, `tolerance`, `max_iterations` | `0.0`, `5.0`, تابعی، تابعی | bracket و همگرایی solver؛ lower < upper و شمار iteration مثبت. |
| `risk_free_rate`, `yield_curve` | scalar/curve یا `None` | نرخ ثابت یا `YieldCurve`; اگر هر دو داده شوند قرارداد تحلیل آن‌ها را اعتبارسنجی می‌کند. |
| `parity_tolerance`, `liquidity_weights` | `float | mapping | None` | band parity و وزن‌های scoring؛ `None` یعنی default داخلی مستند. |

پارامترهای کم‌تکرار نیز بخشی از قراردادند:

| دامنه | پارامترها و معنا |
|---|---|
| history قیمت | `auto_adjust` (`bool=True`) تعدیل OHLC؛ `adjust_volume` (`bool=False`) تعدیل volume متناظر. |
| فهرست بازار | `bourse`, `farabourse`, `payeh` (`bool=True`) و `haghe_taqadom`, `sandogh`, `bonds`, `options`, `mortgage`, `commodity`, `energy` (`bool=False`) سوییچ inclusion؛ `output` (`str='dataframe'`) format؛ `name` (`str|list=''`) نام ارز؛ `fund_type` (`str|list|None`) category؛ `index_name` (`str`) نام/InsCode شاخص؛ `include_id` (`bool=False`) شناسهٔ سهامدار. |
| fundamentals | `pe_min`, `pe_max` (`float|None`) مرزهای شامل؛ `positive_pe` (`bool=True`) فقط P/E مثبت معتبر. |
| live/option | `fallback` (`str='none'`) مسیر point opt-in؛ `exchange` (`int=0`) کد بازار اختیار؛ `category` (`str='treasury'`) دسته IFB؛ `lock_timeout` (`float=10.0`) و `stale_lock_seconds` (`float=300.0`) قفل فایل مثبت. |
| fixed math | `bump_size` (`float=0.0001`) شوک DV01؛ `rate_compounding` (`str='effective'`), `rate_frequency` (`int=1`); `enforce_monotonic_discount` (`bool=True`) guard curve. |
| storage | `event` (`MarketEvent`) رخداد ورودی و `frame` (`DataFrame`) batch archive. |
| resolver | `selector` (`Any`) انتخاب ورودی؛ `require_active` (`bool=True`) الزام فعالیت. |

فیلدهای باقی‌ماندهٔ `MarketEvent` همگی constructor contract هستند:
`sequence` (`int`) شمارهٔ افزایشی، `changed_inscodes` (`tuple[str,...]`) و
`changed_order_levels` (`tuple[tuple[str,int],...]`) delta،
`market_state_changed` (`bool`)، `notification_tokens` (`tuple[str,str,str]`) cursorهای
notification، `state_changes` (`DataFrame|None`)، `cursor_before`/`cursor_after`
(`int`)، `retry_count` (`int`), `retry_error` (`str|None`),
`notification_errors` (`tuple[str,...]`) و `persistence_status`/
`persistence_error` (`str|None`) هستند. فیلد `is_active` (`bool|None`) در
`InstrumentRef` سه حالت فعال/غیرفعال/نامعلوم دارد.

### نوع‌ها، ثابت‌ها، تنظیمات و exceptionهای عمومی

`InstrumentRef(ins_code: 'str', symbol: 'str | None' = None, name: 'str | None' = None, asset_type: 'str' = 'unknown', is_active: 'bool | None' = None, provenance: 'str' = '', selector: 'str | None' = None) -> None`

dataclass immutable هویت است؛ فیلدها به‌ترتیب شناسهٔ canonical، نماد/نام، نوع دارایی،
وضعیت فعال، منبع اثبات و selector ورودی هستند. ساخت مستقیم فقط برای دادهٔ از قبل
اعتبارسنجی‌شده مناسب است؛ مسیر عادی `resolve_instrument()` است. خطای constructor
استاندارد `TypeError` برای field گم‌شده/اضافی است.

`MarketEvent(kind: 'str', sequence: 'int', fetched_at: 'pd.Timestamp', trade_date: 'Optional[_dt.date]', snapshot: 'dict[str, Any]', changed_inscodes: 'tuple[str, ...]' = (), changed_order_levels: 'tuple[tuple[str, int], ...]' = (), market_state_changed: 'bool' = False, notification_tokens: 'tuple[str, str, str]' = ('', '', ''), messages: 'Optional[pd.DataFrame]' = None, state_changes: 'Optional[pd.DataFrame]' = None, cursor_before: 'int' = 0, cursor_after: 'int' = 0, retry_count: 'int' = 0, retry_error: 'Optional[str]' = None, notification_errors: 'tuple[str, ...]' = (), persistence_status: 'Optional[str]' = None, persistence_error: 'Optional[str]' = None) -> None`

event watcher است. `snapshot/messages/state_changes` با `copy_snapshot=True` کپی
دفاعی ولی mutable هستند؛ tupleها delta/cursor و رشته‌های خطا/persistence provenance
را نگه می‌دارند. مثال ساخت دستی لازم نیست؛ نمونهٔ موضوعی `watch_market()` بالاتر است.

`YieldCurve(settlement_date: datetime.date, maturities: tuple, times: tuple, discount_factors: tuple, continuous_zero_rates: tuple, day_count: str = 'ACT/365F', interpolation: str = 'log_discount', extrapolate: bool = False, node_metadata: tuple = <factory>, diagnostics: dict = <factory>) -> None`

curve immutable محاسباتی با آرایه‌های هم‌طول و metadata/diagnostics است؛ آن را با
`build_yield_curve()` بسازید. متدهای interpolation خارج از محدوده با
`extrapolate=False`، `ValueError` می‌دهند.

| export ثابت | type/value | معنا |
|---|---|---|
| `MARKET_HISTORY_SCHEMA_VERSION` | `int = 2` | نسخهٔ schema SQLite market history. |
| `MARKET_HISTORY_APPLICATION_ID` | `int = 1096045381` | application id SQLite برای رد فایل نامرتبط. |
| `IRAN_TREASURY_FACE_VALUE` | `float = 1_000_000.0` | ارزش اسمی پیش‌فرض اخزا، نه override اجباری همهٔ اوراق. |
| `OPTION_SNAPSHOT_SCHEMA_VERSION` | `int = 1` | نسخهٔ سند JSON snapshot اختیار؛ reader mismatch را رد می‌کند. |

`settings` یک singleton از `Settings` است. تنظیمات mutable عمومی مهم:
`ssl_verify: bool=True`, `timeout: int|float=10`, `max_retries: int=3`,
`retry_backoff_factor: float=0.3`, `rate_limit_delay: float=0.3`,
`market_snapshot_freshness_seconds: float=120.0`,
`market_clock_skew_tolerance_seconds: float=5.0`,
`client_volume_consistency_tolerance: float=0.05`,
`order_book_max_requests: int=250`, `trade_max_requests: int=250` و
`order_book_discovery_lookback_days: int=10` هستند. `headers: dict`، mappingهای
روز/ارز/صندوق/بازار پایه و `url_*: str` قرارداد تنظیم provider هستند؛ تغییر URL
می‌تواند source-boundary را نقض کند و برای مصرف عادی توصیه نمی‌شود.

exceptionهای عمومی همگی constructor ارث‌بردهٔ `(*args)` و base مشترک
`AlgotikTSEError` دارند: `AmbiguousSymbolError` برای چند هویت هم‌رتبه،
`ConnectionError` برای HTTP/provider، `DataParsingError` برای schema/identity ناامن،
`InvalidParameterError` برای ورودی نامعتبر، `StockNotFoundError` برای نبود هویت و
`UnsupportedDataSourceError` برای خروج از مرز منبع. نمونهٔ catch در فصل تنظیمات است.

| constructor | قرارداد |
|---|---|
| `AlgotikTSEError` | base exception؛ `args: tuple[Any,...]` پیام/context را مانند `Exception` نگه می‌دارد؛ خودش return ندارد. |
| `AmbiguousSymbolError` | چند هویت exact هم‌رتبه؛ راه‌حل ارائهٔ `ins_code` است. |
| `ConnectionError` | HTTP/status/redirect/provider failure با cause اصلی (`raise ... from exc`). |
| `DataParsingError` | payload/schema/هویت/فایل ناسازگار؛ retry کور معمولاً مناسب نیست. |
| `InvalidParameterError` | constraint ورودی؛ در APIهای جدید پیش از I/O. |
| `StockNotFoundError` | selector exact پیدا نشده؛ fuzzy-first-hit انجام نمی‌شود. |
| `UnsupportedDataSourceError` | API نیازمند منبع خارج boundary؛ `get_introduction` نمونهٔ fail-before-I/O است. |
| `YieldCurve` | constructor dataclass بالا؛ خروجی object curve و خطای field/shape نامعتبر `TypeError/ValueError`؛ مثال `build_yield_curve`. |

### قرارداد API: هویت، قیمت، معاملات و APIهای قدیمی

```text
normalize_instrument_text(value: 'Any') -> 'str'
resolve_instrument(selector=None, *, ins_code=None, asset_type='auto', snapshot=None, require_active=True) -> 'InstrumentRef'
validate_ins_code(value: 'Any') -> 'str'
get_history(symbol='', start=None, end=None, limit=0, raw=False, auto_adjust=True, output_type='standard', date_format='jalali', progress=True, save_to_file=False, dropna=True, adjust_volume=False, return_type=None, ascending=True, save_path=None, include_today=False, *, ins_code=None, asset_type='auto', **kwargs)
get_client_type(symbol='', start=None, end=None, limit=0, raw=False, output_type='standard', date_format='jalali', progress=True, save_to_file=False, dropna=True, ascending=True, save_path=None, include_today=False, *, ins_code=None, asset_type='auto', **kwargs)
get_capital_increase(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
get_intraday(symbol='شتران', interval='1min', start=None, end=None, progress=True, **kwargs)
get_trades(symbol=None, *, ins_code=None, start=None, end=None, include_canceled=False, max_requests=None, raw=False, progress=True)
get_live_trades(symbol=None, *, ins_code=None, include_canceled=False, max_requests=None, raw=False, progress=True)
get_detail(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
get_info(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
get_stats(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
get_introduction(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
get_symbols(bourse=True, farabourse=True, payeh=True, haghe_taqadom=False, sandogh=False, bonds=False, options=False, mortgage=False, commodity=False, energy=False, payeh_color=None, output='dataframe', progress=True, **kwargs)
get_shareholders(symbol='', date=None, include_id=False, *, ins_code=None, asset_type='auto', **kwargs)
get_currency(name='', start=None, end=None, limit=0, output_type='standard', date_format='jalali', progress=True, save_to_file=False, dropna=True, return_type=None, ascending=True, save_path=None, **kwargs)
get_market_snapshot(*args, **kwargs)
get_market_client_type(*args, **kwargs)
```

| API | ورودی خاص افزون بر واژه‌نامه | خروجی، schema و attrs | خطاهای اصلی و مثال |
|---|---|---|---|
| `normalize_instrument_text` | `value: Any`؛ `None` به رشتهٔ تهی و متن با یکسان‌سازی ی/ک، فاصله و ZWNJ به کلید مقایسه تبدیل می‌شود. | `str` canonical؛ ورودی را mutate نمی‌کند. | خطای ویژه ندارد؛ `normalize_instrument_text("كگل") == "کگل"`. |
| `validate_ins_code` | `value: str|int`؛ integer مثبت یا رشتهٔ ۱..۲۰ رقم ASCII (فاصلهٔ ابتدا/انتها strip می‌شود). float، bool، رقم فارسی/عربی، sign، space داخلی، صفر و طول بیش از ۲۰ رد می‌شوند. | `str` ASCII؛ integer معتبر دقیقاً به رشته تبدیل می‌شود. | `InvalidParameterError`؛ مثال بخش resolver. |
| `resolve_instrument` | `snapshot: dict|DataFrame|None` منبع authoritative حتی اگر تهی؛ `require_active: bool=True` ابزار غیرفعال را حذف می‌کند. اولویت exact در فصل resolver آمده است. | `InstrumentRef`; `provenance` مسیر اثبات (`explicit_ins_code`, snapshot/search/index registry و مشابه) را ثبت می‌کند. | `InvalidParameterError`, `StockNotFoundError`, `AmbiguousSymbolError`, `DataParsingError`, `ConnectionError`; مثال exact/ambiguity بالاتر. |
| `get_history` | `auto_adjust: bool=True` تعدیل قیمت؛ `adjust_volume: bool=False` تعدیل volume با ضریب؛ `raw` schema TSE؛ تاریخ/ذخیره طبق glossary. | برای سهم و `auto_adjust=True`، `output_type='standard'` دقیقاً `Open,High,Low,Close,Volume` است؛ `full` ستون‌های `Final,No.,Value` و تقویم/`Ticker` را اضافه می‌کند. با `auto_adjust=False`، standard ستون `Adj Close` هم دارد. index/industry schema محدودتر خود را دارند؛ چند نماد MultiIndex. attrs پیش‌فرض تهی و با `include_today=True` شامل `include_today_appended/include_today_warning` است. | ورودی‌های ناسازگار legacy معمولاً `ValueError`/`None` و provider `ConnectionError`; مثال فصل قیمت. |
| `get_client_type` | `raw=True` schema provider؛ بقیهٔ history params مشترک. | `DataFrame` روزانهٔ `Buy_I/N_Count`, `Buy_I/N_Volume`, `Sell_I/N_Count`, `Sell_I/N_Volume`, قدرت/سرانه‌های مشتق؛ چند نماد MultiIndex. ردیف امروز opt-in است. | خطای selector/provider یا legacy `None`; مثال فصل حقیقی/حقوقی. |
| `get_capital_increase` | selector و alias قدیمی `stock=`. | `DataFrame|None` با index `date` و `old_shares_amount,new_shares_amount`. | index/نماد گم‌شده/provider در قرارداد قدیمی پیام و `None`؛ `att.get_capital_increase("فملی")`. |
| `get_intraday` | `interval` canonical یکی از `tick,1min,5min,15min,30min,1h,4h,12h` و aliasهای `_INTERVAL_MAP` مانند `1m,60min,4hour,240m,12hour,720,ticks,raw`؛ بدون تاریخ معاملات امروز، با `start` snapshot تاریخی. | `DataFrame|None`; tick شامل زمان/قیمت/حجم و candle شامل `Open,High,Low,Close,Volume,TradeCount` با DatetimeIndex. | interval نامعتبر یا تاریخی که validator قدیمی نامعتبر تشخیص دهد پیام چاپ می‌کند و `None` می‌دهد؛ provider/نماد نیز در مسیر legacy `None`؛ `ValueError` خطای عمدی قرارداد این API نیست؛ مثال `att.get_intraday("فملی", interval="5min")`. |
| `get_trades` | بدون تاریخ امروز تهران؛ Thu/Fri قبل از budget حذف؛ `include_canceled`; `max_requests` فقط Trade endpoint؛ `raw` ستون‌های provider را اضافه می‌کند. | standard: `DataFrame[InsCode,Symbol,GregorianDate,JalaliDate,TradeNo,Time,Timestamp,Price,Volume,Value,Canceled,Source]`; attrs شامل request/provenance/failures. raw ستون‌های audit نیز دارد. | `InvalidParameterError`, resolver errors, `ConnectionError`, `DataParsingError`; مثال فصل معاملات. |
| `get_live_trades` | همان trades بدون range؛ wrapper امروز تهران. | همان schema/attrs `get_trades`. | همان خطاها؛ `att.get_live_trades(ins_code="...")`. |
| `get_detail` | selector دقیق؛ API HTML قدیمی. | `DataFrame|None` با index `key` و ستون `value`، به‌همراه row `id`. | index/no-match/HTTP در رفتار legacy `None`; مثال `att.get_detail("فملی")`. |
| `get_info` | selector دقیق. | `DataFrame|None` key/value از flatten کامل `instrumentInfo`. | legacy `None` یا connection/parsing؛ مثال فصل اطلاعات نماد. |
| `get_stats` | selector دقیق. | `DataFrame|None` key/value آمار با کلید فارسی و value عددی. | legacy `None` یا connection/parsing؛ `att.get_stats("فملی")`. |
| `get_introduction` | signature فقط برای BC؛ هیچ پارامتر باعث I/O نمی‌شود. | هرگز خروجی موفق ندارد. | همیشه `UnsupportedDataSourceError` **پیش از I/O**؛ جایگزین market-data: `get_info/get_detail`. |
| `get_symbols` | booleanهای market/asset، `payeh_color: str|list|None`; `output: str='dataframe'`; aliasهای انگلیسی در `kwargs`. | `DataFrame` فهرست ابزارها یا format قدیمی انتخابی؛ ستون‌های هویت/نام/بازار و type؛ خروجی تهی schema پایدار دارد. | فیلتر/output نامعتبر `ValueError` یا legacy `None`; مثال فصل فهرست ابزارها. |
| `get_shareholders` | `include_id: bool=False`; `date=None` آخرین و تاریخ مشخص snapshot آن روز. | `DataFrame|None[share_holder_name,number_of_shares,percentage_of_shares,change_state,change_amount,date]` و با opt-in `share_holder_id`. | provider/selector در legacy پیام و `None`; مثال فصل اطلاعات نماد. |
| `get_currency` | `name: str|list`; منبع legacy TGJU؛ `limit/date/output/save` مشترک. | تک ارز `DataFrame[Open,High,Low,Close]`; چند ارز ستون MultiIndex؛ index تاریخ. | نام نامعتبر/provider ممکن است `ValueError`/`None`; مثال فصل ارز. |
| `get_market_snapshot` | `*args/**kwargs` برای BC به تابع صفرآرگومان `market_watch` forward می‌شود؛ در عمل آرگومان غیرتهی `TypeError` می‌دهد. | `dict` با کلیدهای دقیق `stocks,order_book,market_time,index_value,migration,trade_date,market_state,exchange_time,fetched_at,snapshot_age_seconds,is_today_trade_date,is_history_eligible,is_realtime_fresh,is_previous_trade_date,is_stale,is_partial`. | `ConnectionError`, `DataParsingError`; مثال live. |
| `get_market_client_type` | `*args/**kwargs` wrapper `market_client_type`. | `DataFrame[InsCode,Buy_I_Count,...,Net_I_Volume,Net_N_Volume]`. | `ConnectionError`, `DataParsingError`; مثال live. |

### قرارداد API: live، سفارش، watcher و تحلیل بازار

```text
get_order_book(symbol=None, *, selector_strict=False)
get_live_market(symbol=None, *, strict=False)
get_live_symbol(symbol=None, *, ins_code=None, fallback='none')
get_order_book_history(symbol='', start=None, end=None, limit=0, raw=False, output_type='standard', date_format='jalali', progress=True, save_to_file=False, dropna=True, ascending=True, save_path=None, include_today=False, complete_only=False, *, max_requests=None, _request_budget_state=None, **kwargs)
get_orderbook_history(symbol='', start=None, end=None, limit=0, raw=False, output_type='standard', date_format='jalali', progress=True, save_to_file=False, dropna=True, ascending=True, save_path=None, include_today=False, complete_only=False, *, max_requests=None, _request_budget_state=None, **kwargs)
get_queue(symbol=None, side='both', strict=True, *, selector_strict=False)
get_queue_history(symbol='', start=None, end=None, limit=0, date_format='jalali', progress=True, save_to_file=False, dropna=True, ascending=True, save_path=None, include_today=False, complete_only=False, side='both', strict=True, *, max_requests=None, **kwargs)
MarketWatcher(symbol=None, interval=1.0, max_updates=None, include_initial=True, emit_heartbeats=True, notifications=('messages', 'state'), notification_top=50, stop_event=None, error_policy='retry', max_backoff=30.0, jitter=0.1, callback_error_policy='raise', max_consecutive_retries=5, max_retries=None, max_seen_notifications=10000, copy_snapshot=True, request_timeout=None, *, record_to=None, record_heartbeats=False, checkpoint_interval=100, record_max_records=10000, record_retention_seconds=None, storage_error_policy='raise', _request=safe_get, _clock=None, _wait=None, _random=None)
watch_market(*args, **kwargs)
get_market_messages(flow=0, top=20, since_id=None, *, archive_to=None, _recorded_at=None, _request=safe_get)
get_instrument_state_changes(top=20, since_id=None, *, archive_to=None, _recorded_at=None, _request=safe_get)
get_market_overview(flow=0, *, archive_to=None, _recorded_at=None, _request=safe_get)
get_market_breadth(symbol=None, flow=None, sector=None, traded_only=False, include_base_market=True, instrument_types=None, *, _snapshot=None)
get_sector_flow(symbol=None, flow=None, sector=None, traded_only=False, include_base_market=True, instrument_types=None, *, _snapshot=None, _client_type=None)
```

| API | ورودی خاص | خروجی/schema/attrs | خطا و مثال |
|---|---|---|---|
| `get_order_book` | scalar/list/`None`; `selector_strict` فقط resolution انتخاب را سخت می‌کند. | `DataFrame` long با `InsCode,Symbol,Name,Level,BidOrderCount,BidVolume,BidPrice,AskPrice,AskVolume,AskOrderCount` و metadata `trade_date,market_state,exchange_time,fetched_at,is_*`. پنج سطح از همان response snapshot. | `InvalidParameterError`, `StockNotFoundError` در strict، connection/parsing؛ مثال فصل سفارش. |
| `get_live_market` | `strict=False` selectorهای گم‌شده را در `attrs['missing_selectors']` ثبت می‌کند؛ strict آن‌ها را خطا می‌کند. | `DataFrame` با `STOCK_COLUMNS`، client columns، سطح‌های wide `BidPrice1..5/AskPrice1..5` و metrics از جمله `EstimatedNetIndividualFlow`; freshness ستون row-wise است. attrs دقیق: `field_validity,source_schema_presence,migration,missing_selectors`. `Last` آخرین معامله و `Close` پایانی است. | `InvalidParameterError`, `StockNotFoundError` در strict، `ConnectionError/DataParsingError`; quickstart و مثال attrs بالا. |
| `get_live_symbol` | `fallback: 'none'|'point'`; point فقط در غیاب MarketWatch. `fallback='none'` برای no-match frame تهی نمی‌دهد. | frame دقیقاً یک‌ردیفی یا exception؛ provenance `SnapshotSource='market_watch'|'closing_price_info_fallback'` و ستون‌های `PresentInMarketWatch,MarketStateTitle,has_trade_today,PriceActionable,FallbackReason,IdentityVerified`. | no-match با fallback none: `StockNotFoundError`; همچنین `InvalidParameterError`, `AmbiguousSymbolError`, `DataParsingError`; فصل live. |
| `get_order_book_history` | `raw`; `output_type='standard'` long و `'wide'`; `complete_only`; budget همهٔ calls این workflow. | long/wide/raw `DataFrame`; ستون‌های identity/time/۵ سطح و `is_partial,is_complete,market_partial_status,is_reconstructed,is_stale,record_type,source`; attrs `schema,failed_requests,request_count,max_requests`. | `InvalidParameterError`, `DataParsingError`, resolver/connection؛ failure جزئی warning + attrs؛ مثال فصل تاریخچه سفارش. |
| `get_orderbook_history` | alias هویتی و signature کاملاً یکسان با `get_order_book_history`. | دقیقاً همان object/return/schema/attrs. | همان خطاها و همان مثال؛ `att.get_orderbook_history is att.get_order_book_history`. |
| `get_queue` | `side`; `strict=True` فقط queueهای قطعی را نگه می‌دارد. | `DataFrame[InsCode,Symbol,Name,...,Side,QueuePrice,QueueVolume,QueueOrders,QueueValue,PriceLimit,is_queue,book_state,...]`. | side نامعتبر `InvalidParameterError`; selector/provider errors؛ مثال صف. |
| `get_queue_history` | history params + `side/strict/complete_only`; threshold همان تاریخ و as-of snapshot. | همان `QUEUE_COLUMNS`; `is_queue` nullable، crossed book false؛ attrs budget/failures. | `InvalidParameterError`, resolver/connection/parsing؛ مثال فصل صف. |
| `MarketWatcher` | `notifications` فقط `messages/state`; policy enumها دقیقاً در glossary؛ `interval,max_backoff>=0`, `0<=jitter<=1`, retry limit نامنفی، `request_timeout/record_retention_seconds>0`; `stop_event` دارای `is_set/wait`; `record_to` opt-in. | iterator سنکرون `MarketEvent`; kindهای `initial/delta/heartbeat/resync`; خود constructor I/O نمی‌کند. | policy/range نامعتبر `InvalidParameterError` پیش از iteration؛ runtime `ConnectionError/DataParsingError` طبق policy؛ مثال watcher. |
| `watch_market` | تمام `*args/**kwargs` بدون تغییر به `MarketWatcher` می‌روند. | `MarketWatcher`, نه DataFrame. | همان constructor/runtime؛ مثال `for event in att.watch_market(max_updates=3): ...`. |
| `get_market_messages` | `since_id` فیلتر local؛ `archive_to` نوشتن اتمیک opt-in. | `DataFrame[message_id,date,time,timestamp,title,description,flow]`; attrs provenance/archive. | `InvalidParameterError`, `ConnectionError`, `DataParsingError`, storage error؛ مثال فصل پیام. |
| `get_instrument_state_changes` | `top/since_id/archive_to`. | `DataFrame[event_id,date,time,timestamp,InsCode,Symbol,Name,state_code,state,real_time,under_supervision,state_title]`. | همان خانواده؛ مثال فصل وضعیت. |
| `get_market_overview` | `flow`; payload تهی صفر ردیف است. | provider overview `DataFrame` با `flow` و فیلدهای payload/fast-view؛ attrs source/time/archive. | parameter/connection/parsing/storage؛ مثال overview. |
| `get_market_breadth` | فیلترهای universe؛ denominator ابزار انتخاب‌شده. | یک‌ردیف `DataFrame` با counts/percentages، A/D، volume/value، limit counts و freshness. attrs analytics/source. | `InvalidParameterError`, `DataParsingError`; مثال breadth. |
| `get_sector_flow` | همان filterها؛ client feed فقط برای ردیف reconcileشده. | یک ردیف در هر `SectorCode` با breadth + `client_coverage,net_individual_volume,estimated_net_individual_value,value_available,value_method` و freshness. | parameter/connection/parsing؛ مثال sector. |

### قرارداد API: تاریخچهٔ محلی و fundamentals

```text
get_market_fundamentals(symbols=None, *, pe_min=None, pe_max=None, positive_pe=True, instrument_types=(300, 303, 309), strict=False, allow_stale=False, archive_to=None, max_requests=1, progress=True)
get_market_fundamentals_history(path, start=None, end=None, symbols=None, *, pe_min=None, pe_max=None, positive_pe=True, instrument_types=(300, 303, 309), strict=False, allow_stale=True, limit=1000, offset=0)
get_price_adjustments(symbol=None, *, ins_code=None, start=None, end=None, progress=True)
get_latest_price_adjustment(symbol=None, *, ins_code=None, start=None, end=None, progress=True)
check_market_history(path)
save_market_snapshot(path, snapshot=None, *, as_of=None, _live_fetch=None)
load_market_snapshots(path, start=None, end=None, symbol=None, *, limit=1000, offset=0)
get_live_market_history(path, start=None, end=None, symbol=None, *, limit=1000, offset=0)
get_market_overview_history(path, start=None, end=None, flow=0, *, source='tsetmc', limit=1000, offset=0)
get_market_snapshot_summary_history(path, start=None, end=None, flow=None, *, limit=1000, offset=0)
get_market_breadth_history(path, start=None, end=None, symbol=None, flow=None, sector=None, traded_only=False, include_base_market=True, instrument_types=None, *, limit=1000, offset=0)
get_sector_flow_history(path, start=None, end=None, symbol=None, flow=None, sector=None, traded_only=False, include_base_market=True, instrument_types=None, *, limit=1000, offset=0)
record_market_event(path, event, *, session_id=None, include_snapshot=True, max_records=10000, retention_seconds=None)
get_market_event_history(path, start=None, end=None, kind=None, *, session_id=None, limit=1000, offset=0)
archive_market_records(path, kind, frame, *, source='tsetmc', recorded_at=None)
get_market_messages_history(path, start=None, end=None, flow=0, since_id=None, *, source='tsetmc', limit=1000, offset=0)
get_instrument_state_changes_history(path, start=None, end=None, symbol=None, since_id=None, *, inscode=None, source='tsetmc', limit=1000, offset=0)
```

| API | ورودی خاص | خروجی/schema/attrs | خطا و مثال |
|---|---|---|---|
| `get_market_fundamentals` | `pe_min/pe_max: float|None` شامل مرز؛ `positive_pe=True` فقط P/E مثبت؛ `archive_to`; `max_requests=1` bulk. | schema ثابت بالا؛ attrs دقیق `request_count,max_requests,missing_selectors,strict,stale_rejected,source,price_source,eps_source,no_lookahead,no_backfill,archive_path`. | bounds/filter/no-match در strict: `InvalidParameterError`/resolver error؛ stale با `allow_stale=False` frame تهی و attr است، نه exception؛ provider typed errors؛ مثال fundamentals. |
| `get_market_fundamentals_history` | فقط SQLite؛ `allow_stale=True`; filterها روی همان snapshot. | همان schema؛ attrs `missing_selectors,strict,source,price_source,eps_source,current_eps_used,no_lookahead,no_backfill,coverage_start,coverage_end`; `current_eps_used=False`. | file/schema/filter `InvalidParameterError` یا `DataParsingError`; مثال backtest. |
| `get_price_adjustments` | selector دقیق و date bounds شامل. | `DataFrame[InsCode,Symbol,GregorianDate,JalaliDate,AdjustedClosingPrice,UnadjustedClosingPrice,AdjustmentAmount,CorporateTypeCode,CorporateActionType,IsConfirmedDPS,IdentityVerified,Source,FetchedAt]`; `IsConfirmedDPS=False`, attrs `dps_available=False`. | resolver/parameter/connection/parsing؛ مثال فصل تعدیل. |
| `get_latest_price_adjustment` | همان ورودی؛ latest پس از filter. | همان schema، صفر یا یک ردیف typed و همان attrs. | همان خطاها؛ مثال فصل تعدیل. |
| `check_market_history` | `path` باید SQLite موجود باشد. | `dict[str, bool|int]` دقیقاً با `ok=True,SchemaVersion,ApplicationID`؛ DataFrame نیست. | فایل گم‌شده `InvalidParameterError`؛ غیرSQLite/نسخه ناسازگار `DataParsingError`؛ مثال `att.check_market_history(db)`. |
| `save_market_snapshot` | `snapshot: DataFrame|dict|None`; اگر `None` فقط یک fetch؛ `as_of` override مشاهده. | `str`، SHA-256 `snapshot_id`; DB با live/client/order هم‌زمان و transaction اتمیک؛ attrs داخل reader بازیابی می‌شود. | path/type/schema/storage `InvalidParameterError/DataParsingError`; network فقط هنگام snapshot=None؛ مثال SQLite. |
| `load_market_snapshots` | فیلتر inclusive زمان و symbol؛ pagination SQL. | `DataFrame` ردیف‌های observation با `STOCK_COLUMNS` و meta `SnapshotID,AsOf,Source,SchemaVersion,NoBackfill,CoverageStart,SnapshotAtomic,PersistenceAtomic,SourceAtomic,PriceSourceAsOf,ClientSourceAsOf,NoLookahead`. | file/schema/filter typed؛ مثال SQLite. |
| `get_live_market_history` | alias معنایی reader rich live، نه alias identity. | همان frame/meta `load_market_snapshots`. | همان خطاها؛ مثال `att.get_live_market_history(db, symbol="فملی")`. |
| `get_market_overview_history` | archive مستقل، `flow/source`. | payload exact provider قبلی + meta archive `ArchiveIdentity,Version,FirstObservedAt,ObservedAt,ProviderTimestamp,AsOf,Source,SchemaVersion,NoBackfill,...`. | kind/source/schema نامعتبر typed؛ مثال archive_to. |
| `get_market_snapshot_summary_history` | summary مشتق از snapshot atomic؛ `flow=None` همه. | `DataFrame[flow,instrument_count,trade_count,total_volume,total_value,market_cap,trade_date,exchange_time,fetched_at,is_realtime_fresh]` + meta. | file/filter/schema errors؛ مثال SQLite. |
| `get_market_breadth_history` | همان فیلترهای live روی هر snapshot persisted. | `BREADTH_COLUMNS` + meta؛ snapshot-by-snapshot، بدون look-ahead. | file/filter/schema errors؛ مثال breadth history. |
| `get_sector_flow_history` | همان فیلترهای live، client و prices همان observation. | `SECTOR_FLOW_COLUMNS` + meta/no-lookahead. | file/filter/schema errors؛ مثال sector history. |
| `record_market_event` | `event: MarketEvent`; `include_snapshot`; retention/session. | `str`، SHA-256 `event_id`; event و notification/snapshot در transaction. | type/kind/storage `InvalidParameterError/DataParsingError`; مثال `record_to` watcher. |
| `get_market_event_history` | `kind=None|initial|delta|heartbeat|resync`; session/pagination. | `DataFrame[event_id,SessionID,kind,SnapshotMode,sequence,fetched_at,trade_date,changed_inscodes,changed_order_levels,market_state_changed,notification_tokens,cursor_before,cursor_after,retry_count,retry_error,notification_errors,snapshot,messages,state_changes]` + meta. | kind ناشناخته `InvalidParameterError` حتی برای فایل گم‌شده؛ schema errors؛ مثال replay. |
| `archive_market_records` | `kind` یکی از `messages,state_changes,overview`؛ `frame: DataFrame`; `recorded_at/source` هویت archive. | `int` تعداد versionهای تازهٔ نوشته‌شده؛ true duplicate صفر، transaction atomic. | kind/type/storage errors؛ مثال helperهای `archive_to`. |
| `get_market_messages_history` | `flow/since_id/source` و time/page filters. | schema پیام + archive meta؛ dedup provider ID. | file/schema/filter errors؛ مثال archive. |
| `get_instrument_state_changes_history` | `symbol` و/یا spelling قدیمی `inscode`; `since_id/source`. | schema state + archive meta. | selector متناقض/فایل/schema errors؛ مثال archive. |

### قرارداد API: درآمد ثابت

```text
parse_treasury_maturity(symbol)
day_count_fraction(start, end, convention='ACT/365F')
treasury_yield(price, maturity_date, settlement_date=None, face_value=1000000.0, day_count='ACT/365F')
bond_price(annual_yield, cashflows=None, settlement_date=None, day_count='ACT/365F', compounding='nominal', frequency=1, price_type='dirty', accrued_interest=None, maturity_date=None, face_value=None, coupon_rate=None, issue_date=None)
yield_to_maturity(price, cashflows=None, settlement_date=None, day_count='ACT/365F', compounding='nominal', frequency=1, price_type='dirty', accrued_interest=None, maturity_date=None, face_value=None, coupon_rate=None, issue_date=None, tolerance=1e-12, max_iterations=300)
bond_analytics(price, cashflows=None, settlement_date=None, day_count='ACT/365F', compounding='nominal', frequency=1, price_type='dirty', accrued_interest=None, maturity_date=None, face_value=None, coupon_rate=None, issue_date=None, annual_yield=None, bump_size=0.0001)
build_yield_curve(nodes, settlement_date, interpolation='log_discount', extrapolate=False, duplicate_policy='error', day_count='ACT/365F', rate_compounding='effective', rate_frequency=1, enforce_monotonic_discount=True)
get_ifb_yield_table(category='treasury')
get_treasury_yields(symbol=None, settlement_date=None, face_value=1000000.0, include_stale=False, min_volume=0, price_source='auto', day_count='ACT/365F', strict=False, face_value_source=None, source='tsetmc', maturity_date=None, maturity_map=None, allow_no_trade=False)
get_treasury_yield_history(symbol=None, start=None, end=None, limit=0, settlement_date=None, face_value=1000000.0, include_today=False, date_format='jalali', price_source='auto', day_count='ACT/365F', ascending=True, progress=True, strict=False, face_value_source=None, max_requests=250, maturity_date=None, maturity_map=None, use_ifb_reference=False)
get_treasury_yields_history(symbol=None, start=None, end=None, limit=0, settlement_date=None, face_value=1000000.0, include_today=False, date_format='jalali', price_source='auto', day_count='ACT/365F', ascending=True, progress=True, strict=False, face_value_source=None, max_requests=250, maturity_date=None, maturity_map=None, use_ifb_reference=False)
get_yield_curve(symbol=None, settlement_date=None, face_value=1000000.0, include_stale=False, min_volume=0, min_nodes=3, price_source='auto', day_count='ACT/365F', interpolation='log_discount', extrapolate=False, duplicate_policy='volume_weighted', enforce_monotonic_discount=True, source='tsetmc')
get_yield_curve_history(symbol=None, start=None, end=None, limit=0, face_value=1000000.0, include_today=False, date_format='jalali', price_source='auto', day_count='ACT/365F', min_nodes=3, interpolation='log_discount', duplicate_policy='volume_weighted', enforce_monotonic_discount=True, ascending=True, progress=True, max_requests=250, maturity_map=None)
```

| API | ورودی خاص | خروجی/schema/attrs | خطا و مثال |
|---|---|---|---|
| `parse_treasury_maturity` | `symbol: Any`; فقط full-match `اخزاYYMMDD` پس از تبدیل رقم فارسی/عربی و حذف ZWNJ؛ `00..79→1400..1479` و `80..99→1380..1399`. | `dict|None`; موفق: `maturity_jalali: str`, `maturity_gregorian: datetime.date`, `maturity_source='user_confirmed_symbol_jalali_yymmdd'`. | non-match/تاریخ نامعتبر **`None`**، نه exception؛ مثال deterministic بالاتر. |
| `day_count_fraction` | `start/end: date-like`; `convention`. | `float` year fraction. | date order/convention نامعتبر `ValueError`; `day_count_fraction(date(2025,1,1), date(2026,1,1)) == 1.0`. |
| `treasury_yield` | zero-coupon price/face/maturity/settlement. | `dict` شامل `DiscountFactor,EffectiveAnnualYield,ContinuousYield,SimpleAnnualYield,BankDiscountYield,MacaulayDuration,ModifiedDuration,Convexity,DV01,DaysToMaturity/Tenor`. | قیمت/face/date/day-count نامعتبر `ValueError`; مثال deterministic. |
| `bond_price` | یا `cashflows` صریح، یا پارامترهای ساخت schedule؛ `annual_yield`; `price_type`. | `float` clean یا dirty price. | cashflow/rate/frequency/date نامعتبر `ValueError`; مثال `bond_price(0.2, [(date(...), amount)], ...)`. |
| `yield_to_maturity` | همان schedule + `price`; solver tolerance/iterations. | `float` annual yield با compounding انتخابی. | price خارج bounds/عدم bracket یا عدم همگرایی `ValueError`; مثال round-trip فصل درآمد ثابت. |
| `bond_analytics` | `annual_yield=None` یعنی YTM از price؛ `bump_size: float=0.0001`. | `dict` با price/yield، `MacaulayDuration,ModifiedDuration,Convexity,DV01` و metadata schedule. | همان validation math؛ مثال deterministic. |
| `build_yield_curve` | nodeهای rate/discount، compounding، duplicate و monotonic guard. | `YieldCurve`; `node_metadata` و `diagnostics` با کلیدهای دقیق `input_node_count,node_count,duplicate_count,duplicate_policy,monotonic_discount_enforced`. | node کم/duplicate/discount غیرمثبت/non-monotonic `ValueError`; مثال curve. |
| `get_ifb_yield_table` | `category: str='treasury'` دستهٔ جدول صفحهٔ IFB. | `DataFrame[Symbol,Price,LastTradeJalali,LastTradeDate,PublishJalali,PublishDate,MaturityJalali,Maturity,Volume,ReferenceYTM,ReferenceSimpleYield,ReferenceSource]`; attrs provenance URL/time. | category/HTML/schema/connection typed؛ مثال comparison IFB. |
| `get_treasury_yields` | live universe؛ `min_volume`; `face_value_source`; maturity override/map؛ `allow_no_trade`; source. | `TREASURY_COLUMNS`: هویت/سررسید/تسویه/price provenance، چهار yield، duration/convexity/DV01، stale/status؛ attrs source/universe/fetch time. | `InvalidParameterError`, `StockNotFoundError/AmbiguousSymbolError`, `ConnectionError/DataParsingError`; مثال live اخزا. |
| `get_treasury_yield_history` | history OHLC؛ `max_requests` hard؛ `use_ifb_reference` فقط reference؛ settlement per row مگر override. | `TREASURY_HISTORY_COLUMNS` با `TradeDate,JalaliDate,Open,High,Low,Close,Final,Volume...` و analytics؛ attrs failures/request/provenance. | parameter/resolver/provider/parsing؛ partial در attrs/warning؛ مثال history. |
| `get_treasury_yields_history` | alias identity با signature کامل یکسان. | دقیقاً همان object/schema/attrs `get_treasury_yield_history`. | همان؛ `att.get_treasury_yields_history is att.get_treasury_yield_history`. |
| `get_yield_curve` | حداقل `min_nodes`; duplicate default volume-weighted؛ extrapolation opt-in. | `YieldCurve` calibrated از snapshot live؛ diagnostics و metadata nodeها provenance/no-lookahead را ثبت می‌کند. | node ناکافی/invalid curve `ValueError` و provider typed؛ مثال curve live. |
| `get_yield_curve_history` | curve جدا برای هر trade date؛ `maturity_map`, hard budget؛ بدون extrapolate عمومی. | panel `DataFrame` با `CURVE_HISTORY_COLUMNS`, `CurveID,CurveStatus,CurveError,CurveNodeCount` و flags no-lookahead؛ attrs failures/request. | parameter/budget/provider/curve errors؛ روز ناموفق در status/attrs؛ مثال curve history. |

### قرارداد API: اختیار معامله و فهرست ابزارها

```text
list_options(underlying=None, progress=True)
get_options_chain(underlying, fetch_oi=False, progress=True)
black_scholes_price(spot, strike, time_to_expiry, rate, volatility, option_type='call', dividend_yield=0.0, exercise_style='european')
black_scholes_greeks(spot, strike, time_to_expiry, rate, volatility, option_type='call', dividend_yield=0.0, exercise_style='european')
option_price_bounds(spot, strike, time_to_expiry, rate, option_type='call', dividend_yield=0.0, exercise_style='european')
implied_volatility(option_price, spot, strike, time_to_expiry, rate, option_type='call', dividend_yield=0.0, exercise_style='european', lower_volatility=0.0, upper_volatility=5.0, tolerance=1e-08, max_iterations=200)
get_option_market(exchange=0, underlying=None, progress=True, max_requests=1)
analyze_option_chain(options=None, underlying=None, spot=None, risk_free_rate=None, yield_curve=None, dividend_yield=0.0, valuation_date=None, exercise_style='european', parity_tolerance=None, liquidity_weights=None, progress=True, *, allow_unverified_freshness=True)
option_put_call_ratios(options, group_by='market')
get_option_history(symbol, start=None, end=None, limit=0, include_today=False, snapshot_path=None, progress=True, max_requests=3)
save_option_snapshot(path, options=None, exchange=0, progress=True, *, lock_timeout=10.0, stale_lock_seconds=300.0)
load_option_snapshots(path)
list_etfs(progress=True)
list_bonds(progress=True)
list_funds(fund_type=None, progress=True, *, listed_only=False)
list_listed_funds(progress=True)
list_indices(progress=True)
get_index_companies(index_name, progress=True)
```

| API | ورودی خاص | خروجی/schema/attrs | خطا و مثال |
|---|---|---|---|
| `list_options` | `underlying: str|None` filter نام underlying. | `DataFrame` قراردادها با هویت، `OptionType,Underlying*,Strike,BeginDate,EndDate,DaysToExpiry,ContractSize` و قیمت/حجم. | provider parse/connection یا frame تهی؛ مثال فصل اختیار. |
| `get_options_chain` | `underlying` اجباری؛ `fetch_oi=False` از fan-out OI جلوگیری می‌کند. | `dict` دقیقاً شامل `calls: DataFrame`, `puts: DataFrame`, `underlying_name`, `underlying_price`, `expiry_dates`, `market_time`; با `fetch_oi` ستون‌های `OpenInterest,ContractSize,BeginDate,EndDate`. | underlying/provider errors؛ مثال chain فصل اختیار. |
| `black_scholes_price` | scalar math params؛ European فقط. | `float` premium. | bounds/type/style نامعتبر `ValueError`; مثال deterministic. |
| `black_scholes_greeks` | همان math params. | `dict[Delta,Gamma,Vega,Vega1Pct,ThetaPerYear,ThetaPerDay,Rho,Rho100bp,Status]`; `Status='ok'` یا `undefined_at_expiry_or_zero_volatility`. | constraint نامعتبر `ValueError`; مثال Greeks. |
| `option_price_bounds` | بدون volatility؛ no-arbitrage bound. | tuple `(lower: float, upper: float)`. | `ValueError`; مثال deterministic با خروجی `(4.87705755, 100.0)`. |
| `implied_volatility` | premium + bracket/tolerance/iterations؛ `tolerance>0`, `max_iterations` عدد صحیح مثبت و `0<=lower<upper`. | `dict` با `ImpliedVolatility,Status,Iterations`; statusهای `ok/missing/expiry/out_of_bounds/no_bracket/non_converged` و کلیدهای تشخیصی اختیاری. | premium ناموجود/خارج bounds و عدم همگرایی status هستند، نه exception؛ فقط constraint/style/bracket نامعتبر `ValueError`; مثال IV. |
| `get_option_market` | `exchange: int=0`; underlying filter؛ `max_requests=1` bulk. | `DataFrame[InsCode,PairID,PairSequence,ISIN,Symbol,Name,OptionType,UnderlyingInsCode,UnderlyingSymbol,UnderlyingName,ContractSize,Strike,BeginDate,EndDate,DaysToExpiry,Last,Close,Yesterday,Volume,Value,TradeCount,NotionalValue,OpenInterest,YesterdayOpenInterest,BidPrice,AskPrice,BidVolume,AskVolume,UnderlyingLast,UnderlyingClose,Price,PriceSource,AsOf,AsOfSource,SnapshotFreshnessKnown,PriceFreshnessKnown,Stale,NoTrade,AnalyticsEligible,AnalyticsEligibilityReason,MetadataConflict,Source]`; attrs snapshot provenance. | exchange/budget/filter `InvalidParameterError`; provider typed؛ مثال snapshot. |
| `analyze_option_chain` | `options=None` fetch می‌کند؛ spot/rate/curve overrides؛ `allow_unverified_freshness` explicit risk switch. | input columns + `TimeToExpiry,Spot,RiskFreeRate,DividendYield,ImpliedVolatility*`, Greeks per unit/contract، spread/depth/liquidity، `ParityResidual,ParityStatus,ImpliedForward,AnalyticsReliability`; attrs assumptions/warnings. | input type `TypeError`; math/freshness/rate/column problems `ValueError`; provider errors if fetch؛ مثال حرفه‌ای. |
| `option_put_call_ratios` | `options: DataFrame` از یک `AsOf` اتمیک؛ `group_by` دقیقاً یکی از `market,underlying,expiry,underlying_expiry`. | `DataFrame` با call/put volume/value/OI، `PCRVolume,PCRValue,PCROpenInterest` و statusهای دقیق `PCRVolumeStatus,PCRValueStatus,PCROpenInterestStatus`; attrs coverage/source ورودی. | ستون/group/AsOf یا قرارداد تکراری نامعتبر `ValueError` و نوع غیرDataFrame `TypeError`; مثال PCR. |
| `get_option_history` | قرارداد دقیق؛ server history + `include_today`; `snapshot_path` فقط join snapshotهای opt-in؛ budget. | `DataFrame[Timestamp,InsCode,Symbol,Open,High,Low,Close,Last,Volume,Value,TradeCount,OpenInterest,BidPrice,AskPrice,BidVolume,AskVolume,UnderlyingLast,UnderlyingClose,ContractSize,Strike,EndDate,Price,PriceSource,Source,AsOf,Stale,NoTrade,AnalyticsEligible]`; attrs failures/no-lookahead. | selector/date/budget/provider/snapshot schema errors؛ مثال تاریخچه اختیار. |
| `save_option_snapshot` | `options=None` یک fetch؛ lock timeout نامنفی و stale lock مثبت. | `DataFrame` ترکیب dedupeشده با `OPTION_COLUMNS`; attrs `schema_version,source,path`. فایل JSON versioned با lock و replace اتمیک نوشته می‌شود. | parent گم‌شده `FileNotFoundError`، options غیرDataFrame `TypeError`، مقدار نامعتبر `ValueError`، قفل `TimeoutError`؛ provider اگر fetch؛ مثال snapshot. |
| `load_option_snapshots` | `path` JSON versioned. | `DataFrame` با `OPTION_COLUMNS` و attrs؛ فایل گم‌شده **خطا نیست** و frame تهی با `attrs['status']='missing'` می‌دهد. | JSON خراب `JSONDecodeError` و version ناسازگار `ValueError`; مثال history. |
| `list_etfs` | فقط `progress`. | `DataFrame[InsCode,ISIN,Symbol,Name,Last,Close,Yesterday,Volume,Value,TradeCount,Low,High,NAV,NAV_Discount,Change,ChangePct,MarketCode]`. | provider typed/empty؛ مثال `list_etfs().query("NAV_Discount < -1")`. |
| `list_bonds` | فقط `progress`. | `DataFrame[InsCode,ISIN,Symbol,Name,BondType,Ticker,MaturityJalali,MaturityGregorian,DaysToMaturity,Last,Close,Yesterday,Volume,Value,TradeCount,Change,ChangePct]`. | parse/provider؛ maturity نامعلوم nullable؛ مثال فصل ابزارها. |
| `list_funds` | `fund_type: str|list|None` از categories settings؛ `listed_only=False`; listed_only با type filter قابل ترکیب نیست. | registry rich funds (NAV/returns/composition/manager) بدون تضمین InsCode؛ با `listed_only=True` دقیقاً schema `list_listed_funds`. attrs `no_fuzzy_join=True`. | type/category/combo نامعتبر `ValueError`; provider errors؛ مثال funds. |
| `list_listed_funds` | فقط `progress`; یک MarketWatch bulk. | `LISTED_FUND_COLUMNS`؛ attrs `no_fuzzy_join=True,registry_joined=False`. | connection/parsing؛ مثال فصل صندوق. |
| `list_indices` | فقط `progress`. | `DataFrame[Name,InsCode,Value,High,Low,Change,ChangePct]`. | provider typed/empty؛ مثال شاخص. |
| `get_index_companies` | `index_name: str` فارسی یا InsCode. | `DataFrame[Symbol,Name,InsCode,Close,Yesterday,Last]`. | index گم‌شده/provider در مسیر legacy frame تهی/پیام؛ مثال فصل شاخص. |

### قرارداد aliasها و wrapperهای backward-compatible

aliasهای این جدول مدخل مستقل دارند تا signature قدیمی و تفاوت رفتاری مخفی نماند.
تمام پارامترها type/default/constraint تابع target را دارند؛ فقط تفاوت صریح جدول
override است.

```text
stock(symbol='', start=None, end=None, limit=0, raw=False, auto_adjust=True, output_type='standard', date_format='jalali', progress=True, save_to_file=False, dropna=True, adjust_volume=False, return_type=None, ascending=True, save_path=None, include_today=False, *, ins_code=None, asset_type='auto', **kwargs)
stock_RI(symbol='', start=None, end=None, limit=0, raw=False, output_type='standard', date_format='jalali', progress=True, save_to_file=False, dropna=True, ascending=True, save_path=None, include_today=False, *, ins_code=None, asset_type='auto', **kwargs)
stock_RL(symbol='', start=None, end=None, limit=0, raw=False, output_type='standard', date_format='jalali', progress=True, save_to_file=False, dropna=True, ascending=True, save_path=None, include_today=False, *, ins_code=None, asset_type='auto', **kwargs)
stock_capital_increase(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
stock_intraday(symbol='شتران', interval='1min', start=None, end=None, progress=True, **kwargs)
stockdetail(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
stock_information(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
stock_statistics(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
stock_introduction(symbol='', *, ins_code=None, asset_type='auto', **kwargs)
stocklist(bourse=True, farabourse=True, payeh=True, haghe_taqadom=False, sandogh=False, bonds=False, options=False, mortgage=False, commodity=False, energy=False, payeh_color=None, output='dataframe', progress=True, **kwargs)
shareholders(symbol='', date=None, include_id=False, *, ins_code=None, asset_type='auto', **kwargs)
currency_coin(name='', start=None, end=None, limit=0, output_type='standard', date_format='jalali', progress=True, save_to_file=False, dropna=True, return_type=None, ascending=True, save_path=None, **kwargs)
market_watch()
market_client_type()
market_data()
```

| alias/wrapper | target و تفاوت | خروجی/schema/attrs | خطا و مثال |
|---|---|---|---|
| `stock` | target `get_history`; همان signature و implementation history. | همان DataFrame/attrs. | همان خطاها؛ `att.stock("فملی", limit=10)`. |
| `stock_RI` | target `get_client_type`. | همان DataFrame/attrs. | همان؛ `att.stock_RI("فملی", limit=10)`. |
| `stock_RL` | wrapper compatibility که به `stock_RI` delegate می‌کند؛ identity alias نیست ولی signature برابر است. | همان DataFrame/attrs. | همان؛ برای کد جدید `get_client_type`. |
| `stock_capital_increase` | target canonical `get_capital_increase`. | همان frame/None قدیمی. | همان. |
| `stock_intraday` | target `get_intraday`; signature برابر. | همان tick/candle frame. | همان. |
| `stockdetail` | target `get_detail`. | همان key/value frame یا `None`. | همان. |
| `stock_information` | target `get_info`. | همان key/value frame یا `None`. | همان. |
| `stock_statistics` | target `get_stats`. | همان key/value frame یا `None`. | همان. |
| `stock_introduction` | target `get_introduction`; wrapper legacy unsupported. | هیچ خروجی موفق. | همیشه `UnsupportedDataSourceError` پیش از I/O. |
| `stocklist` | target `get_symbols`; همان signature و aliasهای kwargs. | همان فهرست. | همان. |
| `shareholders` | target `get_shareholders`. | همان frame/None. | همان. |
| `currency_coin` | target `get_currency`. | همان frame/MultiIndex و source TGJU. | همان. |
| `market_watch` | تابع صفرآرگومان canonical قدیمی snapshot؛ target مفهومی `get_market_snapshot`. | `dict[stocks,order_book,market_time,...]`; ستون‌های legacy `Yesterday/BaseVolume/Change` حفظ شده و ستون‌های corrected additive هستند. | `ConnectionError/DataParsingError`; `snapshot=att.market_watch()`. |
| `market_client_type` | تابع صفرآرگومان bulk؛ target مفهومی `get_market_client_type`. | `CLIENT_COLUMNS` DataFrame. | typed provider errors. |
| `market_data` | wrapper deprecated صفرآرگومان به `market_watch`; identity alias نیست. | همان dict. | همان؛ برای کد جدید `get_market_snapshot/get_live_market`. |

دو alias identity غیرlegacy نیز قبلاً مدخل دارند:
`get_orderbook_history is get_order_book_history` و
`get_treasury_yields_history is get_treasury_yield_history`. تفاوت signature یا
خروجی ندارند.

signature constructor exceptionها نیز دقیقاً چنین است:

```text
AlgotikTSEError(*args)
AmbiguousSymbolError(*args)
ConnectionError(*args)
DataParsingError(*args)
InvalidParameterError(*args)
StockNotFoundError(*args)
UnsupportedDataSourceError(*args)
```

## الگوهای کاربردی

### فیلتر قدرت خریدار حقیقی با نقدشوندگی

```python
live = att.get_live_market()
screen = live.loc[
    (live["IndividualPower"] > 1.5)
    & (live["Value"] > 50_000_000_000)
    & live["is_realtime_fresh"].fillna(False)
].sort_values("EstimatedNetIndividualFlow", ascending=False)

print(screen[[
    "Symbol", "Last", "ChangePct", "IndividualPower",
    "EstimatedNetIndividualFlow", "SpreadBps", "L5Imbalance",
]])
```

### backtest بدون look-ahead

```python
db = "research.sqlite"
att.save_market_snapshot(db)

fund = att.get_market_fundamentals_history(db, symbols="فملی")
assert fund.attrs["no_lookahead"] is True
assert fund.attrs["current_eps_used"] is False

curves = att.get_yield_curve_history(
    start="1403-01-01", end="1403-03-31", max_requests=100, progress=False
)
safe_curves = curves.loc[curves["CurveNoLookahead"].fillna(False)]
```

### مانیتور بازار و archive مستقل

```python
db = "monitor.sqlite"

for event in att.watch_market(
    interval=3,
    max_updates=20,
    record_to=db,
    notifications=("messages", "state"),
):
    if event.kind in {"initial", "delta"}:
        print(event.sequence, len(event.changed_inscodes))

# archive_to باید روی helper مستقل فعال شود.
att.get_market_messages(flow=0, top=50, archive_to=db)
messages = att.get_market_messages_history(db, flow=0)
```

## منابع داده

| منبع | استفاده |
|---|---|
| TSETMC (`tsetmc.com` و subdomainهای رسمی) | قیمت، market watch، client type، سفارش، trades، پیام، وضعیت، ابزار، صندوق و اطلاعات بازار |
| فرابورس ایران (`ifb.ir/ytm.aspx`) | جدول مرجع YTM برای مقایسه/دسته‌بندی اوراق؛ منبع مجاز و با provenance جدا |
| TGJU (`api.tgju.org`) | فقط API legacy ارز و سکه |

کدال منبع این پکیج نیست؛ حتی endpointهای proxyشدهٔ آن زیر host دیگر در boundary شبکه رد می‌شوند.

## تست و مشارکت

تست پیش‌فرض کاملاً آفلاین است:

```bash
python -m pytest -m "not online"
```

یا:

```bash
make test
```

smoke آنلاین محدود و opt-in است:

```bash
python -m pytest -m online --timeout=30
```

تست آنلاین به وضعیت بازار/provider وابسته است و جایگزین تست deterministic آفلاین نیست. پیش از PR:

```bash
python -m pytest tests/test_release_offline.py -q
python -m pytest -m "not online" -q
```

برای مشارکت، issue یا pull request در [GitHub](https://github.com/mohsenalipour/algotik_tse) باز کنید. انتشار PyPI فقط با مسیر دستی و تأیید صریح انجام می‌شود؛ target عادی `release` صرفاً artifact محلی می‌سازد و upload نمی‌کند.

## مجوز و ارتباط

این پروژه تحت [GNU General Public License v3](LICENSE) منتشر می‌شود.

- وب‌سایت: [algotik.com](https://algotik.com)
- تلگرام: [t.me/algotik](https://t.me/algotik)
- نویسنده: Mohsen Alipour — `alipour@algotik.ir`
