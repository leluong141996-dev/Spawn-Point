extends SPTestCase

const CARDS := "Strike|1|attack|dmg:6|starter|sword;Defend|1|skill|blk:5|starter|shield;" \
	+ "Bash|2|attack|dmg:8,vuln:2|common|axe;Twin|1|attack|dmg:3,hits:2|common|dagger;" \
	+ "Venom|1|skill|poison:4|uncommon|drop;Rage|1|power|str:2|rare|flex;Sweep|1|attack|all:4|common|wind"


func _battle(params := {}) -> CardBattleComponent:
	GameState.reset_run(1)
	var base := {"cards": CARDS, "starter": "Strike*5,Defend*5", "pace": 0.0, "run_seed": 7, "floors": 3,
		"foes": "Slime|20|normal|atk:6,blk:5+atk:2;King|30|boss|atk:9"}
	base.merge(params, true)
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 40),
			{"Health": {"max_health": 50}, "CardBattle": base}, Vector2(100, 300), true)
	var b := SP.component(p, &"CardBattle") as CardBattleComponent
	b.spawner = func(type: String, at: Vector2) -> Node2D:
		return make_entity(type, "character", SP.TEAM_ENEMY, Vector2(20, 30), {"Health": {"max_health": 10}}, at)
	return b


## Takes the first room on the map (the first floor is all fights) and waits for the fight to start.
func _enter(b: CardBattleComponent) -> void:
	await frames(3)
	if b.phase == "map":
		b.choose(0)
	await frames(2)


func _hp(n: Node) -> int:
	return (SP.component(n, &"Health") as HealthComponent).current


func test_library_starter_and_text() -> void:
	var b := _battle()
	await frames(2)
	assert_eq(b.deck.size(), 10)
	assert_eq(b.card("Bash")["cost"], 2)
	assert_eq(b.card_text("Twin"), "Deal 3 damage 2 times.")
	assert_eq(b.card_text("Sweep"), "Deal 4 damage to ALL foes.")
	assert_eq(b.run_map.size(), 3)
	assert_eq(b.run_map[2].size(), 1)
	assert_eq(b.run_map[2][0]["kind"], "boss")
	for room: Dictionary in b.run_map[0]:
		assert_eq(room["kind"], "fight", "the first floor is all fights")


func test_first_floor_starts_a_fight_with_a_full_hand() -> void:
	var b := _battle()
	await _enter(b)
	assert_eq(b.phase, "fight")
	assert_eq(b.hand.size(), 5)
	assert_eq(b.energy_left, 3)
	assert_eq(b.foes_alive().size(), 1)
	assert_eq(_hp(b.foes_alive()[0]["node"]), 20, "foe HP comes from the foe list, not its Health default")


func test_damage_block_vulnerable_weak_and_strength() -> void:
	var b := _battle()
	await _enter(b)
	var f: Dictionary = b.foes_alive()[0]
	var n: Node = f["node"]
	f["st"]["block"] = 4
	assert_eq(b.deal({"str": 0}, n, f["st"], 6), 2, "block soaks 4 of 6")
	assert_eq(f["st"]["block"], 0)
	f["st"]["vuln"] = 1
	assert_eq(b.deal({"str": 2}, n, f["st"], 6), 12, "(6+2) x1.5")
	f["st"]["vuln"] = 0
	assert_eq(b.deal({"weak": 1}, n, f["st"], 4), 3, "weak deals 25% less")


func test_playing_cards_spends_energy_and_moves_them() -> void:
	var b := _battle()
	await _enter(b)
	b.hand = ["Strike", "Defend", "Bash", "Rage"] as Array[String]
	b.energy_left = 3
	var foe: Node = b.foes_alive()[0]["node"]
	assert_true(b.play_index(0), "Strike")
	assert_eq(_hp(foe), 14)
	assert_true(b.play_index(0), "Defend")
	assert_eq(b.hero_st["block"], 5)
	assert_false(b.play_index(0), "Bash costs 2, only 1 left")
	assert_true(b.play_index(1), "Rage")
	assert_eq(b.hero_st["str"], 2)
	assert_eq(b.discard, ["Strike", "Defend"] as Array[String], "a power stays out of the deck for the fight")
	assert_eq(b.energy_left, 0)


func test_foe_intents_cycle_and_hit_through_block() -> void:
	var b := _battle()
	await _enter(b)
	var hero := b.get_parent()
	b.hand.clear()
	b.hero_st["block"] = 2
	b.end_turn()
	await frames(2)
	assert_eq(_hp(hero), 46, "atk:6 minus 2 block")
	assert_eq(b.phase, "fight")
	assert_eq(b.hero_st["block"], 0, "block lasts one turn")
	var f: Dictionary = b.foes_alive()[0]
	assert_eq(b.intent_of(f).size(), 2, "the second move is block + attack")
	b.hand.clear()
	b.end_turn()
	await frames(2)
	assert_eq(f["st"]["block"], 5)
	assert_eq(_hp(hero), 44)


