extends SPTestCase


func _plot(pos: Vector2, params := {}) -> FarmPlotComponent:
	var e := make_entity("Plot", "area", SP.TEAM_NEUTRAL, Vector2(30, 30), {"FarmPlot": params}, pos)
	return SP.component(e, &"FarmPlot") as FarmPlotComponent


func _farmer(pos := Vector2.ZERO) -> FarmerComponent:
	GameState.reset_run()
	var p := make_entity("Farmer", "character", SP.TEAM_PLAYER, Vector2(20, 20),
			{"Farmer": {"crops": "Carrot|#ff9f1c|1|4;Pumpkin|#ffa300|2|20"}}, pos, true)
	return SP.component(p, &"Farmer") as FarmerComponent


func test_crops_grow_only_while_wet() -> void:
	GameState.reset_run()
	var plot := _plot(Vector2.ZERO, {"water_seconds": 0.5})
	await frames(1)
	assert_true(plot.plant(0, 1.0, Color.ORANGE))
	assert_false(plot.plant(1, 1.0, Color.ORANGE), "one crop per plot")
	await frames(30)
	assert_eq(plot.growth, 0.0, "dry soil: no growth")
	plot.water()
	await frames(90)  # 0.5 s of water, then dry again
	assert_near(plot.growth, 0.5, 0.05)
	assert_false(plot.is_ripe())
	plot.water()
	await frames(40)
	assert_true(plot.is_ripe())
	assert_eq(plot.harvest(), 0)
	assert_true(plot.is_empty())


func test_farmer_plants_waters_harvests_and_sells() -> void:
	var f := _farmer()
	var plot := _plot(Vector2(20, 0), {"water_seconds": 10.0})
	await frames(1)
	f.select(1)
	assert_eq(f.interact(), "plant")
	assert_eq(plot.crop, 1)
	await frames(130)  # pumpkins need 2 s of wet soil; planting waters once
	assert_true(plot.is_ripe())
	assert_eq(f.interact(), "harvest")
	assert_eq(f.basket, {1: 1})
	assert_eq(f.basket_value(), 20)
	var before := GameState.score
	assert_eq(f.sell(), 20)
	assert_eq(GameState.score - before, 20)
	assert_eq(f.basket, {})


func test_market_buys_the_basket_on_contact() -> void:
	var f := _farmer(Vector2(0, 0))
	f.basket = {0: 3}
	var m := make_entity("Stall", "area", SP.TEAM_NEUTRAL, Vector2(40, 40), {"Market": {}}, Vector2(200, 0))
	var sold := []
	(SP.component(m, &"Market") as MarketComponent).sold.connect(func(a: int) -> void: sold.append(a))
	await frames(2)
	(f.get_parent() as Node2D).global_position = Vector2(200, 0)
	await frames(4)
	assert_eq(sold, [12])
	assert_eq(f.basket, {})


func test_pest_eats_the_nearest_crop() -> void:
	GameState.reset_run()
	var plot := _plot(Vector2(60, 0))
	await frames(1)
	plot.plant(0, 100.0, Color.ORANGE)
	var crow := make_entity("Crow", "character", SP.TEAM_ENEMY, Vector2(16, 16),
			{"TopDownMovement": {"max_speed": 300.0}, "CropPest": {"eat_seconds": 0.3, "appetite": 0}})
	var eaten := []
	plot.eaten.connect(func(c: int) -> void: eaten.append(c))
	await frames(80)
	assert_eq(eaten, [0], "the crow walked over and ate it")
	assert_true(plot.is_empty())
	crow.queue_free()
