"""Summarise a PARTUV_PROF dump into cost shares."""
import sys

rows = []
for line in open(sys.argv[1]):
    p = line.split()
    if len(p) < 4 or p[0] == "block":
        continue
    try:
        total = float(p[1]); calls = int(p[2]); per = float(p[3])
    except ValueError:
        continue
    work = int(p[4]) if len(p) > 4 else 0
    rows.append((p[0], total, calls, per, work))

rows.sort(key=lambda r: -r[1])

# group into stages
GROUP = {
    "abf.total": "ABF++ 解包（含角度解+LSCM）",
    "abf.angles": "  ├ 角度优化 (ABF++)",
    "abf.lscm": "  ├ 角度→UV (angle-LSCM)",
    "abf.fixboundary": "ABF 固定边界（PAMO 高模）",
    "lscm.solve": "LSCM 兜底",
    "distortion": "畸变计算",
    "merge.attempt": "合并尝试",
    "submesh.extract": "子网格抽取",
    "pamo.total": "PAMO 两级（简化+低模）",
    "node.helper": "树节点递归",
    "node.seedcut": "种子切分",
    "final.reunwrap": "定稿全分辨率重解",
}

tot = sum(r[1] for r in rows)
print(f"{'block':<20} {'total_s':>10} {'share':>7} {'calls':>9} {'ms/call':>9}  note")
print("-" * 82)
for name, t, c, per, w in rows:
    note = GROUP.get(name, "")
    print(f"{name:<20} {t:>10.2f} {t/tot*100:>6.1f}% {c:>9,} {per:>9.3f}  {note}")
print("-" * 82)
print(f"{'sum(instrumented)':<20} {tot:>10.2f}")

# collapsed view: avoid double counting parents/children
def g(k):
    return sum(r[1] for r in rows if r[0] == k)

abf_angles, abf_lscm = g("abf.angles"), g("abf.lscm")
abf_total = g("abf.total")
print(f"\nABF 内部占比: 角度优化 {abf_angles/max(abf_total,1e-9)*100:.1f}%  "
      f"LSCM 转换 {abf_lscm/max(abf_total,1e-9)*100:.1f}%  "
      f"其余(建 mesh/边界) {(abf_total-abf_angles-abf_lscm)/max(abf_total,1e-9)*100:.1f}%")
print(f"ABF 占总耗时: {abf_total/max(tot,1e-9)*100:.1f}%  "
      f"CGAL 重叠检测: {g('overlap.test')/max(tot,1e-9)*100:.1f}%  "
      f"子网格抽取: {g('submesh.extract')/max(tot,1e-9)*100:.1f}%")