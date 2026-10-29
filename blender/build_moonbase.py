"""Moonbase buildings, modelled in Blender and exported as GLB for the website.

Style follows the reference outpost kit: cream walls with a teal stripe and darker base band, curved rust-orange
roofs, round towers with disk caps and finials, arched wooden doors, glowing cyan windows, pipes, barrels and crates.

Run headless (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python blender/build_moonbase.py

Coordinates: Blender is Z-up and the front of each building faces -Y. The glTF exporter turns that into Y-up with the
front facing +Z, which is the side that faces the factory/road on the website. Units match the website (1 = 1 unit).
"""
import math
import os

import bmesh
import bpy

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")


# ---------------------------------------------------------------- materials
def lin(hexstr):
    h = hexstr.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)) + (1.0,)


MATS = {}


def mat(name, hexstr, rough=0.75, metal=0.0, glow=0.0):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(hexstr)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if glow:
        b.inputs["Emission Color"].default_value = lin(hexstr)
        b.inputs["Emission Strength"].default_value = glow
    MATS[name] = m
    return m


def palette():
    return dict(
        wall=mat("wall", "#ecd3c0"), trim=mat("trim", "#cfa78e"), band=mat("band", "#b98c73"),
        teal=mat("teal", "#5d8d94"), roof=mat("roof", "#c98266", 0.6), roof_dark=mat("roof_dark", "#9a5a44", 0.6),
        grey=mat("grey", "#6d7178", 0.6), grey_dark=mat("grey_dark", "#4a4e55", 0.6), dark=mat("dark", "#2a2d33", 0.5),
        glow=mat("glow", "#6fd8ff", 0.4, glow=3.0), wood=mat("wood", "#c8722e", 0.8), wood_dark=mat("wood_dark", "#8a4a1c", 0.8),
        metal=mat("metal", "#9aa0a8", 0.35, 0.6), red=mat("red", "#c0392b", 0.5), crate=mat("crate", "#c49a5c", 0.85),
        fruit=mat("fruit", "#e3a83a", 0.7), leaf=mat("leaf", "#7fb84a", 0.8),
    )


# ---------------------------------------------------------------- primitives
OBJS = []


def _finish(o, m, bevel):
    o.data.materials.append(m)
    if bevel:
        mod = o.modifiers.new("bevel", "BEVEL")
        mod.width, mod.segments, mod.limit_method = bevel, 3, "ANGLE"
    for p in o.data.polygons:
        p.use_smooth = True
    OBJS.append(o)
    return o


