extends Node
## Build backend: turns res://build_plan.json (written by the Python compiler) into scenes.
## Run as a scene so autoloads and the class cache behave exactly like in the game:
##   godot4 --headless --path <project> res://addons/spawn_point/tools/build.tscn
## Godot itself serializes every scene, so the output is always format-valid.

const PLAN_PATH := "res://build_plan.json"
const ENTITY_CORE := "res://addons/spawn_point/runtime/entity_core.gd"
const LEVEL_SCRIPT := "res://addons/spawn_point/runtime/level.gd"
const CAMERA_SCRIPT := "res://addons/spawn_point/runtime/camera_rig.gd"
const HUD_SCRIPT := "res://addons/spawn_point/runtime/hud.gd"

const TILE_SOLID_TOP := Vector2i(0, 0)
const TILE_SOLID := Vector2i(1, 0)
const TILE_ONEWAY := Vector2i(2, 0)

var _errors: Array[String] = []


func _ready() -> void:
	var text := FileAccess.get_file_as_string(PLAN_PATH)
	var plan: Variant = JSON.parse_string(text)
	if typeof(plan) != TYPE_DICTIONARY:
		_fail("cannot parse %s" % PLAN_PATH)
		return
	for dir in ["res://entities", "res://levels"]:
		DirAccess.make_dir_recursive_absolute(dir)

	for e: Dictionary in plan.entities:
		var node := _build_entity(e)
		_save_scene(node, "res://entities/%s.tscn" % e.name)
	var tileset := _build_tileset(plan)
	var err := ResourceSaver.save(tileset, "res://levels/tiles.tres")
	if err != OK:
		_errors.append("saving tiles.tres failed: %s" % error_string(err))
	var level := _build_level(plan, load("res://levels/tiles.tres"))
	_save_scene(level, "res://levels/main.tscn")

	if _errors.is_empty():
		print("SPAWNPOINT_BUILD_OK")
		get_tree().quit(0)
	else:
		for e in _errors:
			printerr("SPAWNPOINT_BUILD_ERROR: ", e)
		get_tree().quit(1)


func _fail(msg: String) -> void:
	printerr("SPAWNPOINT_BUILD_ERROR: ", msg)
	get_tree().quit(1)


# --- entities ---------------------------------------------------------------------------------

func _build_entity(e: Dictionary) -> Node2D:
	var body: CollisionObject2D
	match String(e.body):
		"character":
			body = CharacterBody2D.new()
		"static":
			body = StaticBody2D.new()
		_:
			body = Area2D.new()
	body.name = e.name
	body.collision_layer = int(e.layer)
	body.collision_mask = int(e.mask)

	var core: Node = load(ENTITY_CORE).new()
	core.name = "Entity"
	core.set(&"entity_type", e.name)
	core.set(&"team", e.team)
	core.set(&"is_player", e.is_player)
	_own(body, core, body)

	var shape_type := String(e.shape.type)
	var size := Vector2(e.shape.size[0], e.shape.size[1])
	var color := Color(String(e.shape.color))
	var sprite: Variant = e.get("sprite")
	var polygon := PackedVector2Array()
	if sprite != null:
		for p in sprite.polygon:
			polygon.append(Vector2(p[0], p[1]))
	body.set_meta(&"sp_half_size", size * 0.5)
	if shape_type != "none":
		if polygon.size() >= 3 and String(e.body) != "character":
			# Pickups, hazards and static bodies collide with the drawing's outline.
			var cp := CollisionPolygon2D.new()
			cp.name = "CollisionPolygon2D"
			cp.polygon = polygon
			_own(body, cp, body)
		else:
			# Moving bodies keep a smooth shape fitted to the sprite (no snagging on tile seams).
			var cs := CollisionShape2D.new()
			cs.name = "CollisionShape2D"
			cs.shape = _collision_shape(shape_type, size, 1.0)
			_own(body, cs, body)
		var visual: Node2D
		if sprite != null:
			visual = _sprite_visual(sprite, size, String(e.pivot) == "bottom")
		else:
			visual = _visual(shape_type, size, color, e.eye, String(e.pivot) == "bottom")
		_own(body, visual, body)
		_own_tree(visual, body)

	for c: Dictionary in e.components:
		var script := load(String(c.script)) as Script
		if script == null:
			_errors.append("%s: cannot load component script %s" % [e.name, c.script])
			continue
		var node: Node = script.new()
		node.name = c.name
		_apply_params(node, c.params, "%s.%s" % [e.name, c.name])
		_own(body, node, body)
		if c.area_scale != null and shape_type != "none" and polygon.size() >= 3:
			# Hit/hurt areas follow the sprite outline: the hitbox matches the drawing.
			var acp := CollisionPolygon2D.new()
			acp.name = "CollisionPolygon2D"
			var scaled := PackedVector2Array()
			for p in polygon:
				scaled.append(p * float(c.area_scale))
			acp.polygon = scaled
			_own(node, acp, body)
		elif c.area_scale != null and shape_type != "none":
			var acs := CollisionShape2D.new()
			acs.name = "CollisionShape2D"
			acs.shape = _collision_shape(shape_type, size, float(c.area_scale))
			_own(node, acs, body)
	return body


