class_name ShmupShipComponent
extends Node
## The player's ship in a side-scrolling shooter. It fires on its own toward the right, grows stronger with every
## power-up (more shots, a wider spread, a faster rate) and loses a level of power when it is hit.

const SP_NAME := "ShmupShip"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = ["Weapon", "TopDownMovement"]
const SP_INTERNAL: Array[String] = ["set_power"]
const SP_CATEGORY := "controller"

## Emitted when the power level changes.
signal powered(level: int)

## Highest power level.
@export_range(1, 6) var max_power: int = 4
## Fire without holding the button.
@export var auto_fire := true

## Current power level (1 = a single shot).
var power := 1

var _entity: Node2D
var _weapon: WeaponComponent
var _base_rate := 6.0


func _ready() -> void:
	process_physics_priority = -5  # after PlayerInput (-10), which resets the trigger, and before the Weapon (0) reads it
	_entity = SP.entity_of(get_parent()) as Node2D
	_weapon = SP.component(_entity, &"Weapon") as WeaponComponent
	_base_rate = _weapon.fire_rate
	var juice := SP.component(_entity, &"Juice")
	if juice:
		juice.set(&"face_movement", false)  # the ship always points right, whichever way it flies
	var health := SP.component(_entity, &"Health") as HealthComponent
	if health:
		health.damaged.connect(func(_a: int) -> void: set_power(power - 1))
	set_power(1)


func _physics_process(_delta: float) -> void:
	_weapon.aim_direction = Vector2.RIGHT
	if auto_fire:
		_weapon.trigger_held = GameState.is_playing()


## One level stronger (a rule calls this when a power-up is collected).
func power_up() -> void:
	if power < max_power:
		set_power(power + 1)
		GameState.message("POWER %d" % power)
	else:
		GameState.add_score(25)  # a full ship turns spare power into points


func set_power(level: int) -> void:
	var l := clampi(level, 1, max_power)
	var changed := l != power
	power = l
	_weapon.projectile_count = 1 if l == 1 else (2 if l == 2 else 3)
	_weapon.spread_deg = 2.0 if l == 1 else (8.0 if l == 2 else 20.0)
	_weapon.fire_rate = _base_rate * (1.0 + 0.18 * (l - 1))
	if changed:
		powered.emit(l)
