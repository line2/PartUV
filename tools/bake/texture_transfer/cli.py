# -*- coding: utf-8 -*-
"""CLI：唯一对外入口。解析参数 -> core.rebake -> write.write_outputs。"""

from __future__ import annotations

import os
import sys
import time

from .config import JobConfig
from .core import log, rebake
from .write import write_outputs


def _redirect_stdout(path: str):
    handle = open(path, "w", encoding="utf-8", buffering=1)
    os.dup2(handle.fileno(), 1)
    return handle


def main(argv=None) -> int:
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else argv
    config = JobConfig.from_cli(raw)

    if config.log_path:
        _redirect_stdout(config.log_path)

    t0 = time.perf_counter()
    log("rebake: size=%d samples=%d keep_uv=%s"
        % (config.texture_size, config.samples, config.keep_uv))

    try:
        result = rebake(config)
    except Exception as exc:                     # noqa: BLE001
        print("FAILED: %s" % exc, flush=True)
        import traceback
        traceback.print_exc()
        return 2

    log("object: %s" % result.object_name)
    log("  uv: layer=%s kept=%s islands=%d coverage=%.2f%%"
        % (result.uv_layer, result.uv_kept, result.uv_islands,
           result.uv_coverage * 100.0))

    write_outputs(result, config)

    log("done in %.1fs -> %s" % (time.perf_counter() - t0,
                                 config.resolved_output_folder()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())