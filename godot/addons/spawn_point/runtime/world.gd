extends Node
## Autoload "World": entity registry, spawning and rule signal bindings.

const ENTITY_SCENE_PATH := "res://entities/%s.tscn"

var level: Node2D
## Entities below this y are killed (platformers). INF disables.
var kill_y := INF

var _bindings: Array[Dictionary] = []
var _scene_cache := {}


## Called by the level root when it enters the tree, before any entity registers.
func begin_level(level_root: Node2D, level_kill_y: float) -> void:
	level = level_root
	kill_y = level_kill_y
	_bindings.clear()


## Called by every [SPEntityCore] when its entity is ready.
func register_entity(entity: Node) -> void:
	for b in _bindings:
		_apply_binding(b, entity)


## Connects [param callable] to [param signal_name] of component [param component_name] on every
## current and future instance of [param entity_type]. The emitting entity is appended as the
## last argument.
func bind_signal(entity_type: StringName, component_name: StringName, signal_name: StringName, callable: Callable) -> void:
	var b := {"type": entity_type, "component": component_name, "signal": signal_name, "callable": callable}
	_bindings.append(b)
	for e in instances(entity_type):
		_apply_binding(b, e)


func _apply_binding(b: Dictionary, entity: Node) -> void:
	if not entity.is_in_group(b.type):
		return
	var src: Object = SP.component(entity, b.component) if b.component != &"" else entity
	if src == null or not src.has_signal(b.signal):
		push_error("Spawn Point: %s has no signal %s.%s" % [b.type, b.component, b.signal])
		return
	var bound: Callable = b.callable.bind(entity)
	if not src.is_connected(b.signal, bound):
		src.connect(b.signal, bound)


## All live instances of an entity type.
func instances(entity_type: StringName) -> Array[Node]:
	var out: Array[Node] = []
	if not is_inside_tree():
		return out
	for n in get_tree().get_nodes_in_group(entity_type):
		if not n.is_queued_for_deletion() and n.is_in_group(SP.ENTITY_GROUP):
			out.append(n)
	return out


func count(entity_type: StringName) -> int:
	return instances(entity_type).size()


func player() -> Node2D:
	var players := get_tree().get_nodes_in_group(SP.PLAYER_GROUP)
	return players[0] as Node2D if players.size() > 0 else null


## Instantiates entity [param entity_type] at [param pos]. [param meta] is applied as node
## metadata before the node enters the tree (e.g. {"sp_team": "enemy"}).
func spawn(entity_type: String, pos: Vector2, meta := {}) -> Node2D:
	var scene: PackedScene = _scene_cache.get(entity_type)
	if scene == null:
		var path := ENTITY_SCENE_PATH % entity_type
		if not ResourceLoader.exists(path):
			push_error("Spawn Point: unknown entity '%s'" % entity_type)
			return null
		scene = load(path)
		_scene_cache[entity_type] = scene
	var node := scene.instantiate() as Node2D
	for k in meta:
		node.set_meta(k, meta[k])
	node.position = pos
	var parent: Node = level.get_node_or_null(^"Entities") if level else null
	if parent == null:
		parent = level if level else get_tree().current_scene
	parent.add_child(node)
	return node


## Spawns at tile coordinates (cell center).
func spawn_at_tile(entity_type: String, tx: int, ty: int) -> Node2D:
	var ts: float = level.get(&"tile_size") if level else 32.0
	return spawn(entity_type, Vector2((tx + 0.5) * ts, (ty + 0.5) * ts))


## Removes an entity from the game (no death effects).
func destroy(entity: Node) -> void:
	if entity and is_instance_valid(entity) and not entity.is_queued_for_deletion():
		if entity.is_in_group(SP.PLAYER_GROUP):
			var h := SP.component(entity, &"Health") as HealthComponent
			if h:
				h.kill()
				return
		entity.queue_free()


func destroy_all(entity_type: StringName) -> void:
	for e in instances(entity_type):
		destroy(e)


## Calls [param method] on component [param component_name] (or the entity root if empty) of
## every instance of [param entity_type].
func call_all(entity_type: StringName, component_name: StringName, method: StringName, args: Array = []) -> void:
	for e in instances(entity_type):
		call_on(e, component_name, method, args)


func call_on(entity: Node, component_name: StringName, method: StringName, args: Array = []) -> Variant:
	if entity == null or not is_instance_valid(entity):
		return null
	var target: Object = SP.component(entity, component_name) if component_name != &"" else entity
	if target == null:
		return null
	return target.callv(method, args)
