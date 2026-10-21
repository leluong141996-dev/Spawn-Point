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


func _animal(pos: Vector2, params := {}) -> FarmAnimalComponent:
	var e := make_entity("Chicken", "character", SP.TEAM_NEUTRAL, Vector2(16, 16), {"FarmAnimal": params}, pos)
	return SP.component(e, &"FarmAnimal") as FarmAnimalComponent


func test_animals_give_their_product_on_a_timer_and_stay_near_home() -> void:
	GameState.reset_run()
	var hen := _animal(Vector2(300, 300), {"product": "Egg", "product_seconds": 1.0, "wander_radius": 40.0, "speed": 60.0})
	await frames(2)
	assert_eq(hen.collect(), "", "nothing yet: just a pat")
	await frames(70)
	assert_true(hen.is_ready())
	assert_eq(hen.collect(), "Egg")
	assert_false(hen.is_ready())
	await frames(240)
	var body := hen.get_parent() as Node2D
	assert_true(body.global_position.distance_to(hen.home) < 40.0 + 8.0, "it strolls around home")


func test_farmer_collects_goods_and_sells_them() -> void:
	var f := _farmer()
	f.goods = "Egg|6;Wood|3"
	f.goods_list = FarmerComponent.parse_goods(f.goods)
	var hen := _animal(Vector2(24, 0), {"product": "Egg", "product_seconds": 0.5, "wander_radius": 0.0})
	await frames(40)
	assert_true(hen.is_ready())
	assert_eq(f.interact(), "collect")
	assert_eq(f.goods_basket, {"Egg": 1})
	assert_eq(f.add_goods("Wood", 2), 2)
	assert_eq(f.basket_value(), 6 + 2 * 3)
	assert_eq(f.sell(), 12)
	assert_eq(f.goods_basket, {})


func test_gatherables_break_after_their_hits() -> void:
	var f := _farmer()
	f.goods_list = FarmerComponent.parse_goods("Wood|3")
	var tree := make_entity("Oak", "static", SP.TEAM_NEUTRAL, Vector2(20, 20),
			{"Gatherable": {"item": "Wood", "hits": 3, "amount": 2}}, Vector2(30, 0))
	var g := SP.component(tree, &"Gatherable") as GatherableComponent
	await frames(2)
	assert_eq(f.interact(), "chop")
	assert_eq(f.interact(), "chop")
	assert_eq(g.hits_left, 1)
	assert_eq(f.interact(), "gather")
	assert_eq(f.goods_basket, {"Wood": 2})
	await frames(2)
	assert_false(is_instance_valid(tree), "the tree is gone")


func test_a_ready_animal_beats_a_closer_one_with_nothing() -> void:
	var f := _farmer()
	var chick := _animal(Vector2(14, 0), {"product": "", "product_seconds": 600.0, "wander_radius": 0.0})
	var cow := _animal(Vector2(36, 0), {"product": "Milk", "product_seconds": 0.5, "wander_radius": 0.0})
	await frames(40)
	assert_true(cow.is_ready())
	assert_eq(f.nearest_target(), cow)
	chick.get_parent().queue_free()


func test_plots_draw_their_crop_from_its_stages() -> void:
	GameState.reset_run()
	var plot := _plot(Vector2.ZERO, {"water_seconds": 10.0})
	await frames(1)
	plot.plant(0, 1.0, Color.ORANGE)
	assert_eq(plot.stage(), 0)
	plot.water()
	await frames(30)
	assert_eq(plot.stage(), 2)
	await frames(40)
	assert_eq(plot.stage(), 4)


func test_the_hoe_tills_grass_before_anything_grows() -> void:
	var f := _farmer()
	var plot := _plot(Vector2(20, 0), {"tilled": false})
	await frames(1)
	assert_false(plot.plant(0, 1.0, Color.ORANGE), "nothing grows in grass")
	assert_eq(f.interact(), "till")
	assert_true(plot.tilled)
	assert_eq(f.interact(), "plant")
	await frames(70)
	assert_eq(f.interact(), "harvest")
	assert_true(plot.tilled and plot.is_empty(), "the soil stays tilled after a harvest")


func test_fishing_casts_waits_for_a_bite_and_reels_in() -> void:
	var f := _farmer()
	f.goods_list = FarmerComponent.parse_goods("Fish|10")
	var shore := make_entity("Shore", "area", SP.TEAM_NEUTRAL, Vector2(20, 20),
			{"FishingSpot": {"min_wait": 0.3, "max_wait": 0.3, "bite_time": 0.5}}, Vector2(20, 0))
	var spot := SP.component(shore, &"FishingSpot") as FishingSpotComponent
	await frames(2)
	assert_eq(f.interact(), "cast")
	assert_eq(f.interact(), "", "too soon: it gets away")
	assert_eq(spot.state, FishingSpotComponent.State.IDLE)
	assert_eq(f.interact(), "cast")
	await frames(25)
	assert_eq(spot.state, FishingSpotComponent.State.BITE)
	assert_eq(f.interact(), "catch")
	assert_eq(f.goods_basket, {"Fish": 1})
	assert_eq(f.interact(), "cast")
	await frames(70)  # the bite comes and goes
	assert_eq(spot.state, FishingSpotComponent.State.IDLE, "too late: it got away")


func test_a_warp_moves_the_player_through_the_doorway() -> void:
	GameState.reset_run()
	var p := make_entity("Farmer", "character", SP.TEAM_PLAYER, Vector2(20, 20), {"TopDownMovement": {}}, Vector2(0, 0), true)
	var door := make_entity("HouseDoor", "area", SP.TEAM_NEUTRAL, Vector2(30, 30), {"Warp": {"to": Vector2(500, 900)}}, Vector2(0, 0))
	var warp := SP.component(door, &"Warp") as WarpComponent
	await frames(4)
	assert_eq(warp.player_inside, p, "the player stands in the doorway")
	warp.warp(p)
	assert_eq(p.global_position, Vector2(500, 900))
	assert_true(warp.player_inside == null)
