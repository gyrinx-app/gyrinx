import sys
from dataclasses import dataclass
from pathlib import Path

import click
import jsonschema
import jsonschema.protocols
from referencing import Registry, Resource

from gyrinx.content.management.utils import DataSource, gather_data, gather_schemas


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

    schemas_to_check = set(schema.name for schema in schemas.values())
    data_to_check = set(src.name for src in data_sources)
    missing_schema = data_to_check - schemas_to_check
    if missing_schema:
        for src in data_sources:
            if src.name in missing_schema:
                invalid.append(src)
                errors.append(
                    f"Missing schema for data source: {src.name} (from {src.path})"
                )

    contents = [Resource.from_contents(schema.schema) for schema in schemas.values()]
    registry = Registry().with_resources([(c.id(), c) for c in contents]).crawl()

    for schema in schemas.values():
        click.echo(f"Validating {schema.name} schema (from {schema.path})...")

        data = [src for src in data_sources if src.name == schema.name]

        if not data:
            click.echo(
                f"Warning: No top-level data sources found for schema {schema.name} (from {schema.path})",
                err=True,
            )

        for src in data:
            try:
                jsonschema.validate(src.data, list_of(schema.schema), registry=registry)
                # TODO: detect duplicate uuids across sources
                # TODO: check the schema ID is correct
                # TODO: check the schema title and description
                valid.append(src)
            except jsonschema.exceptions.ValidationError as e:
                invalid.append(src)
                errors.append(
                    f"Error validating {src.name} source (from {src.path}) against schema {schema.name} (from {schema.path}): {e}",
                )

    return ValidationResult(
        success=len(errors) == 0, valid=valid, invalid=invalid, errors=errors
    )


@click.command()
def check():
    click.echo("Checking schema...")
    content_dir = Path("content")
    directories = [d for d in content_dir.iterdir() if d.is_dir()]

    click.echo("Found these ruleset directories:")
    for directory in directories:
        click.echo(f" - {directory}")

    results = []
    for directory in directories:
        click.echo(f"\nChecking {directory}...")

        schemas = gather_schemas(directory)
        data_sources = gather_data(directory)
        click.echo(
            f"Found {len(schemas)} schemas and {len(data_sources)} data sources ({directory})"
        )
        result = validate_sources(schemas, data_sources)

        if result.success:
            click.echo(f"{directory}: All data sources are valid\n")
        else:
            click.echo(f"{directory}: Some data sources are invalid:", err=True)
            for error in result.errors:
                click.echo(f" - {error}", err=True)
            click.echo()

        results.append(result)

    if all(result.success for result in results):
        click.echo("All directories contain valid data sources")
    else:
        click.echo("Some directories contain invalid data sources", err=True)
        sys.exit(1)


if __name__ == "__main__":
    check()
