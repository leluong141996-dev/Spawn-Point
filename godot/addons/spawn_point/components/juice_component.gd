class_name JuiceComponent
extends Node
## Game feel for one entity. Wires itself to whatever sibling components exist and adds
## feedback: squash & stretch on jump/land, white flash + shake + hit-stop when hurt,
## after-images on dash, particle bursts on death and pickup, recoil shake and sounds.
## Attached automatically to every entity unless the game disables juice.

const SP_NAME := "Juice"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "juice"

const FLASH_SHADER := preload("res://addons/spawn_point/shaders/flash.gdshader")

## Squash & stretch on jump, land and hit.
@export var squash := true
## Squash strength (0.3 = 30% deformation).
@export_range(0.0, 0.8, 0.01) var squash_amount: float = 0.28
## Flash white when damaged.
@export var flash := true
## Screen shake when this entity is hurt (0..1 trauma).
@export_range(0.0, 1.0, 0.01) var shake_on_hurt: float = 0.35
## Screen shake when this entity dies.
@export_range(0.0, 1.0, 0.01) var shake_on_death: float = 0.45
## Screen shake when this entity fires.
@export_range(0.0, 1.0, 0.01) var shake_on_fire: float = 0.06
## Hit-stop (freeze frame) seconds when hurt.
@export_range(0.0, 0.3, 0.005) var hitstop_on_hurt: float = 0.06
## Hit-stop seconds when killed.
@export_range(0.0, 0.3, 0.005) var hitstop_on_death: float = 0.04
## Particle effects (death burst, landing dust, pickup sparkle).
@export var particles := true
## After-images while dashing.
@export var dash_trail := true
## Turn the visual to face the movement direction.
@export var face_movement := true
## Play sound effects.
@export var sounds := true
## Random pitch variation for sounds (0.1 = ±10%).
@export_range(0.0, 0.5, 0.01) var pitch_variance: float = 0.1
## Sound played on jump.
@export var sound_jump: String = "jump"
## Sound played on a hard landing.
@export var sound_land: String = "land"
## Sound played when damaged.
@export var sound_hurt: String = "hurt"
## Sound played on death.
@export var sound_death: String = "explosion"
## Sound played when the Weapon fires.
@export var sound_fire: String = "shoot"
## Sound played when collected (pitch rises on quick chains).
@export var sound_collect: String = "coin"
## Sound played on dash.
@export var sound_dash: String = "dash"

var _entity: Node2D
var _visual: Node2D
var _shape: Node2D
var _mat: ShaderMaterial
var _squash_tween: Tween
var _flash_tween: Tween
var _ghost_timer := 0.0
var _ghost_accum := 0.0
var _base_scale := Vector2.ONE


func _ready() -> void:
	_entity = SP.entity_of(get_parent()) as Node2D
	_visual = _entity.get_node_or_null(^"Visual") as Node2D
	_shape = _entity.get_node_or_null(^"Visual/Shape") as Node2D
	if _visual:
		_base_scale = _visual.scale
		if flash:
			_mat = ShaderMaterial.new()
			_mat.shader = FLASH_SHADER
			_visual.material = _mat
			for ci in _visual.find_children("*", "CanvasItem", true, false):
				(ci as CanvasItem).material = _mat
	_wire.call_deferred()


func _wire() -> void:
	var mv := SP.movement(_entity)
	if mv:
		if mv.has_signal(&"jumped"):
			mv.jumped.connect(_on_jumped)
		if mv.has_signal(&"landed"):
			mv.landed.connect(_on_landed)
		if mv.has_signal(&"dashed"):
			mv.dashed.connect(_on_dashed)
	var health := SP.component(_entity, &"Health") as HealthComponent
	if health:
		health.damaged.connect(_on_damaged)
		health.died.connect(_on_died)
	var weapon := SP.component(_entity, &"Weapon") as WeaponComponent
	if weapon:
		weapon.fired.connect(_on_fired)
	var collectible := SP.component(_entity, &"Collectible") as CollectibleComponent
	if collectible:
		collectible.collected.connect(_on_collected)
	var projectile := SP.component(_entity, &"Projectile") as ProjectileComponent
	if projectile:
		projectile.expired.connect(_on_projectile_expired)
	var stomp := SP.component(_entity, &"Stomp") as StompComponent
	if stomp:
		stomp.stomped.connect(_on_stomped)
	var gate := SP.component(_entity, &"Gate") as GateComponent
	if gate:
		gate.opened.connect(_play.bind("powerup"))


