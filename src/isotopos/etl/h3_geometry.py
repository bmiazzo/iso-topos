"""H3 land mask extraction and antimeridian-safe GeoJSON hexagon geometry builders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h3

from isotopos.etl.catalog_data import EARTH_HOTSPOTS

_LAND_CELL_CACHE: dict[int, frozenset[str]] = {}

# Key volcanic, polar, and oceanic analog islands guaranteed in the land mask
ANALOG_ISLANDS_LATLON: tuple[tuple[float, float], ...] = (
    (19.8207, -155.4681),  # Hawaii (Mauna Kea / Big Island)
    (20.7097, -156.2533),  # Maui (Haleakala)
    (65.0300, -16.7500),   # Iceland (Askja / Holuhraun)
    (63.9800, -22.6000),   # Iceland (Reykjanes)
    (78.9000, 16.0000),    # Svalbard (Spitsbergen)
    (79.8000, 22.0000),    # Svalbard (Nordaustlandet)
    (29.0000, -13.6800),   # Canary Islands (Lanzarote)
    (28.2700, -16.6400),   # Canary Islands (Tenerife / Teide)
    (28.7600, -17.8900),   # Canary Islands (La Palma)
    (38.4700, -28.4000),   # Azores (Pico)
    (-0.8300, -91.1300),   # Galapagos (Sierra Negra)
    (-19.0000, 47.0000),   # Madagascar
    (-62.9700, -60.6500),  # Deception Island (Antarctica)
    (-49.3500, 70.2200),   # Kerguelen Islands
    (75.4300, -89.6500),   # Devon Island (Haughton Crater)
    (79.4000, -90.8000),   # Axel Heiberg Island
)


def _extract_cells_from_geojson(geo_path: Path, res: int) -> set[str]:
    """Extract overlapping H3 cells and boundary-vertex cells from a GeoJSON Polygon/MultiPolygon file."""
    cells: set[str] = set()
    if not geo_path.exists():
        return cells
    geo = json.loads(geo_path.read_text(encoding="utf-8"))
    for feat in geo.get("features", []):
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "Polygon":
            polys = [coords]
        elif gtype == "MultiPolygon":
            polys = coords
        else:
            continue
        for poly in polys:
            outer = [(lat, lon) for lon, lat in poly[0]]
            if len(outer) < 3:
                continue
            holes = [
                [(lat, lon) for lon, lat in hole]
                for hole in poly[1:]
                if len(hole) >= 3
            ]
            h3_poly = h3.LatLngPoly(outer, *holes)
            try:
                extracted = h3.polygon_to_cells_experimental(h3_poly, res, contain="overlap")
            except Exception:
                extracted = h3.polygon_to_cells(h3_poly, res)
            cells.update(extracted)
            # Guarantee every polygon boundary vertex maps to an included cell
            for lat, lon in outer:
                cells.add(h3.latlng_to_cell(lat, lon, res))
    return cells


def load_land_h3_cells(res: int = 4) -> set[str]:
    """Extract H3 land + Antarctic ice-shelf cells from Natural Earth 50m polygons + curated sites."""
    if res in _LAND_CELL_CACHE:
        return set(_LAND_CELL_CACHE[res])

    root = Path(__file__).resolve().parents[3]
    ne_path = root / "data" / "raw" / "ne_50m_land.geojson"
    ice_path = root / "data" / "raw" / "ne_50m_antarctic_ice_shelves_polys.geojson"
    cache_path = root / "data" / "raw" / f"ne_50m_h3_res{res}_cells_polar_v2.json"

    if cache_path.exists():
        cells = frozenset(json.loads(cache_path.read_text(encoding="utf-8")))
        _LAND_CELL_CACHE[res] = cells
        return set(cells)

    cells: set[str] = _extract_cells_from_geojson(ne_path, res)
    cells.update(_extract_cells_from_geojson(ice_path, res))

    # Guarantee all curated Earth hotspots and key volcanic/polar analog islands are included
    for hs in EARTH_HOTSPOTS:
        cells.add(h3.latlng_to_cell(hs.lat, hs.lon, res))
    for lat, lon in ANALOG_ISLANDS_LATLON:
        cells.add(h3.latlng_to_cell(lat, lon, res))

    if ne_path.exists():
        cache_path.write_text(
            json.dumps(sorted(cells), separators=(",", ":")),
            encoding="utf-8",
        )

    _LAND_CELL_CACHE[res] = frozenset(cells)
    return set(cells)


def clip_antimeridian_halfplane(
    pts_360: list[tuple[float, float]],
    keep_le_180: bool,
) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of an unwrapped [0, 360] ring against x = 180.0."""
    out: list[tuple[float, float]] = []
    n = len(pts_360)
    for i in range(n):
        x1, y1 = pts_360[i]
        x2, y2 = pts_360[(i + 1) % n]
        in1 = (x1 <= 180.0) if keep_le_180 else (x1 >= 180.0)
        in2 = (x2 <= 180.0) if keep_le_180 else (x2 >= 180.0)
        if in1 and in2:
            out.append((x2, y2))
        elif in1 and not in2:
            t = (180.0 - x1) / (x2 - x1) if x2 != x1 else 0.0
            out.append((180.0, y1 + t * (y2 - y1)))
        elif not in1 and in2:
            t = (180.0 - x1) / (x2 - x1) if x2 != x1 else 0.0
            out.append((180.0, y1 + t * (y2 - y1)))
            out.append((x2, y2))
    return out


