class_name FarmDaysComponent
extends Node
## A farming season of [member days] days. Each day runs from 6:00 to 22:00 in [member day_seconds]; the light
## warms in the evening and goes dark at night. Sleeping (a [SleepSpotComponent] bed) ends the day early; at
## midnight the farmer drops off anyway. Overnight, watered crops grow and fed animals get their product ready.
## After the last day the season ends ([signal season_ended]).

const SP_NAME := "FarmDays"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["sleep", "next_day", "day", "clock", "time_of_day"]
const SP_CATEGORY := "core"

## Emitted each morning with the day number (1 on the first).
signal day_started(day: int)
## Emitted when the last day is over.
signal season_ended()

## Days in the season.
@export_range(1, 30) var days: int = 3
## Real seconds from 6:00 to 22:00.
@export_range(10.0, 1200.0, 1.0) var day_seconds: float = 90.0
## How much of a crop's growing time one night adds (watered crops only).
@export_range(0.0, 1.0, 0.05) var overnight_growth: float = 0.5

var day := 1
var clock := 0.0  # seconds into the day
var _over := false
var _tint: CanvasModulate
var _layer: CanvasLayer
var _label: Label
var _sleeping := false


func _ready() -> void:
	_tint = CanvasModulate.new()
	_tint.name = "DayLight"
	_layer = CanvasLayer.new()
	_layer.layer = 11
	_label = Label.new()
	_label.add_theme_font_size_override(&"font_size", 20)
	_label.add_theme_color_override(&"font_outline_color", Color.BLACK)
	_label.add_theme_constant_override(&"outline_size", 5)
	_label.anchor_left = 0.5
	_label.anchor_right = 0.5
	_label.offset_left = -110
	_label.offset_right = 110
	_label.offset_top = 40
	_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_layer.add_child(_label)
	add_child.call_deferred(_layer)
	get_tree().current_scene.add_child.call_deferred(_tint)
	(func() -> void: day_started.emit(day)).call_deferred()


## Fraction of the day gone, 0 at 6:00 and 1 at 22:00.
func time_of_day() -> float:
	return clampf(clock / day_seconds, 0.0, 1.0)


func _physics_process(delta: float) -> void:
	if _over or _sleeping or not GameState.is_playing():
		return
	clock += delta
	if clock >= day_seconds * 1.08:  # a little past 22:00 the farmer drops off where they stand
		GameState.message("You fell asleep in the fields...")
		sleep()


func _process(_delta: float) -> void:
	var f := time_of_day()
	var c := Color(1, 1, 1)
	if f < 0.12:
		c = Color(1.0, 0.92, 0.85).lerp(Color.WHITE, f / 0.12)  # dawn
	elif f > 0.62:
		c = Color.WHITE.lerp(Color(1.0, 0.82, 0.66), clampf((f - 0.62) / 0.2, 0.0, 1.0))  # golden evening
		if f > 0.85:
			c = c.lerp(Color(0.42, 0.46, 0.72), clampf((f - 0.85) / 0.15, 0.0, 1.0))  # night
	if _tint:
		_tint.color = c
	var minutes := int(6 * 60 + f * 16 * 60)
	if _label:
		_label.text = "Day %d/%d  %02d:%02d" % [day, days, minutes / 60, (minutes % 60) / 10 * 10]


## Ends the day (the screen dips to black); the next one starts in the morning, or the season ends.
func sleep() -> void:
	if _sleeping or _over:
		return
	_sleeping = true
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_layer.add_child(shade)
	var tw := shade.create_tween()
	tw.tween_property(shade, "color:a", 1.0, 0.5)
	tw.tween_callback(next_day)
	tw.tween_interval(0.3)
	tw.tween_property(shade, "color:a", 0.0, 0.6)
	tw.tween_callback(shade.queue_free)


## Moves to the next morning (or ends the season after the last day).
func next_day() -> void:
	_sleeping = false
	if day >= days:
		_over = true
		clock = day_seconds
		season_ended.emit()
		return
	day += 1
	clock = 0.0
	for e in get_tree().get_nodes_in_group(&"farm_plot"):
		var plot := SP.component(e, &"FarmPlot") as FarmPlotComponent
		if plot:
			plot.overnight(overnight_growth)
	for e in get_tree().get_nodes_in_group(&"farm_animal"):
		var animal := SP.component(e, &"FarmAnimal") as FarmAnimalComponent
		if animal:
			animal.overnight()
	GameState.message("Day %d - good morning!" % day)
	day_started.emit(day)
