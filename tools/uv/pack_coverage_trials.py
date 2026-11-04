"""Compare UV packing margins by resulting coverage (sum of UV triangle areas)."""
import bpy

SRC = r"C:\Users\JdSc-local\Project\blend-baking\weld_uv.obj"


def coverage(obj):
    me = obj.data
    uvl = me.uv_layers.active
    area = 0.0
    for poly in me.polygons:
        us = [tuple(uvl.data[li].uv) for li in poly.loop_indices]
        acc = 0.0
        for i in range(len(us)):
            x1, y1 = us[i]
            x2, y2 = us[(i + 1) % len(us)]
            acc += x1 * y2 - x2 * y1
        area += abs(acc) * 0.5
    return area


def load():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=SRC)
    obj = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


for label, margin in (("16px", 0.0039), ("12px", 0.0029), ("8px", 0.0020),
                      ("6px", 0.0015), ("4px", 0.0010)):
    obj = load()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(margin=margin, rotate=True, scale=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    cov = coverage(obj)
    print(f"[cov] margin {label:5s} -> {cov*100:6.2f}%  ({cov*4096*4096/1e6:.2f} M texels)", flush=True)