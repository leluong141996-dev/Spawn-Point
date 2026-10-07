from spawnpoint.graph import parse

from conftest import minimal


def test_minimal_graph_parses():
    g, d = parse(minimal())
    assert g is not None and d.ok
    assert g.settings.tile_size == 32
    assert g.entities["Player"].body == "character"


def test_unknown_field_gets_typo_hint():
    data = minimal()
    data["entities"]["Player"]["compnents"] = {}
    g, d = parse(data)
    assert g is None
    (err,) = d.errors
    assert err.path == "entities.Player.compnents"
    assert err.hint == "Did you mean 'components'?"


def test_missing_required_field():
    data = minimal()
    del data["genre"]
    _, d = parse(data)
    assert any(e.message == "missing required field 'genre'" for e in d.errors)


def test_bad_color_and_genre():
    data = minimal(genre="rpg")
    data["entities"]["Player"]["shape"] = {"color": "blue"}
    _, d = parse(data)
    paths = {e.path for e in d.errors}
    assert "genre" in paths
    assert any(p.startswith("entities.Player.shape.color") for p in paths)


def test_rule_if_alias():
    data = minimal(rules=[{"on": "Exit.triggered", "if": "score > 1", "do": "win()"}])
    g, d = parse(data)
    assert d.ok
    assert g.rules[0].if_ == "score > 1"
    assert g.rules[0].actions == ["win()"]