func test_poison_ticks_down_at_the_foes_turn() -> void:
	var b := _battle()
	await _enter(b)
	var f: Dictionary = b.foes_alive()[0]
	f["st"]["poison"] = 3
	b.hand.clear()
	b.end_turn()
	await frames(2)
	assert_eq(_hp(f["node"]), 17)
	assert_eq(f["st"]["poison"], 2)


func test_winning_a_fight_offers_cards_then_the_boss_wins_the_run() -> void:
	var b := _battle({"floors": 2})
	var events := []
	b.won.connect(func() -> void: events.append("won"))
	await _enter(b)
	var foe: Node = b.foes_alive()[0]["node"]
	b.deal({}, foe, b.foes_alive()[0]["st"], 99)
	b._after_action()
	await frames(3)
	assert_eq(b.phase, "reward")
	assert_eq(b.options.size(), 3)
	var score := GameState.score
	b.choose(0)
	assert_eq(b.deck.size(), 11)
	await frames(2)
	assert_eq(b.phase, "map")
	b.choose(0)
	await frames(2)
	assert_eq(b.phase, "fight")
	assert_eq(b.foes_alive()[0]["type"], "King")
	b.deal({}, b.foes_alive()[0]["node"], b.foes_alive()[0]["st"], 999)
	b._after_action()
	await frames(3)
	assert_eq(events, ["won"])
	assert_true(GameState.score > score)


func test_autopilot_plays_a_whole_run() -> void:
	var b := _battle({"floors": 3, "foes": "Slime|8|normal|atk:3;King|14|boss|atk:4"})
	var events := []
	b.won.connect(func() -> void: events.append("won"))
	b.died.connect(func() -> void: events.append("died"))
	await frames(3)
	for i in 600:
		if not events.is_empty():
			break
		b.autopilot_step()
		await frames(1)
	assert_eq(events, ["won"])


func test_the_map_is_a_connected_graph() -> void:
	for seed in [1, 2, 3, 4, 5]:
		var b := _battle({"floors": 9, "run_seed": seed})
		await frames(1)
		for f in b.run_map.size() - 1:
			for j in b.run_map[f + 1].size():
				var reached := false
				for room: Dictionary in b.run_map[f]:
					assert_false(room["next"].is_empty(), "every room leads on")
					if j in room["next"]:
						reached = true
				assert_true(reached, "every room can be reached (seed %d floor %d)" % [seed, f + 1])
		assert_eq(b.run_map[7][0]["kind"], "rest", "a rest before the boss")
		assert_eq(b.run_map[4][0]["kind"], "treasure", "treasure halfway")


func test_upgrades_make_better_cards() -> void:
	var b := _battle()
	await frames(2)
	var up := b._upgraded("Bash")
	assert_eq(up, "Bash+")
	assert_eq(b.card_text(up), "Deal 12 damage. Apply 3 Vulnerable.")
	assert_eq(b.card("Bash+")["cost"], 2)
	b._open_rest()
	b.choose(1)  # smith
	assert_eq(b.phase, "pick")
	b.choose(0)
	assert_true(b.deck[0].ends_with("+"), "the picked card is upgraded in the deck")


func test_relics_change_fights() -> void:
	var b := _battle({"starter_relic": "burning_blood"})
	b.relics.append_array(["anchor", "vajra", "stone"] as Array[String])
	await _enter(b)
	assert_eq(b.hero_st["block"], 10, "Anchor")
	assert_eq(b.hero_st["str"], 1, "Vajra")
	b.hand = ["Defend"] as Array[String]
	b.play_index(0)
	assert_eq(b.hero_st["block"], 16, "Smooth Stone adds 1 block")
	var hero := b.get_parent()
	(SP.component(hero, &"Health") as HealthComponent).current = 30
	b.deal({}, b.foes_alive()[0]["node"], b.foes_alive()[0]["st"], 999)
	b._after_action()
	await frames(3)
	assert_eq(_hp(hero), 36, "Burning Blood heals 6 after the fight")


func test_shop_buys_and_removes() -> void:
	var b := _battle()
	await frames(2)
	GameState.add_score(500)
	b._open_shop()
	assert_eq(b.phase, "shop")
	var before := b.deck.size()
	var gold := GameState.score
	b.choose(0)  # the first card
	assert_eq(b.deck.size(), before + 1)
	assert_true(GameState.score < gold)
	var remove_at := -1
	for i in b.options.size():
		if b.options[i][0] == "remove":
			remove_at = i
	b.choose(remove_at)
	assert_eq(b.phase, "pick")
	b.choose(0)
	assert_eq(b.deck.size(), before, "one card bought, one removed")
	assert_eq(b.phase, "shop")


func test_potions_and_events() -> void:
	var b := _battle()
	await _enter(b)
	b.potions = ["fire", "block"] as Array[String]
	var foe: Node = b.foes_alive()[0]["node"]
	assert_true(b.use_potion(0))
	assert_eq(_hp(foe), 0, "a fire potion deals 20")
	await frames(3)
	b._event = SPCardContent.EVENTS[0]
	b.phase = "event"
	b.options = b._event["choices"]
	var gold := GameState.score
	b.choose(0)  # pray at the shrine
	assert_true(GameState.score > gold)
	assert_eq(b.phase, "notice")
