extends SPTestCase


func test_entity_at_finds_bodies_and_near_misses() -> void:
	var slime := make_entity("Slime", "character", SP.TEAM_ENEMY, Vector2(20, 20), {"Health": {}}, Vector2(100, 100))
	var coin := make_entity("Coin", "area", SP.TEAM_NEUTRAL, Vector2(8, 8), {"Collectible": {}}, Vector2(300, 100))
	await frames(2)
	assert_eq(Cockpit.entity_at(Vector2(104, 98)), slime, "direct hit:")
	assert_eq(Cockpit.entity_at(Vector2(318, 100)), coin, "near miss within radius:")
	assert_eq(Cockpit.entity_at(Vector2(600, 600)), null, "nothing there:")


func test_select_emits() -> void:
	var slime := make_entity("Slime", "character", SP.TEAM_ENEMY, Vector2(20, 20), {"Health": {}}, Vector2(100, 100))
	var got := []
	var cb := func(e: Node) -> void: got.append(e)
	Cockpit.selected.connect(cb)
	Cockpit.select(slime)
	Cockpit.selected.disconnect(cb)
	assert_eq(got, [slime])
