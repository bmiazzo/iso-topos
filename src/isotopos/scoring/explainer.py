"""Divergence breakdown, Earth-limit caveats, and exploration relevance (FR-11, parameters.md)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from isotopos.core.models import (
    DimensionBreakdown,
    EarthLimitCaveat,
    EarthSite,
    ParameterComparison,
    PlanetaryBody,
    TargetLocation,
)
from isotopos.core.registry import ParameterRegistry


@dataclass(frozen=True)
class ExplorationRelevanceRule:
    """Declarative rule mapping a physical parameter threshold to an exploration campaign tag."""

    parameter_id: str
    min_threshold: float
    label: str
    body_filter: PlanetaryBody | None = None

    def matches(self, site: EarthSite, target: TargetLocation) -> bool:
        if self.body_filter is not None and target.body != self.body_filter:
            return False
        return site.parameters.get(self.parameter_id, 0.0) >= self.min_threshold


DEFAULT_RELEVANCE_RULES: tuple[ExplorationRelevanceRule, ...] = (
    ExplorationRelevanceRule(
        parameter_id="anorthosite_highland_score",
        min_threshold=0.65,
        label="Lunar Highland Anorthosite Regolith Simulant & Geochemistry Calibration",
    ),
    ExplorationRelevanceRule(
        parameter_id="basalt_volcanic_score",
        min_threshold=0.65,
        label="Volcanic Basalt Rover Mobility & In-Situ Sintering Trials",
    ),
    ExplorationRelevanceRule(
        parameter_id="clay_carbonate_sediment_score",
        min_threshold=0.60,
        label="Lacustrine Clay/Carbonate Sample Caching & Biosignature Extraction",
    ),
    ExplorationRelevanceRule(
        parameter_id="low_sun_grazing_hours",
        min_threshold=1100.0,
        label="Low-Sun Grazing-Angle (0-5 deg) Optical Navigation & Precision Landing Tests",
    ),
    ExplorationRelevanceRule(
        parameter_id="subsurface_ice_permafrost",
        min_threshold=0.55,
        label="Cryogenic Ice-Regolith Drilling, Coring & ISRU Water Extraction",
    ),
    ExplorationRelevanceRule(
        parameter_id="subsurface_cave_drilling_score",
        min_threshold=0.65,
        label="Subsurface Lava Tube / Cold-Trap Cave Robotics & Radiation-Shelter Ops",
    ),
    ExplorationRelevanceRule(
        parameter_id="biosignature_preservation_score",
        min_threshold=0.65,
        label="Extremophile & Microbialite Biosignature Detection Protocol Validation",
        body_filter=PlanetaryBody.MARS,
    ),
    ExplorationRelevanceRule(
        parameter_id="slope_deg",
        min_threshold=18.0,
        label="Steep Crater-Wall Ascent/Descent & Tethered Rover Mobility",
    ),
)

BODY_CAVEAT_SPECS: dict[PlanetaryBody, tuple[EarthLimitCaveat, ...]] = {
    PlanetaryBody.MOON: (
        EarthLimitCaveat(
            category="gravity",
            title="Reduced Lunar Gravity (0.165 g)",
            explanation=(
                "Earth's 1.0 g gravity cannot reproduce lunar 1/6 g regolith cohesion, "
                "slope angle-of-repose stability, or rover traction/excavation loads."
            ),
        ),
        EarthLimitCaveat(
            category="atmosphere_vacuum",
            title="Hard Lunar Vacuum vs. Terrestrial Atmosphere",
            explanation=(
                "Earth's atmosphere causes convective heat transfer, weathering, and dust settling; "
                "on the Moon, electrostatic dust levitation and vacuum thermal radiation dominate."
            ),
        ),
        EarthLimitCaveat(
            category="illumination_scattering",
            title="Pitch-Black Shadows vs. Atmospheric Scattering",
            explanation=(
                "Rayleigh scattering on Earth illuminates shadowed slopes; lunar grazing sunlight "
                "(0-5 deg) casts zero-light black shadows that severely challenge optical landing & navigation."
            ),
        ),
    ),
    PlanetaryBody.MARS: (
        EarthLimitCaveat(
            category="gravity",
            title="Reduced Martian Gravity (0.38 g)",
            explanation=(
                "Martian 0.38 g alters aeolian dust saltation thresholds, slope failure mechanics, "
                "and lander/rover suspension loads relative to Earth."
            ),
        ),
        EarthLimitCaveat(
            category="atmosphere_co2",
            title="Thin 6 mbar CO2 Atmosphere",
            explanation=(
                "Earth's 1013 mbar N2/O2 atmosphere differs fundamentally from Mars' 6 mbar CO2 "
                "regime, affecting aerodynamic braking, convective cooling, and ISRU Sabatier testing."
            ),
        ),
        EarthLimitCaveat(
            category="radiation",
            title="Unshielded Surface Radiation",
            explanation=(
                "Mars lacks a global magnetosphere and thick ozone/atmosphere shield; terrestrial "
                "sites do not reproduce galactic cosmic ray and solar energetic particle fluxes."
            ),
        ),
    ),
}


class DivergenceExplainer:
    """Produces transparent scientific explanations for why an Earth site matches or diverges."""

    def __init__(
        self,
        registry: ParameterRegistry,
        relevance_rules: Sequence[ExplorationRelevanceRule] = DEFAULT_RELEVANCE_RULES,
    ) -> None:
        self._registry = registry
        self._relevance_rules = tuple(relevance_rules)

    def build_dimension_breakdowns(
        self,
        comparisons: list[ParameterComparison],
    ) -> tuple[list[DimensionBreakdown], list[str], list[str]]:
        """Aggregate parameter comparisons into per-dimension sub-scores with N/A guards."""
        comp_by_dim: dict[str, list[ParameterComparison]] = {
            d.id: [] for d in self._registry.dimensions
        }
        for comp in comparisons:
            comp_by_dim[comp.dimension_id].append(comp)

        breakdowns: list[DimensionBreakdown] = []
        strongest: list[str] = []
        diverging: list[str] = []

        for dim in self._registry.dimensions:
            dim_comps = comp_by_dim.get(dim.id, [])
            active = [c for c in dim_comps if c.weight > 0.0]
            total_w = sum(c.weight for c in active)
            if total_w <= 0.0:
                breakdowns.append(
                    DimensionBreakdown(
                        dimension_id=dim.id,
                        dimension_name=dim.name,
                        sub_score=None,
                        active_parameter_count=0,
                        status="N/A",
                    )
                )
                continue

            sub_score = sum(c.weight * c.similarity for c in active) / total_w
            if sub_score >= 0.78:
                status = "strong"
                strongest.append(dim.name)
            elif sub_score >= 0.55:
                status = "moderate"
            else:
                status = "divergent"
                diverging.append(dim.name)

            breakdowns.append(
                DimensionBreakdown(
                    dimension_id=dim.id,
                    dimension_name=dim.name,
                    sub_score=round(sub_score, 4),
                    active_parameter_count=len(active),
                    status=status,
                )
            )

        return breakdowns, strongest, diverging

    def build_caveats(
        self,
        site: EarthSite,
        target: TargetLocation,
        comparisons: list[ParameterComparison],
    ) -> list[EarthLimitCaveat]:
        """Generate explicit Earth-limit caveats grounded in planetary physics (FR-11)."""
        caveats: list[EarthLimitCaveat] = list(BODY_CAVEAT_SPECS.get(target.body, ()))

        if (
            target.parameters.get("subsurface_ice_permafrost", 0.0) >= 0.4
            or site.parameters.get("subsurface_ice_permafrost", 0.0) >= 0.4
        ):
            caveats.append(
                EarthLimitCaveat(
                    category="ice_sublimation",
                    title="Ice Sublimation vs. Terrestrial Melting",
                    explanation=(
                        "Under lunar vacuum or Mars' 6 mbar pressure, water ice sublimates directly from solid to vapor; "
                        "most terrestrial permafrost sites degrade by liquid melting (except hyper-arid Antarctic valleys)."
                    ),
                )
            )

        out_of_env = [c for c in comparisons if c.out_of_envelope_delta > 0.0 and c.weight > 0.0]
        if out_of_env:
            details = "; ".join(
                f"{c.label}: target {c.target_value:.1f} {c.unit} exceeds Earth envelope by {c.out_of_envelope_delta:.1f} {c.unit}"
                for c in out_of_env
            )
            caveats.append(
                EarthLimitCaveat(
                    category="envelope_exceeded",
                    title="Planetary Extremes Beyond Earth's Physical Envelope",
                    explanation=details,
                )
            )

        return caveats

    def build_exploration_relevance(
        self,
        site: EarthSite,
        target: TargetLocation,
    ) -> list[str]:
        """Suggest concrete engineering, ISRU, and scientific test campaigns for the analog."""
        relevance = [rule.label for rule in self._relevance_rules if rule.matches(site, target)]
        if not relevance:
            relevance.append("General Terrain Traversability & Multi-Sensor Instrument Field Calibration")
        return relevance
