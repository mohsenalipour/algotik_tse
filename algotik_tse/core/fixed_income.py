"""Fixed-income analytics and Iranian treasury-bill yield curves.

TSETMC does not publish a complete coupon schedule through the feeds used by
this package. Consequently, high-level market helpers in this module are
strictly limited to verified zero-coupon Iranian treasury bills (اخزا).
Generic coupon-bond analytics require explicit cashflows or complete coupon
metadata supplied by the caller; coupon terms are never inferred from a name.
"""

import datetime
from io import StringIO
import math
import warnings
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np
import pandas as pd
import requests
from persiantools.jdatetime import JalaliDate

from algotik_tse._clock import tehran_now, tehran_today
from algotik_tse.core.conventions import (
    coerce_financial_date,
    day_count_fraction,
    discount_factor_from_rate,
    rate_from_discount_factor,
    validate_frequency,
)
from algotik_tse.core.market_data import (
    _normalise_symbol,
    _is_current_snapshot,
    market_watch,
)
from algotik_tse.core.parsers import parse_treasury_maturity, parse_treasury_name
from algotik_tse.core.stock import stock
from algotik_tse.exceptions import (
    AmbiguousSymbolError,
    ConnectionError,
    DataParsingError,
    StockNotFoundError,
)
from algotik_tse.http_client import safe_get
from algotik_tse.settings import settings

# Widely used market convention for Iranian treasury bills. This is a package
# convention, not a value supplied by TSETMC, and every high-level result marks
# that provenance explicitly.
IRAN_TREASURY_FACE_VALUE = 1_000_000.0
IFB_REFERENCE_SOURCE = "ifb_ytm_page"
_IFB_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def treasury_yield(
    price,
    maturity_date,
    settlement_date=None,
    face_value=IRAN_TREASURY_FACE_VALUE,
    day_count="ACT/365F",
):
    """Calculate zero-coupon treasury yields under explicit conventions.

    Returns effective-annual, continuously-compounded, simple-annual and bank
    discount yields together; it intentionally does not hide the convention
    behind a single ambiguous ``YTM`` number. ``settlement_date`` defaults to
    the local calendar date and that source is recorded in the result.
    """
    price = float(price)
    face_value = float(face_value)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("price must be a positive finite number")
    if not math.isfinite(face_value) or face_value <= 0:
        raise ValueError("face_value must be a positive finite number")
    settlement_source = "user_supplied"
    if settlement_date is None:
        settlement_date = tehran_today()
        settlement_source = "tehran_calendar_date"
    settlement = coerce_financial_date(settlement_date, "settlement_date")
    maturity = coerce_financial_date(maturity_date, "maturity_date")
    if maturity <= settlement:
        raise ValueError("maturity_date must be after settlement_date")
    days = (maturity - settlement).days
    tenor = day_count_fraction(settlement, maturity, day_count)
    discount_factor = price / face_value
    effective = rate_from_discount_factor(discount_factor, tenor, "effective")
    continuous = rate_from_discount_factor(discount_factor, tenor, "continuous")
    simple = (face_value / price - 1.0) / tenor
    bank_discount = (face_value - price) / face_value * (360.0 / days)
    macaulay_duration = tenor
    modified_duration = tenor / (1.0 + effective)
    convexity = tenor * (tenor + 1.0) / ((1.0 + effective) ** 2)
    dv01 = modified_duration * price * 0.0001
    return {
        "Price": price,
        "FaceValue": face_value,
        "SettlementDate": settlement,
        "MaturityDate": maturity,
        "DaysToMaturity": days,
        "Tenor": tenor,
        "DiscountFactor": discount_factor,
        "EffectiveAnnualYield": effective,
        "ContinuousYield": continuous,
        "SimpleAnnualYield": simple,
        "BankDiscountYield": bank_discount,
        "MacaulayDuration": macaulay_duration,
        "ModifiedDuration": modified_duration,
        "Convexity": convexity,
        "DV01": dv01,
        # Additive aliases remain convention-qualified.
        "YTMEffectiveAnnual": effective,
        "YieldConvention": "zero_coupon_multiple",
        "DayCount": str(day_count).upper(),
        "SettlementSource": settlement_source,
        "Status": "ok",
    }


def _add_months(value, months):
    """Add whole Gregorian months while preserving an EOM anchor."""
    source_next = (
        datetime.date(value.year + 1, 1, 1)
        if value.month == 12
        else datetime.date(value.year, value.month + 1, 1)
    )
    source_is_eom = value == source_next - datetime.timedelta(days=1)
    month_index = value.year * 12 + value.month - 1 + int(months)
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    month_end = (next_month - datetime.timedelta(days=1)).day
    return datetime.date(
        year, month, month_end if source_is_eom else min(value.day, month_end)
    )


def _generated_coupon_cashflows(
    settlement,
    maturity_date,
    face_value,
    coupon_rate,
    frequency,
    issue_date=None,
):
    maturity = coerce_financial_date(maturity_date, "maturity_date")
    if maturity <= settlement:
        raise ValueError("maturity_date must be after settlement_date")
    frequency = validate_frequency(frequency)
    if 12 % frequency != 0:
        raise ValueError("frequency must be a positive divisor of 12")
    face_value = float(face_value)
    coupon_rate = float(coupon_rate)
    if (
        not math.isfinite(face_value)
        or not math.isfinite(coupon_rate)
        or face_value <= 0
        or coupon_rate < 0
    ):
        raise ValueError(
            "face_value must be finite/positive and coupon_rate finite/non-negative"
        )
    issue = (
        coerce_financial_date(issue_date, "issue_date")
        if issue_date is not None
        else None
    )
    if issue is not None:
        if issue >= maturity:
            raise ValueError("issue_date must be before maturity_date")
        if settlement < issue:
            raise ValueError("settlement_date cannot precede issue_date")
    months = 12 // frequency
    dates = []
    period = 0
    cursor = maturity
    while cursor > settlement:
        dates.append(cursor)
        period += 1
        cursor = _add_months(maturity, -period * months)
        if len(dates) > 1200:
            raise ValueError("coupon schedule exceeds 1200 periods")
    if issue is not None:
        issue_months = (maturity.year - issue.year) * 12 + maturity.month - issue.month
        if (
            issue_months <= 0
            or issue_months % months != 0
            or _add_months(maturity, -issue_months) != issue
        ):
            raise ValueError(
                "irregular/stub coupon metadata is unsupported; provide explicit dated cashflows"
            )
        if cursor < issue:
            cursor = issue
    dates.sort()
    coupon = face_value * coupon_rate / frequency
    result = [(value, coupon) for value in dates]
    result[-1] = (result[-1][0], result[-1][1] + face_value)
    previous_coupon = cursor
    next_coupon = dates[0]
    return result, previous_coupon, next_coupon, coupon


