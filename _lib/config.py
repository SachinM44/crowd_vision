"""crowdvision._lib.config — load config/*.yaml relative to the repo root.

All tunables live in config/*.yaml (Hard Rule 5 — nothing hardcoded). This
resolves paths from the installed package so scripts work from any CWD.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    """Repo root == the crowdvision package dir (see pyproject package-dir)."""
    # this file is <root>/_lib/config.py
    return Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    return repo_root() / "config"


@functools.lru_cache(maxsize=None)
def load(name: str) -> dict[str, Any]:
    """Load config/<name>.yaml (name without extension). Cached."""
    path = config_dir() / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def zones() -> dict[str, Any]:
    return load("zones")


def cameras() -> dict[str, Any]:
    return load("cameras")


def playbooks() -> dict[str, Any]:
    return load("playbooks")


def devices() -> dict[str, Any]:
    return load("devices")


def env(key: str, default: str | None = None) -> str | None:
    """Read an environment variable (populated from .env by setup scripts)."""
    return os.environ.get(key, default)
