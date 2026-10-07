class_name TriggerZoneComponent
extends Node
## An invisible-or-visible zone that fires [signal triggered] when an entity of [member group]
## enters (exit doors, checkpoints, kill zones, tutorial hints).

const SP_NAME := "TriggerZone"
const SP_HOSTS: Array[String] = ["Area2D"]
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "core"

## Emitted when a matching body enters.
signal triggered(body: Node)

## Only bodies in this group trigger the zone ("player", an entity name, or "" for any).
@export var group: String = "player"
## Trigger only the first time.
@export var once := true

var _fired := false


func _ready() -> void:
	(get_parent() as Area2D).body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
	if once and _fired:
		return
	if group != "" and not body.is_in_group(StringName(group)):
		return
	_fired = true
	triggered.emit(body)