def _normalize_cashflows(
    cashflows,
    settlement,
    day_count,
    maturity_date=None,
    face_value=None,
    coupon_rate=None,
    frequency=1,
    issue_date=None,
):
    accrued = 0.0
    generated = False
    if cashflows is None:
        missing = [
            name
            for name, value in (
                ("maturity_date", maturity_date),
                ("face_value", face_value),
                ("coupon_rate", coupon_rate),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                "cashflows are required unless complete coupon metadata is "
                "supplied; missing {}".format(", ".join(missing))
            )
        cashflows, previous_coupon, next_coupon, coupon = _generated_coupon_cashflows(
            settlement,
            maturity_date,
            face_value,
            coupon_rate,
            frequency,
            issue_date=issue_date,
        )
        generated = True
        if previous_coupon < settlement < next_coupon:
            whole = day_count_fraction(previous_coupon, next_coupon, day_count)
            elapsed = day_count_fraction(previous_coupon, settlement, day_count)
            accrued = coupon * elapsed / whole
    elif isinstance(cashflows, pd.DataFrame):
        lower = {str(column).lower(): column for column in cashflows.columns}
        date_col = next(
            (
                lower[name]
                for name in ("date", "paymentdate", "maturity")
                if name in lower
            ),
            None,
        )
        amount_col = next(
            (
                lower[name]
                for name in ("amount", "cashflow", "payment")
                if name in lower
            ),
            None,
        )
        if date_col is None or amount_col is None:
            raise ValueError("cashflow DataFrame needs Date and Amount columns")
        cashflows = list(zip(cashflows[date_col], cashflows[amount_col]))
    elif isinstance(cashflows, dict):
        cashflows = list(cashflows.items())

    normalized = []
    for item in cashflows:
        if isinstance(item, dict):
            lowered = {str(key).lower(): value for key, value in item.items()}
            date_value = lowered.get("date", lowered.get("paymentdate"))
            amount = lowered.get("amount", lowered.get("cashflow"))
        else:
            try:
                date_value, amount = item
            except (TypeError, ValueError):
                raise ValueError("each cashflow must contain a date and amount")
        payment_date = coerce_financial_date(date_value, "cashflow date")
        amount = float(amount)
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError(
                "cashflows must be positive; sign-changing or non-positive "
                "cashflows can have multiple/undefined IRRs"
            )
        if payment_date <= settlement:
            continue
        normalized.append((payment_date, amount))
    if not normalized:
        raise ValueError("no positive cashflows remain after settlement_date")
    grouped = {}
    for payment_date, amount in normalized:
        grouped[payment_date] = grouped.get(payment_date, 0.0) + amount
    normalized = sorted(grouped.items())
    timed = [
        (date, amount, day_count_fraction(settlement, date, day_count))
        for date, amount in normalized
    ]
    return timed, accrued, generated


def _cashflow_present_value(cashflows, annual_yield, compounding, frequency):
    return sum(
        amount
        * discount_factor_from_rate(
            annual_yield, time, compounding=compounding, frequency=frequency
        )
        for _, amount, time in cashflows
    )


def bond_price(
    annual_yield,
    cashflows=None,
    settlement_date=None,
    day_count="ACT/365F",
    compounding="nominal",
    frequency=1,
    price_type="dirty",
    accrued_interest=None,
    maturity_date=None,
    face_value=None,
    coupon_rate=None,
    issue_date=None,
):
    """Price explicit future cashflows at an annual yield.

    When ``cashflows`` is omitted, ``maturity_date``, ``face_value`` and
    ``coupon_rate`` are all required and coupon dates are generated backwards
    from maturity at ``frequency``. No instrument metadata is fetched or
    inferred. The default result is a dirty price; clean price subtracts either
    supplied accrued interest or schedule-derived accrued interest.
    """
    annual_yield = float(annual_yield)
    if not math.isfinite(annual_yield):
        raise ValueError("annual_yield must be finite")
    frequency = validate_frequency(frequency)
    if accrued_interest is not None and not math.isfinite(float(accrued_interest)):
        raise ValueError("accrued_interest must be finite")
    settlement = coerce_financial_date(
        settlement_date or tehran_today(), "settlement_date"
    )
    timed, schedule_accrued, _ = _normalize_cashflows(
        cashflows,
        settlement,
        day_count,
        maturity_date=maturity_date,
        face_value=face_value,
        coupon_rate=coupon_rate,
        frequency=frequency,
        issue_date=issue_date,
    )
    dirty = _cashflow_present_value(timed, annual_yield, compounding, frequency)
    kind = str(price_type).lower()
    if kind == "dirty":
        return dirty
    if kind == "clean":
        accrued = (
            schedule_accrued if accrued_interest is None else float(accrued_interest)
        )
        return dirty - accrued
    raise ValueError("price_type must be 'dirty' or 'clean'")


def yield_to_maturity(
    price,
    cashflows=None,
    settlement_date=None,
    day_count="ACT/365F",
    compounding="nominal",
    frequency=1,
    price_type="dirty",
    accrued_interest=None,
    maturity_date=None,
    face_value=None,
    coupon_rate=None,
    issue_date=None,
    tolerance=1e-12,
    max_iterations=300,
):
    """Solve the annual yield of positive future cashflows by bisection."""
    price = float(price)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("price must be a positive finite number")
    frequency = validate_frequency(frequency)
    if accrued_interest is not None and not math.isfinite(float(accrued_interest)):
        raise ValueError("accrued_interest must be finite")
    tolerance = float(tolerance)
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be a positive finite number")
    max_iterations = validate_frequency(max_iterations, "max_iterations")
    settlement = coerce_financial_date(
        settlement_date or tehran_today(), "settlement_date"
    )
    timed, schedule_accrued, _ = _normalize_cashflows(
        cashflows,
        settlement,
        day_count,
        maturity_date=maturity_date,
        face_value=face_value,
        coupon_rate=coupon_rate,
        frequency=frequency,
        issue_date=issue_date,
    )
    kind = str(price_type).lower()
    if kind == "dirty":
        dirty_price = price
    elif kind == "clean":
        accrued = (
            schedule_accrued if accrued_interest is None else float(accrued_interest)
        )
        dirty_price = price + accrued
    else:
        raise ValueError("price_type must be 'dirty' or 'clean'")
    if not math.isfinite(dirty_price) or dirty_price <= 0:
        raise ValueError("dirty price must be a positive finite number")

    compound = str(compounding).lower()
    if compound == "continuous":
        lower = -1.0
    elif compound == "effective":
        lower = -1.0 + 1e-12
    elif compound == "nominal":
        lower = -float(frequency) + 1e-12
    else:
        raise ValueError("unsupported compounding {!r}".format(compounding))

    def objective(rate):
        try:
            return (
                _cashflow_present_value(timed, rate, compound, frequency) - dirty_price
            )
        except OverflowError:
            return math.inf

    f_lower = objective(lower)
    if compound == "continuous":
        while f_lower <= 0 and lower > -1e6:
            lower *= 2.0
            f_lower = objective(lower)
    upper = 1.0
    f_upper = objective(upper)
    while f_upper > 0 and upper < 1e6:
        upper = upper * 2.0 + 1.0
        f_upper = objective(upper)
    if math.isnan(f_lower) or not math.isfinite(f_upper):
        raise ValueError("yield solver encountered invalid present values")
    if f_lower < 0 or f_upper > 0:
        raise ValueError("could not bracket a unique yield for the supplied cashflows")
    for _ in range(max_iterations):
        mid = (lower + upper) / 2.0
        f_mid = objective(mid)
        if abs(f_mid) <= tolerance * max(1.0, dirty_price):
            return mid
        if f_mid > 0:
            lower = mid
        else:
            upper = mid
        if upper - lower <= tolerance * max(1.0, abs(mid)):
            return (lower + upper) / 2.0
    raise ValueError("yield solver did not converge within max_iterations")


def bond_analytics(
    price,
    cashflows=None,
    settlement_date=None,
    day_count="ACT/365F",
    compounding="nominal",
    frequency=1,
    price_type="dirty",
    accrued_interest=None,
    maturity_date=None,
    face_value=None,
    coupon_rate=None,
    issue_date=None,
    annual_yield=None,
    bump_size=0.0001,
):
    """Return yield, duration and convexity for an explicit bond definition."""
    settlement_source = "user_supplied"
    if settlement_date is None:
        settlement_date = tehran_today()
        settlement_source = "tehran_calendar_date"
    settlement = coerce_financial_date(settlement_date, "settlement_date")
    frequency = validate_frequency(frequency)
    if accrued_interest is not None and not math.isfinite(float(accrued_interest)):
        raise ValueError("accrued_interest must be finite")
    timed, schedule_accrued, generated = _normalize_cashflows(
        cashflows,
        settlement,
        day_count,
        maturity_date=maturity_date,
        face_value=face_value,
        coupon_rate=coupon_rate,
        frequency=frequency,
        issue_date=issue_date,
    )
    accrued = schedule_accrued if accrued_interest is None else float(accrued_interest)
    kind = str(price_type).lower()
    if kind == "dirty":
        dirty = float(price)
        clean = dirty - accrued
    elif kind == "clean":
        clean = float(price)
        dirty = clean + accrued
    else:
        raise ValueError("price_type must be 'dirty' or 'clean'")
    if not math.isfinite(dirty) or not math.isfinite(clean) or dirty <= 0:
        raise ValueError("clean/dirty price must be finite and dirty price positive")
    if annual_yield is None:
        annual_yield = yield_to_maturity(
            price,
            cashflows=cashflows,
            settlement_date=settlement,
            day_count=day_count,
            compounding=compounding,
            frequency=frequency,
            price_type=price_type,
            accrued_interest=accrued_interest,
            maturity_date=maturity_date,
            face_value=face_value,
            coupon_rate=coupon_rate,
            issue_date=issue_date,
        )
    annual_yield = float(annual_yield)
    if not math.isfinite(annual_yield):
        raise ValueError("annual_yield must be finite")
    pvs = [
        amount
        * discount_factor_from_rate(
            annual_yield, time, compounding=compounding, frequency=frequency
        )
        for _, amount, time in timed
    ]
    model_dirty = sum(pvs)
    macaulay = sum(time * pv for (_, _, time), pv in zip(timed, pvs)) / model_dirty
    compound = str(compounding).lower()
    if compound == "continuous":
        modified = macaulay
        convexity = (
            sum(time * time * pv for (_, _, time), pv in zip(timed, pvs)) / model_dirty
        )
    else:
        divisor = (
            1.0 + annual_yield
            if compound == "effective"
            else 1.0 + annual_yield / frequency
        )
        interval = 1.0 if compound == "effective" else 1.0 / frequency
        modified = macaulay / divisor
        convexity = sum(
            time * (time + interval) * pv for (_, _, time), pv in zip(timed, pvs)
        ) / (model_dirty * divisor * divisor)
    bump = float(bump_size)
    if not math.isfinite(bump) or bump <= 0:
        raise ValueError("bump_size must be positive")
    price_down = _cashflow_present_value(
        timed, annual_yield - bump, compounding, frequency
    )
    price_up = _cashflow_present_value(
        timed, annual_yield + bump, compounding, frequency
    )
    effective_duration = (price_down - price_up) / (2.0 * model_dirty * bump)
    effective_convexity = (price_down + price_up - 2.0 * model_dirty) / (
        model_dirty * bump * bump
    )
    dv01 = modified * model_dirty * 0.0001
    return {
        "CleanPrice": clean,
        "DirtyPrice": dirty,
        "ModelDirtyPrice": model_dirty,
        "AccruedInterest": accrued,
        "AnnualYield": annual_yield,
        "YieldCompounding": compound,
        "Frequency": frequency,
        "MacaulayDuration": macaulay,
        "ModifiedDuration": modified,
        "Convexity": convexity,
        "EffectiveDuration": effective_duration,
        "EffectiveConvexity": effective_convexity,
        "DV01": dv01,
        "BumpSize": bump,
        "SettlementDate": settlement,
        "SettlementSource": settlement_source,
        "DayCount": str(day_count).upper(),
        "CashflowSource": (
            "generated_from_user_metadata" if generated else "user_supplied"
        ),
        "CashflowCount": len(timed),
        "Status": "ok",
    }


@dataclass(frozen=True)
class YieldCurve:
    """Immutable zero curve using linear interpolation in log-discount space."""

    settlement_date: datetime.date
    maturities: tuple
    times: tuple
    discount_factors: tuple
    continuous_zero_rates: tuple
    day_count: str = "ACT/365F"
    interpolation: str = "log_discount"
    extrapolate: bool = False
    node_metadata: tuple = field(default_factory=tuple)
    diagnostics: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "maturities", tuple(self.maturities))
        object.__setattr__(self, "times", tuple(self.times))
        object.__setattr__(self, "discount_factors", tuple(self.discount_factors))
        object.__setattr__(
            self, "continuous_zero_rates", tuple(self.continuous_zero_rates)
        )
        object.__setattr__(self, "node_metadata", tuple(self.node_metadata))
        sizes = {
            len(self.maturities),
            len(self.times),
            len(self.discount_factors),
            len(self.continuous_zero_rates),
        }
        if len(sizes) != 1 or not self.maturities:
            raise ValueError("YieldCurve node arrays must have equal non-zero length")
        if any(
            not math.isfinite(float(time)) or time <= 0 for time in self.times
        ) or any(
            self.times[index] <= self.times[index - 1]
            for index in range(1, len(self.times))
        ):
            raise ValueError(
                "YieldCurve tenors must be positive and strictly increasing"
            )
        if any(
            not math.isfinite(discount) or discount <= 0
            for discount in self.discount_factors
        ):
            raise ValueError("YieldCurve discount factors must be positive and finite")
        if any(not math.isfinite(float(rate)) for rate in self.continuous_zero_rates):
            raise ValueError("YieldCurve zero rates must be finite")
        if self.node_metadata and len(self.node_metadata) != len(self.maturities):
            raise ValueError("node_metadata length must match curve nodes")
        object.__setattr__(
            self,
            "node_metadata",
            tuple(MappingProxyType(dict(item)) for item in self.node_metadata),
        )
        object.__setattr__(
            self, "diagnostics", MappingProxyType(dict(self.diagnostics))
        )

    @property
    def nodes(self):
        """Return a defensive DataFrame copy of the calibrated nodes."""
        records = []
        for index, (maturity, tenor, discount, zero) in enumerate(
            zip(
                self.maturities,
                self.times,
                self.discount_factors,
                self.continuous_zero_rates,
            )
        ):
            record = dict(self.node_metadata[index]) if self.node_metadata else {}
            record.update(
                {
                    "Maturity": maturity,
                    "Tenor": tenor,
                    "DiscountFactor": discount,
                    "ContinuousZeroRate": zero,
                }
            )
            records.append(record)
        return pd.DataFrame(records)

    def _time(self, value):
        if isinstance(value, (int, float, np.integer, np.floating)):
            time = float(value)
        else:
            target = coerce_financial_date(value, "curve date")
            if target == self.settlement_date:
                return 0.0
            if target < self.settlement_date:
                raise ValueError("curve date cannot precede settlement_date")
            time = day_count_fraction(self.settlement_date, target, self.day_count)
        if not math.isfinite(time):
            raise ValueError("tenor must be finite")
        if time < 0:
            raise ValueError("tenor cannot be negative")
        return time

    def discount_factor(self, date_or_tenor):
        """Return the interpolated discount factor for a date or year tenor."""
        time = self._time(date_or_tenor)
        if time == 0:
            return 1.0
        node_times = np.asarray((0.0,) + self.times, dtype=float)
        log_discounts = np.log(np.asarray((1.0,) + self.discount_factors, dtype=float))
        if time > node_times[-1]:
            if not self.extrapolate:
                raise ValueError("requested tenor is beyond the last curve node")
            left, right = -2, -1
            slope = (log_discounts[right] - log_discounts[left]) / (
                node_times[right] - node_times[left]
            )
            log_discount = log_discounts[right] + slope * (time - node_times[right])
        else:
            log_discount = float(np.interp(time, node_times, log_discounts))
        return math.exp(log_discount)

    def zero_rate(self, date_or_tenor, compounding="continuous", frequency=1):
        """Return the annualized zero rate under the requested compounding."""
        time = self._time(date_or_tenor)
        if time == 0:
            raise ValueError("zero rate is undefined at settlement")
        return rate_from_discount_factor(
            self.discount_factor(time), time, compounding, frequency
        )

    def forward_rate(
        self,
        start_date_or_tenor,
        end_date_or_tenor,
        compounding="continuous",
        frequency=1,
    ):
        """Return the annualized forward rate between two curve points."""
        start_time = self._time(start_date_or_tenor)
        end_time = self._time(end_date_or_tenor)
        if end_time <= start_time:
            raise ValueError("forward end must be after start")
        forward_df = self.discount_factor(end_time) / self.discount_factor(start_time)
        return rate_from_discount_factor(
            forward_df, end_time - start_time, compounding, frequency
        )


