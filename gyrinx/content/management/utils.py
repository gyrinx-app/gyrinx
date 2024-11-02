import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import click
import jsonschema
import yaml
from django.db import models


@dataclass
class DataSource:
    name: str
    path: Path
    data: dict


@dataclass
class Schema:
    name: str
    path: Path
    schema: dict


def gather_data(directory: Path) -> list[DataSource]:
    data_dir = directory / "data"
    click.echo(f"Gathering data files from {data_dir}...")
    if not data_dir.exists():
        click.echo(f"Error: No data folder in {directory}", err=True)
        return {}

    data_sources = []

    for file in data_dir.rglob("*.yaml"):
        click.echo(f" - {file}")
        try:
            with open(file, "r") as f:
                loaded = yaml.load(f, Loader=yaml.SafeLoader)
                for key in loaded:
                    data_sources.append(DataSource(key, file, loaded[key]))
        # TODO: mistake, this should be a yaml Error
        except json.JSONDecodeError as e:
            click.echo(f"Error decoding JSON in {file}: {e}", err=True)

    return data_sources


def flatten(xss):
    """
    Flattens a list of lists into a single list.

    Args:
        xss (list of lists): A list where each element is a list.

    Returns:
        list: A single list containing all the elements of the sublists.
    """
    return [x for xs in xss for x in xs]


def data_for_type(name: str, data_sources: list[DataSource]) -> list:
    """
    Retrieves and flattens data from data sources that match the given name.

    Args:
        name (str): The name of the data source to filter by.
        data_sources (list[DataSource]): A list of DataSource objects to search through.

    Returns:
        list: A flattened list of data from the data sources that match the given name.
    """
    return flatten([src.data for src in data_sources if src.name == name])


def gather_schemas(directory: Path) -> dict[str, Schema]:
    schema_dir = directory / "schema"
    click.echo(f"Gathering schema files from {schema_dir}...")
    if not schema_dir.exists():
        click.echo(f"Error: No schema folder in {directory}", err=True)
        return {}

    index = {}

    for file in schema_dir.rglob("*.schema.json"):
        click.echo(f" - {file}")
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


def by_label(enum: type[models.Choices], label: str) -> str:
    """
    Retrieve the name of an enum member based on its label.

    Args:
        enum (type[models.Choices]): The enumeration class containing the choices.
        label (str): The label of the enum member to find.

    Returns:
        str: The name of the enum member corresponding to the given label.

    Raises:
        ValueError: If the label is not found in the enum choices.
    """
    try:
        return next(
            name for name, choice_label in enum.choices if choice_label == label
        )
    except StopIteration:
        raise ValueError(f"Label '{label}' not found in choices: {enum.choices}")


def stable_uuid(v):
    return uuid.UUID(hashlib.md5(v.encode()).hexdigest()[:32])
