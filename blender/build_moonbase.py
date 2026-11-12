"""Moonbase buildings, modelled in Blender and exported as GLB for the website.

Style: a neon outpost on the Moon. Dark shells with glowing edge strips, lit window grids, neon signs, roof plant,
ladders, cables and antennas; each station glows in its own colour (see NEON). The astronaut is rigged and animated.

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


# Neon look: every building has the same dark shell and glows in its own colour ("a"), with a shared second colour ("b").
# The same colours are listed as NEON in index.html, so tile rims and ground glow match the models.
SHELL = dict(body="#1a1f33", frame="#0d1020", panel="#262d4a", win="#9af4ff")
CYAN = "#19e3ff"
NEON = {  # model name: (own colour, second colour)
    "habitat": ("#3d7bff", CYAN), "factory": ("#ffb020", CYAN), "github": ("#e6ecff", CYAN), "claude": ("#ff7a4d", CYAN),
    "chat": ("#2ec5ff", "#ff2bd6"), "media": ("#ff3d9a", CYAN), "rover": ("#ffb020", CYAN), "astronaut": ("#ff7a4d", CYAN), "pup": ("#ffb020", CYAN),
}
GLOW = 4.0  # emission strength of neon strips


def palette(a="#ff2bd6", b=CYAN):
    """Keys keep their old names (wall, roof, wood...) so the building code reads the same; the colours are neon now:
    dark shells, and every band, rim, slat and window is a glowing strip."""
    T = dict(SHELL, a=a, b=b)
    return dict(
        wall=mat("wall", T["body"], 0.55, 0.2), trim=mat("trim", T["frame"], 0.5, 0.3), band=mat("neon_a", T["a"], 0.4, glow=GLOW),
        teal=mat("neon_b", T["b"], 0.4, glow=GLOW), roof=mat("roof", T["panel"], 0.45, 0.3), roof_dark=mat("roof_rim", T["a"], 0.4, glow=GLOW),
        grey=mat("grey", "#3a4055", 0.5, 0.3), grey_dark=mat("grey_dark", "#232738", 0.5, 0.3), dark=mat("dark", "#0b0d14", 0.4),
        glow=mat("glow", T["win"], 0.4, glow=GLOW + 1), wood=mat("door", T["frame"], 0.4, 0.4), wood_dark=mat("door_slat", T["b"], 0.4, glow=GLOW),
        metal=mat("metal", "#8a93ad", 0.3, 0.8), red=mat("pipe", T["a"], 0.4, glow=GLOW * 0.6), crate=mat("crate", "#2a3048", 0.6, 0.2),
        fruit=mat("fruit", T["a"], 0.5, glow=GLOW * 0.7), leaf=mat("leaf", T["b"], 0.5, glow=GLOW * 0.7),
        seam=mat("seam", "#10131f", 0.6, 0.2), win=mat("window", "#ffd98a", 0.4, glow=2.5),
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
    box((w + 0.1, d + 0.1, 0.16), (cx, cy, z0 + 0.12), P["band"], 0.04)          # glowing skirting line
    box((w + 0.08, d + 0.08, 0.14), (cx, cy, z0 + h * 0.42), P["teal"], 0.04)   # glowing waist line
    for sx in (-1, 1):
        for sy in (-1, 1):
            px, py = cx + sx * (w / 2 - 0.1), cy + sy * (d / 2 - 0.1)
            box((0.55, 0.55, h - 0.25), (px, py, z0 + (h - 0.25) / 2), P["trim"], 0.1)  # stays under the roof
            box((0.12, 0.12, h - 0.6), (px + sx * 0.27, py + sy * 0.27, z0 + (h - 0.25) / 2), P["teal"], 0.03)  # neon tube down each corner


def finial(x, y, z, P, h=1.6):
    cyl(0.08, h, (x, y, z + h / 2), P["metal"], verts=12)
    sphere(0.16, (x, y, z + h), P["roof"])


def light_strip(x, y, z, P, vertical=True):
    box((0.14, 0.12, 0.9) if vertical else (0.9, 0.12, 0.14), (x, y, z), P["glow"], 0.02)


# ---------------------------------------------------------------- detail kit
# Small parts that make a shell read as a real building: panel seams, lit window grids, vents, AC units, ladders,
# antenna clusters, cable runs, neon signs and landing lights. All front faces look towards -y.
def panel_seams(w, d, h, P, cx=0.0, cy=0.0, z0=0.4, step=1.6):
    """Thin dark grooves and rivets on all four walls."""
    for sy in (-1, 1):
        n = max(2, int(w / step))
        for i in range(1, n):
            x = cx - w / 2 + i * w / n
            box((0.05, 0.05, h - 0.9), (x, cy + sy * (d / 2 + 0.01), z0 + h / 2 + 0.1), P["seam"], 0)
    for sx in (-1, 1):
        n = max(2, int(d / step))
        for i in range(1, n):
            y = cy - d / 2 + i * d / n
            box((0.05, 0.05, h - 0.9), (cx + sx * (w / 2 + 0.01), y, z0 + h / 2 + 0.1), P["seam"], 0)
    for sy in (-1, 1):
        box((w + 0.04, 0.05, 0.05), (cx, cy + sy * (d / 2 + 0.01), z0 + h * 0.72), P["seam"], 0)
    for sx in (-1, 1):
        box((0.05, d + 0.04, 0.05), (cx + sx * (w / 2 + 0.01), cy, z0 + h * 0.72), P["seam"], 0)


def window_grid(x, y, z, cols, rows, P, facing="front", cw=0.5, ch=0.34, gap=0.14, lit=None):
    """A framed bank of small windows; some warm, some cool, a few dark."""
    W, Hh = cols * cw + (cols + 1) * gap, rows * ch + (rows + 1) * gap
    side = facing != "front"
    sgn = (1 if x > 0 else -1) if side else -1
    fr = (0.16, W, Hh) if side else (W, 0.16, Hh)
    box(fr, (x, y, z), P["dark"], 0.03)
    k = 0
    for r in range(rows):
        for c in range(cols):
            u = -W / 2 + gap + cw / 2 + c * (cw + gap)
            zz = z - Hh / 2 + gap + ch / 2 + r * (ch + gap)
            k += 1
            m = P[(lit or ("win", "glow", "win", "seam", "glow"))[(k * 7 + r) % 5]]
            if side:
                box((0.06, cw, ch), (x + sgn * 0.07, y + u, zz), m, 0.015)
            else:
                box((cw, 0.06, ch), (x + u, y + sgn * 0.07, zz), m, 0.015)


def vent(x, y, z, P, w=0.9, h=0.6, facing="front"):
    side = facing != "front"
    sgn = (1 if x > 0 else -1) if side else -1
    box((0.12, w, h) if side else (w, 0.12, h), (x, y, z), P["grey_dark"], 0.03)
    for i in range(4):
        zz = z - h / 2 + (i + 0.5) * h / 4
        box((0.08, w - 0.14, 0.05) if side else (w - 0.14, 0.08, 0.05), (x + (sgn * 0.05 if side else 0), y + (0 if side else sgn * 0.05), zz), P["metal"], 0.01)


def ac_unit(x, y, z, P, s=1.0):
    box((1.5 * s, 1.1 * s, 0.7 * s), (x, y, z + 0.35 * s), P["grey"], 0.06)
    cyl(0.4 * s, 0.06, (x, y, z + 0.72 * s), P["dark"], verts=20, bevel=0.01)
    ring(0.4 * s, 0.035, (x, y, z + 0.74 * s), P["metal"])
    for i in range(3):
        box((0.5 * s, 0.03, 0.05), (x, y, z + 0.76 * s), P["metal"], 0, rot=(0, 0, i * math.pi / 3))
    box((1.52 * s, 0.05, 0.08), (x, y - 0.56 * s, z + 0.2 * s), P["teal"], 0.01)
    for sx in (-1, 1):
        box((0.12, 0.9 * s, 0.1), (x + sx * 0.55 * s, y, z + 0.04), P["trim"], 0.02)


def ladder(x, y, z0, h, P):
    for sx in (-1, 1):
        cyl(0.035, h, (x + sx * 0.22, y, z0 + h / 2), P["metal"], verts=8, bevel=0)
    for i in range(int(h / 0.38)):
        cyl(0.028, 0.44, (x, y, z0 + 0.25 + i * 0.38), P["metal"], verts=8, bevel=0, rot=(0, math.pi / 2, 0))


def antenna_cluster(x, y, z, P, h=2.2):
    cyl(0.3, 0.2, (x, y, z + 0.1), P["grey_dark"], verts=16)
    cyl(0.05, h, (x, y, z + h / 2), P["metal"], verts=8, bevel=0)
    for i, zz in enumerate((0.45, 0.7, 0.9)):
        box((0.7 - i * 0.18, 0.03, 0.03), (x, y, z + h * zz), P["metal"], 0)
    sphere(0.09, (x, y, z + h + 0.05), P["band"])
    cyl(0.03, h * 0.6, (x + 0.35, y + 0.2, z + h * 0.3), P["metal"], verts=6, bevel=0)
    sphere(0.06, (x + 0.35, y + 0.2, z + h * 0.6 + 0.04), P["teal"])
    # a little dish
    cyl(0.32, 0.1, (x - 0.4, y - 0.15, z + 0.75), P["grey"], r2=0.1, verts=20, bevel=0.01, rot=(0.9, 0, 0.5))
    cyl(0.03, 0.6, (x - 0.4, y - 0.15, z + 0.4), P["metal"], verts=6, bevel=0)


def cable(points, P, r=0.05, m="grey_dark"):
    """A pipe or cable through a list of points (axis-aligned runs look best)."""
    for (x1, y1, z1), (x2, y2, z2) in zip(points, points[1:]):
        dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
        L = math.sqrt(dx * dx + dy * dy + dz * dz)
        if L < 1e-4:
            continue
        rot = (0, math.acos(max(-1, min(1, dz / L))), math.atan2(dy, dx))
        cyl(r, L, ((x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2), P[m], verts=8, bevel=0, rot=rot)
        sphere(r * 1.25, (x2, y2, z2), P[m])


def neon_sign(x, y, z, w, h, P, bars=3, key="band"):
    """A dark sign board with a glowing frame and bars of light, like lettering seen from far away."""
    box((w, 0.16, h), (x, y, z), P["dark"], 0.04)
    for sz in (-1, 1):
        box((w + 0.06, 0.08, 0.06), (x, y - 0.08, z + sz * (h / 2)), P[key], 0.015)
    for sx in (-1, 1):
        box((0.06, 0.08, h + 0.06), (x + sx * (w / 2), y - 0.08, z), P[key], 0.015)
    for i in range(bars):
        ww = (w - 0.5) * (0.9, 0.6, 0.75, 0.5)[i % 4]
        zz = z + h / 2 - (i + 1) * h / (bars + 1)
        box((ww, 0.06, min(0.12, h / (bars * 2.5))), (x - (w - 0.5 - ww) / 2, y - 0.1, zz), P["teal" if i % 2 else key], 0.01)


def ground_light(x, y, P, key="teal"):
    cyl(0.16, 0.12, (x, y, 0.06), P["trim"], verts=12, bevel=0.02)
    cyl(0.1, 0.06, (x, y, 0.14), P[key], verts=12, bevel=0.01)


def console(x, y, P, rot=0.0):
    """An outdoor control post with a glowing screen."""
    box((0.5, 0.4, 1.0), (x, y, 0.5), P["grey_dark"], 0.06, rot=(0, 0, rot))
    box((0.7, 0.12, 0.45), (x, y, 1.15), P["dark"], 0.04, rot=(-0.5, 0, rot))
    box((0.56, 0.05, 0.3), (x - math.sin(rot) * -0.05, y - math.cos(rot) * 0.05, 1.17), P["glow"], 0.01, rot=(-0.5, 0, rot))


def roof_kit(w, d, z, P, cx=0.0, cy=0.0, seed=0):
    """Flat-roof clutter: AC unit, vents, a hatch, a cable run and an antenna cluster."""
    q = (seed % 2) * 2 - 1
    ac_unit(cx + q * w * 0.22, cy + d * 0.18, z, P, 0.8)
    box((0.9, 0.9, 0.16), (cx - q * w * 0.25, cy - d * 0.2, z + 0.08), P["grey_dark"], 0.04)
    ring(0.25, 0.03, (cx - q * w * 0.25, cy - d * 0.2, z + 0.18), P["metal"])
    for i in range(2):
        cyl(0.16, 0.5, (cx - q * w * 0.05 + i * 0.5, cy + d * 0.3, z + 0.25), P["metal"], verts=12)
        cyl(0.2, 0.08, (cx - q * w * 0.05 + i * 0.5, cy + d * 0.3, z + 0.54), P["grey_dark"], verts=12, bevel=0.02)
    cable([(cx + q * w * 0.22, cy + d * 0.18, z + 0.06), (cx - q * w * 0.25, cy + d * 0.18, z + 0.06), (cx - q * w * 0.25, cy - d * 0.2, z + 0.06)], P, 0.04)
    antenna_cluster(cx - q * w * 0.36, cy + d * 0.3, z, P, 1.8)


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
    # detail: seams, lit windows, a name sign, roof kit, ladder, cables, path lights, a control post
    panel_seams(W, D, H, P, cy=0.5)
    window_grid(-2.3, front - 0.02, 1.55, 4, 1, P)
    window_grid(-W / 2 - 0.02, 0.4, 3.0, 3, 2, P, facing="side")
    window_grid(0.6, 0.5 + D / 2 + 0.02, 2.8, 6, 2, P)
    neon_sign(1.6, front - 0.1, 3.75, 2.6, 0.7, P, bars=2)
    vent(W / 2 + 0.02, -1.8, 1.4, P, facing="side")
    vent(-4.2, 0.5 + D / 2 + 0.02, 1.2, P)
    ladder(W / 2 - 1.2, 0.5 + D / 2 + 0.12, 0.4, H, P)
    ac_unit(2.8, 1.6, 0.4 + H + 0.42, P, 0.8)
    antenna_cluster(3.6, -0.8, 0.4 + H + 0.35, P, 2.0)
    cable([(W / 2 + 0.3, 2.6, 2.0), (W / 2 + 0.3, 2.6, 4.2), (W / 2 + 0.3, 1.0, 4.2)], P, 0.06)
    cable([(W / 2 + 0.25, -0.8, 0.5), (W / 2 + 1.2, -0.8, 0.5), (W / 2 + 1.2, -2.6, 0.5)], P, 0.07, "red")
    box((2.6, 2.4, 0.12), (1.6, front - 1.3, 0.06), P["grey_dark"], 0.03)       # doorstep pad
    for x in (0.4, 2.8):
        for y in (front - 0.5, front - 2.1):
            ground_light(x, y, P)
    console(4.2, front - 1.2, P)
    crate(-W / 2 - 0.4, 2.2, 0, 0.9, P)
    crate(-W / 2 - 0.5, 3.2, 0, 0.7, P)


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
    # detail: seams, clerestory windows, bay numbers, hazard lights, roof plant, gantry pipes, ladder, loading marks
    panel_seams(W, D, H, P, step=1.5)
    for x in (-2.4, 2.4):
        window_grid(x, front - 0.02, 3.3, 2, 2, P, cw=0.4, ch=0.3)
    window_grid(0, D / 2 + 0.02, 3.0, 12, 2, P)
    window_grid(W / 2 + 0.02, -1.5, 3.0, 4, 2, P, facing="side")
    neon_sign(0, front - 0.12, 4.25, 5.2, 0.55, P, bars=1)
    for i, x in enumerate((-4.8, 0, 4.8)):
        box((0.9, 0.08, 0.1), (x, front - 0.16, 3.75), P["band"], 0.02)           # light bar over each bay
        for k in range(i + 1):
            box((0.1, 0.06, 0.3), (x - 1.2 + k * 0.2, front - 0.16, 3.75), P["glow"], 0.01)  # bay number as tally marks
        box((3.0, 1.8, 0.05), (x, front - 1.2, 0.03), P["grey_dark"], 0.01)
        for sx in (-1, 1):
            box((0.12, 1.8, 0.06), (x + sx * 1.5, front - 1.2, 0.05), P["band"], 0.01)
    ac_unit(-2.4, -2.2, 0.4 + H + 0.45, P)
    ac_unit(2.4, -2.2, 0.4 + H + 0.45, P)
    cable([(-4.8, 1.0, 5.2), (-4.8, -0.9, 5.2), (0, -0.9, 5.2), (0, 1.6, 5.2)], P, 0.09, "metal")
    cable([(0, -0.9, 5.2), (4.8, -0.9, 5.2), (4.8, 1.0, 5.2)], P, 0.09, "metal")
    for z in (5.4, 6.6, 7.8):
        ring(0.72, 0.05, (W / 2 - 1.6, 2.6, z), P["band"])
    ladder(W / 2 - 1.6, 2.6 - 0.78, 4.9, 3.6, P)
    ladder(-W / 2 + 1.0, D / 2 + 0.12, 0.4, H, P)
    antenna_cluster(-6.4, -2.6, 0.4 + H + 0.2, P, 2.4)
    for y in (-2.4, 0.0, 2.4):
        box((0.3, 0.3, 0.5), (-W / 2 - 0.3, y, 0.25), P["grey_dark"], 0.04)        # pipe brackets
        box((0.3, 0.3, 0.4), (-W / 2 - 0.3, y, 2.0), P["grey_dark"], 0.04)
    cyl(0.9, 2.4, (W / 2 + 1.4, 1.6, 1.2), P["grey"], verts=24)                    # coolant tank
    for z in (0.5, 1.2, 1.9):
        ring(0.92, 0.05, (W / 2 + 1.4, 1.6, z), P["teal"])
    cyl(0.5, 0.3, (W / 2 + 1.4, 1.6, 2.5), P["grey_dark"], r2=0.2, verts=24)
    cable([(W / 2 + 1.4, 1.6, 2.6), (W / 2 + 1.4, 1.6, 3.4), (W / 2 + 0.05, 1.6, 3.4)], P, 0.07)
    console(-1.2, front - 2.4, P)
    for x in (-7.2, -2.4, 2.4, 7.2):
        ground_light(x, front - 2.3, P, "band")


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
    # detail: seams, server-rack windows, octo sign bars, railing lights, roof kit, cable trunk, cargo lockers
    panel_seams(W, D, H, P)
    for x in (-2.6, 2.6):
        window_grid(x, front - 0.02, 3.5, 2, 3, P, cw=0.34, ch=0.2, gap=0.1, lit=("glow", "glow", "seam", "glow", "win"))
    for sx in (-1, 1):
        window_grid(sx * (W / 2 + 0.02), 0, 2.6, 7, 4, P, facing="side", cw=0.36, ch=0.2, gap=0.1, lit=("glow", "seam", "glow", "band", "seam"))
    window_grid(0, D / 2 + 0.02, 2.6, 9, 4, P, cw=0.36, ch=0.2, gap=0.1, lit=("glow", "seam", "glow", "band", "seam"))
    for i in range(9):
        sphere(0.07, (-W / 2 + i * W / 8, -D / 2, top + 0.94), P["teal" if i % 2 else "band"])
    roof_kit(W, D, top, P, seed=1)
    for x in (-1.6, 0.8):
        ring(1.02, 0.05, (x, 1.4, top + 0.5), P["band"])
        ring(1.02, 0.05, (x, 1.4, top + 1.0), P["band"])
    cable([(3.2, 1.6, top + 0.85), (3.2, 3.0, top + 0.85), (3.2, D / 2 + 0.15, top + 0.3), (3.2, D / 2 + 0.15, 0.3)], P, 0.08)
    cable([(3.5, D / 2 + 0.15, top + 0.3), (3.5, D / 2 + 0.15, 0.3)], P, 0.05, "teal")
    for i in range(3):
        box((0.9, 0.7, 1.5), (W / 2 + 0.7, -2.4 + i * 1.0, 0.75), P["grey_dark"], 0.06)
        box((0.06, 0.5, 0.08), (W / 2 + 1.16, -2.4 + i * 1.0, 1.1), P["teal" if i % 2 else "band"], 0.01)
        box((0.06, 0.5, 0.5), (W / 2 + 1.16, -2.4 + i * 1.0, 0.55), P["seam"], 0.01)
    for x in (-1.5, 1.5):
        ground_light(x, front - 1.9, P)
    console(3.6, front - 1.3, P)


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
    # detail: tower window rings, spiral light strips, a balcony, the spark sign, annex windows, vents and cables
    for z in (1.5, 3.5, 5.4):
        for a in range(30, 360, 60):
            r = math.radians(a)
            box((0.42, 0.1, 0.3), (tx + math.sin(r) * 2.32, ty - math.cos(r) * 2.32, z), P["win" if (a // 60 + int(z)) % 3 else "glow"], 0.02, rot=(0, 0, r))
    for a in range(0, 360, 30):
        r = math.radians(a)
        box((0.05, 0.08, 6.0), (tx + math.sin(r) * 2.31, ty - math.cos(r) * 2.31, 3.6), P["seam"], 0, rot=(0, 0, r))
    ring(2.75, 0.06, (tx, ty, 5.0), P["metal"])                                     # balcony rail
    cyl(2.7, 0.12, (tx, ty, 4.55), P["grey_dark"], verts=32, bevel=0.03)
    for a in range(0, 360, 30):
        r = math.radians(a)
        cyl(0.03, 0.45, (tx + math.sin(r) * 2.75, ty - math.cos(r) * 2.75, 4.8), P["metal"], verts=6, bevel=0)
    for k in range(8):                                                              # the spark: eight glowing rays over the door
        a = k * math.pi / 4
        box((0.09, 0.08, 0.5 if k % 2 else 0.7), (tx + 0.2 + math.sin(a) * 0.42, ty - 2.42, 3.55 + math.cos(a) * 0.42), P["band"], 0.02, rot=(0, -a, 0))
    for k in range(6):
        a = math.radians(k * 60 + 15)
        box((0.5, 0.12, 0.2), (tx + math.sin(a) * 3.35, ty - math.cos(a) * 3.35, 6.85), P["teal"], 0.03, rot=(0, 0, a))
    panel_seams(aw, ad, ah, P, cx=ax, cy=ay, step=1.4)
    window_grid(ax - 0.9, ay - ad / 2 - 0.02, 2.2, 3, 2, P, cw=0.4, ch=0.3)
    window_grid(ax + aw / 2 + 0.02, ay, 2.0, 4, 2, P, facing="side", cw=0.4, ch=0.3)
    vent(ax + 1.4, ay + ad / 2 + 0.02, 1.4, P)
    for i in range(3):
        box((aw / 3 - 0.5, 0.06, 0.06), (ax - aw / 3 + i * aw / 3, ay - ad / 2 - 0.42, 0.4 + ah + 0.13), P["teal"], 0.01)
    ring(1.22, 0.05, (ax + 2.4, ay + 2.6, 1.0), P["band"])
    ring(1.22, 0.05, (ax + 2.4, ay + 2.6, 2.0), P["band"])
    ladder(ax + 2.4, ay + 2.6 - 1.26, 0.4, 2.2, P)
    cable([(ax + 2.4, ay + 1.4, 2.4), (ax + 2.4, ay + 1.4, 3.6), (ax + 2.4, ay, 3.6)], P, 0.06)
    cable([(tx + 2.3, ty, 0.3), (ax - aw / 2, ty, 0.3)], P, 0.09, "red")
    antenna_cluster(ax + 1.6, ay + 0.8, 0.4 + ah + 0.7, P, 1.6)
    console(tx + 2.0, ty - 3.2, P)
    for x in (tx - 0.9, tx + 1.3):
        ground_light(x, ty - 3.6, P, "band")


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
    # detail: arena floor lights and seats, a holo table, tower windows, ladder, cable down the mast, signal rings
    for a in range(12, 360, 24):
        r = math.radians(a)
        box((0.5, 0.1, 0.12), (cx + math.cos(r) * 5.38, cy + math.sin(r) * 5.38, 1.2), P["teal" if (a // 24) % 2 else "band"], 0.02, rot=(0, 0, r + math.pi / 2))
    for a in range(0, 360, 45):
        r = math.radians(a)
        ground_light_at = (cx + math.cos(r) * 4.2, cy + math.sin(r) * 4.2)
        cyl(0.1, 0.05, (ground_light_at[0], ground_light_at[1], 0.97), P["band"], verts=10, bevel=0.01)
    ring(1.7, 0.05, (cx, cy, 0.95), P["band"])
    ring(4.5, 0.04, (cx, cy, 0.95), P["teal"])
    for a in (150, 210, 270, 330):                                                 # curved bench segments at the back
        r = math.radians(a)
        box((1.8, 0.5, 0.4), (cx + math.cos(r) * 3.7, cy + math.sin(r) * 3.7, 1.15), P["grey_dark"], 0.1, rot=(0, 0, r + math.pi / 2))
        box((1.8, 0.06, 0.06), (cx + math.cos(r) * 3.45, cy + math.sin(r) * 3.45, 1.37), P["teal"], 0.01, rot=(0, 0, r + math.pi / 2))
    for z in (1.6, 3.2, 4.7, 6.1, 7.5, 9.0):
        for a in (60, 180, 300):
            r = math.radians(a)
            rr = 1.26 - z * 0.026
            box((0.3, 0.08, 0.3), (tx + math.sin(r) * rr, ty - math.cos(r) * rr, z), P["win" if int(z * 2 + a) % 3 else "glow"], 0.02, rot=(0, 0, r))
    ladder(tx + 0.0, ty + 1.3, 0.6, 9.0, P)
    cable([(tx - 1.0, ty - 0.7, 9.6), (tx - 1.15, ty - 0.75, 0.6)], P, 0.05, "band")
    for i, z in enumerate((12.0, 12.4, 12.8)):
        ring(0.7 - i * 0.2, 0.03, (tx, ty, z), P["band"])
    sphere(0.14, (tx, ty, 12.35), P["glow"])
    for a in range(0, 360, 45):
        r = math.radians(a)
        cyl(0.04, 0.4, (tx + math.cos(r) * 1.8, ty + math.sin(r) * 1.8, 10.25), P["metal"], verts=6, bevel=0)
    ring(1.8, 0.035, (tx, ty, 10.45), P["metal"])
    box((1.6, 1.0, 1.1), (tx + 2.4, ty - 0.4, 0.55), P["grey_dark"], 0.08)          # relay cabinet at the tower foot
    window_grid(tx + 2.4, ty - 0.92, 0.65, 3, 2, P, cw=0.3, ch=0.2, gap=0.1, lit=("glow", "band", "seam", "glow", "teal"))
    cable([(tx + 1.6, ty - 0.4, 0.2), (tx + 1.0, ty - 0.4, 0.2)], P, 0.08)
    console(cx + 5.4, cy - 5.4, P)


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
    # detail: seams, a marquee of bulbs, a film-strip sign, studio lights, windows, roof kit, cable reels
    panel_seams(W, D, H, P)
    for i in range(12):
        sphere(0.08, (-4.6 + i * 0.4, front - 1.42, 3.12), P["glow" if i % 2 else "band"])
    neon_sign(3.2, front - 0.12, 3.75, 2.8, 0.75, P, bars=2)
    for i in range(5):                                                             # film strip
        box((0.34, 0.06, 0.34), (-0.2 + i * 0.0, front - 0.1, 0.9 + i * 0.5), P["band" if i % 2 else "teal"], 0.02)
    box((0.5, 0.1, 2.6), (-0.2, front - 0.05, 1.9), P["dark"], 0.03)
    window_grid(1.0, D / 2 + 0.02, 2.6, 10, 2, P)
    window_grid(-W / 2 - 0.02, 0.6, 2.8, 4, 2, P, facing="side")
    vent(W / 2 + 0.02, -1.6, 1.4, P, facing="side")
    for x in (-5.0, 0.2):                                                          # spotlights on stands by the stall
        cyl(0.05, 2.0, (x, front - 1.9, 1.0), P["metal"], verts=8, bevel=0)
        box((0.5, 0.4, 0.4), (x, front - 1.9, 2.1), P["grey_dark"], 0.06, rot=(0.4, 0, 0))
        box((0.38, 0.05, 0.28), (x, front - 1.69, 2.02), P["glow"], 0.01, rot=(0.4, 0, 0))
        for k in range(3):
            a = k * 2.1
            cyl(0.03, 0.6, (x + math.cos(a) * 0.2, front - 1.9 + math.sin(a) * 0.2, 0.25), P["metal"], verts=6, bevel=0, rot=(math.sin(a) * 0.6, -math.cos(a) * 0.6, 0))
    for y in (0.6, 2.2):
        cyl(0.5, 0.35, (W / 2 + 1.0, y, 0.5), P["grey"], verts=20, rot=(0, math.pi / 2, 0))   # cable reels
        cyl(0.3, 0.4, (W / 2 + 1.0, y, 0.5), P["band"], verts=20, rot=(0, math.pi / 2, 0))
    ladder(-W / 2 + 1.0, D / 2 + 0.12, 0.4, H, P)
    antenna_cluster(-W / 2 + 1.6, 2.2, 0.4 + H + 0.2, P, 2.0)
    for x in (2.2, 4.2):
        ground_light(x, front - 1.6, P, "band")
    console(5.4, front - 1.0, P)


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
    Y, O = mat("yellow", "#262d4a", 0.45, 0.3), mat("orange", "#ffb020", 0.4, glow=GLOW)
    cargo, head = mat("cargo", "#3a4055", 0.5, 0.3), mat("camhead", "#1a1f33", 0.5, 0.2)
    tire, arm, lens = mat("tire", "#0b0d14", 0.9), mat("arm", "#8a93ad", 0.3, 0.8), mat("lens", CYAN, 0.2, glow=GLOW)
    for sx in (-1, 1):                                                          # under-glow tubes and tail lights
        box((0.08, 3.4, 0.08), (sx * 1.1, 0, 0.98), P["teal"], 0.02)
        box((0.4, 0.08, 0.14), (sx * 0.8, 1.95, 1.4), P["band"], 0.02)
        box((0.36, 0.08, 0.16), (sx * 0.85, -1.95, 1.55), P["glow"], 0.02)
    box((1.5, 0.06, 0.06), (0, 0.8, 2.57), P["teal"], 0.01)
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


def _tag(n0, bone):
    for o in OBJS[n0:]:
        if "bone" not in o:
            o["bone"] = bone


def astronaut(P):
    """The chibi astronaut, neon edition: pale suit, glowing visor, glowing ear pods, cuffs, knee bands and soles.
    Feet at z=0, about 2.3 tall, facing -y. One skinned mesh on a small rig (root, hips, head, two arms, two legs) with
    three clips: idle, walk and type. Materials 'accent_red' and 'accent_visor' are recoloured per figure by the website."""
    suit, rim = mat("suit", "#cfd6ea", 0.5), mat("rim", "#141a30", 0.4, 0.3)
    red = mat("accent_red", "#f29b38", 0.4, glow=GLOW)
    visor = mat("accent_visor", "#f29b38", 0.15, 0.3, glow=1.2)
    blue, panel = mat("accent_blue", CYAN, 0.4, glow=GLOW), mat("panel", "#1a1f33", 0.45, 0.2)
    n = len(OBJS)
    sphere(0.62, (0, 0, 1.72), suit, (1, 0.95, 0.92))                         # helmet
    sphere(0.5, (0, -0.41, 1.7), rim, (0.97, 0.5, 0.83))                       # visor surround
    sphere(0.47, (0, -0.47, 1.7), visor, (0.9, 0.45, 0.72))                    # glowing visor
    ring(0.6, 0.035, (0, 0, 1.72), red, rot=(0, math.pi / 2, 0))               # light band over the helmet
    cyl(0.02, 0.4, (0.42, 0.25, 2.35), rim, verts=8, bevel=0)                  # antenna
    sphere(0.055, (0.42, 0.25, 2.57), red)
    for sx in (-1, 1):
        cyl(0.18, 0.16, (sx * 0.6, 0, 1.72), rim, rot=(0, math.pi / 2, 0))      # ear pods
        cyl(0.12, 0.18, (sx * 0.62, 0, 1.72), red, rot=(0, math.pi / 2, 0))
    _tag(n, "head"); n = len(OBJS)
    ring(0.25, 0.07, (0, 0, 1.13), rim)                                        # collar
    ring(0.27, 0.025, (0, 0, 1.13), blue)
    sphere(0.38, (0, 0, 0.8), suit, (1, 0.86, 1.08))                           # body
    box((0.36, 0.42, 0.5), (0, 0.32, 0.92), rim, 0.12)                         # backpack
    box((0.06, 0.05, 0.36), (0, 0.54, 0.92), red, 0.02)
    for sx in (-1, 1):
        cyl(0.05, 0.2, (sx * 0.1, 0.36, 1.2), panel, verts=10)                  # air tanks
    box((0.44, 0.12, 0.32), (0, -0.33, 0.86), panel, 0.06)                     # chest panel
    cyl(0.05, 0.06, (-0.12, -0.4, 0.92), red, verts=16, rot=(math.pi / 2, 0, 0))
    cyl(0.05, 0.06, (-0.12, -0.4, 0.8), blue, verts=16, rot=(math.pi / 2, 0, 0))
    for i in range(3):
        for j in range(2):
            box((0.06, 0.04, 0.06), (0.01 + i * 0.07, -0.4, 0.92 - j * 0.1), blue if (i + j) % 2 else rim, 0.01)
    ring(0.36, 0.03, (0, 0, 0.62), red)                                        # belt light
    _tag(n, "hips")
    for sx, side in ((-1, "R"), (1, "L")):
        n = len(OBJS)
        cyl(0.12, 0.42, (sx * 0.44, -0.02, 0.84), suit, verts=16, rot=(0, sx * 0.55, 0))   # arm
        ring(0.12, 0.04, (sx * 0.56, -0.04, 0.68), red, rot=(0, sx * 0.55, 0))           # glowing cuff
        sphere(0.14, (sx * 0.6, -0.05, 0.6), rim)                                        # glove
        _tag(n, "arm." + side); n = len(OBJS)
        cyl(0.14, 0.36, (sx * 0.17, 0, 0.32), suit, verts=16)                           # leg
        ring(0.14, 0.045, (sx * 0.17, 0, 0.36), red)                                    # glowing knee band
        sphere(0.17, (sx * 0.17, -0.06, 0.11), rim, (1, 1.3, 0.62))                     # boot
        cyl(0.16, 0.05, (sx * 0.17, -0.06, 0.03), red, verts=24)                        # glowing sole
        _tag(n, "leg." + side)
    _rig_astronaut()


def _rig_astronaut():
    parts = list(OBJS)
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.convert(target="MESH")                                      # bake the bevels
    for o in parts:
        o.vertex_groups.new(name=o["bone"]).add(range(len(o.data.vertices)), 1.0, "REPLACE")
    bpy.ops.object.join()
    body = bpy.context.active_object
    body.name = "astronaut_body"
    ad = bpy.data.armatures.new("astronaut_rig")
    arm = bpy.data.objects.new("astronaut_rig", ad)
    bpy.context.collection.objects.link(arm)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    for name, head, parent in (("root", (0, 0, 0), None), ("hips", (0, 0, 0.55), "root"), ("head", (0, 0, 1.15), "hips"),
                               ("arm.L", (0.34, 0, 1.0), "hips"), ("arm.R", (-0.34, 0, 1.0), "hips"),
                               ("leg.L", (0.17, 0, 0.5), "root"), ("leg.R", (-0.17, 0, 0.5), "root")):
        b = ad.edit_bones.new(name)
        b.head, b.tail, b.roll = head, (head[0], head[1], head[2] + 0.25), 0.0   # every bone points up: local X = left-right, Y = up
        if parent:
            b.parent = made[parent]
        made[name] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    body.parent = arm
    body.modifiers.new("rig", "ARMATURE").object = arm
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    anim = arm.animation_data_create()
    TAU = 2 * math.pi

    def clip(name, frames, pose):
        """pose(phase 0..TAU) -> {bone: (rot_x, rot_y, rot_z, lift)}; keyed every other frame, first = last so it loops."""
        act = bpy.data.actions.new(name)
        anim.action = act
        for f in range(1, frames + 2, 2):
            vals = pose(TAU * (f - 1) / frames)
            for pb in arm.pose.bones:
                rx, ry, rz, up = vals.get(pb.name, (0, 0, 0, 0))
                pb.rotation_euler = (rx, ry, rz)
                pb.location = (0, up, 0)
                pb.keyframe_insert("rotation_euler", frame=f)
                pb.keyframe_insert("location", frame=f)
        tr = anim.nla_tracks.new()
        tr.name = name
        tr.strips.new(name, 1, act).name = name
        anim.action = None

    s = math.sin
    clip("idle", 96, lambda p: {"hips": (0, 0, 0, 0.012 * s(p)), "head": (0.03 * s(p), 0.2 * s(p), 0, 0),
                                "arm.L": (0.06 * s(2 * p), 0, 0, 0), "arm.R": (-0.06 * s(2 * p), 0, 0, 0)})
    clip("walk", 24, lambda p: {"hips": (0.05, 0, 0.05 * s(p), 0.035 * abs(s(p))), "head": (-0.03, 0, -0.04 * s(p), 0),
                                "leg.L": (-0.65 * s(p), 0, 0, 0.07 * max(0, math.cos(p))), "leg.R": (0.65 * s(p), 0, 0, 0.07 * max(0, -math.cos(p))),
                                "arm.L": (0.6 * s(p), 0, 0, 0), "arm.R": (-0.6 * s(p), 0, 0, 0)})
    clip("type", 24, lambda p: {"hips": (0.04, 0, 0, 0.006 * s(p)), "head": (0.14 + 0.03 * s(p), 0.06 * s(p), 0, 0),
                                "arm.L": (-1.35 + 0.14 * s(2 * p), 0, 0, 0.02), "arm.R": (-1.35 + 0.14 * s(2 * p + math.pi), 0, 0, 0.02)})
    for pb in arm.pose.bones:
        pb.rotation_euler, pb.location = (0, 0, 0), (0, 0, 0)
    OBJS[:] = [arm, body]


def pup(P):
    """The pup in a helmet: golden face behind a round white helmet, little white suit, about 0.9 tall."""
    suit, rim = mat("suit", "#cfd6ea", 0.5), mat("pup_neon", "#ffb020", 0.4, glow=GLOW)
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
    fn(palette(*NEON[name]))
    bpy.ops.object.select_all(action="DESELECT")
    for o in OBJS:
        o.select_set(True)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}.glb")
    rigged = any(o.type == "ARMATURE" for o in OBJS)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=not rigged, export_yup=True,
                              export_animations=rigged, **(dict(export_animation_mode="NLA_TRACKS", export_skins=True) if rigged else {}))
    print("exported", path, len(OBJS), "parts")


BUILDS = (("habitat", habitat), ("factory", factory), ("github", github), ("claude", claude), ("chat", chat), ("media", media), ("rover", rover), ("astronaut", astronaut), ("pup", pup))
if __name__ == "__main__":
    only = os.environ.get("MOONBASE_ONLY", "").split(",") if os.environ.get("MOONBASE_ONLY") else None
    for name, fn in BUILDS:
        if not only or name in only:
            build(name, fn)