def _find_column(frame, names):
    columns = {str(column).lower().replace("_", ""): column for column in frame.columns}
    for name in names:
        key = name.lower().replace("_", "")
        if key in columns:
            return columns[key]
    return None


def build_yield_curve(
    nodes,
    settlement_date,
    interpolation="log_discount",
    extrapolate=False,
    duplicate_policy="error",
    day_count="ACT/365F",
    rate_compounding="effective",
    rate_frequency=1,
    enforce_monotonic_discount=True,
):
    """Build a no-arbitrage-oriented zero curve from dated nodes.

    Nodes need ``Maturity`` plus either ``DiscountFactor`` or a conventionally
    identified rate (``EffectiveAnnualYield``, ``ContinuousYield`` or
    ``ZeroRate``). Duplicate maturities are handled only through the explicit
    ``error``, ``last`` or ``volume_weighted`` policy. By default discount
    factors must be non-increasing with maturity.
    """
    if interpolation != "log_discount":
        raise ValueError("only interpolation='log_discount' is supported")
    policy = str(duplicate_policy).lower()
    if policy not in ("error", "last", "volume_weighted"):
        raise ValueError(
            "duplicate_policy must be 'error', 'last', or 'volume_weighted'"
        )
    settlement = coerce_financial_date(settlement_date, "settlement_date")
    rate_frequency = validate_frequency(rate_frequency, "rate_frequency")
    frame = nodes.copy() if isinstance(nodes, pd.DataFrame) else pd.DataFrame(nodes)
    if frame.empty:
        raise ValueError("at least one curve node is required")
    maturity_col = _find_column(frame, ("Maturity", "MaturityDate", "Date"))
    discount_col = _find_column(frame, ("DiscountFactor", "DF"))
    effective_col = _find_column(frame, ("EffectiveAnnualYield",))
    continuous_col = _find_column(frame, ("ContinuousYield", "ContinuousZeroRate"))
    rate_col = _find_column(frame, ("ZeroRate", "Yield", "Rate"))
    volume_col = _find_column(frame, ("Volume", "Weight"))
    if maturity_col is None:
        raise ValueError("nodes need a Maturity column")
    if (
        discount_col is None
        and effective_col is None
        and continuous_col is None
        and rate_col is None
    ):
        raise ValueError("nodes need DiscountFactor or an explicit zero-rate column")

    records = []
    for position, (_, row) in enumerate(frame.iterrows()):
        maturity = coerce_financial_date(row[maturity_col], "node maturity")
        if maturity <= settlement:
            raise ValueError("every node maturity must be after settlement_date")
        tenor = day_count_fraction(settlement, maturity, day_count)
        if discount_col is not None and pd.notna(row[discount_col]):
            discount = float(row[discount_col])
            rate_source = "discount_factor"
        elif effective_col is not None and pd.notna(row[effective_col]):
            discount = discount_factor_from_rate(
                float(row[effective_col]), tenor, "effective"
            )
            rate_source = "effective_annual_yield"
        elif continuous_col is not None and pd.notna(row[continuous_col]):
            discount = discount_factor_from_rate(
                float(row[continuous_col]), tenor, "continuous"
            )
            rate_source = "continuous_yield"
        elif rate_col is not None and pd.notna(row[rate_col]):
            discount = discount_factor_from_rate(
                float(row[rate_col]), tenor, rate_compounding, rate_frequency
            )
            rate_source = "zero_rate"
        else:
            raise ValueError("node at position {} has no usable value".format(position))
        if not math.isfinite(discount) or discount <= 0:
            raise ValueError("every discount factor must be positive and finite")
        metadata = {
            str(column): row[column]
            for column in frame.columns
            if column
            not in (maturity_col, discount_col, effective_col, continuous_col, rate_col)
        }
        metadata["RateSource"] = rate_source
        records.append(
            {
                "maturity": maturity,
                "tenor": tenor,
                "discount": discount,
                "metadata": metadata,
                "position": position,
                "weight": (
                    float(row[volume_col])
                    if volume_col is not None and pd.notna(row[volume_col])
                    else np.nan
                ),
            }
        )

    grouped = {}
    for record in records:
        grouped.setdefault(record["maturity"], []).append(record)
    deduplicated = []
    duplicate_count = 0
    for maturity, group in grouped.items():
        if len(group) == 1:
            deduplicated.append(group[0])
            continue
        duplicate_count += len(group) - 1
        if policy == "error":
            raise ValueError("duplicate maturity {}".format(maturity.isoformat()))
        if policy == "last":
            deduplicated.append(max(group, key=lambda item: item["position"]))
        elif policy == "volume_weighted":
            weights = np.asarray([item["weight"] for item in group], dtype=float)
            if (
                not np.isfinite(weights).all()
                or (weights < 0).any()
                or weights.sum() <= 0
            ):
                raise ValueError(
                    "volume_weighted duplicates require positive finite Volume"
                )
            selected = dict(max(group, key=lambda item: item["position"]))
            selected["discount"] = float(
                np.average([item["discount"] for item in group], weights=weights)
            )
            selected["metadata"] = dict(selected["metadata"])
            selected["metadata"]["DuplicateCount"] = len(group)
            selected["metadata"]["AggregateWeight"] = float(weights.sum())
            deduplicated.append(selected)
    deduplicated.sort(key=lambda item: item["maturity"])
    discounts = tuple(float(item["discount"]) for item in deduplicated)
    if enforce_monotonic_discount and discounts[0] > 1.0 + 1e-12:
        raise ValueError(
            "first discount factor must not exceed the settlement anchor D(0)=1"
        )
    if enforce_monotonic_discount and any(
        discounts[index] > discounts[index - 1] + 1e-12
        for index in range(1, len(discounts))
    ):
        raise ValueError("discount factors must be non-increasing with maturity")
    times = tuple(float(item["tenor"]) for item in deduplicated)
    zero_rates = tuple(
        rate_from_discount_factor(discount, tenor, "continuous")
        for discount, tenor in zip(discounts, times)
    )
    return YieldCurve(
        settlement_date=settlement,
        maturities=tuple(item["maturity"] for item in deduplicated),
        times=times,
        discount_factors=discounts,
        continuous_zero_rates=zero_rates,
        day_count=str(day_count).upper(),
        interpolation=interpolation,
        extrapolate=bool(extrapolate),
        node_metadata=tuple(item["metadata"] for item in deduplicated),
        diagnostics={
            "input_node_count": len(records),
            "node_count": len(deduplicated),
            "duplicate_count": duplicate_count,
            "duplicate_policy": policy,
            "monotonic_discount_enforced": bool(enforce_monotonic_discount),
        },
    )


IFB_TABLE_IDS = {
    "treasury": "ContentPlaceHolder1_grdytmforkhazaneh",
    "all": "ContentPlaceHolder1_grdytm",
    "latest_history": "ContentPlaceHolder1_ytmHistoryGride",
}
IFB_COLUMNS = [
    "Symbol",
    "Price",
    "LastTradeJalali",
    "LastTradeDate",
    "PublishJalali",
    "PublishDate",
    "MaturityJalali",
    "Maturity",
    "Volume",
    "ReferenceYTM",
    "ReferenceSimpleYield",
    "ReferenceSource",
]


def _ifb_text(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).translate(_IFB_DIGITS).replace("\u200c", "").strip()


def _ifb_number(value):
    text = _ifb_text(value).replace(",", "").replace("٬", "")
    if not text or text in ("-", "--"):
        return np.nan
    try:
        return float(text)
    except ValueError:
        return np.nan


def _ifb_percent(value):
    text = _ifb_text(value).replace("%", "").replace("٪", "").strip()
    if not text or text in ("-", "--"):
        return np.nan
    # IFB's current server-rendered page uses slash as its decimal separator.
    if text.count("/") == 1 and all(part.isdigit() for part in text.split("/")):
        text = text.replace("/", ".")
    text = text.replace(",", "")
    try:
        return float(text) / 100.0
    except ValueError:
        return np.nan


def _ifb_date(value):
    text = _ifb_text(value).replace("-", "/")
    if not text or text in ("-", "--"):
        return "", None
    try:
        date = coerce_financial_date(text, "IFB date")
    except ValueError:
        return text, None
    jalali = JalaliDate.to_jalali(date).isoformat().replace("-", "/")
    return jalali, date


