class_name SPTestCase
extends Node2D
## Base class for headless tests. Every method starting with "test_" is run (it may await).
## A fresh instance is created per test method.

var failures: Array[String] = []
var _current := ""


func fail(msg: String) -> void:
	failures.append("%s: %s" % [_current, msg])


func assert_true(cond: bool, msg := "expected true") -> void:
	if not cond:
		fail(msg)


func assert_false(cond: bool, msg := "expected false") -> void:
	if cond:
		fail(msg)


func assert_eq(actual: Variant, expected: Variant, msg := "") -> void:
	if actual != expected:
		fail("%s expected %s, got %s" % [msg, str(expected), str(actual)])


func assert_near(actual: float, expected: float, tolerance: float, msg := "") -> void:
	if absf(actual - expected) > tolerance:
		fail("%s expected %.3f ± %.3f, got %.3f" % [msg, expected, tolerance, actual])


## Waits [param n] physics frames.
func frames(n: int) -> void:
	for i in n:
		await get_tree().physics_frame


## Static floor from x0..x1 whose top is at y.
func add_floor(x0: float, x1: float, y: float) -> StaticBody2D:
	var body := StaticBody2D.new()
	body.collision_layer = SP.LAYER_WORLD
	var cs := CollisionShape2D.new()
	var r := RectangleShape2D.new()
	r.size = Vector2(x1 - x0, 32)
	cs.shape = r
	body.position = Vector2((x0 + x1) * 0.5, y + 16)
	body.add_child(cs)
	add_child(body)
	return body


## Builds an entity in code the same way the compiler does (minus visuals).
## [param components] maps short names to param dictionaries.
func make_entity(type_name: String, body_kind: String, team: String, size: Vector2, components: Dictionary, pos := Vector2.ZERO, is_player := false) -> Node2D:
	var body: Node2D
	match body_kind:
		"character":
			var cb := CharacterBody2D.new()
			cb.collision_layer = SP.LAYER_PLAYER if team == SP.TEAM_PLAYER else SP.LAYER_ENEMY
			cb.collision_mask = SP.LAYER_WORLD
			body = cb
		"area":
			var a := Area2D.new()
			a.collision_layer = SP.LAYER_PICKUP
			a.collision_mask = SP.LAYER_PLAYER
			body = a
		_:
			body = StaticBody2D.new()
	body.name = type_name
	body.position = pos
	var core := SPEntityCore.new()
	core.name = "Entity"
	core.entity_type = type_name
	core.team = team
	core.is_player = is_player
	body.add_child(core)
	body.add_child(_rect_shape(size))
	var visual := Node2D.new()
	visual.name = "Visual"
	var shape := Polygon2D.new()
	shape.name = "Shape"
	visual.add_child(shape)
	body.add_child(visual)
	for short_name: String in components:
		var script := load(_script_for(short_name)) as Script
		var c: Node = script.new()
		c.name = short_name
		var params: Dictionary = components[short_name]
		for k: String in params:
			c.set(k, params[k])
		if c is Area2D:
			c.add_child(_rect_shape(size))
		body.add_child(c)
	add_child(body)
	return body


func _rect_shape(size: Vector2) -> CollisionShape2D:
	var cs := CollisionShape2D.new()
	cs.name = "CollisionShape2D"
	var r := RectangleShape2D.new()
	r.size = size
	cs.shape = r
	return cs


static func _script_for(short_name: String) -> String:
	return "res://addons/spawn_point/components/%s_component.gd" % short_name.to_snake_case()
