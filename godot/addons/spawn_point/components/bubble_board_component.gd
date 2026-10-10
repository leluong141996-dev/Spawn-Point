class_name BubbleBoardComponent
extends Node
## A complete bubble-shooter ("dinosaur eggs") board, launched by its entity. Aim with the mouse or
## left/right, shoot with Space / X / click. Shots bounce off the side walls and stick to the eggs;
## three or more of one colour pop, and eggs no longer hanging from the ceiling fall for a bonus.
## Every [member shots_per_drop] shots the ceiling comes down a row. Emits [signal cleared] when the
## board is empty and [signal overflowed] when an egg reaches the bottom line (wire them to win() and
## lose() in the rules).

const SP_NAME := "BubbleBoard"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["cell_center", "neighbors", "place", "shoot_at", "egg_count", "board_rect"]
const SP_CATEGORY := "core"

const SQRT3_2 := 0.8660254

## Emitted when eggs pop; [param count] includes the ones that fell.
signal popped(count: int)
## Emitted each time the ceiling comes down.
signal ceiling_dropped(rows: int)
## Emitted when the board is empty.
signal cleared()
## Emitted when an egg reaches the bottom line.
signal overflowed()

## Eggs per row.
@export_range(4, 20) var columns: int = 8
## Rows filled at the start.
@export_range(1, 20) var rows: int = 5
## Board height in rows; an egg in the last row loses the game.
@export_range(4, 30) var height_rows: int = 12
## Egg size in px.
@export_range(12.0, 96.0, 1.0) var cell: float = 32.0
## How many colours are in play (2-6).
@export_range(2, 6) var colors: int = 4
## Comma-separated egg colours.
@export var palette: String = "#ff004d,#29adff,#00e436,#ffec27,#ff77a8,#ffa300"
## Shot speed in px/s.
@export_range(100.0, 4000.0, 10.0) var shot_speed: float = 900.0
## Keyboard aiming speed in degrees per second.
@export_range(10.0, 720.0, 5.0) var aim_speed: float = 110.0
## The ceiling drops one row after this many shots.
@export_range(1, 100) var shots_per_drop: int = 7
## Score per popped egg.
@export_range(0, 10000) var score_pop: int = 10
## Score per egg that falls after a pop.
@export_range(0, 10000) var score_drop: int = 20
## Launcher position relative to the entity (the entity stands next to it).
@export var launcher_offset: Vector2 = Vector2(56, 0)
## Layout seed (0 = a new board every run).
@export_range(0, 1000000) var layout_seed: int = 0

var _entity: Node2D
var _view: Node2D
var _grid := {}  # Vector2i(col, row) -> colour index
var _pal: Array[Color] = []
var _tex: Array[ImageTexture] = []
var _rng := RandomNumberGenerator.new()
var _angle := -PI / 2.0
var _current := 0
var _next := 0
var _shot_active := false
var _shot_pos := Vector2.ZERO
var _shot_vel := Vector2.ZERO
var _shots := 0
var _drop := 0  # rows the ceiling has come down
var _falling: Array[Dictionary] = []
var _mouse_aim := false
var _done := false


func _ready() -> void:
	_entity = get_parent() as Node2D
	PlayerInputComponent.ensure_actions()
	if layout_seed != 0:
		_rng.seed = layout_seed
	else:
		_rng.randomize()
	for c in palette.split(",", false):
		_pal.append(Color(c.strip_edges()))
	while _pal.size() < 6:
		_pal.append(Color.from_hsv(_pal.size() / 6.0, 0.7, 1.0))
	for i in colors:
		_tex.append(_egg_texture(_pal[i]))
	for r in rows:
		for c in _row_len(r):
			_grid[Vector2i(c, r)] = _rng.randi() % colors
	_current = _pick_color()
	_next = _pick_color()
	_view = Node2D.new()
	_view.name = "BubbleView"
	_view.z_index = -1  # under the entity sprite (the dino stands in front of the tray)
	_view.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_view.draw.connect(_on_draw)
	_entity.add_child.call_deferred(_view)


