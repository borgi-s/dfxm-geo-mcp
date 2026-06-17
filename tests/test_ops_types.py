from dfxm_geo_mcp.ops.types import (
    ConfigIssue,
    ForwardResult,
    ReflectionRecord,
    ValidationReport,
)


def test_config_issue_is_frozen():
    issue = ConfigIssue(block="scan.phi", field="steps", problem="missing", fix="add steps")
    assert issue.block == "scan.phi"


def test_validation_report_ok():
    rep = ValidationReport(ok=True, issues=[], resolved=None)
    assert rep.ok and rep.issues == []


def test_reflection_record_fields():
    rec = ReflectionRecord(
        hkl=(1, 1, 1), theta_deg=9.5, eta_deg=0.0, omega_deg=0.0,
        energy_keV=17.0, reachable=True, note="",
    )
    assert rec.hkl == (1, 1, 1) and rec.reachable


def test_forward_result_carries_png():
    res = ForwardResult(png_bytes=b"\x89PNG", stats={"shape": (5, 5), "vmin": 0.0,
                        "vmax": 1.0, "backend": "analytic", "kernel": None, "wall_s": 0.1},
                        bounded=False)
    assert res.png_bytes.startswith(b"\x89PNG")
