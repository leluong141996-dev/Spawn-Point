extends Node
## Autoload "Cockpit": lets the Spawn Point web cockpit select entities in the running game.
## Right-click an entity: it flashes, and on the web its type and node name are posted to the
## parent page ({spawnpoint: "select", entity, node}). Harmless when not embedded.

signal selected(entity: Node)

## How far (px) a click may land from an entity and still select it — sprites are small.
const PICK_RADIUS := 28.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS


func _unhandled_input(event: InputEvent) -> void:
	var mb := event as InputEventMouseButton
	if mb == null or not mb.pressed or mb.button_index != MOUSE_BUTTON_RIGHT:
		return
	if World.level == null or not is_instance_valid(World.level):
		return
	var e := entity_at(World.level.get_global_mouse_position())
	if e:
		select(e)
		get_viewport().set_input_as_handled()


## The entity at (or nearest to, within PICK_RADIUS) a world position, or null.
func entity_at(world_pos: Vector2) -> Node2D:
	var q := PhysicsPointQueryParameters2D.new()
	q.position = world_pos
	q.collide_with_areas = true
	q.collide_with_bodies = true
	for hit in World.level.get_world_2d().direct_space_state.intersect_point(q, 16):
		var e := SP.entity_of(hit.collider) as Node2D
		if e and e.is_in_group(SP.ENTITY_GROUP):
			return e
	var best: Node2D = null
	var best_d := PICK_RADIUS
	for n in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
		var e := n as Node2D
		if e == null or not e.visible:
			continue
		var d := e.global_position.distance_to(world_pos)
		if d < best_d:
			best_d = d
			best = e
	return best


## Highlights [param e] and reports it to the cockpit page.
func select(e: Node2D) -> void:
	selected.emit(e)
	var juice := SP.component(e, &"Juice")
	if juice and juice.has_method(&"flash_white"):
		juice.flash_white(0.35)
	FX.burst(e.global_position, Color.WHITE, 10, 120.0, 0.3, 2.5, 0.0)
	var core := SP.core(e)
	var msg := JSON.stringify({"spawnpoint": "select", "entity": core.entity_type if core else String(e.name),
			"node": String(e.name)})
	if OS.has_feature("web"):
		JavaScriptBridge.eval("window.parent && window.parent.postMessage(%s, '*')" % msg)
