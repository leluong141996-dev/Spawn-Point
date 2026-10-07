class_name PlayerInputComponent
extends Node
## Keyboard/mouse controller for the player. Writes intent into the movement component and
## pulls weapon triggers. Registers its own input actions, so no project setup is needed.
##
## Default keys: move = WASD / arrows, jump = Space / Z / W / Up, dash = Shift / C / K,
## shoot = X / J / left mouse.

const SP_NAME := "PlayerInput"
const SP_HOSTS: Array[String] = ["CharacterBody2D"]
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["ensure_actions"]
const SP_CATEGORY := "controller"

const ACTIONS := {
	&"move_left": [KEY_A, KEY_LEFT],
	&"move_right": [KEY_D, KEY_RIGHT],
	&"move_up": [KEY_W, KEY_UP],
	&"move_down": [KEY_S, KEY_DOWN],
	&"jump": [KEY_SPACE, KEY_Z, KEY_W, KEY_UP],
	&"dash": [KEY_SHIFT, KEY_C, KEY_K],
	&"shoot": [KEY_X, KEY_J, MOUSE_BUTTON_LEFT],
}

var _entity: Node


static func ensure_actions() -> void:
	for action: StringName in ACTIONS:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action, 0.2)
		for code: int in ACTIONS[action]:
			var ev: InputEvent
			if action == &"shoot" and code == MOUSE_BUTTON_LEFT:
				var mb := InputEventMouseButton.new()
				mb.button_index = MOUSE_BUTTON_LEFT
				ev = mb
			else:
				var k := InputEventKey.new()
				k.physical_keycode = code
				ev = k
			InputMap.action_add_event(action, ev)


func _ready() -> void:
	ensure_actions()
	_entity = get_parent()
	# Run before movement and weapons in the same physics frame.
	process_physics_priority = -10


func _physics_process(_delta: float) -> void:
	if not GameState.is_playing():
		_clear_intent()
		return
	var mv := SP.movement(_entity)
	if mv:
		mv.move_vector = Input.get_vector(&"move_left", &"move_right", &"move_up", &"move_down")
		if Input.is_action_just_pressed(&"dash"):
			mv.request_dash()
		if mv is PlatformerMovementComponent:
			mv.jump_held = Input.is_action_pressed(&"jump")
			if Input.is_action_just_pressed(&"jump"):
				mv.request_jump()
	var weapon := SP.component(_entity, &"Weapon") as WeaponComponent
	if weapon:
		weapon.trigger_held = Input.is_action_pressed(&"shoot")


func _clear_intent() -> void:
	var mv := SP.movement(_entity)
	if mv:
		mv.move_vector = Vector2.ZERO
	var weapon := SP.component(_entity, &"Weapon") as WeaponComponent
	if weapon:
		weapon.trigger_held = false
