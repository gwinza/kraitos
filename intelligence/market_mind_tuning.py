"""V5 Market Mind tuning — confidence maps to allocation, not automatic stand-aside."""

from __future__ import annotations

from intelligence.picture_models import DepartmentContribution, MarketPicture, ParticipationMode

# --- Picture fusion ---
FUSION_CLEAR_MIN_CONF = 58.0
FUSION_CLEAR_MAX_CONTRADICTION_RATIO = 0.42
FUSION_INCOMPLETE_MIN_CONF = 44.0
FUSION_INCOMPLETE_MAX_CONTRADICTION_RATIO = 0.62
FUSION_COHERENT_MAX_CONTRADICTION_RATIO = 0.48
DOMINANT_SIDE_MARGIN = 12.0
KEY_EVIDENCE_MIN_CONF = 58.0
NOISE_MAX_CONF = 48.0

# --- Confidence blending (picture + story + CIO + strategy fit) ---
PICTURE_CONF_WEIGHT = 0.50
STORY_CONF_WEIGHT = 0.25
CIO_CONF_WEIGHT = 0.15
STRATEGY_FIT_WEIGHT = 0.10
STRATEGY_FIT_BOOST_THRESHOLD = 72.0
STRATEGY_FIT_MAX_BOOST = 8.0

# --- Participation tiers: less certainty → smaller size, not no trade ---
ALLOCATION_BY_CONFIDENCE: tuple[tuple[float, ParticipationMode, float], ...] = (
    (92.0, "scale_in", 1.0),
    (82.0, "trade", 0.85),
    (72.0, "trade", 0.65),
    (62.0, "probe", 0.40),
    (52.0, "probe", 0.22),
    (42.0, "wait", 0.12),
    (0.0, "stand_aside", 0.0),
)

# Conflicted pictures may still probe when the story has a side and confidence holds.
CONFLICTED_PROBE_MIN_CONF = 52.0
CONFLICTED_PROBE_ALLOCATION = 0.18

# Thesis can form on incomplete pictures when coherence + side + strategy align.
THESIS_MIN_ALLOCATION = 0.12
THESIS_INCOMPLETE_MIN_CONF = 50.0
THESIS_STRATEGY_FIT_MIN = 68.0
THESIS_INCOMPLETE_STRATEGY_FIT_MIN = 74.0

# Evidence-change sensitivity for mind_state transitions.
EVIDENCE_CHANGE_CONF_DELTA = 10.0


def weighted_department_confidence(departments: tuple[DepartmentContribution, ...]) -> float:
    """Weight higher-confidence departments more — key evidence matters most."""
    if not departments:
        return 0.0
    weighted = 0.0
    total = 0.0
    for dept in departments:
        w = 1.0 + (dept.confidence / 100.0)
        if dept.confidence >= KEY_EVIDENCE_MIN_CONF:
            w += 0.25
        weighted += dept.confidence * w
        total += w
    return round(weighted / max(total, 0.01), 2)


def blended_confidence(
    *,
    picture_confidence: float,
    story_confidence: float,
    cio_confidence: float = 0.0,
    strategy_fit: float = 0.0,
) -> float:
    """Blend department picture confidence with story, CIO, and strategy fit."""
    score = (
        picture_confidence * PICTURE_CONF_WEIGHT
        + story_confidence * STORY_CONF_WEIGHT
        + cio_confidence * CIO_CONF_WEIGHT
    )
    if strategy_fit > 0:
        score += strategy_fit * STRATEGY_FIT_WEIGHT
        if strategy_fit >= STRATEGY_FIT_BOOST_THRESHOLD:
            score += min(
                STRATEGY_FIT_MAX_BOOST,
                (strategy_fit - STRATEGY_FIT_BOOST_THRESHOLD) * 0.4,
            )
    return min(100.0, round(score, 2))


