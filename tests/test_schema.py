from pathlib import Path

from src.schema import DataSource, Schema, validate_sources


def test_basic():
    result = validate_sources(
        schemas={
            "test": Schema(
                "test",
                Path("test.schema.json"),
                {"type": "object", "properties": {"name": {"type": "string"}}},
            )
        },
        data_sources=[DataSource("test", Path("data/test.yaml"), [{"name": "test"}])],
    )
    print(result)
    assert result.success


def test_basic_failing():
    result = validate_sources(
        schemas={
            "test": Schema(
                "test",
                Path("test.schema.json"),
                {"type": "object", "properties": {"name": {"type": "string"}}},
            )
        },
        data_sources=[DataSource("test", Path("data/test.yaml"), [{"name": 1}])],
    )
    assert not result.success


def test_source_without_schema():
    result = validate_sources(
        schemas={
            "test": Schema(
                "test",
                Path("test.schema.json"),
                {"type": "object", "properties": {"name": {"type": "string"}}},
            )
        },
        data_sources=[
            DataSource("test", Path("data/test.yaml"), [{"name": "test"}]),
            DataSource("extra", Path("data/extra.yaml"), [{"name": "extra"}]),
        ],
    )
    assert not result.success
