class_name GateComponent
extends Node
## A solid barrier that can be opened and closed by rules (doors, bridges, locked exits).

const SP_NAME := "Gate"
const SP_HOSTS: Array[String] = ["StaticBody2D"]
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "core"

## Emitted when the gate opens.
signal opened
## Emitted when the gate closes.
signal closed

## Start open.
@export var starts_open := false

var is_open := false
var _entity: StaticBody2D


func _ready() -> void:
	_entity = get_parent() as StaticBody2D
	_set_open(starts_open, false)


## Opens the gate (no collision, faded visual).
func open() -> void:
	if not is_open:
		_set_open(true, true)
		opened.emit()


## Closes the gate.
func close() -> void:
	if is_open:
		_set_open(false, true)
		closed.emit()


## Opens if closed, closes if open.
func toggle() -> void:
	if is_open:
		close()
	else:
		open()


func _set_open(value: bool, animate: bool) -> void:
	is_open = value
	for cs in _entity.find_children("*", "CollisionShape2D", false, false):
		(cs as CollisionShape2D).set_deferred(&"disabled", value)
	var visual := _entity.get_node_or_null(^"Visual") as Node2D
	if visual == null:
		return
	var alpha := 0.2 if value else 1.0
	if animate:
		var t := visual.create_tween().set_parallel(true)
		t.tween_property(visual, ^"modulate:a", alpha, 0.25)
		visual.scale = Vector2(1.15, 0.85) if value else Vector2(0.9, 1.1)
		t.tween_property(visual, ^"scale", Vector2.ONE, 0.3).set_trans(Tween.TRANS_ELASTIC).set_ease(Tween.EASE_OUT)
	else:
		visual.modulate.a = alpha
