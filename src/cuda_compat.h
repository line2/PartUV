#pragma once
// CUDA is optional (CMakeLists.txt: PARTUV_ENABLE_CUDA / PARTUV_HAS_CUDA).
//
// The pipeline threads a stream handle through several signatures.  With CUDA off
// that handle is an opaque pointer nobody dereferences, so the call sites compile
// unchanged and the CPU backends behave exactly as before.
#ifdef PARTUV_HAS_CUDA
#include <cuda_runtime.h>
#else
using cudaStream_t = void *;
#endif
