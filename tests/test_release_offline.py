"""Offline release gates for security, compatibility and packaging metadata."""

import datetime
import inspect
import math
from pathlib import Path
import re
import threading
import time

import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse import _clock
from algotik_tse import http_client
from algotik_tse.settings import Settings, settings

pytestmark = pytest.mark.release
ROOT = Path(__file__).resolve().parents[1]


def test_version_is_synchronized():
    assert att.__version__ == "1.1.1"
    assert 'version="1.1.1"' in (ROOT / "setup.py").read_text(encoding="utf-8")
    assert "current_version = 1.1.1" in (ROOT / "setup.cfg").read_text(encoding="utf-8")
    history = (ROOT / "HISTORY.rst").read_text(encoding="utf-8")
    assert "1.1.1 (2026-08-25)" in history
    assert "1.1.0 (2026-08-24)" in history


@pytest.mark.parametrize(
    "name",
    [
        "get_history",
        "get_client_type",
        "get_live_market",
        "get_order_book_history",
        "get_queue_history",
        "watch_market",
        "save_market_snapshot",
        "get_treasury_yields",
        "get_yield_curve_history",
        "get_option_market",
        "analyze_option_chain",
        "option_price_bounds",
        "save_option_snapshot",
    ],
)
def test_public_release_exports_import_directly(name):
    assert callable(getattr(att, name))


def test_required_aliases_are_identity_preserving():
    assert att.get_orderbook_history is att.get_order_book_history
    assert att.get_treasury_yields_history is att.get_treasury_yield_history
    # market_data is intentionally a deprecated compatibility wrapper rather
    # than an identity alias; both zero-argument signatures remain stable.
    assert str(inspect.signature(att.market_data)) == "()"
    assert str(inspect.signature(att.market_watch)) == "()"


def test_legacy_signatures_remain_exact():
    assert str(inspect.signature(att.list_bonds)) == "(progress=True)"
    assert str(inspect.signature(att.get_market_snapshot)) == "(*args, **kwargs)"
    assert str(inspect.signature(att.get_market_client_type)) == "(*args, **kwargs)"
    assert str(inspect.signature(att.get_intraday)) == (
        "(symbol='شتران', interval='1min', start=None, end=None, "
        "progress=True, **kwargs)"
    )
    assert "include_today=False" in str(inspect.signature(att.get_history))
    assert "include_today=False" in str(inspect.signature(att.get_client_type))


def test_option_price_bounds_is_direct_and_deterministic():
    lower, upper = att.option_price_bounds(100, 100, 1, 0.05, "call", 0.0)
    assert lower == pytest.approx(4.87705755)
    assert upper == pytest.approx(100.0)


def test_tehran_clock_handles_utc_calendar_rollover(monkeypatch):
    monkeypatch.setattr(
        _clock,
        "_utc_now",
        lambda: datetime.datetime(2026, 8, 23, 20, 29, tzinfo=datetime.timezone.utc),
    )
    assert _clock.tehran_today() == datetime.date(2026, 8, 23)
    monkeypatch.setattr(
        _clock,
        "_utc_now",
        lambda: datetime.datetime(2026, 8, 23, 20, 31, tzinfo=datetime.timezone.utc),
    )
    assert _clock.tehran_today() == datetime.date(2026, 8, 24)


def test_tls_defaults_and_all_tsetmc_urls_are_https():
    configured = Settings()
    assert configured.ssl_verify is True
    urls = {
        name: value
        for name, value in vars(configured).items()
        if name.startswith("url_") and isinstance(value, str) and "tsetmc.com" in value
    }
    assert urls
    assert all(value.startswith("https://") for value in urls.values()), urls
    source = (ROOT / "algotik_tse" / "http_client.py").read_text(encoding="utf-8")
    assert "disable_warnings" not in source


