"""Render a baked OBJ with the neutral studio setup used for the earlier previews.

Usage: blender -b --factory-startup --python render_views.py -- <obj> <out_dir> [prefix]
"""
import math
import os
import sys

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
OBJ, OUT = argv[0], argv[1]
PREFIX = argv[2] if len(argv) > 2 else "view"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 64
scene.cycles.device = "CPU"

before = set(bpy.data.objects)
bpy.ops.wm.obj_import(filepath=OBJ)
obj = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
print(f"[render] {len(obj.data.polygons)} faces, "
      f"materials={[m.name for m in obj.data.materials]}", flush=True)

pts = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
lo = mathutils.Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = mathutils.Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center = (lo + hi) * 0.5
radius = (hi - lo).length * 0.5

scene.world = bpy.data.worlds.new("W")
scene.world.use_nodes = True
bg = scene.world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.42, 0.44, 0.47, 1)
bg.inputs[1].default_value = 1.0

for pos, energy, size in (
    ((2.0, -2.4, 1.8), 12000, 8.0),
    ((-2.4, -1.6, 0.6), 5000, 9.0),
    ((0.2, 2.6, 1.6), 8000, 7.0),
):
    ld = bpy.data.lights.new("area", type="AREA")
    ld.energy = energy
    ld.size = size
    lo_ = bpy.data.objects.new("area", ld)
    scene.collection.objects.link(lo_)
    lo_.location = center + mathutils.Vector(pos) * radius
    lo_.rotation_euler = (center - lo_.location).to_track_quat("-Z", "Y").to_euler()

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 68
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x = 1100
scene.render.resolution_y = 1550

for name, d in {
    "front": (0.0, -1.0, 0.10),
    "three_quarter": (0.75, -0.75, 0.30),
    "head": (0.35, -0.9, 0.45),
}.items():
    dist = radius * (2.3 if name != "head" else 1.05)
    lift = center + mathutils.Vector((0, 0, radius * 0.85)) if name == "head" else center
    p = lift + mathutils.Vector(d).normalized() * dist
    cam.location = p
    cam.rotation_euler = (lift - p).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(OUT, f"{PREFIX}_{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[render] {name} done", flush=True)