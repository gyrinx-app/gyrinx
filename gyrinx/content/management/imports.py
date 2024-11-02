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
        for d in data:
            suuid = stable_uuid(config.id(d))
            obj = config.model.objects.filter(uuid=suuid).first()
            if obj:
                click.echo(f" - Existing: {config.id(d)} ({obj.uuid}, {obj.version})")

                obj.update(
                    version=self.iv,
                    **config.fields(d),
                )
            else:
                obj = config.model(
                    version=self.iv,
                    uuid=suuid,
                    **config.fields(d),
                )

            click.echo(f" - {obj} ({obj.uuid}, {obj.version})")
            if not self.dry_run:
                obj.save()
