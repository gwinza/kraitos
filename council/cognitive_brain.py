from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from council.chief_intelligence_officer import ChiefIntelligenceOfficer
from council.cognitive_bus import CognitiveBus
from council.cognitive_context import MarketCognitiveContext
from council.cognitive_models import CIODecision
from council.council_memory import CouncilMemory
from council.cognitive_reports import CognitiveReportWriter
from council.specialists import ALL_SPECIALIST_COUNCILS, SpecialistCouncil
from intelligence.harvest_opportunity_score import infer_session

if TYPE_CHECKING:
    from brains.models import TradeCandidate


class CognitiveBrain:
    """
    Kraitos V3 parallel cognitive architecture.

    All specialist councils analyse simultaneously, deliberate via the bus,
    and the CIO produces one coherent probabilistic thesis.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        councils: tuple[SpecialistCouncil, ...] | None = None,
        deliberation_rounds: int = 2,
    ) -> None:
        self._memory = CouncilMemory(project_root) if project_root else CouncilMemory(Path("."))
        if project_root:
            self._memory.load()
        self._councils = councils or ALL_SPECIALIST_COUNCILS
        self._bus = CognitiveBus()
        self._cio = ChiefIntelligenceOfficer(self._memory)
        self._deliberation_rounds = deliberation_rounds
        self._latest: dict[str, CIODecision] = {}
        self.reports = CognitiveReportWriter(project_root) if project_root else None

    def deliberate(
        self,
        candidate: TradeCandidate,
        *,
        evaluation_moment=None,
    ) -> CIODecision:
        hour = evaluation_moment.hour if evaluation_moment is not None else 12
        session = infer_session(hour)
        context = MarketCognitiveContext.from_candidate(
            candidate,
            evaluation_moment=evaluation_moment,
            session_label=session,
        )

        observations = tuple(council.analyze(context) for council in self._councils)
        messages = self._bus.deliberate(
            observations,
            rounds=self._deliberation_rounds,
        )
        decision = self._cio.reason(context, observations, messages)
        self._latest[candidate.symbol] = decision
        if self.reports is not None:
            self.reports.record(candidate.symbol, decision)
        return decision

    def maybe_write_reports(self) -> Path | None:
        if self.reports is None:
            return None
        return self.reports.write_report()

    @property
    def memory(self) -> CouncilMemory:
        return self._memory

    def latest(self, symbol: str) -> CIODecision | None:
        return self._latest.get(symbol)
