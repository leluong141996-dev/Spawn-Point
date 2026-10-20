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
	var ended_at := -1
	for frame in range(skip + total):
		_drive(frame)
		await get_tree().physics_frame
		if not GameState.is_playing():
			if ended_at < 0:
				ended_at = frame
			elif frame - ended_at > 90 and frame >= skip:  # keep 1.5 s of the end screen, then stop
				break
		if frame >= skip and (frame - skip) % step == 0:
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png("%s/frame_%04d.png" % [out_dir, shot])
			shot += 1
	print("SPAWNPOINT_RECORD_SCORE %d lives %d phase %d" % [GameState.score, GameState.lives, GameState.phase])
	get_tree().quit(0)


func _drive(frame: int) -> void:
	var p := World.player() as CharacterBody2D
	if p == null or frame < 20:
		return
	var builder := SP.component(p, &"TowerBuilder") as TowerBuilderComponent
	if builder:
		if frame % 30 == 0:
			_defend(builder)
		return
	var farmer := SP.component(p, &"Farmer") as FarmerComponent
	if farmer:
		_farm(p, farmer, frame)
		return
	if SP.component(p, &"ShmupShip"):
		_shmup(p)
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
	var weapon := SP.component(p, &"Weapon") as WeaponComponent
	if weapon:  # swing / fire at anything just ahead
		weapon.trigger_held = enemy
	var falling_into_gap := not p.is_on_floor() and p.velocity.y > 120 and not ground
	if (p.is_on_floor() and (wall or not ground or enemy)) or (falling_into_gap and mv.air_jumps > 0):
		Input.action_press(&"jump")
		_jump_hold = 14


func _defend(builder: TowerBuilderComponent) -> void:
	# Archers first; from three archers on, save up for cannons. Build on the free pad that covers the
	# most road within range.
	var archers := 0
	for e in get_tree().get_nodes_in_group(&"tower_slot"):
		var s := SP.component(e, &"TowerSlot") as TowerSlotComponent
		if not s.is_free():
			archers += 1
	var want := 1 if archers >= 3 and builder.tower_list.size() > 1 else 0
	builder.select(want)
	if GameState.score < int(builder.tower_list[want].cost):
		return
	var road: Array[Vector2] = []
	for e in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
		var c := SP.core(e)
		if c and String(c.entity_type) == "Road":
			road.append((e as Node2D).global_position)
	var best: TowerSlotComponent = null
	var best_cover := -1
	for e in get_tree().get_nodes_in_group(&"tower_slot"):
		var s := SP.component(e, &"TowerSlot") as TowerSlotComponent
		if not s.is_free():
			continue
		var cover := 0
		for r in road:
			if r.distance_to((e as Node2D).global_position) < 140.0:
				cover += 1
		if cover > best_cover:
			best_cover = cover
			best = s
	if best:
		builder.build_on(best)


var _blocked := {}  # Vector2i cell -> true, for the farm autopilot's path finding
var _path: Array[Vector2] = []
var _goal := Vector2.INF
var _chops := 0
var _skip := {}  # instance id -> frame until which the autopilot ignores it (it could not get there)


func _farm(p: CharacterBody2D, farmer: FarmerComponent, frame: int) -> void:
	# A sensible player: harvest what is ripe, plant empty plots, water dry ones, collect eggs and milk, chop a
	# tree now and then; sell when the basket is heavy or there is nothing to do; swat crows that come close.
	# It walks along a path over the level grid, so fences and trees do not stop it.
	farmer.select(int(frame / 600) % maxi(farmer.crop_list.size(), 1))
	if frame % 120 == 20:
		_blocked = _scan_blocked(p)
	var carried := 0
	for c in farmer.basket:
		carried += int(farmer.basket[c])
	for g in farmer.goods_basket:
		carried += int(farmer.goods_basket[g])
	var target := Vector2.INF
	var target_id := 0
	var act := false
	var on_plot := false
	var best := INF
	for e in get_tree().get_nodes_in_group(&"farm_plot"):
		var fp := SP.component(e, &"FarmPlot") as FarmPlotComponent
		var need := 0.0 if fp.is_ripe() else (1.0 if fp.is_empty() else (2.0 if fp.wet_left <= 0.5 else INF))
		if need == INF or int(_skip.get(e.get_instance_id(), -1)) > frame:
			continue
		var score: float = need * 300.0 + (e as Node2D).global_position.distance_to(p.global_position)
		if score < best:
			best = score
			target = (e as Node2D).global_position
			target_id = e.get_instance_id()
			on_plot = true
	for e in get_tree().get_nodes_in_group(&"farm_animal"):
		var an := SP.component(e, &"FarmAnimal") as FarmAnimalComponent
		if an and an.is_ready() and int(_skip.get(e.get_instance_id(), -1)) <= frame:
			var score: float = 150.0 + (e as Node2D).global_position.distance_to(p.global_position)
			if score < best:
				best = score
				target = (e as Node2D).global_position
				target_id = e.get_instance_id()
				on_plot = false
	if _chops < 6 and frame > 900:
		for e in get_tree().get_nodes_in_group(&"gatherable"):
			if int(_skip.get(e.get_instance_id(), -1)) > frame:
				continue
			var score: float = 500.0 + (e as Node2D).global_position.distance_to(p.global_position) * 2.0
			if score < best:
				best = score
				target = (e as Node2D).global_position
				target_id = e.get_instance_id()
				on_plot = false
	if carried >= 8 or (target == Vector2.INF and carried > 0):
		for e in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
			if SP.component(e, &"Market"):
				target = (e as Node2D).global_position
	else:
		act = target != Vector2.INF
	for a in [&"move_left", &"move_right", &"move_up", &"move_down"]:
		Input.action_release(a)
	Input.action_release(&"shoot")
	for e in get_tree().get_nodes_in_group(&"team_enemy"):
		if (e as Node2D).global_position.distance_to(p.global_position) < 70:
			Input.action_press(&"shoot")
	if target == Vector2.INF:
		return
	# Plots can be stood on, so stand right on the one to work (the farmer works the nearest thing).
	var close := p.global_position.distance_to(target) < (10.0 if on_plot else farmer.reach * 1.1)
	if close:
		_path.clear()
		if act and frame % 8 == 0:
			if farmer.interact() == "chop":
				_chops += 1
		if not act or on_plot:  # walk onto the shipping bin, or right onto the plot
			_steer(target - p.global_position)
		return
	if _path.is_empty() or _goal.distance_to(target) > 24.0 or frame % 45 == 0:
		_goal = target
		_path = _find_path(p.global_position, target, 12.0 if on_plot else farmer.reach * 1.05)
		if _path.is_empty() and target_id != 0:  # no way there: try something else for a while
			_skip[target_id] = frame + 900
	while not _path.is_empty() and p.global_position.distance_to(_path[0]) < 8.0:
		_path.pop_front()
	_steer((_path[0] if not _path.is_empty() else target) - p.global_position)


