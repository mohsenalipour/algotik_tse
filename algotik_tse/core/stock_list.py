import requests
import warnings
from io import StringIO
import pandas as pd
from persiantools import characters
from algotik_tse.settings import settings
from algotik_tse.http_client import safe_get

warnings.simplefilter(action="ignore", category=FutureWarning)


# ── ISIN prefix → asset type mapping ─────────────────────────
_ISIN_STOCKS = ["IRO1", "IRO2", "IRO3", "IRO4", "IRO5", "IRO7"]
_ISIN_RIGHTS = ["IRR1", "IRR3", "IRR5", "IRR7"]
_ISIN_FUNDS = ["IRT1", "IRT3", "IRTE", "IRTK"]
_ISIN_BONDS = ["IRB3", "IRB4", "IRB5", "IRB6", "IRB7"]
_ISIN_OPTIONS = ["IRO9", "IROF", "IROA", "IROB"]
_ISIN_MORTGAGE = ["IRO6"]
_ISIN_COMMODITY = ["IRBK", "IRK1"]
_ISIN_ENERGY = ["IRBE"]


def _split_symbol(text):
    """Extract the ticker symbol from the raw HTML name field.

    Expected formats:
      - "شرکت نام (نماد)"             → "نماد"
      - "شرکت نام (هلدینگ) (نماد)"    → "نماد"  (holding companies)
      - "اوراق ... (اراد271)"         → "اراد271"
      - "ضهرم خرداد 130 (ضهرم1115)"   → "ضهرم1115"
      - "نماد"                        → "نماد"  (fallback)
    """
    try:
        parts = text.split("(")
        if len(parts) >= 3 and ("هلد" in parts[1] or "سهامی" in parts[1]):
            return parts[2].split(")")[0].strip()
        elif len(parts) >= 2:
            return parts[1].split(")")[0].strip()
        else:
            return text.strip()
    except (IndexError, AttributeError):
        return str(text).strip()


