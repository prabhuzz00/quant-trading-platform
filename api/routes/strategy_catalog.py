"""Strategy catalog API — browse, search, build, and compute Greeks for 77 strategies."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from strategies.catalog import (
    Category,
    get_all_strategies,
    get_categories,
    get_strategies_by_category,
    get_strategy_by_id,
    search_strategies,
)
from engine.greeks import (
    black_scholes,
    compute_strategy_greeks,
    implied_volatility,
)

router = APIRouter(prefix="/strategies", tags=["strategy-catalog"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class LegResponse(BaseModel):
    action: str
    option_type: str
    strike_ref: str
    strike_offset: float
    quantity_ratio: int
    expiry: str
    description: str


class StrategyDefResponse(BaseModel):
    id: str
    name: str
    category: str
    legs: List[LegResponse]
    description: str
    best_when: str
    max_profit: str
    max_loss: str
    breakeven: str
    greeks_profile: str
    risk_level: str
    tags: List[str]


class CategorySummary(BaseModel):
    category: str
    count: int
    strategies: List[StrategyDefResponse]


class GreeksRequest(BaseModel):
    spot: float = Field(..., gt=0, description="Current underlying spot price")
    strikes: List[float] = Field(..., description="Strike price for each leg")
    option_types: List[str] = Field(..., description="'CE' or 'PE' for each leg")
    actions: List[str] = Field(..., description="'BUY' or 'SELL' for each leg")
    quantities: List[int] = Field(..., description="Quantity for each leg")
    tte: float = Field(..., gt=0, description="Time to expiry in years")
    iv: float = Field(..., gt=0, description="Implied volatility (decimal, e.g. 0.15)")
    rate: float = Field(0.07, description="Risk-free interest rate")
    descriptions: Optional[List[str]] = None


class LegGreeksResponse(BaseModel):
    description: str
    action: str
    option_type: str
    strike: float
    quantity: int
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


class StrategyGreeksResponse(BaseModel):
    net_price: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    net_rho: float
    legs: List[LegGreeksResponse]


class SingleGreeksRequest(BaseModel):
    spot: float = Field(..., gt=0)
    strike: float = Field(..., gt=0)
    tte: float = Field(..., gt=0, description="Time to expiry in years")
    iv: float = Field(..., gt=0, description="Implied volatility (decimal)")
    rate: float = Field(0.07)
    is_call: bool = True


class SingleGreeksResponse(BaseModel):
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    iv: Optional[float] = None


class IVRequest(BaseModel):
    market_price: float = Field(..., gt=0)
    spot: float = Field(..., gt=0)
    strike: float = Field(..., gt=0)
    tte: float = Field(..., gt=0)
    rate: float = Field(0.07)
    is_call: bool = True


class IVResponse(BaseModel):
    implied_volatility: float
    iv_pct: float  # as percentage


class BuildRequest(BaseModel):
    strategy_id: str
    spot: float = Field(..., gt=0)
    tte: float = Field(7 / 365, gt=0, description="Time to expiry in years")
    iv: float = Field(0.15, gt=0)
    rate: float = Field(0.07)
    lot_size: int = Field(50, gt=0, description="Lot size multiplier")


class BuildLegResponse(BaseModel):
    action: str
    option_type: str
    strike: float
    quantity: int
    premium: float
    delta: float
    gamma: float
    theta: float
    vega: float


class BuildResponse(BaseModel):
    strategy_id: str
    strategy_name: str
    spot: float
    legs: List[BuildLegResponse]
    net_premium: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    max_profit: str
    max_loss: str


# ---------------------------------------------------------------------------
# Helper — convert catalog StrategyDef to API response
# ---------------------------------------------------------------------------

def _to_response(s) -> StrategyDefResponse:
    return StrategyDefResponse(
        id=s.id,
        name=s.name,
        category=s.category.value,
        legs=[
            LegResponse(
                action=leg.action.value,
                option_type=leg.option_type.value,
                strike_ref=leg.strike_ref.value,
                strike_offset=leg.strike_offset,
                quantity_ratio=leg.quantity_ratio,
                expiry=leg.expiry,
                description=leg.description,
            )
            for leg in s.legs
        ],
        description=s.description,
        best_when=s.best_when,
        max_profit=s.max_profit,
        max_loss=s.max_loss,
        breakeven=s.breakeven,
        greeks_profile=s.greeks_profile,
        risk_level=s.risk_level,
        tags=s.tags,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/list", response_model=List[StrategyDefResponse])
async def list_all_strategies():
    """Return the full catalog of 77 strategies with metadata."""
    return [_to_response(s) for s in get_all_strategies()]


@router.get("/categories", response_model=List[CategorySummary])
async def list_categories():
    """Return strategies grouped by category."""
    groups = get_categories()
    return [
        CategorySummary(
            category=cat,
            count=len(strats),
            strategies=[_to_response(s) for s in strats],
        )
        for cat, strats in groups.items()
    ]


@router.get("/search", response_model=List[StrategyDefResponse])
async def search(q: str = Query(..., min_length=1, description="Search query")):
    """Search strategies by name, description, or tags."""
    results = search_strategies(q)
    if not results:
        return []
    return [_to_response(s) for s in results]


@router.get("/detail/{strategy_id}", response_model=StrategyDefResponse)
async def get_strategy_detail(strategy_id: str):
    """Get detailed information for a single strategy."""
    s = get_strategy_by_id(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
    return _to_response(s)


@router.post("/build", response_model=BuildResponse)
async def build_strategy(req: BuildRequest):
    """Build concrete strategy legs with calculated premiums and Greeks."""
    s = get_strategy_by_id(req.strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Strategy '{req.strategy_id}' not found")

    built_legs: List[BuildLegResponse] = []
    net_premium = 0.0
    net_delta = 0.0
    net_gamma = 0.0
    net_theta = 0.0
    net_vega = 0.0

    for leg in s.legs:
        strike = req.spot + leg.strike_offset
        is_call = leg.option_type.value == "CE"
        qty = leg.quantity_ratio * req.lot_size
        result = black_scholes(req.spot, strike, req.tte, req.iv, req.rate, is_call)
        sign = 1 if leg.action.value == "BUY" else -1

        built_legs.append(BuildLegResponse(
            action=leg.action.value,
            option_type=leg.option_type.value,
            strike=strike,
            quantity=qty,
            premium=round(result.price, 2),
            delta=round(result.delta * sign * qty, 4),
            gamma=round(result.gamma * sign * qty, 6),
            theta=round(result.theta * sign * qty, 4),
            vega=round(result.vega * sign * qty, 4),
        ))

        net_premium += result.price * sign * qty
        net_delta += result.delta * sign * qty
        net_gamma += result.gamma * sign * qty
        net_theta += result.theta * sign * qty
        net_vega += result.vega * sign * qty

    return BuildResponse(
        strategy_id=s.id,
        strategy_name=s.name,
        spot=req.spot,
        legs=built_legs,
        net_premium=round(net_premium, 2),
        net_delta=round(net_delta, 4),
        net_gamma=round(net_gamma, 6),
        net_theta=round(net_theta, 4),
        net_vega=round(net_vega, 4),
        max_profit=s.max_profit,
        max_loss=s.max_loss,
    )


@router.post("/greeks", response_model=StrategyGreeksResponse)
async def calculate_strategy_greeks(req: GreeksRequest):
    """Calculate aggregated Greeks for a custom multi-leg strategy."""
    result = compute_strategy_greeks(
        spot=req.spot,
        strikes=req.strikes,
        option_types=req.option_types,
        actions=req.actions,
        quantities=req.quantities,
        tte=req.tte,
        iv=req.iv,
        rate=req.rate,
        descriptions=req.descriptions,
    )
    return StrategyGreeksResponse(
        net_price=result.net_price,
        net_delta=result.net_delta,
        net_gamma=result.net_gamma,
        net_theta=result.net_theta,
        net_vega=result.net_vega,
        net_rho=result.net_rho,
        legs=[
            LegGreeksResponse(
                description=lg.description,
                action=lg.action,
                option_type=lg.option_type,
                strike=lg.strike,
                quantity=lg.quantity,
                price=lg.price,
                delta=lg.delta,
                gamma=lg.gamma,
                theta=lg.theta,
                vega=lg.vega,
                rho=lg.rho,
            )
            for lg in result.legs
        ],
    )


@router.post("/option-price", response_model=SingleGreeksResponse)
async def calculate_option_price(req: SingleGreeksRequest):
    """Calculate Black-Scholes price and Greeks for a single option."""
    result = black_scholes(req.spot, req.strike, req.tte, req.iv, req.rate, req.is_call)
    return SingleGreeksResponse(
        price=result.price,
        delta=result.delta,
        gamma=result.gamma,
        theta=result.theta,
        vega=result.vega,
        rho=result.rho,
        iv=result.iv,
    )


@router.post("/implied-volatility", response_model=IVResponse)
async def calculate_iv(req: IVRequest):
    """Solve for implied volatility given a market price."""
    iv = implied_volatility(
        market_price=req.market_price,
        spot=req.spot,
        strike=req.strike,
        tte=req.tte,
        rate=req.rate,
        is_call=req.is_call,
    )
    return IVResponse(
        implied_volatility=iv,
        iv_pct=round(iv * 100, 2),
    )
