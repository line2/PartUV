// No-op stand-in for easy/profiler.h so the project builds without libeasy_profiler.so.
// Enabled only for profiling builds; EASY_* macros expand to nothing.
#pragma once

#include <string>

namespace profiler {
struct Color { explicit Color(unsigned) {} };
namespace colors {
enum {
    Grey, White, Brown, Blue, Red, Green, Yellow, Magenta, Cyan, Black,
    Orange, Purple, Lime, Navy, Teal, Olive, Maroon, Silver
};
}  // namespace colors
inline void dumpBlocksToFile(const char *) {}
inline void startListen(unsigned short = 0) {}
inline void stopListen() {}
inline bool isEnabled() { return false; }
inline void enable() {}
}  // namespace profiler

#define EASY_PROFILER_ENABLE ((void)0)
#define EASY_BLOCK(...) ((void)0)
#define EASY_END_BLOCK ((void)0)
#define EASY_FUNCTION(...) ((void)0)
#define EASY_VALUE(...) ((void)0)
#define EASY_ARRAY(...) ((void)0)
#define EASY_TEXT(...) ((void)0)
#define EASY_THREAD(...) ((void)0)