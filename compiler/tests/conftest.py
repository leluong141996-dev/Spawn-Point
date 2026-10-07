import copy
import json
from pathlib import Path

import pytest

from spawnpoint import manifest as manifest_mod

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture(scope="session")
def manifest():
    return manifest_mod.load()


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


@pytest.fixture
def platformer() -> dict:
    return copy.deepcopy(load_example("coin_hopper.json"))


@pytest.fixture
def topdown() -> dict:
    return copy.deepcopy(load_example("neon_arena.json"))


def minimal(**overrides) -> dict:
    g = {
        "name": "Tiny",
        "genre": "platformer",
        "entities": {
            "Player": {"components": {"PlatformerMovement": {}, "PlayerInput": {}, "Health": {}, "Hurtbox": {}}},
            "Coin": {"body": "area", "components": {"Collectible": {}}},
            "Exit": {"body": "area", "components": {"TriggerZone": {}}},
        },
        "level": {"map": ["..........", ".P..C...E.", "##########"],
                  "legend": {"#": "solid", "P": "Player", "C": "Coin", "E": "Exit"}},
        "rules": [{"on": "Exit.triggered", "do": ["win()"]}],
    }
    g.update(overrides)
    return g


def codes(diags, severity=None):
    return [d.code for d in diags if severity is None or d.severity == severity]
