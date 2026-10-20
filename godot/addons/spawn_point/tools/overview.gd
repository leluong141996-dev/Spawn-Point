extends "res://addons/spawn_point/tools/record.gd"
## Plays the level with the GIF autopilot for a while, then saves one picture of the WHOLE map at its real size
## (needs a display, not headless). The HUD is hidden.
## Run: godot4 --path <project> --fixed-fps 60 res://addons/spawn_point/tools/overview.tscn -- <out.png> [frames]


func _ready() -> void:
	get_tree().root.set_meta(&"sp_autopilot", true)
	var args := OS.get_cmdline_user_args()
	var out := args[0] if args.size() > 0 else "user://overview.png"
	var total := int(args[1]) if args.size() > 1 else 600
	var main := (load(LEVEL) as PackedScene).instantiate()
	add_child(main)
	await get_tree().physics_frame
	for frame in total:
		_drive(frame)
		await get_tree().physics_frame
	for a in [&"move_left", &"move_right", &"move_up", &"move_down", &"shoot"]:
		Input.action_release(a)
	var bounds: Rect2 = main.get(&"bounds")
	_hide_hud(main)
	var sv := SubViewport.new()
	sv.size = Vector2i(bounds.size)
	sv.world_2d = get_viewport().world_2d
	sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	sv.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
	add_child(sv)
	var cam := Camera2D.new()
	cam.position = bounds.get_center()
	sv.add_child(cam)
	cam.make_current()
	for k in 4:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	sv.get_texture().get_image().save_png(out)
	print("SPAWNPOINT_OVERVIEW %s" % out)
	get_tree().quit(0)


func _hide_hud(node: Node) -> void:
	for c in node.get_children():
		if c is CanvasLayer:
			(c as CanvasLayer).visible = false
		_hide_hud(c)
