import pytest

from spawnpoint.expr import ExprError, Scope, translate


@pytest.fixture
def scope(manifest):
    return Scope(manifest, {"Player": ["Health", "PlatformerMovement"], "Coin": ["Collectible"]},
                 {"by": "a_by"}, self_entity="Player")


@pytest.mark.parametrize("src, expected", [
    ("score >= 10", "(GameState.score >= 10)"),
    ("0 < lives <= 3", "(0 < GameState.lives and GameState.lives <= 3)"),
    ("vars.keys == 2 and not false", '((GameState.get_var("keys") == 2) and (not false))'),
    ("count('Coin') == 0", '(World.count(&"Coin") == 0)'),
    ("count(Coin) == 0", '(World.count(&"Coin") == 0)'),
    ("score / 2 > 1.5", "((float(GameState.score) / 2) > 1.5)"),
    ("score % 3 == 0", "(fposmod(GameState.score, 3) == 0)"),
    ("self.Health.current < 2", '(SP.component(source, &"Health").current < 2)'),
    ("score > 1 && lives > 0 || !true", "(((GameState.score > 1) and (GameState.lives > 0)) or (not true))"),
    ("event.by != null", "(a_by != null)"),
])
def test_translations(scope, src, expected):
    assert translate(src, scope) == expected


def test_exclamation_inside_strings_is_kept(scope):
    assert translate("str('Win!') == 'Win!'", scope) == '(str("Win!") == "Win!")'


@pytest.mark.parametrize("src, fragment", [
    ("__import__('os')", "not allowed"),
    ("score.real", "not allowed"),
    ("Player > 1", "entity type"),
    ("scroe > 1", "unknown name"),
    ("event.nope", "no argument"),
    ("self.Health.hp", "no property"),
    ("self.Gate.is_open", "no component"),
    ("count('Nope')", "unknown entity"),
    ("[1, 2]", "not allowed"),
    ("score ** 2", "not supported"),
])
def test_rejections(scope, src, fragment):
    with pytest.raises(ExprError) as e:
        translate(src, scope)
    assert fragment in str(e.value)


def test_typo_hint(scope):
    with pytest.raises(ExprError) as e:
        translate("scroe > 1", scope)
    assert e.value.hint == "Did you mean 'score'?"


def test_self_unavailable(manifest):
    s = Scope(manifest, {}, {}, None)
    with pytest.raises(ExprError, match="not available"):
        translate("self.Health.current", s)
