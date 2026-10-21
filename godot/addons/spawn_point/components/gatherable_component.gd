class_name GatherableComponent
extends Node
## A tree to chop or a rock to break: each interact from a [FarmerComponent] is a hit (the thing shakes);
## after [member hits] it gives [member item] and is replaced by [member leaves] (a stump), or just goes.

const SP_NAME := "Gatherable"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["hit", "hits_left", "remove_quietly"]
const SP_CATEGORY := "core"

## Emitted when it breaks, with the item it gave.
signal gathered(item: String)

## Hits needed.
@export_range(1, 20) var hits: int = 3
## What it gives ("Wood", "Stone"); the farmer's goods list prices it.
@export var item: String = "Wood"
## How many of it.
@export_range(1, 20) var amount: int = 2
## Entity left behind (e.g. "Stump"); empty for none.
@export var leaves: String = ""
## Colour of the chips that fly off.
@export var chip_color: Color = Color("#6aa84f")

var hits_left := 0
var _entity: Node2D


func _ready() -> void:
	_entity = get_parent() as Node2D
	_entity.add_to_group(&"gatherable")
	hits_left = hits


## Gone without a sound or an item (a saved farm where it was already chopped): leaves its stump.
func remove_quietly() -> void:
	hits_left = 0
	if leaves != "" and ResourceLoader.exists("res://entities/%s.tscn" % leaves):
		var stump := (load("res://entities/%s.tscn" % leaves) as PackedScene).instantiate() as Node2D
		stump.position = _entity.position
		_entity.get_parent().add_child.call_deferred(stump)
	_entity.queue_free()


## One hit. Returns the item when this hit breaks it, "" otherwise.
func hit() -> String:
	if hits_left <= 0:
		return ""
	hits_left -= 1
	var pos := _entity.global_position
	FX.burst(pos + Vector2(0, -14), chip_color, 6, 110.0, 0.35, 2.5, 260.0)
	var visual := _entity.get_node_or_null(^"Visual") as Node2D
	if visual:
		var tw := _entity.create_tween()
		tw.tween_property(visual, "position:x", 3.0, 0.04)
		tw.tween_property(visual, "position:x", -3.0, 0.06)
		tw.tween_property(visual, "position:x", 0.0, 0.04)
	if Sfx.has_sound("hit"):
		Sfx.play("hit", 0.1, -6.0, 0.9)
	if hits_left > 0:
		return ""
	gathered.emit(item)
	if leaves != "" and ResourceLoader.exists("res://entities/%s.tscn" % leaves):
		var stump := (load("res://entities/%s.tscn" % leaves) as PackedScene).instantiate() as Node2D
		stump.position = _entity.position
		_entity.get_parent().add_child.call_deferred(stump)
	FX.burst(pos + Vector2(0, -10), chip_color, 14, 160.0, 0.5, 3.0, 300.0)
	_entity.queue_free()
	return item
