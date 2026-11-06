extends SPTestCase


func _with_sprite(e: Node2D) -> AnimatedSprite2D:
	# Mirrors build.gd: Visual/Shape/Sprite with one frame per animation.
	var visual := e.get_node(^"Visual")
	var placeholder := visual.get_node(^"Shape")
	visual.remove_child(placeholder)  # free now, so the new holder can take the name "Shape"
	placeholder.free()
	var holder := Node2D.new()
	holder.name = "Shape"
	visual.add_child(holder)
	var frames := SpriteFrames.new()
	var img := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	img.fill(Color.WHITE)
	var tex := ImageTexture.create_from_image(img)
	for a in ["idle", "run", "jump", "fall", "hurt", "attack", "die"]:
		frames.add_animation(a)
		frames.add_frame(a, tex)
		frames.set_animation_loop(a, a not in ["attack", "die"])
	var spr := AnimatedSprite2D.new()
	spr.name = "Sprite"
	spr.sprite_frames = frames
	holder.add_child(spr)
	var animator := AnimatorComponent.new()
	animator.name = "Animator"
	e.add_child(animator)
	return spr


func test_animator_follows_movement() -> void:
	add_floor(-500, 500, 100)
	var p := make_entity("Hero", "character", SP.TEAM_PLAYER, Vector2(20, 30),
			{"PlatformerMovement": {}, "Health": {"invincibility_time": 0.0}}, Vector2(0, 60), true)
	var spr := _with_sprite(p)
	var mv := SP.component(p, &"PlatformerMovement") as PlatformerMovementComponent
	await frames(30)
	assert_eq(String(spr.animation), "idle")
	mv.move_vector = Vector2(1, 0)
	await frames(15)
	assert_eq(String(spr.animation), "run")
	mv.jump_held = true
	mv.request_jump()
	await frames(4)
	assert_eq(String(spr.animation), "jump")
	await frames(30)
	assert_eq(String(spr.animation), "fall")
	await frames(40)
	(SP.component(p, &"Health") as HealthComponent).damage(1)
	await frames(2)
	assert_eq(String(spr.animation), "hurt")


func test_sprite_entities_flip_instead_of_rotating() -> void:
	var e := make_entity("Bug", "character", SP.TEAM_ENEMY, Vector2(20, 20), {"TopDownMovement": {}})
	_with_sprite(e)
	await frames(1)
	SP.face(e, Vector2(-1, -1), true)
	var holder := e.get_node(^"Visual/Shape") as Node2D
	assert_eq(holder.scale.x, -1.0)
	assert_eq(holder.rotation, 0.0)


func test_attack_plays_when_the_weapon_fires() -> void:
	var e := make_entity("Knight", "character", SP.TEAM_PLAYER, Vector2(20, 30),
			{"TopDownMovement": {}, "Weapon": {"projectile": "Nope", "muzzle_distance": 0.0}})
	var spr := _with_sprite(e)
	var weapon := SP.component(e, &"Weapon") as WeaponComponent
	await frames(5)
	assert_eq(String(spr.animation), "idle")
	weapon.fired.emit()  # the animation is driven by the signal, not by spawning a projectile
	await frames(3)
	assert_eq(String(spr.animation), "attack")
	await frames(30)
	assert_eq(String(spr.animation), "idle", "back to idle after the swing:")


func test_four_direction_sprites_follow_the_facing() -> void:
	var e := make_entity("Walker", "character", SP.TEAM_PLAYER, Vector2(16, 16), {"TopDownMovement": {}}, Vector2(100, 100))
	var spr := _with_sprite(e)
	var img := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	img.fill(Color.WHITE)
	for a in ["idle_up", "run_up", "idle_side", "run_side"]:
		spr.sprite_frames.add_animation(a)
		spr.sprite_frames.add_frame(a, ImageTexture.create_from_image(img))
	var mv := SP.movement(e) as TopDownMovementComponent
	await frames(2)
	mv.move_vector = Vector2.UP
	await frames(10)
	assert_eq(String(spr.animation), "run_up")
	mv.move_vector = Vector2.LEFT
	await frames(10)
	assert_eq(String(spr.animation), "run_side")
	mv.move_vector = Vector2.DOWN
	await frames(4)
	mv.move_vector = Vector2.ZERO
	await frames(40)
	assert_eq(String(spr.animation), "idle", "standing, facing down")


func test_things_that_loop_in_place_start_at_their_own_frame() -> void:
	var picked := {}
	for x in [0, 32, 64, 96, 128]:
		var e := make_entity("Tree%d" % x, "static", SP.TEAM_NEUTRAL, Vector2(10, 10), {}, Vector2(x, 64))
		var spr := _with_sprite(e)
		var sf := SpriteFrames.new()  # a six-frame swaying idle
		var img := Image.create(4, 4, false, Image.FORMAT_RGBA8)
		img.fill(Color.WHITE)
		var tex := ImageTexture.create_from_image(img)
		for i in 6:
			sf.add_frame(&"default", tex)
		sf.rename_animation(&"default", &"idle")
		sf.set_animation_loop(&"idle", true)
		sf.set_animation_speed(&"idle", 3.0)
		spr.sprite_frames = sf
		spr.play(&"idle")
		picked[x] = spr
	await frames(3)
	var starts := {}
	for x in picked:
		starts[(picked[x] as AnimatedSprite2D).frame] = true
	assert_true(starts.size() > 1, "trees in a row do not sway in step")
