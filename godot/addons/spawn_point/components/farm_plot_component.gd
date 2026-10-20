class_name FarmPlotComponent
extends Node
## A patch of soil for farming games. A [FarmerComponent] plants a crop here, waters it and harvests
## it when ripe. The crop only grows while the soil is wet, and the soil dries after
## [member water_seconds]. Pests ([CropPestComponent]) can eat what grows here.

const SP_NAME := "FarmPlot"
const SP_HOSTS: Array[String] = ["Area2D"]
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["plant", "water", "harvest", "destroy_crop", "state", "is_empty", "is_ripe",
	"has_crop", "growth"]
const SP_CATEGORY := "core"

enum State { EMPTY, GROWING, RIPE }

## Emitted when something is planted; [param crop] is its index in the farmer's crop list.
signal planted(crop: int)
## Emitted when the crop is ripe.
signal ripened(crop: int)
## Emitted when the crop is harvested.
signal harvested(crop: int)
## Emitted when a pest eats the crop.
signal eaten(crop: int)

## How long the soil stays wet after watering (seconds).
@export_range(1.0, 120.0, 0.5) var water_seconds: float = 6.0
## Size of the soil patch in px.
@export_range(16.0, 128.0, 1.0) var size: float = 30.0
## Picture of dry tilled soil (res:// path); empty draws plain soil.
@export var soil_texture: String = ""
## Picture of watered soil (res:// path).
@export var wet_texture: String = ""

var state := State.EMPTY
var crop := -1
var crop_color := Color("#ff9f1c")
var grow_seconds := 8.0
var growth := 0.0  # seconds of wet growth so far
var wet_left := 0.0

var crop_texture: Texture2D  # five growth stages side by side (seeds, sprout, young, grown, ripe)
var _entity: Area2D
var _view: Node2D
var _sway := 0.0
var _soil: Texture2D
var _wet: Texture2D


func _ready() -> void:
	_entity = get_parent() as Area2D
	_entity.add_to_group(&"farm_plot")
	_view = Node2D.new()
	_view.name = "PlotView"
	_view.z_index = -1
	_view.draw.connect(_on_draw)
	_entity.add_child.call_deferred(_view)
	if soil_texture != "" and ResourceLoader.exists(soil_texture):
		_soil = load(soil_texture) as Texture2D
	if wet_texture != "" and ResourceLoader.exists(wet_texture):
		_wet = load(wet_texture) as Texture2D


func is_empty() -> bool:
	return state == State.EMPTY


func is_ripe() -> bool:
	return state == State.RIPE


func has_crop() -> bool:
	return state != State.EMPTY


## Plants crop [param index] that ripens after [param seconds] of wet growth. [param texture] holds the crop's
## growth stages (optional; without it the crop is drawn as shapes in [param color]).
func plant(index: int, seconds: float, color: Color, texture: Texture2D = null) -> bool:
	if state != State.EMPTY:
		return false
	state = State.GROWING
	crop = index
	crop_texture = texture
	grow_seconds = maxf(seconds, 0.5)
	crop_color = color
	growth = 0.0
	wet_left = 0.0
	planted.emit(index)
	return true


func water() -> bool:
	if state != State.GROWING:
		return false
	wet_left = water_seconds
	return true


## Picks the ripe crop. Returns its index, or -1 when nothing is ripe.
func harvest() -> int:
	if state != State.RIPE:
		return -1
	var c := crop
	_clear()
	harvested.emit(c)
	return c


func destroy_crop() -> void:
	if state == State.EMPTY:
		return
	var c := crop
	FX.burst(_entity.global_position, crop_color.darkened(0.3), 8, 120.0, 0.35, 3.0, 200.0)
	_clear()
	eaten.emit(c)


func _clear() -> void:
	state = State.EMPTY
	crop = -1
	growth = 0.0
	wet_left = 0.0


