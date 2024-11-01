from pathlib import Path

from scripts.schema import DataSource, Schema, validate_sources


def mk_schema(name: str, schema: dict) -> Schema:
    return Schema(
        name,
        Path(f"{name}.schema.json"),
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:{name}",
            **schema,
        },
    )


def test_basic():
    result = validate_sources(
        schemas={
            "test": mk_schema(
                "test",
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            )
        },
        data_sources=[DataSource("test", Path("data/test.yaml"), [{"name": "test"}])],
    )

    assert result.success


def test_basic_failing():
    result = validate_sources(
        schemas={
            "test": mk_schema(
                "test",
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            )
        },
        data_sources=[DataSource("test", Path("data/test.yaml"), [{"name": 1}])],
    )
    assert not result.success


def test_source_without_schema():
    result = validate_sources(
        schemas={
            "test": mk_schema(
                "test",
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            )
        },
        data_sources=[
            DataSource("test", Path("data/test.yaml"), [{"name": "test"}]),
            DataSource("extra", Path("data/extra.yaml"), [{"name": "extra"}]),
        ],
    )
    assert not result.success
