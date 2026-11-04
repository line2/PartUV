"""Baseline: Smart UV Project + pack on the same mesh, measured with the same code path."""
import bpy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from partuv_pack_metrics import stats, uv_area_sum, uv_island_count  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
src, out_dir, angle = args[0], args[1], float(args[2]) if len(args) > 2 else 66.0
margin = float(args[3]) if len(args) > 3 else 0.001
os.makedirs(out_dir, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=src)
obj = [o for o in bpy.context.selected_objects if o.type == "MESH"][0]
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj

bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.0)  # 66 degrees
bpy.ops.uv.select_all(action="SELECT")
bpy.ops.uv.pack_islands(margin=margin)
bpy.ops.object.mode_set(mode="OBJECT")

s = stats(obj)
s["method"] = "smart_uv_project+pack"
print("[baseline] " + json.dumps(s), flush=True)

bpy.ops.wm.obj_export(filepath=os.path.join(out_dir, "smartuv_packed.obj"),
                      export_selected_objects=True, export_materials=False,
                      export_normals=False, export_uv=True)
with open(os.path.join(out_dir, "baseline_stats.json"), "w") as fh:
    json.dump(s, fh, indent=2)

# checker render for visual comparison
import math
from partuv_pack_metrics import add_checker_material, setup_render, frame_object  # noqa: E402
add_checker_material(obj)
scene = bpy.context.scene
setup_render(scene)
cam_data = bpy.data.cameras.new("cam")
cam_data.angle = math.radians(35)
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
frame_object(cam, obj, 0.0)
scene.render.filepath = os.path.join(out_dir, "uv_checker_front.png")
bpy.ops.render.render(write_still=True)
print("[baseline] render done", flush=True)