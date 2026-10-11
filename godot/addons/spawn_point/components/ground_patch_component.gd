class_name GroundPatchComponent
extends Node
## Paints a patch of ground under everything else: roads, paths, rugs, puddles. Purely visual.

const SP_NAME := "GroundPatch"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "juice"

## Patch colour.
@export var color: Color = Color("#c2a476")
## Patch size in px.
@export_range(4.0, 512.0, 1.0) var size: float = 32.0
## Corner rounding, 0..1 of half the size (1 = a circle).
@export_range(0.0, 1.0, 0.05) var round_corners: float = 0.3

var _view: Node2D


func _ready() -> void:
	_view = Node2D.new()
	_view.z_index = -5
	_view.draw.connect(_on_draw)
	get_parent().add_child.call_deferred(_view)


func _on_draw() -> void:
	var h := size / 2.0 + 1.0  # a hair larger so neighbouring patches join without seams
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(int(h * round_corners))
	_view.draw_style_box(sb, Rect2(-h, -h, h * 2.0, h * 2.0))
	var rng := RandomNumberGenerator.new()
	rng.seed = int(get_parent().global_position.x * 7 + get_parent().global_position.y)
	for i in 3:  # a few specks so it does not look flat
		_view.draw_circle(Vector2(rng.randf_range(-h * 0.7, h * 0.7), rng.randf_range(-h * 0.7, h * 0.7)),
				rng.randf_range(1.0, 2.2), color.darkened(0.18))
