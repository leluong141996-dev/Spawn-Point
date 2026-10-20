class_name ProjectileComponent
extends Node
## Moves its entity in a straight line; disappears on walls, after its lifetime, or after
## hitting [member pierce] + 1 targets. Pair with a Hitbox to deal damage.

const SP_NAME := "Projectile"
const SP_HOSTS: Array[String] = ["Area2D"]
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "core"

## Emitted when the projectile disappears (wall, lifetime or last hit).
signal expired

## Speed in px/s.
@export_range(0.0, 5000.0, 1.0) var speed: float = 620.0
## Seconds before disappearing.
@export_range(0.05, 20.0, 0.05) var lifetime: float = 1.4
## Number of extra targets it passes through.
@export_range(0, 99) var pierce: int = 0

## Flight direction (set by the Weapon at spawn).
var direction := Vector2.RIGHT

var _entity: Area2D
var _age := 0.0
var _done := false


func _ready() -> void:
	_entity = get_parent() as Area2D
	if _entity.has_meta(&"sp_direction"):
		direction = (_entity.get_meta(&"sp_direction") as Vector2).normalized()
	# Sprites are drawn facing right: turn the visual toward the flight direction (arrows point where they fly).
	var visual := _entity.get_node_or_null(^"Visual/Shape") as Node2D
	if visual and direction.length() > 0.01:
		visual.rotation = direction.angle()
	_entity.body_entered.connect(_on_body_entered)
	var hitbox := SP.component(_entity, &"Hitbox") as HitboxComponent
	if hitbox:
		hitbox.hit.connect(_on_hit)


func _physics_process(delta: float) -> void:
	if _done:
		return
	_entity.global_position += direction * speed * delta
	_age += delta
	if _age >= lifetime:
		expire()


## Removes the projectile now.
func expire() -> void:
	if _done:
		return
	_done = true
	expired.emit()
	_entity.queue_free()


func _on_body_entered(_body: Node) -> void:
	expire()


func _on_hit(_target: Node) -> void:
	pierce -= 1
	if pierce < 0:
		expire()
