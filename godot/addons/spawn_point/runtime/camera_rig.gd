class_name SPCameraRig
extends Camera2D
## Follows the player with smoothing and look-ahead; trauma-based screen shake.
##
## Shake follows the "trauma" model: offset = max_offset * trauma² * noise(t). Trauma decays
## linearly, so small hits produce subtle jitter and big hits a strong, short shake.

## Maximum shake offset in pixels at trauma 1.
@export var max_shake_offset := Vector2(14, 10)
## Maximum shake rotation in radians at trauma 1.
@export var max_shake_rotation := 0.04
## Trauma lost per second.
@export var trauma_decay := 1.6
## How far ahead of the player the camera looks, in pixels at full speed.
@export var look_ahead := Vector2(48, 0)
## Smoothing speed of the look-ahead offset.
@export var look_ahead_speed := 3.0

var trauma := 0.0
var _noise := FastNoiseLite.new()
var _t := 0.0
var _look := Vector2.ZERO
var _target: Node2D


func _ready() -> void:
	position_smoothing_enabled = true
	if position_smoothing_speed <= 0.0:
		position_smoothing_speed = 7.0
	ignore_rotation = false
	_noise.seed = randi()
	_noise.frequency = 2.0
	FX.register_camera(self)
	make_current()
	_snap_to_target.call_deferred()


func _exit_tree() -> void:
	FX.unregister_camera(self)


func add_trauma(amount: float) -> void:
	trauma = clampf(trauma + amount, 0.0, 1.0)


func _snap_to_target() -> void:
	_target = World.player()
	if _target:
		global_position = _target.global_position
		reset_smoothing()


func _process(delta: float) -> void:
	if _target == null or not is_instance_valid(_target):
		_target = World.player()
	if _target:
		var vel := Vector2.ZERO
		if _target is CharacterBody2D:
			vel = (_target as CharacterBody2D).velocity
		var desired := Vector2(signf(vel.x) * look_ahead.x if absf(vel.x) > 20.0 else _look.x,
				signf(vel.y) * look_ahead.y if absf(vel.y) > 20.0 else _look.y)
		_look = _look.lerp(desired, clampf(look_ahead_speed * delta, 0.0, 1.0))
		global_position = _target.global_position + _look

	_t += delta
	trauma = maxf(trauma - trauma_decay * delta, 0.0)
	var s := trauma * trauma
	offset = Vector2(
			max_shake_offset.x * s * _noise.get_noise_2d(_t * 60.0, 0.0),
			max_shake_offset.y * s * _noise.get_noise_2d(0.0, _t * 60.0))
	rotation = max_shake_rotation * s * _noise.get_noise_2d(_t * 60.0, 100.0)
	if FX.pixel_art:  # pixel art shakes in whole pixels and never rotates, or its edges shimmer
		offset = offset.round()
		rotation = 0.0
