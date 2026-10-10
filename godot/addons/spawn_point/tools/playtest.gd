extends Node
## Headless playtest: bots of different skill play the level and report telemetry as JSON.
## Run: godot4 --headless --path <project> --fixed-fps 60 res://addons/spawn_point/tools/playtest.tscn \
##        -- <out.json> <profiles csv> <runs> <seed> <time_limit_s>
##
## Bots press the same input actions as a human, so coyote time, jump buffering, knockback and
## invincibility are exercised for real. Every run is seeded and therefore reproducible.

const LEVEL := "res://levels/main.tscn"

const PROFILES := {
	"novice": {"reaction": 12, "late": 10, "full_hop": 0.6, "panic": 0.25, "trigger": 0.6, "dodge": 0.2, "aim": 0.35},
	"average": {"reaction": 6, "late": 5, "full_hop": 0.85, "panic": 0.08, "trigger": 0.85, "dodge": 0.55, "aim": 0.16},
	"expert": {"reaction": 2, "late": 1, "full_hop": 1.0, "panic": 0.0, "trigger": 1.0, "dodge": 0.9, "aim": 0.05},
}
const MOVE_ACTIONS := [&"move_left", &"move_right", &"move_up", &"move_down"]
const ALL_ACTIONS := [&"move_left", &"move_right", &"move_up", &"move_down", &"jump", &"dash", &"shoot"]
const STUCK_FRAMES := 240
const TARGET_PATIENCE := 20 * 60  # a person moves on after ~20 s of failing at one thing
const NAV := preload("res://addons/spawn_point/tools/playtest_nav.gd")

var _rng := RandomNumberGenerator.new()
var _p: Dictionary  # current profile
var _frame := 0
var _queue: Array[Dictionary] = []  # delayed actions: {at, action, hold}
var _holds := {}  # action -> frames left
var _panic_left := 0
var _double_used := false
var _nav: NAV
var _path: Array[Vector2i] = []
var _target: Node2D
var _blocked_targets := {}
var _unreachable: Array = []
var _target_since := 0
var _wants_move := false
var _aim_error := 0.0  # radians; people don't aim perfectly with a mouse

# Telemetry of the current run.
var _tile := 32.0
var _deaths: Array = []
var _damage: Array = []
var _missed: Array = []
var _stuck: Array = []
var _intended := 0
var _performed := 0
var _pending_jump := 0
var _last_jump_frame := -9999
var _anchor := Vector2.ZERO
var _anchor_frame := 0


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var out_path := args[0] if args.size() > 0 else "user://playtest.json"
	var profiles := (args[1] if args.size() > 1 else "novice,average,expert").split(",")
	var runs := int(args[2]) if args.size() > 2 else 3
	var base_seed := int(args[3]) if args.size() > 3 else 1
	var limit_s := float(args[4]) if args.size() > 4 else 90.0
	var results := []
	for prof in profiles:
		for r in runs:
			results.append(await _play(prof.strip_edges(), r, base_seed * 1000 + r, limit_s))
	var f := FileAccess.open(out_path, FileAccess.WRITE)
	f.store_string(JSON.stringify({"runs": results}, " "))
	f.close()
	print("SPAWNPOINT_PLAYTEST_OK ", results.size())
	get_tree().quit(0)


# --- one run --------------------------------------------------------------------------------