def _parse_ifb_yield_html(html, category="treasury"):
    """Parse one official IFB YTM table from sanitized or live HTML."""
    category = str(category).lower()
    if category not in IFB_TABLE_IDS:
        raise ValueError("category must be 'treasury', 'all', or 'latest_history'")
    try:
        tables = pd.read_html(
            StringIO(str(html)), attrs={"id": IFB_TABLE_IDS[category]}
        )
    except (ValueError, ImportError) as exc:
        raise DataParsingError(
            "official IFB {} yield table was not found".format(category)
        ) from exc
    if len(tables) != 1:
        raise DataParsingError(
            "expected one official IFB {} table, got {}".format(category, len(tables))
        )
    table = tables[0]
    if isinstance(table.columns, pd.MultiIndex):
        table.columns = table.columns.get_level_values(-1)
    expected_count = (
        8 if category == "latest_history" else (7 if category == "treasury" else 6)
    )
    if table.shape[1] < expected_count:
        raise DataParsingError(
            "IFB {} table has {} columns; expected at least {}".format(
                category, table.shape[1], expected_count
            )
        )
    records = []
    for _, raw in table.iloc[:, :expected_count].iterrows():
        values = raw.tolist()
        symbol = _normalise_symbol(_ifb_text(values[1]))
        if not symbol or symbol in ("نماد", "symbol"):
            continue
        if category == "treasury" and not symbol.startswith("اخزا"):
            continue
        if category == "latest_history":
            last_jalali, last_date = _ifb_date(values[2])
            publish_jalali, publish_date = _ifb_date(values[3])
            maturity_jalali, maturity = _ifb_date(values[4])
            price = _ifb_number(values[5])
            volume = _ifb_number(values[6])
            ytm = _ifb_percent(values[7])
            simple = np.nan
        else:
            price = _ifb_number(values[2])
            last_jalali, last_date = _ifb_date(values[3])
            publish_jalali, publish_date = "", None
            maturity_jalali, maturity = _ifb_date(values[4])
            ytm = _ifb_percent(values[5])
            simple = _ifb_percent(values[6]) if category == "treasury" else np.nan
            volume = np.nan
        if (
            maturity is None
            or not math.isfinite(price)
            or price <= 0
            or not math.isfinite(ytm)
        ):
            continue
        records.append(
            {
                "Symbol": symbol,
                "Price": price,
                "LastTradeJalali": last_jalali,
                "LastTradeDate": last_date,
                "PublishJalali": publish_jalali or pd.NA,
                "PublishDate": publish_date,
                "MaturityJalali": maturity_jalali,
                "Maturity": maturity,
                "Volume": volume,
                "ReferenceYTM": ytm,
                "ReferenceSimpleYield": simple,
                "ReferenceSource": IFB_REFERENCE_SOURCE,
            }
        )
    result = pd.DataFrame(records).reindex(columns=IFB_COLUMNS)
    if result.empty:
        result = pd.DataFrame(columns=IFB_COLUMNS)
    else:
        conflict_columns = [
            "Price",
            "LastTradeDate",
            "Maturity",
            "ReferenceYTM",
            "ReferenceSimpleYield",
        ]
        for symbol, group in result.groupby("Symbol"):
            if len(group.drop_duplicates(conflict_columns)) > 1:
                raise DataParsingError(
                    "IFB table contains conflicting duplicate rows for {!r}".format(
                        symbol
                    )
                )
        result = result.drop_duplicates("Symbol", keep="last").reset_index(drop=True)
    result = _cast_treasury_frame(result)
    result.attrs["source"] = IFB_REFERENCE_SOURCE
    result.attrs["reference_url"] = settings.url_ifb_yield_table
    result.attrs["category"] = category
    return result


def get_ifb_yield_table(category="treasury"):
    """Fetch and parse an official Iran Fara Bourse reference YTM table.

    ``latest_history`` is only the initially rendered reference page. This
    function intentionally does not emulate ASP.NET postbacks or claim to
    expose the full filtered history.
    """
    response = safe_get(settings.url_ifb_yield_table)
    if response is None or response.status_code != 200:
        status = None if response is None else response.status_code
        raise ConnectionError("IFB YTM page returned status {!r}".format(status))
    result = _parse_ifb_yield_html(response.text, category=category)
    result.attrs["fetched_at"] = pd.Timestamp(tehran_now())
    return result


TREASURY_COLUMNS = [
    "InsCode",
    "ISIN",
    "Symbol",
    "Name",
    "Ticker",
    "MaturityJalali",
    "Maturity",
    "MaturitySource",
    "MaturityConflict",
    "MaturityCandidates",
    "SettlementDate",
    "DaysToMaturity",
    "Tenor",
    "Price",
    "PriceSource",
    "InstrumentValueSource",
    "NoTrade",
    "InstrumentPriceAsOf",
    "IsInstrumentStale",
    "BidPrice",
    "AskPrice",
    "DiscountFactor",
    "EffectiveAnnualYield",
    "ContinuousYield",
    "SimpleAnnualYield",
    "BankDiscountYield",
    "MacaulayDuration",
    "ModifiedDuration",
    "Convexity",
    "DV01",
    "Volume",
    "Value",
    "TradeCount",
    "FaceValue",
    "FaceValueSource",
    "SettlementSource",
    "DayCount",
    "IsStale",
    "SnapshotAgeSeconds",
    "FetchedAt",
    "Status",
]

TREASURY_HISTORY_COLUMNS = [
    "TradeDate",
    "JalaliDate",
    "Date",
    "InsCode",
    "Symbol",
    "Name",
    "Maturity",
    "MaturitySource",
    "MaturityConflict",
    "MaturityCandidates",
    "SettlementDate",
    "DaysToMaturity",
    "Tenor",
    "Price",
    "PriceSource",
    "DiscountFactor",
    "EffectiveAnnualYield",
    "ContinuousYield",
    "SimpleAnnualYield",
    "BankDiscountYield",
    "MacaulayDuration",
    "ModifiedDuration",
    "Convexity",
    "DV01",
    "Open",
    "High",
    "Low",
    "Close",
    "Final",
    "Volume",
    "Value",
    "TradeCount",
    "FaceValue",
    "FaceValueSource",
    "SettlementSource",
    "DayCount",
    "IsPartial",
    "FetchedAt",
    "Status",
]


_TREASURY_FLOAT_COLUMNS = {
    "Tenor",
    "Price",
    "BidPrice",
    "AskPrice",
    "DiscountFactor",
    "EffectiveAnnualYield",
    "ContinuousYield",
    "SimpleAnnualYield",
    "BankDiscountYield",
    "MacaulayDuration",
    "ModifiedDuration",
    "Convexity",
    "DV01",
    "FaceValue",
    "SnapshotAgeSeconds",
    "Open",
    "High",
    "Low",
    "Close",
    "Final",
    "ReferencePrice",
    "ReferenceYTM",
    "ReferenceSimpleYield",
    "YieldDifferenceBps",
}
_TREASURY_INT_COLUMNS = {
    "DaysToMaturity",
    "Volume",
    "Value",
    "TradeCount",
    "CurveNodeCount",
    "InputNodeCount",
    "CalibratedNodeCount",
}
_TREASURY_BOOL_COLUMNS = {
    "IsStale",
    "NoTrade",
    "IsInstrumentStale",
    "IsPartial",
    "MaturityConflict",
    "MaturityMatchesReference",
    "CurveNoLookahead",
    "CurvePricesNoLookahead",
    "CurveUniverseNoLookahead",
}
_TREASURY_DATE_COLUMNS = {
    "Maturity",
    "SettlementDate",
    "TradeDate",
    "ReferenceAsOf",
    "ReferenceMaturity",
    "LastTradeDate",
    "PublishDate",
}
_TREASURY_TIMESTAMP_COLUMNS = {"FetchedAt", "InstrumentPriceAsOf"}
_TREASURY_STRING_COLUMNS = {
    "InsCode",
    "ISIN",
    "Symbol",
    "Name",
    "Ticker",
    "MaturityJalali",
    "MaturitySource",
    "PriceSource",
    "InstrumentValueSource",
    "FaceValueSource",
    "SettlementSource",
    "DayCount",
    "Status",
    "JalaliDate",
    "CurveID",
    "CurveStatus",
    "CurveError",
    "CurveInterpolation",
    "UniverseSource",
    "ReferenceSource",
    "ReferenceAsOfJalali",
    "ReferenceMaturityJalali",
    "LastTradeJalali",
    "PublishJalali",
}


def _cast_treasury_frame(frame):
    for column in frame.columns:
        if column in _TREASURY_FLOAT_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(
                "Float64"
            )
        elif column in _TREASURY_INT_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(
                "Int64"
            )
        elif column in _TREASURY_BOOL_COLUMNS:
            frame[column] = frame[column].astype("boolean")
        elif column in _TREASURY_DATE_COLUMNS:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
        elif column in _TREASURY_TIMESTAMP_COLUMNS:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
        elif column in _TREASURY_STRING_COLUMNS:
            frame[column] = frame[column].astype("string")
    return frame


def _typed_empty(columns):
    return _cast_treasury_frame(pd.DataFrame(columns=columns))


def _normalized_maturity_map(maturity_map):
    if maturity_map is None:
        return {}
    if not isinstance(maturity_map, dict):
        raise ValueError("maturity_map must be a symbol-to-date dict")
    return {
        _normalise_symbol(key): coerce_financial_date(value, "maturity_map value")
        for key, value in maturity_map.items()
    }


def _reference_maturity_map(reference_table):
    if reference_table is None or reference_table.empty:
        return {}
    result = {}
    for _, row in reference_table.iterrows():
        key = _normalise_symbol(row.get("Symbol"))
        maturity = row.get("Maturity")
        if not key or maturity is None or pd.isna(maturity):
            continue
        maturity = coerce_financial_date(maturity, "IFB maturity")
        if key in result and result[key] != maturity:
            raise DataParsingError(
                "IFB contains conflicting maturities for {!r}".format(key)
            )
        result[key] = maturity
    return result


