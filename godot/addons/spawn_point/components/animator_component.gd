class_name AnimatorComponent
extends Node
## Plays the entity sprite's animations from what the entity is doing: idle, run, jump, fall and
## hurt. Run speed follows movement speed. Attached automatically to entities that have a sprite.

const SP_NAME := "Animator"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "juice"

## Seconds the hurt animation is shown after taking damage.
@export_range(0.0, 2.0, 0.01) var hurt_time: float = 0.25
## Speed (px/s) above which the entity counts as moving.
@export_range(0.0, 200.0, 1.0) var move_threshold: float = 15.0

## Animation currently requested (may fall back to "idle" if the sprite lacks it).
var state := "idle"

var _entity: Node2D
var _sprite: AnimatedSprite2D
var _hurt_left := 0.0


func _ready() -> void:
	_entity = SP.entity_of(get_parent()) as Node2D
	_sprite = _entity.get_node_or_null(^"Visual/Shape/Sprite") as AnimatedSprite2D
	var health := SP.component(_entity, &"Health") as HealthComponent
	if health:
		health.damaged.connect(func(_a: int) -> void: _hurt_left = hurt_time)


func _process(delta: float) -> void:
	if _sprite == null:
		return
	_hurt_left -= delta
	state = pick_state()
	var anim := state if _sprite.sprite_frames.has_animation(state) else &"idle"
	if _sprite.animation != anim or not _sprite.is_playing():
		_sprite.play(anim)
	if state == "run":
		var mv := SP.movement(_entity)
		var top: float = mv.max_speed if mv else 200.0
		_sprite.speed_scale = clampf(_speed() / maxf(top, 1.0) * 1.2, 0.5, 1.6)
	else:
		_sprite.speed_scale = 1.0


## The state the entity is in right now.
func pick_state() -> String:
	if _hurt_left > 0.0:
		return "hurt"
	var body := _entity as CharacterBody2D
	if body == null:
		return "idle"
	if SP.movement(_entity) is PlatformerMovementComponent and not body.is_on_floor():
		return "jump" if body.velocity.y < 0.0 else "fall"
	return "run" if _speed() > move_threshold else "idle"


func _speed() -> float:
	var body := _entity as CharacterBody2D
	if body == null:
		return 0.0
	if SP.movement(_entity) is PlatformerMovementComponent:
		return absf(body.velocity.x)
	return body.velocity.length()
