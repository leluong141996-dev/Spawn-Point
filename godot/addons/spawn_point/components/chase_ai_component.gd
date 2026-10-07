class_name ChaseAIComponent
extends Node
## Enemy brain: wanders until the player comes close, then chases (and shoots, if the entity
## has a Weapon and a clear line of sight). Works top-down; in platformers it only moves
## horizontally.

const SP_NAME := "ChaseAI"
const SP_HOSTS: Array[String] = ["CharacterBody2D"]
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "controller"

enum State { WANDER, CHASE }

## Distance at which the player is noticed (px).
@export_range(0.0, 5000.0, 1.0) var detect_radius: float = 300.0
## Distance at which the chase is abandoned (px).
@export_range(0.0, 5000.0, 1.0) var lose_radius: float = 480.0
## Stop approaching inside this distance (ranged enemies keep their distance).
@export_range(0.0, 2000.0, 1.0) var keep_distance: float = 0.0
## Weapon fires when the player is within this distance (px).
@export_range(0.0, 5000.0, 1.0) var fire_range: float = 380.0
## Wander around while idle.
@export var wander := true
## Fraction of max speed used while wandering.
@export_range(0.0, 1.0, 0.05) var wander_speed: float = 0.35
## Require an unobstructed line to the player to chase/shoot.
@export var needs_line_of_sight := true

var state := State.WANDER

var _body: CharacterBody2D
var _wander_dir := Vector2.ZERO
var _wander_timer := 0.0


func _ready() -> void:
	_body = get_parent() as CharacterBody2D
	process_physics_priority = -10


func _physics_process(delta: float) -> void:
	var mv := SP.movement(_body)
	var weapon := SP.component(_body, &"Weapon") as WeaponComponent
	var player := World.player()
	var to_player := Vector2.ZERO
	var dist := INF
	if player and player.visible and GameState.is_playing():
		to_player = player.global_position - _body.global_position
		dist = to_player.length()

	match state:
		State.WANDER:
			if dist < detect_radius and _can_see(player):
				state = State.CHASE
		State.CHASE:
			if dist > lose_radius or player == null or not player.visible:
				state = State.WANDER

	var desired := Vector2.ZERO
	if state == State.CHASE:
		if dist > keep_distance:
			desired = to_player.normalized()
		elif keep_distance > 0.0 and dist < keep_distance * 0.7:
			desired = -to_player.normalized()
	elif wander:
		_wander_timer -= delta
		if _wander_timer <= 0.0:
			_wander_timer = randf_range(1.0, 2.5)
			_wander_dir = Vector2.ZERO if randf() < 0.3 else Vector2.from_angle(randf() * TAU)
		desired = _wander_dir * wander_speed
	desired += _separation()

	if mv is PlatformerMovementComponent:
		mv.move_vector = Vector2(signf(desired.x) if absf(desired.x) > 0.1 else 0.0, 0)
	elif mv:
		mv.move_vector = desired.limit_length(1.0)

	if weapon:
		var shooting := state == State.CHASE and dist <= fire_range and _can_see(player)
		weapon.trigger_held = shooting
		if shooting:
			weapon.aim_direction = to_player.normalized()


func _can_see(target: Node2D) -> bool:
	if target == null:
		return false
	if not needs_line_of_sight:
		return true
	var q := PhysicsRayQueryParameters2D.create(_body.global_position, target.global_position, SP.LAYER_WORLD, [_body.get_rid()])
	return _body.get_world_2d().direct_space_state.intersect_ray(q).is_empty()


# Keeps a crowd of chasers from collapsing into one blob.
func _separation() -> Vector2:
	var push := Vector2.ZERO
	var half := SP.half_size(_body)
	var radius := maxf(half.x, half.y) * 2.5
	for other in World.instances(StringName(SP.core(_body).entity_type)):
		var o := other as Node2D
		if o == _body:
			continue
		var d := _body.global_position - o.global_position
		var l := d.length()
		if l > 0.01 and l < radius:
			push += d / l * (1.0 - l / radius)
	return push
