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


def load_land_h3_cells(res: int = 4) -> set[str]:
    """Extract H3 land cells from Natural Earth 50m Land polygons + curated islands/hotspots."""
    if res in _LAND_CELL_CACHE:
        return set(_LAND_CELL_CACHE[res])

    root = Path(__file__).resolve().parents[3]
    ne_path = root / "data" / "raw" / "ne_50m_land.geojson"
    cache_path = root / "data" / "raw" / f"ne_50m_h3_res{res}_cells.json"

    if cache_path.exists():
        cells = frozenset(json.loads(cache_path.read_text(encoding="utf-8")))
        _LAND_CELL_CACHE[res] = cells
        return set(cells)

    cells: set[str] = set()
    if ne_path.exists():
        geo = json.loads(ne_path.read_text(encoding="utf-8"))
        for feat in geo["features"]:
            geom = feat["geometry"]
            polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            for poly in polys:
                outer = [(max(-84.5, min(84.5, lat)), lon) for lon, lat in poly[0]]
                if len(outer) < 3:
                    continue
                holes = [
                    [(max(-84.5, min(84.5, lat)), lon) for lon, lat in hole]
                    for hole in poly[1:]
                    if len(hole) >= 3
                ]
                h3_poly = h3.LatLngPoly(outer, *holes)
                try:
                    extracted = h3.polygon_to_cells_experimental(h3_poly, res, contain="overlap")
                except Exception:
                    extracted = h3.polygon_to_cells(h3_poly, res)
                cells.update(extracted)

    # Guarantee all curated Earth hotspots and key volcanic/polar analog islands are included
    for hs in EARTH_HOTSPOTS:
        if abs(hs.lat) <= 84.5:
            cells.add(h3.latlng_to_cell(hs.lat, hs.lon, res))
    for lat, lon in ANALOG_ISLANDS_LATLON:
        if abs(lat) <= 84.5:
            cells.add(h3.latlng_to_cell(lat, lon, res))

    # Strictly filter out polar cap cells beyond Web Mercator's +-84.5 deg safe band
    cells = {cid for cid in cells if abs(h3.cell_to_latlng(cid)[0]) <= 84.5}

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


def safe_hex_geometry(cell_id: str) -> dict[str, Any] | None:
    """Convert H3 cell boundary to GeoJSON Polygon or antimeridian-split MultiPolygon."""
    boundary = h3.cell_to_boundary(cell_id)  # list of (lat, lon)
    lons = [pt[1] for pt in boundary]
    lats = [max(-84.95, min(84.95, pt[0])) for pt in boundary]
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

    return None


def safe_hex_polygon(cell_id: str) -> list[list[float]] | None:
    """Legacy single-ring helper returning the first ring of safe_hex_geometry."""
    geom = safe_hex_geometry(cell_id)
    if geom is None:
        return None
    if geom["type"] == "Polygon":
        return geom["coordinates"][0]
    return geom["coordinates"][0][0]