# --- geometry -------------------------------------------------------------------------------

func _row_h() -> float:
	return cell * SQRT3_2


func _row_len(row: int) -> int:
	return columns if row % 2 == 0 else columns - 1


func launcher() -> Vector2:
	return _entity.global_position + launcher_offset


## The board in global coordinates (its bottom edge is just above the launcher).
func board_rect() -> Rect2:
	var w := columns * cell
	var h := (height_rows - 1) * _row_h() + cell
	var l := launcher()
	return Rect2(l.x - w / 2.0, l.y - cell * 0.9 - h, w, h)


func cell_center(c: Vector2i) -> Vector2:
	var b := board_rect()
	var x := b.position.x + cell / 2.0 + c.x * cell + (cell / 2.0 if c.y % 2 == 1 else 0.0)
	return Vector2(x, b.position.y + cell / 2.0 + (c.y + _drop) * _row_h())


func neighbors(c: Vector2i) -> Array[Vector2i]:
	var odd := c.y % 2 == 1
	var d: Array = [Vector2i(-1, 0), Vector2i(1, 0)]
	d += [Vector2i(0, -1), Vector2i(1, -1), Vector2i(0, 1), Vector2i(1, 1)] if odd \
		else [Vector2i(-1, -1), Vector2i(0, -1), Vector2i(-1, 1), Vector2i(0, 1)]
	var out: Array[Vector2i] = []
	for o: Vector2i in d:
		var n := c + o
		if n.y >= 0 and n.x >= 0 and n.x < _row_len(n.y):
			out.append(n)
	return out


func egg_count() -> int:
	return _grid.size()


# --- play -----------------------------------------------------------------------------------

func _physics_process(delta: float) -> void:
	_update_falling(delta)
	if _view:
		_view.queue_redraw()
	if _done or not GameState.is_playing():
		return
	_aim(delta)
	if not _shot_active and (Input.is_action_just_pressed(&"shoot") or Input.is_action_just_pressed(&"jump")):
		shoot_at(_angle)
	if _shot_active:
		var steps := 4
		for i in steps:
			if _step_shot(delta / steps):
				break


func _aim(delta: float) -> void:
	var dir := Input.get_axis(&"move_left", &"move_right")
	if dir != 0.0:
		_mouse_aim = false
		_angle += deg_to_rad(aim_speed) * dir * delta
	elif _mouse_aim:
		var to := _entity.get_global_mouse_position() - launcher()
		if to.length() > 8.0:
			_angle = to.angle()
	_angle = clampf(_angle, deg_to_rad(-170.0), deg_to_rad(-10.0))


func _input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		_mouse_aim = true


## Fires the current egg at [param angle] (radians, -PI/2 = straight up).
func shoot_at(angle: float) -> void:
	if _shot_active or _done:
		return
	_angle = clampf(angle, deg_to_rad(-170.0), deg_to_rad(-10.0))
	_shot_active = true
	_shot_pos = launcher()
	_shot_vel = Vector2.from_angle(_angle) * shot_speed
	if Sfx.has_sound("shoot"):
		Sfx.play("shoot", 0.05)


func _step_shot(dt: float) -> bool:
	var b := board_rect()
	_shot_pos += _shot_vel * dt
	var left := b.position.x + cell / 2.0
	var right := b.end.x - cell / 2.0
	if _shot_pos.x < left or _shot_pos.x > right:
		_shot_pos.x = clampf(_shot_pos.x, left, right)
		_shot_vel.x = -_shot_vel.x
		if Sfx.has_sound("blip"):
			Sfx.play("blip", 0.1, -8.0)
	var hit := _shot_pos.y <= b.position.y + cell / 2.0 + _drop * _row_h()
	if not hit:
		for c: Vector2i in _grid:
			if cell_center(c).distance_to(_shot_pos) < cell * 0.82:
				hit = true
				break
	if hit:
		_shot_active = false
		place(_snap(_shot_pos), _current)
		return true
	return false


