class_name CollectibleComponent
extends Node
## A pickup (coin, gem, key...). Touching it adds [member score], emits [signal collected] and
## removes it. The visual bobs gently so pickups read as "take me".

const SP_NAME := "Collectible"
const SP_HOSTS: Array[String] = ["Area2D"]
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "core"

## Emitted when collected; [param by] is the collecting entity.
signal collected(by: Node)

## Free-form kind, usable in rules ("coin", "key", "heart").
@export var kind: String = "coin"
## Score added on pickup (0 = none).
@export_range(0, 100000) var score: int = 1
## Health restored to the collector on pickup (0 = none).
@export_range(0, 999) var heal: int = 0
## Bobbing height in px (0 = static).
@export_range(0.0, 32.0, 0.5) var bob_height: float = 3.0

var _entity: Area2D
var _t := 0.0
var _taken := false
var _base_y := 0.0


func _ready() -> void:
	_entity = get_parent() as Area2D
	_entity.body_entered.connect(_on_body_entered)
	_t = randf() * TAU
	var visual := _entity.get_node_or_null(^"Visual") as Node2D
	if visual:
		_base_y = visual.position.y


func _process(delta: float) -> void:
	if bob_height <= 0.0:
		return
	_t += delta * 3.0
	var visual := _entity.get_node_or_null(^"Visual") as Node2D
	if visual:
		visual.position.y = _base_y + sin(_t) * bob_height


func _on_body_entered(body: Node) -> void:
	if _taken or not body.is_in_group(SP.PLAYER_GROUP):
		return
	_taken = true
	# Free first so rules reacting to these signals already see one pickup fewer in World.count().
	_entity.queue_free()
	if heal > 0:
		var h := SP.component(body, &"Health") as HealthComponent
		if h:
			h.heal(heal)
	collected.emit(body)
	GameState.add_score(score)
