extends SPTestCase


func _buttons(n: Node) -> Array[Button]:
	var out: Array[Button] = []
	for c in n.get_children():
		if c is Button:
			out.append(c)
		out.append_array(_buttons(c))
	return out


func test_the_end_screen_has_a_play_again_button_and_the_score() -> void:
	GameState.reset_run()
	var hud := SPHud.new()
	add_child(hud)
	await frames(1)
	GameState.add_score(120)
	GameState.win()
	await frames(2)
	var again := _buttons(hud).filter(func(b: Button) -> bool: return b.text == "Play again")
	assert_eq(again.size(), 1, "a button phones can tap")
	assert_true(again[0].is_visible_in_tree(), "shown with the win screen")
	var texts := []
	for l in hud.find_children("*", "Label", true, false):
		if (l as Label).is_visible_in_tree():
			texts.append((l as Label).text)
	assert_true("YOU WIN!" in texts and "SCORE 120" in texts, str(texts))
	GameState.reset_run()
