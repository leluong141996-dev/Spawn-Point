class_name WeaponComponent
extends Node2D
## Fires projectile entities. Aim comes from aim_direction (set by Aim or ChaseAI), otherwise
## from the movement facing. Projectiles inherit the shooter's team.

const SP_NAME := "Weapon"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["current_direction"]
const SP_CATEGORY := "core"
## Parameters that must name an entity in the graph.
const SP_ENTITY_PARAMS: Array[String] = ["projectile"]

## Emitted every time the weapon fires.
signal fired

## Entity type spawned as the projectile (must have a Projectile component).
@export var projectile: String = "Bullet"
## Shots per second.
@export_range(0.1, 60.0, 0.1) var fire_rate: float = 6.0
## Random spread in degrees (total cone width).
@export_range(0.0, 180.0, 0.5) var spread_deg: float = 4.0
## Projectiles per shot (shotgun when > 1, spread evenly over spread_deg).
@export_range(1, 32) var projectile_count: int = 1
## Spawn distance from the entity center (px).
@export_range(0.0, 200.0, 1.0) var muzzle_distance: float = 20.0
## Fire continuously without input (enemies, turrets).
@export var auto_fire := false
## Push applied to the shooter opposite to the shot (px/s). 0 = none.
@export_range(0.0, 2000.0, 1.0) var recoil: float = 0.0

## Intent: true while the trigger is held.
var trigger_held := false
## Intent: aim direction (zero = use movement facing).
var aim_direction := Vector2.ZERO

var _entity: Node2D
var _cooldown := 0.0


func _ready() -> void:
	_entity = SP.entity_of(get_parent()) as Node2D


func _physics_process(delta: float) -> void:
	_cooldown -= delta
	if (trigger_held or auto_fire) and _cooldown <= 0.0 and GameState.is_playing():
		fire()


## Fires immediately (ignores the trigger, respects nothing else).
func fire() -> void:
	_cooldown = 1.0 / fire_rate
	var dir := current_direction()
	var team := SP.team_of(_entity)
	var n := projectile_count
	for i in n:
		var offset := 0.0
		if n > 1:
			offset = lerpf(-spread_deg * 0.5, spread_deg * 0.5, float(i) / float(n - 1))
		else:
			offset = randf_range(-spread_deg * 0.5, spread_deg * 0.5)
		var d := dir.rotated(deg_to_rad(offset))
		var p := World.spawn(projectile, global_position + d * muzzle_distance, {&"sp_team": team, &"sp_direction": d})
		if p:
			p.rotation = d.angle()
	if recoil > 0.0:
		var mv := SP.movement(_entity)
		if mv and mv.has_method(&"apply_knockback") and mv is TopDownMovementComponent:
			mv.apply_knockback(-dir * recoil)
	fired.emit()


## Direction the weapon currently fires in.
func current_direction() -> Vector2:
	if aim_direction.length() > 0.01:
		return aim_direction.normalized()
	var mv := SP.movement(_entity)
	if mv is TopDownMovementComponent:
		return (mv as TopDownMovementComponent).facing_dir
	if mv:
		return Vector2(mv.facing, 0)
	return Vector2.RIGHT
