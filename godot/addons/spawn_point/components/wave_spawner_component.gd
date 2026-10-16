class_name WaveSpawnerComponent
extends Node
## Sends waves of enemies from its entity (tower defense). [member waves] is a ";"-separated list of
## "count x Entity every seconds", e.g. "8 x Goblin every 1.2; 5 x Orc every 2". Emits [signal cleared]
## once every wave has been sent and no spawned enemy is left.

const SP_NAME := "WaveSpawner"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["parse_waves", "wave", "alive"]
const SP_CATEGORY := "core"

## Emitted when a wave starts; [param number] counts from 1.
signal wave_started(number: int)
## Emitted when every wave is done and the field is clear.
signal cleared()

## The waves (see the class description).
@export var waves: String = "6 x Goblin every 1.5; 8 x Goblin every 1.0"
## Seconds before the first wave and between waves.
@export_range(0.0, 120.0, 0.5) var pause: float = 6.0
## Random offset (px, total range) added to where each enemy appears: side-scrolling shooters spread them along the edge.
@export_range(0.0, 1000.0, 1.0) var spread_x: float = 0.0
## Same, vertically (shooters send enemies in at random heights).
@export_range(0.0, 1000.0, 1.0) var spread_y: float = 0.0
## Start sending waves right away. Off: waits for [method start] (a boss gate).
@export var autostart := true
## After the last wave start again, with bigger and faster waves, and never report [signal cleared].
@export var endless := false

var wave := 0
var _plan: Array[Dictionary] = []
var _left := 0
var _timer := 0.0
var _alive: Array = []
var _done := false
var _running := true
var _loops := 0
var _waves_sent := 0


func _ready() -> void:
	_plan = parse_waves(waves)
	_timer = pause
	_running = autostart


## Begins the waves (for a spawner created with autostart off).
func start() -> void:
	_running = true
	_timer = pause


func _every(w: Dictionary) -> float:
	var every := float(w.every)
	return maxf(minf(every, 0.25), every * pow(0.9, _loops))  # later rounds are faster, but never below 0.25 s


static func parse_waves(text: String) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	var re := RegEx.create_from_string("^\\s*(\\d+)\\s*x\\s*(\\w+)\\s*every\\s*([0-9.]+)\\s*$")
	for part in text.split(";", false):
		var m := re.search(part)
		if m:
			out.append({"count": int(m.get_string(1)), "entity": m.get_string(2), "every": float(m.get_string(3))})
		else:
			push_warning("WaveSpawner: bad wave '%s'" % part)
	return out


func alive() -> int:
	_alive = _alive.filter(func(n) -> bool: return is_instance_valid(n) and not (n as Node).is_queued_for_deletion())
	return _alive.size()


func _physics_process(delta: float) -> void:
	if _done or not _running or not GameState.is_playing():
		return
	_timer -= delta
	if _left > 0:
		if _timer <= 0.0:
			var w: Dictionary = _plan[wave - 1]
			var at := (get_parent() as Node2D).global_position + Vector2(
					randf_range(-spread_x, spread_x) * 0.5, randf_range(-spread_y, spread_y) * 0.5)
			var n := World.spawn(w.entity, at)
			if n:
				_alive.append(n)
			_left -= 1
			_timer = _every(w) if _left > 0 else pause  # a breather after each wave
		return
	if wave >= _plan.size():
		if endless and not _plan.is_empty():
			wave = 0  # round again, harder
			_loops += 1
		elif alive() == 0:
			_done = true
			cleared.emit()
		return
	# Next wave after the pause once the field is clear (or after a long wait even if it is not).
	if _timer <= 0.0 and (wave == 0 or alive() == 0 or _timer < -pause * 2.0):
		wave += 1
		_waves_sent += 1
		_left = int(_plan[wave - 1].count * (1.0 + 0.25 * _loops))
		_timer = 0.0
		GameState.message("Wave %d!" % _waves_sent)
		wave_started.emit(_waves_sent)
