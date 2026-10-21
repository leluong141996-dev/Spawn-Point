class_name FishingSpotComponent
extends Node
## A place on the shore to fish from. A [FarmerComponent]'s interact casts the line (a bobber lands on the
## water in [member water_dir]); after a wait the fish bites (a "!" and a splash) and interact again reels it in.
## Too soon or too late and it gets away.

const SP_NAME := "FishingSpot"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["use", "state", "bite_left"]
const SP_CATEGORY := "core"

enum State { IDLE, WAITING, BITE }

## Emitted with the catch.
signal caught(item: String)

## What a catch is called (the farmer's goods list prices it).
@export var catch_name: String = "Fish"
## Direction of the water from the spot (the bobber lands this way).
@export var water_dir: Vector2 = Vector2.DOWN
## Shortest wait for a bite (seconds).
@export_range(0.2, 30.0, 0.1) var min_wait: float = 1.5
## Longest wait for a bite (seconds).
@export_range(0.2, 30.0, 0.1) var max_wait: float = 4.0
## How long the fish stays on the hook (seconds).
@export_range(0.1, 5.0, 0.05) var bite_time: float = 0.9

var state := State.IDLE
var bite_left := 0.0
var _wait := 0.0
var _entity: Node2D
var _view: Node2D
var _t := 0.0
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	_entity = get_parent() as Node2D
	_entity.add_to_group(&"fishing_spot")
	_rng.seed = int(_entity.global_position.x * 3.0 + _entity.global_position.y)
	_view = Node2D.new()
	_view.name = "FishingView"
	_view.z_index = 4
	_view.draw.connect(_draw)
	_entity.add_child.call_deferred(_view)


## One press of interact: cast, or reel in. Returns the catch's name on a catch, "cast" on a cast, "" otherwise.
func use() -> String:
	match state:
		State.IDLE:
			state = State.WAITING
			_wait = _rng.randf_range(min_wait, max_wait)
			return "cast"
		State.BITE:
			state = State.IDLE
			FX.burst(bobber_position(), Color("#e6fbff"), 10, 120.0, 0.4, 2.5, 300.0)
			caught.emit(catch_name)
			return catch_name
		_:
			state = State.IDLE
			FX.float_text(bobber_position() + Vector2(0, -16), "Too soon!", Color("#fffaf0"))
			return ""


## Where the bobber floats.
func bobber_position() -> Vector2:
	return _entity.global_position + water_dir.normalized() * 44.0


func _physics_process(delta: float) -> void:
	_t += delta
	if state == State.WAITING:
		_wait -= delta
		if _wait <= 0.0:
			state = State.BITE
			bite_left = bite_time
			if Sfx.has_sound("blip"):
				Sfx.play("blip", 0.0, -2.0, 1.8)
	elif state == State.BITE:
		bite_left -= delta
		if bite_left <= 0.0:
			state = State.IDLE
			FX.float_text(bobber_position() + Vector2(0, -16), "It got away", Color("#fffaf0"))
	if _view:
		_view.queue_redraw()


func _draw() -> void:
	if state == State.IDLE:
		return
	var b := bobber_position() - _entity.global_position
	var dip := 3.0 if state == State.BITE else sin(_t * 4.0) * 1.5
	_view.draw_line(Vector2(0, -20), b + Vector2(0, dip - 3), Color(1, 1, 1, 0.7), 1.0)
	_view.draw_circle(b + Vector2(0, dip), 3.0, Color("#e83a3a"))
	_view.draw_circle(b + Vector2(0, dip - 2), 2.0, Color("#fffaf0"))
	if state == State.BITE:
		_view.draw_arc(b + Vector2(0, 3), 6.0 + fmod(_t * 20.0, 6.0), 0.0, TAU, 16, Color(1, 1, 1, 0.6), 1.0)
		_view.draw_string(ThemeDB.fallback_font, b + Vector2(-3, -12), "!", HORIZONTAL_ALIGNMENT_LEFT, -1, 18,
				Color("#ffec27"))