def _treasury_universe(snapshot, maturity_map=None, reference_table=None):
    stocks = snapshot.get("stocks", pd.DataFrame())
    explicit = _normalized_maturity_map(maturity_map)
    official = _reference_maturity_map(reference_table)
    records = []
    for _, row in stocks.iterrows():
        name = str(row.get("Name", ""))
        symbol = _normalise_symbol(row.get("Symbol"))
        is_candidate = symbol.startswith("اخزا") or any(
            keyword in name for keyword in ("اسناد", "خزانه", "اخزا")
        )
        if not is_candidate and symbol not in explicit and symbol not in official:
            continue
        parsed_symbol = parse_treasury_maturity(row.get("Symbol"))
        parsed_name = parse_treasury_name(name)
        candidates = {}
        if symbol in explicit:
            candidates["user_supplied_maturity"] = explicit[symbol]
        if symbol in official:
            candidates[IFB_REFERENCE_SOURCE] = official[symbol]
        if parsed_symbol is not None:
            candidates[parsed_symbol["maturity_source"]] = parsed_symbol[
                "maturity_gregorian"
            ]
        if parsed_name and parsed_name.get("bond_type") == "treasury":
            candidates["verified_name_jalali_yymmdd_fallback"] = parsed_name.get(
                "maturity_gregorian"
            )
        priority = (
            "user_supplied_maturity",
            IFB_REFERENCE_SOURCE,
            "user_confirmed_symbol_jalali_yymmdd",
            "verified_name_jalali_yymmdd_fallback",
        )
        maturity_source = next(
            (source for source in priority if candidates.get(source) is not None),
            "unresolved",
        )
        maturity = candidates.get(maturity_source)
        candidate_dates = {
            source: value.isoformat()
            for source, value in candidates.items()
            if value is not None
        }
        maturity_conflict = len(set(candidate_dates.values())) > 1
        record = row.to_dict()
        record.update(
            {
                "Ticker": (
                    parsed_name.get("ticker")
                    if parsed_name and parsed_name.get("ticker")
                    else row.get("Symbol")
                ),
                "MaturityJalali": (
                    JalaliDate.to_jalali(maturity).isoformat()
                    if maturity is not None
                    else pd.NA
                ),
                "Maturity": maturity,
                "MaturitySource": maturity_source,
                "MaturityConflict": maturity_conflict,
                "MaturityCandidates": candidate_dates,
            }
        )
        records.append(record)
    return pd.DataFrame(records)


def _select_treasuries(universe, symbol, strict=False):
    if symbol is None:
        return universe.copy(), []
    selectors = (
        [symbol]
        if isinstance(symbol, str) or not hasattr(symbol, "__iter__")
        else list(symbol)
    )
    selected_indices = []
    missing = []
    for selector in selectors:
        text = str(selector).strip()
        if text.isdigit():
            mask = universe["InsCode"].astype(str).eq(text)
        else:
            normalized = _normalise_symbol(text)
            mask = universe["Symbol"].map(_normalise_symbol).eq(normalized)
            if "Ticker" in universe:
                mask = mask | universe["Ticker"].map(_normalise_symbol).eq(normalized)
        matches = universe.index[mask].tolist()
        if len(matches) > 1:
            raise AmbiguousSymbolError(
                "Treasury selector {!r} matched {} instruments".format(
                    selector, len(matches)
                )
            )
        if not matches:
            missing.append(selector)
        else:
            selected_indices.extend(matches)
    if strict and missing:
        raise StockNotFoundError("Treasury instruments not found: {!r}".format(missing))
    selected_indices = list(dict.fromkeys(selected_indices))
    return universe.loc[selected_indices].copy(), missing


def _history_treasury_selection(
    snapshot, symbol, strict=False, maturity_map=None, reference_table=None
):
    """Resolve current instruments and recover delisted اخزا from the symbol.

    Historical treasury symbols can disappear from MarketWatch after maturity.
    Their maturity remains self-describing in the authoritative YYMMDD suffix,
    so history does not require a current listing or a guessed name field.
    """
    explicit = _normalized_maturity_map(maturity_map)
    official = _reference_maturity_map(reference_table)
    universe, missing = _select_treasuries(
        _treasury_universe(
            snapshot, maturity_map=explicit, reference_table=reference_table
        ),
        symbol,
        strict=False,
    )
    unresolved_current = universe.loc[universe["Maturity"].isna(), "Symbol"].tolist()
    if unresolved_current:
        universe = universe.loc[universe["Maturity"].notna()].copy()
        missing.extend(unresolved_current)
    recovered = []
    unresolved = []
    for selector in missing:
        text = _normalise_symbol(selector)
        parsed = parse_treasury_maturity(text)
        candidates = {}
        if text in explicit:
            candidates["user_supplied_maturity"] = explicit[text]
        if text in official:
            candidates[IFB_REFERENCE_SOURCE] = official[text]
        if parsed is not None:
            candidates[parsed["maturity_source"]] = parsed["maturity_gregorian"]
        priority = (
            "user_supplied_maturity",
            IFB_REFERENCE_SOURCE,
            "user_confirmed_symbol_jalali_yymmdd",
        )
        maturity_source = next(
            (source for source in priority if candidates.get(source) is not None),
            None,
        )
        if maturity_source is None:
            unresolved.append(selector)
            continue
        maturity = candidates[maturity_source]
        candidate_dates = {
            source: value.isoformat() for source, value in candidates.items()
        }
        recovered.append(
            {
                "InsCode": pd.NA,
                "ISIN": pd.NA,
                "Symbol": text,
                "Name": pd.NA,
                "Ticker": text,
                "MaturityJalali": JalaliDate.to_jalali(maturity).isoformat(),
                "Maturity": maturity,
                "MaturitySource": maturity_source,
                "MaturityConflict": len(set(candidate_dates.values())) > 1,
                "MaturityCandidates": candidate_dates,
            }
        )
    if recovered:
        universe = pd.concat([universe, pd.DataFrame(recovered)], ignore_index=True)
    if strict and unresolved:
        raise StockNotFoundError(
            "Treasury instruments not found: {!r}".format(unresolved)
        )
    return universe, unresolved


def _finite_float(value, default=np.nan):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _safe_count(value, default=0):
    numeric = _finite_float(value)
    if not math.isfinite(numeric):
        return default
    return int(numeric)


def _nonnegative_integer(value, name):
    if isinstance(value, bool):
        raise ValueError("{} must be a non-negative integer".format(name))
    numeric = _finite_float(value)
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        raise ValueError("{} must be a non-negative integer".format(name))
    return int(numeric)


def _instrument_timestamp(row, snapshot):
    value = row.get("Time")
    if value is None or pd.isna(value):
        return pd.NaT
    text = str(value).strip()
    if not text or text == "00:00:00":
        return pd.NaT
    trade_date = snapshot.get("trade_date")
    if trade_date is None:
        return pd.NaT
    try:
        return pd.Timestamp(
            "{} {}".format(trade_date.isoformat(), text), tz="Asia/Tehran"
        )
    except (TypeError, ValueError):
        return pd.NaT


def _choose_live_price(row, best_quote, price_source, snapshot, allow_no_trade=False):
    bid = (
        _finite_float(best_quote.get("BidPrice")) if best_quote is not None else np.nan
    )
    ask = (
        _finite_float(best_quote.get("AskPrice")) if best_quote is not None else np.nan
    )
    quote_size_valid = True
    if best_quote is not None:
        for column in ("BidVolume", "AskVolume", "BidOrderCount", "AskOrderCount"):
            if column in best_quote.index:
                quote_size_valid = (
                    quote_size_valid and _finite_float(best_quote.get(column), 0.0) > 0
                )
    quote_valid = (
        math.isfinite(bid)
        and math.isfinite(ask)
        and bid > 0
        and ask > 0
        and bid <= ask
        and quote_size_valid
    )
    volume = _safe_count(row.get("Volume"))
    trades = _safe_count(row.get("TradeCount"))
    instrument_time = _instrument_timestamp(row, snapshot)
    no_trade = volume <= 0 or trades <= 0 or pd.isna(instrument_time)
    freshness = snapshot.get("is_realtime_fresh", False)
    global_stale = not (pd.notna(freshness) and bool(freshness))
    snapshot_as_of = snapshot.get("exchange_time")
    if snapshot_as_of is None or pd.isna(snapshot_as_of):
        snapshot_as_of = snapshot.get("fetched_at", pd.NaT)
    source = str(price_source).lower()
    if source == "auto":
        if quote_valid:
            return {
                "price": (bid + ask) / 2.0,
                "source": "bid_ask_mid",
                "bid": bid,
                "ask": ask,
                "no_trade": no_trade,
                "price_as_of": snapshot_as_of,
                "instrument_stale": global_stale or pd.isna(snapshot_as_of),
            }
        value = _finite_float(row.get("Last"))
        if value > 0 and not no_trade:
            return {
                "price": value,
                "source": "last",
                "bid": bid,
                "ask": ask,
                "no_trade": no_trade,
                "price_as_of": instrument_time,
                "instrument_stale": global_stale,
            }
        value = _finite_float(row.get("Close"))
        if value > 0 and not no_trade:
            return {
                "price": value,
                "source": "close",
                "bid": bid,
                "ask": ask,
                "no_trade": no_trade,
                "price_as_of": snapshot_as_of,
                "instrument_stale": global_stale or pd.isna(snapshot_as_of),
            }
    elif source in ("mid", "bid_ask_mid"):
        if quote_valid:
            return {
                "price": (bid + ask) / 2.0,
                "source": "bid_ask_mid",
                "bid": bid,
                "ask": ask,
                "no_trade": no_trade,
                "price_as_of": snapshot_as_of,
                "instrument_stale": global_stale or pd.isna(snapshot_as_of),
            }
    elif source in ("last", "close"):
        value = _finite_float(row.get(source.capitalize()))
        if value > 0 and (not no_trade or allow_no_trade):
            return {
                "price": value,
                "source": source if not no_trade else source + "_no_trade_explicit",
                "bid": bid,
                "ask": ask,
                "no_trade": no_trade,
                "price_as_of": (
                    instrument_time if source == "last" else snapshot_as_of
                ),
                "instrument_stale": global_stale or no_trade,
            }
    else:
        raise ValueError("price_source must be 'auto', 'mid', 'last', or 'close'")
    return {
        "price": np.nan,
        "source": "unavailable",
        "bid": bid,
        "ask": ask,
        "no_trade": no_trade,
        "price_as_of": pd.NaT,
        "instrument_stale": True,
    }


