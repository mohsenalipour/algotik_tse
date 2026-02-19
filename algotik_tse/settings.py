import datetime


class Settings:
    def __init__(self):
        self.today = datetime.date.today().isoformat()
        self.headers = {
            "User-Agent": "Mozilla/108.0.1 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"
        }
        self.en_weekdays = {
            0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday",
        }
        self.fa_weekdays = {
            0: "دوشنبه",
            1: "سه شنبه",
            2: "چهارشنبه",
            3: "پنجشنبه",
            4: "جمعه",
            5: "شنبه",
            6: "یکشنبه",
        }

        self.index_names = [
            "شاخص کل",
            "شاخص هم وزن",
            "شاخص کل هم وزن",
            "شاخص هموزن",
            "شاخص کل هموزن",
            "شاخص کل هم\u200cوزن",
            "شاخص قیمت وزنی-ارزشی",
            "شاخص قیمت هم وزن",
            "شاخص قیمت هموزن",
            "شاخص قیمت هم\u200cوزن",
            "شاخص شناور آزاد",
            "شاخص شناور",
            "شاخص بازار اول",
            "شاخص بازار دوم",
            "شاخص صنعت",
            "شاخص 30 شرکت بزرگ",
            "شاخص سی شرکت بزرگ",
            "شاخص ۳۰ شرکت بزرگ",
            "شاخص ۵۰ شرکت فعال",
            "شاخص پنجاه شرکت فعال",
            "شاخص 50 شرکت فعال",
            "شاخص 50 شرکت فعال بورس",
            "شاخص پنجاه شرکت فعال بورس",
            "شاخص ۵۰ شرکت فعال بورس",
        ]
        self.industry_index = [
            "شاخص صنعت فلزات اساسی",
            "شاخص فلزات اساسی",
            "شاخص صنعت سیمان",
            "شاخص سیمان",
            "شاخص صنعت خودرو",
            "شاخص خودرو",
            "شاخص صنعت شیمیایی",
            "شاخص شیمیایی",
            "شاخص صنعت وسایل ارتباطی",
            "شاخص وسایل ارتباطی",
            "شاخص صنعت سایر مالی",
            "شاخص سایر مالی",
            "شاخص صنعت منسوجات",
            "شاخص منسوجات",
            "شاخص صنعت کاشی و سرامیک",
            "شاخص کاشی و سرامیک",
            "شاخص صنعت انتشار و چاپ",
            "شاخص انتشار و چاپ",
            "شاخص صنعت معادن",
            "شاخص معادن",
            "شاخص صنعت محصولات چرمی",
            "شاخص محصولات چرمی",
        ]

        self.url_search = "https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{}"
        self.url_detail = "http://old.tsetmc.com/Loader.aspx?Partree=15131M&i={}"
        self.url_stock_list = "http://old.tsetmc.com/Loader.aspx?ParTree=151114"
        self.url_price_history = (
            "http://old.tsetmc.com/tsev2/data/Export-txt.aspx?t=i&a=1&b=0&i={}"
        )
        self.url_index_history = (
            "http://old.tsetmc.com/tsev2/chart/data/IndexFinancial.aspx?i={}&t=ph"
        )
        self.url_industry_history = (
            "https://cdn.tsetmc.com/api/Index/GetIndexB2History/{}"
        )
        self.url_industry_intra = (
            "https://cdn.tsetmc.com/api/Index/GetIndexB1LastDay/{}"
        )
        self.url_client_type = "http://old.tsetmc.com/tsev2/data/clienttype.aspx?i={}"
        self.url_last_share_holders = (
            "https://cdn.tsetmc.com/api/Shareholder/GetInstrumentShareHolderLast/{}"
        )
        self.url_share_holders_history = "https://cdn.tsetmc.com/api/Shareholder/{}/{}"
        self.url_capital_increase = (
            "https://cdn.tsetmc.com/api/Instrument/GetInstrumentShareChange/{}"
        )
        self.url_instrument_information = (
            "https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/{}"
        )
        self.url_instrument_statistics = (
            "https://cdn.tsetmc.com/api/MarketData/GetInstrumentStatistic/{}"
        )
        self.url_currency_from_tgju = (
            "https://api.tgju.org/v1/market/indicator/summary-table-data/{}"
        )
        self.url_sekke_from_tgju = (
            "https://api.tgju.org/v1/market/indicator/summary-table-data/sekee"
        )
        self.url_market_data_live = (
            "https://old.tsetmc.com/tsev2/data/MarketWatchPlus.aspx"
        )
        self.url_market_watch_init = (
            "https://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0"
        )
        self.url_client_type_all = (
            "https://old.tsetmc.com/tsev2/data/ClientTypeAll.aspx"
        )
        self.url_closing_price_all = (
            "https://members.tsetmc.com/tsev2/data/ClosingPriceAll.aspx"
        )
        self.url_intraday_trades = "https://cdn.tsetmc.com/api/Trade/GetTrade/{}"
        self.url_intraday_history = (
            "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceHistory/{}/{}"
        )
        self.url_option_info = (
            "https://cdn.tsetmc.com/api/Instrument/GetInstrumentOptionByInstrumentID/{}"
        )
        self.url_fund_list = "https://cdn.tsetmc.com/api/Fund/GetFunds/{}"

        self.fund_type_ids = {
            "equity": 6,
            "fixed_income": 4,
            "mixed": 7,
            "market_maker": 11,
            "venture": 12,
            "project": 13,
            "real_estate": 14,
            "commodity": 5,
            "private": 16,
            "fund_of_funds": 17,
        }
        self.fund_type_labels = {
            6: "equity",
            4: "fixed_income",
            7: "mixed",
            11: "market_maker",
            12: "venture",
            13: "project",
            14: "real_estate",
            5: "commodity",
            16: "private",
            17: "fund_of_funds",
        }

        self.currency_web_word = {
            "dollar": {"web_word": "price_dollar_rl", "persian_word": "دلار"},
            "euro": {"web_word": "price_eur", "persian_word": "یورو"},
            "yuan": {"web_word": "price_cny", "persian_word": "یوان"},
            "dirham": {"web_word": "price_aed", "persian_word": "درهم امارات"},
            "pound": {"web_word": "price_gbp", "persian_word": "پوند انگلیس"},
            "lira": {"web_word": "price_try", "persian_word": "لیر ترکیه"},
            "dollar-sana-sell": {
                "web_word": "sana_sell_usd",
                "persian_word": "دلار سنا-فروش",
            },
            "dollar-sana-buy": {
                "web_word": "sana_buy_usd",
                "persian_word": "دلار سنا-خرید",
            },
            "dollar-nima-buy": {
                "web_word": "nima_buy_usd",
                "persian_word": "دلار نیما-خرید",
            },
            "dollar-nima-sell": {
                "web_word": "nima_sell_usd",
                "persian_word": "دلار نیما-فروش",
            },
            "dollar-sarafimelli-buy": {
                "web_word": "sana_real_buy_usd",
                "persian_word": "دلار صرافی ملی-خرید",
            },
            "seke": {"web_word": "sekee", "persian_word": "سکه امامی"},
            "seke-bahar-azadi": {"web_word": "sekeb", "persian_word": "سکه بهار آزادی"},
            "nim-seke": {"web_word": "nim", "persian_word": "نیم سکه"},
            "rob-seke": {"web_word": "rob", "persian_word": "ربع سکه"},
            "seke-gerami": {"web_word": "gerami", "persian_word": "سکه گرمی"},
        }
        self.currency_persian = {
            "دلار": "dollar",
            "یورو": "euro",
            "یوان": "yuan",
            "درهم": "dirham",
            "پوند": "pound",
            "لیر": "lira",
            "دلار سنا فروش": "dollar-sana-sell",
            "دلار سنا خرید": "dollar-sana-buy",
            "دلار نیما خرید": "dollar-nima-buy",
            "دلار نیما فروش": "dollar-nima-sell",
            "دلار صرافی ملی": "dollar-sarafimelli-buy",
            "سکه": "seke",
            "سکه بهار آزادی": "seke-bahar-azadi",
            "نیم سکه": "nim-seke",
            "ربع سکه": "rob-seke",
            "سکه گرمی": "seke-gerami",
        }
        self.payeh_market_color_num = {"زرد": [0, 1], "نارنجی": [1, 2], "قرمز": [2, 4]}
        self.payeh_market_color = [
            "بازار پايه زرد فرابورس",
            "بازار پايه نارنجي فرابورس",
            "بازار پایه قرمز فرابورس",
            "بازار پايه قرمز فرابورس",
        ]

        # ── HTTP Client Settings ──────────────────────────────────────
        self.ssl_verify = False  # Set True to enable SSL certificate verification
        self.timeout = 10  # Request timeout in seconds
        self.max_retries = 3  # Number of retries on transient HTTP errors
        self.retry_backoff_factor = 0.3  # Exponential backoff factor between retries
        self.rate_limit_delay = 0.3  # Minimum seconds between consecutive requests


settings = Settings()
