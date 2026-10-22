class_name AnimatorComponent
extends Node
## Plays the entity sprite's animations from what the entity is doing: idle, run, jump, fall, hurt and
## attack (each time its Weapon fires). Run speed follows movement speed. Attached automatically to entities
## that have a sprite. The "die" animation is played by FX.death_anim when the entity is removed.

const SP_NAME := "Animator"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "juice"

## Seconds the hurt animation is shown after taking damage.
@export_range(0.0, 2.0, 0.01) var hurt_time: float = 0.25
## Seconds the attack animation is shown after the weapon fires (a little under its length, so it never repeats).
@export_range(0.0, 1.0, 0.01) var attack_time: float = 0.2
## Speed (px/s) above which the entity counts as moving.
@export_range(0.0, 200.0, 1.0) var move_threshold: float = 15.0

## Animation currently requested (may fall back to "idle" if the sprite lacks it).
var state := "idle"

var _entity: Node2D
var _sprite: AnimatedSprite2D
var _hurt_left := 0.0
var _attack_left := 0.0


func _ready() -> void:
	_entity = SP.entity_of(get_parent()) as Node2D
	_sprite = _entity.get_node_or_null(^"Visual/Shape/Sprite") as AnimatedSprite2D
	var health := SP.component(_entity, &"Health") as HealthComponent
	if health:
		health.damaged.connect(func(_a: int) -> void: _hurt_left = hurt_time)
	var weapon := SP.component(_entity, &"Weapon") as WeaponComponent
	if weapon:
		weapon.fired.connect(_on_fired)


func _on_fired() -> void:
	play_attack()


## Shows the attack animation once (also for attacks that are not a Weapon, like a played card).
func play_attack() -> void:
	if _sprite and _sprite.sprite_frames.has_animation(&"attack"):
		_attack_left = attack_time
		_sprite.play(&"attack")  # restart on every shot


func _process(delta: float) -> void:
	if _sprite == null:
		return
	_hurt_left -= delta
	_attack_left -= delta
	state = pick_state()
	var anim := _directed(state)
	if not _sprite.sprite_frames.has_animation(anim):
		anim = state if _sprite.sprite_frames.has_animation(state) else &"idle"
	if _sprite.animation != anim or not _sprite.is_playing():
		_sprite.play(anim)
	if state == "run":
		var mv := SP.movement(_entity)
		var top: float = mv.max_speed if mv else 200.0
		_sprite.speed_scale = clampf(_speed() / maxf(top, 1.0) * 1.2, 0.5, 1.6)
	else:
		_sprite.speed_scale = 1.0


## Four-direction sprites (top-down RPG style) have "run_up", "idle_side"...: [param s] with the facing appended,
## or [param s] itself when facing down (the plain animations face down).
func _directed(s: String) -> String:
	var mv := SP.movement(_entity)
	if not (mv is TopDownMovementComponent) or not _sprite.sprite_frames.has_animation(&"idle_up"):
		return s
	var d: Vector2 = (mv as TopDownMovementComponent).facing_dir
	if absf(d.x) > absf(d.y) + 0.05:
		return s + "_side"
	return s + "_up" if d.y < 0.0 else s


## The state the entity is in right now.
func pick_state() -> String:
	if _hurt_left > 0.0:
		return "hurt"
	if _attack_left > 0.0:
		return "attack"
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
