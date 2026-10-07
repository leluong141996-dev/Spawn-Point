from spawnpoint.diagnostics import Diagnostics
from spawnpoint.graph import Level
from spawnpoint.level import Placement, jump_model, parse_level, unreachable


def parse(rows, legend, entities=("Player", "Coin")):
    d = Diagnostics()
    data = parse_level(Level(map=rows, legend=legend), set(entities), d)
    return data, d


def test_tiles_and_placements():
    data, d = parse(["P.C", "#=#"], {"#": "solid", "=": "oneway", "P": "Player", "C": "Coin"})
    assert d.ok
    assert data.tiles == {(0, 1): "solid", (1, 1): "oneway", (2, 1): "solid"}
    assert [(p.entity, p.x, p.y) for p in data.placements] == [("Player", 0, 0), ("Coin", 2, 0)]


def test_ragged_rows_are_padded():
    data, d = parse(["P", "###"], {"#": "solid", "P": "Player"})
    assert d.ok and data.width == 3


def test_unknown_char_reported_once_with_positions():
    _, d = parse(["P.X.X", "#####"], {"#": "solid", "P": "Player"})
    (err,) = d.errors
    assert err.code == "E_MAP_CHAR" and "(2,0), (4,0)" in err.message


def test_bad_legend_value_hint():
    _, d = parse(["P", "#"], {"#": "solidd", "P": "Player"})
    assert d.errors[0].hint == "Did you mean 'solid'?"


def test_reserved_legend_key():
    _, d = parse(["P", "#"], {"#": "solid", ".": "Coin", "P": "Player"})
    assert d.errors[0].code == "E_LEGEND_KEY"


def test_reachability():
    rows = [
        "..........C",  # far above anything the player can stand on
        "...........",
        "...........",
        "...........",
        "...........",
        "......C....",
        "...........",
        "....===....",
        "...........",
        ".P.........",
        "###########",
    ]
    data, d = parse(rows, {"#": "solid", "=": "oneway", "P": "Player", "C": "Coin"})
    jm = jump_model(620, 1600, 1.7, 230, 32, 34)
    coins = [p for p in data.placements if p.entity == "Coin"]
    missing = unreachable(data, (1, 9), coins, jm)
    assert missing == [Placement("Coin", 10, 0)]


def test_double_jump_extends_reach():
    single = jump_model(620, 1600, 1.7, 230, 32, 34)
    double = jump_model(620, 1600, 1.7, 230, 32, 34, air_jumps=1)
    assert double.up > single.up
