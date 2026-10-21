class_name FarmAnimalComponent
extends Node
## A farm animal: wanders around where it was placed, and every [member product_seconds] has something to give
## (an egg, milk) that a [FarmerComponent] collects with interact. A speech bubble shows when it is ready.
## With [member needs_food] it first has to be fed (a hay bubble; interact feeds it), and again after each
## product. A young animal with [member grows_into] turns into that entity after [member grow_seconds].

const SP_NAME := "FarmAnimal"
const SP_HOSTS: Array[String] = ["CharacterBody2D"]
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["collect", "feed", "is_ready", "is_hungry", "home", "snapshot", "restore",
	"overnight"]
const SP_CATEGORY := "core"

## Emitted when the farmer takes the product.
signal collected(item: String)
## Emitted when the farmer feeds it.
signal fed()
## Emitted when it has grown up (just before it is replaced).
signal grew_up()

## What it gives ("Egg", "Milk"); the farmer's goods list prices it.
@export var product: String = "Egg"
## Seconds between products.
@export_range(1.0, 600.0, 0.5) var product_seconds: float = 20.0
## Picture shown in the bubble (res:// path); empty draws a white dot.
@export var icon: String = ""
## It must be fed before each product.
@export var needs_food: bool = false
## Picture shown in the bubble while it is hungry (res:// path).
@export var food_icon: String = ""
## Entity it grows into ("Chicken"); empty: it stays as it is.
@export var grows_into: String = ""
## Seconds until it grows up.
@export_range(1.0, 3600.0, 1.0) var grow_seconds: float = 60.0
## How far from home it strolls (px).
@export_range(0.0, 600.0, 1.0) var wander_radius: float = 70.0
## Walking speed (px/s).
@export_range(0.0, 300.0, 1.0) var speed: float = 28.0

var home := Vector2.ZERO
var _body: CharacterBody2D
var _target := Vector2.ZERO
var _rest := 0.0
var _until_ready := 0.0
var _has_product := false
var _bubble: Node2D
var _tex: Texture2D
var _food_tex: Texture2D
var _hungry := false
var _age := 0.0
var _rng := RandomNumberGenerator.new()
var _t := 0.0


func _ready() -> void:
	_body = get_parent() as CharacterBody2D
	_body.add_to_group(&"farm_animal")
	home = _body.global_position
	_target = home
	_rng.seed = int(home.x * 13.0 + home.y * 7.0)
	_until_ready = product_seconds * _rng.randf_range(0.3, 0.8)
	_rest = _rng.randf_range(0.5, 2.0)
	if icon != "" and ResourceLoader.exists(icon):
		_tex = load(icon) as Texture2D
	if food_icon != "" and ResourceLoader.exists(food_icon):
		_food_tex = load(food_icon) as Texture2D
	_hungry = needs_food and product != ""
	_bubble = Node2D.new()
	_bubble.name = "Bubble"
	_bubble.z_index = 5
	_bubble.visible = false
	_bubble.draw.connect(_draw_bubble)
	_body.add_child.call_deferred(_bubble)


func is_ready() -> bool:
	return _has_product


func is_hungry() -> bool:
	return _hungry


## Feeds it. Returns false when it was not hungry.
func feed() -> bool:
	if not _hungry:
		return false
	_hungry = false
	_until_ready = product_seconds
	FX.float_text(_body.global_position + Vector2(0, -28), "<3", Color("#ff77a8"))
	fed.emit()
	return true


## Takes the product. Returns its name, or "" when there is nothing yet (the animal gets a pat instead).
func collect() -> String:
	if not _has_product:
		FX.float_text(_body.global_position + Vector2(0, -28), "<3", Color("#ff77a8"))
		return ""
	_has_product = false
	_until_ready = product_seconds
	_hungry = needs_food
	_bubble.visible = _hungry
	collected.emit(product)
	return product


func _physics_process(delta: float) -> void:
	_t += delta
	if not GameState.is_playing():
		_body.velocity = Vector2.ZERO
		return
	if grows_into != "":
		_age += delta
		if _age >= grow_seconds:
			_grow_up()
			return
	if _hungry:
		_bubble.visible = true
	elif not _has_product and product != "":
		_until_ready -= delta
		if _until_ready <= 0.0:
			_has_product = true
			_bubble.visible = true
	if _bubble.visible:
		_bubble.position = Vector2(0, -34 + sin(_t * 3.0) * 2.0)
		_bubble.queue_redraw()
	# stroll: rest a moment, pick a spot near home, walk there
	var to := _target - _body.global_position
	if _rest > 0.0:
		_rest -= delta
		_body.velocity = Vector2.ZERO
		if _rest <= 0.0:
			var a := _rng.randf() * TAU
			_target = home + Vector2(cos(a), sin(a)) * _rng.randf_range(0.0, wander_radius)
	elif to.length() < 4.0:
		_rest = _rng.randf_range(1.0, 3.5)
		_body.velocity = Vector2.ZERO
	else:
		_body.velocity = to.normalized() * speed
		SP.face(_body, _body.velocity, false)
	var before := _body.global_position
	_body.move_and_slide()
	if _rest <= 0.0 and _body.global_position.distance_to(before) < speed * delta * 0.2:
		_rest = _rng.randf_range(0.5, 1.5)  # bumped into a fence: think again


## The animal's state as plain data (see [FarmSaveComponent]).
func snapshot() -> Dictionary:
	return {"hungry": _hungry, "ready": _has_product, "until": _until_ready, "age": _age, "hx": home.x, "hy": home.y}


func restore(d: Dictionary) -> void:
	_hungry = bool(d.get("hungry", _hungry))
	_has_product = bool(d.get("ready", false))
	_until_ready = float(d.get("until", product_seconds))
	_age = float(d.get("age", 0.0))
	home = Vector2(float(d.get("hx", home.x)), float(d.get("hy", home.y)))
	_target = home
	_bubble.visible = _hungry or _has_product


## A night passes: a fed animal has its product ready by morning, and everyone is hungry again.
func overnight() -> void:
	if product != "" and not _hungry and not _has_product:
		_has_product = true
		_bubble.visible = true
	elif needs_food and not _has_product:
		_hungry = true
		_bubble.visible = true


func _grow_up() -> void:
	var path := "res://entities/%s.tscn" % grows_into
	if not ResourceLoader.exists(path):
		grows_into = ""
		return
	var grown := (load(path) as PackedScene).instantiate() as Node2D
	grown.position = _body.position
	_body.get_parent().add_child.call_deferred(grown)
	FX.burst(_body.global_position + Vector2(0, -8), Color("#fff1a8"), 10, 90.0, 0.4, 2.5, 200.0)
	grew_up.emit()
	_body.queue_free()


func _draw_bubble() -> void:
	var r := Rect2(-10, -10, 20, 18)
	_bubble.draw_rect(r.grow(1), Color("#2a1e2e"))
	_bubble.draw_rect(r, Color("#fffaf0"))
	_bubble.draw_colored_polygon(PackedVector2Array([Vector2(-3, 8), Vector2(3, 8), Vector2(0, 12)]), Color("#fffaf0"))
	var pic := _food_tex if _hungry else _tex
	if pic:
		_bubble.draw_texture_rect(pic, Rect2(-8, -9, 16, 16), false)
	else:
		_bubble.draw_circle(Vector2(0, -1), 5.0, Color("#f8f0e0"))
