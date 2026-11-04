# texture_transfer — 贴图迁移 / 重烘焙

三通道：**BaseColor / Roughness / Metallic**（Normal、AO 已移除）。
Blender **4.2.9 LTS** 验证通过，兼容 5.2.x。

命名与参数风格对齐 `blender_texture_transfer.py`：字段名 = 命令行参数名，全下划线。

## 结构

```
blender_texture_transfer.py      命令行入口（薄壳）
texture_transfer/
    config.py    JobConfig（唯一参数来源）+ CLI 生成 + 校验   [不依赖 bpy]
    core.py      rebake(cfg) -> JobResult                     [需要 bpy]
    write.py     write_outputs(result, cfg) -> 落盘           [需要 bpy]
    cli.py       参数 -> core -> write -> 退出码
    tests/
        test_cli_parity.py    纯 python，验证 CLI 与 dataclass 一致
        test_api_memory.py    在 Blender 内，验证 API 不写盘
```

## 命令行（唯一对外入口）

```powershell
blender -b --factory-startup --python-exit-code 2 `
  --python blender_texture_transfer.py -- `
  --dest_mesh_path   target_with_uv.obj `
  --source_mesh_path original_textured.obj `
  --keep_uv --output_folder OUT --texture_size 2048 --samples 32 --log_path bake.log
```

`--python-exit-code 2` 是必须的：Blender 默认吞掉脚本退出码。

| 参数 | 默认 | 说明 |
|---|---|---|
| `--dest_mesh_path` | 选中物体 | 目标网格 |
| `--source_mesh_path` | 同目标 | 贴图来源网格 |
| `--output_folder` | `<blend>/Baked_PBR` | 输出根目录 |
| `--texture_size` | 2048 | 贴图边长 |
| `--samples` | 32 | Cycles 采样数 |
| `--keep_uv` | 关 | 沿用目标网格已有 UV |
| `--margin_px` | 16 | 岛边界外扩像素 |
| `--cage_ratio` | 0.005 | cage 挤出 = 最大尺寸 × 该值 |
| `--uv_margin` | 0.0 | Smart UV 岛间距，**必须为 0** |
| `--uv_angle` | 90.0 | Smart UV 角度阈值 |
| `--device` | CPU | CPU / GPU |
| `--no_export_obj` | 关 | 不导出网格 |
| `--no_overwrite` | 关 | 不覆盖已存在文件 |
| `--log_path` | 无 | stdout 重定向（ASCII 安全） |

帮助文本刻意保持 ASCII：Blender 在 Windows 上用 cp936 写 stdout，中文会抛
`UnicodeEncodeError`，连 `--help` 都会崩。

## Python API（内部复用）

```python
from texture_transfer import JobConfig, rebake, write_outputs

cfg = JobConfig(dest_mesh_path="a.obj", source_mesh_path="src.obj",
                keep_uv=True, texture_size=2048, samples=32)
result = rebake(cfg)                       # 只在内存，不写盘

result.uv_layer        # 'UVMap'
result.uv_islands      # 14488
result.uv_coverage     # 0.5763
result.timings         # {'BaseColor': 2.08, ...}

img = result.images["BaseColor"]
img.array              # numpy uint8 (H, W, 4)
img.png_bytes          # 权威 PNG 字节（core 用临时文件编码后删除）
img.path               # 未落盘时 None

write_outputs(result, cfg)                 # 需要文件时再调
result.obj_path        # 落盘后才有值
```

分层：`core` 不写最终产物，`write` 负责 PNG / MTL / OBJ / manifest。

## 一致性怎么保证

`JobConfig` 是唯一事实来源，argparse 选项由 dataclass 字段自动生成。

`tests/test_cli_parity.py`（不需要 Blender）：

```
ok  option/dest parity: 14 fields
ok  defaults parse (16 options)
ok  negate flags
ok  validation rejects bad input
ALL PASSED
```

加参数只改 `config.py` 一处，测试会立刻发现两边不一致。

## 验证记录（Blender 4.2.9 LTS）

CLI，1024²，8 spp：

```
object: mesh_uv.obj_Rebaked
  uv: layer=UVMap kept=True islands=14488 coverage=57.63%
  baked BaseColor 3.67s / Roughness 2.99s / Metallic 2.82s
  wrote 3 PNG + baked.obj + manifest
done in 22.7s
```

产物与重构前字节数完全一致（BaseColor 1,455,163 B）。

API，512²，4 spp：

```
RESULT uv=UVMap kept=True islands=14488 coverage=0.5763
  BaseColor (512,512,4) png=425484 nonzero=95.6%
  Roughness (512,512,4) png=9419   nonzero=96.3%   (常量 0.5)
  Metallic  (512,512,4) png=3686   nonzero=0.0%    (常量 0)
OK no files written by rebake()
```

## 三个必须保留的坑位

1. **`--uv_margin` 必须为 0**（不 `--keep_uv` 时）。margin 按每个岛累加，
   该模型 8,406 个岛，`0.012` 会让覆盖率从 57.6% 掉到 3.1%。
2. **UV 岛统计必须按面做并查集**。按顶点做会得到 38,741（正确 14,488）。
3. **导出的 OBJ 必须补 `usemtl`**。`export_materials=False` 时 Blender 不写 `usemtl`，
   MTL 会变成孤儿，导入端一张贴图都不读。

## 已知限制

- `rebake()` 成功后会把 target 物体留在场景里供 `write_outputs` 导出；
  批量调用需要自行清理。
- v1 只支持单 target；多物体由调用方循环。
- 4.2 便携版在 `--factory-startup` 下退出时会刷 `Unable to delete file`
  （Blender 清理 `%TEMP%` 权限不足），与管线无关，退出码正常。