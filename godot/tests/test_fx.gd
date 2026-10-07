extends SPTestCase


func test_hitstop_restores_time_scale() -> void:
	FX.hitstop(0.05)
	assert_eq(Engine.time_scale, 0.0, "frozen during hit-stop:")
	await frames(12)
	assert_eq(Engine.time_scale, 1.0, "restored after hit-stop:")


func test_overlapping_hitstops_restore() -> void:
	FX.hitstop(0.05)
	await frames(1)
	FX.hitstop(0.08)
	await frames(2)
	FX.hitstop(0.03)
	await frames(20)
	assert_eq(Engine.time_scale, 1.0)
