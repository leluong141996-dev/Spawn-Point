class_name AimComponent
extends Node
## Points the entity's Weapon (and visual) at the mouse, the nearest enemy, or the movement
## direction.

const SP_NAME := "Aim"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = ["Weapon"]
const SP_INTERNAL: Array[String] = ["aim_direction"]
const SP_CATEGORY := "controller"

## "mouse", "nearest_enemy" or "movement".
@export_enum("mouse", "nearest_enemy", "movement") var mode: String = "mouse"
## Rotate the visual to face the aim direction (top-down games).
@export var rotate_visual := true
## Max distance for nearest_enemy targeting (px).
@export_range(0.0, 5000.0, 1.0) var max_range: float = 600.0

var _entity: Node2D


func _ready() -> void:
	_entity = SP.entity_of(get_parent()) as Node2D
	process_physics_priority = -5


func _physics_process(_delta: float) -> void:
	var dir := aim_direction()
	var weapon := SP.component(_entity, &"Weapon") as WeaponComponent
	if weapon:
		weapon.aim_direction = dir
	if rotate_visual and dir != Vector2.ZERO:
		SP.face(_entity, dir, true)


## Current aim direction (normalized, or zero if there is nothing to aim at).
func aim_direction() -> Vector2:
	match mode:
		"mouse":
			var vp := _entity.get_viewport()
			if vp:
				return (_entity.get_global_mouse_position() - _entity.global_position).normalized()
		"nearest_enemy":
			var best: Node2D = null
			var best_d := max_range
			var my_team := SP.team_of(_entity)
			for e in _entity.get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
				var n := e as Node2D
				if n == null or n == _entity or SP.team_of(n) == my_team or SP.team_of(n) == SP.TEAM_NEUTRAL:
					continue
				if SP.component(n, &"Hurtbox") == null:
					continue
				var d := n.global_position.distance_to(_entity.global_position)
				if d < best_d:
					best_d = d
					best = n
			if best:
				return (best.global_position - _entity.global_position).normalized()
		"movement":
			var mv := SP.movement(_entity)
			if mv is TopDownMovementComponent:
				return (mv as TopDownMovementComponent).facing_dir
	return Vector2.ZERO