func _apply_params(node: Object, params: Dictionary, where: String) -> void:
	for key: String in params:
		var current: Variant = node.get(key)
		var v: Variant = params[key]
		var converted: Variant
		match typeof(current):
			TYPE_INT:
				converted = int(v)
			TYPE_FLOAT:
				converted = float(v)
			TYPE_BOOL:
				converted = bool(v)
			TYPE_VECTOR2:
				converted = Vector2(v[0], v[1])
			TYPE_COLOR:
				converted = Color(String(v))
			TYPE_STRING:
				converted = String(v)
			TYPE_STRING_NAME:
				converted = StringName(v)
			_:
				_errors.append("%s: parameter '%s' has unsupported type" % [where, key])
				continue
		node.set(key, converted)


func _collision_shape(type: String, size: Vector2, scale: float) -> Shape2D:
	var s := size * scale
	match type:
		"triangle":
			var tri := ConvexPolygonShape2D.new()
			tri.points = PackedVector2Array([Vector2(0, -s.y * 0.5), Vector2(s.x * 0.5, s.y * 0.5), Vector2(-s.x * 0.5, s.y * 0.5)])
			return tri
		"spikes":
			# Only the lower 60% hurts: brushing the very tips is forgiven.
			var sp := RectangleShape2D.new()
			sp.size = Vector2(s.x * 0.9, s.y * 0.6)
			return sp
		"circle":
			var c := CircleShape2D.new()
			c.radius = minf(s.x, s.y) * 0.5
			return c
		"capsule":
			var cap := CapsuleShape2D.new()
			cap.radius = minf(s.x, s.y) * 0.5
			cap.height = maxf(s.y, cap.radius * 2.0)
			return cap
	var r := RectangleShape2D.new()
	r.size = s
	return r


func _visual(type: String, size: Vector2, color: Color, eye: bool, pivot_bottom: bool) -> Node2D:
	var visual := Node2D.new()
	visual.name = "Visual"
	var shape := Polygon2D.new()
	shape.name = "Shape"
	shape.polygon = _polygon(type, size)
	shape.color = color
	shape.antialiased = true
	if pivot_bottom:
		# Squash & stretch pivots at the feet.
		visual.position = Vector2(0, size.y * 0.5)
		shape.position = Vector2(0, -size.y * 0.5)
	visual.add_child(shape)
	# Darker lower half gives the flat shape some volume.
	var shade := Polygon2D.new()
	shade.name = "Shade"
	shade.polygon = _lower_half(shape.polygon)
	shade.color = Color(0, 0, 0, 0.18)
	shape.add_child(shade)
	if eye:
		var r := clampf(minf(size.x, size.y) * 0.16, 2.5, 7.0)
		var white := Polygon2D.new()
		white.name = "Eye"
		white.polygon = _circle_points(r, 12)
		white.color = Color("#fff1e8")
		white.position = Vector2(size.x * 0.2, -size.y * 0.18)
		shape.add_child(white)
		var pupil := Polygon2D.new()
		pupil.name = "Pupil"
		pupil.polygon = _circle_points(r * 0.5, 10)
		pupil.color = Color("#1d2b53")
		pupil.position = Vector2(r * 0.35, 0)
		white.add_child(pupil)
	return visual


