extends Node
## Autoload "FX": global game-feel effects — hit-stop, screen shake, particle bursts, floating text.

## True while a pixel-art level is loaded: shake snaps to whole pixels, dust and sparks are blocky.
var pixel_art := true

var _hitstop_token := 0
var _cameras: Array[Node] = []
var _sparks := 0


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


## A few square specks of dust that skid sideways along the ground and stop: landings, jumps, footsteps.
## [param dir] is -1 / +1 for one side, 0 for both.
func dust(pos: Vector2, dir := 0, amount := 4, color := Color(0.92, 0.88, 0.78, 0.9)) -> void:
	for side in ([-1, 1] if dir == 0 else [dir]):
		var parent := _fx_parent()
		if parent == null:
			return
		var p := CPUParticles2D.new()
		p.one_shot = true
		p.explosiveness = 0.9
		p.amount = maxi(amount / (2 if dir == 0 else 1), 1)
		p.lifetime = 0.32
		p.direction = Vector2(side, -0.18)
		p.spread = 22.0
		p.initial_velocity_min = 25.0
		p.initial_velocity_max = 70.0
		p.gravity = Vector2.ZERO
		p.damping_min = 90.0
		p.damping_max = 140.0
		p.scale_amount_min = 2.0
		p.scale_amount_max = 4.0 if pixel_art else 3.0
		var curve := Curve.new()
		curve.add_point(Vector2(0, 1))
		curve.add_point(Vector2(1, 0))
		p.scale_amount_curve = curve
		p.color = color
		p.position = pos
		p.z_index = 9
		parent.add_child(p)
		p.emitting = true
		p.finished.connect(p.queue_free)


## A short hit flash: a plus-shaped spark that pops and shrinks, with a few pixels flying off.
func spark(pos: Vector2, color := Color.WHITE) -> void:
	var parent := _fx_parent()
	if parent == null or _sparks >= 24:  # a swarm of enemies must not bury the screen
		return
	_sparks += 1
	var s := Node2D.new()
	s.position = pos
	s.z_index = 11
	s.draw.connect(func() -> void:
		s.draw_rect(Rect2(-1, -6, 2, 12), color)
		s.draw_rect(Rect2(-6, -1, 12, 2), color)
		s.draw_rect(Rect2(-2, -2, 4, 4), Color.WHITE)
		for d in [Vector2(-4, -4), Vector2(3, -4), Vector2(-4, 3), Vector2(3, 3)]:
			s.draw_rect(Rect2(d, Vector2(1, 1)), color))
	parent.add_child(s)
	s.rotation = 0.0 if pixel_art else randf_range(-0.4, 0.4)
	var t := s.create_tween()
	t.set_parallel(true)
	t.tween_property(s, ^"scale", Vector2(0.2, 0.2), 0.13).from(Vector2(1.5, 1.5))
	t.tween_property(s, ^"modulate:a", 0.0, 0.13)
	t.chain().tween_callback(func() -> void:
		_sparks -= 1
		s.queue_free())
	burst(pos, color, 4, 130.0, 0.22, 2.0, 0.0)


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
