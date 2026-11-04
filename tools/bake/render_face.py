"""Close-up render of the head for texture sharpness comparison.

Usage: blender -b -P render_face.py -- <obj> <out_dir> <prefix> [lift] [dist] [lens]
  lift/dist are fractions of the bbox radius.
"""
import os
import sys

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
OBJ, OUT, PREFIX = argv[0], argv[1], argv[2]
LIFT = float(argv[3]) if len(argv) > 3 else 0.62
DIST = float(argv[4]) if len(argv) > 4 else 0.90
LENS = float(argv[5]) if len(argv) > 5 else 85.0
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 96
scene.cycles.device = "CPU"
scene.render.resolution_x = 1200
scene.render.resolution_y = 1400

before = set(bpy.data.objects)
bpy.ops.wm.obj_import(filepath=OBJ)
obj = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]

pts = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
lo = mathutils.Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = mathutils.Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center = (lo + hi) * 0.5
radius = (hi - lo).length * 0.5
target = center + mathutils.Vector((0, 0, radius * LIFT))

scene.world = bpy.data.worlds.new("W")
scene.world.use_nodes = True
bg = scene.world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.42, 0.44, 0.47, 1)
bg.inputs[1].default_value = 1.0

for pos, energy, size in (
    ((1.6, -2.2, 1.4), 9000, 6.0),
    ((-2.0, -1.4, 0.5), 4000, 7.0),
    ((0.2, 2.2, 1.4), 6000, 6.0),
):
    ld = bpy.data.lights.new("area", type="AREA")
    ld.energy = energy
    ld.size = size
    lo_ = bpy.data.objects.new("area", ld)
    scene.collection.objects.link(lo_)
    lo_.location = target + mathutils.Vector(pos) * radius * 0.5
    lo_.rotation_euler = (target - lo_.location).to_track_quat("-Z", "Y").to_euler()

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = LENS
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

d = mathutils.Vector((0.28, -1.0, 0.12)).normalized()
cam.location = target + d * radius * DIST
cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()

scene.render.filepath = os.path.join(OUT, f"{PREFIX}_face.png")
bpy.ops.render.render(write_still=True)
print(f"[face] wrote {scene.render.filepath}", flush=True)