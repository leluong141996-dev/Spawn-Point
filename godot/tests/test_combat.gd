extends SPTestCase


func test_hitbox_damages_opposing_team() -> void:
	var player := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 20),
			{"Health": {"max_health": 3}, "Hurtbox": {}}, Vector2(0, 0), true)
	make_entity("Spiky", "character", SP.TEAM_ENEMY, Vector2(20, 20), {"Hitbox": {"damage": 1}}, Vector2(10, 0))
	await frames(4)
	var h := SP.component(player, &"Health") as HealthComponent
	assert_eq(h.current, 2, "player should take exactly one hit:")


func test_hitbox_ignores_same_team() -> void:
	var a := make_entity("A", "character", SP.TEAM_ENEMY, Vector2(20, 20), {"Health": {}, "Hurtbox": {}}, Vector2(0, 0))
	make_entity("B", "character", SP.TEAM_ENEMY, Vector2(20, 20), {"Hitbox": {}}, Vector2(5, 0))
	await frames(4)
	assert_eq((SP.component(a, &"Health") as HealthComponent).current, 3)


func test_knockback_pushes_away() -> void:
	add_floor(-500, 500, 100)
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 20),
			{"Health": {}, "Hurtbox": {}, "PlatformerMovement": {}}, Vector2(0, 80), true)
	await frames(10)
	make_entity("Spiky", "character", SP.TEAM_ENEMY, Vector2(20, 20), {"Hitbox": {"knockback": 400}}, Vector2(14, 90))
	await frames(3)
	assert_true((p as CharacterBody2D).velocity.x < -50.0, "should be pushed left, v=%s" % (p as CharacterBody2D).velocity)


func test_stomp_kills_enemy_and_bounces() -> void:
	add_floor(-500, 500, 100)
	var enemy := make_entity("Slime", "character", SP.TEAM_ENEMY, Vector2(28, 20),
			{"Health": {"max_health": 1}, "Hurtbox": {"size_scale": 1.0}, "Hitbox": {}, "PlatformerMovement": {}}, Vector2(0, 90))
	var player := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 30),
			{"Health": {}, "Hurtbox": {}, "PlatformerMovement": {}, "Stomp": {}}, Vector2(0, 20), true)
	var stomps := []
	(SP.component(player, &"Stomp") as StompComponent).stomped.connect(func(t: Node) -> void: stomps.append(t))
	await frames(30)
	assert_eq(stomps.size(), 1, "one stomp:")
	assert_false(is_instance_valid(enemy) and not enemy.is_queued_for_deletion(), "enemy should be removed")
	assert_eq((SP.component(player, &"Health") as HealthComponent).current, 3, "player unharmed:")


func test_projectile_hits_and_expires() -> void:
	var target := make_entity("Dummy", "character", SP.TEAM_ENEMY, Vector2(24, 24), {"Health": {"max_health": 5}, "Hurtbox": {"size_scale": 1.0}}, Vector2(200, 0))
	var bullet := make_entity("Bullet", "area", SP.TEAM_PLAYER, Vector2(8, 8), {"Projectile": {"speed": 600.0}, "Hitbox": {"damage": 2}}, Vector2(0, 0))
	(bullet as Area2D).collision_mask = SP.LAYER_WORLD
	await frames(30)
	assert_eq((SP.component(target, &"Health") as HealthComponent).current, 3)
	assert_false(is_instance_valid(bullet), "bullet should be gone")


func test_projectile_visual_points_where_it_flies() -> void:
	var down := make_entity("Arrow", "area", SP.TEAM_PLAYER, Vector2(8, 8), {"Projectile": {"speed": 10.0, "direction": Vector2(0, 1)}}, Vector2(0, 0))
	var right := make_entity("Arrow", "area", SP.TEAM_PLAYER, Vector2(8, 8), {"Projectile": {"speed": 10.0}}, Vector2(0, 40))
	await frames(1)
	assert_near((down.get_node(^"Visual/Shape") as Node2D).rotation, PI / 2, 0.01, "an arrow shot down points down")
	assert_near((right.get_node(^"Visual/Shape") as Node2D).rotation, 0.0, 0.01, "an arrow shot right is not turned")


func test_projectile_stops_at_wall() -> void:
	var wall := add_floor(90, 130, -50)  # 40px wide block straddling the path
	wall.position.y = 0
	var bullet := make_entity("Bullet", "area", SP.TEAM_PLAYER, Vector2(8, 8), {"Projectile": {"speed": 600.0, "lifetime": 5.0}}, Vector2(0, 0))
	(bullet as Area2D).collision_mask = SP.LAYER_WORLD
	await frames(30)
	assert_false(is_instance_valid(bullet), "bullet should hit the wall")
