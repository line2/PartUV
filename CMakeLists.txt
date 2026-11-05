cmake_minimum_required(VERSION 3.10)


# ---------------------------------------------------------------------------
# CUDA is optional.  Its only consumer is the CUDA PAMO path
# (unwrap.pamo_backend: ""), a 300 s baseline -- the shipped default is "none"
# and every CPU backend works without it.  Wheels are built with
# -DPARTUV_ENABLE_CUDA=OFF so they do not link libcudart.
# ---------------------------------------------------------------------------
set(PARTUV_ENABLE_CUDA "AUTO" CACHE STRING "Build the CUDA PAMO path: ON | OFF | AUTO")
set(CMAKE_CUDA_ARCHITECTURES 80 89 90)

include(CheckLanguage)
check_language(CUDA)                      # sets CMAKE_CUDA_COMPILER if nvcc works

set(_partuv_cuda OFF)
if(PARTUV_ENABLE_CUDA STREQUAL "AUTO")
  set(_partuv_cuda ${CMAKE_CUDA_COMPILER})
elseif(PARTUV_ENABLE_CUDA)
  if(CMAKE_CUDA_COMPILER)
    set(_partuv_cuda ON)
  else()
    message(WARNING "PARTUV_ENABLE_CUDA=ON but no working nvcc was found; building without CUDA")
  endif()
endif()
if(_partuv_cuda)
  set(_partuv_cuda ON)
endif()

if(_partuv_cuda)
  project(partuv LANGUAGES CXX CUDA)
  add_compile_definitions(PARTUV_HAS_CUDA=1)
  message(STATUS "partuv: CUDA ENABLED (${CMAKE_CUDA_COMPILER})")
else()
  project(partuv LANGUAGES CXX)
  message(STATUS "partuv: CUDA DISABLED -- unwrap.pamo_backend=\"\" is rejected at runtime")
endif()
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/src)

# Set up shared dependencies at the root level
set(CMAKE_CXX_STANDARD 17)


if(_partuv_cuda)
  set(CMAKE_CUDA_STANDARD 14)
  set(CMAKE_CUDA_STANDARD_REQUIRED ON)
  add_compile_definitions(CUDA_API_PER_THREAD_DEFAULT_STREAM)
endif()

set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Choose the build type")
# set(CMAKE_BUILD_TYPE "Debug" CACHE STRING "Choose the build type" FORCE)

# message(STATUS "CMake build type: ${CMAKE_BUILD_TYPE}")

# -march=native bakes the build host's ISA into the binary, which segfaults on any
# other machine -- never use it for a wheel.  PARTUV_NATIVE_ARCH=OFF (the wheel
# default) targets the x86-64-v2 baseline instead.
option(PARTUV_NATIVE_ARCH "Optimise for the build host CPU (-march=native)" ON)
if(PARTUV_NATIVE_ARCH)
  set(_partuv_arch_flag -march=native)
else()
  set(_partuv_arch_flag -march=x86-64-v2)
endif()
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -ffast-math -mfpmath=sse -Ofast -fno-omit-frame-pointer ${_partuv_arch_flag}")
message(STATUS "partuv: release arch flag: ${_partuv_arch_flag}")
# if(CMAKE_BUILD_TYPE STREQUAL "Release")
# elseif(CMAKE_BUILD_TYPE STREQUAL "Debug")
#     set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -g -O0")
#     add_compile_definitions(DEBUG_MODE)
# endif()

option(ENABLE_PROFILING "Enable or disable profiling timers" ON)

# Define paths to shared dependencies
set(EXTERNAL_DIR "${CMAKE_CURRENT_SOURCE_DIR}/extern")
# set(INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/include")
set(SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src")

set(LIBIGL_INCLUDE_DIR ${EXTERNAL_DIR}/libigl/include)
set(EIGEN_INCLUDE_DIR ${EXTERNAL_DIR}/eigen-3.4.0)
set(OPENABF_INCLUDE_DIR ${EXTERNAL_DIR}/OpenABF/include)
set(STB_INCLUDE_DIR ${EXTERNAL_DIR}/stb)
set(NLOHMANN_JSON_INCLUDE_DIR ${EXTERNAL_DIR}/json/include)

# set(UVPSDK_ROOT "${EXTERNAL_DIR}/uvpackmaster"          # extern/uvpackmaster
#     CACHE PATH "Path to UVPackmaster SDK (include/ + lib/)")
# find_path(UVPCORE_INCLUDE_DIR
# NAMES uvpCore.hpp
# PATHS "${UVPSDK_ROOT}/include"
# NO_DEFAULT_PATH REQUIRED)

# find_library(UVPCORE_LIBRARY
#        NAMES uvpcore libuvpcore
#        PATHS "${UVPSDK_ROOT}/lib"
#        NO_DEFAULT_PATH REQUIRED)

# add_library(uvpcore_sdk SHARED IMPORTED GLOBAL)
# set_target_properties(uvpcore_sdk PROPERTIES
#         IMPORTED_LOCATION             "${UVPCORE_LIBRARY}"
#         INTERFACE_INCLUDE_DIRECTORIES "${UVPCORE_INCLUDE_DIR}")

#   file(GLOB UVP_LIBS "${UVPSDK_ROOT}/lib/libuvpcore.so")


#   if(UVP_LIBS)
#     install(FILES ${UVP_LIBS}  DESTINATION partuv/.libs)
#   endif()
# Make these paths available to all subprojects
include_directories(
    ${LIBIGL_INCLUDE_DIR}
    ${EIGEN_INCLUDE_DIR}
    ${STB_INCLUDE_DIR}
    ${OPENABF_INCLUDE_DIR}
    ${NLOHMANN_JSON_INCLUDE_DIR}
)

# include_directories(${EXTERNAL_DIR}/pybind11/include)
# include_directories("/usr/include/suitesparse")
# Find common dependencies

find_package(CGAL REQUIRED)
# easy_profiler stubbed out (no-op macros) 

find_package(yaml-cpp REQUIRED)
find_package(OpenMP REQUIRED)
find_package(TBB REQUIRED)   # pulled in by CGAL, see the link step
# TBB is never referenced by our own sources, but CGAL's config adds
# CGAL_LINKED_WITH_TBB when it finds TBB, so CGAL headers emit tbb::parallel_* calls
# and the module needs libtbb at link time.  auditwheel vendors it into the wheel.
if(_partuv_cuda)
  find_package(CUDAToolkit REQUIRED)
endif()

# Find pybind11 for Python bindings.  PYBIND11_FINDPYTHON makes it use the modern
# FindPython mode, so Python_EXECUTABLE (what scikit-build-core and every modern
# build frontend sets) is honoured instead of the classic PYTHON_EXECUTABLE.
set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)



