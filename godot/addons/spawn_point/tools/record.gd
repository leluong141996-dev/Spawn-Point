extends Node
## Records a short gameplay clip with a simple autopilot (needs a display, not headless).
## Run: godot4 --path <project> --fixed-fps 60 res://addons/spawn_point/tools/record.tscn -- <out_dir> <frames> <step> [skip]
## Writes frame_0000.png, frame_0001.png, ... every <step> physics frames for <frames> frames.
##
## Autopilot — platformer: run right, jump at walls, gaps and enemies (double jump when airborne
## and falling). Top-down: circle around the arena, aim at the nearest enemy and shoot.

const LEVEL := "res://levels/main.tscn"

var _jump_hold := 0
var _t := 0.0


func _ready() -> void:
	get_tree().root.set_meta(&"sp_autopilot", true)  # level-up menus pick on their own
	var args := OS.get_cmdline_user_args()
	var out_dir := args[0] if args.size() > 0 else "user://record"
	var total := int(args[1]) if args.size() > 1 else 360
	var step := int(args[2]) if args.size() > 2 else 3
	var skip := int(args[3]) if args.size() > 3 else 0  # frames played before recording starts
	DirAccess.make_dir_recursive_absolute(out_dir)
	add_child((load(LEVEL) as PackedScene).instantiate())
	await get_tree().physics_frame
	var player := World.player()
	var aim := SP.component(player, &"Aim") if player else null
	if aim:
		aim.set(&"mode", "nearest_enemy")  # the mouse is not ours to move
	var shot := 0
	for frame in range(skip + total):
		_drive(frame)
		await get_tree().physics_frame
		if frame >= skip and (frame - skip) % step == 0:
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png("%s/frame_%04d.png" % [out_dir, shot])
			shot += 1
	print("SPAWNPOINT_RECORD_SCORE %d" % GameState.score)
	get_tree().quit(0)


func _drive(frame: int) -> void:
	var p := World.player() as CharacterBody2D
	if p == null or frame < 20:
		return
	var farmer := SP.component(p, &"Farmer") as FarmerComponent
	if farmer:
		_farm(p, farmer, frame)
		return
	var board := SP.component(p, &"BubbleBoard") as BubbleBoardComponent
	if board:
		if frame % 42 == 0:
			board.shoot_at(board.autopilot_angle())
		return
	var mv := SP.movement(p)
	if mv is PlatformerMovementComponent:
		_platformer(p, mv as PlatformerMovementComponent)
	elif mv is TopDownMovementComponent:
		_topdown(p, frame)


func _platformer(p: CharacterBody2D, mv: PlatformerMovementComponent) -> void:
	Input.action_press(&"move_right")
	if _jump_hold > 0:
		_jump_hold -= 1
		if _jump_hold == 0:
			Input.action_release(&"jump")
		return
	var half := SP.half_size(p)
	var space := p.get_world_2d().direct_space_state
	var ahead := p.global_position + Vector2(half.x + 26, 0)
	var wall := not space.intersect_ray(PhysicsRayQueryParameters2D.create(p.global_position, ahead, SP.LAYER_WORLD, [p.get_rid()])).is_empty()
	var ground := not space.intersect_ray(PhysicsRayQueryParameters2D.create(ahead, ahead + Vector2(0, half.y + 40), SP.LAYER_WORLD, [p.get_rid()])).is_empty()
	var enemy := false
	for e in p.get_tree().get_nodes_in_group(&"team_enemy"):
		var d := (e as Node2D).global_position - p.global_position
		if d.x > 0 and d.x < 90 and absf(d.y) < 48:
			enemy = true
	var falling_into_gap := not p.is_on_floor() and p.velocity.y > 120 and not ground
	if (p.is_on_floor() and (wall or not ground or enemy)) or (falling_into_gap and mv.air_jumps > 0):
		Input.action_press(&"jump")
		_jump_hold = 14


func _farm(p: CharacterBody2D, farmer: FarmerComponent, frame: int) -> void:
	# A sensible player: harvest what is ripe, plant empty plots, water dry ones; sell when the basket is
	# heavy or there is nothing to do; swat crows that come close.
	farmer.select(1)
	var target: Vector2 = p.global_position
	var plot: FarmPlotComponent = null
	var carried := 0
	for c in farmer.basket:
		carried += int(farmer.basket[c])
	var best := INF
	for e in get_tree().get_nodes_in_group(&"farm_plot"):
		var fp := SP.component(e, &"FarmPlot") as FarmPlotComponent
		var need := 0.0 if fp.is_ripe() else (1.0 if fp.is_empty() else (2.0 if fp.wet_left <= 0.5 else INF))
		if need == INF:
			continue
		var score: float = need * 400.0 + (e as Node2D).global_position.distance_to(p.global_position)
		if score < best:
			best = score
			plot = fp
	if carried >= 8 or (plot == null and carried > 0):
		for e in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
			if SP.component(e, &"Market"):
				target = (e as Node2D).global_position
		plot = null
	elif plot:
		target = (plot.get_parent() as Node2D).global_position
	var to := target - p.global_position
	for a in [&"move_left", &"move_right", &"move_up", &"move_down"]:
		Input.action_release(a)
	if to.length() > farmer.reach * 0.5:
		if to.x < -6:
			Input.action_press(&"move_left")
		elif to.x > 6:
			Input.action_press(&"move_right")
		if to.y < -6:
			Input.action_press(&"move_up")
		elif to.y > 6:
			Input.action_press(&"move_down")
	elif plot and frame % 6 == 0:
		farmer.interact()
	Input.action_release(&"shoot")
	for e in get_tree().get_nodes_in_group(&"team_enemy"):
		if (e as Node2D).global_position.distance_to(p.global_position) < 70:
			Input.action_press(&"shoot")


func _topdown(p: CharacterBody2D, frame: int) -> void:
	_t += 1.0 / 60.0
	var dir := Vector2(cos(_t * 0.9), sin(_t * 1.3))
	for a in [&"move_left", &"move_right", &"move_up", &"move_down"]:
		Input.action_release(a)
	if dir.x < -0.3:
		Input.action_press(&"move_left")
	elif dir.x > 0.3:
		Input.action_press(&"move_right")
	if dir.y < -0.3:
		Input.action_press(&"move_up")
	elif dir.y > 0.3:
		Input.action_press(&"move_down")
	Input.action_press(&"shoot")
	if frame % 120 == 60:
		Input.action_press(&"dash")
	elif frame % 120 == 64:
		Input.action_release(&"dash")
