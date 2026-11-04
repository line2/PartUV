# -*- coding: utf-8 -*-
"""blender_texture_transfer.py — 贴图迁移 / 重烘焙（命令行入口）

用法：

    blender -b --factory-startup --python-exit-code 2 ^
        --python blender_texture_transfer.py -- ^
        --dest_mesh_path target_with_uv.obj ^
        --source_mesh_path original_textured.obj ^
        --keep_uv --output_folder OUT --texture_size 2048 --samples 32

只做三通道：BaseColor / Roughness / Metallic。

本文件只是入口薄壳：把仓库根目录放进 sys.path，然后把参数交给
`texture_transfer.cli.main`。真正的实现在 texture_transfer/ 包里，
也可以直接在 Blender 内 import 使用：

    from texture_transfer import JobConfig, rebake
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from texture_transfer.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())