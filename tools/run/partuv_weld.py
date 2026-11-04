"""Weld duplicate vertices (merge by distance) and report the resulting component count."""
import bpy
import sys

args = sys.argv[sys.argv.index("--") + 1:]
src, dst, thr = args[0], args[1], float(args[2])

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=src)
obj = [o for o in bpy.context.selected_objects if o.type == "MESH"][0]
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj

before = (len(obj.data.vertices), len(obj.data.polygons))
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=thr)
bpy.ops.object.mode_set(mode="OBJECT")
after = (len(obj.data.vertices), len(obj.data.polygons))
print(f"[weld] verts {before[0]} -> {after[0]}, faces {before[1]} -> {after[1]} (thr={thr})", flush=True)

bpy.ops.wm.obj_export(filepath=dst, export_selected_objects=True, export_materials=False,
                      export_normals=False, export_uv=False, export_triangulated_mesh=True)
print(f"[weld] wrote {dst}", flush=True)