func _physics_process(delta: float) -> void:
	_sway += delta
	if state == State.GROWING and GameState.is_playing():
		if wet_left > 0.0:
			wet_left -= delta
			growth += delta
			if growth >= grow_seconds:
				state = State.RIPE
				ripened.emit(crop)
	if _view:
		_view.queue_redraw()


## Growth as 0..1 (1 when ripe).
func progress() -> float:
	return 1.0 if state == State.RIPE else clampf(growth / grow_seconds, 0.0, 1.0)


## Which picture of the crop to show: 0 seeds .. 4 ripe.
func stage() -> int:
	if state == State.RIPE:
		return 4
	var p := progress()
	return 0 if p < 0.12 else 1 if p < 0.4 else 2 if p < 0.72 else 3


func _on_draw() -> void:
	if _soil:
		_draw_textured()
		return
	var h := size / 2.0
	var soil := Color("#6b4a2f") if wet_left <= 0.0 else Color("#3f2a1a")
	_view.draw_rect(Rect2(-h, -h, size, size), soil)
	_view.draw_rect(Rect2(-h, -h, size, size), Color("#2b1d12"), false, 2.0)
	for i in 3:  # furrows
		var y := -h + size * (i + 1) / 4.0
		_view.draw_line(Vector2(-h + 3, y), Vector2(h - 3, y), soil.darkened(0.25), 1.0)
	if state == State.EMPTY:
		return
	var p := progress()
	var sway := sin(_sway * 2.0 + _entity.global_position.x) * 1.5
	var stem := Color("#5fb83d")
	if p < 0.34:  # sprout
		_view.draw_rect(Rect2(-1, -3, 2, 5), stem)
		_view.draw_rect(Rect2(-4 + sway * 0.3, -5, 3, 2), stem.lightened(0.2))
		_view.draw_rect(Rect2(1 + sway * 0.3, -5, 3, 2), stem.lightened(0.2))
	elif state != State.RIPE:  # young plant
		_view.draw_rect(Rect2(-1, -8, 2, 11), stem)
		_view.draw_rect(Rect2(-7 + sway, -9, 6, 4), stem.lightened(0.15))
		_view.draw_rect(Rect2(1 + sway, -11, 6, 4), stem.lightened(0.15))
	else:  # ripe: leaves and the fruit, with a gentle glow
		_view.draw_rect(Rect2(-1, -9, 2, 8), stem)
		_view.draw_rect(Rect2(-8 + sway, -12, 7, 4), stem)
		_view.draw_rect(Rect2(1 + sway, -13, 7, 4), stem)
		var pulse := 0.5 + 0.5 * sin(_sway * 4.0)
		_view.draw_circle(Vector2(0, 2), 9.0, Color(1, 1, 0.6, 0.12 + 0.1 * pulse))
		_view.draw_circle(Vector2(0, 2), 6.0, crop_color)
		_view.draw_circle(Vector2(-2, 0), 2.0, crop_color.lightened(0.4))
	if wet_left > 0.0:  # water drops
		_view.draw_circle(Vector2(h - 5, -h + 5), 2.5, Color("#29adff"))


func _draw_textured() -> void:
	var t := 32.0  # one 16 px art tile at 2x
	var soil := _wet if wet_left > 0.0 and _wet else _soil
	_view.draw_texture_rect(soil, Rect2(-t / 2, -t / 2, t, t), false)
	if state == State.EMPTY:
		return
	if crop_texture == null:
		_view.draw_circle(Vector2(0, -2), 4.0 + 6.0 * progress(), crop_color)
		return
	var st := stage()
	var lift := 0.0
	if st == 4:  # ripe: a little hop and a glint
		lift = -absf(sin(_sway * 3.0)) * 2.0
	_view.draw_texture_rect_region(crop_texture, Rect2(-t / 2, -t / 2 - 6 + lift, t, t), Rect2(st * 16, 0, 16, 16))
	if st == 4 and fmod(_sway, 1.6) < 0.25:
		_view.draw_rect(Rect2(8, -14 + lift, 2, 2), Color("#fffaf0"))