def close_rounded_ring(pts: list[tuple[float, float]]) -> list[list[float]] | None:
    """Round ring coordinates to 4 decimal places and ensure GeoJSON ring closure."""
    if len(pts) < 3:
        return None
    ring = [[round(ln, 4), round(lt, 4)] for ln, lt in pts]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring if len(ring) >= 4 else None


def _append_polar_wedge(
    polys: list[list[list[list[float]]]],
    lon_a: float,
    lat_a: float,
    lon_b: float,
    lat_b: float,
    pole_lat: float,
) -> None:
    """Append one (or two if >90° wide) closed polar wedge triangles meeting at (mid_lon, pole_lat)."""
    if abs(lon_b - lon_a) > 90.0:
        mid_lon = 0.5 * (lon_a + lon_b)
        mid_lat = 0.5 * (lat_a + lat_b)
        _append_polar_wedge(polys, lon_a, lat_a, mid_lon, mid_lat, pole_lat)
        _append_polar_wedge(polys, mid_lon, mid_lat, lon_b, lat_b, pole_lat)
        return
    ring = close_rounded_ring([(lon_a, lat_a), (lon_b, lat_b), (0.5 * (lon_a + lon_b), pole_lat)])
    if ring is not None:
        polys.append([ring])


def fan_polar_ring(lons: list[float], lats: list[float]) -> dict[str, Any] | None:
    """Split a pole-encircling boundary ring into <=90°-span wedges meeting at ±90.0°."""
    n = len(lons)
    if n < 3 or n != len(lats):
        return None
    pole_lat = -90.0 if sum(lats) < 0.0 else 90.0
    polys: list[list[list[list[float]]]] = []
    for i in range(n):
        lon_a, lat_a = lons[i], lats[i]
        lon_b, lat_b = lons[(i + 1) % n], lats[(i + 1) % n]
        if abs(lon_b - lon_a) <= 180.0:
            _append_polar_wedge(polys, lon_a, lat_a, lon_b, lat_b, pole_lat)
        else:
            # Edge crosses the ±180° antimeridian: unwrap into [0, 360] and split at x = 180.0
            ax = lon_a if lon_a >= 0.0 else lon_a + 360.0
            bx = lon_b if lon_b >= 0.0 else lon_b + 360.0
            t = (180.0 - ax) / (bx - ax) if bx != ax else 0.5
            lat_cross = lat_a + t * (lat_b - lat_a)
            seam_a = 180.0 if lon_a >= 0.0 else -180.0
            seam_b = 180.0 if lon_b >= 0.0 else -180.0
            _append_polar_wedge(polys, lon_a, lat_a, seam_a, lat_cross, pole_lat)
            _append_polar_wedge(polys, seam_b, lat_cross, lon_b, lat_b, pole_lat)
    if not polys:
        return None
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def safe_hex_geometry(cell_id: str) -> dict[str, Any] | None:
    """Convert H3 cell boundary to GeoJSON Polygon or antimeridian/polar-split MultiPolygon."""
    boundary = h3.cell_to_boundary(cell_id)  # list of (lat, lon)
    lons = [pt[1] for pt in boundary]
    lats = [pt[0] for pt in boundary]
    lon_span = max(lons) - min(lons)

    if lon_span <= 90.0:
        ring = [[round(ln, 4), round(lt, 4)] for ln, lt in zip(lons, lats)]
        ring.append(ring[0])
        return {"type": "Polygon", "coordinates": [ring]}

    if lon_span > 180.0:
        # Unwrap to [0, 360] and check whether this is a valid antimeridian crossing
        pts_360 = [(ln if ln >= 0.0 else ln + 360.0, lt) for ln, lt in zip(lons, lats)]
        xs_360 = [p[0] for p in pts_360]
        if max(xs_360) - min(xs_360) <= 90.0:
            east_pts = clip_antimeridian_halfplane(pts_360, keep_le_180=True)
            west_pts = [
                (x - 360.0, y)
                for x, y in clip_antimeridian_halfplane(pts_360, keep_le_180=False)
            ]
            east_ring = close_rounded_ring(east_pts)
            west_ring = close_rounded_ring(west_pts)
            polys = []
            if east_ring is not None:
                polys.append([east_ring])
            if west_ring is not None:
                polys.append([west_ring])
            if len(polys) == 2:
                return {"type": "MultiPolygon", "coordinates": polys}
            if len(polys) == 1:
                return {"type": "Polygon", "coordinates": polys[0]}

    # Polar-encircling H3 cell (e.g. cell straddling -90 deg South Pole)
    if all(abs(lt) > 85.0 for lt in lats):
        return fan_polar_ring(lons, lats)

    return None


def safe_hex_polygon(cell_id: str) -> list[list[float]] | None:
    """Legacy single-ring helper returning the first ring of safe_hex_geometry."""
    geom = safe_hex_geometry(cell_id)
    if geom is None:
        return None
    if geom["type"] == "Polygon":
        return geom["coordinates"][0]
    return geom["coordinates"][0][0]
