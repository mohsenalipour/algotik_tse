"""Deterministic Black--Scholes analytics for European options.

All prices and first/second order sensitivities are expressed per one unit of
the underlying.  Contract-scaled values belong in the market-facing options
module, where the exchange supplied contract size is available.
"""

import math


def _finite(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _inputs(spot, strike, time_to_expiry, rate, volatility=None, dividend_yield=0.0):
    spot = _finite(spot, "spot")
    strike = _finite(strike, "strike")
    time_to_expiry = _finite(time_to_expiry, "time_to_expiry")
    rate = _finite(rate, "rate")
    dividend_yield = _finite(dividend_yield, "dividend_yield")
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if time_to_expiry < 0:
        raise ValueError("time_to_expiry cannot be negative")
    if abs(rate * time_to_expiry) > 700 or abs(dividend_yield * time_to_expiry) > 700:
        raise ValueError("discount exponent is outside the stable numeric range")
    if volatility is not None:
        volatility = _finite(volatility, "volatility")
        if volatility < 0:
            raise ValueError("volatility cannot be negative")
    return spot, strike, time_to_expiry, rate, volatility, dividend_yield


def _option_type(option_type):
    value = str(option_type).strip().lower()
    aliases = {"c": "call", "call": "call", "p": "put", "put": "put"}
    if value not in aliases:
        raise ValueError("option_type must be 'call' or 'put'")
    return aliases[value]


def _style(exercise_style):
    if str(exercise_style).strip().lower() != "european":
        raise ValueError("only exercise_style='european' is supported")


def _norm_cdf(value):
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _norm_pdf(value):
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def option_price_bounds(
    spot,
    strike,
    time_to_expiry,
    rate,
    option_type="call",
    dividend_yield=0.0,
    exercise_style="european",
):
    """Return model-independent European lower/upper price bounds."""
    _style(exercise_style)
    kind = _option_type(option_type)
    spot, strike, time_to_expiry, rate, _, dividend_yield = _inputs(
        spot, strike, time_to_expiry, rate, dividend_yield=dividend_yield
    )
    discounted_spot = spot * math.exp(-dividend_yield * time_to_expiry)
    discounted_strike = strike * math.exp(-rate * time_to_expiry)
    if kind == "call":
        return max(0.0, discounted_spot - discounted_strike), discounted_spot
    return max(0.0, discounted_strike - discounted_spot), discounted_strike


def black_scholes_price(
    spot,
    strike,
    time_to_expiry,
    rate,
    volatility,
    option_type="call",
    dividend_yield=0.0,
    exercise_style="european",
):
    """Price a European call/put per one underlying unit.

    ``rate`` and ``dividend_yield`` are continuously-compounded annual rates.
    At expiry the function returns intrinsic value.  At zero volatility it
    returns the deterministic discounted payoff limit.
    """
    _style(exercise_style)
    kind = _option_type(option_type)
    spot, strike, time_to_expiry, rate, volatility, dividend_yield = _inputs(
        spot, strike, time_to_expiry, rate, volatility, dividend_yield
    )
    if time_to_expiry == 0:
        return max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)
    discounted_spot = spot * math.exp(-dividend_yield * time_to_expiry)
    discounted_strike = strike * math.exp(-rate * time_to_expiry)
    if volatility == 0:
        deterministic = discounted_spot - discounted_strike
        return max(deterministic, 0.0) if kind == "call" else max(-deterministic, 0.0)
    root_time = math.sqrt(time_to_expiry)
    d1 = (
        math.log(spot / strike)
        + (rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry
    ) / (volatility * root_time)
    d2 = d1 - volatility * root_time
    if kind == "call":
        return discounted_spot * _norm_cdf(d1) - discounted_strike * _norm_cdf(d2)
    return discounted_strike * _norm_cdf(-d2) - discounted_spot * _norm_cdf(-d1)


def black_scholes_greeks(
    spot,
    strike,
    time_to_expiry,
    rate,
    volatility,
    option_type="call",
    dividend_yield=0.0,
    exercise_style="european",
):
    """Return explicitly-scaled European Black--Scholes Greeks.

    Delta and Gamma are per underlying unit; Vega and Rho are per 1.0 change
    in volatility/rate, with ``Vega1Pct`` and ``Rho100bp`` provided for a one
    percentage-point move. Theta is returned per year and per calendar day.
    """
    _style(exercise_style)
    kind = _option_type(option_type)
    spot, strike, time_to_expiry, rate, volatility, dividend_yield = _inputs(
        spot, strike, time_to_expiry, rate, volatility, dividend_yield
    )
    if time_to_expiry <= 0 or volatility <= 0:
        return {
            "Delta": math.nan,
            "Gamma": math.nan,
            "Vega": math.nan,
            "Vega1Pct": math.nan,
            "ThetaPerYear": math.nan,
            "ThetaPerDay": math.nan,
            "Rho": math.nan,
            "Rho100bp": math.nan,
            "Status": "undefined_at_expiry_or_zero_volatility",
        }
    root_time = math.sqrt(time_to_expiry)
    d1 = (
        math.log(spot / strike)
        + (rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry
    ) / (volatility * root_time)
    d2 = d1 - volatility * root_time
    spot_discount = math.exp(-dividend_yield * time_to_expiry)
    strike_discount = math.exp(-rate * time_to_expiry)
    density = _norm_pdf(d1)
    gamma = spot_discount * density / (spot * volatility * root_time)
    vega = spot * spot_discount * density * root_time
    theta_common = -(spot * spot_discount * density * volatility) / (2.0 * root_time)
    if kind == "call":
        delta = spot_discount * _norm_cdf(d1)
        theta = (
            theta_common
            - rate * strike * strike_discount * _norm_cdf(d2)
            + dividend_yield * spot * spot_discount * _norm_cdf(d1)
        )
        rho = strike * time_to_expiry * strike_discount * _norm_cdf(d2)
    else:
        delta = spot_discount * (_norm_cdf(d1) - 1.0)
        theta = (
            theta_common
            + rate * strike * strike_discount * _norm_cdf(-d2)
            - dividend_yield * spot * spot_discount * _norm_cdf(-d1)
        )
        rho = -strike * time_to_expiry * strike_discount * _norm_cdf(-d2)
    return {
        "Delta": delta,
        "Gamma": gamma,
        "Vega": vega,
        "Vega1Pct": vega * 0.01,
        "ThetaPerYear": theta,
        "ThetaPerDay": theta / 365.0,
        "Rho": rho,
        "Rho100bp": rho * 0.01,
        "Status": "ok",
    }


def implied_volatility(
    option_price,
    spot,
    strike,
    time_to_expiry,
    rate,
    option_type="call",
    dividend_yield=0.0,
    exercise_style="european",
    lower_volatility=0.0,
    upper_volatility=5.0,
    tolerance=1e-8,
    max_iterations=200,
):
    """Solve implied volatility by a bracketed bisection.

    A dict is returned so invalid observations never masquerade as a numeric
    IV. ``Status`` is one of ``ok``, ``missing``, ``expiry``,
    ``out_of_bounds``, ``no_bracket`` or ``non_converged``.
    """
    _style(exercise_style)
    kind = _option_type(option_type)
    tolerance = _finite(tolerance, "tolerance")
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    if (
        isinstance(max_iterations, bool)
        or int(max_iterations) != max_iterations
        or max_iterations <= 0
    ):
        raise ValueError("max_iterations must be a positive integer")
    try:
        price = float(option_price)
    except (TypeError, ValueError):
        return {"ImpliedVolatility": math.nan, "Status": "missing", "Iterations": 0}
    if not math.isfinite(price):
        return {"ImpliedVolatility": math.nan, "Status": "missing", "Iterations": 0}
    spot, strike, time_to_expiry, rate, _, dividend_yield = _inputs(
        spot, strike, time_to_expiry, rate, dividend_yield=dividend_yield
    )
    if time_to_expiry == 0:
        return {"ImpliedVolatility": math.nan, "Status": "expiry", "Iterations": 0}
    lower_bound, upper_bound = option_price_bounds(
        spot, strike, time_to_expiry, rate, kind, dividend_yield, exercise_style
    )
    scale_tolerance = max(float(tolerance), 1e-12) * max(1.0, spot, strike)
    if price < lower_bound - scale_tolerance or price > upper_bound + scale_tolerance:
        return {
            "ImpliedVolatility": math.nan,
            "Status": "out_of_bounds",
            "Iterations": 0,
            "LowerBound": lower_bound,
            "UpperBound": upper_bound,
        }
    low = _finite(lower_volatility, "lower_volatility")
    high = _finite(upper_volatility, "upper_volatility")
    if low < 0 or high <= low:
        raise ValueError("volatility bracket must satisfy 0 <= lower < upper")
    low_price = black_scholes_price(
        spot, strike, time_to_expiry, rate, low, kind, dividend_yield
    )
    high_price = black_scholes_price(
        spot, strike, time_to_expiry, rate, high, kind, dividend_yield
    )
    if abs(price - low_price) <= scale_tolerance:
        return {"ImpliedVolatility": low, "Status": "ok", "Iterations": 0}
    if price < low_price - scale_tolerance or price > high_price + scale_tolerance:
        return {
            "ImpliedVolatility": math.nan,
            "Status": "no_bracket",
            "Iterations": 0,
            "LowerBound": lower_bound,
            "UpperBound": upper_bound,
        }
    for iteration in range(1, int(max_iterations) + 1):
        middle = (low + high) / 2.0
        model = black_scholes_price(
            spot, strike, time_to_expiry, rate, middle, kind, dividend_yield
        )
        if abs(model - price) <= scale_tolerance or high - low <= tolerance:
            return {
                "ImpliedVolatility": middle,
                "Status": "ok",
                "Iterations": iteration,
            }
        if model < price:
            low = middle
        else:
            high = middle
    return {
        "ImpliedVolatility": math.nan,
        "CandidateVolatility": (low + high) / 2.0,
        "Status": "non_converged",
        "Iterations": int(max_iterations),
    }


__all__ = [
    "black_scholes_price",
    "black_scholes_greeks",
    "option_price_bounds",
    "implied_volatility",
]
