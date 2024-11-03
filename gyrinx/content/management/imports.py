import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import click
from django.db import models

from gyrinx.content.management.utils import DataSource, data_for_type, stable_uuid
from gyrinx.content.models import ContentImportVersion


@dataclass
class ImportConfig:
    source: str
    id: callable
    model: models.Model
    fields: callable
    allow_removal: bool = False


class Importer:
    def __init__(self, ruleset_dir: Path, directory: str, dry_run: bool = False):
        self.dry_run = dry_run
        self.index = defaultdict(dict)

        self.iv = ContentImportVersion(
            uuid=stable_uuid(f"{ruleset_dir.name}:{uuid.uuid4()}"),
            ruleset=ruleset_dir.name,
            directory=directory,
        )
        click.echo(
            f"ImportingVersion: {self.iv.directory}, {self.iv.ruleset} ({self.iv.uuid})"
        )
        if not self.dry_run:
            self.iv.save()

    def do(self, config: ImportConfig, data_sources: list[DataSource]):
        data = data_for_type(config.source, data_sources)
        click.echo(f"Found {len(data)} for {config.source}: ")

        # Compare the imported data to the existing objects
        # and check for issues.
        all_existing = config.model.objects.all()
        if all_existing:
            # Check for removal
            if len(all_existing) > len(data):
                click.echo(
                    f"Warning: Found {len(all_existing)} existing {config.model} objects, but only {len(data)} in the data sources."
                )
                if not config.allow_removal:
                    raise ValueError(
                        "Data sources do not match existing objects: something was removed and allow_removal is False."
                    )

            # Check for changes in the ID fields — this is a breaking change so we error
            existing_uuids = set(obj.uuid for obj in all_existing)
            new_uuids = set(stable_uuid(config.id(d)) for d in data)
            if len(all_existing) == len(data) and existing_uuids - new_uuids:
                if not config.allow_removal:
                    raise ValueError(
                        "Data sources do not match existing objects: an ID field has changed."
                    )

        suuids = set()
        for d in data:
            suuid = stable_uuid(config.id(d))
            suuids.add(suuid)
            # TODO: Check for duplicate UUIDs
            obj = config.model.objects.filter(uuid=suuid).first()
            if obj:
                click.echo(f" - Existing: {obj} ({obj.uuid}, {obj.version})")

                obj.version = self.iv
                for k, v in config.fields(d).items():
                    setattr(obj, k, v)
            else:
                obj = config.model(
                    version=self.iv,
                    uuid=suuid,
                    **config.fields(d),
                )

                click.echo(f" - New: {obj} ({obj.uuid}, {obj.version})")

            self.index[config.source][obj.uuid] = obj

            if not self.dry_run:
                obj.save()

        if config.allow_removal:
            for obj in all_existing:
                if obj.uuid not in suuids:
                    click.echo(f" - Removing: {obj} ({obj.uuid}, {obj.version})")
                    if not self.dry_run:
                        obj.delete()
