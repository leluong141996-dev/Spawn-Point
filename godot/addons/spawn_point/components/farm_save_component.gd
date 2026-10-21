class_name FarmSaveComponent
extends Node
## Keeps a farm between plays: the day and the time, the money, the basket, the tools, every plot, the animals and
## which trees and rocks are gone are written to user:// (the browser's storage on the web) each morning and every
## [member every] seconds. Opening the game again carries on where it was left; the save is deleted when the
## season is won or lost (or the player restarts with R), so the next game starts fresh. Put it on the farmer. Bots and recordings (the root's
## "sp_autopilot" mark) neither load nor save, so they always see a fresh farm and leave no save behind.

const SP_NAME := "FarmSave"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["save", "load_save", "clear", "snapshot", "path"]
const SP_CATEGORY := "core"

## Emitted after a save was loaded.
signal restored()

## Name of the save (one per game).
@export var slot: String = "farm"
## Seconds between autosaves.
@export_range(2.0, 600.0, 1.0) var every: float = 15.0

var _entity: Node2D
var _clock := 0.0
var _loaded := false


func _ready() -> void:
	_entity = get_parent() as Node2D
	GameState.game_won.connect(clear)
	GameState.game_lost.connect(clear)
	GameState.restarting.connect(clear)  # R starts the farm over
	var days := SP.component(_entity, &"FarmDays") as FarmDaysComponent
	if days:
		days.day_started.connect(func(_d: int) -> void:
			if _loaded:
				save())
	_load_later.call_deferred()


func _load_later() -> void:
	await get_tree().physics_frame  # everyone is in the tree and ready
	await get_tree().physics_frame
	if get_tree().root.has_meta(&"sp_autopilot"):
		return  # stays unloaded: no autosaves either
	load_save()
	_loaded = true


func path() -> String:
	return "user://spawnpoint_%s.json" % slot.to_lower().replace(" ", "_")


func _physics_process(delta: float) -> void:
	if not _loaded or not GameState.is_playing():
		return
	_clock += delta
	if _clock >= every:
		_clock = 0.0
		save()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST and _loaded and GameState.is_playing():
		save()


func _key(n: Node) -> String:
	var p := (n as Node2D).global_position
	return "%d,%d" % [roundi(p.x), roundi(p.y)]


## Everything worth keeping, as plain data.
func snapshot() -> Dictionary:
	var farmer := SP.component(_entity, &"Farmer") as FarmerComponent
	var days := SP.component(_entity, &"FarmDays") as FarmDaysComponent
	var plots := {}
	for e in get_tree().get_nodes_in_group(&"farm_plot"):
		plots[_key(e)] = (SP.component(e, &"FarmPlot") as FarmPlotComponent).snapshot()
	var animals := []
	for e in get_tree().get_nodes_in_group(&"farm_animal"):
		var d := (SP.component(e, &"FarmAnimal") as FarmAnimalComponent).snapshot()
		d["type"] = String(SP.core(e).entity_type) if SP.core(e) else String(e.name)
		d["x"] = (e as Node2D).global_position.x
		d["y"] = (e as Node2D).global_position.y
		animals.append(d)
	var standing := []
	for e in get_tree().get_nodes_in_group(&"gatherable"):
		standing.append(_key(e))
	var basket := {}
	if farmer:
		for c in farmer.basket:
			basket[str(c)] = farmer.basket[c]
	return {
		"version": 1, "score": GameState.score,
		"day": days.day if days else 1, "clock": days.clock if days else 0.0,
		"basket": basket, "goods": farmer.goods_basket.duplicate() if farmer else {},
		"upgrades": farmer.upgrades.keys() if farmer else [], "selected": farmer.selected if farmer else 0,
		"extra_crops": farmer.extra_crops.duplicate() if farmer else [],
		"sprinklers": _active_sprinklers(),
		"plots": plots, "animals": animals, "standing": standing,
		"x": _entity.global_position.x, "y": _entity.global_position.y,
	}


func _active_sprinklers() -> Array:
	var out := []
	for e in get_tree().get_nodes_in_group(&"sprinkler"):
		if (SP.component(e, &"Sprinkler") as SprinklerComponent).active:
			out.append(_key(e))
	return out


func save() -> void:
	var f := FileAccess.open(path(), FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(snapshot()))
		f.close()


func clear() -> void:
	if FileAccess.file_exists(path()):
		DirAccess.remove_absolute(path())


## Puts a saved farm back. Returns false when there is no save.
func load_save() -> bool:
	if not FileAccess.file_exists(path()):
		return false
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path()))
	if not (data is Dictionary) or int(data.get("version", 0)) != 1:
		return false
	var farmer := SP.component(_entity, &"Farmer") as FarmerComponent
	var days := SP.component(_entity, &"FarmDays") as FarmDaysComponent
	GameState.add_score(int(data.score) - GameState.score)
	if days:
		days.day = int(data.day)
		days.clock = float(data.clock)
	if farmer:
		farmer.basket.clear()
		for c in data.basket:
			farmer.basket[int(c)] = int(data.basket[c])
		farmer.goods_basket.clear()
		for g in data.goods:
			farmer.goods_basket[g] = int(data.goods[g])
		for k in data.upgrades:
			farmer.add_upgrade(String(k))
		for c in data.get("extra_crops", []):
			farmer.add_crop(String(c))
		farmer.select(int(data.selected))
	_entity.global_position = Vector2(float(data.x), float(data.y))
	for e in get_tree().get_nodes_in_group(&"farm_plot"):
		var saved: Variant = data.plots.get(_key(e))
		if saved is Dictionary:
			var plot := SP.component(e, &"FarmPlot") as FarmPlotComponent
			var crop := int(saved.get("crop", -1))
			var tex: Texture2D = null
			if farmer and crop >= 0 and crop < farmer.crop_list.size():
				tex = farmer.crop_list[crop].texture
			plot.restore(saved, tex, farmer.crop_list[crop].color if farmer and crop >= 0 and crop < farmer.crop_list.size() else Color.ORANGE)
	var standing := {}
	for k in data.standing:
		standing[String(k)] = true
	for e in get_tree().get_nodes_in_group(&"gatherable"):
		if not standing.has(_key(e)):
			(SP.component(e, &"Gatherable") as GatherableComponent).remove_quietly()
	var on := {}
	for k in data.get("sprinklers", []):
		on[String(k)] = true
	for e in get_tree().get_nodes_in_group(&"sprinkler"):
		if on.has(_key(e)):
			(SP.component(e, &"Sprinkler") as SprinklerComponent).activate()
	_restore_animals(data.animals)
	GameState.message("Welcome back - day %d" % (days.day if days else 1))
	restored.emit()
	return true


func _restore_animals(saved: Array) -> void:
	var holder: Node = null
	for e in get_tree().get_nodes_in_group(&"farm_animal"):
		holder = e.get_parent()
		e.queue_free()
	for d: Dictionary in saved:
		var scene_path := "res://entities/%s.tscn" % d.type
		if not ResourceLoader.exists(scene_path):
			continue
		var a := (load(scene_path) as PackedScene).instantiate() as Node2D
		a.global_position = Vector2(float(d.x), float(d.y))
		(holder if holder else get_tree().current_scene).add_child(a)
		var comp := SP.component(a, &"FarmAnimal") as FarmAnimalComponent
		if comp:
			comp.restore.call_deferred(d)
