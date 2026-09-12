import datetime as dt

import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import fixed_income as fi
from algotik_tse.core import instruments
from algotik_tse.core.parsers import parse_bond_name


def _market_snapshot():
    rows = [
        ("1", "IRO1ERAD", "اراد103", "مرابحه عام دولت103-ش.خ050821", 900000),
        ("2", "IRO1GAM1", "گام051115", "گواهي اعتبار مولد سپه14051130", 910000),
        ("3", "IRO1GAM2", "گام060216", "گواهي اعتبارمولد كشاورزي060231", 920000),
        ("4", "IRO1AKHZ", "اخزا070101", "اسناد خزانه-م2بودجه04-070101", 800000),
        ("5", "IRO1STCK", "فولاد", "فولاد مباركه اصفهان", 5000),
    ]
    columns = [
        "InsCode",
        "ISIN",
        "Symbol",
        "Name",
        "Last",
        "Close",
        "Yesterday",
        "Volume",
        "Value",
        "TradeCount",
        "Change",
        "ChangePct",
    ]
    data = []
    for ins, isin, symbol, name, price in rows:
        data.append(
            [ins, isin, symbol, name, price, price, price, 10, price * 10, 1, 0, 0]
        )
    return {"stocks": pd.DataFrame(data, columns=columns)}


def test_gam_names_support_six_and_eight_digit_maturities():
    full = parse_bond_name("گواهی اعتبار مولد سپه14051130")
    short = parse_bond_name("گواهي اعتبارمولد كشاورزي060231")
    symbol_only = parse_bond_name("گام051115")
    assert full["bond_type"] == "gam"
    assert full["maturity_jalali"] == "1405/11/30"
    assert short["maturity_jalali"] == "1406/02/31"
    assert symbol_only["maturity_jalali"] == "1405/11/15"


def test_list_bonds_adds_gam_without_changing_legacy_signature(monkeypatch):
    monkeypatch.setattr(instruments, "market_watch", _market_snapshot)
    result = att.list_bonds(progress=False)
    assert set(result["Symbol"]) == {"اراد103", "گام051115", "گام060216", "اخزا070101"}
    assert set(result.loc[result["Symbol"].str.startswith("گام"), "BondType"]) == {
        "gam"
    }


def test_list_debt_instruments_filters_erad_and_gam(monkeypatch):
    monkeypatch.setattr(instruments, "market_watch", _market_snapshot)
    result = att.list_debt_instruments(["erad", "gam"], progress=False)
    assert list(result["DebtType"]) == ["erad", "gam", "gam"]
    assert result.attrs["source"] == "tsetmc_market_watch"
    assert result.attrs["coverage"] == "current_market_snapshot"
    with pytest.raises(att.InvalidParameterError, match="debt_type"):
        att.list_debt_instruments("bond", progress=False)


IFB_ALL_HTML = """
<table id="ContentPlaceHolder1_grdytm">
<thead><tr><th>ردیف</th><th>نماد</th><th>قیمت</th><th>آخرین معامله</th>
<th>سررسید</th><th>YTM</th></tr></thead><tbody>
<tr><td>1</td><td>اراد103</td><td>900,000</td><td>1405-06-22</td><td>1405-08-21</td><td>35/20%</td></tr>
<tr><td>2</td><td>گام051115</td><td>910,000</td><td>1405-06-22</td><td>1405-11-15</td><td>27/10%</td></tr>
<tr><td>3</td><td>اخزا070101</td><td>800,000</td><td>1405-06-22</td><td>1407-01-01</td><td>30/00%</td></tr>
</tbody></table>
"""


def test_ifb_all_table_keeps_erad_and_gam():
    result = fi._parse_ifb_yield_html(IFB_ALL_HTML, "all")
    assert list(result["Symbol"]) == ["اراد103", "گام051115", "اخزا070101"]
    assert result.loc[result["Symbol"].eq("گام051115"), "ReferenceYTM"].iloc[
        0
    ] == pytest.approx(0.271)
    assert result["ReferenceSimpleYield"].isna().all()


def test_get_debt_yields_filters_without_inventing_cashflows(monkeypatch):
    table = fi._parse_ifb_yield_html(IFB_ALL_HTML, "all")
    monkeypatch.setattr(fi, "get_ifb_yield_table", lambda category: table)
    result = att.get_debt_yields(["erad", "gam"])
    assert list(result["DebtType"]) == ["erad", "gam"]
    assert result.attrs["cashflows_inferred"] is False
    assert result.attrs["classification"] == "exact_symbol_prefix"
    with pytest.raises(att.InvalidParameterError, match="debt_type"):
        att.get_debt_yields("murabaha")
