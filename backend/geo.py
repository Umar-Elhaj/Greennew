# ============================================================
# GREEN App — Parcel geometry (pure Python, no GIS dependency)
#
# Coordinates follow GeoJSON: [longitude, latitude] in WGS84.
# - validate_polygon(): GeoJSON Polygon checks (closed ring, ranges,
#   no self-intersection, sensible size, swapped lat/lng detected)
# - geodesic area / perimeter / centroid / bbox
# - region_of(): region of Cameroon containing a point;
#   canonical_region(): the only region names stored (the 10 ADM1 names)
# - build_grid(): square cells aligned with the parcel's long axis,
#   clipped to the parcel, numbered along a serpentine (boustrophedon)
#   path; the path never jumps between non-adjacent cells (detours
#   through transit cells when the parcel is concave).
# Parcels are small (< a few km), so a local equirectangular projection
# around the centroid is accurate enough for the grid; areas use the
# spherical formula (same as Turf's @turf/area).
# ============================================================

import json
import math
import os
import unicodedata
from collections import deque
from typing import Optional

EARTH_RADIUS_M = 6371008.8          # mean radius (Turf / WGS84 authalic approximation)
MAX_VERTICES = 1000
MIN_AREA_M2 = 1.0
MAX_AREA_HA = 10000.0
MAX_CELLS = 5000
MIN_CELL_FRACTION = 0.10            # clipped cells smaller than 10 % of a cell are dropped
CAMEROON_BBOX = (8.4, 1.6, 16.3, 13.2)   # lng_min, lat_min, lng_max, lat_max (with margin)

REGIONS_PATH = os.path.join(os.path.dirname(__file__), "data", "cameroon_regions.json")


class GeometryError(ValueError):
    """Invalid parcel geometry; the message is shown to the user (translated by i18n.py)."""


# ---- Validation ---------------------------------------------
def _ring(geometry: dict) -> list:
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise GeometryError("The parcel geometry must be a GeoJSON Polygon.")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords or not isinstance(coords[0], list):
        raise GeometryError("The parcel geometry must be a GeoJSON Polygon.")
    if len(coords) > 1:
        raise GeometryError("Parcels with holes are not supported.")
    ring = []
    for pt in coords[0]:
        if not (isinstance(pt, (list, tuple)) and len(pt) >= 2
                and all(isinstance(v, (int, float)) and math.isfinite(v) for v in pt[:2])):
            raise GeometryError("Each point must be [longitude, latitude].")
        ring.append((float(pt[0]), float(pt[1])))
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    # drop consecutive duplicates
    ring = [p for i, p in enumerate(ring) if i == 0 or p != ring[i - 1]]
    if len(ring) < 3:
        raise GeometryError("A parcel needs at least 3 points.")
    if len(ring) > MAX_VERTICES:
        raise GeometryError(f"A parcel can have at most {MAX_VERTICES} points.")
    for lng, lat in ring:
        if not (-180 <= lng <= 180 and -90 <= lat <= 90):
            raise GeometryError("Coordinates out of range: expected [longitude, latitude].")
    return ring


def _in_bbox(lng, lat, bbox=CAMEROON_BBOX):
    return bbox[0] <= lng <= bbox[2] and bbox[1] <= lat <= bbox[3]


def _segments_intersect(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-18 else (1 if v > 0 else -1)

    def on_seg(a, b, c):
        return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])

    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    return (o1 == 0 and on_seg(p1, p2, p3)) or (o2 == 0 and on_seg(p1, p2, p4)) \
        or (o3 == 0 and on_seg(p3, p4, p1)) or (o4 == 0 and on_seg(p3, p4, p2))