def _treasury_yields_from_snapshot(
    snapshot,
    symbol=None,
    settlement_date=None,
    face_value=IRAN_TREASURY_FACE_VALUE,
    include_stale=False,
    min_volume=0,
    price_source="auto",
    day_count="ACT/365F",
    strict=False,
    face_value_source=None,
    maturity_map=None,
    reference_table=None,
    allow_no_trade=False,
):
    universe = _treasury_universe(
        snapshot, maturity_map=maturity_map, reference_table=reference_table
    )
    if universe.empty:
        result = _typed_empty(TREASURY_COLUMNS)
        result.attrs["diagnostics"] = {"excluded": [], "missing_symbols": []}
        return result
    universe, missing = _select_treasuries(universe, symbol, strict=strict)
    freshness = snapshot.get("is_realtime_fresh", False)
    stale = not (pd.notna(freshness) and bool(freshness))
    excluded = []
    if stale and not include_stale:
        result = _typed_empty(TREASURY_COLUMNS)
        result.attrs["diagnostics"] = {
            "excluded": [{"reason": "stale_snapshot", "count": len(universe)}],
            "missing_symbols": missing,
        }
        return result
    orders = snapshot.get("order_book", pd.DataFrame())
    if not orders.empty:
        level_one = orders.loc[orders["Level"].eq(1)].drop_duplicates(
            "InsCode", keep="last"
        )
        quotes = {str(row["InsCode"]): row for _, row in level_one.iterrows()}
    else:
        quotes = {}
    if settlement_date is None:
        snapshot_trade_date = snapshot.get("trade_date")
        has_trade_date = snapshot_trade_date is not None and pd.notna(
            snapshot_trade_date
        )
        settlement = snapshot_trade_date if has_trade_date else tehran_today()
        settlement_source = (
            "snapshot_trade_date" if has_trade_date else "tehran_calendar_date"
        )
    else:
        settlement = coerce_financial_date(settlement_date, "settlement_date")
        settlement_source = "user_supplied"
    settlement = coerce_financial_date(settlement, "settlement_date")
    fv_source = face_value_source or (
        "iran_treasury_market_convention_ifb_validated"
        if float(face_value) == IRAN_TREASURY_FACE_VALUE
        else "user_supplied"
    )
    records = []
    for _, row in universe.iterrows():
        volume = _safe_count(row.get("Volume"))
        if volume < int(min_volume):
            excluded.append({"InsCode": str(row["InsCode"]), "reason": "min_volume"})
            continue
        maturity = row.get("Maturity")
        if maturity is None or pd.isna(maturity):
            excluded.append(
                {"InsCode": str(row["InsCode"]), "reason": "missing_maturity"}
            )
            continue
        selected = _choose_live_price(
            row,
            quotes.get(str(row["InsCode"])),
            price_source,
            snapshot,
            allow_no_trade=allow_no_trade,
        )
        price = selected["price"]
        if not math.isfinite(price) or price <= 0:
            excluded.append(
                {"InsCode": str(row["InsCode"]), "reason": "unavailable_price"}
            )
            continue
        try:
            calculated = treasury_yield(
                price,
                maturity,
                settlement_date=settlement,
                face_value=face_value,
                day_count=day_count,
            )
        except ValueError as exc:
            excluded.append({"InsCode": str(row["InsCode"]), "reason": str(exc)})
            continue
        records.append(
            {
                "InsCode": str(row["InsCode"]),
                "ISIN": row.get("ISIN"),
                "Symbol": row.get("Symbol"),
                "Name": row.get("Name"),
                "Ticker": row.get("Ticker"),
                "MaturityJalali": row.get("MaturityJalali"),
                "Maturity": calculated["MaturityDate"],
                "MaturitySource": row.get("MaturitySource"),
                "MaturityConflict": (
                    bool(row.get("MaturityConflict"))
                    if pd.notna(row.get("MaturityConflict", False))
                    else False
                ),
                "MaturityCandidates": row.get("MaturityCandidates", {}),
                "SettlementDate": settlement,
                "DaysToMaturity": calculated["DaysToMaturity"],
                "Tenor": calculated["Tenor"],
                "Price": price,
                "PriceSource": selected["source"],
                "InstrumentValueSource": selected["source"],
                "NoTrade": selected["no_trade"],
                "InstrumentPriceAsOf": selected["price_as_of"],
                "IsInstrumentStale": selected["instrument_stale"],
                "BidPrice": selected["bid"],
                "AskPrice": selected["ask"],
                "DiscountFactor": calculated["DiscountFactor"],
                "EffectiveAnnualYield": calculated["EffectiveAnnualYield"],
                "ContinuousYield": calculated["ContinuousYield"],
                "SimpleAnnualYield": calculated["SimpleAnnualYield"],
                "BankDiscountYield": calculated["BankDiscountYield"],
                "MacaulayDuration": calculated["MacaulayDuration"],
                "ModifiedDuration": calculated["ModifiedDuration"],
                "Convexity": calculated["Convexity"],
                "DV01": calculated["DV01"],
                "Volume": volume,
                "Value": _safe_count(row.get("Value")),
                "TradeCount": _safe_count(row.get("TradeCount")),
                "FaceValue": float(face_value),
                "FaceValueSource": fv_source,
                "SettlementSource": settlement_source,
                "DayCount": str(day_count).upper(),
                "IsStale": stale,
                "SnapshotAgeSeconds": snapshot.get("snapshot_age_seconds", np.nan),
                "FetchedAt": snapshot.get("fetched_at"),
                "Status": "ok",
            }
        )
    result = pd.DataFrame(records).reindex(columns=TREASURY_COLUMNS)
    if result.empty:
        result = _typed_empty(TREASURY_COLUMNS)
    else:
        result = _cast_treasury_frame(result)
    result.attrs["diagnostics"] = {
        "excluded": excluded,
        "missing_symbols": missing,
        "snapshot_trade_date": snapshot.get("trade_date"),
        "snapshot_realtime_fresh": snapshot.get("is_realtime_fresh", False),
    }
    return result.reset_index(drop=True)


def get_treasury_yields(
    symbol=None,
    settlement_date=None,
    face_value=IRAN_TREASURY_FACE_VALUE,
    include_stale=False,
    min_volume=0,
    price_source="auto",
    day_count="ACT/365F",
    strict=False,
    face_value_source=None,
    source="tsetmc",
    maturity_date=None,
    maturity_map=None,
    allow_no_trade=False,
):
    """Return live yields for verified zero-coupon Iranian treasury bills.

    One bulk MarketWatch snapshot supplies instruments, prices and level-one
    quotes, avoiding per-symbol requests. In ``auto`` mode a valid, uncrossed
    bid/ask midpoint is preferred, followed by last and closing price.

    ``source='tsetmc'`` performs no extra reference request. ``'ifb'`` returns
    the official IFB table directly. ``'hybrid'``/``'auto'`` preserve TSETMC
    live prices and add IFB reference yields, dates and yield differences.
    """
    source = str(source).lower()
    if source not in ("tsetmc", "ifb", "hybrid", "auto"):
        raise ValueError("source must be 'tsetmc', 'ifb', 'hybrid', or 'auto'")
    face_value = float(face_value)
    if not math.isfinite(face_value) or face_value <= 0:
        raise ValueError("face_value must be positive and finite")
    min_volume = _nonnegative_integer(min_volume, "min_volume")
    if source == "ifb":
        reference = get_ifb_yield_table("treasury")
        if symbol is not None:
            selectors = (
                [symbol]
                if isinstance(symbol, str) or not hasattr(symbol, "__iter__")
                else list(symbol)
            )
            wanted = {_normalise_symbol(value) for value in selectors}
            reference = reference.loc[
                reference["Symbol"].map(_normalise_symbol).isin(wanted)
            ].reset_index(drop=True)
            if strict and len(reference) < len(wanted):
                found = set(reference["Symbol"].map(_normalise_symbol))
                raise StockNotFoundError(
                    "IFB treasury symbols not found: {!r}".format(
                        sorted(wanted - found)
                    )
                )
        return reference
    if maturity_map is not None and not isinstance(maturity_map, dict):
        raise ValueError("maturity_map must be a symbol-to-date dict")
    explicit_map = dict(maturity_map or {})
    if maturity_date is not None:
        selectors = (
            [symbol]
            if isinstance(symbol, str) or not hasattr(symbol, "__iter__")
            else list(symbol)
        )
        if symbol is None or len(selectors) != 1:
            raise ValueError("maturity_date requires exactly one symbol selector")
        explicit_map[selectors[0]] = maturity_date
    reference = None
    reference_warning = None
    if source in ("hybrid", "auto"):
        try:
            reference = get_ifb_yield_table("treasury")
        except (
            ConnectionError,
            DataParsingError,
            requests.exceptions.RequestException,
        ) as exc:
            reference_warning = (
                "IFB reference unavailable; returning TSETMC-only yields: {}".format(
                    exc
                )
            )
            warnings.warn(reference_warning, RuntimeWarning, stacklevel=2)
    snapshot = market_watch()
    live = _treasury_yields_from_snapshot(
        snapshot,
        symbol=symbol,
        settlement_date=settlement_date,
        face_value=face_value,
        include_stale=include_stale,
        min_volume=min_volume,
        price_source=price_source,
        day_count=day_count,
        strict=strict,
        face_value_source=face_value_source,
        maturity_map=explicit_map,
        reference_table=reference,
        allow_no_trade=allow_no_trade,
    )
    if reference_warning:
        diagnostics = dict(live.attrs.get("diagnostics", {}))
        diagnostics["ifb_reference_warning"] = reference_warning
        live.attrs["diagnostics"] = diagnostics
    if source == "tsetmc" or live.empty or reference is None:
        return live
    live_diagnostics = dict(live.attrs.get("diagnostics", {}))
    merge_reference = reference.rename(
        columns={
            "Price": "ReferencePrice",
            "LastTradeJalali": "ReferenceAsOfJalali",
            "LastTradeDate": "ReferenceAsOf",
            "MaturityJalali": "ReferenceMaturityJalali",
            "Maturity": "ReferenceMaturity",
        }
    )[
        [
            "Symbol",
            "ReferencePrice",
            "ReferenceAsOfJalali",
            "ReferenceAsOf",
            "ReferenceMaturityJalali",
            "ReferenceMaturity",
            "ReferenceYTM",
            "ReferenceSimpleYield",
            "ReferenceSource",
        ]
    ]
    merge_reference["_NormalizedSymbol"] = merge_reference["Symbol"].map(
        _normalise_symbol
    )
    merge_reference["ReferenceMaturity"] = pd.to_datetime(
        merge_reference["ReferenceMaturity"], errors="coerce"
    )
    merge_reference["ReferenceAsOf"] = pd.to_datetime(
        merge_reference["ReferenceAsOf"], errors="coerce"
    )
    if merge_reference["_NormalizedSymbol"].duplicated().any():
        duplicates = merge_reference.loc[
            merge_reference["_NormalizedSymbol"].duplicated(False),
            "_NormalizedSymbol",
        ].tolist()
        raise DataParsingError(
            "IFB normalized-symbol conflict: {!r}".format(duplicates)
        )
    merge_reference.drop(columns="Symbol", inplace=True)
    live["_NormalizedSymbol"] = live["Symbol"].map(_normalise_symbol)
    live = live.merge(
        merge_reference,
        on="_NormalizedSymbol",
        how="left",
        validate="one_to_one",
    ).drop(columns="_NormalizedSymbol")
    matches = pd.Series(pd.NA, index=live.index, dtype="boolean")
    has_reference = live["ReferenceMaturity"].notna()
    matches.loc[has_reference] = live.loc[has_reference, "Maturity"].eq(
        live.loc[has_reference, "ReferenceMaturity"]
    )
    live["MaturityMatchesReference"] = matches
    live["YieldDifferenceBps"] = (
        live["EffectiveAnnualYield"] - live["ReferenceYTM"]
    ) * 10_000.0
    live.loc[
        live["MaturityMatchesReference"].ne(True).fillna(True), "YieldDifferenceBps"
    ] = pd.NA
    live = _cast_treasury_frame(live)
    live_diagnostics["ifb_reference_rows"] = len(reference)
    live_diagnostics["ifb_matched_rows"] = int(live["ReferenceYTM"].notna().sum())
    live.attrs["diagnostics"] = live_diagnostics
    return live


