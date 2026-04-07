"""Payoff diagram API routes."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from strategies.catalog import get_strategy_by_id
from engine.payoff import compute_payoff
from engine.greeks import black_scholes

router = APIRouter(prefix="/payoff", tags=["payoff"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class PayoffLeg(BaseModel):
    option_type: str = Field(..., description="'CE' or 'PE'")
    action: str = Field(..., description="'BUY' or 'SELL'")
    strike: float = Field(..., gt=0, description="Absolute strike price")
    quantity: int = Field(1, gt=0)
    premium: Optional[float] = Field(None, description="Entry premium (auto-calculated if omitted)")


class PayoffRequest(BaseModel):
    strategy_id: Optional[str] = Field(None, description="Build from catalog (overrides legs)")
    spot: float = Field(..., gt=0)
    legs: Optional[List[PayoffLeg]] = Field(None, description="Custom legs (ignored if strategy_id)")
    iv: float = Field(0.15, gt=0)
    rate: float = Field(0.07)
    dte_values: Optional[List[int]] = Field(None, description="Days to expiry for curves")
    spot_range_pct: float = Field(10.0, gt=0, le=50.0)
    lot_size: int = Field(1, gt=0, description="Lot multiplier for catalog strategy")


class PayoffPointResponse(BaseModel):
    spot: float
    pnl: float


class PayoffCurveResponse(BaseModel):
    label: str
    dte: int
    points: List[PayoffPointResponse]


class PayoffResponse(BaseModel):
    strategy_id: str
    strategy_name: str
    current_spot: float
    net_premium: float
    max_profit: Optional[float]
    max_loss: Optional[float]
    breakevens: List[float]
    curves: List[PayoffCurveResponse]
    legs_detail: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=PayoffResponse)
async def calculate_payoff(req: PayoffRequest):
    """Generate payoff diagram data for a strategy or custom legs."""
    strategy_id = req.strategy_id or "custom"
    strategy_name = "Custom Strategy"

    if req.strategy_id:
        s = get_strategy_by_id(req.strategy_id)
        if not s:
            raise HTTPException(status_code=404, detail=f"Strategy '{req.strategy_id}' not found")
        strategy_name = s.name

        # Build legs from catalog
        max_dte = max(req.dte_values) if req.dte_values else 30
        tte = max_dte / 365.0
        legs_dicts: List[Dict[str, Any]] = []
        for leg in s.legs:
            strike = req.spot + leg.strike_offset
            is_call = leg.option_type.value == "CE"
            premium = black_scholes(req.spot, strike, tte, req.iv, req.rate, is_call).price
            legs_dicts.append({
                "option_type": leg.option_type.value,
                "action": leg.action.value,
                "strike": strike,
                "quantity": leg.quantity_ratio * req.lot_size,
                "premium": premium,
            })
    elif req.legs:
        legs_dicts = [
            {
                "option_type": lg.option_type,
                "action": lg.action,
                "strike": lg.strike,
                "quantity": lg.quantity,
                "premium": lg.premium,
            }
            for lg in req.legs
        ]
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either strategy_id or legs",
        )

    result = compute_payoff(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        spot=req.spot,
        legs=legs_dicts,
        iv=req.iv,
        rate=req.rate,
        dte_values=req.dte_values,
        spot_range_pct=req.spot_range_pct,
    )

    return PayoffResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        current_spot=result.current_spot,
        net_premium=result.net_premium,
        max_profit=result.max_profit,
        max_loss=result.max_loss,
        breakevens=result.breakevens,
        curves=[
            PayoffCurveResponse(
                label=c.label,
                dte=c.dte,
                points=[PayoffPointResponse(spot=p.spot, pnl=p.pnl) for p in c.points],
            )
            for c in result.curves
        ],
        legs_detail=result.legs_detail,
    )
