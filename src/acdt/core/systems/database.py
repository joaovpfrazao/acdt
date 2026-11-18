"""Example component database loader (see data/components.yaml header: EXAMPLE DATA)."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml


@dataclass
class ComponentDB:
    motors: list[dict]
    escs: list[dict]
    cells: list[dict]
    servos: list[dict]
    autopilots: list[dict]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ComponentDB":
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(**{k: d.get(k, []) for k in ("motors", "escs", "cells", "servos", "autopilots")})

    def merged(self, extra: dict | None) -> "ComponentDB":
        """User-supplied components (e.g. real datasheets) are added in front of the examples."""
        if not extra:
            return self
        return ComponentDB(**{k: list(extra.get(k, [])) + getattr(self, k)
                              for k in ("motors", "escs", "cells", "servos", "autopilots")})


def load_default_db() -> ComponentDB:
    with resources.as_file(resources.files("acdt.core") / "data" / "components.yaml") as p:
        return ComponentDB.from_yaml(p)


def load_standards() -> list[dict]:
    with resources.as_file(resources.files("acdt.core") / "data" / "standards.yaml") as p:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
