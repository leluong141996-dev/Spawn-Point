class_name StompComponent
extends Area2D
## Platformer "jump on their head" attack: landing on an enemy from above damages it and
## bounces this entity up. Grants a moment of invincibility so the enemy's contact damage
## does not trigger in the same frame.

const SP_NAME := "Stomp"
const SP_HOSTS: Array[String] = ["CharacterBody2D"]
const SP_REQUIRES: Array[String] = ["PlatformerMovement"]
const SP_CATEGORY := "core"

## Emitted after a successful stomp on [param target].
signal stomped(target: Node)

## Damage dealt by a stomp.
@export_range(0, 999) var damage: int = 1
## Upward speed after a stomp (px/s). Holding jump does not add to it.
@export_range(0.0, 3000.0, 1.0) var bounce_velocity: float = 480.0
## Stomp area size relative to the entity shape.
@export_range(0.1, 2.0, 0.05) var size_scale: float = 1.0

var _body: CharacterBody2D


func _ready() -> void:
	_body = SP.entity_of(get_parent()) as CharacterBody2D
	monitorable = false
	monitoring = true
	collision_layer = 0
	collision_mask = SP.opposing_hurtbox_mask(SP.team_of(_body))
	# Run before enemy hitboxes so a stomp wins over contact damage.
	process_physics_priority = -20


func _physics_process(_delta: float) -> void:
	if _body.velocity.y <= 0.0:
		return
	var feet := _body.global_position.y + SP.half_size(_body).y
	for area in get_overlapping_areas():
		var hb := area as HurtboxComponent
		if hb == null:
			continue
		var target := SP.entity_of(hb) as Node2D
		if target == null or target == _body:
			continue
		# Only counts when our feet are above the target's center.
		if feet > target.global_position.y + 2.0:
			continue
		var my_health := SP.component(_body, &"Health") as HealthComponent
		if my_health:
			my_health.grant_invincibility(0.2)
		hb.take_hit(damage, _body.global_position, 0.0)
		var mv := SP.component(_body, &"PlatformerMovement") as PlatformerMovementComponent
		mv.bounce(bounce_velocity)
		stomped.emit(target)
		return