func _sprite_visual(sprite: Dictionary, size: Vector2, pivot_bottom: bool) -> Node2D:
	var visual := Node2D.new()
	visual.name = "Visual"
	visual.set_meta(&"sp_color", Color(String(sprite.color)))
	var holder := Node2D.new()  # flipped to face left/right; the sprite inside keeps its scale
	holder.name = "Shape"
	visual.add_child(holder)
	if pivot_bottom:
		visual.position = Vector2(0, size.y * 0.5)
		holder.position = Vector2(0, -size.y * 0.5)
	var tex := load(String(sprite.texture)) as Texture2D
	if tex == null:
		_errors.append("cannot load sprite texture %s" % sprite.texture)
		return visual
	var fw := int(sprite.frame_size[0])
	var fh := int(sprite.frame_size[1])
	var frames := SpriteFrames.new()
	for anim_name: String in sprite.animations:
		var a: Dictionary = sprite.animations[anim_name]
		if anim_name != "default":
			frames.add_animation(anim_name)
		frames.set_animation_speed(anim_name, float(a.fps))
		frames.set_animation_loop(anim_name, bool(a.loop))
		for f in a.frames:
			var at := AtlasTexture.new()
			at.atlas = tex
			at.region = Rect2(int(f[0]) * fw, int(f[1]) * fh, fw, fh)
			frames.add_frame(anim_name, at)
	if not sprite.animations.has("default"):
		frames.remove_animation(&"default")
	var spr := AnimatedSprite2D.new()
	spr.name = "Sprite"
	spr.sprite_frames = frames
	var first: String = "idle" if sprite.animations.has("idle") else String(sprite.animations.keys()[0])
	spr.animation = first
	spr.autoplay = first
	spr.scale = Vector2(sprite.scale, sprite.scale)
	spr.position = Vector2(sprite.offset[0], sprite.offset[1])
	spr.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	holder.add_child(spr)
	return visual


func _polygon(type: String, size: Vector2) -> PackedVector2Array:
	var hx := size.x * 0.5
	var hy := size.y * 0.5
	match type:
		"triangle":
			return PackedVector2Array([Vector2(0, -hy), Vector2(hx, hy), Vector2(-hx, hy)])
		"spikes":
			# Zigzag row of teeth, one per ~10 px.
			var teeth := maxi(int(size.x / 10.0), 1)
			var pts := PackedVector2Array([Vector2(-hx, hy)])
			for i in teeth:
				var x0 := -hx + size.x * i / teeth
				pts.append(Vector2(x0 + size.x / teeth * 0.5, -hy))
				pts.append(Vector2(x0 + size.x / teeth, hy))
			return pts
		"circle":
			var pts := PackedVector2Array()
			for i in 32:
				var a := TAU * i / 32.0
				pts.append(Vector2(cos(a) * hx, sin(a) * hy))
			return pts
		"capsule":
			var r := minf(hx, hy)
			var pts := PackedVector2Array()
			var top := -hy + r
			var bottom := hy - r
			for i in 13:
				var a := PI + PI * i / 12.0
				pts.append(Vector2(cos(a) * r, top + sin(a) * r))
			for i in 13:
				var a := PI * i / 12.0
				pts.append(Vector2(cos(a) * r, bottom + sin(a) * r))
			return pts
	# Rounded rectangle.
	var rad := minf(minf(hx, hy) * 0.35, 6.0)
	var pts := PackedVector2Array()
	var corners := [Vector2(hx - rad, -hy + rad), Vector2(hx - rad, hy - rad), Vector2(-hx + rad, hy - rad), Vector2(-hx + rad, -hy + rad)]
	for ci in 4:
		for i in 5:
			var a := -PI * 0.5 + PI * 0.5 * ci + PI * 0.5 * i / 4.0
			pts.append(corners[ci] + Vector2(cos(a), sin(a)) * rad)
	return pts


