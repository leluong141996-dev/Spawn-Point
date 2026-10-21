class_name GameMenuComponent
extends Node
## A title screen and a pause menu, and the background music. The game waits on the title screen until the
## player presses Space / Enter or taps; with a saved farm ([FarmSaveComponent]) it offers to carry on, and N
## starts a new one. P or Esc pauses (M turns the music on or off, R restarts). Bots, recordings and headless
## runs skip the title screen. Put it on the player.

const SP_NAME := "GameMenu"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["start", "toggle_pause", "showing"]
const SP_CATEGORY := "core"

## Emitted when the player leaves the title screen.
signal started()

## Big title on the title screen.
@export var title: String = "Spawn Point"
## A line under it (what to do).
@export var subtitle: String = ""
## Play res://sfx/music.wav on repeat.
@export var music: bool = true

var showing := ""  # "title", "pause" or ""
var _layer: CanvasLayer
var _label: Label
var _small: Label


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_open_title.call_deferred()


func _skip_menus() -> bool:
	return get_tree().root.has_meta(&"sp_autopilot") or DisplayServer.get_name() == "headless"


func _open_title() -> void:
	for i in 4:  # a saved farm loads first, so the title can say which day it is
		await get_tree().physics_frame
	if _skip_menus():
		start()
		return
	_build()
	var lines := "Press Space or tap to start"
	var save := _save()
	if save and FileAccess.file_exists(save.path()):
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(save.path()))
		var d := int(data.get("day", 1)) if data is Dictionary else 1
		lines = "Space or tap: carry on (day %d)\nN: start a new farm" % d
	_label.text = title
	_small.text = (subtitle + "\n\n" if subtitle != "" else "") + lines
	showing = "title"
	_layer.visible = true
	get_tree().paused = true


func _save() -> FarmSaveComponent:
	return SP.component(get_parent(), &"FarmSave") as FarmSaveComponent


func _build() -> void:
	if _layer:
		return
	_layer = CanvasLayer.new()
	_layer.layer = 60
	_layer.process_mode = Node.PROCESS_MODE_ALWAYS
	var shade := ColorRect.new()
	shade.color = Color(0.06, 0.05, 0.1, 0.62)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_STOP
	shade.gui_input.connect(func(e: InputEvent) -> void:
		if (e is InputEventMouseButton and e.pressed) or (e is InputEventScreenTouch and e.pressed):
			_confirm())
	_layer.add_child(shade)
	var box := VBoxContainer.new()
	box.set_anchors_preset(Control.PRESET_CENTER)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.grow_vertical = Control.GROW_DIRECTION_BOTH
	box.add_theme_constant_override(&"separation", 18)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_label = Label.new()
	_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_label.add_theme_font_size_override(&"font_size", 54)
	_label.add_theme_color_override(&"font_color", Color("#ffec27"))
	_label.add_theme_color_override(&"font_outline_color", Color("#3a2014"))
	_label.add_theme_constant_override(&"outline_size", 12)
	_small = Label.new()
	_small.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_small.add_theme_font_size_override(&"font_size", 20)
	_small.add_theme_color_override(&"font_outline_color", Color.BLACK)
	_small.add_theme_constant_override(&"outline_size", 6)
	box.add_child(_label)
	box.add_child(_small)
	_layer.add_child(box)
	add_child(_layer)


## Leaves the title screen (or the pause menu) and plays the music.
func start() -> void:
	var was_title := showing == "title" or showing == ""
	showing = ""
	if _layer:
		_layer.visible = false
	get_tree().paused = false
	if music and was_title:
		Sfx.play_music()
	if was_title:
		started.emit()


func toggle_pause() -> void:
	if showing == "pause":
		start()
		return
	if showing != "" or not GameState.is_playing():
		return
	_build()
	_label.text = "Paused"
	_small.text = "Space or P: carry on\nM: music %s\nR: restart" % ("off" if Sfx.music_on else "on")
	showing = "pause"
	_layer.visible = true
	get_tree().paused = true


func _confirm() -> void:
	if showing != "":
		start()


func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed and not event.echo):
		return
	var k := (event as InputEventKey).keycode
	if showing == "title":
		if k in [KEY_SPACE, KEY_ENTER, KEY_KP_ENTER, KEY_E]:
			start()
		elif k == KEY_N:
			var save := _save()
			if save:
				save.clear()
			GameState.restart()
		get_viewport().set_input_as_handled()
		return
	if k in [KEY_P, KEY_ESCAPE]:
		toggle_pause()
		get_viewport().set_input_as_handled()
	elif showing == "pause":
		if k == KEY_SPACE:
			start()
		elif k == KEY_M:
			Sfx.set_music_on(not Sfx.music_on)
			_small.text = "Space or P: carry on\nM: music %s\nR: restart" % ("off" if Sfx.music_on else "on")
		elif k == KEY_R:
			GameState.restart()
		get_viewport().set_input_as_handled()