def stocklist(
    bourse=True,
    farabourse=True,
    payeh=True,
    haghe_taqadom=False,
    sandogh=False,
    bonds=False,
    options=False,
    mortgage=False,
    commodity=False,
    energy=False,
    payeh_color=None,
    output="dataframe",
    progress=True,
    **kwargs
):
    """
    Get all symbols in bourse, farabourse, payeh, and additional asset classes
    from tsetmc.

    Market filters (stocks):
    :param bourse:          Include Bourse (TSE) stocks. Default True.
                            English alias: main_market
    :param farabourse:      Include Fara Bourse (OTC) stocks. Default True.
                            English alias: otc
    :param payeh:           Include Base Market (Payeh) stocks. Default True.
                            English alias: base_market
    :param payeh_color:     Filter Base Market by tier/color.
                            Accepts str ('زرد','نارنجی','قرمز') or list.
                            English alias: base_market_tier

    Asset-class filters:
    :param haghe_taqadom:   Include subscription rights (حق تقدم). Default False.
                            English alias: rights
    :param sandogh:         Include ETFs and investment funds (صندوق). Default False.
                            English alias: funds
    :param bonds:           Include bonds, sukuk, treasury bills & govt bonds
                            (اوراق بدهی: اخزا، اراد، صکوک). Default False.
    :param options:         Include stock & fund options — calls and puts
                            (اختیار معامله). Default False.
    :param mortgage:        Include housing facility certificates
                            (تسهیلات مسکن). Default False.
    :param commodity:       Include commodity-backed certificates & contracts
                            (گواهی‌های کالایی). Default False.
    :param energy:          Include energy certificates
                            (گواهی‌های برق/انرژی). Default False.

    Output control:
    :param output:          'dataframe' (default) or 'list' (symbol names only).
    :param progress:        Show progress messages. Default True.

    :return: pandas DataFrame (with 'asset_type' column) or list of symbols.
    """
    # ── English aliases for Finglish parameter names ──────────
    if "main_market" in kwargs:
        bourse = kwargs.pop("main_market")
    if "otc" in kwargs:
        farabourse = kwargs.pop("otc")
    if "base_market" in kwargs:
        payeh = kwargs.pop("base_market")
    if "rights" in kwargs:
        haghe_taqadom = kwargs.pop("rights")
    if "funds" in kwargs:
        sandogh = kwargs.pop("funds")
    if "base_market_tier" in kwargs:
        payeh_color = kwargs.pop("base_market_tier")

    # ── Validate at least one category selected ───────────────
    any_selected = (
        bourse
        or farabourse
        or payeh
        or haghe_taqadom
        or sandogh
        or bonds
        or options
        or mortgage
        or commodity
        or energy
    )
    if not any_selected:
        print("You should select at least one market or asset type!")
        return None

    # ── Build human-readable label ────────────────────────────
    _labels = []
    if bourse:
        _labels.append("bourse")
    if farabourse:
        _labels.append("farabourse")
    if payeh:
        _labels.append("payeh")
    if haghe_taqadom:
        _labels.append("rights")
    if sandogh:
        _labels.append("funds")
    if bonds:
        _labels.append("bonds")
    if options:
        _labels.append("options")
    if mortgage:
        _labels.append("mortgage")
    if commodity:
        _labels.append("commodity")
    if energy:
        _labels.append("energy")
    markets_text = ", ".join(_labels)

    if progress:
        print("Getting all of {} symbols...".format(markets_text), flush=True)

    try:
        req = safe_get(settings.url_stock_list)
        df = pd.read_html(StringIO(req.text), extract_links="body")[0]

        df.rename(
            columns={
                "کد 12 رقمی نماد [Instrument ISIN]": "instrument_isin",
                "کد 4 رقمی شرکت [Company Code]": "company_code",
                "نام انگلیسی [English Name]": "english_name",
                "کد 12 رقمی شرکت [Company ISIN]": "company_isin",
                "بازار": "market",
                "گروه صنعت": "industry_group",
                "نوع [Type]": "type",
            },
            inplace=True,
        )
        df["name"] = df["نماد [Name]"].str[0]
        df["instrument_isin"] = df["instrument_isin"].str[0]
        df["company_code"] = df["company_code"].str[0]
        df["english_name"] = df["english_name"].str[0]
        df["company_isin"] = df["company_isin"].str[0]
        df["market"] = df["market"].str[0]
        df["industry_group"] = df["industry_group"].str[0]
        df["instrument_id"] = df["نماد [Name]"].str[-1]
        df["instrument_id"] = df["instrument_id"].str.strip().str.split("=").str[-1]
        df["instrument_id"] = df["instrument_id"].str.split("/").str[-1]

        df.drop(columns=["نماد [Name]", "type"], inplace=True)

        # Pre-compute ISIN prefix column for efficient filtering
        isin_prefix = df["instrument_isin"].str.slice(stop=4)
        isin_is_primary = df["instrument_isin"].str.slice(-1) == "1"

        allowed_markets = []
        group_not_allowed = ["اوراق حق تقدم استفاده از تسهيلات مسكن"]
        not_all = ["بازار سوم فرابورس", "-", "بازار عادي آتي"]

        df_final = pd.DataFrame()

        # ── 1. Stocks (bourse / farabourse / payeh) ───────────
        if bourse or farabourse or payeh:
            if bourse:
                allowed_markets.extend(
                    [
                        "بازار دوم بورس",
                        "بازار اول (تابلوي فرعي) بورس",
                        "بازار اول (تابلوي اصلي) بورس",
                    ]
                )
            if farabourse:
                allowed_markets.extend(
                    [
                        "بازار اول فرابورس",
                        "شرکتهاي کوچک و متوسط فرابورس",
                        "بازار دوم فرابورس",
                        "بازار نوآفرين",
                    ]
                )
            if payeh:
                if isinstance(payeh_color, str):
                    list_of_payeh_market = settings.payeh_market_color[
                        settings.payeh_market_color_num[payeh_color][
                            0
                        ] : settings.payeh_market_color_num[payeh_color][1]
                    ]
                elif isinstance(payeh_color, list):
                    list_of_payeh_market = []
                    for color in payeh_color:
                        if color in settings.payeh_market_color_num.keys():
                            list_of_payeh_market.extend(
                                settings.payeh_market_color[
                                    settings.payeh_market_color_num[color][
                                        0
                                    ] : settings.payeh_market_color_num[color][1]
                                ]
                            )
                        else:
                            print("{} is not in payeh market.".format(color))
                            continue
                else:
                    list_of_payeh_market = settings.payeh_market_color
                allowed_markets.extend(list_of_payeh_market)

            mask = (
                isin_prefix.isin(_ISIN_STOCKS)
                & ~df["industry_group"].isin(group_not_allowed)
                & isin_is_primary
            )
            df_filtered = df[mask]
            df_filtered = df_filtered[~df_filtered["market"].isin(not_all)]
            df_filtered = df_filtered[df_filtered["market"].isin(allowed_markets)]
            df_filtered = df_filtered.assign(asset_type="stock")
            df_final = pd.concat([df_final, df_filtered])

        # ── 2. Subscription rights (حق تقدم) ─────────────────
        if haghe_taqadom:
            mask = (
                isin_prefix.isin(_ISIN_RIGHTS)
                & ~df["industry_group"].isin(group_not_allowed)
                & isin_is_primary
            )
            df_filtered = df[mask]
            df_filtered = df_filtered[~df_filtered["market"].isin(not_all)]
            df_filtered = df_filtered.assign(asset_type="right")
            df_final = pd.concat([df_final, df_filtered])

        # ── 3. ETFs & investment funds (صندوق) ────────────────
        if sandogh:
            mask = isin_prefix.isin(_ISIN_FUNDS) & isin_is_primary
            df_filtered = df[mask].assign(asset_type="fund")
            df_final = pd.concat([df_final, df_filtered])

        # ── 4. Bonds / Sukuk / Treasury bills (اوراق بدهی) ───
        if bonds:
            mask = isin_prefix.isin(_ISIN_BONDS) & isin_is_primary
            df_filtered = df[mask].assign(asset_type="bond")
            df_final = pd.concat([df_final, df_filtered])

        # ── 5. Options — calls & puts (اختیار معامله) ─────────
        if options:
            mask = isin_prefix.isin(_ISIN_OPTIONS) & isin_is_primary
            df_filtered = df[mask].assign(asset_type="option")
            df_final = pd.concat([df_final, df_filtered])

        # ── 6. Housing facility certificates (تسهیلات مسکن) ──
        if mortgage:
            mask = isin_prefix.isin(_ISIN_MORTGAGE) & isin_is_primary
            df_filtered = df[mask].assign(asset_type="mortgage")
            df_final = pd.concat([df_final, df_filtered])

        # ── 7. Commodity certificates (گواهی کالایی) ──────────
        if commodity:
            mask = isin_prefix.isin(_ISIN_COMMODITY) & isin_is_primary
            df_filtered = df[mask].assign(asset_type="commodity")
            df_final = pd.concat([df_final, df_filtered])

        # ── 8. Energy certificates (گواهی انرژی) ─────────────
        if energy:
            mask = isin_prefix.isin(_ISIN_ENERGY) & isin_is_primary
            df_filtered = df[mask].assign(asset_type="energy")
            df_final = pd.concat([df_final, df_filtered])

    except requests.exceptions.RequestException:
        print("Connection Error!!!")
        df_final = pd.DataFrame()
    except Exception as e:
        print("Error processing stock list: {}".format(e))
        df_final = pd.DataFrame()

    if df_final.shape[0] != 0:
        df_final["name"] = df_final["name"].str.strip().apply(characters.ar_to_fa)
        df_final["symbol"] = df_final["name"].apply(_split_symbol)
        df_final.set_index("symbol", drop=True, inplace=True)
        df_final["name"] = df_final["name"].str.split("(").str[0]
        df_final["name"] = df_final["name"].str.replace("\u200c", " ").str.strip()
        df_final["market"] = df_final["market"].str.strip().apply(characters.ar_to_fa)
        df_final["market"] = df_final["market"].str.replace("\u200c", " ").str.strip()
        df_final["industry_group"] = (
            df_final["industry_group"].str.strip().apply(characters.ar_to_fa)
        )
        df_final["industry_group"] = (
            df_final["industry_group"].str.replace("\u200c", " ").str.strip()
        )
        df_final = df_final.loc[
            :,
            [
                "name",
                "instrument_isin",
                "english_name",
                "company_code",
                "company_isin",
                "market",
                "industry_group",
                "asset_type",
                "instrument_id",
            ],
        ]

        if output == "dataframe":
            if progress:
                print(
                    "The dataframe of all {} symbols is ready! ({} symbols)".format(
                        markets_text, len(df_final)
                    )
                )
            return df_final
        elif output == "list":
            if progress:
                print(
                    "The list of all {} symbols is ready! ({} symbols)".format(
                        markets_text, len(df_final)
                    )
                )
            symbols_list = df_final.index.to_list()
            return symbols_list
        else:
            print("You should select output only in 'dataframe' or 'list'!!!")
            return None
    else:
        print("Connection Error!!!")
        return None
