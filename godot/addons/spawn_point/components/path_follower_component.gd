class_name PathFollowerComponent
extends Node
## Walks its entity along the road to the [BaseComponent] (tower-defense enemies). The road is every entity
## of type [member road]; the route is the shortest chain of road cells from where the entity spawns to the
## base. Drives a TopDownMovement.

const SP_NAME := "PathFollower"
const SP_HOSTS: Array[String] = ["CharacterBody2D"]
const SP_REQUIRES: Array[String] = ["TopDownMovement"]
const SP_INTERNAL: Array[String] = ["route", "build_route"]
const SP_CATEGORY := "controller"
const SP_ENTITY_PARAMS: Array[String] = ["road"]

## Entity type that marks the road cells.
@export var road: String = "Road"

var route: Array[Vector2] = []
var _entity: CharacterBody2D
var _next := 0


func _ready() -> void:
	_entity = get_parent() as CharacterBody2D
	process_physics_priority = -10
	build_route.call_deferred()


## Breadth-first search over road cells (4-neighbourhood) from the nearest cell to the base's cell.
func build_route() -> void:
	route.clear()
	_next = 0
	var lvl := World.level as SPLevel
	var ts := float(lvl.tile_size) if lvl else 32.0
	var cells := {}
	for e in World.instances(StringName(road)):
		cells[_cell((e as Node2D).global_position, ts)] = (e as Node2D).global_position
	var goal: Node2D = null
	for e in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
		if SP.component(e, &"Base"):
			goal = e as Node2D
	if cells.is_empty() or goal == null:
		return
	var start := _cell(_entity.global_position, ts)
	if not cells.has(start):
		var best := INF
		for c: Vector2i in cells:
			var d := Vector2(c - start).length()
			if d < best:
				best = d
				start = c
	var end := _cell(goal.global_position, ts)
	var prev := {start: start}
	var queue: Array[Vector2i] = [start]
	var reached := start
	var best_end := INF
	while not queue.is_empty():
		var c: Vector2i = queue.pop_front()
		var d := Vector2(c - end).length()
		if d < best_end:
			best_end = d
			reached = c
		if c == end:
			break
		for o in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var n: Vector2i = c + o
			if cells.has(n) and not prev.has(n):
				prev[n] = c
				queue.append(n)
	var chain: Array[Vector2] = [goal.global_position]
	var c2: Vector2i = reached
	while true:
		chain.push_front(cells[c2])
		if c2 == start:
			break
		c2 = prev[c2]
	route = chain


func _cell(p: Vector2, ts: float) -> Vector2i:
	return Vector2i(floori(p.x / ts), floori(p.y / ts))


func _physics_process(_delta: float) -> void:
	var mv := SP.component(_entity, &"TopDownMovement") as TopDownMovementComponent
	if mv == null:
		return
	if not GameState.is_playing() or route.is_empty():
		mv.move_vector = Vector2.ZERO
		return
	while _next < route.size() and _entity.global_position.distance_to(route[_next]) < 6.0:
		_next += 1
	if _next >= route.size():
		mv.move_vector = Vector2.ZERO
		return
	mv.move_vector = (route[_next] - _entity.global_position).normalized()
