"""Spherical-Earth geometry for mission areas: great-circle distance and polygon area.

* Great-circle distance by the haversine formula — Sinnott, R. W. (1984), "Virtues of the Haversine",
  Sky and Telescope 68(2), p. 159.
* Polygon area on a sphere (approximate, lat-lon edges) — Chamberlain, R. G. & Duquette, W. H. (2007),
  "Some algorithms for polygons on a sphere", JPL Publication 07-03, eq. for A = (R²/2)|Σ(λ_{i+1}−λ_{i−1}) sin φ_i|.
* Mean Earth radius R = 6371.0088 km (IUGG mean radius R1 of GRS 80 — Moritz, H. (2000), "Geodetic Reference
  System 1980", Journal of Geodesy 74, 128–133).

Validity: spherical Earth (≤ 0.5 % error against the ellipsoid); polygon simple, no pole inside, edges short
enough that lat-lon, rhumb and great-circle edges coincide (Chamberlain & Duquette 2007, §"rhumb lines").
"""
from __future__ import annotations

import math

R_EARTH_KM = 6371.0088
REF_HAV = "Sinnott 1984 (haversine); R = 6371.0088 km (Moritz 2000, GRS 80 R1)"
REF_AREA = "Chamberlain & Duquette 2007, JPL Publ. 07-03 (polygon on a sphere)"


def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float, R_km: float = R_EARTH_KM) -> float:
    """Haversine great-circle distance [km] between two points given in degrees (Sinnott 1984)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * R_km * math.asin(min(1.0, math.sqrt(a)))


def polygon_area_km2(vertices: list, R_km: float = R_EARTH_KM) -> float:
    """Area [km²] of a simple polygon given as [[lat, lon], ...] in degrees (Chamberlain & Duquette 2007)."""
    pts = [(float(a), float(b)) for a, b in vertices]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    if n < 3:
        raise ValueError("polygon needs at least 3 vertices [[lat, lon], ...]")
    s = 0.0
    for i in range(n):
        lat_i = math.radians(pts[i][0])
        dl = math.radians(pts[(i + 1) % n][1] - pts[(i - 1) % n][1])
        dl = (dl + math.pi) % (2 * math.pi) - math.pi        # antimeridian: shortest signed difference
        s += dl * math.sin(lat_i)
    return abs(s) * R_km ** 2 / 2.0


def centroid_deg(vertices: list) -> tuple[float, float]:
    """Vertex-mean point [lat, lon] (a simple reference point for transit; not the area centroid — PRESSUPOSTO
    adequate for small convex areas)."""
    pts = [(float(a), float(b)) for a, b in vertices]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
