class_name TopDownMovementComponent
extends Node
## Eight-direction movement seen from above, with acceleration, friction and an optional dash.
## Reads intent (move_vector, dash requests) from a controller such as PlayerInput or ChaseAI.

const SP_NAME := "TopDownMovement"
const SP_HOSTS: Array[String] = ["CharacterBody2D"]
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["step_velocity"]
const SP_CATEGORY := "movement"

## Emitted when a dash starts.
signal dashed

## Top speed (px/s).
@export_range(0.0, 2000.0, 1.0) var max_speed: float = 240.0
## Acceleration toward the input direction (px/s²).
@export_range(0.0, 20000.0, 10.0) var acceleration: float = 2400.0
## Deceleration when there is no input (px/s²).
@export_range(0.0, 20000.0, 10.0) var friction: float = 2800.0
## Dash speed (px/s). 0 disables dashing.
@export_range(0.0, 3000.0, 1.0) var dash_speed: float = 0.0
## Dash duration in seconds.
@export_range(0.02, 1.0, 0.01) var dash_duration: float = 0.12
## Seconds between dashes.
@export_range(0.0, 5.0, 0.01) var dash_cooldown: float = 0.5

## Intent: desired direction, length 0..1.
var move_vector := Vector2.ZERO
## Last non-zero movement direction.
var facing_dir := Vector2.RIGHT
## Compatibility with platformer code paths: sign of facing_dir.x.
var facing := 1

var _body: CharacterBody2D
var _dash_requested := false
var _dash_left := 0.0
var _dash_cd := 0.0
var _dash_dir := Vector2.RIGHT
var _control_lock := 0.0


func _ready() -> void:
	_body = get_parent() as CharacterBody2D
	if _body:
		_body.motion_mode = CharacterBody2D.MOTION_MODE_FLOATING


## Asks for a dash in the movement (or facing) direction.
func request_dash() -> void:
	_dash_requested = true


## Pushes the entity; control is reduced briefly.
func apply_knockback(impulse: Vector2) -> void:
	if _body == null:
		return
	_body.velocity = impulse
	_control_lock = 0.15
	_dash_left = 0.0


## True while dashing.
func is_dashing() -> bool:
	return _dash_left > 0.0


func _physics_process(delta: float) -> void:
	if _body == null:
		return
	_body.velocity = step_velocity(_body.velocity, delta)
	_body.move_and_slide()


## Pure movement step: returns the new velocity.
func step_velocity(v: Vector2, delta: float) -> Vector2:
	_dash_cd -= delta
	_control_lock -= delta
	var input := move_vector.limit_length(1.0)
	if input.length() > 0.1:
		facing_dir = input.normalized()
		if absf(facing_dir.x) > 0.1:
			facing = 1 if facing_dir.x > 0.0 else -1

	if _dash_requested and dash_speed > 0.0 and _dash_cd <= 0.0 and _dash_left <= 0.0:
		_dash_left = dash_duration
		_dash_cd = dash_cooldown + dash_duration
		_dash_dir = facing_dir
		dashed.emit()
	_dash_requested = false
	if _dash_left > 0.0:
		_dash_left -= delta
		if _dash_left <= 0.0:
			return _dash_dir * max_speed
		return _dash_dir * dash_speed

	var target := input * max_speed
	var rate := acceleration if input.length() > 0.1 else friction
	if _control_lock > 0.0:
		rate *= 0.15
	return v.move_toward(target, rate * delta)
