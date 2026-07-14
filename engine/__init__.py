"""
Bewertungs-Engine: reine Fachlogik ohne UI-Abhaengigkeiten.

Oeffentliche API dieses Pakets - die App (und Tests) importieren
ausschliesslich von hier, nicht aus den Untermodulen.
"""

from .analytics import (
    HEATMAP_ACHSEN,
    MC_STANDARD_SIGMAS,
    MonteCarloResult,
    SzenarioVergleich,
    break_even_zuschlag,
    calculate_lcoe,
    run_irr_heatmap,
    run_monte_carlo,
    run_scenario_comparison,
    run_tornado,
)
from .cashflow import CashflowTimeseries
from .models import (
    AnlagenTyp,
    CapexBreakdown,
    EffectiveAssumptions,
    GlobalAssumptions,
    KPIs,
    MarktpreisSzenario,
    NegativeStundenModus,
    OpexItem,
    PVProject,
    TaxModus,
    TilgungsArt,
)
from .pipeline import (
    ValuationResult,
    resolve_assumptions,
    run_valuation,
    run_valuation_from_assumptions,
)
from .sensitivity import run_eag_sensitivity

__all__ = [
    "HEATMAP_ACHSEN",
    "MC_STANDARD_SIGMAS",
    "MonteCarloResult",
    "SzenarioVergleich",
    "break_even_zuschlag",
    "calculate_lcoe",
    "run_irr_heatmap",
    "run_monte_carlo",
    "run_scenario_comparison",
    "run_tornado",
    "run_valuation_from_assumptions",
    "AnlagenTyp",
    "CapexBreakdown",
    "CashflowTimeseries",
    "EffectiveAssumptions",
    "GlobalAssumptions",
    "KPIs",
    "MarktpreisSzenario",
    "NegativeStundenModus",
    "OpexItem",
    "PVProject",
    "TaxModus",
    "TilgungsArt",
    "ValuationResult",
    "resolve_assumptions",
    "run_valuation",
    "run_eag_sensitivity",
]
