extends SPTestCase

const DT := 1.0 / 60.0


func _mv() -> PlatformerMovementComponent:
	var m := PlatformerMovementComponent.new()
	m.jump_held = true  # like a player holding the button after pressing it
	add_child(m)
	return m


func test_jump_on_floor() -> void:
	var m := _mv()
	var jumps := [0]
	m.jumped.connect(func() -> void: jumps[0] += 1)
	m.jump_held = true
	m.request_jump()
	var v := m.step_velocity(Vector2.ZERO, DT, true)
	assert_true(v.y < -500.0, "should launch upward, got %s" % v)
	assert_eq(jumps[0], 1)


func test_coyote_time_allows_late_jump() -> void:
	var m := _mv()
	var v := m.step_velocity(Vector2.ZERO, DT, true)
	for i in 4:  # ~0.067s after leaving the ledge (< 0.1s coyote)
		v = m.step_velocity(v, DT, false)
	m.request_jump()
	v = m.step_velocity(v, DT, false)
	assert_true(v.y < -500.0, "coyote jump expected, vy=%.1f" % v.y)


func test_no_jump_after_coyote_expires() -> void:
	var m := _mv()
	var v := m.step_velocity(Vector2.ZERO, DT, true)
	for i in 10:  # 0.167s > coyote
		v = m.step_velocity(v, DT, false)
	m.request_jump()
	v = m.step_velocity(v, DT, false)
	assert_true(v.y > 0.0, "should still be falling, vy=%.1f" % v.y)


func test_jump_buffer_fires_on_landing() -> void:
	var m := _mv()
	var v := Vector2(0, 300)
	for i in 20:
		v = m.step_velocity(v, DT, false)
	m.request_jump()  # pressed while airborne
	v = m.step_velocity(v, DT, false)
	v = m.step_velocity(v, DT, false)
	v = m.step_velocity(Vector2(v.x, 0), DT, true)  # lands within buffer window
	assert_true(v.y < -500.0, "buffered jump expected, vy=%.1f" % v.y)


func test_releasing_jump_cuts_height() -> void:
	var full := _apex_height(true)
	var short := _apex_height(false)
	assert_true(short < full * 0.6, "short hop %.1f should be much lower than full %.1f" % [short, full])


func _apex_height(hold: bool) -> float:
	var m := _mv()
	m.jump_held = true
	m.request_jump()
	var v := m.step_velocity(Vector2.ZERO, DT, true)
	var y := 0.0
	var top := 0.0
	for i in 120:
		y += v.y * DT
		top = minf(top, y)
		m.jump_held = hold or i < 2
		v = m.step_velocity(v, DT, false)
	return -top


func test_falls_faster_than_rises() -> void:
	var m := _mv()
	var up := m.step_velocity(Vector2(0, -200), DT, false)
	var down := m.step_velocity(Vector2(0, 200), DT, false)
	assert_true((down.y - 200.0) > (up.y + 200.0) * 1.5, "fall gravity should be stronger")


func test_air_jump() -> void:
	var m := _mv()
	m.air_jumps = 1
	var v := m.step_velocity(Vector2.ZERO, DT, true)
	for i in 15:
		v = m.step_velocity(v, DT, false)
	m.request_jump()
	v = m.step_velocity(v, DT, false)
	assert_true(v.y < -500.0, "double jump expected")
	for i in 3:
		v = m.step_velocity(v, DT, false)
	m.request_jump()
	var v2 := m.step_velocity(v, DT, false)
	assert_true(v2.y > v.y, "no third jump")


func test_dash_overrides_velocity() -> void:
	var m := _mv()
	m.dash_speed = 800.0
	m.move_vector = Vector2(-1, 0)
	var v := m.step_velocity(Vector2.ZERO, DT, true)
	m.request_dash()
	v = m.step_velocity(v, DT, false)
	assert_near(v.x, -800.0, 0.1)
	assert_eq(v.y, 0.0)


func test_accelerates_to_max_speed() -> void:
	var m := _mv()
	m.move_vector = Vector2(1, 0)
	var v := Vector2.ZERO
	for i in 30:
		v = m.step_velocity(v, DT, true)
	assert_near(v.x, m.max_speed, 0.01)


func test_physics_lands_and_jumps_expected_height() -> void:
	add_floor(-500, 500, 100)
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 36), {"PlatformerMovement": {}}, Vector2(0, 0), true)
	var mv := SP.component(p, &"PlatformerMovement") as PlatformerMovementComponent
	var landings := []
	mv.landed.connect(func(s: float) -> void: landings.append(s))
	await frames(60)
	assert_true((p as CharacterBody2D).is_on_floor(), "should rest on the floor")
	assert_near(p.position.y, 100 - 18, 1.5, "feet on floor:")
	assert_true(landings.size() >= 1, "landed should fire")
	var start_y := p.position.y
	mv.jump_held = true
	mv.request_jump()
	var top := start_y
	for i in 90:
		await frames(1)
		top = minf(top, p.position.y)
	var g: float = ProjectSettings.get_setting("physics/2d/default_gravity")
	var ideal := mv.jump_velocity * mv.jump_velocity / (2.0 * g)
	var h := start_y - top
	# Apex hang adds a little height; stays within 35% of the ballistic estimate.
	assert_true(h > ideal * 0.9 and h < ideal * 1.35, "jump height %.1f vs ideal %.1f" % [h, ideal])
