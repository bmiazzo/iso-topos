"""Curated field photography and real-dataset macro parameter refresh for named Earth hotspots."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from isotopos.core.models import EarthSite
from isotopos.etl.sources.baseline_regions import CountryResolver, is_well_known_baseline_region

if TYPE_CHECKING:
    from isotopos.etl.sources.earth_datasets import EarthOpenDatasets

HOTSPOT_PHOTOS: dict[str, tuple[str, str]] = {
    "atacama_yungay": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/e0/Valle_della_Luna_01.jpg/960px-Valle_della_Luna_01.jpg",
        "Wikimedia Commons — Valle de la Luna, Atacama Desert",
    ),
    "mcmurdo_dry_valleys": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/3/35/Wright_Valley_From_Bull_Pass.jpg/960px-Wright_Valley_From_Bull_Pass.jpg",
        "Wikimedia Commons — Wright Valley, McMurdo Dry Valleys",
    ),
    "haughton_crater": (
        "https://upload.wikimedia.org/wikipedia/commons/7/77/Haughton_impact_crater_radar_image.jpg",
        "NASA/CSA RADARSAT — Haughton Impact Crater, Devon Island",
    ),
    "mauna_loa_hiseas": (
        "https://upload.wikimedia.org/wikipedia/commons/e/e0/Mauna_Loa_Volcano.jpg",
        "USGS / Wikimedia Commons — Mauna Loa Volcano, Hawai'i",
    ),
    "askja_iceland": (
        "https://upload.wikimedia.org/wikipedia/commons/e/e6/Askja.jpg",
        "Wikimedia Commons — Askja Caldera, Central Highlands, Iceland",
    ),
    "rio_tinto": (
        "https://upload.wikimedia.org/wikipedia/commons/b/b0/Rio_tinto_river_CarolStoker_NASA_Ames_Research_Center.jpg",
        "NASA Ames Research Center / Carol Stoker — Río Tinto, Spain",
    ),
    "white_mountain_greenland": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/b/ba/Kangerlussuaq%2C_Greenland.jpg/960px-Kangerlussuaq%2C_Greenland.jpg",
        "Wikimedia Commons — Kangerlussuaq Anorthosite Highlands, Greenland",
    ),
    "grotta_del_gelo_etna": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/3/39/Mt_Etna_and_Catania1.jpg/960px-Mt_Etna_and_Catania1.jpg",
        "Wikimedia Commons — Mount Etna Basaltic Massif, Sicily",
    ),
    "mistastin_crater": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/16/Mistastin_crater_L1C_T20UMG_T20VMH_A026091_20200620T152632.jpg/960px-Mistastin_crater_L1C_T20UMG_T20VMH_A026091_20200620T152632.jpg",
        "Copernicus Sentinel-2 / Wikimedia Commons — Mistastin Impact Structure, Labrador",
    ),
    "lofoten_anorthosite": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/5/59/Moskenes_Reinebringen_lub_2025-07-21_img09_Aussicht.jpg/960px-Moskenes_Reinebringen_lub_2025-07-21_img09_Aussicht.jpg",
        "Wikimedia Commons — Lofoten Archipelago Plutonic Ridge, Norway",
    ),
    "batagaika_megaslump": (
        "https://upload.wikimedia.org/wikipedia/commons/d/da/Batagaika_crater_NASA.jpg",
        "NASA Earth Observatory — Batagaika Permafrost Megaslump, Yakutia",
    ),
    "lake_salda": (
        "https://upload.wikimedia.org/wikipedia/commons/d/de/Lake_Salda_in_June_2020.jpg",
        "NASA Earth Observatory — Lake Salda Hydromagnesite Shorelines, Turkey",
    ),
    "pilbara_shark_bay": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/60/Dales_Gorge%2C_WA.jpg/960px-Dales_Gorge%2C_WA.jpg",
        "Wikimedia Commons — Pilbara Banded Iron Gorge, Western Australia",
    ),
    "svalbard_adventdalen": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d0/Adventdalen-Vei-400.jpg/960px-Adventdalen-Vei-400.jpg",
        "Wikimedia Commons — Adventdalen Permafrost Valley, Svalbard",
    ),
    "lut_desert_iran": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/3/3c/Dasht-e_Lut_Desert_in_Kerman_Province_02.jpg/960px-Dasht-e_Lut_Desert_in_Kerman_Province_02.jpg",
        "Wikimedia Commons — Dasht-e Lut Hyper-Arid Desert, Iran",
    ),
    "qaidam_dalangtan": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a1/Qaidam-basin-china.jpg/960px-Qaidam-basin-china.jpg",
        "Wikimedia Commons — Qaidam Basin Evaporite Playas, Qinghai",
    ),
    "dallol_danakil": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d4/ET_Afar_asv2018-01_img48_Dallol.jpg/960px-ET_Afar_asv2018-01_img48_Dallol.jpg",
        "Wikimedia Commons — Dallol Hydrothermal Salt Terraces, Ethiopia",
    ),
    "puna_de_atacama": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/ce/Llullaillaco_del_este_%2826535509125%29.jpg/960px-Llullaillaco_del_este_%2826535509125%29.jpg",
        "Wikimedia Commons — Puna de Atacama High Altiplano, Argentina",
    ),
    "harrat_khaybar": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/4/4c/%D8%AD%D8%B1%D8%A9_%D8%AE%D9%8A%D8%A8%D8%B1.jpg/960px-%D8%AD%D8%B1%D8%A9_%D8%AE%D9%8A%D8%A8%D8%B1.jpg",
        "Wikimedia Commons — Harrat Khaybar Basaltic Volcanic Field, Saudi Arabia",
    ),
    "lonar_crater": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/8/82/Lonar_Crater%2C_Panorama.jpg/960px-Lonar_Crater%2C_Panorama.jpg",
        "Wikimedia Commons — Lonar Basaltic Impact Crater, Maharashtra",
    ),
    "makgadikgadi_pans": (
        "https://upload.wikimedia.org/wikipedia/commons/4/45/DeltaOkawango.jpg",
        "ESA / Wikimedia Commons — Makgadikgadi Evaporite Basin, Botswana",
    ),
    "meighen_island": (
        "https://upload.wikimedia.org/wikipedia/commons/a/a3/Meighen_island.jpg",
        "NASA / Wikimedia Commons — Meighen Island High Arctic Ice Cap, Nunavut",
    ),
    "lanzarote_corona": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/10/Lanzarote_5_Luc_Viatour.jpg/960px-Lanzarote_5_Luc_Viatour.jpg",
        "Wikimedia Commons — Corona Basalt Lava System, Lanzarote",
    ),
    "tibesti_trou_natron": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/27/Trou_au_Natron_caldera_satellite_photo.jpg/960px-Trou_au_Natron_caldera_satellite_photo.jpg",
        "NASA Earth Observatory — Trou au Natron Caldera, Tibesti Mountains",
    ),
    "barringer_crater": (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/fd/Meteor_Crater_-_Arizona.jpg/960px-Meteor_Crater_-_Arizona.jpg",
        "Wikimedia Commons — Barringer Meteor Crater, Arizona",
    ),
    "salar_de_uyuni": (
        "https://upload.wikimedia.org/wikipedia/commons/4/4a/Salar_Uyuni_au01.jpg",
        "Wikimedia Commons — Salar de Uyuni Evaporite Salt Flat, Bolivia",
    ),
}

# Parameters refreshed from real global Earth rasters at each hotspot's exact coordinate,
# whereas sub-grid catalog measurements (local lithology, caves, biosignature preservation,
# micro-topography) remain intact per FR-5.
_REGIONAL_REFRESH_PARAMS = (
    "elevation_m",
    "magnetic_anomaly_nt",
    "mean_temp_c",
    "diurnal_amplitude_c",
    "low_sun_grazing_hours",
    "aridity_dryness_index",
)


def enrich_hotspots_from_datasets(
    hotspots: list[EarthSite],
    earth_ds: "EarthOpenDatasets | None" = None,
    country_resolver: CountryResolver | None = None,
) -> list[EarthSite]:
    """Attach verified photo URLs, countries, and real-dataset regional physical metrics to hotspots."""
    lats = np.array([h.lat for h in hotspots], dtype=np.float64)
    lons = np.array([h.lon for h in hotspots], dtype=np.float64)

    extracted = None
    if earth_ds is not None:
        extracted = earth_ds.extract_batch(lats, lons)
    elif country_resolver is None:
        default_countries = Path(__file__).resolve().parents[4] / "data" / "raw" / "ne_50m_admin_0_countries.geojson"
        if default_countries.exists():
            country_resolver = CountryResolver(default_countries)

    enriched: list[EarthSite] = []
    for idx, hs in enumerate(hotspots):
        params = dict(hs.parameters)
        interps: list[str] = list(hs.interpolated_parameters)
        country = hs.country
        if extracted is not None:
            params_list, interp_list, countries, _ = extracted
            real_p = params_list[idx]
            for pid in _REGIONAL_REFRESH_PARAMS:
                params[pid] = real_p[pid]
            # Preserve solar_illumination_frac=0.0 inside dark subterranean lava/ice cave (Etna)
            if hs.feature_category != "subterranean_cave" and hs.parameters.get("solar_illumination_frac", 1.0) > 0.05:
                params["solar_illumination_frac"] = real_p["solar_illumination_frac"]
            interps = [ip for ip in interp_list[idx] if ip in _REGIONAL_REFRESH_PARAMS or ip == "solar_illumination_frac"]
            if countries[idx]:
                country = countries[idx]
        elif not country and country_resolver is not None:
            resolved_country, _ = country_resolver.resolve(hs.lat, hs.lon)
            if resolved_country:
                country = resolved_country

        photo_url, photo_attr = HOTSPOT_PHOTOS.get(hs.id, (hs.photo_url, hs.photo_attribution))
        in_region, _ = is_well_known_baseline_region(hs.lat, hs.lon)
        enriched.append(
            hs.model_copy(
                update={
                    "country": country,
                    "is_well_known": bool(hs.is_well_known or in_region),
                    "interpolated_parameters": interps,
                    "photo_url": photo_url,
                    "photo_attribution": photo_attr,
                    "parameters": params,
                }
            )
        )
    return enriched
