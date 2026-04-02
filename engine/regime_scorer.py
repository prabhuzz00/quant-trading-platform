"""
Strategy scorer — maps a :class:`~engine.regime_detector.MarketRegime` to a
0-100 fitness score for each registered strategy.

Score ≥ 80  → strategy is well-suited for the current market regime.
Score < 80  → strategy is sub-optimal or likely to underperform.

The score matrix is intentionally rule-based so that it works without any
external ML dependencies.  Each cell reflects the expected edge of the
strategy in that market environment:

  TRENDING_BULLISH  – trending market with bullish bias
  TRENDING_BEARISH  – trending market with bearish bias
  SIDEWAYS_LOW_VOL  – range-bound, low intraday movement
  SIDEWAYS_HIGH_VOL – choppy / elevated intraday swings
  HIGH_VOLATILITY   – extreme volatility (pre/post event spike)
  UNKNOWN           – insufficient data; neutral scores

Rationale for each strategy:
  * smc_confluence    – structural trades; works best during trends.
  * volume_breakout   – breakout trades; need momentum / high volume.
  * iron_condor       – net credit spread; profits from low-vol sideways.
  * short_straddle    – ATM credit; best in low-vol, range-bound markets.
  * short_strangle    – OTM credit; similar to straddle but wider range.
  * bull_call_spread  – debit spread; directional bullish.
  * bear_put_spread   – debit spread; directional bearish.
  * long_straddle     – long vol; thrives in high volatility.
  * butterfly_spread  – neutral debit; profits from low-vol, pin-risk.
  * calendar_spread   – time-decay play; favours low-vol, stable markets.
  * covered_call      – income overlay; works in mild uptrend or sideways.
  * protective_put    – insurance; suited for bearish / high-vol regimes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from engine.regime_detector import MarketRegime, RegimeType

# ---------------------------------------------------------------------------
# Score matrix  (strategy_name → {regime → score})
# ---------------------------------------------------------------------------

_SCORE_MATRIX: Dict[str, Dict[RegimeType, int]] = {
    "smc_confluence": {
        RegimeType.TRENDING_BULLISH:  90,
        RegimeType.TRENDING_BEARISH:  88,
        RegimeType.SIDEWAYS_HIGH_VOL: 48,
        RegimeType.SIDEWAYS_LOW_VOL:  30,
        RegimeType.HIGH_VOLATILITY:   55,
        RegimeType.UNKNOWN:           50,
    },
    "volume_breakout": {
        RegimeType.TRENDING_BULLISH:  88,
        RegimeType.TRENDING_BEARISH:  84,
        RegimeType.SIDEWAYS_HIGH_VOL: 55,
        RegimeType.SIDEWAYS_LOW_VOL:  25,
        RegimeType.HIGH_VOLATILITY:   68,
        RegimeType.UNKNOWN:           50,
    },
    "iron_condor": {
        RegimeType.TRENDING_BULLISH:  28,
        RegimeType.TRENDING_BEARISH:  28,
        RegimeType.SIDEWAYS_HIGH_VOL: 50,
        RegimeType.SIDEWAYS_LOW_VOL:  92,
        RegimeType.HIGH_VOLATILITY:   15,
        RegimeType.UNKNOWN:           50,
    },
    "short_straddle": {
        RegimeType.TRENDING_BULLISH:  20,
        RegimeType.TRENDING_BEARISH:  20,
        RegimeType.SIDEWAYS_HIGH_VOL: 42,
        RegimeType.SIDEWAYS_LOW_VOL:  90,
        RegimeType.HIGH_VOLATILITY:   10,
        RegimeType.UNKNOWN:           50,
    },
    "short_strangle": {
        RegimeType.TRENDING_BULLISH:  25,
        RegimeType.TRENDING_BEARISH:  25,
        RegimeType.SIDEWAYS_HIGH_VOL: 46,
        RegimeType.SIDEWAYS_LOW_VOL:  88,
        RegimeType.HIGH_VOLATILITY:   12,
        RegimeType.UNKNOWN:           50,
    },
    "bull_call_spread": {
        RegimeType.TRENDING_BULLISH:  88,
        RegimeType.TRENDING_BEARISH:  15,
        RegimeType.SIDEWAYS_HIGH_VOL: 40,
        RegimeType.SIDEWAYS_LOW_VOL:  35,
        RegimeType.HIGH_VOLATILITY:   50,
        RegimeType.UNKNOWN:           50,
    },
    "bear_put_spread": {
        RegimeType.TRENDING_BULLISH:  15,
        RegimeType.TRENDING_BEARISH:  88,
        RegimeType.SIDEWAYS_HIGH_VOL: 40,
        RegimeType.SIDEWAYS_LOW_VOL:  35,
        RegimeType.HIGH_VOLATILITY:   50,
        RegimeType.UNKNOWN:           50,
    },
    "long_straddle": {
        RegimeType.TRENDING_BULLISH:  30,
        RegimeType.TRENDING_BEARISH:  30,
        RegimeType.SIDEWAYS_HIGH_VOL: 85,
        RegimeType.SIDEWAYS_LOW_VOL:  18,
        RegimeType.HIGH_VOLATILITY:   92,
        RegimeType.UNKNOWN:           50,
    },
    "butterfly_spread": {
        RegimeType.TRENDING_BULLISH:  25,
        RegimeType.TRENDING_BEARISH:  25,
        RegimeType.SIDEWAYS_HIGH_VOL: 42,
        RegimeType.SIDEWAYS_LOW_VOL:  86,
        RegimeType.HIGH_VOLATILITY:   15,
        RegimeType.UNKNOWN:           50,
    },
    "calendar_spread": {
        RegimeType.TRENDING_BULLISH:  38,
        RegimeType.TRENDING_BEARISH:  38,
        RegimeType.SIDEWAYS_HIGH_VOL: 52,
        RegimeType.SIDEWAYS_LOW_VOL:  88,
        RegimeType.HIGH_VOLATILITY:   25,
        RegimeType.UNKNOWN:           50,
    },
    "covered_call": {
        RegimeType.TRENDING_BULLISH:  82,
        RegimeType.TRENDING_BEARISH:  15,
        RegimeType.SIDEWAYS_HIGH_VOL: 40,
        RegimeType.SIDEWAYS_LOW_VOL:  72,
        RegimeType.HIGH_VOLATILITY:   28,
        RegimeType.UNKNOWN:           50,
    },
    "protective_put": {
        RegimeType.TRENDING_BULLISH:  18,
        RegimeType.TRENDING_BEARISH:  85,
        RegimeType.SIDEWAYS_HIGH_VOL: 60,
        RegimeType.SIDEWAYS_LOW_VOL:  38,
        RegimeType.HIGH_VOLATILITY:   70,
        RegimeType.UNKNOWN:           50,
    },
    # Regime-aware indicator strategy – adapts its indicator set to the
    # detected market regime, so it scores well across all regimes.
    "indicator_regime": {
        RegimeType.TRENDING_BULLISH:  88,
        RegimeType.TRENDING_BEARISH:  88,
        RegimeType.SIDEWAYS_HIGH_VOL: 82,
        RegimeType.SIDEWAYS_LOW_VOL:  84,
        RegimeType.HIGH_VOLATILITY:   80,
        RegimeType.UNKNOWN:           50,
    },
}

# Default score when a strategy name is not in the matrix
_DEFAULT_SCORE = 50


@dataclass
class StrategyScore:
    """Fitness score for a single strategy."""

    strategy_name: str
    score: int                    # 0-100
    regime: str                   # regime type string
    recommended: bool             # True if score >= threshold
    reason: str = ""


class RegimeScorer:
    """
    Scores each strategy against the detected market regime.

    Parameters
    ----------
    threshold:
        Minimum score for a strategy to be considered "recommended"
        (default 80).
    """

    def __init__(self, threshold: int = 80) -> None:
        self.threshold = threshold

    def score_strategies(
        self,
        regime: MarketRegime,
        strategy_names: List[str],
    ) -> List[StrategyScore]:
        """
        Return a :class:`StrategyScore` for each name in *strategy_names*.

        Parameters
        ----------
        regime:
            The current market regime from :class:`~engine.regime_detector.RegimeDetector`.
        strategy_names:
            Names of all registered strategies.
        """
        results: List[StrategyScore] = []
        for name in strategy_names:
            regime_scores = _SCORE_MATRIX.get(name, {})
            score = regime_scores.get(regime.regime_type, _DEFAULT_SCORE)
            recommended = score >= self.threshold
            reason = (
                f"Score {score}/100 for {regime.regime_type.value} regime "
                f"(trend={regime.trend}, vol={regime.volatility})"
            )
            results.append(
                StrategyScore(
                    strategy_name=name,
                    score=score,
                    regime=regime.regime_type.value,
                    recommended=recommended,
                    reason=reason,
                )
            )
        return results
