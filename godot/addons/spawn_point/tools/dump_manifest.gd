extends Node
## Introspects every component script and writes raw metadata as JSON.
## Run: godot4 --headless --path <project> res://addons/spawn_point/tools/dump_manifest.tscn -- <out.json>
## The Python side merges this with doc comments into manifest.json.

const COMPONENT_DIR := "res://addons/spawn_point/components"


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var out_path := args[0] if args.size() > 0 else "user://manifest_raw.json"
	var components := []
	var files := DirAccess.get_files_at(COMPONENT_DIR)
	files.sort()
	for f in files:
		if f.ends_with("_component.gd"):
			components.append(_describe(COMPONENT_DIR + "/" + f))
	var file := FileAccess.open(out_path, FileAccess.WRITE)
	if file == null:
		push_error("cannot write %s" % out_path)
		get_tree().quit(1)
		return
	file.store_string(JSON.stringify({"godot": Engine.get_version_info().string, "components": components}, "  ", false))
	file.close()
	get_tree().quit(0)


func _describe(path: String) -> Dictionary:
	var s := load(path) as GDScript
	var consts := s.get_script_constant_map()
	var params := []
	var state := []
	for p in s.get_script_property_list():
		var pname: String = p.name
		if not (p.usage & PROPERTY_USAGE_SCRIPT_VARIABLE) or pname.begins_with("_"):
			continue
		if not (p.usage & PROPERTY_USAGE_EDITOR):
			state.append({"name": pname, "type": type_string(p.type)})
			continue
		params.append({
			"name": p.name,
			"type": type_string(p.type),
			"hint": _hint_name(p.hint),
			"hint_string": p.hint_string,
			"default": s.get_property_default_value(p.name),
		})
	var signals := []
	for sig in s.get_script_signal_list():
		signals.append({"name": sig.name, "args": _args(sig.args)})
	var methods := []
	var internal: Array = Array(consts.get("SP_INTERNAL", []))
	for m in s.get_script_method_list():
		var mname: String = m.name
		if mname.begins_with("_") or mname.begins_with("@") or mname in internal:
			continue
		methods.append({
			"name": mname,
			"args": _args(m.args),
			"default_count": m.default_args.size(),
			"returns": type_string(m.return.type),
		})
	return {
		"name": consts.get("SP_NAME", ""),
		"class": s.get_global_name(),
		"script": path,
		"base": s.get_instance_base_type(),
		"hosts": Array(consts.get("SP_HOSTS", [])),
		"requires": Array(consts.get("SP_REQUIRES", [])),
		"category": consts.get("SP_CATEGORY", ""),
		"entity_params": Array(consts.get("SP_ENTITY_PARAMS", [])),
		"params": params,
		"state": state,
		"signals": signals,
		"methods": methods,
	}


func _args(list: Array) -> Array:
	var out := []
	for a in list:
		out.append({"name": a.name, "type": type_string(a.type) if a.type != TYPE_OBJECT else String(a.class_name) if a.class_name != &"" else "Object"})
	return out


func _hint_name(hint: int) -> String:
	match hint:
		PROPERTY_HINT_RANGE:
			return "range"
		PROPERTY_HINT_ENUM:
			return "enum"
	return ""
