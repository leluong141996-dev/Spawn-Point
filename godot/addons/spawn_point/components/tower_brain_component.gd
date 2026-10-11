class_name TowerBrainComponent
extends Node
## A defence tower's brain: aims its Weapon at the enemy furthest along the road within [member fire_range]
## and keeps firing while one is there.

const SP_NAME := "TowerBrain"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = ["Weapon"]
const SP_CATEGORY := "controller"

## Firing range in px.
@export_range(16.0, 2000.0, 1.0) var fire_range: float = 150.0

var _entity: Node2D


func _ready() -> void:
	_entity = get_parent() as Node2D
	process_physics_priority = -10


func _physics_process(_delta: float) -> void:
	var weapon := SP.component(_entity, &"Weapon") as WeaponComponent
	if weapon == null:
		return
	var best: Node2D = null
	var best_progress := -1.0
	for e in get_tree().get_nodes_in_group(&"team_enemy"):
		var n := e as Node2D
		if n.global_position.distance_to(_entity.global_position) > fire_range or SP.component(n, &"Hurtbox") == null:
			continue
		var pf := SP.component(n, &"PathFollower") as PathFollowerComponent
		var progress := float(pf._next) if pf else 0.0  # first in line is the most dangerous
		if progress > best_progress:
			best_progress = progress
			best = n
	weapon.trigger_held = best != null and GameState.is_playing()
	if best:
		weapon.aim_direction = (best.global_position - _entity.global_position).normalized()
