from dfxm_geo_mcp.ops.validate import validate_config


def test_empty_config_is_valid():
    rep = validate_config("")
    assert rep.ok and rep.issues == []
    assert rep.resolved is not None
    assert rep.resolved["reflection"] == (-1, 1, -1)
    assert rep.resolved["n_frames"] == 1


def test_range_without_steps_is_a_value_error_issue():
    rep = validate_config("[scan.phi]\nvalue = 0.0\nrange = 0.001\n")
    assert not rep.ok
    assert any(i.field == "steps" or "steps" in i.problem for i in rep.issues)


def test_unknown_key_is_a_type_error_issue():
    rep = validate_config("[reciprocal]\nnot_a_real_key = 5\n")
    assert not rep.ok and rep.issues


def test_malformed_toml_is_an_issue():
    rep = validate_config("this is not = = toml")
    assert not rep.ok and rep.issues


def test_scanned_config_reports_frames():
    rep = validate_config("[scan.phi]\nvalue = 0.0\nrange = 0.001\nsteps = 5\n")
    assert rep.ok
    assert rep.resolved is not None
    assert rep.resolved["n_frames"] == 5
    assert "phi" in rep.resolved["scanned_axes"]
