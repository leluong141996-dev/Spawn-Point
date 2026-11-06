class_name AmbientFxComponent
extends Node
## A looping world effect on its entity: petals falling under a blossom tree, fireflies round a tree after dusk.
## Plays the game's effect strip (pixel art games have one); without it, does nothing.

const SP_NAME := "AmbientFx"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = []
const SP_CATEGORY := "juice"

## The loop to play: "petals" or "fireflies".
@export var effect: String = "petals"
## Where it plays, from the entity's position (px).
@export var offset: Vector2 = Vector2.ZERO
## Only after dusk, by the farm's clock ([FarmDaysComponent]); always hidden without one.
@export var night_only: bool = false

var _sprite: Sprite2D
var _days: FarmDaysComponent


func _ready() -> void:
	set_process(false)
	_start.call_deferred()  # the entity is still setting up its children


func _start() -> void:
	_sprite = FX.loop(effect, get_parent(), offset)
	if _sprite and night_only:
		_sprite.modulate.a = 0.0
		_sprite.self_modulate = Color(2.4, 2.2, 1.4)  # overbright, so the night tint leaves a warm glow, not grey
	set_process(_sprite != null and night_only)


func _process(_delta: float) -> void:
	if _days == null or not is_instance_valid(_days):
		_days = get_tree().get_first_node_in_group(&"farm_days") as FarmDaysComponent
		if _days == null:
			return
	_sprite.modulate.a = clampf((_days.time_of_day() - 0.78) / 0.1, 0.0, 1.0)
