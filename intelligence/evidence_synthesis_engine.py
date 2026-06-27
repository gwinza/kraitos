"""Evidence Synthesis Engine — one coherent market story from all evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from core.helpers import pip_size_for_symbol
from intelligence.harvest_opportunity_score import infer_session

if TYPE_CHECKING:
    from intelligence.indicator_interpretation_engine import IndicatorInterpretation
    from intelligence.market_psychology_engine import MarketPsychologyResult
    from intelligence.story_evolution_engine import NestedStoryState
    from intelligence.trader_memory_engine import MemoryRecallInsight
    from strategies.models import MarketContext, MultiTimeframeBiasResult, RegimeResult

AllocationBias = Literal["harvest", "proper", "elite", "scout", "micro"]
RiskLevel = Literal["low", "medium", "high"]
UnclearReason = Literal["insufficient", "incoherent", "random", ""]

EVIDENCE_TIMEFRAMES = ("H8", "H4", "H1", "M15", "M5", "M1")
MIN_EVIDENCE_PIECES = 3
NOISE_RANGE_RATIO = 0.55


@dataclass(frozen=True)
class EvidencePiece:
    """Single observation — not a standalone story."""

    category: str
    timeframe: str
    signal: str
    description: str
    direction: str
    strength: float

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "timeframe": self.timeframe,
            "signal": self.signal,
            "description": self.description,
            "direction": self.direction,
            "strength": round(self.strength, 1),
        }


@dataclass(frozen=True)
class MarketStorySummary:
    """Synthesised market story — one explanation from all evidence."""

    symbol: str
    current_explanation: str
    supporting_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    confidence: float
    probable_next_event: str
    recommended_action: str
    risk_level: RiskLevel
    allocation_bias: AllocationBias
    story_clear: bool
    unclear_reason: UnclearReason = ""
    dominant_direction: str = "neutral"
    opportunity_hint: str | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_explanation": self.current_explanation,
            "supporting_evidence": list(self.supporting_evidence),
            "contradicting_evidence": list(self.contradicting_evidence),
            "confidence": round(self.confidence, 1),
            "probable_next_event": self.probable_next_event,
            "recommended_action": self.recommended_action,
            "risk_level": self.risk_level,
            "allocation_bias": self.allocation_bias,
            "story_clear": self.story_clear,
            "unclear_reason": self.unclear_reason or None,
            "dominant_direction": self.dominant_direction,
            "opportunity_hint": self.opportunity_hint,
        }


@dataclass
class SynthesisStats:
    """Accumulated synthesis metrics for validation reporting."""

    synthesised: int = 0
    story_clear: int = 0
    story_unclear: int = 0
    unclear_insufficient: int = 0
    unclear_incoherent: int = 0
    unclear_random: int = 0
    conflicts_interpreted: int = 0
    opportunities_recovered: int = 0


class EvidenceSynthesisEngine:
    """
    Collect evidence across categories and synthesise ONE coherent market story.

    Conflicting evidence is interpreted — not rejected.
    story_unclear only when insufficient, incoherent, or random noise dominates.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root.resolve() if project_root else None
        self._latest: dict[str, MarketStorySummary] = {}
        self._history: list[tuple[str, MarketStorySummary]] = []
        self.stats = SynthesisStats()

    def synthesise(
        self,
        symbol: str,
        candles_by_tf: dict[str, pd.DataFrame],
        *,
        structure: MarketContext | None = None,
        bias: MultiTimeframeBiasResult | None = None,
        regime: RegimeResult | None = None,
        story_evolution_state: NestedStoryState | None = None,
        evaluation_moment: datetime | None = None,
        indicator_interpretation: IndicatorInterpretation | None = None,
        market_psychology: MarketPsychologyResult | None = None,
        trader_memory_recall: MemoryRecallInsight | None = None,
    ) -> MarketStorySummary:
        symbol = symbol.strip().upper()
        pieces = self._collect_all_evidence(
            symbol,
            candles_by_tf,
            structure=structure,
            bias=bias,
            regime=regime,
            story_evolution_state=story_evolution_state,
            evaluation_moment=evaluation_moment,
            indicator_interpretation=indicator_interpretation,
            market_psychology=market_psychology,
            trader_memory_recall=trader_memory_recall,
        )
        summary = self._synthesise_from_pieces(symbol, pieces, story_evolution_state)
        self._latest[symbol] = summary
        self._history.append((symbol, summary))
        self.stats.synthesised += 1
        if summary.story_clear:
            self.stats.story_clear += 1
        else:
            self.stats.story_unclear += 1
            if summary.unclear_reason == "insufficient":
                self.stats.unclear_insufficient += 1
            elif summary.unclear_reason == "incoherent":
                self.stats.unclear_incoherent += 1
            elif summary.unclear_reason == "random":
                self.stats.unclear_random += 1
        if summary.contradicting_evidence and summary.story_clear:
            self.stats.conflicts_interpreted += 1
        return summary

    def _collect_all_evidence(
        self,
        symbol: str,
        candles_by_tf: dict[str, pd.DataFrame],
        *,
        structure: MarketContext | None,
        bias: MultiTimeframeBiasResult | None,
        regime: RegimeResult | None,
        story_evolution_state: NestedStoryState | None,
        evaluation_moment: datetime | None,
        indicator_interpretation: IndicatorInterpretation | None = None,
        market_psychology: MarketPsychologyResult | None = None,
        trader_memory_recall: MemoryRecallInsight | None = None,
    ) -> list[EvidencePiece]:
        pieces: list[EvidencePiece] = []
        pieces.extend(self._collect_trend(symbol, candles_by_tf, structure, bias, regime))
        pieces.extend(self._collect_structure(symbol, candles_by_tf, structure, bias))
        pieces.extend(self._collect_liquidity(symbol, candles_by_tf, structure))
        pieces.extend(self._collect_volume(symbol, candles_by_tf))
        pieces.extend(self._collect_candlestick(symbol, candles_by_tf))
        pieces.extend(self._collect_session(symbol, candles_by_tf, evaluation_moment))
        pieces.extend(self._collect_momentum(symbol, candles_by_tf, bias))
        pieces.extend(self._collect_timeframe(symbol, candles_by_tf, structure, bias))
        if story_evolution_state is not None:
            pieces.extend(self._collect_evolution(story_evolution_state))
        if indicator_interpretation is not None:
            pieces.extend(self._collect_indicator_psychology(indicator_interpretation))
        if market_psychology is not None:
            pieces.extend(self._collect_market_psychology(market_psychology))
        if trader_memory_recall is not None:
            pieces.extend(self._collect_trader_memory(trader_memory_recall))
        return pieces

    @staticmethod
    def _collect_indicator_psychology(
        interpretation: IndicatorInterpretation,
    ) -> list[EvidencePiece]:
        """Merge indicator psychology as evidence — never blocks synthesis."""
        return interpretation.to_evidence_pieces()

    @staticmethod
    def _collect_market_psychology(
        psychology: MarketPsychologyResult,
    ) -> list[EvidencePiece]:
        """Merge inferred participant psychology — never blocks synthesis."""
        return psychology.to_evidence_pieces()

    @staticmethod
    def _collect_trader_memory(
        recall: MemoryRecallInsight,
    ) -> list[EvidencePiece]:
        """Merge remembered experience — never blocks synthesis."""
        return recall.to_evidence_pieces()

    def _collect_trend(
        self,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext | None,
        bias: MultiTimeframeBiasResult | None,
        regime: RegimeResult | None,
    ) -> list[EvidencePiece]:
        out: list[EvidencePiece] = []
        for tf in ("H8", "H4", "H1"):
            frame = candles.get(tf)
            if frame is None or len(frame) < 5:
                continue
            m = _frame_metrics(frame, symbol)
            direction = "bullish" if m["momentum"] > 1.5 else (
                "bearish" if m["momentum"] < -1.5 else "neutral"
            )
            if structure is not None and structure.trend in {"bullish", "bearish"}:
                direction = structure.trend  # type: ignore[assignment]
            strength = min(100.0, 45.0 + abs(m["momentum"]) * 4.0)
            if m["range_ratio"] > 1.2 and m["vol_ratio"] > 1.1:
                out.append(EvidencePiece(
                    "trend", tf, "acceleration",
                    f"{tf} trend accelerating {direction}", direction, strength + 10,
                ))
            elif m["range_ratio"] < 0.7 and abs(m["momentum"]) < 2.0:
                out.append(EvidencePiece(
                    "trend", tf, "deterioration",
                    f"{tf} trend losing momentum", direction, max(30.0, strength - 15),
                ))
            else:
                out.append(EvidencePiece(
                    "trend", tf, "direction",
                    f"{tf} {direction} trend", direction, strength,
                ))
        if regime is not None and regime.regime == "trending":
            d = bias.bias if bias else "neutral"
            out.append(EvidencePiece(
                "trend", "regime", "regime_trending",
                f"Regime trending {d}", d, 60.0 + (bias.confidence * 20 if bias else 0),
            ))
        return out

    def _collect_structure(
        self,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext | None,
        bias: MultiTimeframeBiasResult | None,
    ) -> list[EvidencePiece]:
        out: list[EvidencePiece] = []
        if structure is None:
            return out
        direction = structure.trend
        if structure.last_bos is not None:
            out.append(EvidencePiece(
                "structure", "H1", "bos",
                f"BOS {structure.last_bos.kind} — break of structure",
                direction, 72.0,
            ))
        if structure.last_choch is not None:
            out.append(EvidencePiece(
                "structure", "H1", "mss",
                f"CHoCH — market structure shift",
                "neutral", 68.0,
            ))
        if structure.higher_lows and direction == "bullish":
            out.append(EvidencePiece(
                "structure", "H1", "pullback",
                "Higher lows — bullish pullback zone", "bullish", 65.0,
            ))
        elif structure.lower_highs and direction == "bearish":
            out.append(EvidencePiece(
                "structure", "H1", "pullback",
                "Lower highs — bearish pullback zone", "bearish", 65.0,
            ))
        if structure.support_zones or structure.resistance_zones:
            out.append(EvidencePiece(
                "structure", "H1", "sr_zones",
                "Support/resistance zones mapped", direction, 58.0,
            ))
        for tf in ("M15", "M5"):
            frame = candles.get(tf)
            if frame is None or len(frame) < 5:
                continue
            m = _frame_metrics(frame, symbol)
            if structure.last_bos and abs(m["momentum"]) < 3.0:
                out.append(EvidencePiece(
                    "structure", tf, "continuation",
                    f"{tf} pullback after BOS — continuation zone",
                    direction, 70.0,
                ))
        return out

    def _collect_liquidity(
        self,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext | None,
    ) -> list[EvidencePiece]:
        out: list[EvidencePiece] = []
        for tf in ("M15", "M5", "M1"):
            frame = candles.get(tf)
            if frame is None or len(frame) < 3:
                continue
            m = _frame_metrics(frame, symbol)
            if m["rejection"] and structure and structure.liquidity_zones:
                out.append(EvidencePiece(
                    "liquidity", tf, "sweep",
                    f"{tf} liquidity sweep with rejection", "neutral", 74.0,
                ))
            elif m["rejection"] and m["range_ratio"] > 1.1:
                out.append(EvidencePiece(
                    "liquidity", tf, "failed_breakout",
                    f"{tf} failed breakout — stop hunt", "neutral", 66.0,
                ))
            elif m["vol_ratio"] > 1.3 and m["body"] < m.get("full_range", 1) * 0.3:
                out.append(EvidencePiece(
                    "liquidity", tf, "absorption",
                    f"{tf} absorption at level", "neutral", 62.0,
                ))
        if structure and structure.liquidity_zones:
            out.append(EvidencePiece(
                "liquidity", "H1", "pools",
                "Liquidity pools mapped — watch for sweeps", "neutral", 55.0,
            ))
        return out

    def _collect_volume(self, symbol: str, candles: dict[str, pd.DataFrame]) -> list[EvidencePiece]:
        out: list[EvidencePiece] = []
        for tf in ("M15", "H1", "H4"):
            frame = candles.get(tf)
            if frame is None or len(frame) < 10:
                continue
            vol = frame["tick_volume"].astype(float).values
            ratio = vol[-5:].mean() / max(vol[-15:-5].mean(), 1.0)
            m = _frame_metrics(frame, symbol)
            direction = "bullish" if m["momentum"] > 0 else (
                "bearish" if m["momentum"] < 0 else "neutral"
            )
            if ratio > 1.3:
                out.append(EvidencePiece(
                    "volume", tf, "spike",
                    f"{tf} participation spike", direction, min(100.0, 50 + ratio * 20),
                ))
            elif ratio < 0.75:
                out.append(EvidencePiece(
                    "volume", tf, "quiet",
                    f"{tf} quiet accumulation", direction, 55.0,
                ))
            else:
                out.append(EvidencePiece(
                    "volume", tf, "steady",
                    f"{tf} steady participation", direction, 50.0,
                ))
            if ratio > 1.2 and m["momentum"] > 1.0:
                out.append(EvidencePiece(
                    "volume", tf, "buying_pressure",
                    f"{tf} buying pressure", "bullish", 68.0,
                ))
            elif ratio > 1.2 and m["momentum"] < -1.0:
                out.append(EvidencePiece(
                    "volume", tf, "selling_pressure",
                    f"{tf} selling pressure", "bearish", 68.0,
                ))
        return out

    def _collect_candlestick(
        self, symbol: str, candles: dict[str, pd.DataFrame]
    ) -> list[EvidencePiece]:
        out: list[EvidencePiece] = []
        for tf in ("M1", "M5", "M15"):
            frame = candles.get(tf)
            if frame is None or len(frame) < 3:
                continue
            opens = frame["open"].astype(float).values
            closes = frame["close"].astype(float).values
            highs = frame["high"].astype(float).values
            lows = frame["low"].astype(float).values
            body = abs(closes[-1] - opens[-1])
            full_range = max(highs[-1] - lows[-1], pip_size_for_symbol(symbol) * 0.1)
            wick_upper = highs[-1] - max(closes[-1], opens[-1])
            wick_lower = min(closes[-1], opens[-1]) - lows[-1]

            if len(closes) >= 2:
                prev_body = abs(closes[-2] - opens[-2])
                if closes[-1] > opens[-1] and closes[-2] < opens[-2] and body > prev_body * 1.1:
                    out.append(EvidencePiece(
                        "candlestick", tf, "engulfing",
                        f"{tf} bullish engulfing", "bullish", 78.0,
                    ))
                elif closes[-1] < opens[-1] and closes[-2] > opens[-2] and body > prev_body * 1.1:
                    out.append(EvidencePiece(
                        "candlestick", tf, "bearish_engulfing",
                        f"{tf} bearish engulfing", "bearish", 78.0,
                    ))
            if body < full_range * 0.35 and (wick_upper > body * 2 or wick_lower > body * 2):
                direction = "bearish" if wick_upper > wick_lower else "bullish"
                out.append(EvidencePiece(
                    "candlestick", tf, "pin_bar",
                    f"{tf} pin bar rejection", direction, 76.0,
                ))
            elif wick_upper > body * 1.8 or wick_lower > body * 1.8:
                out.append(EvidencePiece(
                    "candlestick", tf, "rejection",
                    f"{tf} wick rejection", "neutral", 72.0,
                ))
            if body > full_range * 0.65:
                direction = "bullish" if closes[-1] > opens[-1] else "bearish"
                out.append(EvidencePiece(
                    "candlestick", tf, "momentum",
                    f"{tf} momentum candle", direction, 68.0,
                ))
            if len(closes) >= 2:
                if highs[-1] <= highs[-2] and lows[-1] >= lows[-2]:
                    out.append(EvidencePiece(
                        "candlestick", tf, "inside_bar",
                        f"{tf} inside bar — compression", "neutral", 58.0,
                    ))
                elif highs[-1] > highs[-2] and lows[-1] < lows[-2]:
                    out.append(EvidencePiece(
                        "candlestick", tf, "outside_bar",
                        f"{tf} outside bar — expansion", "neutral", 64.0,
                    ))
        return out

    def _collect_session(
        self,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        evaluation_moment: datetime | None,
    ) -> list[EvidencePiece]:
        hour = evaluation_moment.hour if evaluation_moment else 12
        session = infer_session(hour)
        out: list[EvidencePiece] = []
        m15 = candles.get("M15")
        if m15 is not None and len(m15) >= 5:
            m = _frame_metrics(m15, symbol)
            if session in {"london", "london_ny_overlap"} and m["range_ratio"] > 1.1:
                out.append(EvidencePiece(
                    "session", "M15", "london_expansion",
                    "London session expansion", "neutral", 67.0,
                ))
            elif session == "new_york" and m["range_ratio"] > 1.0:
                direction = "bullish" if m["momentum"] > 0 else "bearish"
                out.append(EvidencePiece(
                    "session", "M15", "ny_continuation",
                    f"NY session {direction} continuation", direction, 65.0,
                ))
            elif session == "asian" and m["range_ratio"] < 0.75:
                out.append(EvidencePiece(
                    "session", "M15", "asian_compression",
                    "Asian session compression", "neutral", 58.0,
                ))
            elif session in {"london_ny_overlap", "new_york"}:
                out.append(EvidencePiece(
                    "session", "M15", "transition",
                    "Session transition — watch for momentum", "neutral", 60.0,
                ))
        return out

    def _collect_momentum(
        self,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        bias: MultiTimeframeBiasResult | None,
    ) -> list[EvidencePiece]:
        out: list[EvidencePiece] = []
        for tf in ("H1", "M15", "M5"):
            frame = candles.get(tf)
            if frame is None or len(frame) < 8:
                continue
            m = _frame_metrics(frame, symbol)
            direction = "bullish" if m["momentum"] > 0 else (
                "bearish" if m["momentum"] < 0 else "neutral"
            )
            if len(frame) >= 16:
                prior_mom = (frame["close"].astype(float).values[-8] -
                             frame["close"].astype(float).values[-16]) / m.get("pip", 0.0001)
                if abs(m["momentum"]) > abs(prior_mom) * 1.3:
                    out.append(EvidencePiece(
                        "momentum", tf, "acceleration",
                        f"{tf} momentum accelerating", direction, 70.0,
                    ))
                elif abs(m["momentum"]) < abs(prior_mom) * 0.6:
                    out.append(EvidencePiece(
                        "momentum", tf, "deceleration",
                        f"{tf} momentum decelerating", direction, 62.0,
                    ))
            if m["vol_ratio"] > 1.4 and abs(m["momentum"]) < 2.0:
                out.append(EvidencePiece(
                    "momentum", tf, "exhaustion",
                    f"{tf} momentum exhaustion", direction, 68.0,
                ))
            if bias and bias.bias != "neutral":
                bias_sign = 1 if bias.bias == "bullish" else -1
                if m["momentum"] * bias_sign < -2:
                    out.append(EvidencePiece(
                        "momentum", tf, "divergence",
                        f"{tf} momentum diverging from {bias.bias} bias",
                        "neutral", 65.0,
                    ))
        return out

    def _collect_timeframe(
        self,
        symbol: str,
        candles: dict[str, pd.DataFrame],
        structure: MarketContext | None,
        bias: MultiTimeframeBiasResult | None,
    ) -> list[EvidencePiece]:
        out: list[EvidencePiece] = []
        layer_map = {
            "H8": ("context", "H8/H4 macro context"),
            "H4": ("context", "H4 directional context"),
            "H1": ("development", "H1 story development"),
            "M15": ("opportunity", "M15 opportunity zone"),
            "M5": ("opportunity", "M5 entry opportunity"),
            "M1": ("execution", "M1 execution timing"),
        }
        for tf, (role, label) in layer_map.items():
            frame = candles.get(tf)
            if frame is None or len(frame) < 3:
                continue
            m = _frame_metrics(frame, symbol)
            direction = structure.trend if structure else (
                "bullish" if m["momentum"] > 0 else "bearish" if m["momentum"] < 0 else "neutral"
            )
            out.append(EvidencePiece(
                "timeframe", tf, role,
                f"{label}: {direction} ({tf})", direction, 50.0 + min(30.0, abs(m["momentum"]) * 3),
            ))
        return out

    @staticmethod
    def _collect_evolution(state: NestedStoryState) -> list[EvidencePiece]:
        out: list[EvidencePiece] = []
        direction = "bullish" if state.macro_story in {
            "bullish_campaign", "accumulation", "expansion"
        } else (
            "bearish" if state.macro_story in {
                "bearish_campaign", "distribution", "exhaustion"
            } else "neutral"
        )
        out.append(EvidencePiece(
            "evolution", "H4", state.macro_story,
            f"Evolution novel: {state.macro_story}", direction, state.novel.confidence,
        ))
        out.append(EvidencePiece(
            "evolution", "H1", state.chapter_story,
            f"Evolution chapter: {state.chapter_story}", direction, state.chapter.confidence,
        ))
        if state.conflict:
            out.append(EvidencePiece(
                "evolution", "multi", "conflict",
                f"Nested layers in conflict — alignment {state.alignment}",
                "neutral", 55.0,
            ))
        if state.transition:
            out.append(EvidencePiece(
                "evolution", "multi", "transition",
                f"Story transition — probable {state.probable_evolution}",
                "neutral", 60.0,
            ))
        return out

    def _synthesise_from_pieces(
        self,
        symbol: str,
        pieces: list[EvidencePiece],
        evolution_state: NestedStoryState | None,
    ) -> MarketStorySummary:
        if len(pieces) < MIN_EVIDENCE_PIECES:
            return self._unclear_summary(
                symbol, pieces, "insufficient",
                "Insufficient evidence across timeframes to form a market story.",
            )

        noise_score = self._noise_score(pieces)
        if noise_score > 0.72:
            return self._unclear_summary(
                symbol, pieces, "random",
                "Random noise dominates — no actionable structure visible.",
            )

        bull_weight = sum(p.strength for p in pieces if p.direction == "bullish")
        bear_weight = sum(p.strength for p in pieces if p.direction == "bearish")
        neutral_weight = sum(p.strength for p in pieces if p.direction == "neutral")
        total = bull_weight + bear_weight + neutral_weight
        if total <= 0:
            return self._unclear_summary(
                symbol, pieces, "incoherent",
                "Evidence present but directionally incoherent.",
            )

        bull_pct = bull_weight / total
        bear_pct = bear_weight / total
        dominant = "bullish" if bull_pct > bear_pct and bull_pct > 0.35 else (
            "bearish" if bear_pct > bull_pct and bear_pct > 0.35 else "neutral"
        )

        supporting: list[str] = []
        contradicting: list[str] = []
        for p in pieces:
            label = f"[{p.category}/{p.timeframe}] {p.description}"
            if p.direction == dominant or p.direction == "neutral":
                supporting.append(label)
            elif dominant != "neutral":
                contradicting.append(label)

        has_conflict = len(contradicting) >= 2 and dominant != "neutral"
        avg_strength = sum(p.strength for p in pieces) / len(pieces)
        confidence = min(100.0, avg_strength + (10 if not has_conflict else 5))

        what, why, next_event, action = self._build_narrative(
            dominant, pieces, has_conflict, contradicting, evolution_state,
        )

        if not what or confidence < 25.0:
            return self._unclear_summary(
                symbol, pieces, "incoherent",
                "Evidence does not combine into a coherent explanation.",
            )

        allocation_bias = self._allocation_bias(pieces, dominant, confidence, has_conflict)
        risk_level = self._risk_level(has_conflict, confidence, pieces)
        opportunity_hint = self._opportunity_hint(pieces)

        explanation = f"{what} {why}".strip()
        return MarketStorySummary(
            symbol=symbol,
            current_explanation=explanation,
            supporting_evidence=tuple(supporting[:12]),
            contradicting_evidence=tuple(contradicting[:8]),
            confidence=confidence,
            probable_next_event=next_event,
            recommended_action=action,
            risk_level=risk_level,
            allocation_bias=allocation_bias,
            story_clear=True,
            unclear_reason="",
            dominant_direction=dominant,
            opportunity_hint=opportunity_hint,
        )

    def _unclear_summary(
        self,
        symbol: str,
        pieces: list[EvidencePiece],
        reason: UnclearReason,
        explanation: str,
    ) -> MarketStorySummary:
        supporting = tuple(
            f"[{p.category}/{p.timeframe}] {p.description}" for p in pieces[:8]
        )
        return MarketStorySummary(
            symbol=symbol,
            current_explanation=explanation,
            supporting_evidence=supporting,
            contradicting_evidence=(),
            confidence=max(20.0, sum(p.strength for p in pieces) / max(len(pieces), 1) * 0.5),
            probable_next_event="Wait for clearer evidence",
            recommended_action="Observe — no trade until story clarifies",
            risk_level="high",
            allocation_bias="scout",
            story_clear=False,
            unclear_reason=reason,
            dominant_direction="neutral",
            opportunity_hint=None,
        )

    @staticmethod
    def _noise_score(pieces: list[EvidencePiece]) -> float:
        neutral_count = sum(1 for p in pieces if p.direction == "neutral")
        weak_count = sum(1 for p in pieces if p.strength < 45)
        compression = sum(1 for p in pieces if "compression" in p.signal or "inside_bar" in p.signal)
        n = len(pieces)
        if n == 0:
            return 1.0
        return (neutral_count * 0.4 + weak_count * 0.3 + compression * 0.2) / n

    @staticmethod
    def _build_narrative(
        dominant: str,
        pieces: list[EvidencePiece],
        has_conflict: bool,
        contradicting: list[str],
        evolution_state: NestedStoryState | None,
    ) -> tuple[str, str, str, str]:
        categories = {p.category for p in pieces}
        liquidity = any(p.category == "liquidity" for p in pieces)
        compression = any("compression" in p.signal for p in pieces)
        exhaustion = any("exhaustion" in p.signal for p in pieces)

        if has_conflict:
            contra_tf = contradicting[0].split("/")[1].split("]")[0] if contradicting else "lower TF"
            what = (
                f"The asset is in a {dominant} macro move under pressure — "
                f"conflicting signals from {contra_tf} suggest a corrective phase."
            )
            why = (
                "Higher timeframe context remains directional while lower timeframe "
                "evidence shows absorption or counter-momentum — buyers/sellers testing control."
            )
            next_event = (
                f"Likely resolution: {dominant} continuation if absorption holds, "
                f"or deeper pullback if rejection strengthens."
            )
            action = f"Trade with reduced size — favour {dominant} on confirmation."
        elif compression:
            what = f"Price is coiling in compression with {dominant} bias building."
            why = "Range contraction and quiet volume indicate energy accumulation before expansion."
            next_event = "Breakout or liquidity sweep from the compression range."
            action = "Prepare for compression breakout — scout entry on expansion candle."
        elif liquidity:
            what = f"Liquidity event detected — {dominant} context with sweep/rejection pattern."
            why = "Stop hunt or pool sweep followed by rejection suggests institutional defence."
            next_event = "Mean reversion or continuation after liquidity grab completes."
            action = "Harvest liquidity sweep fade or continuation on retest."
        elif exhaustion:
            what = f"Momentum exhaustion in a {dominant} move — climax without follow-through."
            why = "Volume spike with decelerating momentum signals potential pause or reversal."
            next_event = "Pullback or range formation before next directional leg."
            action = "Scale into harvest on snapback — avoid chasing."
        else:
            what = f"Asset trending {dominant} with aligned multi-timeframe evidence."
            why = (
                f"Trend, structure, and momentum categories ({len(categories)} active) "
                f"support a single directional read."
            )
            next_event = f"Continuation in {dominant} direction on next session impulse."
            action = f"Execute {dominant} opportunity — proper or harvest tier."

        if evolution_state is not None and evolution_state.transition:
            next_event = (
                f"{next_event} Evolution suggests {evolution_state.probable_evolution}."
            )

        return what, why, next_event, action

    @staticmethod
    def _allocation_bias(
        pieces: list[EvidencePiece],
        dominant: str,
        confidence: float,
        has_conflict: bool,
    ) -> AllocationBias:
        if has_conflict:
            return "scout" if confidence < 60 else "harvest"
        m1_strike = any(p.timeframe == "M1" and p.category == "candlestick" for p in pieces)
        liquidity = any(p.category == "liquidity" for p in pieces)
        compression = any("compression" in p.signal for p in pieces)
        if m1_strike and confidence >= 70:
            return "micro"
        if liquidity or compression:
            return "harvest"
        if confidence >= 75 and dominant != "neutral":
            return "proper"
        if confidence >= 85:
            return "elite"
        if confidence < 45:
            return "scout"
        return "harvest"

    @staticmethod
    def _risk_level(
        has_conflict: bool, confidence: float, pieces: list[EvidencePiece]
    ) -> RiskLevel:
        if has_conflict:
            return "medium" if confidence >= 55 else "high"
        exhaustion = any("exhaustion" in p.signal for p in pieces)
        if exhaustion:
            return "medium"
        if confidence >= 65:
            return "low"
        return "medium"

    @staticmethod
    def _opportunity_hint(pieces: list[EvidencePiece]) -> str | None:
        priority = (
            ("liquidity", "sweep", "liquidity_sweep"),
            ("liquidity", "failed_breakout", "failed_breakout"),
            ("structure", "continuation", "pullback_continuation"),
            ("structure", "bos", "breakout_retest"),
            ("candlestick", "engulfing", "pullback_continuation"),
            ("session", "london_expansion", "session_transition"),
            ("momentum", "exhaustion", "mean_reversion_snapback"),
        )
        for cat, sig, hint in priority:
            for p in pieces:
                if p.category == cat and (sig in p.signal or sig in p.description.lower()):
                    return hint
        compression = any("compression" in p.signal for p in pieces)
        if compression:
            return "compression_breakout"
        return None

    def record_opportunity_recovered(self) -> None:
        self.stats.opportunities_recovered += 1

    def write_evidence_synthesis_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (self.project_root / "logs" / "evidence_synthesis_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Evidence Synthesis Report",
            "",
            f"**Generated:** {now}",
            "",
            "Evidence combinations synthesised into single market stories.",
            "",
            f"- Total synthesised: **{self.stats.synthesised}**",
            f"- Story clear: **{self.stats.story_clear}**",
            f"- Conflicts interpreted: **{self.stats.conflicts_interpreted}**",
            "",
        ]
        for symbol in sorted(self._latest):
            s = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Clear:** {'YES' if s.story_clear else 'NO'} ({s.unclear_reason or '—'})",
                f"**Confidence:** {s.confidence:.0f}% | **Bias:** {s.allocation_bias} | **Risk:** {s.risk_level}",
                "",
                f"**Explanation:** {s.current_explanation}",
                "",
                f"**Next:** {s.probable_next_event}",
                "",
                f"**Action:** {s.recommended_action}",
                "",
            ])
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_market_story_explanation_report(self, path: Path | None = None) -> Path | None:
        if not self._latest or self.project_root is None:
            return None
        report_path = path or (
            self.project_root / "logs" / "market_story_explanation_report.md"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Market Story Explanation Report",
            "",
            f"**Generated:** {now}",
            "",
            "Supporting vs contradicting evidence for each synthesised story.",
            "",
        ]
        for symbol in sorted(self._latest):
            s = self._latest[symbol]
            lines.extend([
                f"## {symbol}",
                "",
                f"**Explanation:** {s.current_explanation}",
                "",
                "### Supporting",
                "",
            ])
            for item in s.supporting_evidence:
                lines.append(f"- {item}")
            if not s.supporting_evidence:
                lines.append("- (none)")
            lines.extend(["", "### Contradicting", ""])
            for item in s.contradicting_evidence:
                lines.append(f"- {item}")
            if not s.contradicting_evidence:
                lines.append("- (none)")
            lines.append("")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_story_unclear_root_cause_report(self, path: Path | None = None) -> Path | None:
        if self.project_root is None:
            return None
        report_path = path or (
            self.project_root / "logs" / "story_unclear_root_cause_report.md"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        total = self.stats.story_unclear
        lines = [
            "# Story Unclear Root Cause Report",
            "",
            f"**Generated:** {now}",
            "",
            "Why each unclear story was rejected — only insufficient/incoherent/random.",
            "",
            "## Summary",
            "",
            f"- Total unclear: **{total}**",
            f"- Insufficient evidence: **{self.stats.unclear_insufficient}**",
            f"- Incoherent: **{self.stats.unclear_incoherent}**",
            f"- Random noise: **{self.stats.unclear_random}**",
            f"- Conflicts interpreted (not rejected): **{self.stats.conflicts_interpreted}**",
            "",
            "## Recent unclear cases",
            "",
            "| Symbol | Reason | Explanation |",
            "|--------|--------|-------------|",
        ]
        unclear = [
            (sym, s) for sym, s in reversed(self._history)
            if not s.story_clear
        ][:100]
        for sym, s in unclear:
            lines.append(
                f"| {sym} | {s.unclear_reason} | {s.current_explanation[:60]} |"
            )
        if not unclear:
            lines.append("| — | — | — |")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def write_all_reports(self) -> tuple[Path | None, Path | None, Path | None]:
        return (
            self.write_evidence_synthesis_report(),
            self.write_market_story_explanation_report(),
            self.write_story_unclear_root_cause_report(),
        )


def _frame_metrics(frame: pd.DataFrame, symbol: str) -> dict:
    closes = frame["close"].astype(float).values
    highs = frame["high"].astype(float).values
    lows = frame["low"].astype(float).values
    volumes = (
        frame["tick_volume"].astype(float).values
        if "tick_volume" in frame.columns
        else np.ones(len(closes))
    )
    pip = pip_size_for_symbol(symbol)
    recent_range = (highs[-8:].max() - lows[-8:].min()) / pip
    prior_range = (
        (highs[-20:-8].max() - lows[-20:-8].min()) / pip
        if len(closes) >= 20
        else recent_range
    )
    range_ratio = recent_range / max(prior_range, 0.1)
    vol_recent = volumes[-5:].mean()
    vol_prior = volumes[-15:-5].mean() if len(volumes) >= 15 else vol_recent
    vol_ratio = vol_recent / max(vol_prior, 1.0)
    momentum = (closes[-1] - closes[-8]) / pip if len(closes) >= 8 else 0.0
    opens = frame["open"].astype(float).values
    body = abs(closes[-1] - opens[-1])
    full_range = max(highs[-1] - lows[-1], pip * 0.1)
    wick_upper = highs[-1] - max(closes[-1], opens[-1])
    wick_lower = min(closes[-1], opens[-1]) - lows[-1]
    rejection = wick_upper > body * 1.5 or wick_lower > body * 1.5
    return {
        "range_ratio": range_ratio,
        "vol_ratio": vol_ratio,
        "momentum": momentum,
        "rejection": rejection,
        "body": body,
        "full_range": full_range,
        "wick_upper": wick_upper,
        "wick_lower": wick_lower,
        "pip": pip,
    }