func _play(profile: String, run: int, run_seed: int, limit_s: float) -> Dictionary:
	_p = PROFILES.get(profile, PROFILES["average"])
	seed(run_seed)
	_rng.seed = run_seed
	_reset_bot()
	var level: Node2D = (load(LEVEL) as PackedScene).instantiate()
	GameState.reset_run(int(level.get(&"lives")))
	add_child(level)
	_tile = float(level.get(&"tile_size"))
	await get_tree().physics_frame
	var player := World.player() as CharacterBody2D
	var pickups_total := _count_pickups()
	_setup_nav(level, player)
	_hook(player)
	_anchor = player.global_position
	var limit := int(limit_s * 60.0)
	var outcome := "timeout"
	for i in limit:
		_frame = i
		_drive(player)
		await get_tree().physics_frame
		_observe(player)
		if GameState.phase == GameState.Phase.WON:
			outcome = "won"
			break
		if GameState.phase == GameState.Phase.LOST:
			outcome = "lost"
			break
	var result := {
		"profile": profile, "run": run, "seed": run_seed, "outcome": outcome,
		"time": snappedf(GameState.time, 0.01), "score": GameState.score, "lives_left": GameState.lives,
		"deaths": _deaths, "damage": _damage, "stuck": _stuck, "unreachable": _unreachable,
		"jumps": {"intended": _intended, "performed": _performed, "missed": _missed},
		"pickups": {"total": pickups_total, "collected": pickups_total - _count_pickups()},
	}
	for a in ALL_ACTIONS:
		Input.action_release(a)
	level.queue_free()
	await get_tree().physics_frame
	await get_tree().physics_frame
	Engine.time_scale = 1.0
	return result


func _reset_bot() -> void:
	_queue.clear()
	_holds.clear()
	_panic_left = 0
	_double_used = false
	_deaths = []
	_damage = []
	_missed = []
	_stuck = []
	_intended = 0
	_performed = 0
	_pending_jump = 0
	_last_jump_frame = -9999
	_anchor_frame = 0
	_target = null


func _hook(player: Node) -> void:
	var health := SP.component(player, &"Health") as HealthComponent
	if health:
		health.died.connect(_on_player_died.bind(player))
		health.damaged.connect(_on_player_damaged.bind(player))
	var mv := SP.movement(player)
	if mv and mv.has_signal(&"jumped"):
		mv.jumped.connect(_on_jumped)
	if mv and mv.has_signal(&"landed"):
		mv.landed.connect(func(_s: float) -> void: _double_used = false)


func _on_player_died(player: Node2D) -> void:
	var c := SP.core(player)
	_deaths.append({"x": _tx(player), "y": _ty(player), "cause": c.death_cause if c else "unknown",
			"t": snappedf(GameState.time, 0.01), "after_jump": _frame - _last_jump_frame < 150})


func _on_player_damaged(_amount: int, player: Node2D) -> void:
	var hb := SP.component(player, &"Hurtbox") as HurtboxComponent
	var cause := "unknown"
	if hb and is_instance_valid(hb.last_hit_by) and SP.core(hb.last_hit_by):
		cause = SP.core(hb.last_hit_by).entity_type
	_damage.append({"x": _tx(player), "y": _ty(player), "cause": cause, "t": snappedf(GameState.time, 0.01)})


func _on_jumped() -> void:
	_performed += 1
	_last_jump_frame = _frame
	if _pending_jump > 0:
		_pending_jump = 0


func _tx(n: Node2D) -> int:
	return int(floor(n.global_position.x / _tile))


func _ty(n: Node2D) -> int:
	return int(floor(n.global_position.y / _tile))


func _observe(player: CharacterBody2D) -> void:
	# A ground jump the bot asked for that never happened (e.g. pressed after leaving the ledge
	# and after coyote time ran out).
	if _pending_jump > 0:
		_pending_jump -= 1
		if _pending_jump == 0:
			_missed.append({"x": _tx(player), "y": _ty(player)})
	if not player.visible:
		_anchor_frame = _frame
		_anchor = player.global_position
		return
	if player.global_position.distance_to(_anchor) > 24.0 or not _wants_move:
		_anchor = player.global_position
		_anchor_frame = _frame
	elif _frame - _anchor_frame >= STUCK_FRAMES:
		_stuck.append({"x": _tx(player), "y": _ty(player), "t": snappedf(GameState.time, 0.01)})
		_anchor_frame = _frame


func _count_pickups() -> int:
	var n := 0
	for e in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
		if SP.component(e, &"Collectible") and not e.is_queued_for_deletion():
			n += 1
	return n


# --- input plumbing -------------------------------------------------------------------------

