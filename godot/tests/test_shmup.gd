extends SPTestCase
## The pieces of a side-scrolling shooter: flight patterns, the ship that powers up, boss health bars, wave gates.


func _enemy(pattern: String, pos: Vector2, extra := {}) -> Node2D:
	var fp := {"pattern": pattern, "heading_deg": 180.0}
	fp.merge(extra, true)
	return make_entity("Drone", "character", SP.TEAM_ENEMY, Vector2(20, 20),
			{"TopDownMovement": {"max_speed": 120.0, "acceleration": 20000.0}, "FlightPath": fp}, pos)


func test_straight_flies_left() -> void:
	var e := _enemy("straight", Vector2(700, 300))
	await frames(30)
	assert_true(e.global_position.x < 700.0 - 40.0, "moved left:")
	assert_near(e.global_position.y, 300.0, 1.0, "and stayed level:")


func test_wave_swings_up_and_down_while_advancing() -> void:
	var e := _enemy("wave", Vector2(800, 300), {"amplitude": 60.0, "frequency": 1.0})
	var low := 1e9
	var high := -1e9
	for i in 90:
		await frames(1)
		low = minf(low, e.global_position.y)
		high = maxf(high, e.global_position.y)
	assert_true(high - low > 30.0, "swung %.0f px:" % (high - low))
	assert_true(e.global_position.x < 800.0 - 60.0, "advanced:")


func test_dive_turns_toward_the_players_height() -> void:
	make_entity("Player", "character", SP.TEAM_PLAYER, Vector2(24, 24), {"TopDownMovement": {}}, Vector2(100, 450), true)
	var e := _enemy("dive", Vector2(800, 150))
	await frames(60)
	assert_true(e.global_position.y > 220.0, "dipped toward the player (y=%.0f):" % e.global_position.y)


func test_hover_stops_and_bobs() -> void:
	var e := _enemy("hover", Vector2(900, 270), {"hover_at": 0.7, "amplitude": 100.0, "frequency": 0.8})
	await frames(120)  # fly in
	var x0 := e.global_position.x
	assert_true(x0 < 960.0 * 0.7 + 12.0 and x0 > 960.0 * 0.7 - 40.0, "stopped near 70%% (x=%.0f):" % x0)
	var ys: Array[float] = []
	for i in 80:
		await frames(1)
		ys.append(e.global_position.y)
	assert_near(e.global_position.x, x0, 6.0, "holds its place:")
	assert_true(ys.max() - ys.min() > 40.0, "bobs:")


func test_leaving_the_screen_frees_it_and_reports() -> void:
	var e := _enemy("straight", Vector2(120, 300))
	var fp := SP.component(e, &"FlightPath") as FlightPathComponent
	var seen := [false]
	fp.escaped.connect(func() -> void: seen[0] = true)
	await frames(60)
	assert_true(seen[0], "escaped was emitted:")
	assert_true(not is_instance_valid(e) or e.is_queued_for_deletion(), "freed:")


func test_an_area_drifts_without_a_movement_body() -> void:
	var a := make_entity("PowerUp", "area", SP.TEAM_NEUTRAL, Vector2(14, 14),
			{"FlightPath": {"pattern": "straight", "speed": 100.0}}, Vector2(600, 200))
	await frames(30)
	assert_true(a.global_position.x < 600.0 - 30.0, "drifted left:")


func _stub(entity_type: String) -> void:
	var n := Node2D.new()
	n.name = entity_type
	var ps := PackedScene.new()
	ps.pack(n)
	n.free()
	World._scene_cache[entity_type] = ps


func test_ship_powers_up_and_down() -> void:
	_stub("Shot")
	var ship := make_entity("Ship", "character", SP.TEAM_PLAYER, Vector2(24, 16),
			{"TopDownMovement": {}, "Health": {"max_health": 5, "invincibility_time": 0.0},
			"Weapon": {"projectile": "Shot", "fire_rate": 5.0, "spread_deg": 0.0, "projectile_count": 1, "muzzle_distance": 0.0},
			"ShmupShip": {"max_power": 4}}, Vector2(100, 270), true)
	var s := SP.component(ship, &"ShmupShip") as ShmupShipComponent
	var w := SP.component(ship, &"Weapon") as WeaponComponent
	await frames(2)
	assert_eq(w.aim_direction, Vector2.RIGHT, "aims right:")
	assert_true(w.trigger_held, "fires on its own:")
	assert_eq(w.projectile_count, 1)
	var rates: Array[float] = [w.fire_rate]
	for i in 3:
		s.power_up()
		rates.append(w.fire_rate)
	assert_eq([s.power, w.projectile_count], [4, 3], "power 4 = three shots:")
	assert_true(w.spread_deg > 10.0 and rates[3] > rates[0] * 1.4, "wider and faster:")
	var score := GameState.score
	s.power_up()
	assert_eq(s.power, 4, "capped:")
	assert_eq(GameState.score, score + 25, "a full ship scores instead:")
	(SP.component(ship, &"Health") as HealthComponent).damage(1)
	assert_eq(s.power, 3, "a hit costs a level:")


