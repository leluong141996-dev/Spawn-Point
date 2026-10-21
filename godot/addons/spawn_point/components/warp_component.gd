class_name WarpComponent
extends Node
## A doorway: while the player stands in this area, interact (Space / E) moves them to [member to] (a house's
## inside, and back out). The screen dips to black for a moment and the camera jumps along.

const SP_NAME := "Warp"
const SP_HOSTS: Array[String] = ["Area2D"]
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["warp", "player_inside"]
const SP_CATEGORY := "core"

## Emitted after the player went through.
signal warped()

## Where the player arrives (world px).
@export var to: Vector2 = Vector2.ZERO
## The hint shown when the player steps in ("Enter", "Go out").
@export var hint: String = "Enter"

var player_inside: Node2D
var _entity: Area2D
var _cooldown := 0.0


func _ready() -> void:
	_entity = get_parent() as Area2D
	_entity.body_entered.connect(_on_enter)
	_entity.body_exited.connect(func(b: Node) -> void:
		if b == player_inside:
			player_inside = null)
	if not InputMap.has_action(&"interact"):
		InputMap.add_action(&"interact", 0.2)
		for code in [KEY_SPACE, KEY_E, KEY_ENTER]:
			var k := InputEventKey.new()
			k.physical_keycode = code
			InputMap.action_add_event(&"interact", k)


func _on_enter(body: Node) -> void:
	var e := SP.entity_of(body)
	if e and e.is_in_group(SP.PLAYER_GROUP) and _cooldown <= 0.0:
		player_inside = body as Node2D
		FX.float_text(_entity.global_position + Vector2(0, -26), "Space: " + hint, Color("#fffaf0"))


func _physics_process(delta: float) -> void:
	_cooldown -= delta
	if player_inside and GameState.is_playing() and Input.is_action_just_pressed(&"interact"):
		warp(player_inside)


## Moves [param body] through the doorway.
func warp(body: Node2D) -> void:
	_cooldown = 0.4
	player_inside = null
	body.global_position = to
	if body is CharacterBody2D:
		(body as CharacterBody2D).velocity = Vector2.ZERO
	var cam := _entity.get_viewport().get_camera_2d()
	if cam:
		cam.global_position = to
		cam.reset_smoothing()
	var layer := CanvasLayer.new()
	layer.layer = 50
	var shade := ColorRect.new()
	shade.color = Color.BLACK
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(shade)
	_entity.get_tree().current_scene.add_child(layer)
	var tw := shade.create_tween()
	tw.tween_property(shade, "color:a", 0.0, 0.35)
	tw.tween_callback(layer.queue_free)
	if Sfx.has_sound("blip"):
		Sfx.play("blip", 0.0, -6.0, 0.7)
	warped.emit()
