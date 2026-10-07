class_name SP
## Static helpers shared by every Spawn Point component.
##
## Conventions:
## - An entity is a physics body (CharacterBody2D / StaticBody2D / Area2D) whose direct child
##   named "Entity" is an [SPEntityCore].
## - Components are direct children of the entity, named by their short name ("Health", ...).

# Physics layer bits (1-based layer N == bit 1 << (N - 1)).
const LAYER_WORLD := 1 << 0
const LAYER_PLAYER := 1 << 1
const LAYER_ENEMY := 1 << 2
const LAYER_PLAYER_HURTBOX := 1 << 3
const LAYER_ENEMY_HURTBOX := 1 << 4
const LAYER_PICKUP := 1 << 5

const TEAM_PLAYER := "player"
const TEAM_ENEMY := "enemy"
const TEAM_NEUTRAL := "neutral"

const ENTITY_GROUP := &"sp_entity"
const PLAYER_GROUP := &"player"


## Returns the entity root owning [param node] (or [param node] itself), or null.
static func entity_of(node: Node) -> Node:
	var n := node
	while n != null:
		if n.is_in_group(ENTITY_GROUP) or n.has_node(^"Entity"):
			return n
		n = n.get_parent()
	return null


## Returns the entity's core node, or null.
static func core(entity: Node) -> SPEntityCore:
	if entity == null:
		return null
	return entity.get_node_or_null(^"Entity") as SPEntityCore


## Returns the component named [param short_name] on [param entity], or null.
static func component(entity: Node, short_name: StringName) -> Node:
	if entity == null:
		return null
	return entity.get_node_or_null(NodePath(String(short_name)))


## Returns the movement component (platformer or top-down) of [param entity], or null.
static func movement(entity: Node) -> Node:
	var m := component(entity, &"PlatformerMovement")
	if m == null:
		m = component(entity, &"TopDownMovement")
	return m


## Team of [param entity]: "player", "enemy" or "neutral".
static func team_of(entity: Node) -> String:
	if entity == null:
		return TEAM_NEUTRAL
	if entity.has_meta(&"sp_team"):
		return String(entity.get_meta(&"sp_team"))
	var c := core(entity)
	return c.team if c else TEAM_NEUTRAL


## Hurtbox layer bit for a team.
static func hurtbox_layer(team: String) -> int:
	match team:
		TEAM_PLAYER:
			return LAYER_PLAYER_HURTBOX
		TEAM_ENEMY:
			return LAYER_ENEMY_HURTBOX
	return 0


## Layer bits of hurtboxes that a hitbox of [param team] should damage.
static func opposing_hurtbox_mask(team: String) -> int:
	match team:
		TEAM_PLAYER:
			return LAYER_ENEMY_HURTBOX
		TEAM_ENEMY:
			return LAYER_PLAYER_HURTBOX
	return LAYER_PLAYER_HURTBOX | LAYER_ENEMY_HURTBOX


## Half extents of the entity's main collision shape (falls back to 16x16).
static func half_size(entity: Node) -> Vector2:
	var cs := entity.get_node_or_null(^"CollisionShape2D") as CollisionShape2D
	if cs and cs.shape:
		return cs.shape.get_rect().size * 0.5
	return Vector2(8, 8)


## Base color of the entity's placeholder visual (white if none).
static func color_of(entity: Node) -> Color:
	var shape := entity.get_node_or_null(^"Visual/Shape") as Polygon2D
	return shape.color if shape else Color.WHITE
