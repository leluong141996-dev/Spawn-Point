import pytest

from spawnpoint.diagnostics import Diagnostics
from spawnpoint.expr import ExprError
from spawnpoint.graph import Rule
from spawnpoint.rules import compile_rules, resolve_event

ENTITIES = {
    "Player": ["PlatformerMovement", "PlayerInput", "Health", "Hurtbox", "Stomp"],
    "Slime": ["PlatformerMovement", "PatrolAI", "Health", "Hurtbox", "Hitbox"],
    "Coin": ["Collectible"],
    "Door": ["Gate"],
    "Exit": ["TriggerZone"],
}


def run(manifest, *rules):
    d = Diagnostics()
    res = compile_rules([Rule.model_validate(r) for r in rules], ENTITIES, manifest, d)
    return res, d


def test_short_event_resolves_unique_component(manifest):
    ev = resolve_event("Coin.collected", ENTITIES, manifest)
    assert (ev.component, ev.signal, ev.args) == ("Collectible", "collected", ["by"])


def test_ambiguous_event(manifest):
    with pytest.raises(ExprError) as e:
        resolve_event("Slime.dashed", {"Slime": ["PlatformerMovement", "TopDownMovement"]}, manifest)
    assert "ambiguous" in str(e.value)
    assert "Slime.PlatformerMovement.dashed" in e.value.hint


def test_unknown_signal_lists_available(manifest):
    with pytest.raises(ExprError) as e:
        resolve_event("Door.open", ENTITIES, manifest)
    assert "Door.opened" in e.value.hint


def test_codegen(manifest):
    res, d = run(manifest,
                 {"on": "Coin.collected", "if": "count('Coin') == 0", "do": ["Door.open()", "message('Open!')"]},
                 {"on": "Slime.died", "do": ["add_score(5)", "spawn('Coin')"]},
                 {"on": "Game.ready", "do": "message('Go')"},
                 {"on": "GameState.score_changed", "if": "event.score >= 3", "do": ["win()"]},
                 {"on": "Coin.collected", "do": ["event.by.Health.heal(1)"]})
    assert d.ok, [str(x) for x in d]
    src = res.source
    assert res.calls_win
    assert 'World.bind_signal(&"Coin", &"Collectible", &"collected", _rule_0)' in src
    assert "func _rule_0(_a_by, _source) -> void:" in src
    assert 'World.call_all(&"Door", &"Gate", &"open", [])' in src
    assert 'World.spawn.call_deferred("Coin", source.global_position)' in src
    assert "func _rule_1(source) -> void:" in src
    assert "GameState.score_changed.connect(_rule_3)" in src
    assert "func _rule_3(a_score) -> void:" in src
    assert "_on_game_ready.call_deferred()" in src
    assert 'World.call_on(a_by, &"Health", &"heal", [1])' in src


@pytest.mark.parametrize("rule, code, fragment", [
    ({"on": "Coin.colected", "do": ["win()"]}, "E_RULE_EVENT", "Did you mean"),
    ({"on": "Ghost.died", "do": ["win()"]}, "E_RULE_EVENT", "unknown entity"),
    ({"on": "Exit.triggered", "do": ["wn()"]}, "E_RULE_DO", "unknown action"),
    ({"on": "Exit.triggered", "do": ["Door.opne()"]}, "E_RULE_DO", "no method"),
    ({"on": "Exit.triggered", "do": ["Door.Gate.open(1)"]}, "E_RULE_DO", "argument"),
    ({"on": "Exit.triggered", "do": ["Coin.Gate.open()"]}, "E_RULE_DO", "no component"),
    ({"on": "Game.ready", "do": ["spawn('Coin')"]}, "E_RULE_DO", "has none"),
    ({"on": "Game.ready", "do": ["destroy(self)"]}, "E_RULE_DO", "not available"),
    ({"on": "Exit.triggered", "if": "scor > 1", "do": ["win()"]}, "E_RULE_IF", "unknown name"),
    ({"on": "Exit.triggered", "do": ["set_var(x, 1)"]}, "E_RULE_DO", "quotes"),
    ({"on": "Exit.triggered", "do": ["win"]}, "E_RULE_DO", "must be a call"),
])
def test_rule_errors(manifest, rule, code, fragment):
    _, d = run(manifest, rule)
    assert not d.ok
    err = d.errors[0]
    assert err.code == code
    assert fragment in (err.message + " " + (err.hint or ""))


def test_error_paths_point_at_action(manifest):
    _, d = run(manifest, {"on": "Exit.triggered", "do": ["win()", "nope()"]})
    assert d.errors[0].path == "rules[0].do[1]"
