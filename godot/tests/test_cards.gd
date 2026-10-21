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
	assert_eq(b.run_map[2], ["boss"])


func test_first_floor_starts_a_fight_with_a_full_hand() -> void:
	var b := _battle()
	await frames(3)
	assert_eq(b.phase, "fight")
	assert_eq(b.hand.size(), 5)
	assert_eq(b.energy_left, 3)
	assert_eq(b.foes_alive().size(), 1)
	assert_eq(_hp(b.foes_alive()[0]["node"]), 20, "foe HP comes from the foe list, not its Health default")


func test_damage_block_vulnerable_weak_and_strength() -> void:
	var b := _battle()
	await frames(3)
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
	await frames(3)
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
	await frames(3)
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
	await frames(3)
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
	await frames(3)
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
	for i in 300:
		if not events.is_empty():
			break
		b.autopilot_step()
		await frames(1)
	assert_eq(events, ["won"])
