class_name FarmDaysComponent
extends Node
## A farming season of [member days] days. Each day runs from 6:00 to 22:00 in [member day_seconds]; the light
## warms in the evening and goes dark at night. Sleeping (a [SleepSpotComponent] bed) ends the day early; at
## midnight the farmer drops off anyway. Overnight, watered crops grow and fed animals get their product ready.
## After the last day the season ends ([signal season_ended]).

const SP_NAME := "FarmDays"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["sleep", "next_day", "day", "clock", "time_of_day", "weather", "weather_for"]
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
## Chance that a day (after the first) is rainy: rain waters every crop all day.
@export_range(0.0, 1.0, 0.05) var rain_chance: float = 0.3
## Snow instead of rain (winter farms): it looks lovely and waters nothing.
@export var snow: bool = false
## Seeds the weather, so a farm has the same weather every time it is played.
@export var weather_seed: int = 0

var day := 1
var clock := 0.0  # seconds into the day
var weather := "sunny"  # "sunny", "rain" or "snow"
var _sky: Node2D
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
	_sky = Node2D.new()
	_sky.name = "Weather"
	_sky.draw.connect(_draw_weather)
	var sky_layer := CanvasLayer.new()
	sky_layer.layer = 5
	sky_layer.add_child(_sky)
	add_child.call_deferred(sky_layer)
	weather = weather_for(day)
	(func() -> void: day_started.emit(day)).call_deferred()


## The weather of day [param d]: the first day is always sunny.
func weather_for(d: int) -> String:
	if d <= 1:
		return "sunny"
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(weather_seed * 131 + d)
	if rng.randf() >= rain_chance:
		return "sunny"
	return "snow" if snow else "rain"


## Fraction of the day gone, 0 at 6:00 and 1 at 22:00.
func time_of_day() -> float:
	return clampf(clock / day_seconds, 0.0, 1.0)


func _physics_process(delta: float) -> void:
	if _over or _sleeping or not GameState.is_playing():
		return
	clock += delta
	if weather == "rain":  # the rain keeps every crop watered
		for e in get_tree().get_nodes_in_group(&"farm_plot"):
			var plot := SP.component(e, &"FarmPlot") as FarmPlotComponent
			if plot and plot.has_crop():
				plot.rain()
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
	if weather == "rain":
		c = c * Color(0.78, 0.82, 0.92)
	elif weather == "snow":
		c = c * Color(0.92, 0.94, 1.0)
	if _tint:
		_tint.color = c
	if _sky and weather != "sunny":
		_sky.queue_redraw()
	var minutes := int(6 * 60 + f * 16 * 60)
	if _label:
		var w := {"rain": "  Rain", "snow": "  Snow"}.get(weather, "")
		_label.text = "Day %d/%d  %02d:%02d%s" % [day, days, minutes / 60, (minutes % 60) / 10 * 10, w]


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
	weather = weather_for(day)
	match weather:
		"rain":
			GameState.message("Day %d - rain today: the crops water themselves" % day)
		"snow":
			GameState.message("Day %d - it's snowing!" % day)
		_:
			GameState.message("Day %d - good morning!" % day)
	day_started.emit(day)


func _draw_weather() -> void:
	if weather == "sunny":
		return
	var vp := _sky.get_viewport_rect().size
	var t := Time.get_ticks_msec() / 1000.0
	if weather == "rain":
		for i in 90:
			var x := fmod(i * 97.0 + t * 120.0, vp.x + 40.0) - 20.0
			var y := fmod(i * 61.0 + t * 520.0, vp.y + 40.0) - 20.0
			_sky.draw_line(Vector2(x, y), Vector2(x - 4, y + 12), Color(0.75, 0.85, 1.0, 0.55), 1.5)
	else:
		for i in 70:
			var x := fmod(i * 83.0 + sin(t + i) * 20.0 + t * 15.0, vp.x)
			var y := fmod(i * 47.0 + t * 45.0, vp.y)
			_sky.draw_rect(Rect2(x, y, 3, 3), Color(1, 1, 1, 0.8))
