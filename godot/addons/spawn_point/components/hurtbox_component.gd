class_name HurtboxComponent
extends Area2D
## The area where this entity can be hit. Forwards damage to Health and pushes the entity back.

const SP_NAME := "Hurtbox"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = ["Health"]
const SP_INTERNAL: Array[String] = ["take_hit"]
const SP_CATEGORY := "core"

## Emitted when a hit lands (after invincibility checks).
signal hurt(amount: int)

## Hurtbox size relative to the entity shape. Below 1 is more forgiving for the player.
@export_range(0.1, 2.0, 0.05) var size_scale: float = 0.85
## Multiplies knockback received.
@export_range(0.0, 5.0, 0.05) var knockback_scale: float = 1.0

var _entity: Node2D


func _ready() -> void:
	_entity = SP.entity_of(get_parent()) as Node2D
	monitoring = false
	monitorable = true
	collision_mask = 0
	collision_layer = SP.hurtbox_layer(SP.team_of(_entity))


## Applies a hit coming from [param from_position]. Returns true if damage was dealt.
func take_hit(amount: int, from_position: Vector2, knockback: float) -> bool:
	var health := SP.component(_entity, &"Health") as HealthComponent
	if health == null or health.is_dead() or health.is_invincible():
		return false
	health.damage(amount)
	hurt.emit(amount)
	var mv := SP.movement(_entity)
	if mv and knockback > 0.0 and mv.has_method(&"apply_knockback"):
		var dir := (_entity.global_position - from_position).normalized()
		if dir == Vector2.ZERO:
			dir = Vector2.UP
		mv.apply_knockback(dir * knockback * knockback_scale)
	return true
