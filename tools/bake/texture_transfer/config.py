# -*- coding: utf-8 -*-
"""配置：JobConfig 是 CLI 与 Python API 的唯一事实来源。

命名沿用 `blender_texture_transfer.py` 的风格：字段与命令行参数同名、全下划线。
本模块**不 import bpy**，因此一致性测试可以脱离 Blender 运行。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, fields
from typing import Any, Optional

# 固定三通道：刻意不支持 Normal / AO
CHANNELS = ("BaseColor", "Roughness", "Metallic")


def _f(default: Any, flag: str, help_text: str, **extra):
    return field(default=default, metadata={"flag": flag, "help": help_text, **extra})


@dataclass
class JobConfig:
    """一次贴图迁移任务的全部参数。

    CLI 与 API 共用本类：argparse 选项由字段自动生成，两边不可能参数漂移。
    """

    dest_mesh_path: Optional[str] = _f(
        None, "--dest_mesh_path", "target mesh path; defaults to the mesh selected in Blender")
    source_mesh_path: Optional[str] = _f(
        None, "--source_mesh_path", "texture source mesh; defaults to the target itself (bake in place)")
    output_folder: Optional[str] = _f(
        None, "--output_folder", "output root folder; defaults to <blend>/Baked_PBR")
    texture_size: int = _f(2048, "--texture_size", "output texture edge length in pixels")
    samples: int = _f(32, "--samples", "Cycles samples")
    keep_uv: bool = _f(
        False, "--keep_uv", "keep the existing UV layout instead of running Smart UV")
    margin_px: int = _f(16, "--margin_px", "UV island border padding in pixels")
    cage_ratio: float = _f(
        0.005, "--cage_ratio", "cage extrusion = max object dimension * this ratio")
    uv_margin: float = _f(
        0.0, "--uv_margin", "Smart UV island margin; must be 0 (thousands of islands eat the atlas)")
    uv_angle: float = _f(90.0, "--uv_angle", "Smart UV angle limit in degrees")
    device: str = _f("CPU", "--device", "bake device: CPU or GPU")
    export_obj: bool = _f(
        True, "--no_export_obj", "do not export the baked mesh (exported by default)", negate=True)
    overwrite: bool = _f(
        True, "--no_overwrite", "do not overwrite existing output files", negate=True)
    log_path: Optional[str] = _f(
        None, "--log_path", "redirect stdout to this file (CLI only; ignored by the API)")

    # ------------------------------------------------------------ 推导
    def resolved_output_folder(self) -> str:
        import os

        if self.output_folder:
            return os.path.abspath(self.output_folder)
        base = getattr(__import__("bpy").data, "filepath", "") if _has_bpy() else ""
        root = os.path.dirname(base) if base else os.path.expanduser("~")
        return os.path.join(root, "Baked_PBR")

    def validate(self) -> None:
        if self.texture_size < 16 or self.texture_size > 16384:
            raise ValueError("texture_size must be 16..16384, got %r"
                             % (self.texture_size,))
        if self.samples < 1:
            raise ValueError("samples must be >= 1, got %r" % (self.samples,))
        if self.margin_px < 0:
            raise ValueError("margin_px must be >= 0, got %r" % (self.margin_px,))
        if self.cage_ratio <= 0:
            raise ValueError("cage_ratio must be > 0, got %r" % (self.cage_ratio,))
        if self.device not in ("CPU", "GPU"):
            raise ValueError("device must be CPU or GPU, got %r" % (self.device,))

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    # ------------------------------------------------------------ CLI
    @classmethod
    def cli_parser(cls, prog: str = "blender_texture_transfer") -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog=prog,
            description="Texture transfer / rebake: BaseColor, Roughness, Metallic",
        )
        for f in fields(cls):
            meta = f.metadata
            flag = meta.get("flag")
            if not flag:
                continue
            dest = f.name
            default = f.default
            if meta.get("negate"):
                parser.add_argument(
                    flag, dest=dest, action="store_false", default=default,
                    help=meta.get("help", ""))
            elif isinstance(default, bool):
                parser.add_argument(
                    flag, dest=dest, action="store_true", default=default,
                    help=meta.get("help", ""))
            else:
                parser.add_argument(
                    flag, dest=dest,
                    type=type(default) if default is not None else str,
                    default=default, help=meta.get("help", ""))
        return parser

    @classmethod
    def from_cli(cls, argv: Optional[list] = None) -> "JobConfig":
        args = cls.cli_parser().parse_args(argv)
        cfg = cls(**vars(args))
        cfg.validate()
        return cfg


def _has_bpy() -> bool:
    import sys

    return "bpy" in sys.modules


def cli_option_strings() -> set:
    """返回 CLI 暴露的所有选项字符串（用于一致性测试）。"""
    parser = JobConfig.cli_parser()
    return {opt for action in parser._actions for opt in action.option_strings}


def config_field_names() -> set:
    """返回需要在 CLI 暴露的字段名（以 flag 是否存在为准）。"""
    return {f.name for f in fields(JobConfig) if f.metadata.get("flag")}