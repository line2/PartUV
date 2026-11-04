# PartUV 性能优化记录

本文件记录本轮针对 PartUV（`pipeline_numpy` / `pipeline_file` 路径）的全部性能改动：
每个问题的**症状 → 根因 → 改法 → 实测效果**，以及复现方式。

所有数字都是同一台机器（RTX 5060 / 16 核 / WSL2）实测，两个模型：

| 代号 | 模型 | 顶点 | 面 | 部件数 | 特征 |
|---|---|---|---|---|---|
| **frag** | `out/shusheng/model/model.obj` | 309,873 | 499,804 | 3,915 | 原始碎壳，8,406 个连通块，中位 8 面/部件 |
| **weld** | `out/model_welded/model_welded/model_welded.obj` | 249,876 | 499,804 | 101 | 焊接后，中位 3,461 面/部件 |

---

## 0. 总览

| 阶段 | frag | weld |
|---|---|---|
| 基线（CUDA PAMO 代理） | 125.4 s | 335.6 s |
| → 换成顶点聚类代理 | 82.3 s | 70.4 s\* |
| → unwrap 结果缓存 | 68.1 s | 66.5 s |
| → 修数据竞争（输出变确定） | 68.1 s | 60.6 s |
| → 移除 OpenABF 热路径日志 | 60.3 s | 49.7 s |
| → 重叠检测换非精确内核 + 短路 | **55.9 s** | **43.8 s** |

\* weld 的 70.4 s 已包含缓存（该模型缓存命中率仅 18.9%，影响很小）。

累计：frag **2.24×**（125.4 → 55.9），weld **7.7×**（335.6 → 43.8）。
对比最初发布的 wheel 在 weld 上的 757 s，是 **17.3×**。

输出正确性：frag 全程 md5 恒为 `8d2361690449a7f8a7b84c0b523e2f0b`；
weld 恒为 `3f3769b552d7fd7761eee3704bcc58c7`（除有意改变几何决策的代理切换之外）。

---

## 1. 性能分析基础设施

`src/prof.h`（新增，header-only）提供始终开启的计时累加器：

```cpp
{ prof::Scope _s("abf.total"); ... }          // 计时
prof::add_work("abf.faces", F.rows());        // 附带工作量计数
```
`PARTUV_PROF=/path/report.txt` 环境变量触发转储，按总耗时排序输出：

```
block                total_s   calls    ms/call     work
abf.angles            115.232   18135     6.3541        0
overlap.cgal           52.360   21619     2.4219 19861131
```

嵌套 Scope（`node.helper` → `abf.total` → `abf.angles`）用于区分"含子调用的总时间"和"自身时间"。
`src/easy/` 是本项目自带的最小 easy-profiler 兼容垫片，只为让既有 `EASY_BLOCK` 宏编译通过，不做实际记录。

---

## 2. 优化项

### O1 递归建树的内存爆炸（22.7 GB → 2.5 GB）

- **症状**：500k 面模型在 `pipeline_helper` 递归到 605 个部件时 OOM（峰值 22.7 GB）。
- **根因**：每一层递归都把整个 `Tree`（`unordered_map<int, NodeRecord>`，50 万节点）按值传递，
  并且每个候选分支各复制一份顶点/面数组。
- **改法**：
  - `pipeline.{h,cpp}`：改为按引用传 `Tree&`，配合 `TreeUndoGuard` 记录每层的写操作并回滚；
  - 只对"当前 seed 的子集"做拷贝，而不是整棵树；
  - `CuMeshSimplifier.cpp`：三处 `cudaMallocHost` 的对端 `cudaFreeHost` 补齐（原先泄漏）。
- **效果**：峰值 22.7 GB → **2.54 GB**，605 部件可跑完，269.9 s。

### O2 `abf_unwrap` 里的无用深拷贝

- **症状**：每次 ABF 调用多花约 8%。
- **根因**：`abf_unwrap` 入口对 `V`/`F` 做了 4 份 Eigen 深拷贝和 2 个 `std::string` 标签，全部未被读取。
- **改法**：删除（`src/Component.cpp`）。
- **效果**：120k 模型 36.6 s → 33.8 s。

### O3 CUDA PAMO 代理 → CPU 顶点聚类代理

- **症状**：`pamo.total` 占 21% 墙钟，单次 291 ms，且输出不确定（4 次运行 4 个不同 md5）。
- **根因**：PAMO 是 CUDA QEM 简化器，内部 72 轮迭代，每轮一次 `cudaStreamSynchronize` +
  4 次 device→host 回传，实际上被同步开销支配；作为"判断这个图表要不要合并"的**粗略代理**，
  它做了远超需要的精确工作。
- **改法**：新增 `src/cheap_proxy.{h,cpp}`——网格顶点聚类（`decimate()`），把顶点按
  `cell = bbox_diag × ratio` 量化到格子中点，去重合并。`config.yaml` 加 `pamo_backend: "cluster"`，
  `Component.cpp` 按后端分派。
