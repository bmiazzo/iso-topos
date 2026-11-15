"""Declarative Parameter & Dimension Registry (FR-7, FR-8, FR-9, DR-3)."""

from __future__ import annotations

from collections.abc import Iterable

from isotopos.core.models import DimensionSpec, ParameterSpec, ProvenanceMetadata


class ParameterRegistry:
    """Registry holding analogy dimensions and physical parameters.

    Adding or removing a ParameterSpec here automatically updates scoring,
    API metadata, and UI controls without modifying core engine logic (FR-7).
    """

    def __init__(
        self,
        dimensions: Iterable[DimensionSpec],
        parameters: Iterable[ParameterSpec],
    ) -> None:
        self._dimensions: list[DimensionSpec] = []
        self._dim_map: dict[str, DimensionSpec] = {}
        for dim in dimensions:
            if dim.id in self._dim_map:
                raise ValueError(f"Duplicate dimension id: {dim.id}")
            self._dimensions.append(dim)
            self._dim_map[dim.id] = dim

        self._parameters: list[ParameterSpec] = []
        self._param_map: dict[str, ParameterSpec] = {}
        for param in parameters:
            if param.id in self._param_map:
                raise ValueError(f"Duplicate parameter id: {param.id}")
            if param.dimension_id not in self._dim_map:
                raise ValueError(
                    f"Parameter {param.id} references unknown dimension {param.dimension_id}"
                )
            self._parameters.append(param)
            self._param_map[param.id] = param

    @property
    def dimensions(self) -> list[DimensionSpec]:
        """Return registered dimensions in declaration order."""
        return list(self._dimensions)

    @property
    def parameters(self) -> list[ParameterSpec]:
        """Return registered parameters in declaration order."""
        return list(self._parameters)

    @property
    def parameter_ids(self) -> list[str]:
        """Return ordered parameter ids."""
        return [p.id for p in self._parameters]

    def get_dimension(self, dimension_id: str) -> DimensionSpec:
        """Look up a dimension by id."""
        if dimension_id not in self._dim_map:
            raise KeyError(f"Unknown dimension id: {dimension_id}")
        return self._dim_map[dimension_id]

    def get_parameter(self, parameter_id: str) -> ParameterSpec:
        """Look up a parameter by id."""
        if parameter_id not in self._param_map:
            raise KeyError(f"Unknown parameter id: {parameter_id}")
        return self._param_map[parameter_id]

    def parameter_ids_for_dimension(self, dimension_id: str) -> list[str]:
        """Return all parameter ids belonging to a given dimension."""
        return [p.id for p in self._parameters if p.dimension_id == dimension_id]

    def default_weights(self) -> dict[str, float]:
        """Return default weight mapping for all registered parameters."""
        return {p.id: p.default_weight for p in self._parameters}


def _prov(agency: str, dataset: str, url: str, unit: str, resolution: str) -> ProvenanceMetadata:
    return ProvenanceMetadata(
        agency_mission=agency,
        dataset_name=dataset,
        url=url,
        unit=unit,
        resolution=resolution,
    )


_CORE_DIMENSIONS: list[DimensionSpec] = [
    DimensionSpec(
        id="topography",
        name="Topography & Terrain",
        description="Elevation, slope steepness, crater walls vs. flat plateaus, and surface roughness.",
        is_core_v1=True,
    ),
    DimensionSpec(
        id="geology",
        name="Geology, Mineralogy & Magnetism",
        description="Anorthositic highlands, basaltic mare/plains, lacustrine clays/carbonates, regolith, and crustal magnetic anomalies.",
        is_core_v1=True,
    ),
    DimensionSpec(
        id="temperature_illumination",
        name="Temperature & Illumination",
        description="Thermal extremes, diurnal cycles, annual insolation, and low-angle 0-5 deg grazing sunlight.",
        is_core_v1=True,
    ),
    DimensionSpec(
        id="water_ice",
        name="Water, Ice & Permafrost",
        description="Hyper-aridity, shallow buried permafrost/ice, and cold-trap sublimation regimes.",
        is_core_v1=True,
    ),
    DimensionSpec(
        id="subsurface_biology",
        name="Subsurface, Biology & Operations",
        description="Lava tubes/ice caves, 2m drilling targets, and biosignature/stromatolite preservation (extensible FR-9).",
        is_core_v1=False,
    ),
]


