extends SPTestCase


func _board(params := {}) -> BubbleBoardComponent:
	GameState.reset_run()
	var base := {"columns": 6, "rows": 0, "height_rows": 10, "colors": 3, "layout_seed": 5}
	base.merge(params, true)
	var p := make_entity("Dino", "character", SP.TEAM_PLAYER, Vector2(20, 20), {"BubbleBoard": base},
			Vector2(300, 400), true)
	return SP.component(p, &"BubbleBoard") as BubbleBoardComponent


func test_hex_neighbors_respect_row_offsets() -> void:
	var b := _board()
	await frames(1)
	assert_eq(b.neighbors(Vector2i(0, 0)).size(), 2)  # top-left corner: right and one below
	assert_eq(b.neighbors(Vector2i(2, 2)).size(), 6)
	assert_true(Vector2i(2, 2) in b.neighbors(Vector2i(2, 1)) and Vector2i(3, 2) in b.neighbors(Vector2i(2, 1)))
	assert_true(b.cell_center(Vector2i(0, 1)).x > b.cell_center(Vector2i(0, 0)).x, "odd rows are offset")


func test_three_of_a_colour_pop_and_orphans_fall() -> void:
	var b := _board()
	await frames(1)
	# Row 0: red red blue; (0,1) green hangs only from the two reds.
	b._grid = {Vector2i(0, 0): 0, Vector2i(1, 0): 0, Vector2i(2, 0): 1, Vector2i(0, 1): 2}
	b.place(Vector2i(3, 0), 1)  # two blues: no pop
	assert_eq(b.egg_count(), 5)
	b._grid.erase(Vector2i(3, 0))
	var before := GameState.score
	b.place(Vector2i(1, 1), 0)  # under (1,0): three reds pop
	assert_false(b._grid.has(Vector2i(0, 0)) or b._grid.has(Vector2i(1, 0)) or b._grid.has(Vector2i(1, 1)), "reds popped")
	assert_false(b._grid.has(Vector2i(0, 1)), "the green orphan fell")
	assert_eq(b._grid.keys(), [Vector2i(2, 0)])
	assert_eq(GameState.score - before, 3 * 10 + 20)


func test_cleared_and_overflowed_signals() -> void:
	var b := _board({"height_rows": 4})
	await frames(1)
	var events := []
	b.cleared.connect(func() -> void: events.append("cleared"))
	b._grid = {Vector2i(0, 0): 1, Vector2i(1, 0): 1}
	b.place(Vector2i(2, 0), 1)
	assert_eq(b.egg_count(), 0)
	var c := _board({"height_rows": 4, "shots_per_drop": 1})
	await frames(1)
	c.overflowed.connect(func() -> void: events.append("overflowed"))
	c._grid = {Vector2i(0, 0): 0, Vector2i(0, 2): 1}
	c._grid[Vector2i(0, 1)] = 2
	c.place(Vector2i(5, 0), 1)  # no pop; the ceiling drops one row: (0,2) reaches the last row
	assert_eq(events, ["cleared", "overflowed"])


func test_a_shot_travels_bounces_and_sticks() -> void:
	var b := _board({"rows": 3, "shot_speed": 1500.0})
	await frames(1)
	var n := b.egg_count()
	b.shoot_at(deg_to_rad(-60.0))  # toward the right wall first
	await frames(90)
	assert_false(b._shot_active, "the shot landed")
	assert_true(b.egg_count() == n + 1 or b.egg_count() < n, "it stuck (or popped a group)")
