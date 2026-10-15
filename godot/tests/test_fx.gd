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


func test_dust_and_spark_clean_up_after_themselves() -> void:
	var parent: Node = World.level if World.level else get_tree().current_scene
	var before := parent.get_child_count()
	FX.dust(Vector2(10, 10), 0, 6)
	FX.dust(Vector2(10, 10), -1, 3)
	assert_eq(parent.get_child_count(), before + 3, "two puffs for both sides plus one for a single side:")
	FX.spark(Vector2(20, 20))
	assert_true(parent.get_child_count() > before + 3, "a spark and its flying pixels:")
	await frames(60)
	assert_eq(parent.get_child_count(), before, "everything is gone again:")


func test_sparks_are_capped_so_a_swarm_cannot_bury_the_screen() -> void:
	var parent: Node = World.level if World.level else get_tree().current_scene
	var before := parent.get_child_count()
	for i in 200:
		FX.spark(Vector2(i, 0))
	assert_true(parent.get_child_count() - before < 24 * 2 + 2, "at most 24 sparks (each with one burst):")
	await frames(60)
	assert_eq(parent.get_child_count(), before)


func test_pixel_art_shake_is_whole_pixels_and_never_rotates() -> void:
	var cam := SPCameraRig.new()
	add_child(cam)
	await frames(2)
	FX.pixel_art = true
	cam.trauma = 1.0
	await frames(3)
	assert_eq(cam.rotation, 0.0, "no rotation in pixel art:")
	assert_eq(cam.offset, cam.offset.round(), "whole-pixel offset:")
	FX.pixel_art = false
	cam.trauma = 1.0
	await frames(3)
	assert_true(cam.rotation != 0.0 or cam.offset != cam.offset.round(), "smooth shake for other styles:")
	FX.pixel_art = true
	cam.queue_free()