# Add the LSCM library subdirectory
add_subdirectory(${SRC_DIR}/lscm)
target_compile_options(lscm_lib PUBLIC -fPIC)
add_subdirectory(${SRC_DIR}/triangle_intersection)
target_compile_options(triangle_intersection PUBLIC -fPIC)



# add_subdirectory(${EXTERNAL_DIR}/pybind11)

# Collect source files:
# 1. Add main.cpp from the project root
option(USE_ALL_SRC_FILES "Use all .cpp files in src directory" ON)

if(USE_ALL_SRC_FILES)
    file(GLOB SOURCES "${SRC_DIR}/*.cpp")
    if(_partuv_cuda)
        file(GLOB CUDA_SOURCES "${SRC_DIR}/*.cu")
        list(APPEND SOURCES ${CUDA_SOURCES})
    endif()
    set(BINDINGS_SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/bindings.cpp")
    list(APPEND SOURCES ${BINDINGS_SOURCES})
    message(STATUS "Using all source files in ${SRC_DIR}")
else()
    set(SOURCES
        "${SRC_DIR}/Distortion.cpp"
        "${SRC_DIR}/IO.cpp"
    )
    message(STATUS "Using selected source files only")
endif()



set(ENV{OMP_NUM_THREADS} "8")

# Create Python module
# pybind11_add_module(partuv src/bindings.cpp)
pybind11_add_module(_core bindings.cpp ${SOURCES})

# --- allow device-side lambdas & cross-TU __device__ calls ---
if(_partuv_cuda)
  set_target_properties(_core PROPERTIES CUDA_SEPARABLE_COMPILATION ON)
  target_compile_definitions(_core PRIVATE CUDA_API_PER_THREAD_DEFAULT_STREAM)
  target_compile_options(_core PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:
      --expt-extended-lambda
      --expt-relaxed-constexpr
      --default-stream=per-thread
    >
  )
endif()
# Link the Python module with the same dependencies as the main executable
target_link_libraries(_core
    PUBLIC
        # uvpcore_sdk          
    PRIVATE
        lscm_lib
        triangle_intersection
        OpenMP::OpenMP_CXX
        yaml-cpp
        TBB::tbb
)
if(_partuv_cuda)
  target_link_libraries(_core PRIVATE CUDA::cudart)
endif()

# Set include directories for the Python module
target_include_directories(_core PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${LIBIGL_INCLUDE_DIR}
    ${EIGEN_INCLUDE_DIR}
    ${STB_INCLUDE_DIR}
    ${OPENABF_INCLUDE_DIR}
    ${NLOHMANN_JSON_INCLUDE_DIR}
)

# --- Add at the end of CMakeLists.txt ---
# install(TARGETS _core LIBRARY DESTINATION partuv)
install(TARGETS _core DESTINATION partuv)
# install(FILES DESTINATION partuv/.libs)

install(FILES
  ${CMAKE_CURRENT_SOURCE_DIR}/partuv/__init__.py
  ${CMAKE_CURRENT_SOURCE_DIR}/partuv/preprocess.py
  DESTINATION partuv)

# The pipeline needs a config; ship the default inside the package so a wheel is
# usable without an external config/config.yaml.
install(FILES
  ${CMAKE_CURRENT_SOURCE_DIR}/config/config.yaml
  DESTINATION partuv/data
  RENAME default_config.yaml)

install(DIRECTORY
  ${CMAKE_CURRENT_SOURCE_DIR}/preprocess_utils/
  DESTINATION partuv/preprocess_utils
  FILES_MATCHING
    PATTERN "*.py"
    PATTERN "*.yaml"
    PATTERN "*.yml"
    PATTERN "*.json"
    PATTERN "*.txt"
    PATTERN "*.pt"
    PATTERN "*.bin"
)
set_target_properties(_core PROPERTIES
  # so the built artifact also works from the build tree
  BUILD_RPATH  "\$ORIGIN;\$ORIGIN/.libs"
  # so the installed wheel works after pip install
  INSTALL_RPATH "\$ORIGIN;\$ORIGIN/.libs"
)