func _lower_half(poly: PackedVector2Array) -> PackedVector2Array:
	var out := PackedVector2Array()
	var min_y := INF
	var max_y := -INF
	for p in poly:
		min_y = minf(min_y, p.y)
		max_y = maxf(max_y, p.y)
	var cut := lerpf(min_y, max_y, 0.55)
	for p in poly:
		out.append(Vector2(p.x, maxf(p.y, cut)))
	return out


func _circle_points(r: float, n: int) -> PackedVector2Array:
	var pts := PackedVector2Array()
	for i in n:
		var a := TAU * i / n
		pts.append(Vector2(cos(a), sin(a)) * r)
	return pts


# --- tiles ------------------------------------------------------------------------------------

func _build_tileset(plan: Dictionary) -> TileSet:
	var ts := int(plan.tile_size)
	var base := Color(String(plan.tiles.solid.color))
	var top := Color(String(plan.tiles.solid.top))
	var plank := Color(String(plan.tiles.oneway.color))
	var img := Image.create(ts * 3, ts, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	_paint_block(img, 0, ts, base)
	_paint_top(img, 0, ts, top)
	_paint_block(img, ts, ts, base)
	_paint_plank(img, ts * 2, ts, plank)

	var tileset := TileSet.new()
	tileset.tile_size = Vector2i(ts, ts)
	tileset.add_physics_layer()
	tileset.set_physics_layer_collision_layer(0, 1)
	tileset.set_physics_layer_collision_mask(0, 0)
	var src := TileSetAtlasSource.new()
	src.texture = ImageTexture.create_from_image(img)
	src.texture_region_size = Vector2i(ts, ts)
	tileset.add_source(src, 0)
	var h := ts * 0.5
	for coords in [TILE_SOLID_TOP, TILE_SOLID]:
		src.create_tile(coords)
		var td := src.get_tile_data(coords, 0)
		td.add_collision_polygon(0)
		td.set_collision_polygon_points(0, 0, PackedVector2Array([Vector2(-h, -h), Vector2(h, -h), Vector2(h, h), Vector2(-h, h)]))
	src.create_tile(TILE_ONEWAY)
	var od := src.get_tile_data(TILE_ONEWAY, 0)
	od.add_collision_polygon(0)
	var plank_h := maxf(ts * 0.3, 6.0)
	od.set_collision_polygon_points(0, 0, PackedVector2Array([Vector2(-h, -h), Vector2(h, -h), Vector2(h, -h + plank_h), Vector2(-h, -h + plank_h)]))
	od.set_collision_polygon_one_way(0, 0, true)
	return tileset


func _paint_block(img: Image, x0: int, ts: int, c: Color) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 1234
	var edge := maxi(ts / 16, 1)
	for y in ts:
		for x in ts:
			var col := c
			if x < edge or y < edge:
				col = c.lightened(0.12)
			elif x >= ts - edge or y >= ts - edge:
				col = c.darkened(0.25)
			elif rng.randf() < 0.06:
				col = c.darkened(0.12)
			img.set_pixel(x0 + x, y, col)


func _paint_top(img: Image, x0: int, ts: int, c: Color) -> void:
	var depth := maxi(ts / 5, 3)
	for x in ts:
		# Slightly ragged lower edge (grass / trim).
		var d := depth + (1 if (x / maxi(ts / 8, 1)) % 2 == 0 else 0)
		for y in d:
			var col := c.lightened(0.25) if y < maxi(ts / 16, 1) else c
			img.set_pixel(x0 + x, y, col)
		img.set_pixel(x0 + x, d, c.darkened(0.3))


func _paint_plank(img: Image, x0: int, ts: int, c: Color) -> void:
	var plank_h := maxi(int(ts * 0.3), 6)
	for y in plank_h:
		for x in ts:
			var col := c
			if y < maxi(ts / 16, 1):
				col = c.lightened(0.25)
			elif y >= plank_h - maxi(ts / 16, 1):
				col = c.darkened(0.3)
			elif x == ts / 2:
				col = c.darkened(0.2)
			img.set_pixel(x0 + x, y, col)


# --- level ------------------------------------------------------------------------------------

func _build_level(plan: Dictionary, tileset: TileSet) -> Node2D:
	var ts := int(plan.tile_size)
	var bounds := Rect2(plan.bounds[0], plan.bounds[1], plan.bounds[2], plan.bounds[3])
	var root := Node2D.new()
	root.name = "Main"
	root.set_script(load(LEVEL_SCRIPT))
	root.set(&"genre", plan.genre)
	root.set(&"lives", int(plan.lives))
	root.set(&"tile_size", ts)
	root.set(&"bounds", bounds)

	_build_backdrop(root, plan, bounds)

	var tiles := TileMapLayer.new()
	tiles.name = "Tiles"
	tiles.tile_set = tileset
	var solid := {}
	for cell in plan.map.cells:
		if cell[2] == "solid":
			solid[Vector2i(cell[0], cell[1])] = true
	for cell in plan.map.cells:
		var pos := Vector2i(cell[0], cell[1])
		var atlas := TILE_ONEWAY
		if cell[2] == "solid":
			atlas = TILE_SOLID if solid.has(pos + Vector2i.UP) else TILE_SOLID_TOP
		tiles.set_cell(pos, 0, atlas)
	_own(root, tiles, root)

	var walls := StaticBody2D.new()
	walls.name = "Bounds"
	walls.collision_layer = 1
	walls.collision_mask = 0
	_own(root, walls, root)
	for side: String in plan.walls:
		var wb := WorldBoundaryShape2D.new()
		match side:
			"left":
				wb.normal = Vector2.RIGHT
				wb.distance = bounds.position.x
			"right":
				wb.normal = Vector2.LEFT
				wb.distance = -bounds.end.x
			"top":
				wb.normal = Vector2.DOWN
				wb.distance = bounds.position.y
			"bottom":
				wb.normal = Vector2.UP
				wb.distance = -bounds.end.y
		var cs := CollisionShape2D.new()
		cs.name = "Wall" + side.capitalize()
		cs.shape = wb
		_own(walls, cs, root)

	var entities := Node2D.new()
	entities.name = "Entities"
	_own(root, entities, root)
	var counts := {}
	for p: Dictionary in plan.placements:
		var scene := load("res://entities/%s.tscn" % p.entity) as PackedScene
		var inst := scene.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node2D
		var n: int = counts.get(p.entity, 0) + 1
		counts[p.entity] = n
		inst.name = p.entity if n == 1 else "%s%d" % [p.entity, n]
		inst.position = Vector2(p.x, p.y)
		entities.add_child(inst)
		inst.owner = root

	var cam := Camera2D.new()
	cam.name = "Camera"
	cam.set_script(load(CAMERA_SCRIPT))
	var vp := Vector2(plan.viewport[0], plan.viewport[1])
	_apply_camera_limits(cam, bounds, vp)
	_own(root, cam, root)

	var hud := CanvasLayer.new()
	hud.name = "HUD"
	hud.set_script(load(HUD_SCRIPT))
	_own(root, hud, root)

	var rules := Node.new()
	rules.name = "Rules"
	var rules_script := load(String(plan.rules_script)) as Script
	if rules_script == null or not rules_script.can_instantiate():
		_errors.append("generated rules script %s does not compile" % plan.rules_script)
	else:
		rules.set_script(rules_script)
	_own(root, rules, root)
	return root


# Cheap depth: rolling parallax hills and clouds for platformers, a checker floor for top-down.
func _build_backdrop(root: Node2D, plan: Dictionary, bounds: Rect2) -> void:
	var bg := Color(String(plan.background))
	var holder := Node2D.new()
	holder.name = "Backdrop"
	holder.z_index = -10
	_own(root, holder, root)
	if plan.genre == "topdown":
		var floor_rect := ColorRect.new()
		floor_rect.name = "Floor"
		floor_rect.position = bounds.position
		floor_rect.size = bounds.size
		floor_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var mat := ShaderMaterial.new()
		mat.shader = load("res://addons/spawn_point/shaders/floor_grid.gdshader")
		mat.set_shader_parameter(&"tile_size", float(plan.tile_size))
		mat.set_shader_parameter(&"size", bounds.size)
		mat.set_shader_parameter(&"color_a", bg.lightened(0.04))
		mat.set_shader_parameter(&"color_b", bg.lightened(0.08))
		floor_rect.material = mat
		_own(holder, floor_rect, root)
		return
	var width := 1280.0
	var ground := bounds.end.y
	var layers := [
		{"name": "Clouds", "scroll": 0.1, "color": Color(1, 1, 1, 0.05), "kind": "clouds"},
		{"name": "FarHills", "scroll": 0.25, "color": bg.lightened(0.07), "kind": "hills", "base": ground - 220.0, "amp": 70.0, "seed": 1.3},
		{"name": "NearHills", "scroll": 0.5, "color": bg.lightened(0.13), "kind": "hills", "base": ground - 120.0, "amp": 45.0, "seed": 4.1},
	]
	for layer: Dictionary in layers:
		var px := Parallax2D.new()
		px.name = layer.name
		px.scroll_scale = Vector2(layer.scroll, 1.0)
		px.repeat_size = Vector2(width, 0)
		px.repeat_times = 3
		_own(holder, px, root)
		if layer.kind == "hills":
			var poly := Polygon2D.new()
			poly.name = "Shape"
			var pts := PackedVector2Array()
			var steps := 64
			for i in steps + 1:
				var x := width * i / steps
				var t := TAU * i / steps
				var y: float = layer.base - layer.amp * (0.6 * sin(t * 2.0 + layer.seed) + 0.4 * sin(t * 5.0 + layer.seed * 2.0))
				pts.append(Vector2(x, y))
			pts.append(Vector2(width, ground + 600.0))
			pts.append(Vector2(0, ground + 600.0))
			poly.polygon = pts
			poly.color = layer.color
			_own(px, poly, root)
		else:
			var rng := RandomNumberGenerator.new()
			rng.seed = 99
			for i in 6:
				var cloud := Polygon2D.new()
				cloud.name = "Cloud%d" % i
				var w := rng.randf_range(80, 180)
				cloud.polygon = _ellipse(w, w * 0.3)
				cloud.position = Vector2(width * i / 6.0 + rng.randf_range(0, 120), bounds.position.y + rng.randf_range(20, 160))
				cloud.color = layer.color
				_own(px, cloud, root)


func _ellipse(w: float, h: float) -> PackedVector2Array:
	var pts := PackedVector2Array()
	for i in 24:
		var a := TAU * i / 24.0
		pts.append(Vector2(cos(a) * w * 0.5, sin(a) * h * 0.5))
	return pts


func _apply_camera_limits(cam: Camera2D, bounds: Rect2, vp: Vector2) -> void:
	# When the level is smaller than the screen on an axis, center it instead of clamping.
	if bounds.size.x >= vp.x:
		cam.limit_left = int(bounds.position.x)
		cam.limit_right = int(bounds.end.x)
	else:
		var cx := bounds.get_center().x
		cam.limit_left = int(cx - vp.x * 0.5)
		cam.limit_right = int(cx + vp.x * 0.5)
	if bounds.size.y >= vp.y:
		cam.limit_top = int(bounds.position.y - vp.y * 0.25)
		cam.limit_bottom = int(bounds.end.y)
	else:
		var cy := bounds.get_center().y
		cam.limit_top = int(cy - vp.y * 0.5)
		cam.limit_bottom = int(cy + vp.y * 0.5)


func _own(parent: Node, child: Node, owner_node: Node) -> void:
	parent.add_child(child)
	child.owner = owner_node


func _own_tree(node: Node, owner_node: Node) -> void:
	for c in node.get_children():
		c.owner = owner_node
		_own_tree(c, owner_node)


func _save_scene(root: Node, path: String) -> void:
	var ps := PackedScene.new()
	var err := ps.pack(root)
	if err != OK:
		_errors.append("packing %s failed: %s" % [path, error_string(err)])
		return
	err = ResourceSaver.save(ps, path)
	if err != OK:
		_errors.append("saving %s failed: %s" % [path, error_string(err)])
	root.free()
