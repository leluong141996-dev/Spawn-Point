extends SPTestCase


func test_hitstop_restores_time_scale() -> void:
	FX.hitstop(0.05)
	assert_eq(Engine.time_scale, 0.0, "frozen during hit-stop:")
	await frames(12)
	assert_eq(Engine.time_scale, 1.0, "restored after hit-stop:")


func test_overlapping_hitstops_restore() -> void:
	FX.hitstop(0.05)
	await frames(1)
	FX.hitstop(0.08)
	await frames(2)
	FX.hitstop(0.03)
	await frames(20)
	assert_eq(Engine.time_scale, 1.0)


func test_death_anim_plays_a_copy_and_removes_it() -> void:
	var e := make_entity("Slime", "character", SP.TEAM_ENEMY, Vector2(20, 20), {"TopDownMovement": {}})
	var visual := e.get_node(^"Visual")
	var placeholder := visual.get_node(^"Shape")
	visual.remove_child(placeholder)
	placeholder.free()
	var holder := Node2D.new()
	holder.name = "Shape"
	visual.add_child(holder)
	var frames_res := SpriteFrames.new()
	var img := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	img.fill(Color.WHITE)
	var tex := ImageTexture.create_from_image(img)
	for a in ["idle", "die"]:
		frames_res.add_animation(a)
		frames_res.add_frame(a, tex)
		frames_res.add_frame(a, tex)
		frames_res.set_animation_speed(a, 20.0)
		frames_res.set_animation_loop(a, a == "idle")
	var spr := AnimatedSprite2D.new()
	spr.name = "Sprite"
	spr.sprite_frames = frames_res
	holder.add_child(spr)
	var before := World.level.get_child_count() if World.level else get_tree().current_scene.get_child_count()
	assert_true(FX.death_anim(e), "an entity with a die animation gets a corpse:")
	var parent: Node = World.level if World.level else get_tree().current_scene
	assert_eq(parent.get_child_count(), before + 1)
	await frames(60)
	assert_eq(parent.get_child_count(), before, "the corpse removes itself:")
	var plain := make_entity("Box", "character", SP.TEAM_ENEMY, Vector2(10, 10), {"TopDownMovement": {}})
	assert_false(FX.death_anim(plain), "no sprite, no corpse:")
