# -*- coding: utf-8 -*-
"""bpy 重烘焙管线。

对外只有 CLI；Python API 供内部复用，两边共用 `JobConfig`。

    from texture_transfer import JobConfig, rebake

    cfg = JobConfig(dest_mesh_path="a.obj", keep_uv=True, texture_size=2048)
    result = rebake(cfg)                  # 只在内存里，不写盘
    result.images["BaseColor"].array      # uint8 (H, W, 4)
    result.images["BaseColor"].png_bytes  # 权威 PNG 字节

需要文件时再调：

    from texture_transfer import write_outputs
    write_outputs(result, cfg)

注意：`bake` 相关符号是惰性导出的（PEP 562），所以 `import texture_transfer.config`
不会触发 bpy 导入，一致性测试可以在普通 Python 里跑。
"""

from importlib import import_module

from .config import CHANNELS, JobConfig

_LAZY = {
    "BakeImage": (".core", "BakeImage"),
    "JobResult": (".core", "JobResult"),
    "rebake": (".core", "rebake"),
    "uv_stats": (".core", "uv_stats"),
    "write_outputs": (".write", "write_outputs"),
}

__all__ = ["CHANNELS", "JobConfig"] + sorted(_LAZY)


def __getattr__(name):
    if name in _LAZY:
        module, attr = _LAZY[name]
        return getattr(import_module(module, __name__), attr)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(set(__all__))