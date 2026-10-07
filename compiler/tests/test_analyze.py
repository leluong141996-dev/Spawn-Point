import pytest

from spawnpoint.analyze import analyze

from conftest import codes, minimal


def test_examples_are_clean(manifest, platformer, topdown):
    for g in (platformer, topdown):
        a = analyze(g, manifest)
        assert a.ok, [str(d) for d in a.diagnostics]
        assert not a.diagnostics.warnings, [str(d) for d in a.diagnostics]


def test_plan_shape(manifest):
    a = analyze(minimal(), manifest)
    assert a.ok, [str(d) for d in a.diagnostics]
    plan = a.plan
    player = next(e for e in plan["entities"] if e["name"] == "Player")
    assert player["is_player"] and player["team"] == "player"
    assert player["layer"] == 2 and player["mask"] == 1
    assert player["pivot"] == "bottom"
    names = [c["name"] for c in player["components"]]
    assert names[-1] == "Juice"
    hurtbox = next(c for c in player["components"] if c["name"] == "Hurtbox")
    assert hurtbox["area_scale"] == pytest.approx(0.85)
    # Player feet rest on the floor row (row 2 -> y = 64).
    p = next(p for p in plan["placements"] if p["entity"] == "Player")
    assert p["y"] + 14 == pytest.approx(64)  # default shape is 28 px tall
    # Collectibles float at the cell center.
    c = next(p for p in plan["placements"] if p["entity"] == "Coin")
    assert c["y"] == pytest.approx(48)
    assert plan["map"]["cells"][0] == [0, 2, "solid"]


def test_juice_none_and_overrides(manifest):
    g = minimal()
    g["entities"]["Coin"]["juice"] = "none"
    g["entities"]["Player"]["juice"] = {"shake_on_hurt": 0.9}
    plan = analyze(g, manifest).plan
    coin = next(e for e in plan["entities"] if e["name"] == "Coin")
    assert "Juice" not in [c["name"] for c in coin["components"]]
    player = next(e for e in plan["entities"] if e["name"] == "Player")
    assert player["components"][-1]["params"] == {"shake_on_hurt": 0.9}
    g["settings"] = {"juice": "none"}
    plan = analyze(g, manifest).plan
    assert all(c["name"] != "Juice" for e in plan["entities"] for c in e["components"])


def _with(mutate):
    g = minimal()
    mutate(g)
    return g


def _player(g):
    return g["entities"]["Player"]["components"]


@pytest.mark.parametrize("mutate, code, hint", [
    (lambda g: _player(g).update({"Helth": {}}), "E_UNKNOWN_COMPONENT", "Did you mean 'Health'?"),
    (lambda g: _player(g)["Health"].update({"max_hp": 3}), "E_UNKNOWN_PARAM", "Did you mean 'max_health'?"),
    (lambda g: _player(g)["Health"].update({"max_health": 0}), "E_PARAM_RANGE", None),
    (lambda g: _player(g)["Health"].update({"max_health": 2.5}), "E_PARAM_TYPE", None),
    (lambda g: _player(g)["PlatformerMovement"].update({"max_speed": "fast"}), "E_PARAM_TYPE", None),
    (lambda g: g["entities"]["Coin"]["components"].update({"Gate": {}}), "E_HOST", None),
    (lambda g: _player(g).pop("Health"), "E_REQUIRES", None),
    (lambda g: _player(g).update({"Weapon": {"projectile": "Coin"}}), "E_NOT_PROJECTILE", None),
    (lambda g: _player(g).update({"Weapon": {"projectile": "Bulet"}}), "E_ENTITY_REF", None),
    (lambda g: _player(g).update({"Weapon": {}}), "E_ENTITY_REF", None),
    (lambda g: _player(g).update({"TopDownMovement": {}}), "E_MOVEMENT", None),
    (lambda g: _player(g).pop("PlayerInput"), "E_NO_PLAYER", None),
    (lambda g: g["level"].update(map=["PP........", "##########"]), "E_PLAYER_PLACEMENT", None),
    (lambda g: g["entities"].update({"slime": {}}), "E_ENTITY_NAME", None),
    (lambda g: g["entities"].update({"Health": {}}), "E_ENTITY_NAME", None),
    (lambda g: g["entities"]["Player"].update({"juice": {"shake": 1}}), "E_UNKNOWN_PARAM", None),
    (lambda g: g["entities"]["Coin"].update({"shape": {"type": "none"}}) or g["entities"]["Coin"]["components"].update({"Hitbox": {}}), "E_SHAPE", None),
])
def test_entity_errors(manifest, mutate, code, hint):
    a = analyze(_with(mutate), manifest)
    assert not a.ok
    assert code in codes(a.diagnostics, "error"), [str(d) for d in a.diagnostics]
    if hint:
        assert any(d.hint == hint for d in a.diagnostics.errors)


def test_aim_mode_choice(manifest):
    g = minimal()
    _player(g).update({"Aim": {"mode": "mose"}})
    _player(g).update({"Weapon": {"projectile": "Coin"}})
    a = analyze(g, manifest)
    err = next(d for d in a.diagnostics.errors if d.code == "E_PARAM_CHOICE")
    assert err.hint == "Did you mean 'mouse'?"


def test_warnings(manifest):
    g = minimal(rules=[])
    g["level"]["map"] = [".P........", ".........."]
    a = analyze(g, manifest)
    assert a.ok
    assert set(codes(a.diagnostics, "warning")) >= {"W_NO_WIN", "W_NO_GROUND"}


def test_genre_mismatch_warning(manifest):
    g = minimal(genre="topdown")
    a = analyze(g, manifest)
    assert "W_GENRE" in codes(a.diagnostics, "warning")


def test_topdown_plan(manifest, topdown):
    plan = analyze(topdown, manifest).plan
    assert plan["gravity"] == 0
    assert plan["walls"] == ["left", "right", "top", "bottom"]
    bullet = next(e for e in plan["entities"] if e["name"] == "Bullet")
    assert bullet["layer"] == 0 and bullet["mask"] == 1
    assert all(e["pivot"] == "center" for e in plan["entities"])
