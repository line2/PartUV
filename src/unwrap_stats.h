#pragma once
// Probe: does the pipeline unwrap the same face set more than once?
// (decides whether a face-set keyed unwrap cache can pay off at all)
#include <algorithm>
#include <cstdio>
#include <mutex>
#include <unordered_set>
#include <vector>

namespace unwrap_stats {

inline std::mutex g_mu;
inline std::unordered_set<unsigned long long> g_seen;
inline long long g_total = 0;
inline long long g_dup = 0;

inline void probe(const std::vector<int> &faces) {
    std::vector<int> key = faces;
    std::sort(key.begin(), key.end());
    unsigned long long h = 1469598103934665603ULL;   // FNV-1a over the sorted ids
    for (int f : key) {
        unsigned long long v = static_cast<unsigned long long>(static_cast<unsigned>(f));
        for (int b = 0; b < 8; ++b) {
            h ^= (v >> (8 * b)) & 0xFFULL;
            h *= 1099511628211ULL;
        }
    }
    std::lock_guard<std::mutex> lk(g_mu);
    g_total++;
    if (!g_seen.insert(h).second) g_dup++;
}

inline void dump() {
    std::lock_guard<std::mutex> lk(g_mu);
    if (g_total == 0) return;
    std::fprintf(stderr,
        "\n[unwrap-cache probe] unwrap calls: %lld   unique face sets: %zu   repeats: %lld (%.1f%%)\n",
        g_total, g_seen.size(), g_dup, 100.0 * double(g_dup) / double(g_total));
}

}  // namespace unwrap_stats