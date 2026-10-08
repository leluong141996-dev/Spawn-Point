extends SPTestCase


func test_death_cause_is_the_attacker_type() -> void:
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 20),
			{"Health": {"max_health": 1}, "Hurtbox": {"size_scale": 1.0}}, Vector2.ZERO, true)
	make_entity("Spikes", "area", SP.TEAM_ENEMY, Vector2(20, 20), {"Hitbox": {"damage": 1}}, Vector2(5, 0))
	await frames(4)
	var core := SP.core(p)
	assert_true(core.dead, "player should be dead")
	assert_eq(core.death_cause, "Spikes")
	assert_eq(String(SP.core((SP.component(p, &"Hurtbox") as HurtboxComponent).last_hit_by).entity_type), "Spikes")


func test_falling_out_is_a_fall() -> void:
	World.kill_y = 200.0
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 20),
			{"Health": {"max_health": 3}, "PlatformerMovement": {}}, Vector2.ZERO, true)
	await frames(40)
	assert_eq(SP.core(p).death_cause, "fall")


func test_cause_resets_on_respawn() -> void:
	World.kill_y = 200.0
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 20),
			{"Health": {"max_health": 3}, "PlatformerMovement": {}}, Vector2.ZERO, true)
	var causes := []
	SP.core(p).respawned.connect(func() -> void: causes.append(SP.core(p).death_cause))
	await frames(40)
	World.kill_y = INF
	await frames(70)
	assert_eq(causes, [""])
