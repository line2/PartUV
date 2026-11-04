"""Bake the original asset onto a packed PartUV result, then render three views.

The UVs are already packed by the caller (see pack_to_obj.py), so this script skips the
packing step and goes straight to the texture transfer.

Usage:
  blender -b --factory-startup --python bake_and_render.py -- <target.obj> <source.obj> <out_dir> [size]
"""
import math
import os
import sys

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
TARGET, SOURCE, OUT = argv[0], argv[1], argv[2]
SIZE = int(argv[3]) if len(argv) > 3 else 4096

os.makedirs(OUT, exist_ok=True)
stem = os.path.splitext(os.path.basename(TARGET))[0]


# ------------------------------------------------------------------ bake
def bake():
    sys.argv = [
        "blender", "--",
        "--dest_mesh_path", TARGET,
        "--source_mesh_path", SOURCE,
        "--keep_uv",
        "--output_folder", OUT,
        "--texture_size", str(SIZE),
        "--samples", "32",
        "--log_path", os.path.join(OUT, "bake.log"),
    ]
    addon_entry = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "blender_texture_transfer.py")
    src = open(addon_entry, encoding="utf-8").read()
    exec(compile(src, addon_entry, "exec"), {"__name__": "__main__", "__file__": addon_entry})


bake()

baked = None
for f in os.listdir(OUT):
    if f.lower().endswith(".obj") and "baked" in f.lower():
        baked = os.path.join(OUT, f)
if baked is None:
    import glob
    cand = sorted(glob.glob(os.path.join(OUT, "*.obj")))
    baked = cand[-1] if cand else None
print(f"[render] baked obj: {baked}", flush=True)

# ------------------------------------------------------------------ render
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 64
scene.cycles.device = "CPU"

before = set(bpy.data.objects)
bpy.ops.wm.obj_import(filepath=baked)
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
    scene.render.filepath = os.path.join(OUT, f"{stem}_{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[render] {name} done", flush=True)