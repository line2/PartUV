#!/usr/bin/env python3
"""Call the C++ pipeline directly with a saved tree (skips PartField inference).

usage: run_core.py <mesh.obj> <tree.bin> <out_dir> [threshold]
Prints wall time and peak RSS of the process (ru_maxrss).
"""
import os
import resource
import struct
import sys
import time

import numpy as np
import trimesh

import partuv  # noqa: E402


def load_tree(path):
    with open(path, "rb") as fh:
        n = struct.unpack("<i", fh.read(4))[0]
        arr = np.frombuffer(fh.read(12 * n), dtype="<i4").reshape(n, 3)
    return {int(i): {"left": int(l), "right": int(r)} for i, l, r in arr}


def main():
    mesh_path, tree_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    thr = float(sys.argv[4]) if len(sys.argv) > 4 else 1.25
    default_cfg = os.path.join(os.environ.get("PARTUV_WORK", os.path.expanduser("~/partuv_work")), "PartUV", "config", "config.yaml")
    cfg = sys.argv[5] if len(sys.argv) > 5 else default_cfg

    mesh = trimesh.load(mesh_path, process=False, force="mesh")
    V = np.asarray(mesh.vertices, dtype=np.float64)
    F = np.asarray(mesh.faces, dtype=np.int32)
    tree = load_tree(tree_path)
    print(f"[input] V={V.shape} F={F.shape} tree={len(tree)} nodes", flush=True)

    t0 = time.perf_counter()
    final_parts, individual_parts = partuv.pipeline_numpy(
        np.asfortranarray(V), np.asfortranarray(F), tree, cfg, thr)
    dt = time.perf_counter() - t0
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # MiB

    print(f"[done] {dt:.1f}s  peak RSS {peak:.0f} MiB  "
          f"parts={len(individual_parts)} charts={final_parts.num_components} "
          f"distortion={final_parts.distortion:.4f}")

    os.makedirs(out_dir, exist_ok=True)
    from partuv.preprocess import save_results
    save_results(out_dir, final_parts, individual_parts)
    print(f"[saved] {out_dir}")


if __name__ == "__main__":
    main()


