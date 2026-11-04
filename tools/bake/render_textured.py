"""Render an OBJ (with its baked texture) to a PNG for visual verification."""
import bpy
import math
import os
import sys

import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
src, out_png = args[0], args[1]
res = int(args[2]) if len(args) > 2 else 900
angle_deg = float(args[3]) if len(args) > 3 else 0.0

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=src)
meshes = [o for o in bpy.context.selected_objects if o.type == "MESH"]
if len(meshes) > 1:
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
obj = bpy.context.view_layer.objects.active

# material -> emission of the baked texture (flat, colour-accurate)
img = None
for m in obj.data.materials:
    if m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                img = n.image
if img is None:
    raise RuntimeError("no texture material on the imported mesh")
print(f"[tex] {img.name} {tuple(img.size)} channels", flush=True)

mat = bpy.data.materials.new("flat")
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
emit = nt.nodes.new("ShaderNodeEmission")
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
obj.data.materials.clear()
obj.data.materials.append(mat)

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 8
scene.cycles.use_denoising = False
scene.render.resolution_x = res
scene.render.resolution_y = res
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"

world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.02, 0.02, 1)
scene.world = world

cam_data = bpy.data.cameras.new("cam")
cam_data.angle = math.radians(35)
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

import mathutils
bbox = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
center = sum(bbox, mathutils.Vector()) / 8.0
radius = max((v - center).length for v in bbox)
dist = radius * 1.25 / math.tan(cam_data.angle / 2.0)
a = math.radians(angle_deg)
cam.location = center + mathutils.Vector((math.sin(a) * dist, -math.cos(a) * dist, 0.12 * dist))
cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()

scene.render.filepath = out_png
bpy.ops.render.render(write_still=True)
print(f"[render] {out_png}", flush=True)