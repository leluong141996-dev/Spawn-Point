extends SPTestCase


func test_experience_levels_up_with_growing_thresholds() -> void:
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 20),
			{"Experience": {"first_level_xp": 4, "growth": 1.5, "score_per_xp": 0}}, Vector2.ZERO, true)
	await frames(1)
	var xp := SP.component(p, &"Experience") as ExperienceComponent
	var levels := []
	xp.leveled_up.connect(func(l: int) -> void: levels.append(l))
	xp.add_xp(3)
	assert_eq(xp.level, 1)
	xp.add_xp(1)  # 4 -> level 2, next needs 6
	assert_eq([xp.level, xp.xp_to_next], [2, 6])
	xp.add_xp(20)  # 6 -> level 3 (needs 9), 9 -> level 4 (needs 14); 5 left
	assert_eq(levels, [2, 3, 4])
	assert_eq(xp.xp, 5)


func test_xp_orb_is_pulled_in_and_absorbed() -> void:
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 20),
			{"Experience": {"magnet_radius": 120.0, "score_per_xp": 0}}, Vector2.ZERO, true)
	var orb := make_entity("Gem", "area", SP.TEAM_NEUTRAL, Vector2(8, 8), {"XpOrb": {"value": 3}}, Vector2(100, 0))
	var far := make_entity("Gem", "area", SP.TEAM_NEUTRAL, Vector2(8, 8), {"XpOrb": {"value": 3}}, Vector2(400, 0))
	await frames(40)
	assert_eq((SP.component(p, &"Experience") as ExperienceComponent).xp, 3)
	assert_false(is_instance_valid(orb), "pulled orb absorbed")
	assert_true(is_instance_valid(far), "orb outside the magnet stays")


func test_level_up_menu_parses_and_applies_upgrades() -> void:
	var ups := LevelUpMenuComponent.parse_upgrades(
			"Fast|Shoot faster|Weapon.fire_rate*2;Multi|More|Weapon.projectile_count+1,Weapon.spread_deg+10;Bad|x|nope")
	assert_eq(ups.size(), 2)
	assert_eq(ups[1].changes.size(), 2)
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 20), {
		"Experience": {}, "Weapon": {"fire_rate": 3.0, "projectile_count": 1, "spread_deg": 4.0},
		"Health": {"max_health": 3}, "LevelUpMenu": {}}, Vector2.ZERO, true)
	await frames(1)
	var menu := SP.component(p, &"LevelUpMenu") as LevelUpMenuComponent
	var w := SP.component(p, &"Weapon") as WeaponComponent
	menu.apply_upgrade(ups[0])
	menu.apply_upgrade(ups[1])
	assert_near(w.fire_rate, 6.0, 0.001)
	assert_eq([w.projectile_count, w.spread_deg], [2, 14.0])
	var h := SP.component(p, &"Health") as HealthComponent
	h.current = 1
	menu.apply_upgrade(LevelUpMenuComponent.parse_upgrades("Vit|x|Health.max_health+1,Health.current+99")[0])
	assert_eq([h.max_health, h.current], [4, 4])


func test_level_up_pauses_until_a_card_is_picked() -> void:
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 20), {
		"Experience": {"first_level_xp": 1, "score_per_xp": 0}, "Weapon": {"fire_rate": 2.0},
		"LevelUpMenu": {"upgrades": "Fast|x|Weapon.fire_rate+1", "choices": 1}}, Vector2.ZERO, true)
	await frames(1)
	var menu := SP.component(p, &"LevelUpMenu") as LevelUpMenuComponent
	(SP.component(p, &"Experience") as ExperienceComponent).add_xp(1)
	assert_true(menu.is_open() and get_tree().paused, "menu open, game paused")
	menu.pick(0)
	assert_false(menu.is_open() or get_tree().paused, "menu closed, game resumed")
	assert_near((SP.component(p, &"Weapon") as WeaponComponent).fire_rate, 3.0, 0.001)


func test_type_params_reach_existing_and_future_instances() -> void:
	var a := make_entity("Shot", "area", SP.TEAM_PLAYER, Vector2(8, 8), {"Projectile": {"pierce": 0}})
	await frames(1)
	World.set_type_param(&"Shot", &"Projectile", &"pierce", 2)
	assert_eq((SP.component(a, &"Projectile") as ProjectileComponent).pierce, 2)
	var b := make_entity("Shot", "area", SP.TEAM_PLAYER, Vector2(8, 8), {"Projectile": {"pierce": 0}}, Vector2(50, 0))
	await frames(1)
	assert_eq((SP.component(b, &"Projectile") as ProjectileComponent).pierce, 2)
	assert_eq(World.type_param(&"Shot", &"Projectile", &"pierce", 0), 2)
	World.begin_level(null, INF)  # overrides belong to one level


func test_spawner_interval_ramps_down_to_a_floor() -> void:
	var s := make_entity("Gate", "static", SP.TEAM_NEUTRAL, Vector2(8, 8), {"Spawner": {
		"entity": "Nope", "interval": 1.0, "interval_ramp": 0.5, "min_interval": 0.3, "start_delay": 0.0,
		"max_alive": 1}})
	var blocker := Node2D.new()
	add_child(blocker)
	await frames(1)
	var sp := SP.component(s, &"Spawner") as SpawnerComponent
	sp._alive.assign([blocker])  # at max_alive: the timer runs but nothing spawns
	await frames(3)
	assert_near(sp.interval, 0.5, 0.001)
	sp.interval = 0.31
	sp._timer = 0.0
	await frames(2)
	assert_near(sp.interval, 0.3, 0.001, "never below min_interval")
