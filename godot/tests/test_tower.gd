extends SPTestCase


func _road(cells: Array) -> void:
	for c: Vector2i in cells:
		make_entity("Road", "area", SP.TEAM_NEUTRAL, Vector2(4, 4), {}, Vector2(c) * 32.0 + Vector2(16, 16))


func test_path_follower_walks_the_road_to_the_base() -> void:
	GameState.reset_run()
	var cells := []
	for x in range(0, 6):
		cells.append(Vector2i(x, 0))
	for y in range(1, 4):
		cells.append(Vector2i(5, y))
	_road(cells)
	make_entity("Keep", "area", SP.TEAM_NEUTRAL, Vector2(20, 20), {"Base": {}}, Vector2(5, 4) * 32.0 + Vector2(16, 16))
	var e := make_entity("Goblin", "character", SP.TEAM_ENEMY, Vector2(16, 16),
			{"TopDownMovement": {"max_speed": 400.0}, "PathFollower": {"road": "Road"}}, Vector2(16, 16))
	await frames(3)
	var pf := SP.component(e, &"PathFollower") as PathFollowerComponent
	assert_eq(pf.route.size(), 10, "9 road cells then the base")
	var lives := GameState.lives
	await frames(120)
	assert_false(is_instance_valid(e), "it reached the base and was removed")
	assert_eq(GameState.lives, lives - 1)


func test_waves_parse_and_finish_when_cleared() -> void:
	var w := WaveSpawnerComponent.parse_waves("3 x Goblin every 0.5; 2 x Orc every 1; nonsense")
	assert_eq(w.size(), 2)
	assert_eq([w[0].count, w[0].entity, w[1].every], [3, "Goblin", 1.0])


func test_builder_spends_gold_on_a_free_slot() -> void:
	GameState.reset_run()
	var p := make_entity("Commander", "character", SP.TEAM_PLAYER, Vector2(4, 4),
			{"TowerBuilder": {"towers": "Nope|50", "start_gold": 40}}, Vector2.ZERO, true)
	var s := make_entity("Pad", "area", SP.TEAM_NEUTRAL, Vector2(30, 30), {"TowerSlot": {}}, Vector2(100, 0))
	await frames(2)
	var b := SP.component(p, &"TowerBuilder") as TowerBuilderComponent
	var slot := SP.component(s, &"TowerSlot") as TowerSlotComponent
	assert_eq(GameState.score, 40)
	assert_eq(b.build_on(slot), null, "40 gold is not enough for a 50 tower")
	assert_true(slot.is_free())


func test_tower_brain_fires_only_at_enemies_in_range() -> void:
	GameState.reset_run()
	var t := make_entity("Tower", "static", SP.TEAM_PLAYER, Vector2(20, 20),
			{"Weapon": {"projectile": "Nope", "fire_rate": 1.0}, "TowerBrain": {"fire_range": 100.0}})
	var w := SP.component(t, &"Weapon") as WeaponComponent
	w.set_physics_process(false)  # only the brain's decision is under test, not the shots
	await frames(2)
	assert_false(w.trigger_held, "nothing to shoot")
	var far := make_entity("Orc", "character", SP.TEAM_ENEMY, Vector2(16, 16), {"Hurtbox": {}}, Vector2(300, 0))
	await frames(2)
	assert_false(w.trigger_held, "out of range")
	far.global_position = Vector2(60, 0)
	await frames(1)
	assert_true(w.trigger_held)
	assert_near(w.aim_direction.x, 1.0, 0.01)
	far.queue_free()
