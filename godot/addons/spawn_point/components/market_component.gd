class_name MarketComponent
extends Node
## A market stall for farming games: a [FarmerComponent] that walks in sells everything in the basket.

const SP_NAME := "Market"
const SP_HOSTS: Array[String] = ["Area2D"]
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "core"

## Emitted after a sale with the money earned.
signal sold(amount: int)

## Stall width in px (the drawing; the collision comes from the entity's shape).
@export_range(16.0, 256.0, 1.0) var width: float = 64.0
## Awning colour.
@export var color: Color = Color("#ff004d")

var _entity: Area2D
var _view: Node2D


func _ready() -> void:
	_entity = get_parent() as Area2D
	_entity.body_entered.connect(_on_body_entered)
	_view = Node2D.new()
	_view.name = "StallView"
	_view.z_index = -1
	_view.draw.connect(_on_draw)
	_entity.add_child.call_deferred(_view)


func _on_body_entered(body: Node) -> void:
	var farmer := SP.component(body, &"Farmer") as FarmerComponent
	if farmer:
		var amount := farmer.sell()
		if amount > 0:
			sold.emit(amount)


func _on_draw() -> void:
	var w := width
	var h := w * 0.75
	_view.draw_rect(Rect2(-w / 2, -h / 2 + h * 0.35, w, h * 0.65), Color("#8a5a3b"))  # counter
	_view.draw_rect(Rect2(-w / 2, -h / 2 + h * 0.35, w, h * 0.65), Color("#4a2f1c"), false, 2.0)
	var stripes := 6
	for i in stripes:  # striped awning
		var c := color if i % 2 == 0 else Color("#fff1e8")
		_view.draw_rect(Rect2(-w / 2 + i * w / stripes, -h / 2, w / stripes, h * 0.35), c)
	for x in [-w * 0.3, -w * 0.05, w * 0.2]:  # produce on the counter
		_view.draw_circle(Vector2(x, h * 0.05), 5.0, Color("#ff9f1c"))
	_view.draw_string(ThemeDB.fallback_font, Vector2(-w / 2 + 4, h / 2 - 4), "MARKET", HORIZONTAL_ALIGNMENT_LEFT,
			w - 8, 11, Color("#fff1e8"))