- **效果**：

  | | PAMO (CUDA) | cluster (CPU) |
  |---|---|---|
  | 单次 | 291 ms | **0.15 ms** |
  | frag 总耗时 | 125.4 s | 82.3 s |
  | 峰值内存 | 3.24–3.49 GB | 3.23–3.30 GB |
  | 输出 | 4 次 4 个 md5 | **4 次完全一致** |

  注意：weld 上部件数从 81 变成 101、畸变从 `INT_MAX` 哨兵变成 1.2452——代理确实改变了合并决策。
  要复现旧行为把 `config/config.yaml` 里的 `pamo_backend` 行删掉即可。

### O4 unwrap 结果缓存

- **症状**：`abf.total` 187.5 s，但同样的（面集, 几何）被反复展开。
- **根因**：合并是自底向上递归的，父图表的展开结果被多个候选分支重复计算。
- **改法**：`src/unwrap_cache.h`（新增）——键 = 排序后的面 id + 合并后 `V`/`F` 的全量哈希，
  值 = 代理网格 + UV + 重叠计数。接入 `UnwrapMerge.cpp`（两轮合并）与 `UnwrapPlane.cpp`（拆分路径）。
  命中时返回**指针**而不是拷贝；768 MiB 上限，满了只停止新增。
  `PARTUV_UNWRAP_CACHE=0` 可关闭。
- **效果**：frag `abf.total` 187.5 → 120.3 s，墙钟 82.3 → **68.1 s**，命中率 **78.1%**（62,955 次调用）；
  weld 命中率仅 18.9%（图表太大、每次几何都不同）。
  注意键必须包含几何：约 12% 的面集相同但顶点集不同，只按面集缓存会返回错误结果。

### O5 并行合并的数据竞争（正确性）

- **症状**：weld 模型同一份二进制连续两次运行 md5 不同。
- **根因**：`UnwrapMerge.cpp` 的 `#pragma omp parallel for` 直接对 `allComponents[dst]` 调用
  `merge_B_to_A`，两个共享同一部件的 pair 会并发写同一对象。
- **改法**：改成"每轮只并行执行两两互不相交的 pair"（冲突的留到下一轮）。轮内无交互，
  轮序固定 ⇒ 结果确定。
- **效果**：连续运行 md5 一致；耗时无变化。

### O6 OpenABF 热路径日志（最大单项，13.5×）

- **症状**：`abf.build` 178.9 s，占 ABF 总时间的 50%；每面 11 µs（单独基准只要 0.4 µs/面）。
- **根因**：`extern/OpenABF/include/OpenABF/HalfEdgeMesh.hpp` 的 `insert_face_2` 在遇到
  非流形边时构造 3 个 `std::to_string` + 字符串拼接 + `std::cerr << msg << std::endl`（**每条 flush**）。
  一次 weld 运行打印 **36,602 行**（日志 3.47 MB），8 个 OpenMP 线程全部堵在 stderr 锁上。
- **证据**：

  | 场景 | 每面耗时 |
  |---|---|
  | 独立基准（干净网格，单线程） | 0.25–0.42 µs |
  | 管线，1 线程 | 2.38 µs |
  | 管线，8 线程（修复前） | **11.0 µs** |
  | 管线，8 线程（修复后） | **0.16 µs** |

- **改法**：删除该分支的打印，改为计数（`non_manifold_edges_` / `degenerate_faces_`）。
- **效果**：`abf.build` **178.9 → 13.3 s**；weld 墙钟 60.6 → **49.7 s**，frag 68.1 → **60.3 s**；
  日志 3.47 MB → 430 KB。输出 md5 不变。

### O7 OpenABF 构建器的容器改造（小幅）

- `std::deque` 竞技场 + 非拥有 `shared_ptr`（别名构造，无控制块分配）替代每元素 `make_shared`；
  同时补 `Mesh::reserve()`。
- 把 `std::multimap<size_t, EdgePtr> edges_`（每边一次树节点分配 + 每次 `find_edge_` 一次
  `equal_range`）换成按起点分桶的 `std::vector<std::vector<EdgePtr>>`。
- **效果**：合计约 9%（`abf.build` 203 → 185 s）。收益有限，说明 O6 才是主因——
  这两项保留是因为它们同时降低了 allocator 争用（对多线程有利）。

### O8 重叠检测：非精确内核 + 首次命中即返回

- **症状**：`overlap.cgal` 125 s（weld），每次 5.79 ms，**6.3 µs/面**。
- **根因**：
  1. `Point_2` / `Triangle_2` 用的是 `CGAL::Exact_predicates_exact_constructions_kernel`，
     每个三角形（含 bbox）都构造惰性精确有理数；
  2. 两个以几何对象为键的 `std::map` 只写不读；
  3. 调用方只关心"有没有重叠"，但函数会枚举**全部**重叠对。
