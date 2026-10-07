extends SPTestCase
## Every library script compiles and follows the component contract.

const DIRS := ["res://addons/spawn_point/components", "res://addons/spawn_point/runtime", "res://addons/spawn_point/tools"]


func test_all_scripts_compile() -> void:
	for dir in DIRS:
		for f in DirAccess.get_files_at(dir):
			if not f.ends_with(".gd"):
				continue
			var s := load(dir + "/" + f) as GDScript
			assert_true(s != null and s.can_instantiate(), "%s/%s does not compile" % [dir, f])


func test_components_declare_contract() -> void:
	var dir := "res://addons/spawn_point/components"
	for f in DirAccess.get_files_at(dir):
		if not f.ends_with("_component.gd"):
			continue
		var s := load(dir + "/" + f) as GDScript
		var consts := s.get_script_constant_map()
		for key in ["SP_NAME", "SP_HOSTS", "SP_REQUIRES", "SP_CATEGORY"]:
			assert_true(consts.has(key), "%s is missing %s" % [f, key])
		if consts.has("SP_NAME"):
			assert_eq(_script_for(consts.SP_NAME), dir + "/" + f, "file name must match SP_NAME:")