def _history_price(row, source):
    source = str(source).lower()
    if source == "auto":
        for column, label in (("Final", "final"), ("Close", "close")):
            value = pd.to_numeric(row.get(column), errors="coerce")
            if pd.notna(value) and float(value) > 0:
                return float(value), label
    elif source in ("final", "close"):
        value = pd.to_numeric(row.get(source.capitalize()), errors="coerce")
        if pd.notna(value) and float(value) > 0:
            return float(value), source
    else:
        raise ValueError("history price_source must be 'auto', 'final', or 'close'")
    return np.nan, "unavailable"


def _date_in_range(value, start, end):
    return (start is None or value >= start) and (end is None or value <= end)


def get_treasury_yield_history(
    symbol=None,
    start=None,
    end=None,
    limit=0,
    settlement_date=None,
    face_value=IRAN_TREASURY_FACE_VALUE,
    include_today=False,
    date_format="jalali",
    price_source="auto",
    day_count="ACT/365F",
    ascending=True,
    progress=True,
    strict=False,
    face_value_source=None,
    max_requests=250,
    maturity_date=None,
    maturity_map=None,
    use_ifb_reference=False,
):
    """Return unadjusted historical yields for one or more اخزا symbols.

    Historical prices are always requested with ``auto_adjust=False``. Unless
    explicitly supplied, settlement is each observation's own trade date,
    preventing look-ahead. ``include_today`` reuses the same bulk snapshot used
    for metadata and replaces (rather than duplicates) an existing current row.
    ``symbol=None`` selects the current MarketWatch treasury universe; its
    survivor-bias provenance is reported explicitly in ``DataFrame.attrs``.
    """
    limit = _nonnegative_integer(limit, "limit")
    face_value = float(face_value)
    if not math.isfinite(face_value) or face_value <= 0:
        raise ValueError("face_value must be positive and finite")
    max_requests = validate_frequency(max_requests, "max_requests")
    if date_format not in ("jalali", "gregorian", "both"):
        raise ValueError("date_format must be 'jalali', 'gregorian', or 'both'")
    if maturity_map is not None and not isinstance(maturity_map, dict):
        raise ValueError("maturity_map must be a symbol-to-date dict")
    explicit_map = dict(maturity_map or {})
    if symbol is None:
        universe_source = (
            "current_tsetmc_market_watch_enriched_ifb"
            if use_ifb_reference
            else "current_tsetmc_market_watch"
        )
        universe_no_lookahead = False
    else:
        universe_source = "user_supplied_symbol_selector"
        # A caller-supplied list is not proof that the list existed as-of every
        # historical observation, so do not overclaim universe no-lookahead.
        universe_no_lookahead = pd.NA
    if maturity_date is not None:
        selectors = (
            [symbol]
            if isinstance(symbol, str) or not hasattr(symbol, "__iter__")
            else list(symbol)
        )
        if symbol is None or len(selectors) != 1:
            raise ValueError("maturity_date requires exactly one symbol selector")
        explicit_map[selectors[0]] = maturity_date
    initial_requests = 1 + int(bool(use_ifb_reference))
    if initial_requests > max_requests:
        raise ValueError(
            "request budget requires at least {} initial requests; max_requests={}".format(
                initial_requests, max_requests
            )
        )
    reference = None
    reference_warning = None
    if use_ifb_reference:
        try:
            reference = get_ifb_yield_table("treasury")
        except (
            ConnectionError,
            DataParsingError,
            requests.exceptions.RequestException,
        ) as exc:
            reference_warning = "IFB maturity resolver unavailable: {}".format(exc)
            warnings.warn(reference_warning, RuntimeWarning, stacklevel=2)
    snapshot = market_watch()
    universe, missing = _history_treasury_selection(
        snapshot,
        symbol,
        strict=strict,
        maturity_map=explicit_map,
        reference_table=reference,
    )
    failures = [
        {"Symbol": value, "reason": "unresolved_maturity_or_symbol"}
        for value in missing
    ]
    if universe.empty:
        result = _typed_empty(TREASURY_HISTORY_COLUMNS)
        result.attrs["diagnostics"] = {
            "failures": failures,
            "missing_symbols": missing,
            "prices_no_lookahead": True,
            "universe_no_lookahead": universe_no_lookahead,
            "no_lookahead": False if universe_no_lookahead is not True else True,
            "universe_source": universe_source,
            "request_budget": {
                "max_requests": max_requests,
                "estimated_requests_used": initial_requests,
            },
        }
        return result
    required_requests = initial_requests + 2 * len(universe)
    if required_requests > max_requests:
        raise ValueError(
            "historical request budget needs {} requests ({} initial + 2 per "
            "symbol); max_requests={}".format(
                required_requests, initial_requests, max_requests
            )
        )
    start_date = coerce_financial_date(start, "start") if start is not None else None
    end_date = coerce_financial_date(end, "end") if end is not None else None
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ValueError("end cannot be before start")
    explicit_settlement = (
        coerce_financial_date(settlement_date, "settlement_date")
        if settlement_date is not None
        else None
    )
    fv_source = face_value_source or (
        "iran_treasury_market_convention_ifb_validated"
        if float(face_value) == IRAN_TREASURY_FACE_VALUE
        else "user_supplied"
    )
    records = []
    # We apply the public limit after optional live replacement, so fetch the
    # requested number plus one historical row when today may be appended.
    fetch_limit = limit + (1 if include_today and limit > 0 else 0)
    for _, instrument in universe.iterrows():
        ticker = instrument["Symbol"]
        history = stock(
            symbol=ticker,
            start=start,
            end=end,
            limit=fetch_limit,
            auto_adjust=False,
            output_type="full",
            date_format="gregorian",
            progress=progress,
            dropna=False,
            ascending=True,
            include_today=False,
        )
        if history is None or history.empty:
            failures.append({"Symbol": ticker, "reason": "empty_history"})
            continue
        for index, row in history.iterrows():
            try:
                trade_date = coerce_financial_date(index, "trade date")
            except ValueError as exc:
                failures.append({"Symbol": ticker, "reason": str(exc)})
                continue
            if not _date_in_range(trade_date, start_date, end_date):
                continue
            row_settlement = explicit_settlement or trade_date
            if row_settlement > trade_date:
                failures.append(
                    {
                        "Symbol": ticker,
                        "TradeDate": trade_date,
                        "reason": "settlement_after_observation",
                    }
                )
                continue
            price, selected_source = _history_price(row, price_source)
            if not math.isfinite(price):
                failures.append(
                    {
                        "Symbol": ticker,
                        "TradeDate": trade_date,
                        "reason": "unavailable_price",
                    }
                )
                continue
            try:
                calculated = treasury_yield(
                    price,
                    instrument["Maturity"],
                    settlement_date=row_settlement,
                    face_value=face_value,
                    day_count=day_count,
                )
            except ValueError as exc:
                failures.append(
                    {"Symbol": ticker, "TradeDate": trade_date, "reason": str(exc)}
                )
                continue
            records.append(
                {
                    "TradeDate": trade_date,
                    "JalaliDate": JalaliDate.to_jalali(trade_date).isoformat(),
                    "InsCode": (
                        pd.NA
                        if pd.isna(instrument.get("InsCode"))
                        else str(instrument["InsCode"])
                    ),
                    "Symbol": ticker,
                    "Name": instrument["Name"],
                    "Maturity": calculated["MaturityDate"],
                    "MaturitySource": instrument.get("MaturitySource"),
                    "MaturityConflict": bool(instrument.get("MaturityConflict", False)),
                    "MaturityCandidates": instrument.get("MaturityCandidates", {}),
                    "SettlementDate": row_settlement,
                    "DaysToMaturity": calculated["DaysToMaturity"],
                    "Tenor": calculated["Tenor"],
                    "Price": price,
                    "PriceSource": selected_source,
                    "DiscountFactor": calculated["DiscountFactor"],
                    "EffectiveAnnualYield": calculated["EffectiveAnnualYield"],
                    "ContinuousYield": calculated["ContinuousYield"],
                    "SimpleAnnualYield": calculated["SimpleAnnualYield"],
                    "BankDiscountYield": calculated["BankDiscountYield"],
                    "MacaulayDuration": calculated["MacaulayDuration"],
                    "ModifiedDuration": calculated["ModifiedDuration"],
                    "Convexity": calculated["Convexity"],
                    "DV01": calculated["DV01"],
                    "Open": row.get("Open"),
                    "High": row.get("High"),
                    "Low": row.get("Low"),
                    "Close": row.get("Close"),
                    "Final": row.get("Final"),
                    "Volume": row.get("Volume"),
                    "Value": row.get("Value"),
                    "TradeCount": row.get("No."),
                    "FaceValue": float(face_value),
                    "FaceValueSource": fv_source,
                    "SettlementSource": (
                        "user_supplied" if explicit_settlement else "trade_date"
                    ),
                    "DayCount": str(day_count).upper(),
                    "IsPartial": False,
                    "FetchedAt": pd.NaT,
                    "Status": "historical",
                }
            )

    if include_today and _is_current_snapshot(snapshot):
        live = _treasury_yields_from_snapshot(
            snapshot,
            symbol=universe["Symbol"].tolist(),
            settlement_date=explicit_settlement,
            face_value=face_value,
            include_stale=True,
            min_volume=0,
            price_source=("close" if price_source in ("auto", "final") else "last"),
            day_count=day_count,
            strict=False,
            face_value_source=fv_source,
            maturity_map=explicit_map,
            reference_table=reference,
        )
        for _, row in live.iterrows():
            trade_date = snapshot["trade_date"]
            if not _date_in_range(trade_date, start_date, end_date):
                continue
            if explicit_settlement is not None and explicit_settlement > trade_date:
                continue
            records = [
                item
                for item in records
                if not (
                    item["Symbol"] == row["Symbol"] and item["TradeDate"] == trade_date
                )
            ]
            records.append(
                {
                    "TradeDate": trade_date,
                    "JalaliDate": JalaliDate.to_jalali(trade_date).isoformat(),
                    "InsCode": row["InsCode"],
                    "Symbol": row["Symbol"],
                    "Name": row["Name"],
                    "Maturity": row["Maturity"],
                    "MaturitySource": row["MaturitySource"],
                    "MaturityConflict": row["MaturityConflict"],
                    "MaturityCandidates": row["MaturityCandidates"],
                    "SettlementDate": row["SettlementDate"],
                    "DaysToMaturity": row["DaysToMaturity"],
                    "Tenor": row["Tenor"],
                    "Price": row["Price"],
                    "PriceSource": row["PriceSource"],
                    "DiscountFactor": row["DiscountFactor"],
                    "EffectiveAnnualYield": row["EffectiveAnnualYield"],
                    "ContinuousYield": row["ContinuousYield"],
                    "SimpleAnnualYield": row["SimpleAnnualYield"],
                    "BankDiscountYield": row["BankDiscountYield"],
                    "MacaulayDuration": row["MacaulayDuration"],
                    "ModifiedDuration": row["ModifiedDuration"],
                    "Convexity": row["Convexity"],
                    "DV01": row["DV01"],
                    "Open": np.nan,
                    "High": np.nan,
                    "Low": np.nan,
                    "Close": row["Price"],
                    "Final": row["Price"],
                    "Volume": row["Volume"],
                    "Value": row["Value"],
                    "TradeCount": row["TradeCount"],
                    "FaceValue": row["FaceValue"],
                    "FaceValueSource": row["FaceValueSource"],
                    "SettlementSource": row["SettlementSource"],
                    "DayCount": row["DayCount"],
                    "IsPartial": snapshot.get("is_partial", pd.NA),
                    "FetchedAt": row["FetchedAt"],
                    "Status": "live_snapshot",
                }
            )

    result = pd.DataFrame(records)
    if result.empty:
        result = _typed_empty(TREASURY_HISTORY_COLUMNS)
    else:
        result.sort_values(["Symbol", "TradeDate"], inplace=True)
        if limit > 0:
            result = result.groupby("Symbol", group_keys=False).tail(limit)
        if not ascending:
            result = result.sort_values(
                ["Symbol", "TradeDate"], ascending=[True, False]
            )
        if date_format == "jalali":
            result["Date"] = result["JalaliDate"]
        elif date_format == "gregorian":
            result["Date"] = result["TradeDate"]
        elif date_format == "both":
            result["Date"] = result["TradeDate"]
        else:
            raise ValueError("date_format must be 'jalali', 'gregorian', or 'both'")
        result = result.reindex(columns=TREASURY_HISTORY_COLUMNS).reset_index(drop=True)
        result = _cast_treasury_frame(result)
    result.attrs["diagnostics"] = {
        "failures": failures,
        "missing_symbols": missing,
        "auto_adjust": False,
        "prices_no_lookahead": True,
        "universe_no_lookahead": universe_no_lookahead,
        "no_lookahead": False if universe_no_lookahead is not True else True,
        "universe_source": universe_source,
        "include_today_requested": bool(include_today),
        "snapshot_trade_date": snapshot.get("trade_date"),
        "ifb_reference_warning": reference_warning,
        "request_budget": {
            "max_requests": max_requests,
            "estimated_requests_used": required_requests,
            "initial_requests": initial_requests,
            "per_symbol_requests": 2,
        },
    }
    return result


