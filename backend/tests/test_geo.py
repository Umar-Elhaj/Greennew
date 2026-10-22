"""Parcel geometry: validation, measures, regions, grid and serpentine path (lot 5)."""

import math

import pytest

import geo

LAT0, LNG0 = 3.85, 11.50          # near Yaoundé
M_LAT = 1 / 111195.0               # degrees per metre (latitude)
M_LNG = 1 / (111195.0 * math.cos(math.radians(LAT0)))


def poly_m(points_m, origin=(LNG0, LAT0)):
    """GeoJSON Polygon from (x, y) metre offsets."""
    ring = [[origin[0] + x * M_LNG, origin[1] + y * M_LAT] for x, y in points_m]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


def rotated_rect(w, h, deg):
    t = math.radians(deg)
    pts = [(0, 0), (w, 0), (w, h), (0, h)]
    return poly_m([(x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t)) for x, y in pts])


# ---- validation & measures -----------------------------------
def test_square_area_within_one_percent():
    m = geo.measures(geo.validate_polygon(poly_m([(0, 0), (100, 0), (100, 100), (0, 100)])))
    assert abs(m["area_ha"] - 1.0) < 0.01
    assert abs(m["perimeter_m"] - 400) < 4
    assert abs(m["latitude"] - (LAT0 + 50 * M_LAT)) < 1e-6


def test_self_intersecting_polygon_rejected():
    bowtie = poly_m([(0, 0), (100, 100), (100, 0), (0, 100)])
    with pytest.raises(geo.GeometryError, match="crosses itself"):
        geo.validate_polygon(bowtie)


def test_swapped_coordinates_detected():
    g = poly_m([(0, 0), (100, 0), (100, 100)])
    g["coordinates"][0] = [[lat, lng] for lng, lat in g["coordinates"][0]]
    with pytest.raises(geo.GeometryError, match="swapped"):
        geo.validate_polygon(g)


@pytest.mark.parametrize("bad", [
    {"type": "Point", "coordinates": [1, 2]},
    {"type": "Polygon", "coordinates": [[[11.5, 3.8], [11.6, 3.8]]]},
    {"type": "Polygon", "coordinates": [[[11.5, 3.8], [11.6, 3.8], [11.6, 95], [11.5, 3.8]]]},
    {"type": "Polygon", "coordinates": [[["a", 3.8], [11.6, 3.8], [11.6, 3.9]]]},
])
def test_invalid_geometries(bad):
    with pytest.raises(geo.GeometryError):
        geo.validate_polygon(bad)


def test_ring_is_closed_and_counter_clockwise():
    clockwise = poly_m([(0, 0), (0, 50), (50, 50), (50, 0)])
    out = geo.validate_polygon(clockwise)
    ring = out["coordinates"][0]
    assert ring[0] == ring[-1]
    assert geo._signed_area_deg([tuple(p) for p in ring[:-1]]) > 0


@pytest.mark.parametrize("lng,lat,region", [
    (9.2416, 4.1597, "Sud-Ouest"),       # Buea (was 'Littoral' with the old bounding boxes)
    (9.7679, 4.0511, "Littoral"),        # Douala
    (11.5021, 3.8480, "Centre"),         # Yaoundé
    (13.3921, 9.3017, "Nord"),           # Garoua
    (14.3158, 10.5910, "Extrême-Nord"),  # Maroua
    (10.4175, 5.4737, "Ouest"),          # Bafoussam
    (2.35, 48.85, None),                 # Paris
])
def test_region_of(lng, lat, region):
    assert geo.region_of(lng, lat) == region


# ---- grid & path ---------------------------------------------
def _adjacent(cells_by_index, a, b):
    ca, cb = cells_by_index[a], cells_by_index[b]
    return max(abs(ca["row"] - cb["row"]), abs(ca["col"] - cb["col"])) <= 1


def _check_path(g):
    by_index = {c["index"]: c for c in g["cells"]}
    wps = g["waypoints"]
    for a, b in zip(wps, wps[1:]):
        assert _adjacent(by_index, a["cell_index"], b["cell_index"]), (a, b)
    captured = [w["cell_index"] for w in wps if w["capture"]]
    assert captured == list(range(1, len(g["cells"]) + 1))   # every cell once, in numbering order


def test_rectangle_grid_count_and_serpentine():
    g = geo.build_grid(poly_m([(0, 0), (50, 0), (50, 20), (0, 20)]), 5)
    assert len(g["cells"]) == 40
    _check_path(g)
    assert len(g["waypoints"]) == 40            # no detour needed
    first_row = [c for c in g["cells"] if c["index"] <= 10]
    assert len({c["row"] for c in first_row}) == 1   # rows follow the long (50 m) side
    # serpentine: row 2 is walked in the opposite direction
    row = {c["index"]: c["col"] for c in g["cells"]}
    assert row[1] < row[10] and row[11] > row[20]
    assert 40 * 5 * 0.9 < g["distance_m"] < 40 * 5 * 1.1


def test_grid_aligned_with_long_axis_of_rotated_parcel():
    g = geo.build_grid(rotated_rect(50, 20, 37), 5)
    assert len(g["cells"]) == 40
    assert abs(g["angle_deg"] - 37) < 1 or abs(g["angle_deg"] - 37 - 180) < 1
    _check_path(g)


def test_concave_parcel_path_never_jumps():
    # U shape: two 10 m wide arms joined at the bottom
    u = poly_m([(0, 0), (40, 0), (40, 40), (30, 40), (30, 10), (10, 10), (10, 40), (0, 40)])
    g = geo.build_grid(u, 5)
    _check_path(g)
    assert len(g["waypoints"]) > len(g["cells"])   # some transit waypoints were needed


def test_start_corner():
    rect = poly_m([(0, 0), (50, 0), (50, 20), (0, 20)])
    far = (LNG0 + 50 * M_LNG, LAT0 + 20 * M_LAT)
    g = geo.build_grid(rect, 5, start=far)
    first = g["waypoints"][0]
    assert abs(first["lng"] - (LNG0 + 47.5 * M_LNG)) < 1e-6 and abs(first["lat"] - (LAT0 + 17.5 * M_LAT)) < 1e-6


def test_too_many_cells_suggests_a_size():
    big = poly_m([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])   # 100 ha
    with pytest.raises(geo.GeometryError, match=r"at least (\d+) m") as e:
        geo.build_grid(big, 5)
    size = int(__import__("re").search(r"at least (\d+) m", str(e.value)).group(1))
    assert len(geo.build_grid(big, size)["cells"]) <= geo.MAX_CELLS


def test_cell_size_bounds_and_lookup():
    rect = poly_m([(0, 0), (50, 0), (50, 20), (0, 20)])
    with pytest.raises(geo.GeometryError):
        geo.build_grid(rect, 0.5)
    with pytest.raises(geo.GeometryError):
        geo.build_grid(rect, 60)
    g = geo.build_grid(rect, 5)
    c7 = next(c for c in g["cells"] if c["index"] == 7)
    assert geo.cell_at(g["cells"], *c7["center"]) == 7
    assert geo.cell_at(g["cells"], LNG0 - 0.01, LAT0) is None