def participation_from_confidence(
    confidence: float,
    picture: MarketPicture,
    *,
    hard_blocked: bool,
) -> tuple[ParticipationMode, float]:
    """
    Map understanding confidence to participation mode and allocation.

    Conflicted pictures probe rather than stand aside when confidence holds.
    """
    if hard_blocked:
        return "stand_aside", 0.0

    if picture.clarity == "conflicted" and confidence >= CONFLICTED_PROBE_MIN_CONF:
        if picture.dominant_side != "neutral":
            return "probe", CONFLICTED_PROBE_ALLOCATION

    for threshold, mode, mult in ALLOCATION_BY_CONFIDENCE:
        if confidence >= threshold:
            if picture.clarity == "incomplete" and mode in {"trade", "scale_in"}:
                return "probe", min(mult, 0.55)
            if picture.clarity == "conflicted" and mult > CONFLICTED_PROBE_ALLOCATION:
                return "probe", CONFLICTED_PROBE_ALLOCATION
            return mode, mult

    return "stand_aside", 0.0


def thesis_is_clear(
    *,
    picture: MarketPicture,
    side: str,
    participation: ParticipationMode,
    allocation: float,
    strategy_fit: float,
    hard_blocked: bool,
) -> bool:
    """Thesis is clear when understanding supports a professional expression of the view."""
    if hard_blocked or side not in {"buy", "sell"}:
        return False
    if participation == "stand_aside" or allocation < THESIS_MIN_ALLOCATION:
        return False

    if picture.professional_thesis_supported:
        return True

    if (
        picture.clarity == "incomplete"
        and picture.coherent_story
        and picture.dominant_side != "neutral"
        and picture.confidence >= THESIS_INCOMPLETE_MIN_CONF
        and strategy_fit >= THESIS_INCOMPLETE_STRATEGY_FIT_MIN
        and allocation >= 0.20
    ):
        return True

    if (
        picture.clarity == "conflicted"
        and confidence_allows_conflict_probe(picture, strategy_fit)
        and allocation >= CONFLICTED_PROBE_ALLOCATION
    ):
        return True

    return False


def confidence_allows_conflict_probe(picture: MarketPicture, strategy_fit: float) -> bool:
    """Some regime contradictions are normal — probe when strategy fit is strong."""
    return (
        picture.dominant_side != "neutral"
        and picture.confidence >= CONFLICTED_PROBE_MIN_CONF
        and strategy_fit >= THESIS_STRATEGY_FIT_MIN
    )


def clarity_from_metrics(
    *,
    avg_conf: float,
    contradiction_ratio: float,
    dominant_side: str,
    coherent: bool,
) -> tuple[str, bool, bool, str]:
    """
    Derive picture clarity, coherence, and thesis support from fused metrics.

    Returns: clarity, coherent_story, thesis_supported, reason_not_clear
    """
    if (
        avg_conf >= FUSION_CLEAR_MIN_CONF
        and contradiction_ratio <= FUSION_CLEAR_MAX_CONTRADICTION_RATIO
        and dominant_side != "neutral"
    ):
        return "clear", True, True, ""

    if avg_conf >= FUSION_INCOMPLETE_MIN_CONF and contradiction_ratio <= FUSION_INCOMPLETE_MAX_CONTRADICTION_RATIO:
        coherent_story = contradiction_ratio <= FUSION_COHERENT_MAX_CONTRADICTION_RATIO
        thesis_supported = coherent_story and dominant_side != "neutral"
        reason = "" if thesis_supported else "Picture incomplete — awaiting alignment"
        return "incomplete", coherent_story, thesis_supported, reason

    if (
        dominant_side != "neutral"
        and avg_conf >= CONFLICTED_PROBE_MIN_CONF
        and contradiction_ratio <= 0.72
    ):
        return (
            "conflicted",
            False,
            False,
            "Tension present — probe only if strategy fit supports the story",
        )

    return (
        "conflicted",
        False,
        False,
        "Conflicting department evidence — reduce size or observe",
    )
