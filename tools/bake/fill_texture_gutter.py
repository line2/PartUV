#!/usr/bin/env python3
"""Fill the black padding between UV islands of a texture (gutter dilation).

Sampling a texture exactly at an island border picks up the black padding, which shows up as
dark seams after rebaking to a new UV layout. This dilates real colours into the padding.
"""
import argparse

import numpy as np
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=float, default=0.03,
                    help="max channel below this counts as padding")
    ap.add_argument("--iters", type=int, default=64)
    args = ap.parse_args()

    im = np.asarray(Image.open(args.inp).convert("RGB")).astype(np.float32) / 255.0
    h, w, _ = im.shape
    filled = im.copy()
    valid = filled.max(axis=2) > args.threshold
    print(f"[gutter] {valid.mean()*100:.1f}% of texels are non-padding")

    for it in range(args.iters):
        if valid.all():
            print(f"[gutter] fully filled after {it} iterations")
            break
        # 8-neighbour mean of already-valid texels, applied only where still invalid
        acc = np.zeros_like(filled)
        cnt = np.zeros((h, w), dtype=np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                sy0, sy1 = max(dy, 0), h + min(dy, 0)
                sx0, sx1 = max(dx, 0), w + min(dx, 0)
                dy0, dy1 = max(-dy, 0), h + min(-dy, 0)
                dx0, dx1 = max(-dx, 0), w + min(-dx, 0)
                src = filled[sy0:sy1, sx0:sx1]
                sv = valid[sy0:sy1, sx0:sx1].astype(np.float32)
                acc[dy0:dy1, dx0:dx1] += src * sv[..., None]
                cnt[dy0:dy1, dx0:dx1] += sv
        grow = (~valid) & (cnt > 0)
        filled[grow] = acc[grow] / cnt[grow][:, None]
        valid = valid | grow
    print(f"[gutter] after {args.iters} iterations, {valid.mean()*100:.1f}% valid")

    out = np.clip(filled * 255.0 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(out).save(args.out, optimize=True)
    print(f"[gutter] wrote {args.out}")


if __name__ == "__main__":
    main()