func test_ship_never_flips_to_face_left() -> void:
	_stub("Shot")
	var ship := make_entity("Ship", "character", SP.TEAM_PLAYER, Vector2(24, 16),
			{"TopDownMovement": {}, "Weapon": {"projectile": "Shot"}, "Juice": {}, "ShmupShip": {}}, Vector2(100, 270), true)
	await frames(2)
	assert_eq(SP.component(ship, &"Juice").get(&"face_movement"), false)


func test_health_bar_shows_after_damage_and_always_for_bosses() -> void:
	var boss := make_entity("Boss", "character", SP.TEAM_ENEMY, Vector2(60, 40),
			{"TopDownMovement": {}, "Health": {"max_health": 10, "invincibility_time": 0.0}, "HealthBar": {"always": true}}, Vector2(700, 270))
	await frames(2)
	(SP.component(boss, &"Health") as HealthComponent).damage(4)
	await frames(2)
	var health := SP.component(boss, &"Health") as HealthComponent
	assert_eq(health.current, 6)
	assert_true(boss.get_child_count() > 0)


func _grunt_scene() -> void:
	var n := Node2D.new()
	n.name = "Grunt"
	var ps := PackedScene.new()
	ps.pack(n)
	n.free()
	World._scene_cache["Grunt"] = ps


func test_wave_spawner_spreads_waits_for_start_and_loops() -> void:
	_grunt_scene()
	var gate := make_entity("Gate", "area", SP.TEAM_NEUTRAL, Vector2(10, 10),
			{"WaveSpawner": {"waves": "4 x Grunt every 0.05", "pause": 0.05, "spread_y": 300.0, "autostart": false}},
			Vector2(900, 300))
	var sp := SP.component(gate, &"WaveSpawner") as WaveSpawnerComponent
	await frames(30)
	assert_eq(sp.wave, 0, "waits for start():")
	sp.start()
	await frames(50)
	assert_eq(sp.wave, 1)
	assert_eq(sp.alive(), 4)
	var ys: Array[float] = []
	for n in sp._alive:
		ys.append((n as Node2D).global_position.y)
		assert_true(absf((n as Node2D).global_position.y - 300.0) <= 150.5, "inside the spread:")
	assert_true(ys.max() - ys.min() > 5.0, "spread out:")
	for n in sp._alive:
		(n as Node).queue_free()
	# endless: the same waves again, bigger
	var gate2 := make_entity("Gate2", "area", SP.TEAM_NEUTRAL, Vector2(10, 10),
			{"WaveSpawner": {"waves": "2 x Grunt every 0.03", "pause": 0.03, "endless": true}}, Vector2(900, 300))
	var sp2 := SP.component(gate2, &"WaveSpawner") as WaveSpawnerComponent
	for i in 200:
		await frames(1)
		for n in sp2._alive:
			if is_instance_valid(n):
				(n as Node).queue_free()
	assert_true(sp2._waves_sent >= 3, "kept sending waves (%d):" % sp2._waves_sent)
	assert_true(sp2._loops >= 1, "looped:")
	for n in sp2._alive:
		if is_instance_valid(n):
			(n as Node).queue_free()


func test_the_ship_really_fires_even_with_player_input() -> void:
	_stub("Shot")
	var ship := make_entity("Ship", "character", SP.TEAM_PLAYER, Vector2(24, 16),
			{"TopDownMovement": {}, "PlayerInput": {}, "Weapon": {"projectile": "Shot", "fire_rate": 10.0, "muzzle_distance": 0.0},
			"ShmupShip": {}}, Vector2(100, 270), true)
	var w := SP.component(ship, &"Weapon") as WeaponComponent
	var shots := [0]
	w.fired.connect(func() -> void: shots[0] += 1)
	await frames(60)
	assert_true(shots[0] >= 5, "fired %d times in a second:" % shots[0])
