class_name HealthBarComponent
extends Node
## A thin bar above the entity showing how much health is left. Hidden at full health unless [member always] is on
## (bosses). Draws in the world, so it follows the entity and never flips with its picture.

const SP_NAME := "HealthBar"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = ["Health"]
const SP_CATEGORY := "juice"

## Show the bar even at full health.
@export var always := false
## Bar width in px.
@export_range(8.0, 400.0, 1.0) var width: float = 48.0
## Gap between the entity's top edge and the bar (px).
@export_range(0.0, 100.0, 1.0) var gap: float = 8.0
## Fill colour.
@export var color: Color = Color("#ff004d")

var _entity: Node2D
var _health: HealthComponent
var _view: Node2D


func _ready() -> void:
	_entity = SP.entity_of(get_parent()) as Node2D
	_health = SP.component(_entity, &"Health") as HealthComponent
	_view = Node2D.new()
	_view.z_index = 20
	_view.draw.connect(_on_draw)
	_entity.add_child.call_deferred(_view)
	_health.damaged.connect(func(_a: int) -> void: _view.queue_redraw())


func _on_draw() -> void:
	if _health == null or (not always and _health.current >= _health.max_health):
		return
	var y := -SP.half_size(_entity).y - gap
	var ratio := clampf(float(_health.current) / float(maxi(_health.max_health, 1)), 0.0, 1.0)
	_view.draw_rect(Rect2(-width / 2.0 - 1, y - 1, width + 2, 6), Color(0, 0, 0, 0.7))
	_view.draw_rect(Rect2(-width / 2.0, y, width * ratio, 4), color)
