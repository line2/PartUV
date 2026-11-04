"""One-page summary chart of the UV packing / proxy experiments."""
import os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

OUT = os.path.join(os.environ.get("BAKE_WORK", "/mnt/c/Users/JdSc-local/Project/blend-baking"), "bake_noproxy4", "summary_chart.png")

# ---- data (all welded 500k model, 4096^2 unless stated) --------------------------
margins = [2, 4, 8, 16]
cov_noproxy = [61.87, 57.31, 52.43, 43.48]
cov_proxy = [57.94, 53.14, 46.46, 36.45]

variants = ["no proxy", "identity", "cluster\nquad/4k", "IDT\n(quad+flip)", "cluster\ncentroid/600"]
islands = [248, 248, 314, 314, 314]
coverage = [44.74, 44.74, 37.07, 36.73, 36.49]

density_labels = ["original\n3072$^2$", "old bake\nproxy 16px", "proxy\n4px", "no proxy\n4px", "no proxy\n2px"]
density = [18.9, 12.2, 17.8, 19.2, 20.8]

plt.rcParams.update({
    "font.size": 9,
    "axes.edgecolor": "#555",
    "axes.labelcolor": "#222",
    "text.color": "#222",
    "axes.titlesize": 10,
    "figure.facecolor": "white",
})

fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.6))

# ---- panel 1: coverage vs margin --------------------------------------------------
ax = axes[0]
ax.plot(margins, cov_noproxy, "o-", lw=2, ms=6, color="#1f77b4", label="no proxy (248 islands)")
ax.plot(margins, cov_proxy, "s--", lw=2, ms=5, color="#d62728", label="proxy (318 islands)")
for m, a, b in zip(margins, cov_noproxy, cov_proxy):
    ax.annotate(f"{a:.1f}%", (m, a), textcoords="offset points", xytext=(0, 8),
                ha="center", fontsize=8, color="#1f77b4")
    ax.annotate(f"{b:.1f}%", (m, b), textcoords="offset points", xytext=(0, -14),
                ha="center", fontsize=8, color="#d62728")
ax.set_xlabel("UV island margin (px @4096)")
ax.set_ylabel("texture coverage")
ax.set_title("A. Coverage vs island margin")
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.set_xticks(margins)
ax.set_ylim(30, 68)
ax.grid(alpha=0.25)
ax.legend(frameon=False, loc="lower left", fontsize=8)

# ---- panel 2: proxy variants ------------------------------------------------------
ax = axes[1]
x = range(len(variants))
bars = ax.bar(x, coverage, color=["#2ca02c", "#2ca02c", "#ff7f0e", "#ff7f0e", "#ff7f0e"], alpha=0.85)
ax.set_xticks(list(x))
ax.set_xticklabels(variants, fontsize=7.5)
ax.set_ylabel("coverage (4 px margin)")
ax.set_title("B. Any decimated proxy lands in the same place")
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.set_ylim(0, 55)
for b, c, n in zip(bars, coverage, islands):
    ax.text(b.get_x() + b.get_width() / 2, c + 1.2, f"{c:.1f}%\n{n} islands",
            ha="center", fontsize=7.5)
ax.axhline(44.74, color="#2ca02c", ls=":", lw=1)
ax.grid(axis="y", alpha=0.25)

# ---- panel 3: texel density -------------------------------------------------------
ax = axes[2]
colors = ["#888", "#d62728", "#ff7f0e", "#1f77b4", "#1f77b4"]
bars = ax.bar(range(len(density)), density, color=colors, alpha=0.85)
ax.axhline(density[0], color="#555", ls="--", lw=1)
ax.text(-0.42, density[0] + 0.35, "original 18.9", fontsize=7.5, ha="left", color="#555")
ax.set_xticks(range(len(density)))
ax.set_xticklabels(density_labels, fontsize=7.5)
ax.set_ylabel("texels per face")
ax.set_title("C. Effective resolution (4096$^2$ bakes)")
ax.set_ylim(0, 24)
for b, d in zip(bars, density):
    ax.text(b.get_x() + b.get_width() / 2, d + 0.5, f"{d:.1f}", ha="center", fontsize=8)
ax.grid(axis="y", alpha=0.25)

fig.suptitle("PartUV 500k welded model — UV atlas packing and proxy ablations",
             fontsize=11.5, y=0.995)
fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig(OUT, dpi=170)
print(f"[chart] {OUT}")