func _press(action: StringName, frames: int) -> void:
	Input.action_press(action)
	_holds[action] = maxi(int(_holds.get(action, 0)), frames)


func _later(action: StringName, hold: int, extra_delay := 0) -> void:
	var delay := int(_p.reaction) + extra_delay
	_queue.append({"at": _frame + delay, "action": action, "hold": hold})


func _tick_inputs() -> void:
	for a in _holds.keys():
		_holds[a] -= 1
		if _holds[a] <= 0:
			Input.action_release(a)
			_holds.erase(a)
	var keep: Array[Dictionary] = []
	for q in _queue:
		if q.at <= _frame:
			_press(q.action, q.hold)
		else:
			keep.append(q)
	_queue = keep


# --- bots -----------------------------------------------------------------------------------

func _setup_nav(level: Node2D, player: CharacterBody2D) -> void:
	_nav = NAV.new()
	var tiles := level.get_node_or_null(^"Tiles") as TileMapLayer
	var mv := SP.movement(player)
	var platformer := mv is PlatformerMovementComponent
	var up := 3
	var across := 4
	if platformer:
		var m := mv as PlatformerMovementComponent
		var g: float = ProjectSettings.get_setting("physics/2d/default_gravity", 1600.0) * m.gravity_scale
		var jumps := 1 + m.air_jumps
		var h := m.jump_velocity * m.jump_velocity / (2.0 * g)
		var t_air := m.jump_velocity / g + sqrt(2.0 * h / (g * m.fall_gravity_multiplier))
		up = int(h * jumps / _tile)
		across = maxi(1, int(m.max_speed * t_air * jumps / _tile))
	if tiles:
		_nav.setup(tiles, _tile, platformer, SP.half_size(player).y * 2.0, up, across)
	for e in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
		# Static things that hurt (spikes): a damaging hitbox on something that never moves.
		if SP.component(e, &"Hitbox") and SP.movement(e) == null and SP.component(e, &"Projectile") == null:
			_nav.mark_hazard((e as Node2D).global_position)
	_path = []
	_blocked_targets.clear()
	_unreachable = []


func _drive(p: CharacterBody2D) -> void:
	_tick_inputs()
	if p == null or not p.visible or _frame < 10:
		return
	if _panic_left > 0:
		_panic_left -= 1
		for a in MOVE_ACTIONS:
			Input.action_release(a)
		return
	if _rng.randf() < float(_p.panic) / 60.0:
		_panic_left = 30
	var mv := SP.movement(p)
	if mv is PlatformerMovementComponent:
		_platformer(p, mv as PlatformerMovementComponent)
	elif mv is TopDownMovementComponent:
		_topdown(p)


## Picks the next target node (pickup, exit, or enemy), skipping ones known to be unreachable.
func _pick_target(p: CharacterBody2D) -> Node2D:
	var best: Node2D = null
	var best_d := INF
	var health := SP.component(p, &"Health") as HealthComponent
	var hurt := health != null and health.current < health.max_health
	for e in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
		var n := e as Node2D
		if n == p or n.is_queued_for_deletion() or _blocked_targets.has(n.get_instance_id()):
			continue
		var weight := INF
		var c := SP.component(n, &"Collectible")
		if c:
			weight = 1.0 if (int(c.get(&"score")) > 0 or hurt) else INF
		elif SP.component(n, &"TriggerZone"):
			weight = 4.0
		elif SP.team_of(n) == SP.TEAM_ENEMY and SP.component(n, &"Hurtbox") and SP.component(n, &"Projectile") == null:
			weight = 2.5
		if weight == INF:
			continue
		var d := n.global_position.distance_to(p.global_position) * weight
		if d < best_d:
			best_d = d
			best = n
	return best


func _give_up(target: Node2D, reason := "no_path") -> void:
	_blocked_targets[target.get_instance_id()] = true
	var c := Vector2i(floori(target.global_position.x / _tile), floori(target.global_position.y / _tile))
	var entry := {"x": c.x, "y": c.y, "entity": SP.core(target).entity_type if SP.core(target) else "?",
			"reason": reason}
	if entry not in _unreachable:
		_unreachable.append(entry)
	_path = []


