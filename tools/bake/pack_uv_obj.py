"""Pack the unpacked PartUV UV layout into [0,1] and re-export, so a keep-uv bake is valid."""
import os
import sys

import bpy

SRC = r"C:\Users\JdSc-local\Project\blend-baking\weld_uv.obj"
DST = r"C:\Users\JdSc-local\Project\blend-baking\weld_uv_packed.obj"
MARGIN = float(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else 0.004

bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects)
bpy.ops.wm.obj_import(filepath=SRC)
obj = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]

uvl = obj.data.uv_layers.active
us = [d.uv[0] for d in uvl.data]
vs = [d.uv[1] for d in uvl.data]
print(f"[pack] before: u [{min(us):.3f},{max(us):.3f}] v [{min(vs):.3f},{max(vs):.3f}]", flush=True)

bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.pack_islands(margin=MARGIN, rotate=True, scale=True)
bpy.ops.object.mode_set(mode="OBJECT")

us = [d.uv[0] for d in uvl.data]
vs = [d.uv[1] for d in uvl.data]
print(f"[pack] after : u [{min(us):.3f},{max(us):.3f}] v [{min(vs):.3f},{max(vs):.3f}]", flush=True)

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.wm.obj_export(filepath=DST, export_selected_objects=True, export_materials=False,
                      export_uv=True, export_normals=True)
print(f"[pack] wrote {DST}", flush=True)