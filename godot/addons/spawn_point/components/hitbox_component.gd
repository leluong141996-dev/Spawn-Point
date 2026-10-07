class_name HitboxComponent
extends Area2D
## Deals damage to hurtboxes of the opposing team on contact (enemy bodies, bullets, spikes).

const SP_NAME := "Hitbox"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["refresh_team"]
const SP_CATEGORY := "core"

## Emitted when this hitbox damages [param target] (the entity that was hit).
signal hit(target: Node)

## Damage per hit.
@export_range(0, 999) var damage: int = 1
## Push applied to the victim, in pixels/second.
@export_range(0.0, 2000.0, 1.0) var knockback: float = 260.0
## Hitbox size relative to the entity shape.
@export_range(0.1, 2.0, 0.05) var size_scale: float = 1.0
## Neutral hitboxes (traps) hurt both teams.
@export var hurts_own_team := false

var _entity: Node2D


func _ready() -> void:
	_entity = SP.entity_of(get_parent()) as Node2D
	monitorable = false
	monitoring = true
	collision_layer = 0
	refresh_team()


## Re-reads the entity team (call after changing it at runtime).
func refresh_team() -> void:
	var team := SP.team_of(_entity)
	collision_mask = SP.opposing_hurtbox_mask(team)
	if hurts_own_team:
		collision_mask |= SP.hurtbox_layer(team)


func _physics_process(_delta: float) -> void:
	# Polling overlaps (instead of area_entered) keeps damaging a victim that stays inside us
	# once its invincibility ends.
	for area in get_overlapping_areas():
		var hb := area as HurtboxComponent
		if hb == null or SP.entity_of(hb) == _entity:
			continue
		if hb.take_hit(damage, global_position, knockback):
			hit.emit(SP.entity_of(hb))