_CORE_PARAMETERS: list[ParameterSpec] = [
    # 1. Topography & Terrain
    ParameterSpec(
        id="elevation_m",
        dimension_id="topography",
        label="Elevation / Datum Relief",
        unit="m",
        earth_min=-420.0,
        earth_max=5500.0,
        default_weight=0.6,
        description="Surface elevation relative to planetary geoid/datum.",
        earth_provenance=_prov(
            "NASA / NGA",
            "SRTM / ETOPO 2022 Global Relief",
            "https://search.earthdata.nasa.gov/",
            "m",
            "30 m – 1 arc-min",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "LOLA Lunar Orbiter Laser Altimeter GDR",
            "https://pds-geosciences.wustl.edu/missions/lro/lola.htm",
            "m",
            "5 m – 118 m",
        ),
        mars_provenance=_prov(
            "NASA MGS",
            "MOLA Mars Orbiter Laser Altimeter MEGDR",
            "https://pds-geosciences.wustl.edu/missions/mgs/mola.html",
            "m",
            "463 m",
        ),
    ),
    ParameterSpec(
        id="slope_deg",
        dimension_id="topography",
        label="Mean Terrain Slope",
        unit="deg",
        earth_min=0.0,
        earth_max=38.0,
        default_weight=0.85,
        description="Regional terrain slope; >30 deg reflects steep crater walls, <3 deg reflects landing plains.",
        earth_provenance=_prov(
            "NASA / USGS",
            "SRTM Derived Terrain Slope",
            "https://search.earthdata.nasa.gov/",
            "deg",
            "90 m",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "LOLA Polar & Global Slope Maps",
            "https://pds-geosciences.wustl.edu/missions/lro/lola.htm",
            "deg",
            "20 m – 240 m",
        ),
        mars_provenance=_prov(
            "NASA MGS / MRO",
            "MOLA & HiRISE Landing Site Slope Products",
            "https://pds.nasa.gov/",
            "deg",
            "1 m – 463 m",
        ),
    ),
    ParameterSpec(
        id="roughness_index",
        dimension_id="topography",
        label="Surface Roughness & Polygons",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.75,
        description="Normalized Terrain Ruggedness / SAR backscatter proxy for boulder fields and patterned ground.",
        earth_provenance=_prov(
            "CSA / NASA",
            "RADARSAT SAR & SRTM Terrain Ruggedness Index",
            "https://www.asc-csa.gc.ca/eng/satellites/radarsat/",
            "index (0-1)",
            "50 m – 1 km",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "Mini-RF CPR & LOLA Pulse Width Roughness",
            "https://pds-geosciences.wustl.edu/missions/lro/mini_rf.htm",
            "index (0-1)",
            "100 m",
        ),
        mars_provenance=_prov(
            "NASA MGS / MRO",
            "MOLA Surface Roughness & Context Camera Texture",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "463 m",
        ),
    ),
    # 2. Geology, Mineralogy & Magnetism
    ParameterSpec(
        id="anorthosite_highland_score",
        dimension_id="geology",
        label="Anorthosite & Impact Breccia Affinity",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.9,
        description="Calcium-rich plagioclase anorthosite crust & impact breccia affinity (key Lunar Highland proxy).",
        earth_provenance=_prov(
            "GLiM / Earth Impact DB",
            "Global Lithological Map & Impact Crater Database",
            "https://opensciencedata.esa.int/",
            "index (0-1)",
            "0.5 deg / site",
        ),
        moon_provenance=_prov(
            "NASA LRO / Chandrayaan-1",
            "Diviner Christiansen Feature & M3 Plagioclase Map",
            "https://pds-geosciences.wustl.edu/missions/lro/diviner.htm",
            "index (0-1)",
            "200 m",
        ),
        mars_provenance=_prov(
            "NASA MRO",
            "CRISM Feldspathic Highland Crust Detections",
            "https://pds-geosciences.wustl.edu/missions/mro/crism.htm",
            "index (0-1)",
            "18 m – 200 m",
        ),
    ),
    ParameterSpec(
        id="basalt_volcanic_score",
        dimension_id="geology",
        label="Mafic / Basaltic Regolith Affinity",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.85,
        description="Mafic volcanic basalt and pyroclastic regolith affinity (Lunar Mare & Martian plains).",
        earth_provenance=_prov(
            "GLiM / USGS",
            "Global Lithological Volcanic & Mafic Provinces",
            "https://opensciencedata.esa.int/",
            "index (0-1)",
            "0.5 deg",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "LROC WAC TiO2 / FeO Mare Basalt Abundance",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "400 m",
        ),
        mars_provenance=_prov(
            "NASA MGS / MRO",
            "TES & CRISM Mafic Basalt Spectral Index",
            "https://pds-geosciences.wustl.edu/missions/mro/crism.htm",
            "index (0-1)",
            "3 km",
        ),
    ),
    ParameterSpec(
        id="clay_carbonate_sediment_score",
        dimension_id="geology",
        label="Clays, Carbonates & Evaporite Salts",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.75,
        description="Phyllosilicate clays, lacustrine carbonates, sulfates, and perchlorate-analog evaporite salts.",
        earth_provenance=_prov(
            "NASA ASTER / GLiM",
            "ASTER Mineralogy & Lacustrine Evaporite Basins",
            "https://search.earthdata.nasa.gov/",
            "index (0-1)",
            "90 m – 0.5 deg",
        ),
        moon_provenance=_prov(
            "NASA LRO / M3",
            "Lunar Trace Alteration Baseline (Near-Zero)",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "200 m",
        ),
        mars_provenance=_prov(
            "NASA MRO",
            "CRISM Phyllosilicate, Carbonate & Sulfate Maps",
            "https://pds-geosciences.wustl.edu/missions/mro/crism.htm",
            "index (0-1)",
            "18 m – 200 m",
        ),
    ),
    ParameterSpec(
        id="regolith_rock_abundance",
        dimension_id="geology",
        label="Bare Rock & Dry Fine Regolith",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.85,
        description="Unvegetated bare rock and dry fine regolith exposure fraction.",
        earth_provenance=_prov(
            "ESA Copernicus / NASA MODIS",
            "Copernicus Bare Soil & MODIS NDVI Inverse",
            "https://dataspace.copernicus.eu/",
            "index (0-1)",
            "300 m – 1 km",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "Diviner Lunar Rock Abundance & Regolith Fines",
            "https://pds-geosciences.wustl.edu/missions/lro/diviner.htm",
            "index (0-1)",
            "200 m",
        ),
        mars_provenance=_prov(
            "NASA Mars Odyssey / MGS",
            "THEMIS / TES Thermal Inertia & Rock Abundance",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "100 m – 3 km",
        ),
    ),
    ParameterSpec(
        id="magnetic_anomaly_nt",
        dimension_id="geology",
        label="Crustal Magnetic Anomaly",
        unit="nT",
        earth_min=0.0,
        earth_max=1500.0,
        default_weight=0.35,
        description="Absolute crustal magnetic field anomaly intensity (from NOAA EMAG2v3 / planetary magnetometers).",
        earth_provenance=_prov(
            "NOAA / NCEI",
            "EMAG2v3 Earth Magnetic Anomaly Grid (2 arc-min)",
            "https://www.ncei.noaa.gov/products/earth-magnetic-model-anomaly-grid-2",
            "nT",
            "2 arc-min (~3.7 km)",
        ),
        moon_provenance=_prov(
            "NASA Lunar Prospector / JAXA Kaguya",
            "Lunar Crustal Magnetic Field Map",
            "https://pds.nasa.gov/",
            "nT",
            "0.5 deg",
        ),
        mars_provenance=_prov(
            "NASA MGS",
            "MAG/ER Martian Crustal Magnetic Anomaly Model",
            "https://pds.nasa.gov/",
            "nT",
            "1 deg",
        ),
    ),
    # 3. Temperature & Illumination
    ParameterSpec(
        id="mean_temp_c",
        dimension_id="temperature_illumination",
        label="Mean Surface Temperature",
        unit="degC",
        earth_min=-58.0,
        earth_max=48.0,
        default_weight=0.9,
        description="Annual mean surface skin temperature.",
        earth_provenance=_prov(
            "NASA EOSDIS",
            "MODIS Terra/Aqua Land Surface Temperature (MOD11C3)",
            "https://search.earthdata.nasa.gov/",
            "degC",
            "0.05 deg",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "Diviner Bolometric Surface Temperature Maps",
            "https://pds-geosciences.wustl.edu/missions/lro/diviner.htm",
            "degC",
            "240 m",
        ),
        mars_provenance=_prov(
            "NASA MGS / Mars Odyssey",
            "TES & THEMIS Surface Brightness Temperature",
            "https://pds.nasa.gov/",
            "degC",
            "3 km",
        ),
    ),
    ParameterSpec(
        id="diurnal_amplitude_c",
        dimension_id="temperature_illumination",
        label="Diurnal Temperature Swing",
        unit="degC",
        earth_min=2.0,
        earth_max=38.0,
        default_weight=0.75,
        description="Day-to-night surface thermal amplitude driving thermal fatigue.",
        earth_provenance=_prov(
            "NASA EOSDIS",
            "MODIS Day-Night LST Amplitude",
            "https://search.earthdata.nasa.gov/",
            "degC",
            "0.05 deg",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "Diviner Diurnal Bolometric Swing",
            "https://pds-geosciences.wustl.edu/missions/lro/diviner.htm",
            "degC",
            "500 m",
        ),
        mars_provenance=_prov(
            "NASA MGS",
            "TES Diurnal Thermal Swing",
            "https://pds.nasa.gov/",
            "degC",
            "3 km",
        ),
    ),
    ParameterSpec(
        id="solar_illumination_frac",
        dimension_id="temperature_illumination",
        label="Annual Solar Illumination Fraction",
        unit="fraction (0-1)",
        earth_min=0.0,
        earth_max=0.95,
        default_weight=0.7,
        description="Fraction of year receiving direct sunlight (0.0 in dark caves/PSRs, >0.85 on lunar peaks of eternal light).",
        earth_provenance=_prov(
            "NASA Langley",
            "CERES / POWER Surface Solar Irradiance",
            "https://search.earthdata.nasa.gov/",
            "fraction (0-1)",
            "0.5 deg",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "LOLA Polar Illumination & Horizon Model",
            "https://pds-geosciences.wustl.edu/missions/lro/lola.htm",
            "fraction (0-1)",
            "20 m – 60 m",
        ),
        mars_provenance=_prov(
            "NASA MRO / Viking",
            "Mars Solar Insolation & Dust Optical Depth Model",
            "https://pds.nasa.gov/",
            "fraction (0-1)",
            "5 deg",
        ),
    ),
    ParameterSpec(
        id="low_sun_grazing_hours",
        dimension_id="temperature_illumination",
        label="Grazing Sun Angle (0-5 deg)",
        unit="hrs/yr",
        earth_min=180.0,
        earth_max=2400.0,
        default_weight=0.75,
        description="Annual hours with solar elevation between 0 and 5 deg (navigation & long-shadow proxy from parameters.md).",
        earth_provenance=_prov(
            "NASA POWER / Ephemeris",
            "Analytical Solar Ephemeris (0-5 deg Elevation Hours)",
            "https://power.larc.nasa.gov/",
            "hrs/yr",
            "Analytical (lat)",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "LOLA Lunar Polar Grazing Illumination (1.54 deg obliquity)",
            "https://pds-geosciences.wustl.edu/missions/lro/lola.htm",
            "hrs/yr",
            "60 m",
        ),
        mars_provenance=_prov(
            "NASA PDS",
            "Mars Ephemeris Grazing Illumination (25.19 deg obliquity)",
            "https://pds.nasa.gov/",
            "hrs/yr",
            "Analytical (lat)",
        ),
    ),
    # 4. Water, Ice & Permafrost
    ParameterSpec(
        id="aridity_dryness_index",
        dimension_id="water_ice",
        label="Surface Hyper-Aridity",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.9,
        description="Surface dryness and absence of liquid water.",
        earth_provenance=_prov(
            "NASA JPL",
            "SMAP L3 Surface Soil Moisture (Inverted Dryness)",
            "https://search.earthdata.nasa.gov/",
            "index (0-1)",
            "9 km – 36 km",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "LEND Epithermal Neutron Surface Dryness",
            "https://pds-geosciences.wustl.edu/missions/lro/lend.htm",
            "index (0-1)",
            "10 km",
        ),
        mars_provenance=_prov(
            "NASA Mars Odyssey",
            "GRS / MONS Surface Hydration Index",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "5 deg",
        ),
    ),
    ParameterSpec(
        id="subsurface_ice_permafrost",
        dimension_id="water_ice",
        label="Shallow Subsurface Ice & Permafrost",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.9,
        description="Shallow (<1-2 m) ground ice and permafrost abundance for ISRU & drilling.",
        earth_provenance=_prov(
            "NSIDC / JAXA",
            "Circum-Arctic Permafrost & GCOM-W Cryosphere",
            "https://gportal.jaxa.jp/",
            "index (0-1)",
            "1 km – 12.5 km",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "LEND Hydrogen Suppression & Diviner Ice Stability",
            "https://pds-geosciences.wustl.edu/missions/lro/lend.htm",
            "index (0-1)",
            "10 km",
        ),
        mars_provenance=_prov(
            "NASA Mars Odyssey / MRO",
            "GRS Water-Equivalent Hydrogen & SHARAD Ice Sheet Map",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "5 deg",
        ),
    ),
    ParameterSpec(
        id="cold_trap_sublimation_index",
        dimension_id="water_ice",
        label="Cold-Trap & Sublimation Regime",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.75,
        description="Stability of buried/trapped ice via cold-trapping and sublimation vs. liquid melting.",
        earth_provenance=_prov(
            "NSIDC / Speleological DB",
            "Hyper-Arid Cryosphere & Geometric Ice Cave Traps",
            "https://nsidc.org/",
            "index (0-1)",
            "Site / 25 km",
        ),
        moon_provenance=_prov(
            "NASA LRO",
            "Diviner <110 K Cold-Trap Stability Index",
            "https://pds-geosciences.wustl.edu/missions/lro/diviner.htm",
            "index (0-1)",
            "240 m",
        ),
        mars_provenance=_prov(
            "NASA MRO / Viking",
            "Sub-Regolith Ice Sublimation Depth Model",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "5 deg",
        ),
    ),
    # 5. Subsurface, Biology & Operations (Extensible FR-9 + parameters.md)
    ParameterSpec(
        id="subsurface_cave_drilling_score",
        dimension_id="subsurface_biology",
        label="Caves, Lava Tubes & Subsurface Access",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.5,
        description="Presence of lava tube skylights, single-opening ice caves, or 2m stratigraphic drilling analogs.",
        earth_provenance=_prov(
            "Speleological & Volcanic Catalogs",
            "Global Lava Tube & Ice Cave Registry",
            "https://opensciencedata.esa.int/",
            "index (0-1)",
            "Local Hotspot",
        ),
        moon_provenance=_prov(
            "NASA LRO / JAXA Kaguya",
            "LROC & Terrain Camera Skylight Pit Catalog",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "1 m – 10 m",
        ),
        mars_provenance=_prov(
            "NASA MRO / ESA ExoMars",
            "HiRISE Volcanic Pit Skylights & 2m Drill Stratigraphy",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "0.25 m",
        ),
    ),
    ParameterSpec(
        id="biosignature_preservation_score",
        dimension_id="subsurface_biology",
        label="Biosignature & Microbialite Preservation",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.0,
        description="Preservation potential for microbialites/stromatolites in fine sediments (weighted active for Mars astrobiology; 0 on Moon).",
        earth_provenance=_prov(
            "NASA Astrobiology / NAI",
            "Terrestrial Stromatolite & Extremophile Analog DB",
            "https://search.earthdata.nasa.gov/",
            "index (0-1)",
            "Local / Basin",
        ),
        moon_provenance=_prov(
            "NASA PDS",
            "Lunar Sterile Baseline (Non-Biological Target)",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "Global",
        ),
        mars_provenance=_prov(
            "NASA MRO / ESA ExoMars",
            "Jezero & Oxia Planum Biosignature Preservation Potential",
            "https://pds.nasa.gov/",
            "index (0-1)",
            "Local Basin",
        ),
    ),
]


DEFAULT_REGISTRY = ParameterRegistry(
    dimensions=_CORE_DIMENSIONS,
    parameters=_CORE_PARAMETERS,
)