func _platformer(p: CharacterBody2D, mv: PlatformerMovementComponent) -> void:
	var half := SP.half_size(p)
	var cur := _nav.cell_of(p.global_position, half.y)
	var target := _pick_target(p)
	if target != _target:
		_target = target
		_target_since = _frame
		_path = []
	if target and _frame - _target_since > TARGET_PATIENCE:
		_give_up(target, "too_hard")
		return
	_wants_move = true
	if p.is_on_floor() and target and (_path.is_empty() or _frame % 20 == 0 or cur not in _path):
		if _nav.standable(cur):
			_path = _nav.path(cur, _nav.reaches(target.global_position))
			if _path.is_empty():
				_give_up(target)
				return
	if OS.has_environment("SPAWNPOINT_PLAYTEST_DEBUG") and _frame % 120 == 0:
		print("f=%d cur=%s target=%s path=%s" % [_frame, cur, target.global_position.round() if target else null, _path.slice(0, 4)])
	# Advance along the path only once landed: passing through a cell mid-jump is not standing on it
	# (steering on to the next cell from the air used to overshoot small platforms).
	if p.is_on_floor():
		while _path.size() > 1 and _path[0] != cur and _path[1] == cur:
			_path.pop_front()
		var idx := _path.find(cur)
		if idx > 0:
			_path = _path.slice(idx)
	var next: Vector2i = _path[1] if _path.size() > 1 else cur
	var want_x: float = _nav.center(next).x if _path.size() > 1 else (target.global_position.x if target else p.global_position.x + 64.0)
	var dx := want_x - p.global_position.x
	var dir := 0
	if absf(dx) > 4.0:
		dir = 1 if dx > 0.0 else -1
	Input.action_release(&"move_left")
	Input.action_release(&"move_right")
	if dir != 0:
		Input.action_press(&"move_right" if dir > 0 else &"move_left")

	var enemy_ahead := false
	for e in get_tree().get_nodes_in_group(&"team_enemy"):
		var d := (e as Node2D).global_position - p.global_position
		if SP.component(e, &"Hurtbox") and d.x * (dir if dir != 0 else 1) > 0 and absf(d.x) < 70 and absf(d.y) < 40:
			enemy_ahead = true
	var step := next - cur
	var needs_jump := _path.size() > 1 and (step.y < 0 or absi(step.x) > 1)
	var at_edge := dir != 0 and not _nav.standable(cur + Vector2i(dir, 0))
	if at_edge and absi(step.x) > 1:
		# A long jump needs the whole run-up: wait until the feet are at the platform's end, not just in its
		# last tile (fast reactions used to jump a tile early and fall short; coyote time covers overshoot).
		var edge_x := _nav.center(cur).x + dir * _tile * 0.5
		# Within half a body of the boundary: against a wall the body stops exactly there.
		at_edge = absf(edge_x - p.global_position.x) < half.x + 4.0 or signf(p.global_position.x - edge_x) == dir
	var target_above := _path.size() <= 1 and target != null and target.global_position.y < p.global_position.y - half.y
	var busy := _pending_jump > 0 or _queue.any(func(q: Dictionary) -> bool: return q.action == &"jump")
	if p.is_on_floor() and not busy and ((needs_jump and (absi(step.x) <= 1 or at_edge)) or enemy_ahead or target_above):
		# People hold the button when they need height; short hops happen on flat ground.
		var hold := 18 if (step.y < 0 or target_above or _rng.randf() < float(_p.full_hop)) else 4
		_later(&"jump", hold, _rng.randi_range(0, int(_p.late)))
		_intended += 1
		_pending_jump = int(_p.reaction) + int(_p.late) + 14
	elif not p.is_on_floor() and p.velocity.y > 40 and mv.air_jumps > 0 and not _double_used \
			and (step.y < 0 or not _ray(p.get_world_2d().direct_space_state, p, p.global_position, p.global_position + Vector2(0, 200))):
		_double_used = true
		_later(&"jump", 16)
	if SP.component(p, &"Weapon") and enemy_ahead and _rng.randf() < float(_p.trigger):
		_press(&"shoot", 2)