def box(size, loc, m, bevel=0.12, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    return _finish(o, m, min(bevel, min(size) / 2.2))


def cyl(r, h, loc, m, r2=None, verts=32, bevel=0.06, rot=(0, 0, 0)):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(radius1=r, radius2=r2, depth=h, vertices=verts, location=loc, rotation=rot)
    return _finish(bpy.context.active_object, m, min(bevel, h / 2.2))


def sphere(r, loc, m, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=24, ring_count=12)
    o = bpy.context.active_object
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    return _finish(o, m, 0)


def ring(r, minor, loc, m, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=minor, location=loc, rotation=rot, major_segments=48, minor_segments=10)
    return _finish(bpy.context.active_object, m, 0)


def curved_roof(w, d, thick, sag, loc, m, axis="x", rot_z=0.0):
    """A thick slab whose ends droop: the rounded overhanging roofs of the reference kit."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    o = bpy.context.active_object
    o.scale = (w, d, thick)
    bpy.ops.object.transform_apply(scale=True)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    edges = [e for e in bm.edges if abs((e.verts[0].co - e.verts[1].co).x if axis == "x" else (e.verts[0].co - e.verts[1].co).y) > 1e-4]
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=16, use_grid_fill=True)
    half = (w if axis == "x" else d) / 2
    for v in bm.verts:
        t = (v.co.x if axis == "x" else v.co.y) / half
        v.co.z -= sag * t * t
    bm.to_mesh(o.data)
    bm.free()
    o.location = loc
    o.rotation_euler = (0, 0, rot_z)
    return _finish(o, m, min(0.12, thick / 2.2))


def arch_door(x, y, z0, w, h, P, frame="trim"):
    """An arched wooden door with planks, set into the wall plane at y (front faces -y)."""
    box((w + 0.5, 0.3, h + 0.3), (x, y - 0.02, z0 + (h + 0.3) / 2), P[frame], 0.08)
    cyl((w + 0.5) / 2, 0.3, (x, y - 0.02, z0 + h + 0.3), P[frame], rot=(math.pi / 2, 0, 0))
    box((w, 0.34, h), (x, y - 0.06, z0 + h / 2), P["wood"], 0.05)
    cyl(w / 2, 0.34, (x, y - 0.06, z0 + h), P["wood"], rot=(math.pi / 2, 0, 0))
    for i in range(1, 4):
        box((0.06, 0.36, h * 0.9), (x - w / 2 + i * w / 4, y - 0.08, z0 + h * 0.48), P["wood_dark"], 0.01)


def porthole(x, y, z, r, P, facing="front"):
    rot = (math.pi / 2, 0, 0) if facing == "front" else (0, math.pi / 2, 0)
    off = (0, -0.05, 0) if facing == "front" else (0.05 if x > 0 else -0.05, 0, 0)
    cyl(r + 0.14, 0.2, (x, y, z), P["trim"], rot=rot)
    cyl(r, 0.24, (x + off[0], y + off[1], z), P["dark"], rot=rot)
    ring(r * 0.75, 0.05, (x + off[0] * 2, y + off[1] * 2, z), P["glow"], rot=rot)


def barrel(x, y, P, h=1.1, m="grey_dark"):
    cyl(0.5, h, (x, y, h / 2), P[m])
    for z in (0.25, h - 0.25):
        ring(0.51, 0.04, (x, y, z), P["metal"])


def crate(x, y, z, s, P):
    box((s, s, s), (x, y, z + s / 2), P["crate"], 0.06)
    box((s * 1.02, s * 0.25, s * 1.02), (x, y, z + s / 2), P["wood_dark"], 0.02)


def walls(w, d, h, P, cx=0.0, cy=0.0, z0=0.4):
    box((w + 0.6, d + 0.6, z0), (cx, cy, z0 / 2), P["trim"], 0.1)
    box((w, d, h), (cx, cy, z0 + h / 2), P["wall"], 0.18)
    box((w + 0.06, d + 0.06, 0.55), (cx, cy, z0 + 0.3), P["band"], 0.06)
    box((w + 0.08, d + 0.08, 0.42), (cx, cy, z0 + h * 0.42), P["teal"], 0.06)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box((0.55, 0.55, h - 0.25), (cx + sx * (w / 2 - 0.1), cy + sy * (d / 2 - 0.1), z0 + (h - 0.25) / 2), P["trim"], 0.1)  # stays under the roof


def finial(x, y, z, P, h=1.6):
    cyl(0.08, h, (x, y, z + h / 2), P["metal"], verts=12)
    sphere(0.16, (x, y, z + h), P["roof"])


def light_strip(x, y, z, P, vertical=True):
    box((0.14, 0.12, 0.9) if vertical else (0.9, 0.12, 0.14), (x, y, z), P["glow"], 0.02)


# ---------------------------------------------------------------- buildings
def habitat(P):
    W, D, H = 10, 7, 4.4
    walls(W, D, H, P, cy=0.5)
    front = 0.5 - D / 2
    curved_roof(W + 1.8, D + 1.6, 0.55, 1.0, (0, 0.5, 0.4 + H + 0.45), P["roof"])
    curved_roof(W + 2.0, D + 1.8, 0.2, 1.0, (0, 0.5, 0.4 + H + 0.1), P["roof_dark"])
    # round drum on the roof with a disk cap and a finial
    cyl(1.6, 1.4, (-1.4, 1.2, 5.9), P["wall"])
    ring(1.62, 0.09, (-1.4, 1.2, 5.9), P["glow"])
    cyl(2.2, 0.35, (-1.4, 1.2, 6.75), P["roof"])
    cyl(1.2, 0.6, (-1.4, 1.2, 7.2), P["roof_dark"], r2=0.5)
    finial(-1.4, 1.2, 7.4, P)
    arch_door(1.6, front, 0.4, 1.8, 2.4, P)
    for x in (-3.2, -1.4):
        porthole(x, front, 3.0, 0.45, P)
    light_strip(2.95, front - 0.05, 2.2, P)
    porthole(W / 2, 1.6, 3.0, 0.4, P, facing="side")
    cyl(0.25, 4.6, (W / 2 + 0.25, -0.8, 2.7), P["metal"], verts=16)
    box((0.9, 0.7, 0.9), (W / 2 + 0.3, 2.6, 1.6), P["grey"], 0.1)
    barrel(-W / 2 - 0.3, front - 0.8, P)
    barrel(-W / 2 + 0.8, front - 1.2, P, 0.9, "grey")
    box((2.2, 1.0, 0.25), (-3.6, front - 0.7, 0.55), P["wood"], 0.05)


def factory(P):
    W, D, H = 15, 8.5, 4.2
    walls(W, D, H, P)
    front = -D / 2
    curved_roof(W + 1.6, D + 1.4, 0.5, 0.7, (0, 0, 0.4 + H + 0.35), P["roof"])
    curved_roof(W + 1.8, D + 1.6, 0.18, 0.7, (0, 0, 0.4 + H + 0.05), P["roof_dark"])
    for x, y in ((-4.8, 1.0), (0, 1.6), (4.8, 1.0)):
        cyl(1.4, 1.5, (x, y, 5.6), P["wall"])
        ring(1.42, 0.08, (x, y, 5.5), P["glow"])
        cyl(1.85, 0.3, (x, y, 6.45), P["roof"])
        cyl(1.4, 0.9, (x, y, 7.05), P["roof_dark"], r2=0.35)
        finial(x, y, 7.4, P, 1.2)
    for x in (-4.8, 0, 4.8):  # garage bays with wooden shutters
        box((3.4, 0.3, 3.2), (x, front - 0.02, 2.0), P["trim"], 0.08)
        box((2.8, 0.34, 2.7), (x, front - 0.06, 1.8), P["wood"], 0.04)
        for i in range(1, 6):
            box((2.82, 0.36, 0.05), (x, front - 0.08, 0.45 + i * 0.45), P["wood_dark"], 0.01)
        light_strip(x + 1.85, front - 0.05, 3.0, P)
    cyl(0.7, 4.6, (W / 2 - 1.6, 2.6, 6.6), P["metal"], verts=24)
    cyl(0.85, 0.5, (W / 2 - 1.6, 2.6, 8.9), P["roof"])
    bpy.ops.object.empty_add(location=(W / 2 - 1.6, 2.6, 9.3)); bpy.context.active_object.name = "smoke"; OBJS.append(bpy.context.active_object)
    for z in (1.4, 2.6):
        cyl(0.18, D + 0.6, (-W / 2 - 0.3, 0, z), P["red"], verts=12, rot=(math.pi / 2, 0, 0))
    barrel(W / 2 + 0.6, front + 1.2, P)
    crate(-W / 2 + 0.2, front - 1.4, 0, 1.0, P)
    crate(-W / 2 + 1.4, front - 1.2, 0, 0.9, P)
    crate(-W / 2 + 0.7, front - 1.3, 1.0, 0.8, P)


def github(P):
    W, D, H = 9.6, 7.6, 4.2
    walls(W, D, H, P)
    front = -D / 2
    box((W + 1.0, D + 1.0, 0.5), (0, 0, 0.4 + H + 0.25), P["grey"], 0.15)
    box((W + 1.1, D + 1.1, 0.2), (0, 0, 0.4 + H), P["grey_dark"], 0.05)
    top = 0.4 + H + 0.5
    for i in range(9):  # railing posts along the front and sides
        x = -W / 2 + i * W / 8
        cyl(0.06, 0.9, (x, -D / 2, top + 0.45), P["metal"], verts=8)
        cyl(0.06, 0.9, (x, D / 2, top + 0.45), P["metal"], verts=8)
    for y in (-D / 2, D / 2):
        cyl(0.05, W, (0, y, top + 0.9), P["metal"], verts=8, rot=(0, math.pi / 2, 0))
    for x in (-1.6, 0.8):  # rust tanks on the roof
        cyl(1.0, 1.4, (x, 1.4, top + 0.7), P["roof"])
        cyl(1.05, 0.25, (x, 1.4, top + 1.45), P["roof_dark"])
    box((1.6, 1.2, 0.8), (3.2, 1.6, top + 0.4), P["grey_dark"], 0.1)
    # double wooden door and the sign above it
    box((3.0, 0.3, 3.3), (0, front - 0.02, 2.05), P["trim"], 0.08)
    for x in (-0.65, 0.65):
        box((1.25, 0.34, 2.9), (x, front - 0.06, 1.85), P["wood"], 0.04)
        for i in range(1, 4):
            box((1.27, 0.36, 0.05), (x, front - 0.08, 0.4 + i * 0.7), P["wood_dark"], 0.01)
    box((3.6, 0.25, 0.9), (0, front - 0.06, 4.05), P["dark"], 0.06)
    box((2.8, 0.1, 0.18), (0, front - 0.2, 4.05), P["glow"], 0.02)
    for x in (-3.4, 3.4):
        box((0.7, 0.2, 1.8), (x, front - 0.04, 2.6), P["dark"], 0.06)
        light_strip(x, front - 0.12, 2.6, P)
    # planter with yellow-green plants by the door
    box((2.2, 1.0, 0.7), (-3.2, front - 1.0, 0.35), P["grey_dark"], 0.08)
    for i, x in enumerate((-3.9, -3.3, -2.6)):
        cyl(0.22, 1.2 + 0.25 * (i % 2), (x, front - 1.0, 1.2), P["leaf" if i % 2 else "fruit"], r2=0.02, verts=8)
    box((3.4, 1.6, 0.25), (0, front - 0.9, 0.12), P["trim"], 0.05)


def claude(P):
    # tall round tower with a wide grey disk roof, glowing band, and a low annex with sloped panels
    tx, ty = -1.8, 0.8
    cyl(2.5, 0.4, (tx, ty, 0.2), P["trim"])
    cyl(2.3, 6.2, (tx, ty, 3.5), P["wall"])
    ring(2.32, 0.1, (tx, ty, 0.75), P["band"])
    cyl(2.34, 0.5, (tx, ty, 2.6), P["teal"])
    ring(2.36, 0.07, (tx, ty, 2.6), P["glow"])
    for a in range(0, 360, 60):
        r = math.radians(a)
        box((0.5, 0.2, 0.9), (tx + math.sin(r) * 2.3, ty - math.cos(r) * 2.3, 4.4), P["dark"], 0.05, rot=(0, 0, r))
    cyl(3.4, 0.45, (tx, ty, 6.85), P["grey"])
    ring(3.2, 0.08, (tx, ty, 6.55), P["glow"])
    cyl(1.6, 0.9, (tx, ty, 7.5), P["grey_dark"], r2=0.8)
    sphere(0.8, (tx, ty, 7.95), P["grey"], (1, 1, 0.55))
    finial(tx, ty, 8.3, P, 1.4)
    # annex
    ax, ay, aw, ad, ah = 2.4, -0.4, 5.6, 4.2, 2.8
    walls(aw, ad, ah, P, cx=ax, cy=ay)
    for i in range(3):
        s = box((aw / 3 - 0.1, ad + 0.8, 0.3), (ax - aw / 3 + i * aw / 3, ay, 0.4 + ah + 0.55), P["grey"], 0.06, rot=(0.25, 0, 0))
    box((2.0, 0.3, 0.7), (ax + 1.2, ay - ad / 2 - 0.25, 2.6), P["roof"], 0.05, rot=(-0.35, 0, 0))
    for z in (1.2, 1.8):
        cyl(0.13, aw - 0.6, (ax, ay - ad / 2 - 0.25, z), P["red"], verts=12, rot=(0, math.pi / 2, 0))
    arch_door(tx + 0.2, ty - 2.35, 0.4, 1.4, 2.0, P)
    cyl(1.2, 2.2, (ax + 2.4, ay + 2.6, 1.5), P["wall"])
    sphere(1.2, (ax + 2.4, ay + 2.6, 2.6), P["grey"], (1, 1, 0.55))
    barrel(ax + 3.4, ay - 2.6, P, 0.9, "red")


def chat(P):
    # round arena (floor top at z 0.9, centred where the chat astronauts stand) and a tall tower for the dish
    cx, cy = -2.4, -2.2
    cyl(5.5, 0.9, (cx, cy, 0.45), P["wall"], verts=48)
    ring(5.5, 0.12, (cx, cy, 0.2), P["band"])
    cyl(5.52, 0.25, (cx, cy, 0.55), P["teal"], verts=48)
    cyl(4.7, 0.06, (cx, cy, 0.92), P["trim"], verts=48)
    ring(3.0, 0.08, (cx, cy, 0.95), P["glow"])
    for a in range(0, 360, 24):  # segmented rust rim
        r = math.radians(a)
        box((1.7, 0.5, 0.7), (cx + math.cos(r) * 5.1, cy + math.sin(r) * 5.1, 1.2), P["roof"], 0.08, rot=(0, 0, r + math.pi / 2))
    for i in range(5):  # stairs up to the rim
        box((2.0, 0.7, 0.18 * (i + 1)), (cx + 4.6, cy - 4.4 + i * 0.7, 0.09 * (i + 1)), P["trim"], 0.04)
    tx, ty = 3.8, 3.4
    cyl(1.9, 0.6, (tx, ty, 0.3), P["trim"])
    cyl(1.25, 9.6, (tx, ty, 5.0), P["wall"], r2=1.0)
    for z in (2.6, 5.4, 8.2):
        cyl(1.28 - z * 0.025, 0.4, (tx, ty, z), P["teal"])
    for z in (3.9, 6.8):
        box((0.5, 0.2, 0.8), (tx, ty - 1.15, z), P["dark"], 0.05)
        light_strip(tx, ty - 1.25, z, P)
    cyl(1.9, 0.3, (tx, ty, 9.9), P["roof"])
    cyl(1.4, 1.2, (tx, ty, 10.6), P["roof_dark"], r2=0.4)
    cyl(0.12, 1.4, (tx, ty, 11.6), P["metal"], verts=12)


def media(P):
    # a market hall: big curved rust roof over the front, open stall with fruit crates under a teal awning, arched door
    W, D, H = 12.5, 7.6, 4.0
    walls(W, D, H, P)
    front = -D / 2
    curved_roof(W + 1.6, D + 2.4, 0.55, 0.9, (0, -0.5, 0.4 + H + 0.45), P["roof"], axis="y")
    curved_roof(W + 1.8, D + 2.6, 0.2, 0.9, (0, -0.5, 0.4 + H + 0.1), P["roof_dark"], axis="y")
    box((4.6, 0.4, 2.2), (-2.4, front - 0.02, 2.0), P["trim"], 0.06)
    box((4.0, 0.44, 1.7), (-2.4, front - 0.06, 2.0), P["dark"], 0.04)
    box((4.8, 1.4, 0.18), (-2.4, front - 0.75, 3.35), P["teal"], 0.04, rot=(-0.3, 0, 0))
    box((3.8, 1.0, 0.6), (-2.4, front - 0.6, 0.9), P["wood"], 0.05)
    for i in range(8):
        sphere(0.2, (-3.9 + i * 0.42, front - 0.6 + (i % 2) * 0.2, 1.35), P["fruit"])
    arch_door(3.2, front, 0.4, 1.7, 2.4, P)
    light_strip(4.4, front - 0.05, 2.0, P)
    barrel(-W / 2 - 0.5, front - 0.4, P)
    cyl(0.6, 1.6, (-W / 2 - 0.4, front + 1.4, 0.8), P["grey_dark"])
    finial(W / 2 - 1.2, 1.5, 0.4 + H + 0.8, P, 2.0)
    porthole(W / 2, 1.4, 2.8, 0.45, P, facing="side")


def _spin_part(o, wheel):
    """Bake a part's rotation into its mesh and hang it on the wheel's pivot, so the website can spin the pivot."""
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    o.select_set(False)
    o.parent = wheel
    o.matrix_parent_inverse = wheel.matrix_world.inverted()


def rover(P):
    """The delivery rover from the sketch: yellow chassis, grey cargo case, camera mast, chunky black wheels."""
    Y, O = mat("yellow", "#f2b33d", 0.55), mat("orange", "#d9822b", 0.6)
    cargo, head = mat("cargo", "#c9ccd2", 0.5), mat("camhead", "#dcd7cd", 0.5)
    tire, arm, lens = mat("tire", "#24262b", 0.9), mat("arm", "#e8e8e6", 0.4), mat("lens", "#2f6fd6", 0.2, glow=0.8)
    # chassis with trim, vents and side lights (front faces -y)
    box((2.4, 3.8, 0.6), (0, 0, 1.35), Y, 0.12)
    box((2.52, 3.92, 0.14), (0, 0, 1.7), O, 0.05)
    box((2.44, 3.84, 0.16), (0, 0, 1.05), O, 0.05)
    for x in (-0.6, 0.6):
        box((0.62, 0.1, 0.3), (x, -1.93, 1.35), P["grey_dark"], 0.04)
    for side in (-1, 1):
        for y in (-1.0, -0.3, 0.4):
            cyl(0.08, 0.06, (side * 1.22, y, 1.4), P["dark"], rot=(0, math.pi / 2, 0))
    # ribbed cargo case on the back
    box((1.9, 1.9, 0.8), (0, 0.8, 2.15), cargo, 0.3)
    for y in (0.35, 0.8, 1.25):
        box((1.96, 0.08, 0.82), (0, y, 2.15), P["grey_dark"], 0.03)
    # front sensor block
    box((1.0, 0.6, 0.45), (-0.4, -1.4, 1.98), Y, 0.1)
    for x in (-0.65, -0.2):
        box((0.3, 0.1, 0.25), (x, -1.72, 2.0), P["dark"], 0.05)
    # camera mast
    cyl(0.18, 0.25, (0.75, -1.1, 1.85), P["grey_dark"])
    cyl(0.1, 2.0, (0.75, -1.1, 2.9), P["metal"], verts=12)
    box((0.9, 0.5, 0.6), (0.75, -1.15, 4.1), head, 0.08)
    cyl(0.18, 0.14, (0.75, -1.43, 4.1), lens, rot=(math.pi / 2, 0, 0))
    cyl(0.025, 0.55, (1.05, -1.0, 4.6), P["metal"], verts=8)
    # wheels on suspension arms; each wheel hangs on an empty named wheel_N that the website spins
    n = 0
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy, cz = sx * 1.75, sy * 1.45, 0.7
            cyl(0.08, 0.5, (sx * 1.4, cy, 1.05), arm, verts=10, rot=(0, math.pi / 2, 0))
            cyl(0.07, 0.45, (sx * 1.62, cy, 0.86), arm, verts=10)
            bpy.ops.object.empty_add(location=(cx, cy, cz))
            wheel = bpy.context.active_object
            wheel.name = f"wheel_{n}"
            n += 1
            OBJS.append(wheel)
            _spin_part(cyl(0.68, 0.6, (cx, cy, cz), tire, verts=32, rot=(0, math.pi / 2, 0)), wheel)
            for k in range(12):
                a = k * math.pi / 6
                _spin_part(box((0.62, 0.17, 0.12), (cx, cy + 0.69 * math.cos(a), cz + 0.69 * math.sin(a)), tire, 0.03, rot=(a, 0, 0)), wheel)
            _spin_part(cyl(0.42, 0.64, (cx, cy, cz), O, rot=(0, math.pi / 2, 0)), wheel)
            _spin_part(cyl(0.16, 0.7, (cx, cy, cz), P["metal"], rot=(0, math.pi / 2, 0)), wheel)


def astronaut(P):
    """The chibi astronaut: big round helmet with a glossy dark visor, red ear pods, chest panel, red-soled boots.
    Feet at z=0, about 2.3 tall, facing -y. The visor material is named 'visor' so the website can tint it."""
    suit, rim = mat("suit", "#f1ede6", 0.55), mat("rim", "#2b2645", 0.4)
    visor, red, blue = mat("visor", "#1d1937", 0.12, 0.2), mat("accent_red", "#e2553b", 0.45), mat("accent_blue", "#3f6fd8", 0.4)
    panel = mat("panel", "#fbfaf7", 0.5)
    sphere(0.62, (0, 0, 1.72), suit, (1, 0.95, 0.92))                         # helmet
    sphere(0.5, (0, -0.41, 1.7), visor, (0.92, 0.5, 0.78))                     # visor
    for sx in (-1, 1):
        cyl(0.18, 0.16, (sx * 0.6, 0, 1.72), rim, rot=(0, math.pi / 2, 0))      # ear pods
        cyl(0.12, 0.18, (sx * 0.62, 0, 1.72), red, rot=(0, math.pi / 2, 0))
    ring(0.25, 0.07, (0, 0, 1.13), rim)                                        # collar
    sphere(0.38, (0, 0, 0.8), suit, (1, 0.86, 1.08))                           # body
    box((0.36, 0.42, 0.5), (0, 0.32, 0.92), suit, 0.12)                        # backpack
    box((0.44, 0.12, 0.32), (0, -0.33, 0.86), panel, 0.06)                     # chest panel
    cyl(0.05, 0.06, (-0.12, -0.4, 0.92), red, verts=16, rot=(math.pi / 2, 0, 0))
    cyl(0.05, 0.06, (-0.12, -0.4, 0.8), blue, verts=16, rot=(math.pi / 2, 0, 0))
    for i in range(3):
        for j in range(2):
            box((0.06, 0.04, 0.06), (0.01 + i * 0.07, -0.4, 0.92 - j * 0.1), rim, 0.01)
    for sx in (-1, 1):
        cyl(0.12, 0.42, (sx * 0.44, -0.02, 0.84), suit, verts=16, rot=(0, sx * 0.55, 0))   # arms
        ring(0.12, 0.04, (sx * 0.56, -0.04, 0.68), rim, rot=(0, sx * 0.55, 0))           # cuffs
        sphere(0.14, (sx * 0.6, -0.05, 0.6), suit)                                       # gloves
        cyl(0.14, 0.36, (sx * 0.17, 0, 0.32), suit, verts=16)                           # legs
        ring(0.14, 0.045, (sx * 0.17, 0, 0.36), rim)                                    # knee bands
        sphere(0.17, (sx * 0.17, -0.06, 0.11), rim, (1, 1.3, 0.62))                     # boots
        cyl(0.16, 0.05, (sx * 0.17, -0.06, 0.03), red, verts=24)                        # red soles


def pup(P):
    """The pup in a helmet: golden face behind a round white helmet, little white suit, about 0.9 tall."""
    suit, rim = mat("suit", "#f1ede6", 0.55), mat("rim", "#2b2645", 0.4)
    gold, cream, dark = mat("pup_gold", "#e8a93a", 0.6), mat("pup_cream", "#f6e3bf", 0.7), mat("pup_dark", "#1d1a24", 0.4)
    sphere(0.22, (0, 0, 0.3), suit, (1, 1.1, 1))                               # body
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(0.06, 0.2, (sx * 0.1, sy * 0.1, 0.1), suit, verts=12)         # legs
    ring(0.15, 0.04, (0, 0, 0.47), rim)                                        # collar
    sphere(0.33, (0, 0.04, 0.68), suit, (1, 1, 0.95))                          # helmet
    sphere(0.25, (0, -0.1, 0.66), gold)                                        # face
    sphere(0.1, (0, -0.32, 0.6), cream, (1, 0.8, 0.8))                         # snout
    sphere(0.035, (0, -0.4, 0.63), dark)                                       # nose
    for sx in (-1, 1):
        sphere(0.03, (sx * 0.09, -0.32, 0.73), dark)                           # eyes
        sphere(0.07, (sx * 0.17, -0.12, 0.86), gold)                           # ears
    ring(0.24, 0.035, (0, -0.2, 0.66), rim, rot=(math.pi / 2, 0, 0))           # helmet opening rim


# ---------------------------------------------------------------- export
def build(name, fn):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATS.clear()
    OBJS.clear()
    fn(palette())
    bpy.ops.object.select_all(action="DESELECT")
    for o in OBJS:
        o.select_set(True)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
    print("exported", path, len(OBJS), "parts")


for name, fn in (("habitat", habitat), ("factory", factory), ("github", github), ("claude", claude), ("chat", chat), ("media", media), ("rover", rover), ("astronaut", astronaut), ("pup", pup)):
    build(name, fn)
