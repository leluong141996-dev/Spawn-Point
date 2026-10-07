extends SPTestCase


func _health(max_hp := 3, iframes := 0.5) -> HealthComponent:
	var h := HealthComponent.new()
	h.max_health = max_hp
	h.invincibility_time = iframes
	add_child(h)
	return h


func test_damage_reduces_and_emits() -> void:
	var h := _health()
	var got := []
	h.damaged.connect(func(a: int) -> void: got.append(a))
	h.damage(1)
	assert_eq(h.current, 2)
	assert_eq(got, [1])


func test_invincibility_blocks_followup_hits() -> void:
	var h := _health(3, 0.5)
	h.damage(1)
	h.damage(1)
	assert_eq(h.current, 2, "second hit should be blocked:")
	await frames(35)
	h.damage(1)
	assert_eq(h.current, 1, "hit after invincibility:")


func test_died_emitted_once() -> void:
	var h := _health(1, 0.0)
	var deaths := [0]
	h.died.connect(func() -> void: deaths[0] += 1)
	h.damage(5)
	h.damage(5)
	h.kill()
	assert_eq(deaths[0], 1)
	assert_true(h.is_dead())


func test_heal_caps_at_max() -> void:
	var h := _health(5, 0.0)
	h.damage(3)
	h.heal(10)
	assert_eq(h.current, 5)