# Additive naming alias: live and historical plural APIs now read symmetrically.
get_treasury_yields_history = get_treasury_yield_history


def get_yield_curve(
    symbol=None,
    settlement_date=None,
    face_value=IRAN_TREASURY_FACE_VALUE,
    include_stale=False,
    min_volume=0,
    min_nodes=3,
    price_source="auto",
    day_count="ACT/365F",
    interpolation="log_discount",
    extrapolate=False,
    duplicate_policy="volume_weighted",
    enforce_monotonic_discount=True,
    source="tsetmc",
):
    """Build the current zero curve from live اخزا nodes."""
    min_nodes = validate_frequency(min_nodes, "min_nodes")
    if str(source).lower() == "ifb":
        raise ValueError(
            "source='ifb' rows may have different reference dates and cannot "
            "form one no-lookahead curve; use source='hybrid' or 'tsetmc'"
        )
    nodes = get_treasury_yields(
        symbol=symbol,
        settlement_date=settlement_date,
        face_value=face_value,
        include_stale=include_stale,
        min_volume=min_volume,
        price_source=price_source,
        day_count=day_count,
        source=source,
    )
    if nodes.empty:
        raise ValueError("yield curve has no usable nodes")
    settlement = nodes["SettlementDate"].iloc[0]
    curve = build_yield_curve(
        nodes,
        settlement_date=settlement,
        interpolation=interpolation,
        extrapolate=extrapolate,
        duplicate_policy=duplicate_policy,
        day_count=day_count,
        enforce_monotonic_discount=enforce_monotonic_discount,
    )
    if len(curve.maturities) < min_nodes:
        raise ValueError(
            "yield curve requires at least {} distinct maturities after "
            "calibration; got {} from {} input nodes".format(
                min_nodes, len(curve.maturities), len(nodes)
            )
        )
    return curve


CURVE_HISTORY_COLUMNS = TREASURY_HISTORY_COLUMNS + [
    "CurveID",
    "CurveStatus",
    "CurveError",
    "CurveNodeCount",
    "InputNodeCount",
    "CalibratedNodeCount",
    "CurveInterpolation",
    "CurvePricesNoLookahead",
    "CurveUniverseNoLookahead",
    "CurveNoLookahead",
    "UniverseSource",
]


def get_yield_curve_history(
    symbol=None,
    start=None,
    end=None,
    limit=0,
    face_value=IRAN_TREASURY_FACE_VALUE,
    include_today=False,
    date_format="jalali",
    price_source="auto",
    day_count="ACT/365F",
    min_nodes=3,
    interpolation="log_discount",
    duplicate_policy="volume_weighted",
    enforce_monotonic_discount=True,
    ascending=True,
    progress=True,
    max_requests=250,
    maturity_map=None,
):
    """Return dated curve-node panels calibrated without future observations."""
    min_nodes = validate_frequency(min_nodes, "min_nodes")
    max_requests = validate_frequency(max_requests, "max_requests")
    history_symbol = symbol
    history_maturity_map = dict(maturity_map or {})
    universe_source = "user_supplied_symbols"
    external_requests = 0
    if symbol is None and history_maturity_map:
        history_symbol = list(history_maturity_map)
        universe_source = "user_supplied_maturity_map"
    elif symbol is None:
        if max_requests <= 1:
            raise ValueError(
                "symbol=None curve history needs one IFB universe request plus history budget"
            )
        external_requests = 1
        try:
            catalog = get_ifb_yield_table("latest_history")
        except (
            ConnectionError,
            DataParsingError,
            requests.exceptions.RequestException,
        ):
            catalog = pd.DataFrame()
        if not catalog.empty:
            history_symbol = catalog["Symbol"].dropna().tolist()
            history_maturity_map.update(
                dict(zip(catalog["Symbol"], catalog["Maturity"]))
            )
            universe_source = "ifb_latest_history_initial"
        else:
            history_symbol = None
            universe_source = "current_marketwatch_fallback"
    history = get_treasury_yield_history(
        history_symbol,
        start=start,
        end=end,
        limit=limit,
        face_value=face_value,
        include_today=include_today,
        date_format=date_format,
        price_source=price_source,
        day_count=day_count,
        ascending=True,
        progress=progress,
        max_requests=max_requests - external_requests,
        maturity_map=history_maturity_map,
    )
    if history.empty:
        result = _typed_empty(CURVE_HISTORY_COLUMNS)
        result.attrs["diagnostics"] = {
            "curves": [],
            "source": history.attrs.get("diagnostics", {}),
            "prices_no_lookahead": True,
            "universe_no_lookahead": False,
            "no_lookahead": False,
            "universe_source": universe_source,
            "external_requests": external_requests,
        }
        return result
    panels = []
    diagnostics = []
    for trade_date, group in history.groupby("TradeDate", sort=True):
        curve_id = "treasury-{}".format(trade_date.strftime("%Y%m%d"))
        status = "invalid"
        error = None
        calibrated_count = 0
        try:
            curve = build_yield_curve(
                group,
                settlement_date=trade_date,
                interpolation=interpolation,
                duplicate_policy=duplicate_policy,
                day_count=day_count,
                enforce_monotonic_discount=enforce_monotonic_discount,
            )
            calibrated_count = len(curve.maturities)
            if calibrated_count < min_nodes:
                status = "insufficient_nodes"
                error = "requires {} distinct maturities, got {} from {} inputs".format(
                    min_nodes, calibrated_count, len(group)
                )
            else:
                status = "valid"
        except ValueError as exc:
            error = str(exc)
        panel = group.copy()
        panel["CurveID"] = curve_id
        panel["CurveStatus"] = status
        panel["CurveError"] = error
        panel["CurveNodeCount"] = calibrated_count
        panel["InputNodeCount"] = len(group)
        panel["CalibratedNodeCount"] = calibrated_count
        panel["CurveInterpolation"] = interpolation
        panel["CurvePricesNoLookahead"] = True
        panel["CurveUniverseNoLookahead"] = False
        panel["CurveNoLookahead"] = False
        panel["UniverseSource"] = universe_source
        panels.append(panel)
        diagnostics.append(
            {
                "CurveID": curve_id,
                "TradeDate": trade_date,
                "Status": status,
                "Error": error,
                "InputNodeCount": len(group),
                "CalibratedNodeCount": calibrated_count,
                "UniverseSource": universe_source,
            }
        )
    result = _cast_treasury_frame(
        pd.concat(panels, ignore_index=True).reindex(columns=CURVE_HISTORY_COLUMNS)
    )
    if not ascending:
        result = result.sort_values(
            ["TradeDate", "Symbol"], ascending=[False, True]
        ).reset_index(drop=True)
    result.attrs["diagnostics"] = {
        "curves": diagnostics,
        "source": history.attrs.get("diagnostics", {}),
        "prices_no_lookahead": True,
        "universe_no_lookahead": False,
        "no_lookahead": False,
        "universe_source": universe_source,
        "external_requests": external_requests,
    }
    return result


__all__ = [
    "IRAN_TREASURY_FACE_VALUE",
    "YieldCurve",
    "treasury_yield",
    "bond_price",
    "yield_to_maturity",
    "bond_analytics",
    "build_yield_curve",
    "get_ifb_yield_table",
    "get_treasury_yields",
    "get_treasury_yield_history",
    "get_treasury_yields_history",
    "get_yield_curve",
    "get_yield_curve_history",
]
