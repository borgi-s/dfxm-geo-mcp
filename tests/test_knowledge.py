from dfxm_geo_mcp.knowledge.schema import config_schema, example_names, list_examples
from dfxm_geo_mcp.ops.validate import validate_config


def test_schema_has_reciprocal_block():
    schema = config_schema()
    assert "reciprocal" in schema
    assert "keV" in schema["reciprocal"]


def test_examples_all_validate():
    examples = list_examples()
    assert set(example_names()) == set(examples)
    for name, toml in examples.items():
        assert validate_config(toml).ok, name
