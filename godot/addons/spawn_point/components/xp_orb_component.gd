class_name XpOrbComponent
extends Node
## An experience gem dropped by defeated enemies. It drifts toward a player that has an
## [ExperienceComponent] once inside their magnet radius, then gives [member value] XP on touch.

const SP_NAME := "XpOrb"
const SP_HOSTS: Array[String] = ["Area2D"]
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "core"

## Emitted when picked up; [param by] is the collecting entity.
signal absorbed(by: Node)

## XP given on pickup.
@export_range(1, 10000) var value: int = 1
## Top speed when pulled by a magnet (px/s).
@export_range(0.0, 5000.0, 1.0) var pull_speed: float = 520.0
## Disappears after this many seconds (0 = never).
@export_range(0.0, 600.0, 0.5) var lifetime: float = 0.0

var _entity: Area2D
var _taken := false
var _speed := 0.0
var _age := 0.0


func _ready() -> void:
	_entity = get_parent() as Area2D
	_entity.body_entered.connect(_on_body_entered)


func _physics_process(delta: float) -> void:
	if _taken:
		return
	_age += delta
	if lifetime > 0.0 and _age > lifetime:
		_entity.queue_free()
		return
	var p := World.player()
	var xp := SP.component(p, &"Experience") as ExperienceComponent if p else null
	if xp == null:
		return
	var to := p.global_position - _entity.global_position
	if to.length() <= xp.magnet_radius or _speed > 0.0:
		_speed = minf(pull_speed, _speed + pull_speed * 3.0 * delta)
		_entity.global_position += to.normalized() * minf(_speed * delta, to.length())
		if to.length() < 12.0:
			_absorb(p)


func _on_body_entered(body: Node) -> void:
	if body.is_in_group(SP.PLAYER_GROUP):
		_absorb(body)


func _absorb(by: Node) -> void:
	if _taken:
		return
	var xp := SP.component(by, &"Experience") as ExperienceComponent
	if xp == null:
		return
	_taken = true
	_entity.queue_free()
	if Sfx.has_sound("coin"):
		Sfx.play_combo("coin", 0.5, 16)  # rising pitch while a stream of gems comes in
	xp.add_xp(value)
	absorbed.emit(by)
