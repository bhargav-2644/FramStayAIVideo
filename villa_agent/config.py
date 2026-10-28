"""Load config.yaml and the secrets that live in environment variables."""

from __future__ import annotations

import os
from pathlib import Path

import yaml


class Config(dict):
    """config.yaml as a dict, plus the data folder and secret lookups."""

    def __init__(self, data: dict, data_dir: Path):
        super().__init__(data)
        self.data_dir = data_dir

    @property
    def paused(self) -> bool:
        return bool(self.get("pause"))

    @property
    def dry_run(self) -> bool:
        return bool(self.get("dry_run", True))

    def section(self, name: str) -> dict:
        return self.get(name) or {}

    @staticmethod
    def secret(name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError(f"set the {name} environment variable (see .env.example)")
        return value


def load_env(path: Path) -> None:
    """Read KEY=value lines from a .env file without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load(path: Path, data_dir: Path | None = None) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; copy config.example.yaml to {path.name}")
    load_env(path.parent / ".env")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config(data, data_dir or path.parent / "data")
