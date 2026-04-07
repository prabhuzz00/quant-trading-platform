"""Black-Scholes model backtesting engine.

Simulates strategy performance over a configurable date range using
Black-Scholes theoretical pricing.  Produces equity curves, trade logs,
and summary statistics (Sharpe ratio, max drawdown, win rate, etc.).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from engine.greeks import black_scholes


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BacktestTrade:
    """One round-trip trade produced by the backtester."""
    trade_id: int
    strategy_id: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    legs: List[Dict[str, Any]] = field(default_factory=list)
    exit_reason: str = "expiry"


@dataclass
class BacktestResult:
    """Complete result of a backtest run."""
    strategy_id: str
    strategy_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    max_pnl: float
    min_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    equity_curve: List[Dict[str, Any]]  # [{date, equity, drawdown}]
    monthly_pnl: List[Dict[str, Any]]   # [{month, pnl}]
    trades: List[BacktestTrade]
    parameters: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Backtester engine
# ---------------------------------------------------------------------------

def run_backtest(
    strategy_id: str,
    strategy_name: str,
    legs_config: List[Dict[str, Any]],
    spot: float = 22000.0,
    iv: float = 0.15,
    rate: float = 0.07,
    hold_days: int = 7,
    stop_loss_mult: float = 2.0,
    profit_target_pct: float = 0.50,
    start_date: Optional[str] = None,   # YYYY-MM-DD
    end_date: Optional[str] = None,     # YYYY-MM-DD
    num_trades: int = 52,
    annual_drift: float = 0.10,
    annual_vol: float = 0.15,
) -> BacktestResult:
    """Run a Black-Scholes model backtest for a strategy.

    Parameters
    ----------
    strategy_id : str
        Strategy identifier from the catalog.
    strategy_name : str
        Human-readable strategy name.
    legs_config : list of dict
        Each dict has keys: ``option_type`` ("CE"/"PE"), ``action`` ("BUY"/"SELL"),
        ``strike_offset`` (float, points from ATM), ``quantity`` (int).
    spot : float
        Initial underlying spot price.
    iv : float
        Annualised implied volatility (decimal).
    hold_days : int
        Days each trade is held before exit.
    stop_loss_mult : float
        Stop loss as multiple of initial premium.
    profit_target_pct : float
        Take profit as fraction of initial premium.
    start_date / end_date : str or None
        Date range (ISO format).  Defaults to last 12 months.
    num_trades : int
        Number of simulated entry points.
    annual_drift / annual_vol : float
        GBM parameters for simulating spot movement.
    """
    # --- Resolve dates -------------------------------------------------------
    if end_date:
        dt_end = date.fromisoformat(end_date)
    else:
        dt_end = date.today()
    if start_date:
        dt_start = date.fromisoformat(start_date)
    else:
        dt_start = dt_end - timedelta(days=365)

    total_days = (dt_end - dt_start).days
    if total_days < hold_days:
        total_days = hold_days * 2
    interval = max(total_days // num_trades, 1)

    # --- Simulate trades -----------------------------------------------------
    trades: List[BacktestTrade] = []
    equity = 100_000.0  # starting capital
    equity_curve: List[Dict[str, Any]] = []
    peak_equity = equity
    current_spot = spot

    rng = random.Random(42)  # deterministic for reproducibility

    for i in range(num_trades):
        entry_dt = dt_start + timedelta(days=i * interval)
        if entry_dt > dt_end:
            break

        tte = hold_days / 365.0

        # --- Calculate entry premium for each leg ---
        entry_premiums: List[float] = []
        for leg in legs_config:
            strike = current_spot + leg.get("strike_offset", 0.0)
            is_call = leg["option_type"].upper() == "CE"
            qty = leg.get("quantity", 1)
            result = black_scholes(current_spot, strike, tte, iv, rate, is_call)
            sign = 1 if leg["action"].upper() == "BUY" else -1
            entry_premiums.append(result.price * sign * qty)

        net_entry = sum(entry_premiums)

        # --- Simulate spot movement (GBM) ---
        dt_step = hold_days / 365.0
        drift = (annual_drift - 0.5 * annual_vol ** 2) * dt_step
        diffusion = annual_vol * math.sqrt(dt_step) * rng.gauss(0, 1)
        spot_exit = current_spot * math.exp(drift + diffusion)

        # --- Calculate exit premium ---
        exit_premiums: List[float] = []
        remaining_tte = max(tte * 0.1, 1 / 365.0)  # small residual time
        for leg in legs_config:
            strike = current_spot + leg.get("strike_offset", 0.0)
            is_call = leg["option_type"].upper() == "CE"
            qty = leg.get("quantity", 1)
            result = black_scholes(spot_exit, strike, remaining_tte, iv, rate, is_call)
            sign = 1 if leg["action"].upper() == "BUY" else -1
            exit_premiums.append(result.price * sign * qty)

        net_exit = sum(exit_premiums)

        # P&L = exit value - entry cost (for debit trades: buy entry is negative)
        raw_pnl = net_exit - net_entry

        # Apply stop-loss / profit-target
        exit_reason = "expiry"
        if net_entry < 0:  # net debit (bought strategy)
            max_loss = abs(net_entry)
            if raw_pnl < -max_loss * stop_loss_mult:
                raw_pnl = -max_loss * stop_loss_mult
                exit_reason = "stop_loss"
            elif raw_pnl > max_loss * profit_target_pct:
                raw_pnl = max_loss * profit_target_pct
                exit_reason = "profit_target"
        else:  # net credit (sold strategy)
            max_premium = abs(net_entry)
            if raw_pnl < -max_premium * stop_loss_mult:
                raw_pnl = -max_premium * stop_loss_mult
                exit_reason = "stop_loss"
            elif raw_pnl > max_premium * profit_target_pct:
                raw_pnl = max_premium * profit_target_pct
                exit_reason = "profit_target"

        pnl_pct = (raw_pnl / abs(net_entry) * 100) if net_entry != 0 else 0

        exit_dt = entry_dt + timedelta(days=hold_days)

        trade = BacktestTrade(
            trade_id=i + 1,
            strategy_id=strategy_id,
            entry_date=entry_dt.isoformat(),
            exit_date=exit_dt.isoformat(),
            entry_price=round(net_entry, 2),
            exit_price=round(net_exit, 2),
            pnl=round(raw_pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            exit_reason=exit_reason,
            legs=[{
                "option_type": leg["option_type"],
                "action": leg["action"],
                "strike_offset": leg.get("strike_offset", 0),
                "quantity": leg.get("quantity", 1),
            } for leg in legs_config],
        )
        trades.append(trade)

        equity += raw_pnl
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0

        equity_curve.append({
            "date": entry_dt.isoformat(),
            "equity": round(equity, 2),
            "drawdown": round(drawdown * 100, 2),
        })

        # Drift spot for next trade
        current_spot = spot_exit

    # --- Compute summary stats -----------------------------------------------
    pnls = [t.pnl for t in trades]
    winning = [p for p in pnls if p > 0]
    losing = [p for p in pnls if p <= 0]

    total_pnl = sum(pnls)
    avg_pnl = total_pnl / len(pnls) if pnls else 0
    std_pnl = _std(pnls)
    sharpe = (avg_pnl / std_pnl * math.sqrt(252 / max(hold_days, 1))) if std_pnl > 0 else 0

    gross_profit = sum(winning)
    gross_loss = abs(sum(losing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    max_dd = max((ec["drawdown"] for ec in equity_curve), default=0)

    # Monthly P&L
    monthly: Dict[str, float] = {}
    for t in trades:
        month = t.entry_date[:7]
        monthly[month] = monthly.get(month, 0) + t.pnl
    monthly_pnl = [{"month": m, "pnl": round(v, 2)} for m, v in sorted(monthly.items())]

    return BacktestResult(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        total_trades=len(trades),
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=round(len(winning) / len(trades) * 100, 1) if trades else 0,
        total_pnl=round(total_pnl, 2),
        avg_pnl=round(avg_pnl, 2),
        max_pnl=round(max(pnls, default=0), 2),
        min_pnl=round(min(pnls, default=0), 2),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown=round(max_dd, 2),
        profit_factor=round(profit_factor, 3),
        equity_curve=equity_curve,
        monthly_pnl=monthly_pnl,
        trades=trades,
        parameters={
            "spot": spot,
            "iv": iv,
            "rate": rate,
            "hold_days": hold_days,
            "stop_loss_mult": stop_loss_mult,
            "profit_target_pct": profit_target_pct,
            "num_trades": num_trades,
        },
    )


def _std(values: List[float]) -> float:
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)
