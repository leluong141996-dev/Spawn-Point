class_name FlightPathComponent
extends Node
## Flies its entity across the screen on a pattern (side-scrolling shooters). "straight" keeps its heading, "wave"
## swings up and down along it, "dive" turns toward the player's height while the player is still ahead, "hover"
## flies in, stops at [member hover_at] and bobs up and down (gunships and bosses). Drives a TopDownMovement
## body, or moves an Area2D directly at [member speed]. Leaves the screen quietly past the far edge.

const SP_NAME := "FlightPath"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["desired_direction"]
const SP_CATEGORY := "controller"

## Emitted when the entity flew off the far edge without being destroyed.
signal escaped

## How it flies.
@export_enum("straight", "wave", "dive", "hover") var pattern: String = "straight"
## Direction of travel in degrees (180 = leftward, 0 = rightward).
@export_range(0.0, 360.0, 1.0) var heading_deg: float = 180.0
## Speed (px/s) when the entity has no TopDownMovement of its own.
@export_range(0.0, 600.0, 1.0) var speed: float = 90.0
## Wave: how far it swings (px). Hover: how far it bobs.
@export_range(0.0, 300.0, 1.0) var amplitude: float = 70.0
## Wave and hover: swings per second.
@export_range(0.1, 6.0, 0.1) var frequency: float = 0.9
## Hover: where it stops, as a fraction of the level width from the left edge.
@export_range(0.0, 1.0, 0.01) var hover_at: float = 0.75
## Point the Weapon at the player every frame.
@export var aim_at_player := false
## Distance from the far edge (px) at which it counts as having left.
@export_range(0.0, 400.0, 1.0) var exit_margin: float = 72.0

var _entity: Node2D
var _mv: Node
var _age := 0.0
var _phase := 0.0
var _origin_y := 0.0


func _ready() -> void:
	process_physics_priority = -10  # a controller: decide before the movement body acts
	_entity = SP.entity_of(get_parent()) as Node2D
	_mv = SP.movement(_entity)
	_phase = randf() * TAU
	_origin_y = _entity.global_position.y


func _physics_process(delta: float) -> void:
	if not GameState.is_playing():
		if _mv:
			_mv.move_vector = Vector2.ZERO
		return
	_age += delta
	var dir := desired_direction()
	if _mv:
		_mv.move_vector = dir
	else:
		_entity.global_position += dir * speed * delta
	if aim_at_player:
		var weapon := SP.component(_entity, &"Weapon") as WeaponComponent
		var player := World.player()
		if weapon and player:
			weapon.aim_direction = (player.global_position - _entity.global_position).normalized()
	var b := _bounds()
	var heading := Vector2.from_angle(deg_to_rad(heading_deg))
	var pos := _entity.global_position
	if (heading.x < -0.1 and pos.x < b.position.x + exit_margin) or (heading.x > 0.1 and pos.x > b.end.x - exit_margin):
		escaped.emit()
		World.destroy(_entity)


## Where the entity wants to go this frame (a unit vector, or zero).
func desired_direction() -> Vector2:
	var h := Vector2.from_angle(deg_to_rad(heading_deg))
	var pos := _entity.global_position
	match pattern:
		"wave":
			var vy := amplitude * TAU * frequency * cos(TAU * frequency * _age + _phase)
			var base: float = _mv.max_speed if _mv else speed
			return (h * base + Vector2(0, vy)).normalized()
		"dive":
			var p := World.player()
			if p and (p.global_position.x - pos.x) * h.x > 0.0:  # the player is still ahead
				var steer := clampf((p.global_position.y - pos.y) / 120.0, -1.0, 1.0) * 1.3
				return (h + Vector2(0, steer)).normalized()
			return h
		"hover":
			var b := _bounds()
			var stop_x := b.position.x + b.size.x * hover_at
			if (pos.x - stop_x) * h.x < 0.0:  # still flying in
				return h
			var target_y := clampf(_origin_y + amplitude * sin(TAU * frequency * _age + _phase),
					b.position.y + 64.0, b.end.y - 64.0)
			return Vector2(0, clampf((target_y - pos.y) / 16.0, -1.0, 1.0))
	return h


func _bounds() -> Rect2:
	var b = World.level.get(&"bounds") if World.level else null
	return b if b is Rect2 else Rect2(0, 0, 960, 540)
