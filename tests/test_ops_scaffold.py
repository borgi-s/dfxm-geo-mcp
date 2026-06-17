from dfxm_geo_mcp.ops.scaffold import scaffold_config
from dfxm_geo_mcp.ops.validate import validate_config


def test_default_scaffold_validates():
    toml = scaffold_config()
    assert validate_config(toml).ok


def test_fcc_aluminium_scaffold_validates():
    toml = scaffold_config(material="Al", structure_type="fcc", reflection=(1, 1, 1))
    rep = validate_config(toml)
    assert rep.ok, [i.problem for i in rep.issues]


def test_bcc_tungsten_scaffold_validates():
    toml = scaffold_config(
        material="W", structure_type="bcc", reflection=(1, 1, 0),
        geometry_mode="oblique", energy_keV=17.0,
    )
    rep = validate_config(toml)
    assert rep.ok, [i.problem for i in rep.issues]