def self_intersects(ring: list) -> bool:
    n = len(ring)
    edges = [(ring[i], ring[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue  # adjacent edges share a vertex
            if _segments_intersect(*edges[i], *edges[j]):
                return True
    return False


def validate_polygon(geometry: dict) -> dict:
    """Normalised closed GeoJSON Polygon, or GeometryError."""
    ring = _ring(geometry)
    if not any(_in_bbox(lng, lat) for lng, lat in ring) and all(_in_bbox(lat, lng) for lng, lat in ring):
        raise GeometryError("Latitude and longitude seem swapped: GeoJSON expects [longitude, latitude].")
    if self_intersects(ring):
        raise GeometryError("The parcel outline crosses itself.")
    area = geodesic_area(ring)
    if area < MIN_AREA_M2:
        raise GeometryError("The parcel is too small.")
    if area > MAX_AREA_HA * 10000:
        raise GeometryError(f"The parcel is too large (more than {int(MAX_AREA_HA)} ha).")
    # counter-clockwise exterior ring (RFC 7946)
    if _signed_area_deg(ring) < 0:
        ring = ring[::-1]
    return {"type": "Polygon", "coordinates": [[[lng, lat] for lng, lat in ring] + [[ring[0][0], ring[0][1]]]]}


# ---- Measures -----------------------------------------------
def _signed_area_deg(ring):
    return sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
               for i in range(len(ring))) / 2


def geodesic_area(ring: list) -> float:
    """Area in m² on the sphere (Chamberlain & Duquette, as in Turf)."""
    n = len(ring)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        lo, mi, hi = ring[i - 1], ring[i], ring[(i + 1) % n]
        total += (math.radians(hi[0]) - math.radians(lo[0])) * math.sin(math.radians(mi[1]))
    return abs(total * EARTH_RADIUS_M ** 2 / 2)


def haversine(a, b) -> float:
    lng1, lat1, lng2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def perimeter(ring: list) -> float:
    return sum(haversine(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring)))


class LocalProjection:
    """Equirectangular projection in metres around an origin (fine for parcels)."""

    def __init__(self, lng0: float, lat0: float):
        self.lng0, self.lat0 = lng0, lat0
        self.kx = math.radians(1) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
        self.ky = math.radians(1) * EARTH_RADIUS_M

    def fwd(self, p):
        return ((p[0] - self.lng0) * self.kx, (p[1] - self.lat0) * self.ky)

    def inv(self, q):
        return (self.lng0 + q[0] / self.kx, self.lat0 + q[1] / self.ky)


def _planar_area_centroid(pts):
    a = cx = cy = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a /= 2
    if abs(a) < 1e-12:
        return 0.0, (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return abs(a), (cx / (6 * a), cy / (6 * a))


def ring_of(polygon: dict) -> list:
    pts = [(float(x), float(y)) for x, y in polygon["coordinates"][0]]
    return pts[:-1] if pts[0] == pts[-1] else pts


def centroid(ring: list):
    proj = LocalProjection(*ring[0])
    _, c = _planar_area_centroid([proj.fwd(p) for p in ring])
    return proj.inv(c)


def bbox(ring: list):
    lngs, lats = [p[0] for p in ring], [p[1] for p in ring]
    return [min(lngs), min(lats), max(lngs), max(lats)]


def measures(polygon: dict) -> dict:
    ring = ring_of(polygon)
    lng, lat = centroid(ring)
    return {
        "area_ha": geodesic_area(ring) / 10000,
        "perimeter_m": perimeter(ring),
        "latitude": lat,
        "longitude": lng,
        "bbox": bbox(ring),
    }


# ---- Point in polygon / regions -----------------------------
def point_in_ring(pt, ring) -> bool:
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


_regions = None

# Official names, as in data/cameroon_regions.json; English and unaccented
# spellings are accepted on input and mapped to these.
REGION_NAMES = ("Adamaoua", "Centre", "Est", "Extrême-Nord", "Littoral",
                "Nord", "Nord-Ouest", "Ouest", "Sud", "Sud-Ouest")
_REGION_ALIASES = {"adamawa": "Adamaoua", "east": "Est", "far north": "Extrême-Nord",
                   "far-north": "Extrême-Nord", "north": "Nord", "north west": "Nord-Ouest",
                   "north-west": "Nord-Ouest", "northwest": "Nord-Ouest", "west": "Ouest",
                   "south": "Sud", "south west": "Sud-Ouest", "south-west": "Sud-Ouest",
                   "southwest": "Sud-Ouest", "center": "Centre"}


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).strip().lower()


def canonical_region(value: Optional[str]) -> Optional[str]:
    """Official region name for `value`, None for empty; ValueError otherwise."""
    if value is None or not value.strip():
        return None
    key = _fold(value)
    for name in REGION_NAMES:
        if _fold(name) == key:
            return name
    if key in _REGION_ALIASES:
        return _REGION_ALIASES[key]
    raise ValueError("Unknown region of Cameroon.")


def region_of(lng: float, lat: float) -> Optional[str]:
    global _regions
    if _regions is None:
        try:
            with open(REGIONS_PATH, encoding="utf-8") as f:
                _regions = json.load(f)["features"]
        except OSError:
            _regions = []
    for feat in _regions:
        for poly in feat["geometry"]["coordinates"]:
            if point_in_ring((lng, lat), poly[0]) and not any(point_in_ring((lng, lat), h) for h in poly[1:]):
                return feat["properties"]["region"]
    return None


# ---- Grid + serpentine path ---------------------------------
def _convex_hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _rotate(p, theta):
    c, s = math.cos(theta), math.sin(theta)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def long_axis_angle(pts) -> float:
    """Angle that rotates the minimum-area bounding rectangle so that its long side is along x."""
    hull = _convex_hull(pts)
    best = (float("inf"), 0.0)
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        theta = -math.atan2(b[1] - a[1], b[0] - a[0])
        rot = [_rotate(p, theta) for p in hull]
        xs, ys = [p[0] for p in rot], [p[1] for p in rot]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if w * h < best[0] - 1e-9:
            best = (w * h, theta if w >= h else theta + math.pi / 2)
    return best[1]


def _clip(subject, xmin, ymin, xmax, ymax):
    """Sutherland–Hodgman clipping of a polygon by an axis-aligned rectangle."""
    def clip_edge(points, inside, intersect):
        out = []
        for i in range(len(points)):
            cur, prev = points[i], points[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(intersect(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(intersect(prev, cur))
        return out

    def ix(x):
        return lambda p, q: (x, p[1] + (q[1] - p[1]) * (x - p[0]) / (q[0] - p[0]))

    def iy(y):
        return lambda p, q: (p[0] + (q[0] - p[0]) * (y - p[1]) / (q[1] - p[1]), y)

    pts = subject
    for inside, inter in ((lambda p: p[0] >= xmin, ix(xmin)), (lambda p: p[0] <= xmax, ix(xmax)),
                          (lambda p: p[1] >= ymin, iy(ymin)), (lambda p: p[1] <= ymax, iy(ymax))):
        pts = clip_edge(pts, inside, inter)
        if not pts:
            return []
    return pts


def estimate_cells(polygon: dict, cell_size_m: float) -> int:
    return math.ceil(geodesic_area(ring_of(polygon)) / (cell_size_m ** 2))


def suggest_cell_size(polygon: dict, max_cells: int = MAX_CELLS) -> int:
    return math.ceil(math.sqrt(geodesic_area(ring_of(polygon)) / max_cells) * 1.15)


def build_grid(polygon: dict, cell_size_m: float, start: Optional[tuple] = None,
               speed_mps: float = 0.5, pause_s: float = 3.0) -> dict:
    """
    Square cells of `cell_size_m`, aligned with the parcel's long axis,
    clipped to the parcel and numbered 1..N along a serpentine path.
    `start` = (lng, lat): the path starts at the corner nearest to it.
    Returns {cells, waypoints, distance_m, duration_s, angle_deg}.
    """
    if not (1 <= cell_size_m <= 50):
        raise GeometryError("The cell size must be between 1 and 50 m.")
    if estimate_cells(polygon, cell_size_m) > MAX_CELLS:
        raise GeometryError(f"Too many cells (more than {MAX_CELLS}): use cells of at least "
                            f"{suggest_cell_size(polygon)} m.")

    ring = ring_of(polygon)
    clng, clat = centroid(ring)
    proj = LocalProjection(clng, clat)
    pts = [proj.fwd(p) for p in ring]
    theta = long_axis_angle(pts)
    rpts = [_rotate(p, theta) for p in pts]

    def to_lnglat(q):
        lng, lat = proj.inv(_rotate(q, -theta))
        return [round(lng, 7), round(lat, 7)]

    xs, ys = [p[0] for p in rpts], [p[1] for p in rpts]
    x0, y0 = min(xs), min(ys)
    ncols = max(1, math.ceil((max(xs) - x0) / cell_size_m))
    nrows = max(1, math.ceil((max(ys) - y0) / cell_size_m))

    kept = {}  # (row, col) -> {"poly": [...], "center": (x, y)}
    min_area = MIN_CELL_FRACTION * cell_size_m ** 2
    for r in range(nrows):
        for c in range(ncols):
            xa, ya = x0 + c * cell_size_m, y0 + r * cell_size_m
            clipped = _clip(rpts, xa, ya, xa + cell_size_m, ya + cell_size_m)
            if len(clipped) < 3:
                continue
            area, ctr = _planar_area_centroid(clipped)
            if area < min_area:
                continue
            if not point_in_ring(ctr, rpts):
                # concave piece: fall back to the square's centre or any inside vertex
                for cand in [(xa + cell_size_m / 2, ya + cell_size_m / 2)] + clipped:
                    if point_in_ring(cand, rpts):
                        ctr = cand
                        break
            kept[(r, c)] = {"poly": clipped, "center": ctr, "area": area}
    if not kept:
        raise GeometryError("The parcel is smaller than one cell: choose a smaller cell size.")
    if len(kept) > MAX_CELLS:
        raise GeometryError(f"Too many cells (more than {MAX_CELLS}): use cells of at least "
                            f"{suggest_cell_size(polygon)} m.")

    # Start corner in the rotated frame
    from_top = from_right = False
    if start is not None:
        sx, sy = _rotate(proj.fwd(start), theta)
        from_right = abs(sx - max(xs)) < abs(sx - min(xs))
        from_top = abs(sy - max(ys)) < abs(sy - min(ys))

    rows = sorted({r for r, _ in kept}, reverse=from_top)
    order = []
    left_to_right = not from_right
    for r in rows:
        cols = sorted((c for rr, c in kept if rr == r), reverse=not left_to_right)
        order.extend((r, c) for c in cols)
        left_to_right = not left_to_right

    # Detours: consecutive cells must be neighbours (8-connectivity) on the kept grid
    def neighbours(rc):
        r, c = rc
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if (dr or dc) and (r + dr, c + dc) in kept:
                    yield (r + dr, c + dc)

    def bfs(a, b):
        prev = {a: None}
        q = deque([a])
        while q:
            cur = q.popleft()
            if cur == b:
                path = []
                while cur is not None:
                    path.append(cur)
                    cur = prev[cur]
                return path[::-1]
            for n in neighbours(cur):
                if n not in prev:
                    prev[n] = cur
                    q.append(n)
        return [a, b]  # disconnected parcel pieces: direct move

    # route: (cell, is_capture) — a cell is captured when reached in its numbered
    # turn; cells crossed during a detour are transit only.
    number = {rc: i + 1 for i, rc in enumerate(order)}
    route = [(order[0], True)]
    for a, b in zip(order, order[1:], strict=False):
        if max(abs(a[0] - b[0]), abs(a[1] - b[1])) > 1:
            route.extend((rc, False) for rc in bfs(a, b)[1:-1])
        route.append((b, True))

    waypoints = []
    for i, (rc, capture) in enumerate(route):
        lng, lat = to_lnglat(kept[rc]["center"])
        waypoints.append({"index": i, "cell_index": number[rc], "lat": lat, "lng": lng, "capture": capture})

    cells = []
    for rc, cell in kept.items():
        poly = [to_lnglat(p) for p in cell["poly"]]
        poly.append(poly[0])
        cells.append({
            "index": number[rc], "row": rc[0], "col": rc[1],
            "polygon": poly, "center": to_lnglat(cell["center"]),
            "area_m2": round(cell["area"], 2),
        })
    cells.sort(key=lambda c: c["index"])

    distance = sum(haversine((a["lng"], a["lat"]), (b["lng"], b["lat"]))
                   for a, b in zip(waypoints, waypoints[1:], strict=False))
    return {
        "cells": cells,
        "waypoints": waypoints,
        "distance_m": round(distance, 1),
        "duration_s": round(distance / speed_mps + pause_s * len(cells)),
        "angle_deg": round(math.degrees(-theta) % 180, 2),
        "cell_size_m": cell_size_m,
    }


def cell_at(cells: list, lng: float, lat: float) -> Optional[int]:
    """Index of the cell containing the point, if any."""
    for c in cells:
        ring = c["polygon"][:-1]
        if point_in_ring((lng, lat), ring):
            return c["index"]
    return None