func _steer(to: Vector2) -> void:
	if to.x < -4:
		Input.action_press(&"move_left")
	elif to.x > 4:
		Input.action_press(&"move_right")
	if to.y < -4:
		Input.action_press(&"move_up")
	elif to.y > 4:
		Input.action_press(&"move_down")


func _tile() -> float:
	var main := get_child(0)
	return float(main.get(&"tile_size")) if main and main.get(&"tile_size") else 32.0


## Cells with something solid in them (tiles, fences, trees, buildings), found with point queries.
func _scan_blocked(p: CharacterBody2D) -> Dictionary:
	var out := {}
	var ts := _tile()
	var bounds: Rect2 = get_child(0).get(&"bounds")
	var space := p.get_world_2d().direct_space_state
	var q := PhysicsPointQueryParameters2D.new()
	q.collide_with_areas = false
	q.collision_mask = p.collision_mask
	q.exclude = [p.get_rid()]
	for cy in int(bounds.size.y / ts):
		for cx in int(bounds.size.x / ts):
			for off in [Vector2(0.5, 0.5), Vector2(0.25, 0.75), Vector2(0.75, 0.75), Vector2(0.5, 0.9)]:
				q.position = bounds.position + (Vector2(cx, cy) + off) * ts
				var hits := space.intersect_point(q, 4)
				var solid := false
				for h in hits:
					if not (h.collider is CharacterBody2D):
						solid = true
				if solid:
					out[Vector2i(cx, cy)] = true
					break
	return out


## Breadth-first search over free cells to any cell within [param reach] of [param to].
func _find_path(from: Vector2, to: Vector2, reach: float) -> Array[Vector2]:
	var ts := _tile()
	var start := Vector2i(floor(from.x / ts), floor(from.y / ts))
	var prev := {start: start}
	var queue: Array[Vector2i] = [start]
	var found := Vector2i(-1, -1)
	var n := 0
	while not queue.is_empty() and n < 4000:
		n += 1
		var c: Vector2i = queue.pop_front()
		var center := (Vector2(c) + Vector2(0.5, 0.5)) * ts
		if center.distance_to(to) < reach:
			found = c
			break
		for d in [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN]:
			var nb: Vector2i = c + d
			if prev.has(nb) or _blocked.has(nb) or nb.x < 0 or nb.y < 0 or nb.x > 200 or nb.y > 200:
				continue
			prev[nb] = c
			queue.append(nb)
	var out: Array[Vector2] = []
	if found.x < 0:
		return out
	var c := found
	while c != start:
		out.push_front((Vector2(c) + Vector2(0.5, 0.5)) * ts)
		c = prev[c]
	return out


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


## Shooter autopilot: line up with the nearest enemy ahead (or a power-up, which comes first), slip out of the
## way of shots that are close, and stay in the left part of the field.
func _shmup(p: CharacterBody2D) -> void:
	var pos := p.global_position
	var target_y := pos.y
	var nearest := 1e9
	var dodge := 0.0
	for e in p.get_tree().get_nodes_in_group(&"team_enemy"):
		var d := (e as Node2D).global_position - pos
		if SP.component(e, &"Projectile"):
			if d.x > -10.0 and d.x < 130.0 and absf(d.y) < 34.0:
				dodge += signf(-d.y) if absf(d.y) > 2.0 else 1.0
		elif d.x > 0.0 and d.x < nearest:
			nearest = d.x
			target_y = (e as Node2D).global_position.y
	for e in p.get_tree().get_nodes_in_group(&"team_neutral"):
		var d := (e as Node2D).global_position - pos
		if SP.component(e, &"Collectible") and d.x > 0.0 and d.x < 420.0:
			target_y = (e as Node2D).global_position.y
			nearest = 0.0
	var dy := target_y - pos.y
	if dodge != 0.0:
		dy = dodge * 100.0
	for a in [&"move_left", &"move_right", &"move_up", &"move_down"]:
		Input.action_release(a)
	if dy < -10.0:
		Input.action_press(&"move_up")
	elif dy > 10.0:
		Input.action_press(&"move_down")
	if pos.x < 110.0:
		Input.action_press(&"move_right")
	elif pos.x > 240.0:
		Input.action_press(&"move_left")
