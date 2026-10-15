extends Node
## Autoload "FX": global game-feel effects — hit-stop, screen shake, particle bursts, floating text.

var _hitstop_token := 0
var _cameras: Array[Node] = []


func register_camera(cam: Node) -> void:
	if cam not in _cameras:
		_cameras.append(cam)


func unregister_camera(cam: Node) -> void:
	_cameras.erase(cam)


## Freezes the game for [param seconds] ("hit-stop"). The most recent call decides when it ends.
## Timed in engine time (not wall-clock), so it also works when the game runs faster than real
## time (fixed-fps tests, high refresh rates).
func hitstop(seconds: float) -> void:
	if seconds <= 0.0 or not is_inside_tree():
		return
	_hitstop_token += 1
	var token := _hitstop_token
	Engine.time_scale = 0.0
	await get_tree().create_timer(seconds, true, false, true).timeout
	if token == _hitstop_token:
		Engine.time_scale = 1.0


## Adds trauma (0..1) to every active camera rig. Shake strength grows with trauma².
func shake(amount: float) -> void:
	for cam in _cameras:
		if is_instance_valid(cam):
			cam.add_trauma(amount)


## One-shot particle burst at [param pos].
func burst(pos: Vector2, color: Color, amount := 16, speed := 180.0, lifetime := 0.45, size := 4.0, gravity := 300.0) -> void:
	var parent := _fx_parent()
	if parent == null:
		return
	var p := CPUParticles2D.new()
	p.one_shot = true
	p.explosiveness = 0.95
	p.amount = maxi(amount, 1)
	p.lifetime = lifetime
	p.direction = Vector2.UP
	p.spread = 180.0
	p.initial_velocity_min = speed * 0.4
	p.initial_velocity_max = speed
	p.gravity = Vector2(0, gravity)
	p.damping_min = 40.0
	p.damping_max = 80.0
	p.scale_amount_min = size * 0.5
	p.scale_amount_max = size
	var curve := Curve.new()
	curve.add_point(Vector2(0, 1))
	curve.add_point(Vector2(1, 0))
	p.scale_amount_curve = curve
	p.color = color
	p.position = pos
	p.z_index = 10
	parent.add_child(p)
	p.emitting = true
	p.finished.connect(p.queue_free)


## Rising, fading text (e.g. "+1") at [param pos].
func float_text(pos: Vector2, text: String, color := Color.WHITE) -> void:
	var parent := _fx_parent()
	if parent == null:
		return
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override(&"font_size", 18)
	label.add_theme_color_override(&"font_color", color)
	label.add_theme_color_override(&"font_outline_color", Color(0, 0, 0, 0.8))
	label.add_theme_constant_override(&"outline_size", 4)
	label.position = pos - Vector2(20, 24)
	label.z_index = 20
	parent.add_child(label)
	var t := label.create_tween().set_parallel(true)
	t.tween_property(label, ^"position:y", label.position.y - 28.0, 0.6).set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_CUBIC)
	t.tween_property(label, ^"modulate:a", 0.0, 0.6).set_delay(0.25)
	t.chain().tween_callback(label.queue_free)


## Fading copy of [param visual] — used for dash after-images.
func ghost(visual: Node2D, color := Color(1, 1, 1, 0.5)) -> void:
	var parent := _fx_parent()
	if parent == null or visual == null:
		return
	var copy := visual.duplicate(0) as Node2D
	copy.material = null
	for c in copy.find_children("*", "CanvasItem", true, false):
		(c as CanvasItem).material = null
	copy.modulate = color
	copy.z_index = -1
	parent.add_child(copy)
	copy.global_transform = visual.global_transform
	var t := copy.create_tween()
	t.tween_property(copy, ^"modulate:a", 0.0, 0.25)
	t.tween_callback(copy.queue_free)


## A copy of [param entity]'s picture that plays its "die" animation where it stood and then goes away.
## Returns false (and does nothing) when the entity has no such animation.
func death_anim(entity: Node2D) -> bool:
	var parent := _fx_parent()
	var visual := entity.get_node_or_null(^"Visual") as Node2D if entity else null
	if parent == null or visual == null:
		return false
	var src := visual.get_node_or_null(^"Shape/Sprite") as AnimatedSprite2D
	if src == null or src.sprite_frames == null or not src.sprite_frames.has_animation(&"die"):
		return false
	var copy := visual.duplicate(0) as Node2D
	copy.material = null
	for c in copy.find_children("*", "CanvasItem", true, false):
		(c as CanvasItem).material = null
	parent.add_child(copy)
	copy.global_transform = visual.global_transform
	copy.global_scale = Vector2.ONE  # the squash of the moment is not part of the death
	copy.modulate = Color.WHITE
	var spr := copy.get_node(^"Shape/Sprite") as AnimatedSprite2D
	spr.speed_scale = 1.0
	spr.play(&"die")
	spr.animation_finished.connect(copy.queue_free)
	var failsafe := Timer.new()  # a child of the copy, so it goes away with it
	failsafe.wait_time = 1.5
	failsafe.one_shot = true
	failsafe.autostart = true
	failsafe.timeout.connect(copy.queue_free)
	copy.add_child(failsafe)
	return true


func _fx_parent() -> Node:
	if not is_inside_tree():
		return null
	if World.level and is_instance_valid(World.level):
		return World.level
	return get_tree().current_scene
