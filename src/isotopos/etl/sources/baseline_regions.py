"""Full-region FR-6 baseline classifier and Natural Earth Admin-0 country resolver."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class BaselineRegionBox:
    """Named planetary analog region masked when 'Beyond Well-Known Sites' is enabled (FR-6)."""

    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


# Full geographical hubs for flagship planetary analog programs.
# Deliberately keeps neighboring novel alternatives (Bolivia Uyuni -67.49, Argentina Puna -67.45,
# Greenland White Mountain, Sicily Etna, etc.) unmasked.
WELL_KNOWN_REGION_BOXES: tuple[BaselineRegionBox, ...] = (
    BaselineRegionBox("Antarctica Continental Polar Ice & Dry Valleys", -90.0, -60.0, -180.0, 180.0),
    BaselineRegionBox("Iceland Volcanic Analog Corridor", 63.0, 67.2, -25.0, -12.5),
    BaselineRegionBox("Hawaiian Volcanic Archipelago", 18.5, 22.6, -161.0, -154.5),
    BaselineRegionBox("Atacama Hyper-Arid Corridor (Chile)", -27.5, -17.5, -71.2, -68.0),
    BaselineRegionBox("Devon Island / Haughton Impact Basin", 74.2, 77.2, -94.0, -79.0),
    BaselineRegionBox("Rio Tinto Acidic Sulfide Corridor", 37.2, 38.2, -7.4, -6.0),
)


def is_well_known_baseline_region(lat: float, lon: float) -> tuple[bool, str | None]:
    """Return (True, region_name) if (lat, lon) falls inside a full well-known baseline region."""
    for box in WELL_KNOWN_REGION_BOXES:
        if box.lat_min <= lat <= box.lat_max and box.lon_min <= lon <= box.lon_max:
            return True, box.name
    return False, None


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) if yj != yi else 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, rings: list[list[list[float]]]) -> bool:
    if not rings or not _point_in_ring(lon, lat, rings[0]):
        return False
    # Subtract interior holes
    return not any(_point_in_ring(lon, lat, hole) for hole in rings[1:])


@dataclass(frozen=True)
class _CountryPolygon:
    name: str
    continent: str
    subregion: str
    min_lon: float
    max_lon: float
    min_lat: float
    max_lat: float
    polygons: tuple[list[list[list[float]]], ...]


class CountryResolver:
    """Fast bounding-box-indexed Natural Earth Admin-0 country and continent resolver."""

    def __init__(self, geojson_path: Path | None = None) -> None:
        self._entries: list[_CountryPolygon] = []
        if geojson_path is not None and geojson_path.exists():
            self._load(geojson_path)

    def _load(self, path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        for feat in raw.get("features", []):
            props = feat.get("properties", {}) or {}
            geom = feat.get("geometry", {}) or {}
            gtype = geom.get("type")
            coords = geom.get("coordinates") or []
            polys: list[list[list[list[float]]]] = []
            if gtype == "Polygon":
                polys = [coords]
            elif gtype == "MultiPolygon":
                polys = coords
            if not polys:
                continue

            name = str(props.get("NAME") or props.get("ADMIN") or props.get("SOVEREIGNT") or "").strip()
            continent = str(props.get("CONTINENT") or props.get("REGION_UN") or "").strip()
            subregion = str(props.get("SUBREGION") or continent or "").strip()
            if not name:
                continue

            xs: list[float] = []
            ys: list[float] = []
            for poly in polys:
                for ring in poly:
                    for pt in ring:
                        xs.append(float(pt[0]))
                        ys.append(float(pt[1]))
            if not xs:
                continue

            self._entries.append(
                _CountryPolygon(
                    name=name,
                    continent=continent or "Global Land",
                    subregion=subregion or continent or "Global Land",
                    min_lon=min(xs),
                    max_lon=max(xs),
                    min_lat=min(ys),
                    max_lat=max(ys),
                    polygons=tuple(polys),
                )
            )

    def resolve(self, lat: float, lon: float) -> tuple[str, str]:
        """Return (country, region) for (lat, lon); uses continent/polar fallback if coastal."""
        if lat <= -60.0:
            return "Antarctica", "Antarctica"

        for entry in self._entries:
            if not (entry.min_lon <= lon <= entry.max_lon and entry.min_lat <= lat <= entry.max_lat):
                continue
            for poly in entry.polygons:
                if _point_in_polygon(lon, lat, poly):
                    region = entry.subregion if entry.subregion != entry.name else entry.continent
                    return entry.name, region

        # Coastline/island buffer (~0.35 deg) so H3 hexagons overlapping ragged shorelines still tag
        pad = 0.35
        for dl, dn in ((pad, 0.0), (-pad, 0.0), (0.0, pad), (0.0, -pad)):
            qlat = max(-89.9, min(89.9, lat + dl))
            qlon = ((lon + dn + 180.0) % 360.0) - 180.0
            for entry in self._entries:
                if not (entry.min_lon <= qlon <= entry.max_lon and entry.min_lat <= qlat <= entry.max_lat):
                    continue
                for poly in entry.polygons:
                    if _point_in_polygon(qlon, qlat, poly):
                        region = entry.subregion if entry.subregion != entry.name else entry.continent
                        return entry.name, region

        return "", _fallback_continent_band(lat, lon)


def _fallback_continent_band(lat: float, lon: float) -> str:
    if lat >= 66.0:
        return "High Arctic / Boreal"
    if -58.0 <= lat <= 13.0 and -85.0 <= lon <= -34.0:
        return "South America"
    if 13.0 < lat <= 75.0 and -170.0 <= lon <= -50.0:
        return "North America"
    if -36.0 <= lat <= 37.0 and -20.0 <= lon <= 52.0:
        return "Africa"
    if 36.0 < lat <= 72.0 and -25.0 <= lon <= 45.0:
        return "Europe"
    if -48.0 <= lat <= -10.0 and 110.0 <= lon <= 180.0:
        return "Oceania"
    return "Asia & Eurasia"


def format_h3_display_name(country: str, region: str, lat: float, lon: float, cell_id: str) -> str:
    """Create a clear geographic label for an H3 macro-cell."""
    lat_tag = f"{abs(lat):.1f}°{'N' if lat >= 0 else 'S'}"
    lon_tag = f"{abs(lon):.1f}°{'E' if lon >= 0 else 'W'}"
    short_id = cell_id[:7] if len(cell_id) > 7 else cell_id
    place = country or region or "Terrestrial Region"
    return f"{place} ({lat_tag}, {lon_tag}) · {short_id}"


def any_box_matches(points: Iterable[tuple[float, float]]) -> list[bool]:
    """Batch helper evaluating is_well_known_baseline_region over coordinates."""
    return [is_well_known_baseline_region(lat, lon)[0] for lat, lon in points]
