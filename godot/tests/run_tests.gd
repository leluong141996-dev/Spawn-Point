extends Node
## Headless test runner (scene res://tests/run_tests.tscn). Usage:
##   godot4 --headless --path godot --fixed-fps 60 res://tests/run_tests.tscn [-- filter]
## Runs every test_* method of every res://tests/test_*.gd. Exit code 1 on failure.
## Runs as a scene (not --script) so autoloads exist exactly as in a real game.


class ErrorCatcher extends Logger:
	## Script/engine errors raised while a test runs. A runtime error aborts the test function
	## silently, so without this a broken test would be reported as passing.
	var errors: Array[String] = []
	var _mutex := Mutex.new()

	func _log_error(function: String, file: String, line: int, code: String, rationale: String,
			_editor_notify: bool, error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
		if error_type == ERROR_TYPE_WARNING:
			return
		_mutex.lock()
		errors.append("%s (%s:%d %s)" % [rationale if rationale else code, file.get_file(), line, function])
		_mutex.unlock()

	func take() -> Array[String]:
		_mutex.lock()
		var out := errors.duplicate()
		errors.clear()
		_mutex.unlock()
		return out


var _catcher := ErrorCatcher.new()


func _ready() -> void:
	OS.add_logger(_catcher)
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
			_catcher.take()
			await case.call(mname)
			for err in _catcher.take():
				case.failures.append("%s: runtime error: %s" % [case._current, err])
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
