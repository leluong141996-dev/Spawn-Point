extends Node
## Headless test runner (scene res://tests/run_tests.tscn). Usage:
##   godot4 --headless --path godot --fixed-fps 60 res://tests/run_tests.tscn [-- filter]
## Runs every test_* method of every res://tests/test_*.gd. Exit code 1 on failure.
## Runs as a scene (not --script) so autoloads exist exactly as in a real game.


func _ready() -> void:
	_run.call_deferred()


func _run() -> void:
	var filter := ""
	var args := OS.get_cmdline_user_args()
	if args.size() > 0:
		filter = args[0]
	var files := DirAccess.get_files_at("res://tests")
	var total := 0
	var failed: Array[String] = []
	for f in files:
		if not f.begins_with("test_") or not f.ends_with(".gd"):
			continue
		var script := load("res://tests/" + f) as GDScript
		if script == null or not script.can_instantiate():
			failed.append("%s: failed to load" % f)
			continue
		for m in script.get_script_method_list():
			var mname: String = m.name
			if not mname.begins_with("test_"):
				continue
			if filter != "" and not (f + "::" + mname).contains(filter):
				continue
			total += 1
			var case: SPTestCase = script.new()
			case._current = "%s::%s" % [f.get_basename(), mname]
			add_child(case)
			GameState.reset_run(3)
			World.begin_level(case, INF)
			await case.call(mname)
			if case.failures.is_empty():
				print("  ok    ", case._current)
			else:
				print("  FAIL  ", case._current)
				for msg in case.failures:
					print("        ", msg)
				failed.append_array(case.failures)
			case.queue_free()
			await get_tree().process_frame
			Engine.time_scale = 1.0
	print("\n%d tests, %d failures" % [total, failed.size()])
	get_tree().quit(1 if failed.size() > 0 else 0)
