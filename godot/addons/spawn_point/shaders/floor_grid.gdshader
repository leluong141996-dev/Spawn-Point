shader_type canvas_item;

// Subtle checkerboard floor for top-down levels, in world-space tiles.
uniform float tile_size = 32.0;
uniform vec4 color_a : source_color = vec4(0.12, 0.13, 0.2, 1.0);
uniform vec4 color_b : source_color = vec4(0.14, 0.15, 0.23, 1.0);
uniform vec2 size = vec2(1024.0, 1024.0);

void fragment() {
	vec2 cell = floor(UV * size / tile_size);
	float checker = mod(cell.x + cell.y, 2.0);
	COLOR = mix(color_a, color_b, checker);
}
