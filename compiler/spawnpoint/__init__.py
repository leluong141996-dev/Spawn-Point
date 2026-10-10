"""Spawn Point: compile JSON game graphs into runnable Godot 4 projects."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("spawnpoint-studio")  # single source of truth: pyproject.toml
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+source"