class _FakeSession:
    def __init__(self, starts=None, entered=None, release=None):
        self.starts = starts if starts is not None else []
        self.entered = entered
        self.release = release
        self.closed = False
        self.headers = {}
        self.adapters = {}

    def mount(self, prefix, adapter):
        self.adapters[prefix] = adapter

    def get(self, url, **kwargs):
        self.starts.append((time.monotonic(), kwargs))
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(2)
        return object()

    def close(self):
        self.closed = True


def test_threaded_rate_spacing_and_explicit_tls_opt_out(monkeypatch):
    fake = _FakeSession()
    monkeypatch.setattr(http_client, "_session", fake)
    monkeypatch.setattr(settings, "rate_limit_delay", 0.04)
    monkeypatch.setattr(http_client, "_next_request_time", 0.0)
    threads = [
        threading.Thread(
            target=http_client.safe_get,
            args=("https://cdn.tsetmc.com/test",),
            kwargs={"verify": False},
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)
    assert not any(thread.is_alive() for thread in threads)
    assert fake.starts[1][0] - fake.starts[0][0] >= 0.035
    assert all(call[1]["verify"] is False for call in fake.starts)


def test_rate_scheduler_rechecks_after_early_sleep(monkeypatch):
    fake = _FakeSession()
    clock = {"now": 0.0}
    sleeps = []

    def early_sleep(seconds):
        sleeps.append(seconds)
        # Simulate two early Windows wakeups, then reach the requested deadline.
        clock["now"] += seconds / 2 if len(sleeps) <= 2 else seconds

    monkeypatch.setattr(http_client, "_session", fake)
    monkeypatch.setattr(settings, "rate_limit_delay", 1.0)
    monkeypatch.setattr(http_client, "_next_request_time", 1.0)
    monkeypatch.setattr(http_client.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(http_client.time, "sleep", early_sleep)
    http_client.safe_get("https://cdn.tsetmc.com/test")
    assert len(sleeps) == 3
    assert fake.starts[0][0] == pytest.approx(1.0)
    assert http_client._next_request_time == pytest.approx(2.0)


def test_reset_preserves_reserved_spacing_and_waits_for_inflight(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    starts = []
    first = _FakeSession(starts=starts, entered=entered, release=release)
    second = _FakeSession(starts=starts)
    monkeypatch.setattr(http_client, "_session", first)
    monkeypatch.setattr(http_client.requests, "Session", lambda: second)
    monkeypatch.setattr(settings, "rate_limit_delay", 0.08)
    monkeypatch.setattr(http_client, "_next_request_time", 0.0)
    requester = threading.Thread(
        target=http_client.safe_get, args=("https://cdn.tsetmc.com/test",)
    )
    requester.start()
    assert entered.wait(1)
    resetter = threading.Thread(target=http_client.reset_session)
    resetter.start()
    time.sleep(0.01)
    assert first.closed is False
    assert resetter.is_alive()
    release.set()
    requester.join(2)
    resetter.join(2)
    follower = threading.Thread(
        target=http_client.safe_get, args=("https://cdn.tsetmc.com/test",)
    )
    follower.start()
    follower.join(2)
    assert not any(thread.is_alive() for thread in (requester, resetter, follower))
    assert first.closed is True
    assert len(starts) == 2
    assert starts[1][0] - starts[0][0] >= 0.075
    assert http_client._session is second


def test_retry_adapter_is_always_mounted(monkeypatch):
    fake = _FakeSession()
    monkeypatch.setattr(http_client, "_session", None)
    monkeypatch.setattr(http_client.requests, "Session", lambda: fake)
    monkeypatch.setattr(settings, "max_retries", 4)
    session = http_client._get_session()
    assert session is fake
    assert set(fake.adapters) == {"http://", "https://"}
    assert fake.adapters["http://"] is fake.adapters["https://"]
    retries = fake.adapters["https://"].max_retries
    assert retries.total == 4
    assert retries.allowed_methods == frozenset(["GET"])
    assert set(retries.status_forcelist) == {429, 500, 502, 503, 504}


def test_retry_compatibility_branch_is_explicit(monkeypatch):
    calls = []

    def legacy_retry(**kwargs):
        calls.append(kwargs)
        if "allowed_methods" in kwargs:
            raise TypeError("legacy API")
        return kwargs

    monkeypatch.setattr(http_client, "Retry", legacy_retry)
    retry = http_client._build_retry_strategy(settings)
    assert "allowed_methods" in calls[0]
    assert retry["method_whitelist"] == frozenset(["GET"])


def test_event_history_rejects_unknown_watcher_kind(tmp_path):
    with pytest.raises(att.InvalidParameterError, match="unknown watcher event kind"):
        att.get_market_event_history(tmp_path / "missing.sqlite", kind="update")
    for kind in (None, "initial", "delta", "heartbeat", "resync"):
        assert att.get_market_event_history(
            tmp_path / "missing.sqlite", kind=kind
        ).empty


def test_release_files_prevent_accidental_publish_and_global_warning_filters():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert (
        "release: dist ## build release artifacts locally (never uploads)" in makefile
    )
    assert "publish: ## MANUAL:" in makefile
    assert "publish: dist" not in makefile
    assert makefile.count("twine upload") == 1
    assert "CONFIRM_PYPI_UPLOAD" in makefile
    for name in ("intraday.py", "stock_list.py", "stock_detail.py"):
        source = (ROOT / "algotik_tse" / "core" / name).read_text(encoding="utf-8")
        assert "warnings.simplefilter" not in source
        assert "warnings.filterwarnings" not in source


def test_ci_timeout_docs_and_gitignore_release_guards():
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    assert "timeout-minutes: 20" in workflow
    assert "--timeout=30" in workflow
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        ".claude/settings.local.json",
        "/AGENTS.md",
        "/market_profiles.xlsx",
        "/.tmp-review-*",
        "/.tmp_phase6_*",
    ):
        assert pattern in ignore
    readme_rst = (ROOT / "README.rst").read_text(encoding="utf-8")
    readme_md = (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'get_market_event_history(db, kind="delta"' in readme_md
    assert 'get_market_event_history(db, kind="update"' not in readme_md
    assert "archive_to=db" in readme_md
    assert "record_to" in readme_md and "archive_to" in readme_md
    assert "single authoritative guide" in readme_rst
    assert "README.md" in readme_rst
    assert len(readme_rst) < 1500


def test_manifest_has_release_denylist_and_no_test_recursion():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include tests" not in manifest
    for rule in (
        "prune tests",
        "prune .release-check",
        "recursive-exclude * .tmp*",
        "recursive-exclude * *.pdf",
        "recursive-exclude * *.xlsx",
    ):
        assert rule in manifest


def test_build_metadata_declares_supported_python_and_primary_readme():
    setup = (ROOT / "setup.py").read_text(encoding="utf-8")
    tox = (ROOT / "tox.ini").read_text(encoding="utf-8")
    assert 'python_requires=">=3.8"' in setup
    assert '"Programming Language :: Python :: 3.14"' in setup
    assert 'open("README.md"' in setup
    assert 'long_description_content_type="text/markdown"' in setup
    assert "read_history" not in setup
    assert "long_description=read_readme()" in setup
    assert "py314" in tox


def test_markdown_is_single_authoritative_reference_and_covers_public_exports():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "README.md` سند مرجع واحد" in readme
    assert "## Version 1.1.1" not in readme
    assert readme.count('<div dir="rtl" align="right">') == 1
    assert readme.rstrip().endswith("</div>")
    for badge in (
        "img.shields.io/pypi/v/algotik-tse.svg?cacheSeconds=300",
        "img.shields.io/pypi/pyversions/algotik-tse.svg",
        "static.pepy.tech/personalized-badge/algotik-tse",
        "img.shields.io/pypi/l/algotik-tse.svg",
        "results.pre-commit.ci/badge/github/mohsenalipour/algotik_tse/master.svg",
    ):
        assert badge in readme
    assert "get_codal_disclosures" not in readme
    assert 'notifications=("messages", "state", "codal")' not in readme
    assert "فقط برای حفظ import/signature قدیمی" in readme
    assert "UnsupportedDataSourceError" in readme
    assert "IsConfirmedDPS" in readme and "dps_available" in readme
    assert "price adjustment" in readme.lower()
    assert "ssl_verify = True" in readme
    assert "مسیر پوشه" in readme
    missing = [name for name in att.__all__ if name not in readme]
    assert missing == []


def test_markdown_covers_each_release_domain_with_examples_and_outputs():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required = (
        "## حل دقیق هویت نماد",
        "## قیمت و حقیقی/حقوقی؛ تاریخچه و زنده",
        "## معاملات ریز",
        "## سفارش و صف",
        "## Watcher و تحلیل کل بازار",
        "## تاریخچهٔ محلی SQLite",
        "## فاندامنتال بازار، صندوق و تعدیل قیمت",
        "## اخزا و درآمد ثابت",
        "## اختیار معامله",
        "خروجی نماینده",
        "DataFrame.attrs",
        "include_today=True",
        "get_market_fundamentals_history",
        "list_listed_funds",
        "get_latest_price_adjustment",
        "MacaulayDuration",
        "DV01",
        "ParityStatus",
        "PCROpenInterest",
        "option-snapshots.json",
    )
    for token in required:
        assert token in readme


def _stable_public_signature(obj):
    """Return the renderer-independent signature used by README.md."""
    try:
        signature = str(inspect.signature(obj))
    except (TypeError, ValueError):
        # Python does not expose a signature for bare Exception subclasses;
        # their documented constructor is the inherited Exception(*args).
        signature = "(*args)"
    return re.sub(r"<function safe_get at 0x[0-9A-Fa-f]+>", "safe_get", signature)


def test_markdown_has_exact_signature_and_contract_entry_for_every_callable():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    compact = re.sub(r"\s+", "", readme)
    contract_rows = set(
        re.findall(r"^\| `([A-Za-z_][A-Za-z0-9_]*)`", readme, flags=re.MULTILINE)
    )
    callables = {
        name: getattr(att, name) for name in att.__all__ if callable(getattr(att, name))
    }
    assert len(att.__all__) == 110
    assert len(callables) == 105
    missing_signatures = []
    missing_contract_entries = []
    for name, obj in callables.items():
        documented = re.sub(r"\s+", "", name + _stable_public_signature(obj))
        if documented not in compact:
            missing_signatures.append(name)
        # A visible first-column table row is the semantic contract marker;
        # merely appearing in an inventory or generated signature cannot pass.
        if name not in contract_rows:
            missing_contract_entries.append(name)
    assert missing_signatures == []
    assert missing_contract_entries == []


def test_markdown_semantically_defines_every_user_facing_parameter():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    parameters = set()
    for name in att.__all__:
        obj = getattr(att, name)
        if not callable(obj):
            continue
        try:
            signature = inspect.signature(obj)
        except (TypeError, ValueError):
            continue
        parameters.update(
            parameter.name
            for parameter in signature.parameters.values()
            if not parameter.name.startswith("_")
            and parameter.name not in {"args", "kwargs"}
        )
    # Backticks here are a semantic-doc marker: a name merely present inside
    # a generated signature cannot satisfy this gate.
    undocumented = sorted(
        parameter for parameter in parameters if f"`{parameter}`" not in readme
    )
    assert len(parameters) == 176
    assert undocumented == []


def test_markdown_documents_public_values_and_alias_relationships():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name in (
        "settings",
        "MARKET_HISTORY_SCHEMA_VERSION",
        "MARKET_HISTORY_APPLICATION_ID",
        "IRAN_TREASURY_FACE_VALUE",
        "OPTION_SNAPSHOT_SCHEMA_VERSION",
    ):
        assert f"`{name}`" in readme
    assert "get_orderbook_history is get_order_book_history" in readme
    assert "get_treasury_yields_history is get_treasury_yield_history" in readme
    assert "stock_RL" in readme and "identity alias نیست" in readme


def test_high_risk_deterministic_contracts_match_documentation():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    maturity = att.parse_treasury_maturity("اخزا020322")
    assert set(maturity) == {
        "maturity_jalali",
        "maturity_gregorian",
        "maturity_source",
    }
    assert maturity["maturity_jalali"] == "1402/03/22"
    assert att.parse_treasury_maturity("اخزا021322") is None
    assert "`dict|None`" in readme
    assert "non-match/تاریخ نامعتبر **`None`**" in readme

    price = att.black_scholes_price(100, 100, 1, 0.05, 0.2)
    iv = att.implied_volatility(price, 100, 100, 1, 0.05)
    assert set(("ImpliedVolatility", "Status", "Iterations")) <= set(iv)
    assert iv["Status"] == "ok"
    exhausted = att.implied_volatility(
        price, 100, 100, 1, 0.05, tolerance=1e-30, max_iterations=1
    )
    assert exhausted["Status"] == "non_converged"
    assert math.isnan(exhausted["ImpliedVolatility"])
    assert att.black_scholes_greeks(100, 100, 1, 0.05, 0.2)["Status"] == "ok"
    assert "عدم همگرایی exception نیست" in readme
    assert (
        "Delta,Gamma,Vega,Vega1Pct,ThetaPerYear,ThetaPerDay,Rho,Rho100bp,Status"
        in readme
    )

    assert att.validate_ins_code(123) == "123"
    assert att.validate_ins_code(" 123 ") == "123"
    for invalid in (123.0, True, "۱۲۳"):
        with pytest.raises(att.InvalidParameterError):
            att.validate_ins_code(invalid)
    assert "float، bool، رقم فارسی/عربی" in readme
    assert "فقط رشتهٔ ده‌دهی دقیق را می‌پذیرد" not in readme

    curve = att.build_yield_curve(
        [
            {"Maturity": "2027-01-01", "DiscountFactor": 0.9},
            {"Maturity": "2028-01-01", "DiscountFactor": 0.8},
        ],
        settlement_date="2026-01-01",
    )
    diagnostic_keys = {
        "input_node_count",
        "node_count",
        "duplicate_count",
        "duplicate_policy",
        "monotonic_discount_enforced",
    }
    assert set(curve.diagnostics) == diagnostic_keys
    for key in diagnostic_keys:
        assert key in readme


def test_legacy_intraday_and_option_pcr_contracts_are_not_contradictory(monkeypatch):
    from algotik_tse.core import intraday

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert intraday._validate_interval("4hour") == "4h"
    assert intraday._validate_interval("240m") == "4h"
    assert intraday._validate_interval("12hour") == "12h"
    assert intraday._validate_interval("720") == "12h"
    assert intraday._validate_interval("not-an-interval") is None
    monkeypatch.setattr(intraday, "_resolve_web_id", lambda *_args, **_kwargs: "1")
    monkeypatch.setattr(intraday, "date_fix", lambda *_args, **_kwargs: (None, None))
    assert (
        intraday.stock_intraday(
            "فملی", interval="1min", start="not-a-date", progress=False
        )
        is None
    )
    assert "`ValueError` خطای عمدی قرارداد این API نیست" in readme
    assert "interval/date نامعتبر `ValueError`" not in readme

    options = pd.DataFrame(
        {
            "InsCode": ["1", "2"],
            "OptionType": ["call", "put"],
            "Volume": [0, 10],
            "Value": [100, 50],
            "OpenInterest": [20, 30],
            "AsOf": ["2026-08-25T08:00:00Z"] * 2,
            "UnderlyingInsCode": ["10"] * 2,
            "EndDate": ["2026-09-01"] * 2,
        }
    )
    ratios = att.option_put_call_ratios(options, group_by="underlying_expiry")
    assert {
        "PCRVolumeStatus",
        "PCRValueStatus",
        "PCROpenInterestStatus",
    } <= set(ratios)
    assert ratios.loc[0, "PCRVolumeStatus"] == "zero_denominator"
    for value in ("market", "underlying", "expiry", "underlying_expiry"):
        assert value in readme
    for invalid in ("UnderlyingInsCode", "symbol", ""):
        with pytest.raises(ValueError):
            att.option_put_call_ratios(options, group_by=invalid)
    assert "grouping پشتیبانی‌شدهٔ dataframe" not in readme


def test_high_risk_live_snapshot_option_and_fundamental_contracts(monkeypatch):
    from algotik_tse.core import fundamentals, instruments, market_data

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    snapshot = market_data._parse_market_watch_response(
        "x@05/06/03 10:00:00,P,1@@@x",
        fetched_at=pd.Timestamp("2026-08-25 10:00", tz="Asia/Tehran"),
    )
    snapshot_keys = {
        "stocks",
        "order_book",
        "market_time",
        "index_value",
        "migration",
        "trade_date",
        "market_state",
        "exchange_time",
        "fetched_at",
        "snapshot_age_seconds",
        "is_today_trade_date",
        "is_history_eligible",
        "is_realtime_fresh",
        "is_previous_trade_date",
        "is_stale",
        "is_partial",
    }
    assert set(snapshot) == snapshot_keys
    for key in snapshot_keys:
        assert key in readme
    assert "market_status" not in readme

    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    monkeypatch.setattr(
        market_data,
        "market_client_type",
        lambda: pd.DataFrame(columns=market_data.CLIENT_COLUMNS),
    )
    live = market_data.get_live_market()
    assert {"BidPrice1", "AskPrice1", "EstimatedNetIndividualFlow"} <= set(live)
    assert set(live.attrs) == {
        "field_validity",
        "source_schema_presence",
        "migration",
        "missing_selectors",
    }
    with pytest.raises(att.StockNotFoundError):
        market_data.get_live_symbol("missing", fallback="none")
    for token in (
        "BidPrice1, AskPrice1",
        "EstimatedNetIndividualFlow",
        "closing_price_info_fallback",
        "field_validity,source_schema_presence,migration,missing_selectors",
    ):
        assert token in readme
    assert "market_watch_snapshot" not in readme
    assert "tsetmc_point_fallback" not in readme

    monkeypatch.setattr(instruments, "list_options", lambda **_: pd.DataFrame())
    chain = instruments.get_options_chain("تست", progress=False)
    assert set(chain) == {
        "calls",
        "puts",
        "underlying_name",
        "underlying_price",
        "expiry_dates",
        "market_time",
    }
    assert "`underlying_price`" in readme
    assert "کلید `price` وجود ندارد" in readme

    stale = dict(snapshot, is_stale=True, is_realtime_fresh=False)
    monkeypatch.setattr(fundamentals, "market_watch", lambda: stale)
    screened = fundamentals.get_market_fundamentals(allow_stale=False, progress=False)
    assert screened.empty
    assert screened.attrs["stale_rejected"] is True
    assert set(screened.attrs) == {
        "request_count",
        "max_requests",
        "missing_selectors",
        "strict",
        "stale_rejected",
        "source",
        "price_source",
        "eps_source",
        "no_lookahead",
        "no_backfill",
        "archive_path",
    }
    assert "stale با `allow_stale=False` frame تهی و attr است، نه exception" in readme


def test_high_risk_policy_and_http_contract_snapshot():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required = (
        "error_policy∈{retry,raise,stop}",
        "callback_error_policy∈{raise,ignore,stop}",
        "storage_error_policy∈{raise,ignore}",
        "`allow_redirects: bool=True`",
        "`max_redirects: int=5`",
        "`params` فقط روی درخواست اول",
        "`requests.exceptions.TooManyRedirects`",
        "به‌تنهایی روی status 4xx/5xx `raise_for_status()` نمی‌کند",
        "`output_type='standard'` دقیقاً `Open,High,Low,Close,Volume`",
        "`Final,No.,Value`",
        "`DataFrame|None` با index `key` و ستون `value`",
    )
    for token in required:
        assert token in readme
    assert "pandas.read_html" not in readme
