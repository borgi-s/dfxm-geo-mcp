import dataclasses

from dfxm_geo_mcp.ops.types import (
    DefectRow,
    MatrixRow,
    ReflGeom,
    SlipSystemLabel,
    VisibilityResult,
)


def test_dataclasses_construct_and_asdict_round_trips():
    geom = ReflGeom(hkl=(1, 1, 1), theta_deg=8.0, eta_deg=0.0, omega_deg=8.0)
    res = VisibilityResult(
        mode="defect",
        structure="fcc",
        energy_keV=17.0,
        burgers=(1, -1, 0),
        threshold_deg=10.0,
        resolved_families=[],
        systems=[SlipSystemLabel(plane=(1, 1, 1), burgers=(1, -1, 0), family="{111}<110>")],
        defect_rows=[DefectRow(refl=geom, gb_cos=0.0, visibility="invisible")],
        matrix_rows=[MatrixRow(refl=geom, cells=[0.0, 0.7])],
        caveats=["edge note"],
    )
    d = dataclasses.asdict(res)
    assert d["mode"] == "defect"
    assert d["defect_rows"][0]["visibility"] == "invisible"
    assert d["defect_rows"][0]["refl"]["hkl"] == (1, 1, 1)
    assert d["matrix_rows"][0]["cells"] == [0.0, 0.7]
    assert d["systems"][0]["family"] == "{111}<110>"
