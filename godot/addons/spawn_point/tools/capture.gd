extends Node
## Plays the main level with scripted input and saves screenshots (needs a display, not headless).
## Run: godot4 --path <project> --fixed-fps 60 res://addons/spawn_point/tools/capture.tscn -- <out_dir> [frames]
## frames: comma-separated physics frames to capture (default 40,100,160,220).

const LEVEL := "res://levels/main.tscn"


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var out_dir := args[0] if args.size() > 0 else "user://captures"
	var shots: Array[int] = []
	for s in (args[1] if args.size() > 1 else "40,100,160,220").split(","):
		shots.append(int(s))
	DirAccess.make_dir_recursive_absolute(out_dir)
	add_child((load(LEVEL) as PackedScene).instantiate())
	var last: int = shots.max()
	for frame in range(1, last + 1):
		_script_input(frame)
		await get_tree().physics_frame
		if frame in shots:
			await RenderingServer.frame_post_draw
			var img := get_viewport().get_texture().get_image()
			img.save_png("%s/frame_%04d.png" % [out_dir, frame])
	get_tree().quit(0)


# Idle for a moment, then run right with periodic jumps, shooting and a dash.
func _script_input(frame: int) -> void:
	if frame == 30:
		Input.action_press(&"move_right")
	if frame >= 30 and frame % 35 == 0:
		Input.action_press(&"jump")
	if frame >= 30 and frame % 35 == 14:
		Input.action_release(&"jump")
	if frame == 120:
		Input.action_press(&"shoot")
		Input.action_press(&"dash")
	if frame == 125:
		Input.action_release(&"dash")
	if frame == 170:
		Input.action_release(&"shoot")
