"""Comprehensive strategy catalog — 77 options strategies across 13 categories.

Each strategy is defined as metadata (name, category, legs, description,
optimal conditions, max profit/loss characteristics).  This catalog powers the
strategy browser UI, the builder API, and the backtesting engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class LegAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class StrikeRef(str, Enum):
    ATM = "ATM"
    OTM = "OTM"
    ITM = "ITM"
    CUSTOM = "CUSTOM"


class Category(str, Enum):
    DIRECTIONAL = "Directional"
    VERTICAL_SPREAD = "Vertical Spreads"
    SYNTHETIC = "Synthetic"
    THETA = "Theta / Premium Selling"
    GAMMA = "Gamma / Volatility Buying"
    BUTTERFLY = "Butterflies"
    CONDOR = "Condors"
    LADDER = "Ladders"
    RATIO = "Ratio / Asymmetric"
    CALENDAR = "Calendar / Diagonal"
    HEDGING = "Hedging / Protective"
    ARBITRAGE = "Arbitrage & Exotic"
    VOLATILITY = "Volatility Strategies"
    SIGNAL = "Signal-Based"


# ---------------------------------------------------------------------------
# Leg definition
# ---------------------------------------------------------------------------

@dataclass
class LegDef:
    """A single option leg within a strategy."""
    action: LegAction
    option_type: OptionType
    strike_ref: StrikeRef
    strike_offset: float = 0.0  # points from ATM (positive = OTM direction)
    quantity_ratio: int = 1     # relative quantity multiplier
    expiry: str = "near"        # "near" or "far" for calendar strategies
    description: str = ""


# ---------------------------------------------------------------------------
# Strategy definition
# ---------------------------------------------------------------------------

@dataclass
class StrategyDef:
    """Complete metadata for a single options strategy."""
    id: str
    name: str
    category: Category
    legs: List[LegDef]
    description: str = ""
    best_when: str = ""
    max_profit: str = ""
    max_loss: str = ""
    breakeven: str = ""
    greeks_profile: str = ""  # e.g. "Positive Theta, Negative Gamma"
    risk_level: str = "Medium"  # Low, Medium, High
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Full catalog — 77 strategies
# ---------------------------------------------------------------------------

STRATEGY_CATALOG: List[StrategyDef] = [
    # ==================== 1. DIRECTIONAL (3) ====================
    StrategyDef(
        id="directional_ce_sell",
        name="Directional CE Sell",
        category=Category.DIRECTIONAL,
        legs=[LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short ATM CE")],
        description="Sell ATM call for bearish or range-bound view.",
        best_when="Bearish or sideways market",
        max_profit="Premium received",
        max_loss="Unlimited",
        greeks_profile="Positive Theta, Negative Delta",
        risk_level="High",
        tags=["bearish", "premium-selling"],
    ),
    StrategyDef(
        id="directional_pe_sell",
        name="Directional PE Sell",
        category=Category.DIRECTIONAL,
        legs=[LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short ATM PE")],
        description="Sell ATM put for bullish or range-bound view.",
        best_when="Bullish or sideways market",
        max_profit="Premium received",
        max_loss="Substantial (strike - premium)",
        greeks_profile="Positive Theta, Positive Delta",
        risk_level="High",
        tags=["bullish", "premium-selling"],
    ),
    StrategyDef(
        id="cash_secured_put",
        name="Cash Secured Put",
        category=Category.DIRECTIONAL,
        legs=[LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short OTM PE")],
        description="Sell OTM put with cash reserved to buy at strike price.",
        best_when="Bullish, willing to buy underlying at strike",
        max_profit="Premium received",
        max_loss="Strike - Premium",
        greeks_profile="Positive Theta, Positive Delta",
        risk_level="Medium",
        tags=["bullish", "income"],
    ),

    # ==================== 2. VERTICAL SPREADS (6) ====================
    StrategyDef(
        id="bull_call_spread",
        name="Bull Call Spread",
        category=Category.VERTICAL_SPREAD,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long lower CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short higher CE"),
        ],
        description="Buy lower call, sell higher call. Defined risk bullish play.",
        best_when="Moderately bullish",
        max_profit="Width - Net Debit",
        max_loss="Net Debit",
        greeks_profile="Positive Delta, variable Theta",
        risk_level="Low",
        tags=["bullish", "defined-risk"],
    ),
    StrategyDef(
        id="bull_put_spread",
        name="Bull Put Spread",
        category=Category.VERTICAL_SPREAD,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short higher PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long lower PE"),
        ],
        description="Sell higher put, buy lower put. Credit spread for bullish view.",
        best_when="Moderately bullish",
        max_profit="Net Credit",
        max_loss="Width - Credit",
        greeks_profile="Positive Delta, Positive Theta",
        risk_level="Low",
        tags=["bullish", "credit", "defined-risk"],
    ),
    StrategyDef(
        id="bear_call_spread",
        name="Bear Call Spread",
        category=Category.VERTICAL_SPREAD,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short lower CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long higher CE"),
        ],
        description="Sell lower call, buy higher call. Credit spread for bearish view.",
        best_when="Moderately bearish",
        max_profit="Net Credit",
        max_loss="Width - Credit",
        greeks_profile="Negative Delta, Positive Theta",
        risk_level="Low",
        tags=["bearish", "credit", "defined-risk"],
    ),
    StrategyDef(
        id="bear_put_spread",
        name="Bear Put Spread",
        category=Category.VERTICAL_SPREAD,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long higher PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short lower PE"),
        ],
        description="Buy higher put, sell lower put. Defined risk bearish play.",
        best_when="Moderately bearish",
        max_profit="Width - Net Debit",
        max_loss="Net Debit",
        greeks_profile="Negative Delta, variable Theta",
        risk_level="Low",
        tags=["bearish", "defined-risk"],
    ),
    StrategyDef(
        id="bullish_seagull",
        name="Bullish Seagull",
        category=Category.VERTICAL_SPREAD,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Short OTM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-200, description="Short OTM PE"),
        ],
        description="Long CE + Short CE + Short PE. Funded bullish play.",
        best_when="Moderately bullish, fund with PE premium",
        max_profit="Mid - PE strike",
        max_loss="Lower strike risk",
        greeks_profile="Positive Delta",
        risk_level="Medium",
        tags=["bullish", "funded"],
    ),
    StrategyDef(
        id="bearish_seagull",
        name="Bearish Seagull",
        category=Category.VERTICAL_SPREAD,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-200, description="Short OTM PE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Short OTM CE"),
        ],
        description="Long PE + Short PE + Short CE. Funded bearish play.",
        best_when="Moderately bearish, fund with CE premium",
        max_profit="Higher - Mid",
        max_loss="Unlimited on CE side",
        greeks_profile="Negative Delta",
        risk_level="Medium",
        tags=["bearish", "funded"],
    ),

    # ==================== 3. SYNTHETIC (4) ====================
    StrategyDef(
        id="long_synthetic_forward",
        name="Long Synthetic Forward",
        category=Category.SYNTHETIC,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short ATM PE"),
        ],
        description="Replicates a long futures position using options.",
        best_when="Bullish; need futures-like exposure via options",
        max_profit="Unlimited",
        max_loss="Substantial",
        greeks_profile="Delta ≈ +1.0",
        risk_level="High",
        tags=["bullish", "synthetic"],
    ),
    StrategyDef(
        id="short_synthetic_forward",
        name="Short Synthetic Forward",
        category=Category.SYNTHETIC,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
        ],
        description="Replicates a short futures position using options.",
        best_when="Bearish; need short exposure via options",
        max_profit="Substantial",
        max_loss="Unlimited",
        greeks_profile="Delta ≈ -1.0",
        risk_level="High",
        tags=["bearish", "synthetic"],
    ),
    StrategyDef(
        id="long_combo",
        name="Long Combo",
        category=Category.SYNTHETIC,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long OTM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short OTM PE"),
        ],
        description="Cheaper synthetic long using OTM options.",
        best_when="Bullish with lower capital",
        max_profit="Unlimited",
        max_loss="Substantial",
        greeks_profile="Positive Delta",
        risk_level="High",
        tags=["bullish", "synthetic"],
    ),
    StrategyDef(
        id="short_combo",
        name="Short Combo",
        category=Category.SYNTHETIC,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long OTM PE"),
        ],
        description="Cheaper synthetic short using OTM options.",
        best_when="Bearish with lower capital",
        max_profit="Substantial",
        max_loss="Unlimited",
        greeks_profile="Negative Delta",
        risk_level="High",
        tags=["bearish", "synthetic"],
    ),

    # ==================== 4. THETA / PREMIUM SELLING (10) ====================
    StrategyDef(
        id="iron_condor",
        name="Iron Condor",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Long further OTM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short OTM PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-200, description="Long further OTM PE"),
        ],
        description="Short OTM call spread + put spread. Champion strategy with ~80% win rate.",
        best_when="Range-bound, low volatility",
        max_profit="Net premium received",
        max_loss="Width - Net premium",
        greeks_profile="Positive Theta, Negative Gamma",
        risk_level="Low",
        tags=["range-bound", "premium-selling", "champion"],
    ),
    StrategyDef(
        id="iron_butterfly",
        name="Iron Butterfly",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short ATM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short ATM PE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long OTM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long OTM PE"),
        ],
        description="Short ATM straddle + Long OTM wings. Max profit if price pins at ATM.",
        best_when="Range-bound, expect pin at ATM",
        max_profit="Net premium - wing cost",
        max_loss="Width - Net premium",
        greeks_profile="High Theta, Negative Gamma",
        risk_level="Low",
        tags=["range-bound", "premium-selling"],
    ),
    StrategyDef(
        id="short_straddle",
        name="Short Straddle",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short ATM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short ATM PE"),
        ],
        description="Sell ATM call and put. Maximum theta capture with unlimited risk.",
        best_when="Range-bound, low volatility expected",
        max_profit="Total premium received",
        max_loss="Unlimited",
        greeks_profile="Maximum Theta, Negative Gamma",
        risk_level="High",
        tags=["range-bound", "premium-selling"],
    ),
    StrategyDef(
        id="short_strangle",
        name="Short Strangle",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short OTM PE"),
        ],
        description="Sell OTM call and put. Wider breakevens than straddle.",
        best_when="Range-bound, low volatility",
        max_profit="Total premium received",
        max_loss="Unlimited",
        greeks_profile="Positive Theta, Negative Gamma",
        risk_level="High",
        tags=["range-bound", "premium-selling"],
    ),
    StrategyDef(
        id="short_guts",
        name="Short Guts",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Short ITM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ITM, strike_offset=100, description="Short ITM PE"),
        ],
        description="Sell ITM call and put. Very high premium, very high margin.",
        best_when="Strong conviction of range-bound market",
        max_profit="Net premium - intrinsic",
        max_loss="Unlimited",
        greeks_profile="Positive Theta",
        risk_level="High",
        tags=["range-bound", "premium-selling"],
    ),
    StrategyDef(
        id="jade_lizard",
        name="Jade Lizard",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short OTM PE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Long further OTM CE"),
        ],
        description="Short put + Short call spread. No upside risk if credit > width.",
        best_when="Neutral to bullish",
        max_profit="Net credit",
        max_loss="PE strike - premium (downside only)",
        greeks_profile="Positive Theta",
        risk_level="Medium",
        tags=["neutral-bullish", "premium-selling"],
    ),
    StrategyDef(
        id="covered_short_straddle",
        name="Covered Short Straddle",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short ATM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short ATM PE"),
        ],
        description="Long stock + Short ATM straddle. Maximum premium with stock hedge.",
        best_when="Neutral on stock, want max income",
        max_profit="Premium + stock appreciation to strike",
        max_loss="Stock decline - premium",
        greeks_profile="Positive Theta",
        risk_level="Medium",
        tags=["income", "premium-selling"],
    ),
    StrategyDef(
        id="covered_short_strangle",
        name="Covered Short Strangle",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short OTM PE"),
        ],
        description="Long stock + Short OTM strangle. Income on stock holding.",
        best_when="Neutral on stock, want income",
        max_profit="Premium + appreciation to CE strike",
        max_loss="Stock decline - premium",
        greeks_profile="Positive Theta",
        risk_level="Medium",
        tags=["income", "premium-selling"],
    ),
    StrategyDef(
        id="short_call_synth_straddle",
        name="Short Call Synthetic Straddle",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, quantity_ratio=2, description="Short 2× ATM CE"),
        ],
        description="Short 2 calls + Long underlying. Premium selling via calls.",
        best_when="Neutral with stock position",
        max_profit="Premium received",
        max_loss="Unlimited on upside",
        greeks_profile="Positive Theta",
        risk_level="High",
        tags=["premium-selling"],
    ),
    StrategyDef(
        id="short_put_synth_straddle",
        name="Short Put Synthetic Straddle",
        category=Category.THETA,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, quantity_ratio=2, description="Short 2× ATM PE"),
        ],
        description="Short 2 puts + Short underlying. Premium selling via puts.",
        best_when="Neutral with short stock position",
        max_profit="Premium received",
        max_loss="Substantial on downside",
        greeks_profile="Positive Theta",
        risk_level="High",
        tags=["premium-selling"],
    ),

    # ==================== 5. GAMMA / VOLATILITY BUYING (11) ====================
    StrategyDef(
        id="long_straddle",
        name="Long Straddle",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
        ],
        description="Buy ATM call and put. Unlimited profit from large moves in either direction.",
        best_when="High volatility expected, event-driven",
        max_profit="Unlimited",
        max_loss="Total premium paid",
        greeks_profile="Positive Gamma, Negative Theta",
        risk_level="Medium",
        tags=["volatility", "event"],
    ),
    StrategyDef(
        id="long_strangle",
        name="Long Strangle",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long OTM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long OTM PE"),
        ],
        description="Buy OTM call and put. Cheaper than straddle, needs larger move.",
        best_when="High volatility expected, lower cost",
        max_profit="Unlimited",
        max_loss="Total premium paid",
        greeks_profile="Positive Gamma, Negative Theta",
        risk_level="Medium",
        tags=["volatility", "event"],
    ),
    StrategyDef(
        id="long_guts",
        name="Long Guts",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Long ITM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ITM, strike_offset=100, description="Long ITM PE"),
        ],
        description="Buy ITM call and put. More expensive, higher delta exposure.",
        best_when="Very high volatility expected",
        max_profit="Unlimited",
        max_loss="Total premium - intrinsic",
        greeks_profile="Positive Gamma, High Delta",
        risk_level="High",
        tags=["volatility"],
    ),
    StrategyDef(
        id="strap",
        name="Strap",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, quantity_ratio=2, description="Long 2× ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
        ],
        description="Bullish-biased straddle — 2× upside exposure.",
        best_when="Expecting large move, bullish bias",
        max_profit="Unlimited (2× on upside)",
        max_loss="Total premium paid",
        greeks_profile="Positive Gamma, Positive Delta",
        risk_level="Medium",
        tags=["volatility", "bullish-bias"],
    ),
    StrategyDef(
        id="strip",
        name="Strip",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, quantity_ratio=2, description="Long 2× ATM PE"),
        ],
        description="Bearish-biased straddle — 2× downside exposure.",
        best_when="Expecting large move, bearish bias",
        max_profit="Substantial (2× on downside)",
        max_loss="Total premium paid",
        greeks_profile="Positive Gamma, Negative Delta",
        risk_level="Medium",
        tags=["volatility", "bearish-bias"],
    ),
    StrategyDef(
        id="long_iron_butterfly",
        name="Long Iron Butterfly",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE wing"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short OTM PE wing"),
        ],
        description="Long ATM straddle + Short OTM wings. Capped risk debit trade.",
        best_when="Expecting move, want defined risk",
        max_profit="Width - Net debit",
        max_loss="Net debit",
        greeks_profile="Positive Gamma (at entry)",
        risk_level="Low",
        tags=["volatility", "defined-risk"],
    ),
    StrategyDef(
        id="reverse_iron_condor",
        name="Reverse Iron Condor",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long inner OTM CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Short outer OTM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long inner OTM PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-200, description="Short outer OTM PE"),
        ],
        description="Buy inner strikes, sell outer. Breakout play with defined risk.",
        best_when="Expecting breakout from range",
        max_profit="Width - Net debit",
        max_loss="Net debit",
        greeks_profile="Positive Gamma",
        risk_level="Low",
        tags=["volatility", "breakout", "defined-risk"],
    ),
    StrategyDef(
        id="short_call_condor",
        name="Short Call Condor",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=50, description="Short outer low CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long inner low CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=150, description="Long inner high CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Short outer high CE"),
        ],
        description="Short outer + Long inner calls. Breakout play via calls.",
        best_when="Expecting breakout via calls",
        max_profit="Width - Net debit",
        max_loss="Net debit",
        greeks_profile="Positive Gamma",
        risk_level="Low",
        tags=["volatility", "breakout"],
    ),
    StrategyDef(
        id="short_put_condor",
        name="Short Put Condor",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-200, description="Short outer low PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-150, description="Long inner low PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long inner high PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-50, description="Short outer high PE"),
        ],
        description="Short outer + Long inner puts. Breakout play via puts.",
        best_when="Expecting breakout via puts",
        max_profit="Width - Net debit",
        max_loss="Net debit",
        greeks_profile="Positive Gamma",
        risk_level="Low",
        tags=["volatility", "breakout"],
    ),
    StrategyDef(
        id="long_call_synth_straddle",
        name="Long Call Synthetic Straddle",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, quantity_ratio=2, description="Long 2× ATM CE"),
        ],
        description="Long 2 calls + Short underlying. Straddle replication via calls.",
        best_when="Expecting large move, use calls only",
        max_profit="Unlimited",
        max_loss="Premium paid",
        greeks_profile="Positive Gamma",
        risk_level="Medium",
        tags=["volatility"],
    ),
    StrategyDef(
        id="long_put_synth_straddle",
        name="Long Put Synthetic Straddle",
        category=Category.GAMMA,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, quantity_ratio=2, description="Long 2× ATM PE"),
        ],
        description="Long 2 puts + Long underlying. Straddle replication via puts.",
        best_when="Expecting large move, use puts only",
        max_profit="Substantial",
        max_loss="Premium paid",
        greeks_profile="Positive Gamma",
        risk_level="Medium",
        tags=["volatility"],
    ),

    # ==================== 6. BUTTERFLIES (10) ====================
    StrategyDef(
        id="long_call_butterfly",
        name="Long Call Butterfly",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Long lower CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, quantity_ratio=2, description="Short 2× ATM CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long upper CE"),
        ],
        description="Buy lower + upper call, sell 2× ATM call. Max profit if price pins at ATM.",
        best_when="Expecting price to pin at center strike",
        max_profit="Width - Net debit",
        max_loss="Net debit",
        greeks_profile="Positive Theta near ATM",
        risk_level="Low",
        tags=["range-bound", "low-cost"],
    ),
    StrategyDef(
        id="long_put_butterfly",
        name="Long Put Butterfly",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long lower PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, quantity_ratio=2, description="Short 2× ATM PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ITM, strike_offset=100, description="Long upper PE"),
        ],
        description="Buy lower + upper put, sell 2× ATM put. Max profit if pin at ATM.",
        best_when="Expecting price to pin at center strike",
        max_profit="Width - Net debit",
        max_loss="Net debit",
        greeks_profile="Positive Theta near ATM",
        risk_level="Low",
        tags=["range-bound", "low-cost"],
    ),
    StrategyDef(
        id="short_call_butterfly",
        name="Short Call Butterfly",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Short lower CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, quantity_ratio=2, description="Long 2× ATM CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short upper CE"),
        ],
        description="Reverse of long call butterfly. Profits from large move.",
        best_when="Big move expected",
        max_profit="Net credit",
        max_loss="Width - Net credit",
        greeks_profile="Negative Theta, Positive Gamma",
        risk_level="Low",
        tags=["volatility"],
    ),
    StrategyDef(
        id="short_put_butterfly",
        name="Short Put Butterfly",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short lower PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, quantity_ratio=2, description="Long 2× ATM PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ITM, strike_offset=100, description="Short upper PE"),
        ],
        description="Reverse of long put butterfly. Profits from large move.",
        best_when="Big move expected",
        max_profit="Net credit",
        max_loss="Width - Net credit",
        greeks_profile="Negative Theta, Positive Gamma",
        risk_level="Low",
        tags=["volatility"],
    ),
    StrategyDef(
        id="modified_call_butterfly",
        name="Modified Call Butterfly",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Long lower CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=50, quantity_ratio=2, description="Short 2× mid CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Long upper CE"),
        ],
        description="Asymmetric wing widths for directional bias + limited risk.",
        best_when="Directional bias with limited risk",
        max_profit="Upper width - debit",
        max_loss="Net debit",
        greeks_profile="Directional Theta",
        risk_level="Low",
        tags=["directional", "low-cost"],
    ),
    StrategyDef(
        id="modified_put_butterfly",
        name="Modified Put Butterfly",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-200, description="Long lower PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-50, quantity_ratio=2, description="Short 2× mid PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ITM, strike_offset=100, description="Long upper PE"),
        ],
        description="Asymmetric wing widths (puts) for directional bias + limited risk.",
        best_when="Directional bias with limited risk",
        max_profit="Lower width - debit",
        max_loss="Net debit",
        greeks_profile="Directional Theta",
        risk_level="Low",
        tags=["directional", "low-cost"],
    ),
    StrategyDef(
        id="broken_wing_butterfly",
        name="Broken Wing Butterfly",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Long lower CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, quantity_ratio=2, description="Short 2× ATM CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Long skip-strike upper CE"),
        ],
        description="Skip-strike butterfly for credit entry with directional bias.",
        best_when="Slightly directional, want credit entry",
        max_profit="Width of narrow side",
        max_loss="Width of wide side - credit",
        greeks_profile="Positive Theta (at entry)",
        risk_level="Low",
        tags=["directional", "credit"],
    ),
    StrategyDef(
        id="long_call_condor",
        name="Long Call Condor",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ITM, strike_offset=-150, description="Long lowest CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ITM, strike_offset=-50, description="Short inner low CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=50, description="Short inner high CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=150, description="Long highest CE"),
        ],
        description="4 different CE strikes forming a condor. Wider profit zone than butterfly.",
        best_when="Range-bound market, wider zone",
        max_profit="Inner width - Net debit",
        max_loss="Net debit",
        greeks_profile="Positive Theta in range",
        risk_level="Low",
        tags=["range-bound"],
    ),
    StrategyDef(
        id="long_put_condor",
        name="Long Put Condor",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-150, description="Long lowest PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-50, description="Short inner low PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ITM, strike_offset=50, description="Short inner high PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ITM, strike_offset=150, description="Long highest PE"),
        ],
        description="4 different PE strikes forming a condor.",
        best_when="Range-bound market",
        max_profit="Inner width - Net debit",
        max_loss="Net debit",
        greeks_profile="Positive Theta in range",
        risk_level="Low",
        tags=["range-bound"],
    ),
    StrategyDef(
        id="condor_spread",
        name="Condor Spread",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ITM, strike_offset=-150, description="Long lowest CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ITM, strike_offset=-50, description="Short inner low CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=50, description="Short inner high CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=150, description="Long highest CE"),
        ],
        description="Alias for Long Call Condor — 4 CE strikes.",
        best_when="Range-bound market",
        max_profit="Inner width - Net debit",
        max_loss="Net debit",
        greeks_profile="Positive Theta in range",
        risk_level="Low",
        tags=["range-bound"],
    ),

    # Christmas Tree Spread (Butterfly family)
    StrategyDef(
        id="christmas_tree_call",
        name="Christmas Tree Call Spread",
        category=Category.BUTTERFLY,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Short further OTM CE"),
        ],
        description="Long ATM CE + Short two different OTM CEs. Ladder-like with bullish bias.",
        best_when="Mildly bullish, range-bound",
        max_profit="First short strike - ATM - Net debit",
        max_loss="Net debit + unlimited above highest short",
        greeks_profile="Positive Delta, Positive Theta near body",
        risk_level="Medium",
        tags=["bullish", "range-bound"],
    ),

    # ==================== 7. LADDERS (4) ====================
    StrategyDef(
        id="bull_call_ladder",
        name="Bull Call Ladder",
        category=Category.LADDER,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Long lower CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short mid CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short higher CE"),
        ],
        description="Long lower CE + Short mid CE + Short higher CE. Mildly bullish with extra premium.",
        best_when="Mildly bullish, want extra premium",
        max_profit="Mid - Lower - Debit",
        max_loss="Unlimited above upper strike",
        greeks_profile="Positive Delta (limited), Positive Theta",
        risk_level="High",
        tags=["bullish", "premium-selling"],
    ),
    StrategyDef(
        id="bull_put_ladder",
        name="Bull Put Ladder",
        category=Category.LADDER,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, strike_offset=100, description="Short higher PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long mid PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short lower PE"),
        ],
        description="Short higher PE + Long mid PE + Short lower PE.",
        best_when="Mildly bullish",
        max_profit="Net credit",
        max_loss="Unlimited below lower strike",
        greeks_profile="Positive Delta, Positive Theta",
        risk_level="High",
        tags=["bullish"],
    ),
    StrategyDef(
        id="bear_call_ladder",
        name="Bear Call Ladder",
        category=Category.LADDER,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Short lower CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long mid CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long higher CE"),
        ],
        description="Short lower CE + Long mid CE + Long higher CE. Bearish with breakout potential.",
        best_when="Bearish with potential upside breakout",
        max_profit="Unlimited above upper strike",
        max_loss="Upper - Mid - Credit",
        greeks_profile="Negative Delta, Positive Gamma",
        risk_level="High",
        tags=["bearish", "breakout"],
    ),
    StrategyDef(
        id="bear_put_ladder",
        name="Bear Put Ladder",
        category=Category.LADDER,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ITM, strike_offset=100, description="Long higher PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short mid PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long lower PE"),
        ],
        description="Long higher PE + Short mid PE + Long lower PE. Mildly bearish.",
        best_when="Mildly bearish",
        max_profit="Upper - Mid - Debit",
        max_loss="Net debit",
        greeks_profile="Negative Delta",
        risk_level="Medium",
        tags=["bearish"],
    ),

    # ==================== 8. RATIO / ASYMMETRIC (4) ====================
    StrategyDef(
        id="call_ratio_backspread",
        name="Call Ratio Backspread",
        category=Category.RATIO,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Short 1 lower CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, quantity_ratio=2, description="Long 2 higher CE"),
        ],
        description="Short 1 lower CE + Long 2 higher CE. Unlimited upside, very bullish.",
        best_when="Very bullish, expecting large upside move",
        max_profit="Unlimited",
        max_loss="Upper - Lower - Net credit",
        greeks_profile="Positive Gamma, Positive Delta on move up",
        risk_level="Medium",
        tags=["bullish", "volatility"],
    ),
    StrategyDef(
        id="put_ratio_backspread",
        name="Put Ratio Backspread",
        category=Category.RATIO,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, quantity_ratio=2, description="Long 2 lower PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ITM, strike_offset=100, description="Short 1 higher PE"),
        ],
        description="Long 2 lower PE + Short 1 higher PE. Large downside profit, very bearish.",
        best_when="Very bearish, expecting large downside move",
        max_profit="Substantial (lower strike - premium)",
        max_loss="Upper - Lower - Net credit",
        greeks_profile="Positive Gamma, Negative Delta on move down",
        risk_level="Medium",
        tags=["bearish", "volatility"],
    ),
    StrategyDef(
        id="ratio_call_spread",
        name="Ratio Call Spread",
        category=Category.RATIO,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long 1 lower CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, quantity_ratio=2, description="Short 2 higher CE"),
        ],
        description="Long 1 lower CE + Short 2 higher CE. Mildly bullish, extra premium (unlimited risk).",
        best_when="Mildly bullish, high IV",
        max_profit="Upper - Lower + Net credit",
        max_loss="Unlimited above upper strike",
        greeks_profile="Positive Theta, Negative Gamma on big move",
        risk_level="High",
        tags=["bullish", "premium-selling"],
    ),
    StrategyDef(
        id="ratio_put_spread",
        name="Ratio Put Spread",
        category=Category.RATIO,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, quantity_ratio=2, description="Short 2 lower PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long 1 higher PE"),
        ],
        description="Short 2 lower PE + Long 1 higher PE. Mildly bearish, extra premium.",
        best_when="Mildly bearish, high IV",
        max_profit="Upper - Lower + Net credit",
        max_loss="Substantial below lower strike",
        greeks_profile="Positive Theta, Negative Gamma on big move",
        risk_level="High",
        tags=["bearish", "premium-selling"],
    ),

    # ==================== 9. CALENDAR / DIAGONAL (4) ====================
    StrategyDef(
        id="calendar_call_spread",
        name="Calendar Call Spread",
        category=Category.CALENDAR,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, expiry="near", description="Short near-term ATM CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, expiry="far", description="Long far-term ATM CE"),
        ],
        description="Short near CE + Long far CE (same strike). Profit from near-month time decay.",
        best_when="Neutral, expect near-month to decay faster",
        max_profit="Far premium - Near premium at expiry",
        max_loss="Net debit",
        greeks_profile="Positive Theta, Positive Vega",
        risk_level="Low",
        tags=["neutral", "time-spread"],
    ),
    StrategyDef(
        id="calendar_put_spread",
        name="Calendar Put Spread",
        category=Category.CALENDAR,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, expiry="near", description="Short near-term ATM PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, expiry="far", description="Long far-term ATM PE"),
        ],
        description="Short near PE + Long far PE (same strike). Profit from near-month time decay.",
        best_when="Neutral, expect near-month to decay faster",
        max_profit="Far premium - Near premium at expiry",
        max_loss="Net debit",
        greeks_profile="Positive Theta, Positive Vega",
        risk_level="Low",
        tags=["neutral", "time-spread"],
    ),
    StrategyDef(
        id="diagonal_call_spread",
        name="Diagonal Call Spread",
        category=Category.CALENDAR,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, expiry="near", description="Short near-term OTM CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, expiry="far", description="Long far-term ATM CE"),
        ],
        description="Short near higher CE + Long far lower CE. Directional + time spread.",
        best_when="Mildly bullish with time decay",
        max_profit="Variable (depends on IV)",
        max_loss="Net debit",
        greeks_profile="Positive Delta, Positive Theta",
        risk_level="Low",
        tags=["bullish", "time-spread"],
    ),
    StrategyDef(
        id="diagonal_put_spread",
        name="Diagonal Put Spread",
        category=Category.CALENDAR,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, expiry="near", description="Short near-term OTM PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, expiry="far", description="Long far-term ATM PE"),
        ],
        description="Short near lower PE + Long far higher PE. Directional + time spread.",
        best_when="Mildly bearish with time decay",
        max_profit="Variable (depends on IV)",
        max_loss="Net debit",
        greeks_profile="Negative Delta, Positive Theta",
        risk_level="Low",
        tags=["bearish", "time-spread"],
    ),
    StrategyDef(
        id="double_calendar",
        name="Double Calendar Spread",
        category=Category.CALENDAR,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, expiry="near", description="Short near OTM CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, expiry="far", description="Long far OTM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, expiry="near", description="Short near OTM PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, expiry="far", description="Long far OTM PE"),
        ],
        description="Two calendar spreads — one call side, one put side. Profits from near-month decay at two strikes.",
        best_when="Range-bound, expect time decay differential",
        max_profit="Near premium decay on both sides",
        max_loss="Net debit",
        greeks_profile="Positive Theta, Positive Vega",
        risk_level="Low",
        tags=["neutral", "time-spread", "range-bound"],
    ),
    StrategyDef(
        id="double_diagonal",
        name="Double Diagonal Spread",
        category=Category.CALENDAR,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=150, expiry="near", description="Short near further OTM CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, expiry="far", description="Long far OTM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-150, expiry="near", description="Short near further OTM PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, expiry="far", description="Long far OTM PE"),
        ],
        description="Two diagonal spreads — different strikes and expiries on both sides.",
        best_when="Range-bound with slight directional view",
        max_profit="Near premium decay + directional profit",
        max_loss="Net debit",
        greeks_profile="Positive Theta, Positive Vega",
        risk_level="Low",
        tags=["neutral", "time-spread"],
    ),

    # ==================== 10. HEDGING / PROTECTIVE (5) ====================
    StrategyDef(
        id="covered_call",
        name="Covered Call",
        category=Category.HEDGING,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE"),
        ],
        description="Long stock + Short OTM CE. Income generation on existing long position.",
        best_when="Mildly bullish on stock, want income",
        max_profit="CE premium + (strike - cost)",
        max_loss="Cost basis - premium received",
        greeks_profile="Positive Theta, reduced Delta",
        risk_level="Low",
        tags=["income", "hedging"],
    ),
    StrategyDef(
        id="covered_put",
        name="Covered Put",
        category=Category.HEDGING,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short OTM PE"),
        ],
        description="Short stock + Short OTM PE. Income on existing short position.",
        best_when="Mildly bearish on stock, want income",
        max_profit="PE premium + (short price - strike)",
        max_loss="Unlimited (stock rises)",
        greeks_profile="Positive Theta",
        risk_level="Medium",
        tags=["income", "hedging"],
    ),
    StrategyDef(
        id="protective_put",
        name="Protective Put",
        category=Category.HEDGING,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long OTM PE"),
        ],
        description="Long stock + Long OTM PE. Insurance for long position.",
        best_when="Want downside protection on long stock",
        max_profit="Unlimited (stock rises)",
        max_loss="Cost basis - strike + premium",
        greeks_profile="Negative Theta, Delta protected",
        risk_level="Low",
        tags=["hedging", "insurance"],
    ),
    StrategyDef(
        id="protective_call",
        name="Protective Call",
        category=Category.HEDGING,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long OTM CE"),
        ],
        description="Short stock + Long OTM CE. Insurance for short position.",
        best_when="Want upside protection on short stock",
        max_profit="Short price - premium",
        max_loss="Strike - short price + premium",
        greeks_profile="Negative Theta, Delta protected",
        risk_level="Low",
        tags=["hedging", "insurance"],
    ),
    StrategyDef(
        id="collar",
        name="Collar",
        category=Category.HEDGING,
        legs=[
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long OTM PE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE"),
        ],
        description="Long stock + Long PE + Short CE. Zero/low-cost downside protection.",
        best_when="Want free/cheap downside protection",
        max_profit="CE strike - cost (capped)",
        max_loss="Cost - PE strike (capped)",
        greeks_profile="Near-zero Theta if balanced",
        risk_level="Low",
        tags=["hedging", "zero-cost"],
    ),

    # ==================== 11. ARBITRAGE & EXOTIC (2) ====================
    StrategyDef(
        id="long_box",
        name="Long Box Spread",
        category=Category.ARBITRAGE,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ITM, strike_offset=-100, description="Long lower CE"),
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short upper CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=100, description="Long upper PE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ITM, strike_offset=-100, description="Short lower PE"),
        ],
        description="Bull call spread + Bear put spread. Risk-free profit if mispriced.",
        best_when="Options mispricing detected",
        max_profit="Width - Net debit (if mispriced)",
        max_loss="Net debit (typically minimal)",
        greeks_profile="All Greeks ≈ 0",
        risk_level="Low",
        tags=["arbitrage"],
    ),
    StrategyDef(
        id="cash_futures_arbitrage",
        name="Cash-Futures Arbitrage",
        category=Category.ARBITRAGE,
        legs=[],
        description="Buy spot + Sell futures when futures basis > fair value.",
        best_when="Futures premium exceeds fair value",
        max_profit="Basis - fair value",
        max_loss="Minimal (execution risk)",
        greeks_profile="Market neutral",
        risk_level="Low",
        tags=["arbitrage", "basis-trade"],
    ),

    # ==================== 12. VOLATILITY STRATEGIES (4) ====================
    StrategyDef(
        id="vol_risk_premium",
        name="Volatility Risk Premium",
        category=Category.VOLATILITY,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short ATM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short ATM PE"),
        ],
        description="Sell when IV significantly above realized vol. Capture volatility risk premium.",
        best_when="IV significantly above realized vol",
        max_profit="Premium received",
        max_loss="Unlimited",
        greeks_profile="Short Vega, Positive Theta",
        risk_level="High",
        tags=["volatility", "premium-selling"],
    ),
    StrategyDef(
        id="vol_skew_reversal",
        name="Vol Skew Risk Reversal",
        category=Category.VOLATILITY,
        legs=[
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-200, description="Sell expensive OTM PE (high IV)"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Buy cheap OTM CE (low IV)"),
        ],
        description="Sell expensive wing, buy cheap wing. Exploit extreme IV skew.",
        best_when="Extreme skew in IV surface",
        max_profit="Unlimited on CE side",
        max_loss="PE strike - premium",
        greeks_profile="Long Vega skew",
        risk_level="Medium",
        tags=["volatility", "skew"],
    ),
    StrategyDef(
        id="dispersion_trade",
        name="Dispersion Trade",
        category=Category.VOLATILITY,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short index ATM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short index ATM PE"),
        ],
        description="Sell index straddle + buy component straddles. Profit when index IV > component IV.",
        best_when="Index IV > weighted component IV",
        max_profit="IV differential × vega",
        max_loss="Reverse IV move",
        greeks_profile="Short index Vega, Long component Vega",
        risk_level="High",
        tags=["volatility", "dispersion"],
    ),
    StrategyDef(
        id="gamma_scalp_enhanced",
        name="Gamma Scalp Enhanced",
        category=Category.VOLATILITY,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
        ],
        description="Long straddle + delta-hedge repeatedly. Profit from realized vol > implied vol.",
        best_when="High realized vol environment",
        max_profit="Realized vol profit - theta decay",
        max_loss="Net premium if vol stays low",
        greeks_profile="Positive Gamma, delta-hedged",
        risk_level="Medium",
        tags=["volatility", "gamma-scalping"],
    ),

    # ==================== 13. SIGNAL-BASED (4) ====================
    StrategyDef(
        id="earnings_straddle",
        name="Earnings Straddle",
        category=Category.SIGNAL,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
        ],
        description="Long straddle before earnings announcements.",
        best_when="Before earnings announcements",
        max_profit="Unlimited",
        max_loss="Total premium paid",
        greeks_profile="Positive Gamma, Positive Vega",
        risk_level="Medium",
        tags=["event", "earnings"],
    ),
    StrategyDef(
        id="rbi_policy_straddle",
        name="RBI Policy Straddle",
        category=Category.SIGNAL,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
        ],
        description="Long straddle before RBI monetary policy decisions.",
        best_when="Before RBI monetary policy",
        max_profit="Unlimited",
        max_loss="Total premium paid",
        greeks_profile="Positive Gamma, Positive Vega",
        risk_level="Medium",
        tags=["event", "policy"],
    ),
    StrategyDef(
        id="low_vol_premium_sell",
        name="Low Vol Premium Sell",
        category=Category.SIGNAL,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Short OTM CE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=200, description="Long further OTM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Short OTM PE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-200, description="Long further OTM PE"),
        ],
        description="Iron condor triggered when India VIX < 15.",
        best_when="India VIX < 15",
        max_profit="Net premium received",
        max_loss="Width - premium",
        greeks_profile="Positive Theta",
        risk_level="Low",
        tags=["signal", "low-vol"],
    ),
    StrategyDef(
        id="high_vol_premium_buy",
        name="High Vol Premium Buy",
        category=Category.SIGNAL,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
        ],
        description="Long straddle triggered when India VIX > 20.",
        best_when="India VIX > 20",
        max_profit="Unlimited",
        max_loss="Total premium paid",
        greeks_profile="Positive Gamma, Positive Vega",
        risk_level="Medium",
        tags=["signal", "high-vol"],
    ),
    StrategyDef(
        id="budget_day_straddle",
        name="Budget Day Straddle",
        category=Category.SIGNAL,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.ATM, description="Long ATM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.ATM, description="Long ATM PE"),
        ],
        description="Long straddle before Union Budget presentation — high event volatility.",
        best_when="Before Union Budget day",
        max_profit="Unlimited",
        max_loss="Total premium paid",
        greeks_profile="Positive Gamma, Positive Vega",
        risk_level="Medium",
        tags=["signal", "event", "budget"],
    ),
    StrategyDef(
        id="expiry_day_iron_fly",
        name="Expiry Day Iron Butterfly",
        category=Category.SIGNAL,
        legs=[
            LegDef(LegAction.SELL, OptionType.CE, StrikeRef.ATM, description="Short ATM CE"),
            LegDef(LegAction.SELL, OptionType.PE, StrikeRef.ATM, description="Short ATM PE"),
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long OTM CE wing"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long OTM PE wing"),
        ],
        description="Iron butterfly on expiry day — rapid theta decay maximizes premium capture.",
        best_when="Thursday expiry day (0DTE)",
        max_profit="Net premium received",
        max_loss="Width - premium",
        greeks_profile="Maximum Theta, Negative Gamma",
        risk_level="Medium",
        tags=["signal", "0dte", "expiry"],
    ),
    StrategyDef(
        id="gap_open_strangle",
        name="Gap Open Strangle",
        category=Category.SIGNAL,
        legs=[
            LegDef(LegAction.BUY, OptionType.CE, StrikeRef.OTM, strike_offset=100, description="Long OTM CE"),
            LegDef(LegAction.BUY, OptionType.PE, StrikeRef.OTM, strike_offset=-100, description="Long OTM PE"),
        ],
        description="Long strangle entered before expected gap openings based on global market cues.",
        best_when="Significant overnight global moves",
        max_profit="Unlimited",
        max_loss="Total premium paid",
        greeks_profile="Positive Gamma",
        risk_level="Medium",
        tags=["signal", "event", "gap"],
    ),
]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def get_all_strategies() -> List[StrategyDef]:
    """Return all 77 strategy definitions."""
    return STRATEGY_CATALOG


def get_strategy_by_id(strategy_id: str) -> Optional[StrategyDef]:
    """Look up a single strategy by its id."""
    for s in STRATEGY_CATALOG:
        if s.id == strategy_id:
            return s
    return None


def get_strategies_by_category(category: Category) -> List[StrategyDef]:
    """Return all strategies in a given category."""
    return [s for s in STRATEGY_CATALOG if s.category == category]


def get_categories() -> Dict[str, List[StrategyDef]]:
    """Return strategies grouped by category."""
    groups: Dict[str, List[StrategyDef]] = {}
    for s in STRATEGY_CATALOG:
        key = s.category.value
        groups.setdefault(key, []).append(s)
    return groups


def search_strategies(query: str) -> List[StrategyDef]:
    """Simple text search across strategy name, description, and tags."""
    q = query.lower()
    return [
        s for s in STRATEGY_CATALOG
        if q in s.name.lower()
        or q in s.description.lower()
        or any(q in t for t in s.tags)
    ]
