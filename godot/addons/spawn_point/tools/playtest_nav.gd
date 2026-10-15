extends RefCounted
## Grid navigation for playtest bots, built from the level's TileMapLayer.
## Platformer: graph of standable cells linked by walks, drops and jumps within the player's jump
## reach. Top-down: 4-neighbour grid of free cells. Both use BFS (levels are small).

const DOWN := Vector2i(0, 1)

var platformer := true
var ts := 32.0
var cells := {}  # Vector2i -> 1 solid, 2 one-way
var hazards := {}  # Vector2i -> true: static damaging entities (spikes) — never stand there
var rect := Rect2i()
var ph := 1  # player height in tiles
var up := 3
var across := 4


func setup(tiles: TileMapLayer, tile_size: float, is_platformer: bool, player_h: float, jump_up: int, jump_across: int) -> void:
	ts = tile_size
	platformer = is_platformer
	ph = maxi(1, ceili(player_h / ts))
	up = jump_up
	across = jump_across
	rect = tiles.get_used_rect()
	for c in tiles.get_used_cells():
		var td := tiles.get_cell_tile_data(c)  # one-way planks are known by their collision, not their atlas slot
		var one_way := td != null and td.get_collision_polygons_count(0) > 0 and td.is_collision_polygon_one_way(0, 0)
		cells[c] = 2 if one_way else 1


func blocked(c: Vector2i) -> bool:
	return cells.get(c, 0) == 1


func floor_at(c: Vector2i) -> bool:
	return cells.has(c)


func inside(c: Vector2i) -> bool:
	return c.x >= rect.position.x and c.x < rect.end.x and c.y >= rect.position.y - 4 and c.y < rect.end.y


func standable(c: Vector2i) -> bool:
	if not inside(c) or not floor_at(c + DOWN) or hazards.has(c):
		return false
	for k in ph:
		if blocked(c - Vector2i(0, k)):
			return false
	return true


func open_cell(c: Vector2i) -> bool:
	return inside(c) and not blocked(c) and (platformer or not hazards.has(c))


func mark_hazard(pos: Vector2) -> void:
	hazards[Vector2i(floori(pos.x / ts), floori(pos.y / ts))] = true


## Cell containing the feet (platformer) or the center (top-down) of a body.
func cell_of(pos: Vector2, half_h: float) -> Vector2i:
	if platformer:
		return Vector2i(floori(pos.x / ts), floori((pos.y + half_h - 2.0) / ts))
	return Vector2i(floori(pos.x / ts), floori(pos.y / ts))


func center(c: Vector2i) -> Vector2:
	return Vector2((c.x + 0.5) * ts, (c.y + 0.5) * ts)


func _drop(c: Vector2i) -> Vector2i:
	var d := c
	while inside(d) and not standable(d):
		if blocked(d):
			return Vector2i(-99999, 0)
		d += DOWN
	return d if inside(d) else Vector2i(-99999, 0)


func neighbors(c: Vector2i) -> Array[Vector2i]:
	var out: Array[Vector2i] = []
	if not platformer:
		for d in [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN]:
			if open_cell(c + d):
				out.append(c + d)
		return out
	for dx in [-1, 1]:
		var side := c + Vector2i(dx, 0)
		if standable(side):
			out.append(side)
		elif open_cell(side):
			var land := _drop(side)
			if land.x != -99999:
				out.append(land)
	for dx in range(-across, across + 1):
		for dy in range(-up, up + 3):
			if absi(dx) <= 1 and dy == 0:
				continue
			var t := c + Vector2i(dx, dy)
			if dy > 0 and absi(dx) > across - 1 + dy:
				continue
			if standable(t) and not blocked(c - Vector2i(0, ph)):
				out.append(t)
	return out


## Cheapest path (Dijkstra) from `from` to the first cell satisfying `goal`; walking is cheap,
## jumps cost more the longer they are, so bots move like people instead of leaping everywhere.
## Returns the path (both ends included) or [].
func path(from: Vector2i, goal: Callable, max_nodes := 6000) -> Array[Vector2i]:
	var prev := {from: from}
	var cost := {from: 0.0}
	var frontier: Array = [[0.0, from]]  # sorted by cost
	var done := {}
	var expanded := 0
	while not frontier.is_empty() and expanded < max_nodes:
		var item: Array = frontier.pop_front()
		var c: Vector2i = item[1]
		if done.has(c):
			continue
		done[c] = true
		expanded += 1
		if goal.call(c):
			var out: Array[Vector2i] = [c]
			while c != from:
				c = prev[c]
				out.push_front(c)
			return out
		for n in neighbors(c):
			var d: Vector2i = n - c
			var step := 1.0
			if platformer and (absi(d.x) > 1 or d.y < 0):
				step = 2.0 + absi(d.x) * 0.6 + maxi(0, -d.y) * 0.5
			elif d.y > 0:
				step = 1.0 + d.y * 0.2
			var nc: float = cost[c] + step
			if nc < cost.get(n, INF):
				cost[n] = nc
				prev[n] = c
				var i := frontier.bsearch_custom([nc, n], func(a: Array, b: Array) -> bool: return a[0] < b[0])
				frontier.insert(i, [nc, n])
	return []


## Goal predicate: a stand cell from which a target at `pos` can be touched.
func reaches(pos: Vector2) -> Callable:
	var tc := Vector2i(floori(pos.x / ts), floori(pos.y / ts))
	if not platformer:
		return func(c: Vector2i) -> bool: return absi(c.x - tc.x) <= 1 and absi(c.y - tc.y) <= 1
	# Pickups floating over gaps are grabbed mid-jump, so the horizontal reach grows with height.
	var reach_x := 1 if tc.y >= rect.end.y - 3 else maxi(1, across / 2)
	return func(c: Vector2i) -> bool:
		var dx := absi(c.x - tc.x)
		return (dx <= 1 or (dx <= reach_x and tc.y < c.y)) and tc.y <= c.y + 1 and tc.y > c.y - up - ph
