from dataclasses import dataclass


@dataclass
class ModContext:
    all_stats: dict[str, dict] | None = None
