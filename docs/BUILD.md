# Building and packaging

Two things are worth knowing before you build:

1. **CUDA is optional.**  `PARTUV_ENABLE_CUDA=AUTO|ON|OFF` (default `AUTO`: on when a
   usable `nvcc` exists).  The only CUDA consumer is the CUDA PAMO baseline
   (`unwrap.pamo_backend: ""`); every shipped default is CPU.  Wheels set it `OFF`, so
   they never link `libcudart`.
2. **`-march=native` is off in wheels.**  `PARTUV_NATIVE_ARCH=OFF` targets
   `-march=x86-64-v2`; `native` bakes the build machine's ISA into the binary and
   segfaults elsewhere.

## Local build (matches the venv used in development)

```bash
cmake -S . -B pybuild -DCMAKE_BUILD_TYPE=Release \
      -DPARTUV_ENABLE_CUDA=OFF -DPARTUV_NATIVE_ARCH=OFF \
      -Dpybind11_DIR="$(python -c 'import pybind11; print(pybind11.get_cmake_dir())')"
cmake --build pybuild -j"$(nproc)"
cp pybuild/_core*.so "$VIRTUAL_ENV/lib/python3.*/site-packages/partuv/"
```

Dependencies: a C++17 compiler, CMake ≥ 3.20, OpenMP, yaml-cpp, CGAL 6 (header-only is
fine).  Eigen, libigl, OpenABF, nlohmann/json and stb are vendored under `extern/`, so
there is no dependency resolution step.  TBB is optional.

## Wheels (manylinux, CPU only)

`ci/Dockerfile.manylinux` builds the image the wheels are compiled in.  manylinux_2_28
already has cp39–cp313, gcc 14 and cmake 4, but no CGAL and no Boost new enough for it
(base repos stop at 1.66; CGAL 6 wants ≥ 1.74), so the image adds:

* Boost 1.86 **headers only** (copied from the source tarball) plus a small hand-written
  `BoostConfig.cmake`, because CGAL's config-mode lookup expects one;
* CGAL 6.1.1 installed header-only (`-DCGAL_HEADER_ONLY=ON`, nothing compiled);
* yaml-cpp 0.8.0 built from source.

```bash
docker build -f ci/Dockerfile.manylinux -t partuv-manylinux:2_28 ci/
python -m cibuildwheel --output-dir dist .
```

`pyproject.toml` pins the matrix (`cp39`–`cp313`), the image tag and the CPU-only CMake
defines, so no flags are needed on the command line.  Each wheel is ~2.3 MB; `auditwheel`
repairs the tag to `manylinux_2_28_x86_64`.

Build one version while iterating:

```bash
python -m cibuildwheel --output-dir dist --only cp311-manylinux_x86_64 .
```

## Verifying a wheel

```bash
python -m venv /tmp/w && /tmp/w/bin/pip install dist/partuv-0.2.0-cp311-*.whl
cd /tmp && /tmp/w/bin/python -c "import sys, partuv; print(partuv.__version__, 'torch' in sys.modules)"
```

Run it from outside the source tree — a local `partuv/` directory shadows the installed
package and has no `_core.so`.

The regression check is the 500k welded model with its saved tree:

```python
res = partuv.unwrap(mesh, tree=".../model_welded.bin")
# expect: 93 parts, 499,804 faces, distortion 1.2383, 248 charts, ~110 s
```

## What is *not* in the wheel

* CUDA PAMO.  `pamo_backend: ""` degrades to `none` with a warning.
* PartField preprocessing (torch).  Install `partuv[preprocess]` if you want
  `partuv.prepare()`; otherwise supply a tree.

## Gotchas found while packaging

* CGAL's config defines `CGAL_LINKED_WITH_TBB` when TBB is present, so CGAL headers emit
  `tbb::parallel_*` calls and the module must link `libtbb`.  With TBB absent nothing
  references it — hence `find_package(TBB QUIET)` plus a conditional link.
* The no-CUDA `StreamPool` stub must return a **non-null** handle: `UnwrapPlane.cpp` gates
  the proxy path on `stream != nullptr`, and returning `nullptr` silently dropped 77 % of
  the faces.
* `src/triangle_intersection` links CGAL unconditionally (it uses
  `CGAL::box_self_intersection_d`), so CGAL stays a hard dependency even though the
  cutting-plane search no longer needs it (`src/hull2d.h`).