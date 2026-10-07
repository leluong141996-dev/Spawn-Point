import json

import pytest

from spawnpoint import godot, manifest as manifest_mod
from spawnpoint.manifest import parse_docs

SOURCE = '''class_name FooComponent
extends Node
## Does foo.
## Second line.

const SP_NAME := "Foo"

## Fired on foo.
signal fooed(amount: int)

## How much foo.
@export_range(0, 10) var amount: int = 3
var _private := 1


## Foos now.
func foo() -> void:
	pass
'''


def test_parse_docs():
    docs = parse_docs(SOURCE)
    assert docs["@class"] == "Does foo. Second line."
    assert docs["fooed"] == "Fired on foo."
    assert docs["amount"] == "How much foo."
    assert docs["foo"] == "Foos now."
    assert "_private" not in docs


def test_manifest_contents(manifest):
    pm = manifest.get("PlatformerMovement")
    assert pm.hosts == ["CharacterBody2D"]
    assert pm.params["coyote_time"].max == 0.5
    assert "step_velocity" not in pm.methods  # internal
    assert pm.signals["landed"].args[0].name == "impact_speed"
    assert manifest.get("Aim").params["mode"].choices == ("mouse", "nearest_enemy", "movement")
    assert manifest.get("Health").state["current"] == "int"
    assert all(c.doc for c in manifest.components.values())
    assert all(p.doc for c in manifest.components.values() for p in c.params.values())


@pytest.mark.skipif(not godot.available(), reason="Godot not installed")
def test_manifest_is_up_to_date(tmp_path):
    fresh = manifest_mod.generate(out=tmp_path / "manifest.json")
    committed = json.loads(manifest_mod.MANIFEST_PATH.read_text())
    assert fresh == committed, "manifest.json is stale: run `spawnpoint manifest`"
