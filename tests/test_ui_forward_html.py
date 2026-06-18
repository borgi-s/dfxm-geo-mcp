import json

from dfxm_geo_mcp.ui.forward_html import build_rocking_html, build_static_html


def test_static_html_is_self_contained_and_embeds_image():
    html = build_static_html(
        "QUJD",
        {
            "reflection": [-1, 1, -1],
            "energy_keV": 17.0,
            "backend": "analytic",
            "beam": "weak",
        },
    )
    assert html.startswith("<!doctype html>")
    assert "data:image/png;base64,QUJD" in html
    # No external origins.
    assert "http://" not in html and "https://" not in html
    # Metadata surfaced.
    assert "analytic" in html
    assert "-1" in html  # reflection rendered


def test_rocking_html_embeds_all_frames_and_inits_at_one_end():
    frames = ["QUJD", "REVG", "R0hJ"]
    phis = [-6e-4, 0.0, 6e-4]
    intens = [10.0, 50.0, 12.0]
    html = build_rocking_html(frames, phis, intens, {"reflection": [-1, 1, -1], "n_frames": 3})
    assert html.startswith("<!doctype html>")
    # all frames embedded
    for b in frames:
        assert b in html
    # scrubber over 0..N-1, initialized at one end (index 0)
    assert 'type="range"' in html
    assert 'max="2"' in html
    assert 'value="0"' in html
    # curve + data present, no external origins
    assert "<svg" in html
    assert "http://" not in html and "https://" not in html
    # embedded data round-trips
    start = html.index('id="dfxm-data"')
    blob = html[html.index(">", start) + 1 : html.index("</script>", start)]
    data = json.loads(blob)
    assert data["phis"] == phis
    assert data["intensities"] == intens
    assert len(data["frames"]) == 3
    assert data["start"] == 0
