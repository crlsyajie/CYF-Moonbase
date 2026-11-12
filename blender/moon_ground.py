"""Render the seamless Moon regolith texture the website lays under the base.

Run: Blender --background --factory-startup --python blender/moon_ground.py
Writes models/moon_ground.jpg (1024 x 1024). Every noise is fed (cos u, sin u, cos v, sin v), so the image tiles.
"""
import math
import os

import bpy

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "moon_ground.jpg")
TAU = 2 * math.pi

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 4
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x = sc.render.resolution_y = 1024
sc.render.image_settings.file_format = "JPEG"
sc.render.image_settings.quality = 88
sc.render.filepath = OUT

bpy.ops.mesh.primitive_plane_add(size=2)
plane = bpy.context.active_object
m = bpy.data.materials.new("moon")
m.use_nodes = True
nt = m.node_tree
N, L = nt.nodes, nt.links
N.clear()


def node(kind, **inputs):
    n = N.new(kind)
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def math_node(op, a, b=None, value=None):
    n = N.new("ShaderNodeMath")
    n.operation = op
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            L.new(x, n.inputs[i])
    return n.outputs[0]


uv = N.new("ShaderNodeTexCoord").outputs["UV"]
sep = N.new("ShaderNodeSeparateXYZ")
L.new(uv, sep.inputs[0])
u, v = sep.outputs[0], sep.outputs[1]
cu, su = math_node("COSINE", math_node("MULTIPLY", u, TAU)), math_node("SINE", math_node("MULTIPLY", u, TAU))
cv, sv = math_node("COSINE", math_node("MULTIPLY", v, TAU)), math_node("SINE", math_node("MULTIPLY", v, TAU))


def torus_noise(scale, detail, rough, seed):
    """4D noise sampled on a torus, so it wraps in both directions."""
    comb = N.new("ShaderNodeCombineXYZ")
    for i, s in enumerate((cu, su, cv)):
        L.new(s, comb.inputs[i])
    n = N.new("ShaderNodeTexNoise")
    n.noise_dimensions = "4D"
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    L.new(comb.outputs[0], n.inputs["Vector"])
    L.new(math_node("ADD", sv, seed), n.inputs["W"])
    return n.outputs["Fac"]




def torus_voronoi(scale, seed):
    """4D Voronoi on the same torus: (distance to the cell centre, a random number per cell)."""
    comb = N.new("ShaderNodeCombineXYZ")
    for i, s in enumerate((cu, su, cv)):
        L.new(s, comb.inputs[i])
    n = N.new("ShaderNodeTexVoronoi")
    n.voronoi_dimensions = "4D"
    n.inputs["Scale"].default_value = scale
    L.new(comb.outputs[0], n.inputs["Vector"])
    L.new(math_node("ADD", sv, seed), n.inputs["W"])
    rnd = N.new("ShaderNodeSeparateColor")
    L.new(n.outputs["Color"], rnd.inputs[0])
    return n.outputs["Distance"], rnd.outputs[0]


patches = torus_noise(0.55, 3, 0.5, 0.0)       # broad light and dark dust fields (maria and highlands)
grain = torus_noise(7.0, 9, 0.7, 7.0)          # fine regolith grit
mottle = torus_noise(2.2, 5, 0.6, 13.0)        # mid-size blotches


def craters(scale, seed, share, size):
    """Small impact craters: a bright rim and a dark bowl in some of the Voronoi cells."""
    d, rnd = torus_voronoi(scale, seed)
    on = math_node("LESS_THAN", rnd, share)
    rim = math_node("LESS_THAN", math_node("ABSOLUTE", math_node("SUBTRACT", d, size)), size * 0.22)
    bowl = math_node("LESS_THAN", d, size * 0.8)
    return math_node("MULTIPLY", on, math_node("SUBTRACT", math_node("MULTIPLY", rim, 0.16), math_node("MULTIPLY", bowl, 0.12)))


pits = math_node("ADD", craters(2.2, 3.0, 0.45, 0.2), craters(5.5, 21.0, 0.4, 0.17))

ramp = N.new("ShaderNodeValToRGB")
cr = ramp.color_ramp
cr.elements[0].position, cr.elements[0].color = 0.2, (0.045, 0.047, 0.055, 1)
cr.elements[1].position, cr.elements[1].color = 0.85, (0.36, 0.37, 0.4, 1)
mid = cr.elements.new(0.5)
mid.color = (0.16, 0.165, 0.185, 1)
shade = math_node("ADD", math_node("MULTIPLY", patches, 0.55), math_node("MULTIPLY", grain, 0.3))
shade = math_node("ADD", shade, math_node("MULTIPLY", mottle, 0.25))
shade = math_node("ADD", shade, pits)
L.new(shade, ramp.inputs["Fac"])
emit = node("ShaderNodeEmission", Strength=1.0)
L.new(ramp.outputs["Color"], emit.inputs["Color"])
out = N.new("ShaderNodeOutputMaterial")
L.new(emit.outputs[0], out.inputs["Surface"])
plane.data.materials.append(m)

bpy.ops.object.camera_add(location=(0, 0, 5))
cam = bpy.context.active_object
cam.data.type = "ORTHO"
cam.data.ortho_scale = 2
sc.camera = cam
bpy.ops.render.render(write_still=True)
print("rendered", OUT)
