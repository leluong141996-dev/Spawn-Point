extends SPTestCase


func test_collectible_adds_score_and_frees() -> void:
	add_floor(-500, 500, 100)
	var coin := make_entity("Coin", "area", SP.TEAM_NEUTRAL, Vector2(14, 14), {"Collectible": {"score": 5}}, Vector2(0, 85))
	var got := []
	(SP.component(coin, &"Collectible") as CollectibleComponent).collected.connect(func(by: Node) -> void: got.append(by))
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 30), {"PlatformerMovement": {}}, Vector2(0, 60), true)
	await frames(20)
	assert_eq(GameState.score, 5)
	assert_eq(got, [p])
	assert_false(is_instance_valid(coin))


func test_bind_signal_reaches_existing_and_future_instances() -> void:
	var hits := []
	var a := make_entity("Target", "character", SP.TEAM_ENEMY, Vector2(10, 10), {"Health": {"invincibility_time": 0.0}})
	await frames(1)
	World.bind_signal(&"Target", &"Health", &"damaged", func(amount: int, src: Node) -> void: hits.append([amount, src]))
	var b := make_entity("Target", "character", SP.TEAM_ENEMY, Vector2(10, 10), {"Health": {"invincibility_time": 0.0}}, Vector2(100, 0))
	await frames(1)
	(SP.component(a, &"Health") as HealthComponent).damage(1)
	(SP.component(b, &"Health") as HealthComponent).damage(2)
	assert_eq(hits, [[1, a], [2, b]])


func test_call_all_and_count() -> void:
	var g1 := make_entity("Door", "static", SP.TEAM_NEUTRAL, Vector2(32, 64), {"Gate": {}})
	var g2 := make_entity("Door", "static", SP.TEAM_NEUTRAL, Vector2(32, 64), {"Gate": {}}, Vector2(100, 0))
	await frames(1)
	assert_eq(World.count(&"Door"), 2)
	World.call_all(&"Door", &"Gate", &"open")
	await frames(2)
	assert_true((SP.component(g1, &"Gate") as GateComponent).is_open and (SP.component(g2, &"Gate") as GateComponent).is_open)
	assert_true((g1.get_node(^"CollisionShape2D") as CollisionShape2D).disabled, "collision disabled")


func test_enemy_death_frees_entity() -> void:
	var e := make_entity("Slime", "character", SP.TEAM_ENEMY, Vector2(10, 10), {"Health": {"max_health": 1}})
	await frames(1)
	(SP.component(e, &"Health") as HealthComponent).damage(1)
	await frames(2)
	assert_false(is_instance_valid(e))


func test_player_death_costs_life_and_respawns() -> void:
	add_floor(-500, 500, 100)
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 30), {"Health": {"max_health": 1}, "PlatformerMovement": {}}, Vector2(0, 60), true)
	await frames(30)
	var spawn := p.global_position
	p.global_position.x = 200
	(SP.component(p, &"Health") as HealthComponent).damage(1)
	assert_eq(GameState.lives, 2)
	assert_false(p.visible)
	await frames(70)
	assert_true(p.visible, "respawned")
	assert_near(p.global_position.x, spawn.x, 1.0)
	assert_eq((SP.component(p, &"Health") as HealthComponent).current, 1)


func test_last_life_loses_game() -> void:
	GameState.reset_run(1)
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 30), {"Health": {"max_health": 1}}, Vector2.ZERO, true)
	var lost := [false]
	GameState.game_lost.connect(func() -> void: lost[0] = true)
	await frames(1)
	(SP.component(p, &"Health") as HealthComponent).damage(1)
	assert_true(lost[0])
	assert_false(GameState.is_playing())


func test_patrol_turns_at_ledge() -> void:
	add_floor(-100, 100, 100)
	var e := make_entity("Slime", "character", SP.TEAM_ENEMY, Vector2(24, 20), {"PlatformerMovement": {"max_speed": 120.0}, "PatrolAI": {"start_direction": "right"}}, Vector2(0, 85))
	var ai := SP.component(e, &"PatrolAI") as PatrolAIComponent
	await frames(150)
	assert_true(e.position.y < 100, "must not fall off (y=%.1f)" % e.position.y)
	assert_true(absf(e.position.x) < 100, "stays on platform (x=%.1f)" % e.position.x)
	assert_true(ai.direction == -1 or e.position.x < 80, "should have turned")


func test_dying_entity_not_counted_by_died_listeners() -> void:
	var e := make_entity("Slime", "character", SP.TEAM_ENEMY, Vector2(10, 10), {"Health": {"max_health": 1}})
	await frames(1)
	var seen := [-1]
	World.bind_signal(&"Slime", &"Health", &"died", func(_src: Node) -> void: seen[0] = World.count(&"Slime"))
	(SP.component(e, &"Health") as HealthComponent).damage(1)
	assert_eq(seen[0], 0)


func test_second_passed_signal() -> void:
	var got := []
	GameState.second_passed.connect(func(s: int) -> void: got.append(s))
	await frames(130)
	assert_eq(got, [1, 2])


func test_spawner_prunes_freed_entities() -> void:
	# Spawned entities freed outright (not queue_free) must not break the alive-list cleanup.
	var sp := SpawnerComponent.new()
	add_child(sp)
	var gone := Node2D.new()
	var queued := Node2D.new()
	var kept := Node2D.new()
	for n in [gone, queued, kept]:
		add_child(n)
	sp._alive.assign([gone, queued, kept])
	gone.free()
	queued.queue_free()
	sp._prune()
	assert_eq(sp._alive.size(), 1)
	assert_true(sp._alive[0] == kept)
	kept.queue_free()
	sp.queue_free()
