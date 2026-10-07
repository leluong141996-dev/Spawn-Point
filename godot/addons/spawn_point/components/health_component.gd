class_name HealthComponent
extends Node
## Hit points with brief invincibility after each hit.
## When health reaches zero the entity dies (players respawn while lives remain).

const SP_NAME := "Health"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "core"

## Emitted after taking damage that was not blocked.
signal damaged(amount: int)
## Emitted after healing.
signal healed(amount: int)
## Emitted once when health reaches zero.
signal died

## Maximum (and starting) hit points.
@export_range(1, 999) var max_health: int = 3
## Seconds of invincibility after being hit (prevents instant multi-hits).
@export_range(0.0, 5.0, 0.01) var invincibility_time: float = 0.6

var current: int
var _invincible_left := 0.0


func _ready() -> void:
	current = max_health


func _physics_process(delta: float) -> void:
	if _invincible_left > 0.0:
		_invincible_left -= delta


## Deals [param amount] damage unless invincible or dead.
func damage(amount: int) -> void:
	if amount <= 0 or is_dead() or is_invincible():
		return
	current = maxi(current - amount, 0)
	_invincible_left = invincibility_time
	damaged.emit(amount)
	if current == 0:
		died.emit()


## Restores up to [param amount] hit points.
func heal(amount: int) -> void:
	if amount <= 0 or is_dead():
		return
	var before := current
	current = mini(current + amount, max_health)
	if current > before:
		healed.emit(current - before)


## Kills the entity immediately, ignoring invincibility.
func kill() -> void:
	if is_dead():
		return
	current = 0
	died.emit()


## Restores full health.
func reset() -> void:
	current = max_health
	_invincible_left = 0.0


## Makes the entity invincible for [param seconds].
func grant_invincibility(seconds: float) -> void:
	_invincible_left = maxf(_invincible_left, seconds)


## True while hits are ignored.
func is_invincible() -> bool:
	return _invincible_left > 0.0


## True when health is zero.
func is_dead() -> bool:
	return current <= 0
