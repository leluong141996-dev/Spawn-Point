"""Bundles the Godot addon and the example graphs into the wheel (spawnpoint/_data)."""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).parent
IGNORE = shutil.ignore_patterns("*.import", "*.uid", "__pycache__", ".godot")


class BuildPyWithData(build_py):
    def run(self):
        super().run()
        data = Path(self.build_lib) / "spawnpoint" / "_data"
        shutil.rmtree(data, ignore_errors=True)
        shutil.copytree(ROOT / "godot" / "addons" / "spawn_point", data / "godot" / "addons" / "spawn_point", ignore=IGNORE)
        shutil.copytree(ROOT / "examples", data / "examples", ignore=IGNORE)


setup(cmdclass={"build_py": BuildPyWithData})
