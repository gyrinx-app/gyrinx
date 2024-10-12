import json
import sys
from dataclasses import dataclass
from pathlib import Path

import click
import jsonschema
import jsonschema.protocols
import yaml


@dataclass
class Schema:
    name: str
    path: Path
    schema: dict


@dataclass
class DataSource:
    name: str
    path: Path
    data: dict


def gather_schemas(directory: Path) -> dict[str, Schema]:
    schema_dir = directory / "schema"
    click.echo(f"Gathering data from {schema_dir}...")
    if not schema_dir.exists():
        click.echo(f"Error: No schema folder in {directory}", err=True)
        return {}

    index = {}

    for file in schema_dir.rglob("*.schema.json"):
        click.echo(file)
        try:
            with open(file, "r") as f:
                schema = json.load(f)
                # TODO: Validate schema itself
                name = file.name.replace(".schema.json", "")
                index[name] = Schema(name, file, schema)
        except json.JSONDecodeError as e:
            click.echo(f"Error decoding JSON in {file}: {e}", err=True)
        except jsonschema.exceptions.SchemaError as e:
            click.echo(f"Invalid JSON schema in {file}: {e}", err=True)

    return index


def gather_data(directory: Path) -> list[DataSource]:
    data_dir = directory / "data"
    click.echo(f"Gathering data from {data_dir}...")
    if not data_dir.exists():
        click.echo(f"Error: No data folder in {directory}", err=True)
        return {}

    data_sources = []

    for file in data_dir.rglob("*.yaml"):
        click.echo(file)
        try:
            with open(file, "r") as f:
                loaded = yaml.load(f, Loader=yaml.SafeLoader)
                for key in loaded:
                    data_sources.append(DataSource(key, file, loaded[key]))
        except json.JSONDecodeError as e:
            click.echo(f"Error decoding JSON in {file}: {e}", err=True)

    return data_sources


def list_of(schema):
    return {
        "type": "array",
        "items": schema,
    }


@dataclass
class ValidationResult:
    success: bool
    valid: list[DataSource]
    invalid: list[DataSource]
    errors: list[jsonschema.exceptions.ValidationError]


def validate_sources(schemas, data_sources) -> ValidationResult:
    valid = []
    invalid = []
    errors = []

    for schema in schemas.values():
        click.echo(f"Validating {schema.name} schema (from {schema.path})...")

        data = [src for src in data_sources if src.name == schema.name]

        for src in data:
            try:
                jsonschema.validate(src.data, list_of(schema.schema))
                valid.append(src)
            except jsonschema.exceptions.ValidationError as e:
                invalid.append(src)
                errors.append(
                    f"Error validating {src.name} source (from {src.path}) against schema {schema.name} (from {schema.path}): {e}",
                )

    return ValidationResult(
        success=len(invalid) == 0, valid=valid, invalid=invalid, errors=errors
    )


@click.command()
def check():
    click.echo("Checking schema...")
    content_dir = Path("content")
    directories = [d for d in content_dir.iterdir() if d.is_dir()]

    results = []
    for directory in directories:
        click.echo(directory)
        schemas = gather_schemas(directory)
        click.echo(f"Found schemas: {", ".join(schemas.keys())}")

        data_sources = gather_data(directory)

        result = validate_sources(schemas, data_sources)
        if result.success:
            click.echo(f"{directory}: All data sources are valid")
        else:
            click.echo(f"{directory}: Some data sources are invalid:", err=True)
            for error in result.errors:
                click.echo(f"{error}", err=True)

        results.append(result)

    if all(result.success for result in results):
        click.echo("All directories contain valid data sources")
    else:
        click.echo("Some directories contain invalid data sources", err=True)
        sys.exit(1)


if __name__ == "__main__":
    check()
