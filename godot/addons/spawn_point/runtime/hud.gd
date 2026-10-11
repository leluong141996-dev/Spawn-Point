class_name SPHud
extends CanvasLayer
## Score, lives, player health, toast messages and the win / game-over overlay; an XP bar when the
## player has Experience, and a countdown when the rules set the variable "time_limit" (seconds).
## Press R at any time (or Enter after the game ends) to restart.

const TEXT_COLOR := Color("#fff1e8")
const ACCENT := Color("#ffec27")
const DANGER := Color("#ff004d")

var _score: Label
var _lives: Label
var _hearts: HBoxContainer
var _toast: Label
var _overlay: Control
var _overlay_title: Label
var _toast_tween: Tween
var _shown_health := -1
var _xp_back: ColorRect
var _xp_fill: ColorRect
var _level: Label
var _timer: Label


func _ready() -> void:
	layer = 10
	process_mode = Node.PROCESS_MODE_ALWAYS
	_build()
	GameState.score_changed.connect(_on_score)
	GameState.lives_changed.connect(_on_lives)
	GameState.message_posted.connect(show_message)
	GameState.var_changed.connect(func(n: String, _v: Variant) -> void:
		if n == "score_label":
			_on_score(GameState.score))
	GameState.game_won.connect(_show_overlay.bind("YOU WIN!", ACCENT))
	GameState.game_lost.connect(_show_overlay.bind("GAME OVER", DANGER))
	_on_score(GameState.score)
	_on_lives(GameState.lives)


func _process(_delta: float) -> void:
	var p := World.player()
	var h: HealthComponent = SP.component(p, &"Health") as HealthComponent if p else null
	var cur: int = h.current if h else -1
	if cur != _shown_health:
		_shown_health = cur
		_refresh_hearts(h)
	var xp := SP.component(p, &"Experience") as ExperienceComponent if p else null
	_xp_back.visible = xp != null
	_level.visible = xp != null
	if xp:
		_xp_fill.size.x = _xp_back.size.x * xp.progress()
		_level.text = "LV %d" % xp.level
	_timer.visible = GameState.vars.has("time_limit")
	if _timer.visible:
		var left := maxi(0, int(ceil(float(GameState.vars["time_limit"]) - GameState.time)))
		_timer.text = "%d:%02d" % [left / 60, left % 60]


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		var key := (event as InputEventKey).keycode
		if key == KEY_R or (not GameState.is_playing() and key in [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE]):
			GameState.restart()


func show_message(text: String) -> void:
	_toast.text = text
	_toast.modulate.a = 1.0
	_toast.scale = Vector2(1.3, 1.3)
	if _toast_tween:
		_toast_tween.kill()
	_toast_tween = _toast.create_tween()
	_toast_tween.tween_property(_toast, ^"scale", Vector2.ONE, 0.25).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	_toast_tween.tween_interval(1.4)
	_toast_tween.tween_property(_toast, ^"modulate:a", 0.0, 0.5)


func _on_score(score: int) -> void:
	_score.text = "%s %d" % [str(GameState.vars.get("score_label", "SCORE")), score]  # e.g. MONEY in farm games
	_score.pivot_offset = _score.size * 0.5
	var t := _score.create_tween()
	_score.scale = Vector2(1.25, 1.25)
	t.tween_property(_score, ^"scale", Vector2.ONE, 0.2).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)


func _on_lives(lives: int) -> void:
	_lives.text = "LIVES %d" % lives


func _refresh_hearts(h: HealthComponent) -> void:
	for c in _hearts.get_children():
		c.queue_free()
	if h == null:
		return
	for i in h.max_health:
		var r := ColorRect.new()
		r.custom_minimum_size = Vector2(14, 14)
		r.color = DANGER if i < h.current else Color(1, 1, 1, 0.15)
		_hearts.add_child(r)


func _show_overlay(title: String, color: Color) -> void:
	_overlay_title.text = title
	_overlay_title.add_theme_color_override(&"font_color", color)
	_overlay.visible = true
	_overlay.modulate.a = 0.0
	_overlay.create_tween().tween_property(_overlay, ^"modulate:a", 1.0, 0.35)


func _label(size: int, color := TEXT_COLOR) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override(&"font_size", size)
	l.add_theme_color_override(&"font_color", color)
	l.add_theme_color_override(&"font_outline_color", Color(0, 0, 0, 0.85))
	l.add_theme_constant_override(&"outline_size", maxi(size / 5, 3))
	return l


func _build() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	var top := HBoxContainer.new()
	top.set_anchors_preset(Control.PRESET_TOP_WIDE)
	top.offset_left = 16
	top.offset_right = -16
	top.offset_top = 10
	top.add_theme_constant_override(&"separation", 24)
	root.add_child(top)
	_score = _label(26, ACCENT)
	top.add_child(_score)
	_hearts = HBoxContainer.new()
	_hearts.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_hearts.add_theme_constant_override(&"separation", 4)
	_hearts.alignment = BoxContainer.ALIGNMENT_CENTER
	top.add_child(_hearts)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(spacer)
	_lives = _label(22)
	top.add_child(_lives)

	_timer = _label(30, TEXT_COLOR)
	_timer.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_timer.offset_top = 8
	_timer.offset_left = -80
	_timer.offset_right = 80
	_timer.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_timer.visible = false
	root.add_child(_timer)

	_xp_back = ColorRect.new()
	_xp_back.color = Color(0, 0, 0, 0.55)
	_xp_back.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_xp_back.offset_left = 16
	_xp_back.offset_right = -16
	_xp_back.offset_top = -22
	_xp_back.offset_bottom = -10
	_xp_back.visible = false
	root.add_child(_xp_back)
	_xp_fill = ColorRect.new()
	_xp_fill.color = Color("#29adff")
	_xp_fill.position = Vector2.ZERO
	_xp_fill.size = Vector2(0, 12)
	_xp_back.add_child(_xp_fill)
	_level = _label(20, Color("#29adff"))
	_level.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	_level.offset_left = -90
	_level.offset_right = -18
	_level.offset_top = -52
	_level.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_level.visible = false
	root.add_child(_level)

	_toast = _label(34)
	_toast.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_toast.offset_top = 70
	_toast.offset_left = -300
	_toast.offset_right = 300
	_toast.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_toast.pivot_offset = Vector2(300, 20)
	_toast.modulate.a = 0.0
	root.add_child(_toast)

	_overlay = ColorRect.new()
	(_overlay as ColorRect).color = Color(0, 0, 0, 0.55)
	_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	_overlay.visible = false
	root.add_child(_overlay)
	var box := VBoxContainer.new()
	box.set_anchors_preset(Control.PRESET_CENTER)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.grow_vertical = Control.GROW_DIRECTION_BOTH
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	_overlay.add_child(box)
	_overlay_title = _label(64)
	_overlay_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_overlay_title)
	var hint := _label(22)
	hint.text = "Press R to play again"
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(hint)
