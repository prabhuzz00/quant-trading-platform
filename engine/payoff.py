"""Payoff diagram calculator for multi-leg options strategies.

Generates P&L arrays across a range of spot prices at various
days-to-expiry values, suitable for rendering interactive payoff charts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.greeks import black_scholes


@dataclass
class PayoffPoint:
    """Single point on a payoff curve."""
    spot: float
    pnl: float


@dataclass
class PayoffCurve:
    """One payoff curve for a given DTE."""
    label: str
    dte: int
    points: List[PayoffPoint]


@dataclass
class PayoffResult:
    """Complete payoff diagram data for a strategy."""
    strategy_id: str
    strategy_name: str
    current_spot: float
    net_premium: float
    max_profit: Optional[float]
    max_loss: Optional[float]
    breakevens: List[float]
    curves: List[PayoffCurve]
    legs_detail: List[Dict[str, Any]] = field(default_factory=list)


def compute_payoff(
    strategy_id: str,
    strategy_name: str,
    spot: float,
    legs: List[Dict[str, Any]],
    iv: float = 0.15,
    rate: float = 0.07,
    dte_values: Optional[List[int]] = None,
    spot_range_pct: float = 10.0,
    num_points: int = 100,
) -> PayoffResult:
    """Compute payoff diagram for a multi-leg strategy.

    Parameters
    ----------
    spot : float
        Current underlying price.
    legs : list of dict
        Each dict: ``option_type`` ("CE"/"PE"), ``action`` ("BUY"/"SELL"),
        ``strike`` (float, absolute strike), ``quantity`` (int),
        ``premium`` (float, optional — auto-calculated if omitted).
    iv : float
        Implied volatility (decimal).
    dte_values : list of int or None
        Days to expiry to plot.  Defaults to [0, 3, 7, 14, 30].
    spot_range_pct : float
        % range around current spot to plot.
    num_points : int
        Number of price points per curve.
    """
    if dte_values is None:
        dte_values = [0, 3, 7, 14, 30]

    spot_low = spot * (1 - spot_range_pct / 100.0)
    spot_high = spot * (1 + spot_range_pct / 100.0)
    step = (spot_high - spot_low) / max(num_points - 1, 1)
    spot_prices = [round(spot_low + i * step, 2) for i in range(num_points)]

    # --- Compute entry premiums (at current spot, max DTE) ---
    max_dte = max(dte_values) if dte_values else 30
    entry_premiums: List[float] = []
    legs_detail: List[Dict[str, Any]] = []

    for leg in legs:
        strike = leg["strike"]
        is_call = leg["option_type"].upper() == "CE"
        qty = leg.get("quantity", 1)
        action = leg["action"].upper()
        sign = 1 if action == "BUY" else -1

        if "premium" in leg and leg["premium"] is not None:
            entry_px = leg["premium"]
        else:
            tte = max_dte / 365.0
            entry_px = black_scholes(spot, strike, tte, iv, rate, is_call).price

        entry_premiums.append(entry_px * sign * qty)
        legs_detail.append({
            "option_type": leg["option_type"],
            "action": action,
            "strike": strike,
            "quantity": qty,
            "entry_premium": round(entry_px, 2),
        })

    net_premium = sum(entry_premiums)

    # --- Generate curves for each DTE ---
    curves: List[PayoffCurve] = []
    expiry_pnls: List[float] = []  # P&L at DTE=0 for breakeven/max calc

    for dte in sorted(dte_values):
        points: List[PayoffPoint] = []
        for s in spot_prices:
            leg_values: List[float] = []
            for idx, leg in enumerate(legs):
                strike = leg["strike"]
                is_call = leg["option_type"].upper() == "CE"
                qty = leg.get("quantity", 1)
                action = leg["action"].upper()
                sign = 1 if action == "BUY" else -1

                if dte == 0:
                    # At expiry: intrinsic value only
                    px = max(s - strike, 0.0) if is_call else max(strike - s, 0.0)
                else:
                    tte = dte / 365.0
                    px = black_scholes(s, strike, tte, iv, rate, is_call).price

                leg_values.append(px * sign * qty)

            total_value = sum(leg_values)
            pnl = total_value - net_premium
            points.append(PayoffPoint(spot=s, pnl=round(pnl, 2)))

            if dte == 0:
                expiry_pnls.append(pnl)

        label = "At Expiry" if dte == 0 else f"{dte}D to Expiry"
        curves.append(PayoffCurve(label=label, dte=dte, points=points))

    # --- Compute breakevens at expiry ---
    breakevens: List[float] = []
    if expiry_pnls:
        for i in range(1, len(expiry_pnls)):
            if expiry_pnls[i - 1] * expiry_pnls[i] < 0:
                # Linear interpolation
                frac = abs(expiry_pnls[i - 1]) / (abs(expiry_pnls[i - 1]) + abs(expiry_pnls[i]))
                be = spot_prices[i - 1] + frac * step
                breakevens.append(round(be, 2))

    max_profit_val = max(expiry_pnls, default=None)
    max_loss_val = min(expiry_pnls, default=None)

    return PayoffResult(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        current_spot=spot,
        net_premium=round(net_premium, 2),
        max_profit=round(max_profit_val, 2) if max_profit_val is not None else None,
        max_loss=round(max_loss_val, 2) if max_loss_val is not None else None,
        breakevens=breakevens,
        curves=curves,
        legs_detail=legs_detail,
    )
