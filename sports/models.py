"""Shared data models for Kraitos Sports intelligence pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Sport(str, Enum):
    SOCCER = "soccer"
    BASKETBALL = "basketball"
    TENNIS = "tennis"
    RUGBY = "rugby"
    CRICKET = "cricket"
    BASEBALL = "baseball"
    AMERICAN_FOOTBALL = "american_football"
    ICE_HOCKEY = "ice_hockey"
    MMA = "mma"
    ESPORTS = "esports"


class Decision(str, Enum):
    VALUE_BET = "Value Bet"
    ARBITRAGE = "Arbitrage"
    WATCHLIST = "Watchlist"
    PASS = "Pass"


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class OpportunityGrade(str, Enum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    PASS = "PASS"


class BetMarket(str, Enum):
    MATCH_WINNER = "Match Winner"
    DOUBLE_CHANCE = "Double Chance"
    DRAW_NO_BET = "Draw No Bet"
    ASIAN_HANDICAP = "Asian Handicap"
    OVER_UNDER = "Over/Under"
    BTTS = "Both Teams To Score"
    CORRECT_SCORE = "Correct Score"
    FIRST_HALF = "First Half Markets"
    PLAYER_PROPS = "Player Props"
    CORNERS = "Corners"
    CARDS = "Cards"
    SET_BETTING = "Set Betting"
    TOTALS = "Totals"
    LIVE = "Live Markets"


@dataclass(frozen=True)
class BookmakerOdds:
    bookmaker: str
    home: float
    draw: float | None = None
    away: float | None = None
    over: float | None = None
    under: float | None = None
    line: float | None = None


@dataclass(frozen=True)
class TeamProfile:
    name: str
    squad_quality: float
    market_value_m: float
    injuries: tuple[str, ...] = ()
    suspensions: tuple[str, ...] = ()
    full_strength_pct: float = 100.0
    recent_transfers: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoachProfile:
    name: str
    tactical_style: str
    home_overperformance: float
    away_overperformance: float
    adaptability: float
    historical_overperformance: float


@dataclass(frozen=True)
class FormSnapshot:
    last_5: str
    last_10: str
    home_form: str
    away_form: str
    momentum: str
    goal_trend: str
    trend_label: str


@dataclass(frozen=True)
class XGSnapshot:
    xg: float
    xga: float
    big_chances_created: int
    big_chances_conceded: int
    shot_quality: float
    conversion_rate: float
    defensive_efficiency: float
    luck_label: str


@dataclass(frozen=True)
class MatchContext:
    """Inputs for a single-match sports evaluation."""

    match_id: str
    sport: Sport
    league: str
    home_team: str
    away_team: str
    kickoff: datetime
    trace_id: str
    home_profile: TeamProfile | None = None
    away_profile: TeamProfile | None = None
    home_coach: CoachProfile | None = None
    away_coach: CoachProfile | None = None
    home_form: FormSnapshot | None = None
    away_form: FormSnapshot | None = None
    home_xg: XGSnapshot | None = None
    away_xg: XGSnapshot | None = None
    bookmaker_odds: tuple[BookmakerOdds, ...] = ()
    context_factors: tuple[str, ...] = ()
    is_live: bool = False
    live_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArbitrageResult:
    detected: bool
    profit_pct: float
    stake_allocation: dict[str, float] = field(default_factory=dict)
    bookmakers: tuple[str, ...] = ()
    risk_level: RiskLevel = RiskLevel.MEDIUM
    execution_speed: str = "Standard"
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "detected": self.detected,
            "profit_pct": round(self.profit_pct, 2),
            "stake_allocation": {
                k: round(v, 2) for k, v in self.stake_allocation.items()
            },
            "bookmakers": list(self.bookmakers),
            "risk_level": self.risk_level.value,
            "execution_speed": self.execution_speed,
            "summary": self.summary,
        }


@dataclass
class ValueBetResult:
    fair_odds: float
    market_odds: float
    fair_probability: float
    market_probability: float
    ev_pct: float
    value_score: float
    confidence: float
    market: BetMarket
    selection: str
    positive_ev: bool = False

    def to_dict(self) -> dict:
        return {
            "fair_odds": round(self.fair_odds, 2),
            "market_odds": round(self.market_odds, 2),
            "fair_probability": round(self.fair_probability, 3),
            "market_probability": round(self.market_probability, 3),
            "ev_pct": round(self.ev_pct, 2),
            "value_score": round(self.value_score, 1),
            "confidence": round(self.confidence, 1),
            "market": self.market.value,
            "selection": self.selection,
            "positive_ev": self.positive_ev,
        }


@dataclass
class AgentOpinion:
    agent: str
    opinion: str
    confidence: float
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "opinion": self.opinion,
            "confidence": round(self.confidence, 1),
            "evidence": list(self.evidence),
        }


@dataclass
class CouncilSummary:
    consensus: str
    confidence: float
    opinions: tuple[AgentOpinion, ...] = ()
    edge_detected: bool = False

    def to_dict(self) -> dict:
        return {
            "consensus": self.consensus,
            "confidence": round(self.confidence, 1),
            "opinions": [o.to_dict() for o in self.opinions],
            "edge_detected": self.edge_detected,
        }


@dataclass
class RedTeamResult:
    approved: bool
    concerns: tuple[str, ...] = ()
    challenges: tuple[str, ...] = ()
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "concerns": list(self.concerns),
            "challenges": list(self.challenges),
            "summary": self.summary,
        }


@dataclass
class MonteCarloResult:
    home_win: float
    draw: float
    away_win: float
    over_25: float
    btts: float
    top_scores: tuple[tuple[str, float], ...] = ()
    simulations: int = 10000

    def to_dict(self) -> dict:
        return {
            "home_win": round(self.home_win, 3),
            "draw": round(self.draw, 3),
            "away_win": round(self.away_win, 3),
            "over_25": round(self.over_25, 3),
            "btts": round(self.btts, 3),
            "top_scores": [
                {"score": s, "probability": round(p, 3)} for s, p in self.top_scores
            ],
            "simulations": self.simulations,
        }


@dataclass
class MatchAnalysis:
    """Full Kraitos Sports output for one match."""

    match_id: str
    sport: Sport
    league: str
    home_team: str
    away_team: str
    kickoff: datetime
    trace_id: str
    recommended_market: BetMarket | None = None
    decision: Decision = Decision.PASS
    edge_score: float = 0.0
    confidence: float = 0.0
    grade: OpportunityGrade = OpportunityGrade.PASS
    risk_level: RiskLevel = RiskLevel.MEDIUM
    pass_reason: str = ""
    value_bet: ValueBetResult | None = None
    arbitrage: ArbitrageResult | None = None
    team_strength: str = ""
    coach_analysis: str = ""
    form_analysis: str = ""
    xg_analysis: str = ""
    market_intelligence: str = ""
    context_factors: tuple[str, ...] = ()
    monte_carlo: MonteCarloResult | None = None
    council: CouncilSummary | None = None
    red_team: RedTeamResult | None = None
    reasoning_summary: str = ""
    explainability: dict[str, Any] = field(default_factory=dict)
    portfolio_notes: str = ""
    prediction: str = ""
    prediction_confidence: float = 0.0
    prediction_reasoning: str = ""
    prediction_detail: dict[str, Any] = field(default_factory=dict)
    is_lower_league: bool = False
    league_tier: int | None = None

    @property
    def match_label(self) -> str:
        return f"{self.home_team} vs {self.away_team}"

    def to_dict(self) -> dict:
        return {
            "match_id": self.match_id,
            "match": self.match_label,
            "sport": self.sport.value,
            "league": self.league,
            "kickoff_time": self.kickoff.isoformat(),
            "recommended_market": (
                self.recommended_market.value if self.recommended_market else None
            ),
            "decision": self.decision.value,
            "edge_score": round(self.edge_score, 1),
            "confidence": round(self.confidence, 1),
            "grade": self.grade.value,
            "risk_level": self.risk_level.value,
            "pass_reason": self.pass_reason,
            "fair_odds": (
                round(self.value_bet.fair_odds, 2) if self.value_bet else None
            ),
            "market_odds": (
                round(self.value_bet.market_odds, 2) if self.value_bet else None
            ),
            "expected_value": (
                round(self.value_bet.ev_pct, 2) if self.value_bet else None
            ),
            "value_bet": self.value_bet.to_dict() if self.value_bet else None,
            "arbitrage": self.arbitrage.to_dict() if self.arbitrage else None,
            "team_strength_analysis": self.team_strength,
            "coach_analysis": self.coach_analysis,
            "form_analysis": self.form_analysis,
            "xg_analysis": self.xg_analysis,
            "market_intelligence": self.market_intelligence,
            "context_factors": list(self.context_factors),
            "monte_carlo_results": (
                self.monte_carlo.to_dict() if self.monte_carlo else None
            ),
            "multi_agent_council_summary": (
                self.council.to_dict() if self.council else None
            ),
            "red_team_concerns": (
                self.red_team.to_dict() if self.red_team else None
            ),
            "reasoning_summary": self.reasoning_summary,
            "explainability": self.explainability,
            "portfolio_notes": self.portfolio_notes,
            "prediction": self.prediction or None,
            "prediction_confidence": round(self.prediction_confidence, 1) if self.prediction else None,
            "prediction_reasoning": self.prediction_reasoning or None,
            "prediction_detail": self.prediction_detail or None,
            "is_lower_league": self.is_lower_league,
            "league_tier": self.league_tier,
            "philosophy": "Kraitos does not pick winners. Kraitos finds edges.",
        }


@dataclass
class SportsBrainStats:
    matches_scanned: int = 0
    edges_found: int = 0
    arbitrage_found: int = 0
    passes: int = 0
