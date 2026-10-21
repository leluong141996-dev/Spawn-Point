class_name ShopComponent
extends Node
## A shop stall: interact once to see the next thing for sale, again (within a few seconds) to buy it. Sells
## animals (a new hen or cow walks into the pen), a rare crop's seeds (a new slot in the hotbar) and sprinklers
## (the next [SprinklerComponent] on the farm starts working).
##
## [member offers] is a ";"-separated list of "key|Name|price"; keys: chicken, cow, seeds, sprinkler.

const SP_NAME := "Shop"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["use", "offer_list", "buy"]
const SP_CATEGORY := "core"

## Emitted after a purchase with the offer's key.
signal bought(key: String)

## What is for sale (see the class description).
@export var offers: String = "chicken|Chicken|40;cow|Cow|90;sprinkler|Sprinkler|60"
## The rare crop the "seeds" offer adds, in the farmer's crop format ("Name|#color|seconds|price|stages|icon").
@export var rare_crop: String = ""

const WHAT := {"chicken": "a hen for the pen", "cow": "a cow for the pen", "seeds": "a rare crop that sells high",
	"sprinkler": "waters the plots around it every morning"}

var offer_list: Array[Dictionary] = []
var _shown := -1
var _shown_at := -100.0
var _entity: Node2D


func _ready() -> void:
	_entity = get_parent() as Node2D
	_entity.add_to_group(&"shop")
	for entry in offers.split(";", false):
		var p := entry.strip_edges().split("|")
		if p.size() == 3:
			offer_list.append({"key": p[0], "name": p[1], "price": int(p[2])})


func _available(farmer: FarmerComponent, o: Dictionary) -> bool:
	match String(o.key):
		"seeds":
			return rare_crop != "" and not farmer.extra_crops.has(rare_crop)
		"sprinkler":
			for e in get_tree().get_nodes_in_group(&"sprinkler"):
				if not (SP.component(e, &"Sprinkler") as SprinklerComponent).active:
					return true
			return false
	return true


## One press: show the next offer, or buy the one just shown. Returns "buy" on a purchase, "browse" otherwise.
func use(farmer: FarmerComponent) -> String:
	var now := Time.get_ticks_msec() / 1000.0
	if _shown >= 0 and now - _shown_at < 4.0 and _available(farmer, offer_list[_shown]):
		var o: Dictionary = offer_list[_shown]
		if GameState.score < int(o.price):
			GameState.message("%s costs $%d - not enough money yet" % [o.name, o.price])
			_shown_at = now
			return "browse"
		GameState.add_score(-int(o.price))
		buy(farmer, String(o.key))
		GameState.message("Bought: %s!" % o.name)
		FX.burst(_entity.global_position + Vector2(0, -16), Color("#ffec27"), 14, 140.0, 0.5, 3.0, 200.0)
		bought.emit(String(o.key))
		_shown = -1
		return "buy"
	for k in offer_list.size():
		var i := (_shown + 1 + k) % offer_list.size()
		if _available(farmer, offer_list[i]):
			_shown = i
			_shown_at = now
			var o2: Dictionary = offer_list[i]
			GameState.message("%s: %s - $%d (press again to buy)" % [o2.name, WHAT.get(o2.key, ""), o2.price])
			return "browse"
	GameState.message("Sold out!")
	return ""


## Delivers [param key] (also used when a saved farm is loaded).
func buy(farmer: FarmerComponent, key: String) -> void:
	match key:
		"chicken", "cow":
			_deliver_animal("Chicken" if key == "chicken" else "Cow")
		"seeds":
			farmer.add_crop(rare_crop)
		"sprinkler":
			for e in get_tree().get_nodes_in_group(&"sprinkler"):
				var s := SP.component(e, &"Sprinkler") as SprinklerComponent
				if not s.active:
					s.activate()
					break


func _deliver_animal(entity: String) -> void:
	var path := "res://entities/%s.tscn" % entity
	if not ResourceLoader.exists(path):
		return
	var at := _entity.global_position + Vector2(0, 40)
	var holder := _entity.get_parent()
	for e in get_tree().get_nodes_in_group(&"farm_animal"):  # into the pen, next to the others
		at = (e as Node2D).global_position + Vector2(randf_range(-20, 20), randf_range(-12, 12))
		holder = e.get_parent()
		break
	var a := (load(path) as PackedScene).instantiate() as Node2D
	holder.add_child(a)
	a.global_position = at
	FX.burst(at, Color("#fff1a8"), 10, 90.0, 0.4, 2.5, 200.0)