func _snap(pos: Vector2) -> Vector2i:
	var b := board_rect()
	var row := maxi(0, int(round((pos.y - b.position.y - cell / 2.0) / _row_h())) - _drop)
	var best := Vector2i(-1, -1)
	var best_d := INF
	for r in range(maxi(0, row - 1), row + 2):
		for c in _row_len(r):
			var k := Vector2i(c, r)
			if _grid.has(k):
				continue
			var d := cell_center(k).distance_squared_to(pos)
			if d < best_d:
				best_d = d
				best = k
	return best


## Puts an egg of colour [param color] in cell [param c] and resolves pops, falls and the ceiling.
func place(c: Vector2i, color: int) -> void:
	if c.x < 0:
		return
	_grid[c] = color
	var group := _same_color(c)
	var popped_n := 0
	if group.size() >= 3:
		for k in group:
			_burst(k, score_pop)
			_grid.erase(k)
		popped_n = group.size()
		var floating := _floating()
		for k in floating:
			_falling.append({"pos": cell_center(k), "vel": Vector2(_rng.randf_range(-60, 60), -120), "color": _grid[k]})
			GameState.add_score(score_drop)
			_grid.erase(k)
		popped_n += floating.size()
		FX.shake(0.15 + 0.03 * popped_n)
		if Sfx.has_sound("explosion"):
			Sfx.play("explosion", 0.1, -4.0, 1.3)
		if floating.size() > 0:
			FX.float_text(cell_center(c) + Vector2(0, -20), "+%d" % (floating.size() * score_drop), Color("#ffec27"))
		popped.emit(popped_n)
	_shots += 1
	if popped_n == 0 and _shots % shots_per_drop == 0:
		_drop += 1
		FX.shake(0.3)
		if Sfx.has_sound("land"):
			Sfx.play("land", 0.0, 0.0, 0.6)
		ceiling_dropped.emit(_drop)
	if _grid.is_empty():
		_done = true
		cleared.emit()
		return
	for k: Vector2i in _grid:
		if k.y + _drop >= height_rows - 1:
			_done = true
			overflowed.emit()
			return
	_current = _next
	if not _color_in_play(_current):
		_current = _pick_color()
	_next = _pick_color()


func _same_color(start: Vector2i) -> Array[Vector2i]:
	var color: int = _grid[start]
	var seen := {start: true}
	var todo: Array[Vector2i] = [start]
	var out: Array[Vector2i] = []
	while not todo.is_empty():
		var k: Vector2i = todo.pop_back()
		out.append(k)
		for n in neighbors(k):
			if not seen.has(n) and _grid.get(n, -1) == color:
				seen[n] = true
				todo.append(n)
	return out


func _floating() -> Array[Vector2i]:
	var seen := {}
	var todo: Array[Vector2i] = []
	for k: Vector2i in _grid:
		if k.y == 0:
			seen[k] = true
			todo.append(k)
	while not todo.is_empty():
		var k: Vector2i = todo.pop_back()
		for n in neighbors(k):
			if not seen.has(n) and _grid.has(n):
				seen[n] = true
				todo.append(n)
	var out: Array[Vector2i] = []
	for k: Vector2i in _grid:
		if not seen.has(k):
			out.append(k)
	return out


func _color_in_play(color: int) -> bool:
	return _grid.values().has(color)


func _pick_color() -> int:
	var present := {}
	for v in _grid.values():
		present[v] = true
	if present.is_empty():
		return _rng.randi() % colors
	var keys := present.keys()
	return keys[_rng.randi() % keys.size()]


func _burst(c: Vector2i, points: int) -> void:
	var pos := cell_center(c)
	FX.burst(pos, _pal[_grid[c]], 10, 160.0, 0.4, 3.0, 200.0)
	GameState.add_score(points)


func _update_falling(delta: float) -> void:
	var b := board_rect()
	for f in _falling:
		f.vel.y += 900.0 * delta
		f.pos += f.vel * delta
	_falling = _falling.filter(func(f: Dictionary) -> bool: return f.pos.y < b.end.y + 400.0)


