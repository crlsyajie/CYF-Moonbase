"""Render the seamless Mars sand texture the website lays under the base.

Run: Blender --background --factory-startup --python blender/mars_ground.py
Writes models/mars_ground.jpg (1024 x 1024). Every noise is fed (cos u, sin u, cos v, sin v), so the image tiles.
"""
import math
import os

import bpy

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "mars_ground.jpg")
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
m = bpy.data.materials.new("mars")
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


patches = torus_noise(0.55, 3, 0.5, 0.0)       # broad light and dark dust fields
grain = torus_noise(6.0, 8, 0.65, 7.0)         # fine grit
warp = torus_noise(1.2, 4, 0.5, 13.0)          # bends the ripples

# wind ripples: integer frequencies keep them periodic, the warp keeps them from looking ruled
phase = math_node("ADD", math_node("ADD", math_node("MULTIPLY", u, TAU * 22), math_node("MULTIPLY", v, TAU * 8)), math_node("MULTIPLY", warp, 16.0))
ripple = math_node("POWER", math_node("MULTIPLY", math_node("ADD", math_node("SINE", phase), 1.0), 0.5), 3.0)

# two faint tyre tracks that wander across and wrap
def track(freq_v, amp, offset):
    centre = math_node("ADD", math_node("MULTIPLY", math_node("SINE", math_node("ADD", math_node("MULTIPLY", v, TAU * freq_v), offset)), amp), 0.5 + offset * 0.05)
    d = math_node("ABSOLUTE", math_node("SUBTRACT", u, centre))
    ruts = math_node("ADD", math_node("LESS_THAN", math_node("ABSOLUTE", math_node("SUBTRACT", d, 0.009)), 0.0025), 0)
    return ruts


tracks = track(1, 0.07, 0.0)

ramp = N.new("ShaderNodeValToRGB")
cr = ramp.color_ramp
cr.elements[0].position, cr.elements[0].color = 0.25, (0.33, 0.035, 0.016, 1)
cr.elements[1].position, cr.elements[1].color = 0.78, (0.78, 0.13, 0.055, 1)
mid = cr.elements.new(0.52)
mid.color = (0.58, 0.075, 0.032, 1)
shade = math_node("ADD", math_node("MULTIPLY", patches, 0.8), math_node("MULTIPLY", grain, 0.25))
shade = math_node("ADD", shade, math_node("MULTIPLY", ripple, 0.05))
shade = math_node("SUBTRACT", shade, math_node("MULTIPLY", tracks, 0.08))
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
