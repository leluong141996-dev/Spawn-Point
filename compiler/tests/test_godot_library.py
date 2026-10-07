"""Runs the GDScript component test-suite (godot/tests) so `pytest` covers everything."""

import pytest

from spawnpoint import godot
from spawnpoint.manifest import LIBRARY_PROJECT

pytestmark = pytest.mark.skipif(not godot.available(), reason="Godot not installed")


def test_component_library_suite():
    godot.import_project(LIBRARY_PROJECT)
    result = godot.run_scene(LIBRARY_PROJECT, "res://tests/run_tests.tscn", fixed_fps=60, check=False, timeout=300)
    summary = [ln for ln in result.output.splitlines() if "tests," in ln]
    assert result.returncode == 0, result.output[-4000:]
    assert summary and summary[-1].endswith(", 0 failures"), result.output[-4000:]
    assert not result.script_errors, result.script_errors