- **改法**（`src/triangle_intersection/triangleHelper.cpp`）：
  - 改用同文件已有的 `Point_2S` / `Triangle_2S`（`CGAL::Simple_cartesian<double>`）；
  - 删掉两个死查表；
  - 找到第一对重叠就抛私有异常 `OverlapFound` 终止 CGAL 扫描
    （CGAL 6.1 的 `box_self_intersection_d` **忽略回调返回值**，`segment_tree.h` 里是裸调用，
    所以不能用 return 停）。
- **效果**：

  | | 修复前 | 修复后 |
  |---|---|---|
  | weld `overlap.cgal` | 124.9 s | **52.4 s** |
  | frag `overlap.cgal` | 50.3 s | **22.4 s** |
  | weld 单次 | 5.79 ms | 2.42 ms |
  | frag 单次 | 1.69 ms | 0.75 ms |

  墙钟 weld 49.7 → **43.8 s**，frag 60.3 → **55.9 s**，两者输出 md5 均不变。

### O9 其它清扫

- `merge.cpp`：加 `merge.mesh` 计时；删除 `UnwrapMerge.cpp` 中合并前对 `A.V/A.F/B.V/B.F` 的
  四份深拷贝（从未被读取）。
- 删除每节点无条件打印 `mergePairs` 列表（12k 行 stdout）。
- `IO.{h,cpp}`：`Tree` 改为可回滚的写日志 + 父节点索引修正（配合 O1）。
- `bindings.cpp`：缓存/探针统计的转储接到 `pipeline_file_py` 与 `pipeline_numpy_py` 两个入口。

---

## 3. 现在的瓶颈（weld，43.8 s 墙钟 / 约 366 s CPU）

| 块 | CPU | 占比 | 备注 |
|---|---|---|---|
| `abf.angles`（ABF++ 牛顿迭代） | 115–141 s | ~40% | 大图表 7.8 ms/次 |
| `overlap.cgal` | 52.4 s | 20% | 21.6k 次，仍有 17k 次未走缓存 |
| `abf.lscm` | 42.6 s | 16% | |
| `abf.build` | 13.3 s | 4% | 已从 58% 降下来 |
| `abf.boundary` | 10.0 s | 4% | 每次 O(面数) 找边界环 |

frag（55.9 s）：`abf.angles` 36.3 s、`overlap.cgal` 22.4 s、`abf.lscm` 19.3 s、`pamo.total` 11.5 s。

**并行度**：weld 墙钟 43.8 s / CPU 约 366 s ≈ 8.4×（16 核）；frag 更差（约 3×）。
跨图表并行是剩下最大的结构性空间。

---

## 4. 复现

```bash
# 构建（out-of-tree，避免污染源码树）
bash cmake_build.sh        # -> pybuild/，日志 cmake_build.log
bash install_mod.sh        # 把 _core*.so 拷进 site-packages

# 运行 + 出 profile
PARTUV_PROF=/tmp/prof.txt python run_core.py \
    out/shusheng/model/model.obj \
    out/shusheng/model/bin/model.bin \
    out/run 1.25
# 输出: [done] 55.9s  peak RSS 3388 MiB  parts=3915 charts=1 distortion=1.2415
```

> 构建/安装期间不要同时跑基准——`install_mod.sh` 会 `cp -f` 覆盖正在被加载的 `.so`。

---

## 5. 开关与回退

| 配置 / 环境变量 | 默认 | 作用 |
|---|---|---|
| `config.yaml: pamo_backend` | `cluster` | 删掉该行即回到 CUDA PAMO |
| `config.yaml: usePamoFaceThreshold` | `4000` | 只对大于该面数的图表启用代理 |
| `PARTUV_UNWRAP_CACHE` | 开 | `0` 关闭 unwrap 缓存 |
| `PARTUV_PROF` | 无 | 设置路径即转储 profile |

已验证的阈值门禁：`usePamoFaceThreshold=1000` → 部件 4,184；`=300` → 部件 4,069 且畸变 3.91（不可接受），
因此保持 4,000。

---

## 6. 未做的方向（及原因）

- **ABF++ 求解上 GPU**：ABF++ 是每图表一次稀疏 Newton + Cholesky，图表仅 300–15,000 未知数，
  cuSolver 在该尺度反而更慢；且 18k 次小求解的 launch 开销会吃掉收益。
  唯一 GPU 友好的形态是"多图表锁步批量 Newton"，需要重写求解器，数值行为会变。本项目的 PAMO
  已经是"上 GPU 反而更慢"的现成反例（291 ms vs 0.15 ms）。
- **网格拓扑"拷贝代替构建"**：曾计划用全局配对表批量建 ABF 网格，但 O6 修完后 `abf.build`
  只占 4%，收益上限几秒，不值得引入半开边不变量的风险。
- **`pamo_proxy_mode: "global"`**：实测对结果与耗时均无影响（md5 相同、81.7 vs 82.3 s），
  属于应删除的死代码。