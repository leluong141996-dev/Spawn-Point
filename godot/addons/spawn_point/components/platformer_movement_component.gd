class_name PlatformerMovementComponent
extends Node
## Side-view running and jumping tuned for good game feel.
##
## Includes coyote time (jump shortly after leaving a ledge), jump buffering (press jump shortly
## before landing), variable jump height (release early for a short hop), stronger gravity when
## falling, a little hang time at the apex, snappy turning and an optional dash.
## Reads intent (move_vector, jump requests) from a controller such as PlayerInput or PatrolAI.

const SP_NAME := "PlatformerMovement"
const SP_HOSTS: Array[String] = ["CharacterBody2D"]
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["step_velocity"]
const SP_CATEGORY := "movement"

## Emitted when a jump starts (ground, coyote or air jump).
signal jumped
## Emitted when touching the floor after being airborne. [param impact_speed] is the fall speed.
signal landed(impact_speed: float)
## Emitted when a dash starts.
signal dashed

## Top running speed (px/s).
@export_range(0.0, 2000.0, 1.0) var max_speed: float = 230.0
## Ground acceleration toward max speed (px/s²).
@export_range(0.0, 20000.0, 10.0) var acceleration: float = 2200.0
## Ground deceleration when no input (px/s²).
@export_range(0.0, 20000.0, 10.0) var deceleration: float = 2600.0
## Air acceleration (px/s²). Lower = less air control.
@export_range(0.0, 20000.0, 10.0) var air_acceleration: float = 1500.0
## Air deceleration when no input (px/s²).
@export_range(0.0, 20000.0, 10.0) var air_deceleration: float = 800.0
## Initial jump speed (px/s). Jump height ≈ jump_velocity² / (2·gravity).
@export_range(0.0, 3000.0, 1.0) var jump_velocity: float = 620.0
## Multiplies the project gravity for this entity.
@export_range(0.0, 5.0, 0.05) var gravity_scale: float = 1.0
## Extra gravity while falling — makes jumps feel weighty instead of floaty.
@export_range(1.0, 5.0, 0.05) var fall_gravity_multiplier: float = 1.7
## Vertical speed is multiplied by this when jump is released while rising (short hop).
@export_range(0.0, 1.0, 0.05) var jump_cut: float = 0.45
## Gravity multiplier near the top of a held jump (a little hang time).
@export_range(0.1, 1.0, 0.05) var apex_gravity_multiplier: float = 0.6
## Vertical speed below which the apex hang applies (px/s).
@export_range(0.0, 500.0, 1.0) var apex_threshold: float = 70.0
## Terminal fall speed (px/s).
@export_range(50.0, 5000.0, 1.0) var max_fall_speed: float = 900.0
## Seconds after leaving a ledge during which jumping still works.
@export_range(0.0, 0.5, 0.01) var coyote_time: float = 0.1
## Seconds a jump press is remembered before landing.
@export_range(0.0, 0.5, 0.01) var jump_buffer: float = 0.12
## Extra jumps in the air (1 = double jump).
@export_range(0, 5) var air_jumps: int = 0
## Dash speed (px/s). 0 disables dashing.
@export_range(0.0, 3000.0, 1.0) var dash_speed: float = 0.0
## Dash duration in seconds.
@export_range(0.02, 1.0, 0.01) var dash_duration: float = 0.14
## Seconds between dashes.
@export_range(0.0, 5.0, 0.01) var dash_cooldown: float = 0.45

## Intent: x in -1..1 is the run direction (y is ignored).
var move_vector := Vector2.ZERO
## Intent: true while the jump button is held (enables full-height jumps).
var jump_held := false
## 1 = facing right, -1 = facing left.
var facing := 1

var _body: CharacterBody2D
var _coyote_left := 0.0
var _buffer_left := 0.0
var _air_jumps_left := 0
var _rising_from_jump := false
var _dash_requested := false
var _dash_left := 0.0
var _dash_cd := 0.0
var _dash_dir := 1
var _control_lock := 0.0
var _was_on_floor := true


