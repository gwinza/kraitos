"""
SemanticMemory: Store timeless market knowledge.

This is NOT trade history.
It is permanent market knowledge.

Examples:
- "Higher real yields usually pressure gold."
- "Risk-off environments often strengthen USD and CHF."
- "Interest rate expectations move currencies."
- "Liquidity seeks liquidity."

Facts are not opinions.
Facts must be explainable.
Facts must be versioned.
Facts can become obsolete.
Never store trading signals.
Store market truths.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class KnowledgeFact:
    """
    A permanent fact about market behavior.

    Attributes
    ----------
    id : str
        Unique identifier for this fact (UUID).
    title : str
        Short, memorable title of the fact.
    description : str
        Detailed explanation of the fact.
    category : str
        Category (e.g., "yield", "currency", "liquidity", "volatility", "structure").
    source : str
        Where this fact was learned or verified.
    confidence : float
        How confident we are in this fact [0.0, 1.0].
    tags : list[str]
        Tags for categorization and search.
    created : datetime
        When this fact was added to semantic memory.
    last_verified : datetime
        When this fact was last confirmed in real markets.
    verification_count : int
        How many times this fact has been verified.
    is_active : bool
        Whether this fact is currently considered valid.
    obsolescence_notes : str
        Notes on why this fact may be becoming obsolete.
    related_facts : list[str]
        IDs of related facts.
    counter_examples : list[str]
        Known exceptions or counter-examples to this fact.
    context : str
        Context in which this fact applies (e.g., "trending markets", "low liquidity").
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    category: str = ""
    source: str = ""
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)
    created: datetime = field(default_factory=datetime.now)
    last_verified: datetime = field(default_factory=datetime.now)
    verification_count: int = 0
    is_active: bool = True
    obsolescence_notes: str = ""
    related_facts: list[str] = field(default_factory=list)
    counter_examples: list[str] = field(default_factory=list)
    context: str = ""

    def __post_init__(self) -> None:
        """Validate the fact on creation."""
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}."
            )

        if not self.title:
            raise ValueError("title cannot be empty.")

        if not self.description:
            raise ValueError("description cannot be empty.")

        if not self.category:
            raise ValueError("category cannot be empty.")

    def __str__(self) -> str:
        """Return a human-readable representation."""
        status = "active" if self.is_active else "inactive"
        return (
            f"KnowledgeFact({self.title}, "
            f"confidence={self.confidence:.1%}, "
            f"verified={self.verification_count}x, "
            f"status={status})"
        )

    def is_stale(self, days_threshold: int = 90) -> bool:
        """Check if this fact hasn't been verified recently."""
        days_since_verification = (datetime.now() - self.last_verified).days
        return days_since_verification > days_threshold

    def mark_verified(self) -> None:
        """Mark this fact as verified today."""
        self.last_verified = datetime.now()
        self.verification_count += 1


