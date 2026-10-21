class_name ToolBenchComponent
extends Node
## A workbench that sells tool upgrades to a [FarmerComponent]. Interact once to see the next upgrade and its
## price, again (within a few seconds) to buy it; interacting after that shows the next one.
##
## [member offers] is a ";"-separated list of "key|Name|price": keys are can (waters a 3x3 patch), hoe (tills a
## 3x3 patch), basket (8 more room), axe (two hits a swing) and rod (fish stay on the hook longer).

const SP_NAME := "ToolBench"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["use", "offer_list", "next_offer"]
const SP_CATEGORY := "core"

## Emitted after a purchase with the upgrade's key.
signal bought(key: String)

## Upgrades for sale (see the class description).
@export var offers: String = "can|Watering can|40;hoe|Hoe|30;basket|Big basket|25;axe|Axe|35;rod|Fishing rod|25"

const WHAT := {"can": "waters 9 plots at once", "hoe": "tills 9 plots at once", "basket": "8 more room",
	"axe": "chops twice as fast", "rod": "fish stay on the hook longer"}

var offer_list: Array[Dictionary] = []
var _shown := -1
var _shown_at := -100.0
var _entity: Node2D


func _ready() -> void:
	_entity = get_parent() as Node2D
	_entity.add_to_group(&"tool_bench")
	for entry in offers.split(";", false):
		var p := entry.strip_edges().split("|")
		if p.size() == 3:
			offer_list.append({"key": p[0], "name": p[1], "price": int(p[2])})


## The first upgrade [param farmer] does not have yet (index into offer_list), or -1.
func next_offer(farmer: FarmerComponent, after := -1) -> int:
	for k in offer_list.size():
		var i := (after + 1 + k) % offer_list.size()
		if not farmer.has_upgrade(String(offer_list[i].key)):
			return i
	return -1


## One press: show the next upgrade, or buy the one just shown. Returns "upgrade" on a purchase, "browse" otherwise
## ("" when everything is bought).
func use(farmer: FarmerComponent) -> String:
	var now := Time.get_ticks_msec() / 1000.0
	if _shown >= 0 and now - _shown_at < 4.0 and not farmer.has_upgrade(String(offer_list[_shown].key)):
		var o: Dictionary = offer_list[_shown]
		if GameState.score < int(o.price):
			GameState.message("%s costs $%d - not enough money yet" % [o.name, o.price])
			_shown_at = now
			return "browse"
		GameState.add_score(-int(o.price))
		farmer.add_upgrade(String(o.key))
		GameState.message("%s upgraded: %s!" % [o.name, WHAT.get(o.key, "")])
		FX.burst(_entity.global_position + Vector2(0, -12), Color("#ffec27"), 14, 140.0, 0.5, 3.0, 200.0)
		bought.emit(String(o.key))
		_shown = -1
		return "upgrade"
	var i := next_offer(farmer, _shown)
	if i < 0:
		GameState.message("Your tools are the best there are")
		return ""
	_shown = i
	_shown_at = now
	var o2: Dictionary = offer_list[i]
	GameState.message("%s: %s - $%d (press again to buy)" % [o2.name, WHAT.get(o2.key, ""), o2.price])
	return "browse"
