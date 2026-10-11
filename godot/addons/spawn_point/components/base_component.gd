class_name BaseComponent
extends Node
## The base that tower-defense enemies walk to. Each enemy that reaches it is removed and costs a life;
## with no lives left the game is lost (the HUD shows the lives).

const SP_NAME := "Base"
const SP_HOSTS: Array[String] = ["Area2D"]
const SP_REQUIRES: Array[String] = []
const SP_CATEGORY := "core"

## Emitted when an enemy gets in; [param lives] is what is left.
signal breached(lives: int)

var _entity: Area2D


func _ready() -> void:
	_entity = get_parent() as Area2D
	_entity.collision_mask |= SP.LAYER_ENEMY
	_entity.body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
	if SP.team_of(body) != SP.TEAM_ENEMY or not SP.component(body, &"PathFollower"):
		return
	body.queue_free()
	FX.shake(0.4)
	if Sfx.has_sound("hurt"):
		Sfx.play("hurt")
	GameState.player_died()  # one life per enemy that gets through (loses the game at zero)
	breached.emit(GameState.lives)
