#!/usr/bin/env python3
"""Run the PartUV pipeline (preprocess -> unwrap -> save) on one mesh and record stage timings."""
import argparse
import json
import os
import sys
import time
import traceback

import numpy as np

REPO = os.environ.get("PARTUV_REPO", os.path.dirname(os.path.abspath(__file__)))
# Append (not prepend) so the installed `partuv` wheel wins over the repo's source dir,
# while `preprocess_utils` (repo only) still resolves.
sys.path.append(REPO)

import torch  # noqa: E402
import trimesh  # noqa: E402

from preprocess_utils.partfield_official.run_PF import PFInferenceModel  # noqa: E402
from partuv.preprocess import preprocess, save_results  # noqa: E402
import partuv  # noqa: E402


def stamp():
    return time.perf_counter()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=float, default=1.25)
    ap.add_argument("--config", default=os.path.join(REPO, "config", "config.yaml"))
    ap.add_argument("--sample-on-faces", type=int, default=10)
    ap.add_argument("--sample-batch", type=int, default=20000,
                    help="faces per PartField batch; each face yields sample_on_faces points")
    ap.add_argument("--ckpt", default="model_objaverse.ckpt")
    ap.add_argument("--timing", default=None)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    timing = {"mesh": args.mesh, "threshold": args.threshold,
              "sample_on_faces": args.sample_on_faces, "sample_batch": args.sample_batch}

    print(f"[env] torch {torch.__version__} cuda={torch.cuda.is_available()}", flush=True)
    if torch.cuda.is_available():
        print(f"[env] gpu {torch.cuda.get_device_name(0)} "
              f"{torch.cuda.get_device_properties(0).total_memory/2**30:.2f} GiB", flush=True)

    t_all = stamp()
    t = stamp()
    pf_model = PFInferenceModel(device="cuda" if torch.cuda.is_available() else "cpu",
                                checkpoint_path=args.ckpt)
    timing["pf_model_load_s"] = round(stamp() - t, 3)
    print(f"[pf] model loaded in {timing['pf_model_load_s']}s", flush=True)

    t = stamp()
    mesh, tree_file, tree_dict, pre_times = preprocess(
        args.mesh, pf_model, args.out,
        save_tree_file=True, save_processed_mesh=True,
        sample_on_faces=args.sample_on_faces,
        sample_batch_size=args.sample_batch,
        merge_vertices_epsilon=None,
    )
    timing["preprocess_s"] = round(stamp() - t, 3)
    timing["preprocess_breakdown_s"] = {k: round(v, 3) for k, v in pre_times.items()}
    V = np.asarray(mesh.vertices, dtype=np.float64, order="F")
    F = np.asarray(mesh.faces, dtype=np.int32, order="F")
    timing["mesh_after_preprocess"] = {"V": int(V.shape[0]), "F": int(F.shape[0])}
    print(f"[pre] done {timing['preprocess_s']}s breakdown={timing['preprocess_breakdown_s']} "
          f"V={V.shape} F={F.shape}", flush=True)
    if torch.cuda.is_available():
        timing["gpu_peak_gb_preprocess"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)

    t = stamp()
    final_parts, individual_parts = partuv.pipeline_numpy(
        V=V, F=F, tree_dict=tree_dict, configPath=args.config, threshold=args.threshold
    )
    timing["unwrap_s"] = round(stamp() - t, 3)
    timing["charts"] = int(final_parts.num_components)
    timing["individual_parts"] = len(individual_parts)
    timing["distortion"] = float(final_parts.distortion)
    print(f"[unwrap] done {timing['unwrap_s']}s charts={timing['charts']} "
          f"parts={timing['individual_parts']} distortion={timing['distortion']:.4f}", flush=True)
    if torch.cuda.is_available():
        timing["gpu_peak_gb_unwrap"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)

    t = stamp()
    written = save_results(args.out, final_parts, individual_parts)
    timing["save_s"] = round(stamp() - t, 3)
    timing["written"] = [os.path.basename(str(p)) for p in written]

    timing["total_s"] = round(stamp() - t_all, 3)
    timing["status"] = "ok"
    print("[timing] " + json.dumps(timing), flush=True)
    if args.timing:
        with open(args.timing, "w") as fh:
            json.dump(timing, fh, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        print("[FATAL]\n" + tb, flush=True)
        sys.exit(1)