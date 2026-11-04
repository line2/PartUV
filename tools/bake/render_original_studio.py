"""Studio render of the ORIGINAL model.obj (its own UVs + texture), Cycles CPU.

Usage:
  blender -b --factory-startup --python render_original_studio.py -- <model.obj> <out_dir> [res] [samples]
"""
import bpy
import math
import os
import sys

import mathutils

args = sys.argv[sys.argv.index("--") + 1:]
model_path, out_dir = args[0], args[1]
res_x = int(args[2]) if len(args) > 2 else 1200
samples = int(args[3]) if len(args) > 3 else 96
os.makedirs(out_dir, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=model_path)
meshes = [o for o in bpy.context.selected_objects if o.type == "MESH"]
if len(meshes) > 1:
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
obj = bpy.context.view_layer.objects.active
print(f"[model] {model_path} faces={len(obj.data.polygons)} verts={len(obj.data.vertices)}", flush=True)
print(f"[mat] {[m.name for m in obj.data.materials]}", flush=True)

for m in obj.data.materials:
    if not m.use_nodes:
        continue
    for n in m.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image:
            print(f"[mat] tex={n.image.name} {tuple(n.image.size)}", flush=True)
        if n.type == "BSDF_PRINCIPLED":
            n.inputs["Roughness"].default_value = 0.55
            n.inputs["Metallic"].default_value = 0.0
            try:
                n.inputs["Specular IOR Level"].default_value = 0.35
            except KeyError:
                pass

# --- bounds ---
bbox = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
lo = mathutils.Vector((min(v.x for v in bbox), min(v.y for v in bbox), min(v.z for v in bbox)))
hi = mathutils.Vector((max(v.x for v in bbox), max(v.y for v in bbox), max(v.z for v in bbox)))
center = (lo + hi) * 0.5
size = hi - lo
radius = max(size) * 0.5
print(f"[bounds] size={tuple(round(v,2) for v in size)} center={tuple(round(v,2) for v in center)}", flush=True)

# --- ground plane (catches shadow, subtle reflection) ---
bpy.ops.mesh.primitive_plane_add(size=radius * 12, location=(center.x, center.y, lo.z - 0.01))
ground = bpy.context.active_object
gmat = bpy.data.materials.new("ground")
gmat.use_nodes = True
gn = gmat.node_tree.nodes
gbsdf = gn["Principled BSDF"]
gbsdf.inputs["Base Color"].default_value = (0.035, 0.037, 0.042, 1.0)
gbsdf.inputs["Roughness"].default_value = 0.32
ground.data.materials.append(gmat)

# --- world: soft neutral gradient-ish ---
scene = bpy.context.scene
world = bpy.data.worlds.new("studio")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.015, 0.017, 0.022, 1.0)
bg.inputs[1].default_value = 0.6
scene.world = world

# --- lights (relative to model size) ---
def area_light(name, loc, energy, size_xy, color=(1, 1, 1)):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.size = size_xy
    data.color = color
    o = bpy.data.objects.new(name, data)
    scene.collection.objects.link(o)
    o.location = loc
    direction = center - o.location
    o.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return o

R = radius * 4
# Light power has to scale with the squared distance: the figure is 60 Blender units tall.
P = R * R
key = area_light("key", center + mathutils.Vector((-R * 0.85, -R * 0.75, R * 0.85)), 44 * P, radius * 2.0, (1.0, 0.97, 0.93))
fill = area_light("fill", center + mathutils.Vector((R * 0.95, -R * 0.55, R * 0.35)), 7 * P, radius * 3.0, (0.92, 0.95, 1.0))
rim = area_light("rim", center + mathutils.Vector((R * 0.15, R * 1.0, R * 0.75)), 26 * P, radius * 1.6, (0.95, 0.97, 1.0))
print(f"[lights] key={key.data.energy} fill={fill.data.energy} rim={rim.data.energy} at R={R:.2f}", flush=True)

# --- render settings ---
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = samples
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 6
scene.render.resolution_x = res_x
scene.render.resolution_y = int(res_x * 1.25)
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"

# --- camera ---
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 85
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def shoot(name, yaw_deg, pitch=0.12, margin=1.24):
    a = math.radians(yaw_deg)
    # frame the whole figure vertically
    dist = (max(size.z, size.x) * 0.5 * margin) / math.tan(cam_data.angle * 0.5)
    eye = center + mathutils.Vector((math.sin(a) * dist, -math.cos(a) * dist, size.z * pitch))
    cam.location = eye
    cam.rotation_euler = (center - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(out_dir, name)
    bpy.ops.render.render(write_still=True)
    print(f"[render] {name}", flush=True)


shoot("original_front.png", 0.0)
shoot("original_three_quarter.png", 38.0)
print("[done]", flush=True)