class SemanticMemory:
    """
    Store and manage permanent market knowledge.

    The SemanticMemory stores facts about how markets work, not trading signals.
    Facts are versioned, can be marked obsolete, and are verified over time.

    This is the permanent knowledge base that informs all analysis.
    """

    # Valid categories
    VALID_CATEGORIES = {
        "yield",
        "currency",
        "liquidity",
        "volatility",
        "structure",
        "participation",
        "correlation",
        "regime",
        "macro",
        "central_bank",
        "risk_sentiment",
    }

    def __init__(self) -> None:
        """Initialize the SemanticMemory."""
        self.facts: dict[str, KnowledgeFact] = {}
        self.category_index: dict[str, list[str]] = {}
        self.tag_index: dict[str, list[str]] = {}
        self._initialize_core_facts()

    def add_fact(
        self,
        title: str,
        description: str,
        category: str,
        source: str,
        confidence: float = 0.7,
        tags: Optional[list[str]] = None,
        context: str = "",
    ) -> KnowledgeFact:
        """
        Add a new fact to semantic memory.

        Parameters
        ----------
        title : str
            Short title of the fact.
        description : str
            Detailed explanation.
        category : str
            Category from VALID_CATEGORIES.
        source : str
            Where this fact comes from.
        confidence : float, optional
            Confidence [0.0, 1.0]. Default: 0.7.
        tags : list[str], optional
            Tags for categorization.
        context : str, optional
            Context where fact applies.

        Returns
        -------
        KnowledgeFact
            The created fact.

        Raises
        ------
        ValueError
            If category is not valid or confidence is out of range.
        """
        if category not in self.VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category: {category}. Must be one of: "
                f"{', '.join(sorted(self.VALID_CATEGORIES))}"
            )

        if not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {confidence}."
            )

        fact = KnowledgeFact(
            title=title,
            description=description,
            category=category,
            source=source,
            confidence=confidence,
            tags=tags or [],
            context=context,
        )

        self.facts[fact.id] = fact

        # Update indices
        self._update_category_index(fact.id, category)
        self._update_tag_index(fact.id, tags or [])

        return fact

    def remove_fact(self, fact_id: str) -> bool:
        """
        Remove a fact from semantic memory.

        Parameters
        ----------
        fact_id : str
            ID of the fact to remove.

        Returns
        -------
        bool
            True if fact was removed, False if not found.
        """
        if fact_id not in self.facts:
            return False

        fact = self.facts[fact_id]

        # Remove from indices
        if fact.category in self.category_index:
            self.category_index[fact.category].remove(fact_id)

        for tag in fact.tags:
            if tag in self.tag_index:
                self.tag_index[tag].remove(fact_id)

        del self.facts[fact_id]
        return True

    def update_fact(
        self,
        fact_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        confidence: Optional[float] = None,
        is_active: Optional[bool] = None,
        obsolescence_notes: Optional[str] = None,
    ) -> bool:
        """
        Update an existing fact.

        Parameters
        ----------
        fact_id : str
            ID of the fact to update.
        title : str, optional
            New title.
        description : str, optional
            New description.
        confidence : float, optional
            New confidence.
        is_active : bool, optional
            Whether fact is still active.
        obsolescence_notes : str, optional
            Notes on why fact may be obsolete.

        Returns
        -------
        bool
            True if fact was updated, False if not found.
        """
        if fact_id not in self.facts:
            return False

        fact = self.facts[fact_id]

        if title is not None:
            fact.title = title

        if description is not None:
            fact.description = description

        if confidence is not None:
            if not (0.0 <= confidence <= 1.0):
                raise ValueError(f"confidence must be between 0.0 and 1.0.")
            fact.confidence = confidence

        if is_active is not None:
            fact.is_active = is_active

        if obsolescence_notes is not None:
            fact.obsolescence_notes = obsolescence_notes

        return True

    def verify_fact(self, fact_id: str) -> bool:
        """
        Mark a fact as verified today.

        Parameters
        ----------
        fact_id : str
            ID of the fact to verify.

        Returns
        -------
        bool
            True if fact was verified, False if not found.
        """
        if fact_id not in self.facts:
            return False

        self.facts[fact_id].mark_verified()
        return True

    def search(self, query: str) -> list[KnowledgeFact]:
        """
        Search facts by title or description.

        Parameters
        ----------
        query : str
            Search query (case-insensitive).

        Returns
        -------
        list[KnowledgeFact]
            Matching facts, ordered by relevance.
        """
        query_lower = query.lower()
        results = []

        for fact in self.facts.values():
            if not fact.is_active:
                continue

            title_match = query_lower in fact.title.lower()
            description_match = query_lower in fact.description.lower()

            if title_match or description_match:
                # Prioritize title matches
                relevance = 2 if title_match else 1
                results.append((relevance, fact))

        # Sort by relevance, then by confidence
        results.sort(key=lambda x: (-x[0], -x[1].confidence))

        return [fact for _, fact in results]

    def find_related(self, fact_id: str, depth: int = 1) -> list[KnowledgeFact]:
        """
        Find facts related to a given fact.

        Parameters
        ----------
        fact_id : str
            ID of the fact to find relatives for.
        depth : int, optional
            How many levels of relationships to traverse.

        Returns
        -------
        list[KnowledgeFact]
            Related facts.
        """
        if fact_id not in self.facts:
            return []

        fact = self.facts[fact_id]
        related = []
        visited = {fact_id}

        # Find facts with same category or tags
        for other_fact in self.facts.values():
            if other_fact.id in visited:
                continue

            # Same category
            if other_fact.category == fact.category:
                related.append(other_fact)
                visited.add(other_fact.id)
                continue

            # Shared tags
            if set(other_fact.tags) & set(fact.tags):
                related.append(other_fact)
                visited.add(other_fact.id)
                continue

            # Shared context
            if other_fact.context and fact.context and other_fact.context in fact.context:
                related.append(other_fact)
                visited.add(other_fact.id)

        # Sort by confidence
        related.sort(key=lambda x: -x.confidence)

        return related[:10]  # Return top 10

    def get_by_category(self, category: str, active_only: bool = True) -> list[KnowledgeFact]:
        """
        Get all facts in a category.

        Parameters
        ----------
        category : str
            Category to retrieve.
        active_only : bool, optional
            Only return active facts. Default: True.

        Returns
        -------
        list[KnowledgeFact]
            Facts in the category, ordered by confidence.
        """
        if category not in self.category_index:
            return []

        fact_ids = self.category_index[category]
        facts = [self.facts[fid] for fid in fact_ids if fid in self.facts]

        if active_only:
            facts = [f for f in facts if f.is_active]

        # Sort by confidence
        facts.sort(key=lambda x: -x.confidence)

        return facts

    def get_stale_facts(self, days_threshold: int = 90) -> list[KnowledgeFact]:
        """
        Get facts that haven't been verified recently.

        Parameters
        ----------
        days_threshold : int, optional
            Days since last verification. Default: 90.

        Returns
        -------
        list[KnowledgeFact]
            Stale facts.
        """
        stale = [f for f in self.facts.values() if f.is_stale(days_threshold)]
        stale.sort(key=lambda x: (x.last_verified, -x.confidence))
        return stale

    def get_summary(self) -> dict:
        """
        Get summary statistics of the semantic memory.

        Returns
        -------
        dict
            Summary statistics.
        """
        active_facts = [f for f in self.facts.values() if f.is_active]
        inactive_facts = [f for f in self.facts.values() if not f.is_active]

        avg_confidence = (
            sum(f.confidence for f in active_facts) / len(active_facts)
            if active_facts
            else 0.0
        )

        total_verifications = sum(f.verification_count for f in active_facts)

        return {
            "total_facts": len(self.facts),
            "active_facts": len(active_facts),
            "inactive_facts": len(inactive_facts),
            "avg_confidence": avg_confidence,
            "total_verifications": total_verifications,
            "categories": dict(
                sorted(
                    [
                        (cat, len(ids))
                        for cat, ids in self.category_index.items()
                        if ids
                    ]
                )
            ),
            "stale_count": len(self.get_stale_facts()),
        }

    def _update_category_index(self, fact_id: str, category: str) -> None:
        """Update category index."""
        if category not in self.category_index:
            self.category_index[category] = []

        self.category_index[category].append(fact_id)

    def _update_tag_index(self, fact_id: str, tags: list[str]) -> None:
        """Update tag index."""
        for tag in tags:
            if tag not in self.tag_index:
                self.tag_index[tag] = []

            self.tag_index[tag].append(fact_id)

    def _initialize_core_facts(self) -> None:
        """Initialize fundamental market facts."""
        # Yield facts
        self.add_fact(
            title="Higher Real Yields Pressure Gold",
            description=(
                "When real interest rates (nominal rates minus inflation expectations) rise, "
                "the opportunity cost of holding non-yielding gold increases. This typically "
                "pressures gold prices lower as investors shift to yield-bearing assets."
            ),
            category="yield",
            source="Market behavior, historical analysis",
            confidence=0.85,
            tags=["gold", "rates", "opportunity_cost"],
            context="Developed markets with positive real rates",
        )

        # Currency facts
        self.add_fact(
            title="Risk-Off Environments Strengthen USD and CHF",
            description=(
                "When risk sentiment deteriorates (equity volatility rises, spreads widen), "
                "capital flows toward safe-haven currencies. USD and CHF are primary "
                "beneficiaries due to their deep, liquid markets and associated economies."
            ),
            category="currency",
            source="Historical crisis analysis, daily flows",
            confidence=0.88,
            tags=["safe_haven", "risk_off", "usd", "chf"],
            context="Global risk-off episodes",
        )

        # Interest rate facts
        self.add_fact(
            title="Interest Rate Expectations Move Currencies",
            description=(
                "Currency valuation depends heavily on interest rate differentials. "
                "When market expectations for future rates change in one currency, "
                "capital repostures to capture the new rate differential."
            ),
            category="currency",
            source="Interest rate parity theory, market behavior",
            confidence=0.87,
            tags=["rates", "differentials", "carry"],
            context="Developed market currencies",
        )

        # Liquidity facts
        self.add_fact(
            title="Liquidity Seeks Liquidity",
            description=(
                "In stress periods or when liquidity dries up, large players liquidate "
                "illiquid positions to meet margin calls or reduce risk. This creates "
                "a self-reinforcing cycle where liquid assets become more liquid."
            ),
            category="liquidity",
            source="Market microstructure, stress events",
            confidence=0.83,
            tags=["stress", "cascade", "market_structure"],
            context="Illiquid or stressed conditions",
        )

        # Volatility facts
        self.add_fact(
            title="Volatility Regimes Shift Suddenly",
            description=(
                "Markets alternate between low-volatility regimes (where complacency builds) "
                "and high-volatility regimes (where uncertainty dominates). Transitions "
                "often occur quickly, sometimes on catalysts, sometimes endogenously."
            ),
            category="volatility",
            source="Volatility regime research, empirical observation",
            confidence=0.82,
            tags=["regime", "jump", "transition"],
            context="All markets",
        )

        # Structure facts
        self.add_fact(
            title="Support and Resistance Reflect Participation",
            description=(
                "Key price levels develop where many participants have positions or orders. "
                "Support forms where buyers previously entered, resistance where sellers "
                "accumulated. These levels reflect genuine market memory."
            ),
            category="structure",
            source="Technical analysis, market microstructure",
            confidence=0.79,
            tags=["levels", "orders", "memory"],
            context="All timeframes",
        )

        # Participation facts
        self.add_fact(
            title="Participation Divergence Precedes Reversals",
            description=(
                "When price reaches new extremes but participation (volume, breadth) lags, "
                "reversals often follow. This indicates conviction is waning even as price "
                "extends, suggesting weak commitment by new participants."
            ),
            category="participation",
            source="Technical analysis, divergence theory",
            confidence=0.76,
            tags=["divergence", "weakness", "reversal"],
            context="Trending markets",
        )

        # Correlation facts
        self.add_fact(
            title="Correlations Converge in Stress",
            description=(
                "During normal periods, many assets move independently or oppositely. "
                "During stress, correlations spike toward 1.0 as 'everything sells off'. "
                "This reflects common funding flows and margin pressure."
            ),
            category="correlation",
            source="Correlation research, stress events",
            confidence=0.84,
            tags=["stress", "diversification", "flows"],
            context="Stressed markets",
        )

        # Macro facts
        self.add_fact(
            title="Central Bank Communication Moves Markets",
            description=(
                "Market expectations for future central bank policy drive current pricing. "
                "Guidance, forward rates, and policy signals can move markets as much as "
                "actual decisions, as pricing reflects probability-weighted outcomes."
            ),
            category="central_bank",
            source="Central bank analysis, market reactions",
            confidence=0.86,
            tags=["policy", "expectations", "guidance"],
            context="Developed markets",
        )

        # Risk sentiment facts
        self.add_fact(
            title="Risk Sentiment Governs Asset Allocation",
            description=(
                "Periods of positive risk sentiment drive capital toward riskier assets "
                "(equities, commodities, high-yield credit). Negative risk sentiment "
                "drives capital toward defensive assets (treasuries, gold, cash)."
            ),
            category="risk_sentiment",
            source="Daily asset flows, portfolio theory",
            confidence=0.85,
            tags=["flows", "allocation", "sentiment"],
            context="Multi-asset environment",
        )

    def __str__(self) -> str:
        """Return a human-readable representation."""
        summary = self.get_summary()
        return (
            f"SemanticMemory({summary['active_facts']} active facts, "
            f"{summary['avg_confidence']:.1%} avg confidence)"
        )
