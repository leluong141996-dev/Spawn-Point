class_name SpawnerComponent
extends Node
## Spawns entities at its position on a timer (enemy waves, portals, hazards).

const SP_NAME := "Spawner"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "core"
const SP_ENTITY_PARAMS: Array[String] = ["entity"]

## Emitted after each spawn with the new node.
signal spawned(node: Node)

## Entity type to spawn.
@export var entity: String = ""
## Seconds between spawns.
@export_range(0.05, 600.0, 0.05) var interval: float = 3.0
## Seconds before the first spawn.
@export_range(0.0, 600.0, 0.05) var start_delay: float = 1.0
## Do not spawn while this many spawned entities are alive.
@export_range(1, 500) var max_alive: int = 5
## Total spawns before stopping (0 = unlimited).
@export_range(0, 10000) var total: int = 0
## Random offset radius around the spawner (px).
@export_range(0.0, 2000.0, 1.0) var radius: float = 0.0

var _timer := 0.0
var _count := 0
var _alive: Array[Node] = []


func _ready() -> void:
	_timer = start_delay


func _physics_process(delta: float) -> void:
	if not GameState.is_playing() or (total > 0 and _count >= total):
		return
	_timer -= delta
	if _timer > 0.0:
		return
	_timer = interval
	_prune()
	if _alive.size() >= max_alive:
		return
	spawn_now()


func _prune() -> void:
	# Untyped on purpose: a freed entity can't be passed to a `Node`-typed parameter.
	_alive.assign(_alive.filter(func(n) -> bool: return is_instance_valid(n) and not (n as Node).is_queued_for_deletion()))


## Spawns one entity immediately. Returns it (or null).
func spawn_now() -> Node:
	var origin := (get_parent() as Node2D).global_position
	var offset := Vector2.from_angle(randf() * TAU) * randf() * radius
	var n := World.spawn(entity, origin + offset)
	if n:
		_count += 1
		_alive.append(n)
		spawned.emit(n)
	return n
