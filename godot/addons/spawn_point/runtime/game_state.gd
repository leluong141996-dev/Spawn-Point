extends Node
## Autoload "GameState": score, lives, rule variables and the win/lose flow.

signal score_changed(score: int)
signal lives_changed(lives: int)
signal var_changed(name: String, value: Variant)
signal message_posted(text: String)
## Emitted once per whole second of play time (survival goals, timed events).
signal second_passed(seconds: int)
signal game_won
signal game_lost
## Emitted just before a full restart reloads the level (a saved game should start over).
signal restarting

enum Phase { PLAYING, WON, LOST }

var score := 0
var lives := 3
var start_lives := 3
var time := 0.0
var phase := Phase.PLAYING
var vars := {}

var _started := false


## Called by the level on load. Resets everything on the first load and after restart().
func begin_level(level_lives: int) -> void:
	if _started:
		phase = Phase.PLAYING
		return
	_started = true
	start_lives = level_lives
	score = 0
	lives = level_lives
	time = 0.0
	vars.clear()
	phase = Phase.PLAYING


func _process(delta: float) -> void:
	if phase == Phase.PLAYING:
		var before := int(time)
		time += delta
		if int(time) > before:
			second_passed.emit(int(time))


func is_playing() -> bool:
	return phase == Phase.PLAYING


func add_score(amount: int) -> void:
	if amount == 0:
		return
	score += amount
	score_changed.emit(score)


func set_var(var_name: String, value: Variant) -> void:
	vars[var_name] = value
	var_changed.emit(var_name, value)


func add_var(var_name: String, delta: float) -> void:
	set_var(var_name, get_var(var_name) + delta)


func get_var(var_name: String) -> Variant:
	return vars.get(var_name, 0)


func message(text: String) -> void:
	message_posted.emit(text)


## The player lost a life. Returns true if the player may respawn.
func player_died() -> bool:
	if phase != Phase.PLAYING:
		return false
	lives = maxi(lives - 1, 0)
	lives_changed.emit(lives)
	if lives <= 0:
		lose()
		return false
	return true


func win() -> void:
	if phase != Phase.PLAYING:
		return
	phase = Phase.WON
	game_won.emit()


func lose() -> void:
	if phase != Phase.PLAYING:
		return
	phase = Phase.LOST
	game_lost.emit()


## Resets the run state without reloading the scene (used by tests and tools).
func reset_run(level_lives := 3) -> void:
	_started = false
	begin_level(level_lives)


## Full restart: score, lives and variables reset, level reloads.
func restart() -> void:
	restarting.emit()
	get_tree().paused = false  # a restart from a pause menu
	_started = false
	Engine.time_scale = 1.0
	get_tree().reload_current_scene()
