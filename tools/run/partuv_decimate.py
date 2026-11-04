"""Decimate an OBJ to a target triangle count with Blender's collapse decimator."""
import bpy
import os
import sys


def args():
    return sys.argv[sys.argv.index("--") + 1:]


src, dst, target = args()[0], args()[1], int(args()[2])

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=src)
objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
if len(objs) > 1:
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
obj = bpy.context.view_layer.objects.active
obj.data.materials.clear()

before = len(obj.data.polygons)
mod = obj.modifiers.new("dec", "DECIMATE")
mod.decimate_type = "COLLAPSE"
mod.ratio = min(1.0, target / max(before, 1))
mod.use_collapse_triangulate = True
bpy.context.view_layer.objects.active = obj
bpy.ops.object.modifier_apply(modifier=mod.name)
after = len(obj.data.polygons)

os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.wm.obj_export(filepath=dst, export_selected_objects=True,
                      export_materials=False, export_normals=False,
                      export_uv=False, export_triangulated_mesh=True)
print(f"[decimate] {before} -> {after} tris -> {dst}")