func _process(delta: float) -> void:
	if _ghost_timer > 0.0:
		_ghost_timer -= delta
		_ghost_accum += delta
		if _ghost_accum >= 0.03:
			_ghost_accum = 0.0
			FX.ghost(_visual, Color(1, 1, 1, 0.45))
	if not face_movement or _shape == null:
		return
	var mv := SP.movement(_entity)
	if mv is PlatformerMovementComponent:
		SP.face(_entity, Vector2((mv as PlatformerMovementComponent).facing, 0), false)
	elif mv is TopDownMovementComponent and SP.component(_entity, &"Aim") == null:
		SP.face(_entity, (mv as TopDownMovementComponent).facing_dir, true, clampf(delta * 14.0, 0.0, 1.0))


## Squash (x wider, y shorter) when [param amount] > 0, stretch when < 0, then spring back.
func squash_stretch(amount: float, duration := 0.22) -> void:
	if not squash or _visual == null:
		return
	if _squash_tween:
		_squash_tween.kill()
	_visual.scale = _base_scale * Vector2(1.0 + amount, 1.0 - amount)
	_squash_tween = _visual.create_tween()
	_squash_tween.tween_property(_visual, ^"scale", _base_scale, duration).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)


## Flashes the visual white for [param duration] seconds.
func flash_white(duration := 0.12) -> void:
	if _mat == null:
		return
	if _flash_tween:
		_flash_tween.kill()
	_mat.set_shader_parameter(&"flash", 1.0)
	_flash_tween = _visual.create_tween()
	_flash_tween.tween_method(func(v: float) -> void: _mat.set_shader_parameter(&"flash", v), 1.0, 0.0, duration)


func _on_jumped() -> void:
	squash_stretch(-squash_amount)
	_play(sound_jump)


func _on_landed(impact_speed: float) -> void:
	var k := clampf(impact_speed / 900.0, 0.2, 1.0)
	squash_stretch(squash_amount * k)
	if particles and impact_speed > 250.0:
		var feet := _entity.global_position + Vector2(0, SP.half_size(_entity).y)
		FX.burst(feet, Color(1, 1, 1, 0.55), int(6 + 8 * k), 90.0 * k + 40.0, 0.35, 3.0, -60.0)
	if impact_speed > 250.0:
		_play(sound_land, -6.0)


func _on_dashed() -> void:
	if dash_trail:
		_ghost_timer = 0.15
	squash_stretch(-squash_amount * 0.6, 0.15)
	_play(sound_dash)


func _on_damaged(_amount: int) -> void:
	if flash:
		flash_white()
	squash_stretch(squash_amount * 0.8, 0.18)
	FX.shake(shake_on_hurt)
	FX.hitstop(hitstop_on_hurt)
	_play(sound_hurt)


func _on_died() -> void:
	if particles:
		FX.burst(_entity.global_position, SP.color_of(_entity), 28, 260.0, 0.6, 5.0)
		FX.burst(_entity.global_position, Color.WHITE, 10, 160.0, 0.3, 3.0)
	FX.shake(shake_on_death)
	FX.hitstop(hitstop_on_death)
	_play(sound_death)


func _on_fired() -> void:
	FX.shake(shake_on_fire)
	squash_stretch(squash_amount * 0.3, 0.1)
	_play(sound_fire)


func _on_collected(_by: Node) -> void:
	if particles:
		FX.burst(_entity.global_position, SP.color_of(_entity), 12, 150.0, 0.4, 3.0, 0.0)
	var c := SP.component(_entity, &"Collectible") as CollectibleComponent
	if c and c.score > 0:
		FX.float_text(_entity.global_position, "+%d" % c.score, SP.color_of(_entity))
	if sounds:
		Sfx.play_combo(sound_collect)


func _on_projectile_expired() -> void:
	if particles:
		FX.burst(_entity.global_position, SP.color_of(_entity), 5, 90.0, 0.2, 2.5, 0.0)


func _on_stomped(_target: Node) -> void:
	squash_stretch(-squash_amount)
	FX.shake(0.25)
	_play(sound_jump, 0.0, 1.25)


func _play(sound_name: String, volume_db := 0.0, pitch := 1.0) -> void:
	if sounds:
		Sfx.play(sound_name, pitch_variance, volume_db, pitch)
