class_name PatrolAIComponent
extends Node
## Platformer enemy brain: walks back and forth, turning at walls and (optionally) ledges.
## Can hop periodically.

const SP_NAME := "PatrolAI"
const SP_HOSTS: Array[String] = ["CharacterBody2D"]
const SP_REQUIRES: Array[String] = ["PlatformerMovement"]
const SP_CATEGORY := "controller"

## Initial walking direction.
@export_enum("left", "right") var start_direction: String = "left"
## Turn around instead of walking off ledges.
@export var turn_at_ledges := true
## Fraction of the movement max_speed to walk at.
@export_range(0.0, 1.0, 0.05) var speed_scale: float = 1.0
## Seconds between hops (0 = never hop).
@export_range(0.0, 30.0, 0.1) var jump_interval: float = 0.0

## Current direction: -1 left, 1 right.
var direction := -1

var _body: CharacterBody2D
var _turn_cooldown := 0.0
var _jump_timer := 0.0


func _ready() -> void:
	_body = get_parent() as CharacterBody2D
	direction = 1 if start_direction == "right" else -1
	_jump_timer = jump_interval
	process_physics_priority = -10


func _physics_process(delta: float) -> void:
	var mv := SP.component(_body, &"PlatformerMovement") as PlatformerMovementComponent
	if mv == null:
		return
	_turn_cooldown -= delta
	if _turn_cooldown <= 0.0:
		if _body.is_on_wall() and signf(_body.get_wall_normal().x) == -direction:
			_turn()
		elif turn_at_ledges and _body.is_on_floor() and not _ground_ahead():
			_turn()
	mv.move_vector = Vector2(direction * speed_scale, 0)
	if jump_interval > 0.0:
		_jump_timer -= delta
		mv.jump_held = true
		if _jump_timer <= 0.0 and _body.is_on_floor():
			_jump_timer = jump_interval
			mv.request_jump()


func _turn() -> void:
	direction = -direction
	_turn_cooldown = 0.2


func _ground_ahead() -> bool:
	var half := SP.half_size(_body)
	var from := _body.global_position + Vector2(direction * (half.x + 2.0), 0)
	var q := PhysicsRayQueryParameters2D.create(from, from + Vector2(0, half.y + 12.0), SP.LAYER_WORLD, [_body.get_rid()])
	return not _body.get_world_2d().direct_space_state.intersect_ray(q).is_empty()
