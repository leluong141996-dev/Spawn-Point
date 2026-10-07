extends Node
## Smoke test for a generated game: loads the main level, plays a few seconds with scripted
## input (idle, run right, jump, shoot, dash), and prints a JSON report line:
##   SPAWNPOINT_SMOKE {...}
## Run: godot4 --headless --path <project> --fixed-fps 60 res://addons/spawn_point/tools/smoke.tscn

const LEVEL := "res://levels/main.tscn"


func _ready() -> void:
	var report := {}
	var scene := load(LEVEL) as PackedScene
	if scene == null:
		_finish({"error": "cannot load " + LEVEL})
		return
	var level := scene.instantiate()
	add_child(level)
	await _frames(60)

	var player := World.player()
	report["player_found"] = player != null
	report["entity_counts"] = _counts()
	if player == null:
		_finish(report)
		return
	var cb := player as CharacterBody2D
	report["on_floor_after_1s"] = cb.is_on_floor() if cb else false
	var start := player.global_position

	Input.action_press(&"move_right")
	for i in 90:
		if i % 30 == 0:
			Input.action_press(&"jump")
		elif i % 30 == 12:
			Input.action_release(&"jump")
		await _frames(1)
	Input.action_release(&"move_right")
	Input.action_release(&"jump")
	Input.action_press(&"shoot")
	Input.action_press(&"dash")
	await _frames(20)
	Input.action_release(&"shoot")
	Input.action_release(&"dash")
	await _frames(40)

	player = World.player()
	report["player_alive"] = player != null and player.visible
	report["moved_px"] = player.global_position.distance_to(start) if player else 0.0
	report["score"] = GameState.score
	report["lives"] = GameState.lives
	report["phase"] = ["playing", "won", "lost"][GameState.phase]
	_finish(report)


func _counts() -> Dictionary:
	var out := {}
	for n in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
		var c := SP.core(n)
		if c:
			out[c.entity_type] = out.get(c.entity_type, 0) + 1
	return out


func _frames(n: int) -> void:
	for i in n:
		await get_tree().physics_frame


func _finish(report: Dictionary) -> void:
	print("SPAWNPOINT_SMOKE ", JSON.stringify(report))
	Engine.time_scale = 1.0
	get_tree().quit(0)
