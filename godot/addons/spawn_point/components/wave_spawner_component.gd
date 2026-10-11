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

var wave := 0
var _plan: Array[Dictionary] = []
var _left := 0
var _timer := 0.0
var _alive: Array = []
var _done := false


func _ready() -> void:
	_plan = parse_waves(waves)
	_timer = pause


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
	if _done or not GameState.is_playing():
		return
	_timer -= delta
	if _left > 0:
		if _timer <= 0.0:
			var w: Dictionary = _plan[wave - 1]
			var n := World.spawn(w.entity, (get_parent() as Node2D).global_position)
			if n:
				_alive.append(n)
			_left -= 1
			_timer = w.every if _left > 0 else pause  # a breather after each wave
		return
	if wave >= _plan.size():
		if alive() == 0:
			_done = true
			cleared.emit()
		return
	# Next wave after the pause once the field is clear (or after a long wait even if it is not).
	if _timer <= 0.0 and (wave == 0 or alive() == 0 or _timer < -pause * 2.0):
		wave += 1
		_left = _plan[wave - 1].count
		_timer = 0.0
		GameState.message("Wave %d!" % wave)
		wave_started.emit(wave)