func _topdown(p: CharacterBody2D) -> void:
	var aim := SP.component(p, &"Aim")
	if aim and aim.is_physics_processing():
		aim.set_physics_process(false)  # bots have no mouse: they aim themselves, with a human-sized error
	_aim(p)
	var pos := p.global_position
	var cur := _nav.cell_of(pos, 0.0)
	var target := _pick_target(p)
	if target != _target:
		_target = target
		_target_since = _frame
		_path = []
	var steer := Vector2.ZERO
	if target:
		var is_enemy := SP.team_of(target) == SP.TEAM_ENEMY
		if _path.is_empty() or _frame % 30 == 0:
			_path = _nav.path(cur, _nav.reaches(target.global_position))
			if _path.is_empty() and not is_enemy:
				_give_up(target)
		var idx := _path.find(cur)
		if idx > 0:
			_path = _path.slice(idx)
		var goal := _nav.center(_path[1]) if _path.size() > 1 else target.global_position
		var to := goal - pos
		var keep := 150.0 if is_enemy and _path.size() <= 6 else 0.0
		var dist := target.global_position.distance_to(pos)
		if dist > keep:
			steer += to.normalized()
		elif keep > 0.0:
			steer -= (target.global_position - pos).normalized() * 0.6
	var bullet_close := false
	for e in get_tree().get_nodes_in_group(&"team_enemy"):
		var n := e as Node2D
		var d := pos - n.global_position
		var is_bullet := SP.component(n, &"Projectile") != null
		var radius := 110.0 if is_bullet else 80.0
		if d.length() < radius and d.length() > 0.1:
			steer += d.normalized() * (1.0 - d.length() / radius) * (1.8 if is_bullet else 1.2)
			if is_bullet and d.length() < 70.0:
				bullet_close = true
	_wants_move = steer.length() > 0.5
	for a in MOVE_ACTIONS:
		Input.action_release(a)
	if steer.x < -0.25:
		Input.action_press(&"move_left")
	elif steer.x > 0.25:
		Input.action_press(&"move_right")
	if steer.y < -0.25:
		Input.action_press(&"move_up")
	elif steer.y > 0.25:
		Input.action_press(&"move_down")
	if SP.component(p, &"Weapon") and _rng.randf() < float(_p.trigger):
		_press(&"shoot", 2)
	if bullet_close and _rng.randf() < float(_p.dodge) * 0.1:
		_later(&"dash", 3)


func _aim(p: CharacterBody2D) -> void:
	var weapon := SP.component(p, &"Weapon")
	if weapon == null:
		return
	var best: Node2D = null
	var best_d := 600.0
	for e in get_tree().get_nodes_in_group(&"team_enemy"):
		var n := e as Node2D
		if SP.component(n, &"Hurtbox") == null or SP.component(n, &"Projectile") != null:
			continue
		var d := n.global_position.distance_to(p.global_position)
		if d < best_d:
			best_d = d
			best = n
	if best == null:
		return
	if _frame % (int(_p.reaction) * 3 + 6) == 0:  # the error drifts at the speed of the player's reactions
		_aim_error = _rng.randfn(0.0, float(_p.aim))
	var dir := (best.global_position - p.global_position).normalized().rotated(_aim_error)
	weapon.set(&"aim_direction", dir)
	if aim_visual_supported(p):
		SP.face(p, dir, true)


func aim_visual_supported(p: Node2D) -> bool:
	var aim := SP.component(p, &"Aim")
	return aim != null and bool(aim.get(&"rotate_visual"))


func _ray(space: PhysicsDirectSpaceState2D, p: CharacterBody2D, from: Vector2, to: Vector2) -> bool:
	return not space.intersect_ray(PhysicsRayQueryParameters2D.create(from, to, SP.LAYER_WORLD, [p.get_rid()])).is_empty()
