class_name SPLevel
extends Node2D
## Root of a generated level. Configures [World] and [GameState] before entities load.

## "platformer" or "topdown".
@export var genre := "platformer"
## Lives at the start of a run.
@export var lives := 3
## Tile size in pixels.
@export var tile_size := 32
## Level bounds in pixels.
@export var bounds := Rect2(0, 0, 960, 540)
## "pixel" or "cartoon": pixel levels get pixel-snapped shake and blocky particles.
@export var art_style := "pixel"


func _enter_tree() -> void:
	var kill_y := bounds.end.y + tile_size * 4.0 if genre == "platformer" else INF
	FX.pixel_art = art_style == "pixel"
	World.begin_level(self, kill_y)
	GameState.begin_level(lives)
	Engine.time_scale = 1.0
