"""Black-Scholes option pricing and Greeks calculator.

Provides analytical pricing for European options plus all first-order Greeks
(Delta, Gamma, Theta, Vega, Rho) used by the strategy builder, backtester,
and Greeks analysis tabs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Normal distribution helpers (pure Python — no scipy dependency needed)
# ---------------------------------------------------------------------------


def _norm_cdf(x: float) -> float:
    """Cumulative distribution function for standard normal."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Probability density function for standard normal."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# ---------------------------------------------------------------------------
# Black-Scholes core
# ---------------------------------------------------------------------------


@dataclass
class GreeksResult:
    """Container for option price and Greeks."""
    price: float
    delta: float
    gamma: float
    theta: float  # per calendar day
    vega: float   # per 1% change in IV
    rho: float    # per 1% change in rate
    iv: Optional[float] = None  # implied volatility if computed


def black_scholes(
    spot: float,
    strike: float,
    tte: float,          # time to expiry in years
    iv: float,           # implied volatility (annualised, e.g. 0.20 = 20%)
    rate: float = 0.07,  # risk-free rate (default 7% for Indian markets)
    is_call: bool = True,
) -> GreeksResult:
    """Compute Black-Scholes price and Greeks for a European option.

    Parameters
    ----------
    spot : float
        Current underlying price.
    strike : float
        Option strike price.
    tte : float
        Time to expiry in *years* (e.g. 7/365 for a weekly expiry).
    iv : float
        Annualised implied volatility as a decimal (0.15 = 15%).
    rate : float
        Risk-free interest rate as a decimal.
    is_call : bool
        ``True`` for Call, ``False`` for Put.

    Returns
    -------
    GreeksResult
        Option price plus Delta, Gamma, Theta, Vega, Rho.
    """
    if tte <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        # At/past expiry — return intrinsic value.
        intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
        delta = (1.0 if spot > strike else 0.0) if is_call else (-1.0 if spot < strike else 0.0)
        return GreeksResult(
            price=intrinsic,
            delta=delta,
            gamma=0.0,
            theta=0.0,
            vega=0.0,
            rho=0.0,
            iv=iv,
        )

    sqrt_t = math.sqrt(tte)
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * tte) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t

    discount = math.exp(-rate * tte)

    if is_call:
        price = spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        rho = strike * tte * discount * _norm_cdf(d2) / 100.0
    else:
        price = strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
        rho = -strike * tte * discount * _norm_cdf(-d2) / 100.0

    gamma = _norm_pdf(d1) / (spot * iv * sqrt_t)
    theta = (
        -(spot * _norm_pdf(d1) * iv) / (2.0 * sqrt_t)
        - rate * strike * discount * (_norm_cdf(d2) if is_call else _norm_cdf(-d2))
        * (1 if is_call else -1)
    ) / 365.0  # per calendar day
    vega = spot * _norm_pdf(d1) * sqrt_t / 100.0  # per 1% IV change

    return GreeksResult(
        price=round(price, 4),
        delta=round(delta, 6),
        gamma=round(gamma, 6),
        theta=round(theta, 4),
        vega=round(vega, 4),
        rho=round(rho, 4),
        iv=iv,
    )


# ---------------------------------------------------------------------------
# Implied Volatility solver (Newton-Raphson)
# ---------------------------------------------------------------------------


def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    tte: float,
    rate: float = 0.07,
    is_call: bool = True,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    """Solve for implied volatility using Newton-Raphson.

    Returns the annualised IV as a decimal.  Returns ``0.0`` if the solver
    cannot converge (e.g. deep OTM with near-zero market price).
    """
    if market_price <= 0 or tte <= 0:
        return 0.0

    sigma = 0.25  # initial guess
    for _ in range(max_iter):
        result = black_scholes(spot, strike, tte, sigma, rate, is_call)
        diff = result.price - market_price
        vega_raw = result.vega * 100.0  # convert back from per-1%
        if vega_raw < 1e-10:
            break
        sigma -= diff / vega_raw
        sigma = max(sigma, 0.001)
        if abs(diff) < tol:
            return round(sigma, 6)
    return round(max(sigma, 0.0), 6)


# ---------------------------------------------------------------------------
# Strategy-level Greeks aggregation
# ---------------------------------------------------------------------------


@dataclass
class LegGreeks:
    """Greeks for a single strategy leg."""
    description: str
    action: str        # "BUY" or "SELL"
    option_type: str   # "CE" or "PE"
    strike: float
    quantity: int
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


@dataclass
class StrategyGreeks:
    """Aggregated Greeks for a complete multi-leg strategy."""
    net_price: float       # net premium (positive = debit, negative = credit)
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    net_rho: float
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    legs: List[LegGreeks] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.legs is None:
            self.legs = []


def compute_strategy_greeks(
    spot: float,
    strikes: List[float],
    option_types: List[str],        # "CE" or "PE"
    actions: List[str],             # "BUY" or "SELL"
    quantities: List[int],
    tte: float,
    iv: float,
    rate: float = 0.07,
    descriptions: Optional[List[str]] = None,
) -> StrategyGreeks:
    """Compute aggregated Greeks for a multi-leg options strategy.

    Each parallel list element defines one leg.
    """
    n = len(strikes)
    if descriptions is None:
        descriptions = [f"Leg {i+1}" for i in range(n)]

    legs: List[LegGreeks] = []
    net_price = 0.0
    net_delta = 0.0
    net_gamma = 0.0
    net_theta = 0.0
    net_vega = 0.0
    net_rho = 0.0

    for i in range(n):
        is_call = option_types[i].upper() == "CE"
        result = black_scholes(spot, strikes[i], tte, iv, rate, is_call)
        sign = 1 if actions[i].upper() == "BUY" else -1
        qty = quantities[i]

        legs.append(LegGreeks(
            description=descriptions[i],
            action=actions[i],
            option_type=option_types[i],
            strike=strikes[i],
            quantity=qty,
            price=round(result.price * sign * qty, 4),
            delta=round(result.delta * sign * qty, 6),
            gamma=round(result.gamma * sign * qty, 6),
            theta=round(result.theta * sign * qty, 4),
            vega=round(result.vega * sign * qty, 4),
            rho=round(result.rho * sign * qty, 4),
        ))

        net_price += result.price * sign * qty
        net_delta += result.delta * sign * qty
        net_gamma += result.gamma * sign * qty
        net_theta += result.theta * sign * qty
        net_vega += result.vega * sign * qty
        net_rho += result.rho * sign * qty

    return StrategyGreeks(
        net_price=round(net_price, 4),
        net_delta=round(net_delta, 6),
        net_gamma=round(net_gamma, 6),
        net_theta=round(net_theta, 4),
        net_vega=round(net_vega, 4),
        net_rho=round(net_rho, 4),
        legs=legs,
    )
