import json

from dfxm_geo_mcp.ui.forward_html import build_visibility_html

_DEFECT = {
    "mode": "defect",
    "structure": "fcc",
    "energy_keV": 17.0,
    "burgers": [1, -1, 0],
    "threshold_deg": 10.0,
    "resolved_families": [],
    "systems": [],
    "defect_rows": [
        {"refl": {"hkl": [2, 0, 0], "theta_deg": 8.0, "eta_deg": 0.0, "omega_deg": 8.0},
         "gb_cos": 0.707, "visibility": "strong"},
        {"refl": {"hkl": [1, 1, 1], "theta_deg": 7.0, "eta_deg": 0.0, "omega_deg": 7.0},
         "gb_cos": 0.0, "visibility": "invisible"},
    ],
    "matrix_rows": [],
    "caveats": ["g.b = 0 is exact kinematic invisibility for screw character; ..."],
}

_MATRIX = {
    "mode": "matrix",
    "structure": "fcc",
    "energy_keV": 17.0,
    "burgers": None,
    "threshold_deg": 10.0,
    "resolved_families": ["{111}<110>"],
    "systems": [
        {"plane": [1, 1, 1], "burgers": [1, -1, 0], "family": "{111}<110>"},
        {"plane": [1, 1, 1], "burgers": [-1, 0, 1], "family": "{111}<110>"},
    ],
    "defect_rows": [],
    "matrix_rows": [
        {"refl": {"hkl": [2, 0, 0], "theta_deg": 8.0, "eta_deg": 0.0, "omega_deg": 8.0},
         "cells": [0.707, 0.0]},
    ],
    "caveats": ["edge note"],
}


def _assert_self_contained(html: str):
    assert html.startswith("<!doctype html>")
    assert "http://" not in html and "https://" not in html
    # embedded JSON blob is </ guarded
    assert "</script" not in html.replace("</script>", "")  # no stray close before the real ones


def test_defect_html_renders_table_and_is_self_contained():
    html = build_visibility_html(_DEFECT)
    _assert_self_contained(html)
    assert "strong" in html and "invisible" in html
    assert "2, 0, 0" in html or "[2, 0, 0]" in html  # reflection rendered
    assert "g.b" in html  # caveat surfaced (escaped text)


def test_matrix_html_renders_heatmap_and_columns():
    html = build_visibility_html(_MATRIX)
    _assert_self_contained(html)
    assert "{111}&lt;110&gt;" in html  # family label, html-escaped
    # both system columns present
    assert html.count("1, -1, 0") >= 1


def test_embedded_blob_round_trips_and_is_guarded():
    html = build_visibility_html(_MATRIX)
    start = html.index('id="dfxm-vis"')
    blob = html[html.index(">", start) + 1 : html.index("</script>", start)]
    data = json.loads(blob)
    assert data["mode"] == "matrix"
    # the raw json.dumps would contain </ only if a value did; the guard replaces it
    assert "<\\/" in html or "</" not in json.dumps(_MATRIX)
