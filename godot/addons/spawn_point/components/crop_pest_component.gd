class_name CropPestComponent
extends Node
## A pest (crow, mole, rabbit) for farming games: it heads for the nearest plot with a crop, ripe ones
## first, and eats it after [member eat_seconds] unless it is chased off. Drives a TopDownMovement.

const SP_NAME := "CropPest"
const SP_HOSTS: Array[String] = ["CharacterBody2D"]
const SP_REQUIRES: Array[String] = ["TopDownMovement"]
const SP_CATEGORY := "controller"

## Emitted when a crop is eaten.
signal ate()

## Seconds of pecking before the crop is gone.
@export_range(0.1, 60.0, 0.1) var eat_seconds: float = 3.0
## Leaves after this many crops (0 = never).
@export_range(0, 100) var appetite: int = 2

var _entity: CharacterBody2D
var _target: FarmPlotComponent
var _eating := 0.0
var _eaten := 0
var _wander := Vector2.ZERO
var _wander_t := 0.0


func _ready() -> void:
	_entity = get_parent() as CharacterBody2D
	process_physics_priority = -10


func _physics_process(delta: float) -> void:
	var mv := SP.component(_entity, &"TopDownMovement") as TopDownMovementComponent
	if mv == null:
		return
	if not GameState.is_playing():
		mv.move_vector = Vector2.ZERO
		return
	if _target == null or not is_instance_valid(_target) or not _target.has_crop():
		_target = _pick()
		_eating = 0.0
	if _target == null:  # nothing to eat: drift around
		_wander_t -= delta
		if _wander_t <= 0.0:
			_wander = Vector2.from_angle(randf() * TAU) * 0.4
			_wander_t = 1.5
		mv.move_vector = _wander
		return
	var to := (_target.get_parent() as Node2D).global_position - _entity.global_position
	if to.length() > 10.0:
		mv.move_vector = to.normalized()
		_eating = 0.0
		return
	mv.move_vector = Vector2.ZERO
	_eating += delta
	if _eating >= eat_seconds:
		_target.destroy_crop()
		_target = null
		_eaten += 1
		ate.emit()
		if appetite > 0 and _eaten >= appetite:
			World.destroy(_entity)


func _pick() -> FarmPlotComponent:
	var best: FarmPlotComponent = null
	var best_score := INF
	for e in _entity.get_tree().get_nodes_in_group(&"farm_plot"):
		var plot := SP.component(e, &"FarmPlot") as FarmPlotComponent
		if plot == null or not plot.has_crop():
			continue
		var d := (e as Node2D).global_position.distance_to(_entity.global_position)
		var score := d * (0.5 if plot.is_ripe() else 1.0)  # ripe crops are the tastiest
		if score < best_score:
			best_score = score
			best = plot
	return best