func _ready() -> void:
	_body = get_parent() as CharacterBody2D
	if _body:
		_body.motion_mode = CharacterBody2D.MOTION_MODE_GROUNDED
		_body.floor_snap_length = 6.0


## Asks for a jump; it happens as soon as it is allowed (buffered).
func request_jump() -> void:
	_buffer_left = jump_buffer if jump_buffer > 0.0 else 0.0001


## Asks for a dash in the move / facing direction.
func request_dash() -> void:
	_dash_requested = true


## Launches the entity upward (e.g. after stomping an enemy). Not cut by releasing jump.
func bounce(speed: float) -> void:
	if _body:
		_body.velocity.y = -absf(speed)
	_rising_from_jump = false


## Pushes the entity; player control is reduced briefly so the push is felt.
func apply_knockback(impulse: Vector2) -> void:
	if _body == null:
		return
	_body.velocity = Vector2(impulse.x, minf(impulse.y, -absf(impulse.length()) * 0.5))
	_control_lock = 0.18
	_dash_left = 0.0
	_rising_from_jump = false


## True while dashing.
func is_dashing() -> bool:
	return _dash_left > 0.0


func _physics_process(delta: float) -> void:
	if _body == null:
		return
	var v := step_velocity(_body.velocity, delta, _body.is_on_floor())
	_body.velocity = v
	_body.move_and_slide()
	var on_floor := _body.is_on_floor()
	if on_floor and not _was_on_floor:
		landed.emit(maxf(v.y, 0.0))
	_was_on_floor = on_floor


## Pure movement step: returns the new velocity. Separated from physics for testing.
func step_velocity(v: Vector2, delta: float, on_floor: bool) -> Vector2:
	var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity", 1600.0) * gravity_scale

	if on_floor:
		_coyote_left = coyote_time
		_air_jumps_left = air_jumps
	else:
		_coyote_left -= delta
	_buffer_left -= delta
	_dash_cd -= delta
	_control_lock -= delta

	if move_vector.x != 0.0:
		facing = 1 if move_vector.x > 0.0 else -1

	# Dash: fixed horizontal speed, no gravity.
	if _dash_requested and dash_speed > 0.0 and _dash_cd <= 0.0 and _dash_left <= 0.0:
		_dash_left = dash_duration
		_dash_cd = dash_cooldown + dash_duration
		_dash_dir = facing
		dashed.emit()
	_dash_requested = false
	if _dash_left > 0.0:
		_dash_left -= delta
		if _dash_left <= 0.0:
			return Vector2(_dash_dir * max_speed, 0.0)
		return Vector2(_dash_dir * dash_speed, 0.0)

	# Horizontal.
	var target := clampf(move_vector.x, -1.0, 1.0) * max_speed
	var accel: float
	if on_floor:
		accel = acceleration if absf(target) > 0.01 else deceleration
	else:
		accel = air_acceleration if absf(target) > 0.01 else air_deceleration
	if absf(target) > 0.01 and signf(target) != signf(v.x) and v.x != 0.0:
		accel *= 1.6  # Snappy turnarounds.
	if _control_lock > 0.0:
		accel *= 0.15
	v.x = move_toward(v.x, target, accel * delta)

	# Jump (buffered, coyote, air jumps).
	if _buffer_left > 0.0:
		if on_floor or _coyote_left > 0.0:
			v.y = _start_jump()
		elif _air_jumps_left > 0:
			_air_jumps_left -= 1
			v.y = _start_jump()

	# Variable jump height.
	if _rising_from_jump and not jump_held and v.y < 0.0:
		v.y *= jump_cut
		_rising_from_jump = false
	if v.y >= 0.0:
		_rising_from_jump = false

	# Gravity.
	if not on_floor or v.y < 0.0:
		var g := gravity
		if v.y > 0.0:
			g *= fall_gravity_multiplier
		elif absf(v.y) < apex_threshold and jump_held:
			g *= apex_gravity_multiplier
		v.y = minf(v.y + g * delta, max_fall_speed)
	return v


func _start_jump() -> float:
	_buffer_left = 0.0
	_coyote_left = 0.0
	_rising_from_jump = true
	jumped.emit()
	return -jump_velocity
