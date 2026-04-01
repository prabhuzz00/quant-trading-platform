"""Regime detection and auto-toggle API routes."""
from typing import Optional

from fastapi import APIRouter, Depends

from api.dependencies import get_regime_engine
from api.schemas import (
    RegimeConfigResponse,
    RegimeConfigUpdateRequest,
    RegimeStatusResponse,
    StrategyScoreItem,
)

router = APIRouter(prefix="/regime", tags=["regime"])


def _build_status(engine) -> RegimeStatusResponse:
    """Convert the engine's last result into a response model."""
    result = engine.last_result
    if result is None:
        return RegimeStatusResponse(
            regime_type="UNKNOWN",
            trend="neutral",
            volatility="medium",
            volume="normal",
            candle_count=0,
            description="Regime analysis has not run yet. Trigger via POST /api/regime/analyze.",
            auto_regime_enabled=engine.enabled,
            score_threshold=engine.score_threshold,
            interval_minutes=engine.interval_minutes,
        )

    regime = result.regime
    scores = [
        StrategyScoreItem(
            strategy_name=s.strategy_name,
            score=s.score,
            regime=s.regime,
            recommended=s.recommended,
            reason=s.reason,
        )
        for s in result.scores
    ]
    return RegimeStatusResponse(
        regime_type=regime.regime_type.value,
        trend=regime.trend,
        volatility=regime.volatility,
        volume=regime.volume,
        atr_pct=regime.atr_pct,
        volume_ratio=regime.volume_ratio,
        ema_fast=regime.ema_fast,
        ema_slow=regime.ema_slow,
        candle_count=regime.candle_count,
        description=regime.description,
        scores=scores,
        enabled_by_regime=result.enabled_by_regime,
        disabled_by_regime=result.disabled_by_regime,
        analyzed_at=result.analyzed_at,
        error=result.error,
        auto_regime_enabled=engine.enabled,
        score_threshold=engine.score_threshold,
        interval_minutes=engine.interval_minutes,
    )


@router.get("/status", response_model=RegimeStatusResponse)
async def get_regime_status(engine=Depends(get_regime_engine)):
    """Return the last regime analysis result and current strategy scores."""
    return _build_status(engine)


@router.post("/analyze", response_model=RegimeStatusResponse)
async def run_regime_analysis(engine=Depends(get_regime_engine)):
    """Trigger an immediate regime analysis and return results."""
    await engine.analyze_and_apply()
    return _build_status(engine)


@router.get("/config", response_model=RegimeConfigResponse)
async def get_regime_config(engine=Depends(get_regime_engine)):
    """Return the current auto-regime engine configuration."""
    return RegimeConfigResponse(
        enabled=engine.enabled,
        score_threshold=engine.score_threshold,
        interval_minutes=engine.interval_minutes,
        instrument_id=engine.instrument_id,
        timeframe=engine.timeframe,
    )


@router.put("/config", response_model=RegimeConfigResponse)
async def update_regime_config(
    body: RegimeConfigUpdateRequest,
    engine=Depends(get_regime_engine),
):
    """Update the auto-regime engine configuration."""
    if body.enabled is not None:
        engine.enabled = body.enabled
    if body.score_threshold is not None:
        engine.score_threshold = max(1, min(100, body.score_threshold))
    if body.interval_minutes is not None:
        engine.interval_minutes = max(1, body.interval_minutes)
    if body.instrument_id is not None:
        engine.instrument_id = body.instrument_id
    if body.timeframe is not None:
        engine.timeframe = body.timeframe

    return RegimeConfigResponse(
        enabled=engine.enabled,
        score_threshold=engine.score_threshold,
        interval_minutes=engine.interval_minutes,
        instrument_id=engine.instrument_id,
        timeframe=engine.timeframe,
    )