# --- drawing --------------------------------------------------------------------------------

func _on_draw() -> void:
	var b := board_rect()
	var to_local := func(p: Vector2) -> Vector2: return _view.to_local(p)
	var frame := Rect2(to_local.call(b.position) - Vector2(6, 6), b.size + Vector2(12, 12 + cell))
	_view.draw_rect(frame, Color(0.05, 0.05, 0.12, 0.72))
	_view.draw_rect(frame, Color("#5f574f"), false, 4.0)
	var ceiling_y: float = to_local.call(Vector2(0, b.position.y + _drop * _row_h())).y
	if _drop > 0:
		_view.draw_rect(Rect2(frame.position.x, frame.position.y, frame.size.x, ceiling_y - frame.position.y),
				Color("#5f574f"))
	var dead_y: float = to_local.call(Vector2(0, b.position.y + (height_rows - 1) * _row_h() + cell * 0.1)).y
	var x0 := frame.position.x
	while x0 < frame.end.x:
		_view.draw_line(Vector2(x0, dead_y), Vector2(minf(x0 + 8.0, frame.end.x), dead_y), Color(1, 0.2, 0.3, 0.7), 2.0)
		x0 += 14.0
	for k: Vector2i in _grid:
		_draw_egg(to_local.call(cell_center(k)), _grid[k])
	for f in _falling:
		_draw_egg(to_local.call(f.pos), f.color)
	var l: Vector2 = to_local.call(launcher())
	if not _done:
		var dir := Vector2.from_angle(_angle)
		for i in range(1, 7):  # dotted aim guide
			_view.draw_circle(l + dir * (cell * 0.9 + i * 16.0), 2.0, Color(1, 1, 1, 0.55 - i * 0.07))
		_view.draw_line(l, l + dir * cell * 0.9, Color("#c2c3c7"), 8.0)
		_view.draw_circle(l, cell * 0.45, Color("#5f574f"))
		if not _shot_active:
			_draw_egg(l, _current)
		_draw_egg(l + Vector2(cell * 1.6, cell * 0.3), _next, 0.7)
	if _shot_active:
		_draw_egg(to_local.call(_shot_pos), _current)


func _draw_egg(pos: Vector2, color: int, scale := 1.0) -> void:
	var t := _tex[color]
	var size := Vector2(cell, cell) * scale
	_view.draw_texture_rect(t, Rect2(pos - size / 2.0, size), false)


func _egg_texture(base: Color) -> ImageTexture:
	# Pixel-art egg at half resolution: outline, shading, a highlight and speckles.
	var n := maxi(8, int(cell / 2.0))
	var img := Image.create(n, n, false, Image.FORMAT_RGBA8)
	var outline := base.darkened(0.6)
	var shadow := base.darkened(0.25)
	var light := base.lightened(0.45)
	var spot := base.darkened(0.4)
	var cx := (n - 1) / 2.0
	var rng := RandomNumberGenerator.new()
	rng.seed = int(base.to_rgba32())
	for y in n:
		for x in n:
			var dx := (x - cx) / (n * 0.42)
			var t := (y + 0.5) / n
			var dy := (y - n * 0.54) / (n * (0.5 if t > 0.54 else 0.6))  # narrower top: egg shape
			var d := dx * dx + dy * dy
			if d > 1.0:
				continue
			var c := base
			if d > 0.72:
				c = outline
			elif dx + dy * 0.6 > 0.35:
				c = shadow
			elif dx < -0.25 and dy < -0.2:
				c = light
			img.set_pixel(x, y, c)
	for i in maxi(3, n / 4):
		var sx := rng.randi_range(int(n * 0.3), int(n * 0.7))
		var sy := rng.randi_range(int(n * 0.35), int(n * 0.8))
		if img.get_pixel(sx, sy).a > 0.0 and img.get_pixel(sx, sy) != outline:
			img.set_pixel(sx, sy, spot)
	return ImageTexture.create_from_image(img)
