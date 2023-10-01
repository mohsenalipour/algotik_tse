class Settings:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/108.0.1 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
        self.en_weekdays = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday",
                            6: "Sunday"}
        self.fa_weekdays = {0: "دوشنبه", 1: "سه شنبه", 2: "چهارشنبه", 3: "پنجشنبه", 4: "جمعه", 5: "شنبه", 6: "یکشنبه"}

        self.index_names = ["شاخص کل", "شاخص هم وزن", "شاخص کل هم وزن", "شاخص هموزن", "شاخص کل هموزن",
                            "شاخص کل هم\u200cوزن",
                            "شاخص قیمت وزنی-ارزشی", "شاخص قیمت هم وزن", "شاخص قیمت هموزن", "شاخص قیمت هم\u200cوزن",
                            "شاخص شناور آزاد", "شاخص شناور", "شاخص بازار اول", "شاخص بازار دوم", "شاخص صنعت",
                            "شاخص 30 شرکت بزرگ", "شاخص سی شرکت بزرگ", "شاخص ۳۰ شرکت بزرگ",
                            "شاخص ۵۰ شرکت فعال", "شاخص پنجاه شرکت فعال", "شاخص 50 شرکت فعال",
                            "شاخص 50 شرکت فعال بورس", "شاخص پنجاه شرکت فعال بورس", "شاخص ۵۰ شرکت فعال بورس"]

        self.url_search = 'http://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{}'
        self.url_detail = 'http://old.tsetmc.com/Loader.aspx?Partree=15131M&i={}'
        self.url_stock_list = 'http://old.tsetmc.com/Loader.aspx?ParTree=151114'
        self.url_price_history = 'http://old.tsetmc.com/tsev2/data/Export-txt.aspx?t=i&a=1&b=0&i={}'
        self.url_index_history = 'http://old.tsetmc.com/tsev2/chart/data/IndexFinancial.aspx?i={}&t=ph'
        self.url_client_type = 'http://old.tsetmc.com/tsev2/data/clienttype.aspx?i={}'
