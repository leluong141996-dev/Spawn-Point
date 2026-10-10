class_name ExperienceComponent
extends Node
## Experience points and levels (survivor-style games). XP comes from [XpOrbComponent] pickups or
## [method add_xp]; every level needs [member growth] times more XP than the one before. Pair with
## [LevelUpMenuComponent] to let the player pick an upgrade on each level.

const SP_NAME := "Experience"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["xp", "level", "xp_to_next"]
const SP_CATEGORY := "core"

## Emitted after gaining XP; [param amount] is what was added.
signal gained(amount: int)
## Emitted once per level reached.
signal leveled_up(level: int)

## XP needed for level 2.
@export_range(1, 100000) var first_level_xp: int = 5
## Each level needs this many times the XP of the previous one.
@export_range(1.0, 3.0, 0.01) var growth: float = 1.35
## XP orbs within this distance (px) fly to the entity.
@export_range(0.0, 2000.0, 1.0) var magnet_radius: float = 90.0
## Score added per XP point (0 = XP does not count as score).
@export_range(0, 1000) var score_per_xp: int = 1

var xp := 0
var level := 1
var xp_to_next := 5


func _ready() -> void:
	xp_to_next = first_level_xp


## Adds XP and levels up as many times as it covers.
func add_xp(amount: int) -> void:
	if amount <= 0:
		return
	xp += amount
	gained.emit(amount)
	if score_per_xp > 0:
		GameState.add_score(amount * score_per_xp)
	while xp >= xp_to_next:
		xp -= xp_to_next
		level += 1
		xp_to_next = maxi(xp_to_next + 1, int(round(xp_to_next * growth)))
		leveled_up.emit(level)


## Progress toward the next level, 0..1.
func progress() -> float:
	return clampf(float(xp) / float(maxi(xp_to_next, 1)), 0.0, 1.0)
