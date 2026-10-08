class_name SPEntityCore
extends Node
## Core of every Spawn Point entity (always the child named "Entity").
##
## Registers the entity with [World], handles default death behaviour (players lose a life and
## respawn, everything else is removed) and kills entities that fall out of the level.

signal respawned

## Entity type name from the game graph ("Player", "Slime", ...).
@export var entity_type := ""
## "player", "enemy" or "neutral".
@export var team := SP.TEAM_NEUTRAL
## True for the entity controlled by the player.
@export var is_player := false
## Seconds before a dead player respawns.
@export var respawn_delay := 0.9

var spawn_position := Vector2.ZERO
var dead := false
## Why the entity last died: "fall", the attacking entity's type (e.g. "Spikes"), or "unknown".
## Empty while alive.
var death_cause := ""


func _enter_tree() -> void:
	var e := get_parent()
	e.add_to_group(SP.ENTITY_GROUP)
	if entity_type != "":
		e.add_to_group(StringName(entity_type))
	if e.has_meta(&"sp_team"):
		team = String(e.get_meta(&"sp_team"))
	e.add_to_group(StringName("team_" + team))
	if is_player:
		e.add_to_group(SP.PLAYER_GROUP)


func _ready() -> void:
	var e := get_parent() as Node2D
	spawn_position = e.global_position
	var health := SP.component(e, &"Health") as HealthComponent
	if health:
		health.died.connect(_on_died)
	World.register_entity(e)


func _physics_process(_delta: float) -> void:
	var e := get_parent() as Node2D
	if not dead and e.global_position.y > World.kill_y:
		death_cause = "fall"
		var health := SP.component(e, &"Health") as HealthComponent
		if health:
			health.kill()
		else:
			_on_died()


func _on_died() -> void:
	if dead:
		return
	dead = true
	var e := get_parent() as Node2D
	if death_cause == "":
		death_cause = _attacker_type(e)
	if not is_player:
		e.queue_free.call_deferred()
		return
	e.visible = false
	e.set_deferred(&"process_mode", Node.PROCESS_MODE_DISABLED)
	if GameState.player_died():
		get_tree().create_timer(respawn_delay).timeout.connect(_respawn)


func _respawn() -> void:
	var e := get_parent() as Node2D
	if not is_instance_valid(e):
		return
	e.global_position = spawn_position
	if e is CharacterBody2D:
		(e as CharacterBody2D).velocity = Vector2.ZERO
	var health := SP.component(e, &"Health") as HealthComponent
	if health:
		health.reset()
		health.grant_invincibility(1.5)
	dead = false
	death_cause = ""
	e.visible = true
	e.process_mode = Node.PROCESS_MODE_INHERIT
	respawned.emit()


func _attacker_type(e: Node) -> String:
	var hb := SP.component(e, &"Hurtbox") as HurtboxComponent
	if hb and is_instance_valid(hb.last_hit_by):
		var c := SP.core(hb.last_hit_by)
		if c and c.entity_type != "":
			return c.entity_type
	return "unknown"
