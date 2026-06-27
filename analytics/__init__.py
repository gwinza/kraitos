"""Metrics, reporting, and performance analysis."""

from analytics.models import (
    ClosedTradeRecord,
    PairSpecialisationEntry,
    PairSpecialisationResult,
    PerformanceMetrics,
    SymbolPerformance,
)
from analytics.pair_specialisation import (
    PairSpecialisationAnalyzer,
    PairSpecialisationError,
)
from analytics.performance import PerformanceAnalyzer, PerformanceError
from analytics.trade_intelligence import (
    TradeIntelligenceEngine,
    TradeIntelligenceReport,
    OvercautionWarning,
)
from analytics.opportunity_cost_report import OpportunityCostReporter, OpportunityCostReport
from analytics.regime_performance_report import RegimePerformanceReporter, RegimePerformanceReport
from analytics.conviction_report import ConvictionReporter, ConvictionReport
from analytics.thesis_accuracy_report import ThesisAccuracyReporter, ThesisAccuracyReport
from analytics.trade_records import EnrichedTradeRecord, RejectedOpportunityRecord
from analytics.journal_bridge import (
    KraitosLearningLoop,
    get_learning_loop,
    journal_entry_to_enriched_record,
)

__all__ = [
    "ClosedTradeRecord",
    "ConvictionReport",
    "ConvictionReporter",
    "EnrichedTradeRecord",
    "journal_entry_to_enriched_record",
    "get_learning_loop",
    "KraitosLearningLoop",
    "OpportunityCostReport",
    "OpportunityCostReporter",
    "OvercautionWarning",
    "PairSpecialisationAnalyzer",
    "PairSpecialisationEntry",
    "PairSpecialisationError",
    "PairSpecialisationResult",
    "PerformanceAnalyzer",
    "PerformanceError",
    "PerformanceMetrics",
    "RegimePerformanceReport",
    "RegimePerformanceReporter",
    "RejectedOpportunityRecord",
    "SymbolPerformance",
    "ThesisAccuracyReport",
    "ThesisAccuracyReporter",
    "TradeIntelligenceEngine",
    "TradeIntelligenceReport",
]
