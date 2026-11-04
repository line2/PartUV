#pragma once
// Face-set + geometry keyed cache for unwrap_pamo().
//
// Measurement (500k model): 62,945 unwrap calls, only 2,966 distinct face sets
// -> 95.3% of the ABF work is re-solving a chart the pipeline already solved.
// The key includes the merged mesh geometry, so a hit means "identical input",
// which makes reuse exact rather than approximate.
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <unordered_map>
#include <vector>

#include <Eigen/Dense>

namespace unwrap_cache {

struct Entry {
    Eigen::MatrixXd V;    // proxy vertices as returned by unwrap_pamo
    Eigen::MatrixXi F;    // proxy faces
    Eigen::MatrixXd UV;   // UVs on the proxy
    double overlaps = -1.0;   // memoised computeOverlapingTrianglesFast(UV, F); <0 = unknown
};

inline uint64_t mix(uint64_t h, uint64_t v) {
    h ^= v + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    return h * 1099511628211ULL;
}

inline uint64_t key_of(const std::vector<int> &faces,
                       const Eigen::MatrixXd &V,
                       const Eigen::MatrixXi &F) {
    std::vector<int> sorted = faces;
    std::sort(sorted.begin(), sorted.end());
    uint64_t h = 1469598103934665603ULL;
    h = mix(h, static_cast<uint64_t>(sorted.size()));
    for (int f : sorted) h = mix(h, static_cast<uint64_t>(static_cast<uint32_t>(f)));

    h = mix(h, static_cast<uint64_t>(V.rows()));
    h = mix(h, static_cast<uint64_t>(V.cols()));
    const double *vp = V.data();
    for (Eigen::Index i = 0; i < V.size(); ++i) {
        uint64_t bits;
        std::memcpy(&bits, &vp[i], sizeof(bits));
        h = mix(h, bits);
    }
    h = mix(h, static_cast<uint64_t>(F.rows()));
    const int *fp = F.data();
    for (Eigen::Index i = 0; i < F.size(); ++i)
        h = mix(h, static_cast<uint64_t>(static_cast<uint32_t>(fp[i])));
    return h;
}

class Cache {
  public:
    std::mutex mu;
    std::unordered_map<uint64_t, Entry> map;
    size_t bytes = 0;
    size_t cap_bytes = size_t(768) << 20;   // 768 MiB
    long long hits = 0, misses = 0, stored = 0, skipped = 0;

    // Returns a pointer to the stored entry (stable across rehash for
    // std::unordered_map) and its key; nullptr on miss.
    const Entry *get(const std::vector<int> &faces, const Eigen::MatrixXd &V,
                     const Eigen::MatrixXi &F, uint64_t &key_out) {
        const uint64_t k = key_of(faces, V, F);
        key_out = k;
        std::lock_guard<std::mutex> lk(mu);
        auto it = map.find(k);
        if (it == map.end()) {
            misses++;
            return nullptr;
        }
        hits++;
        return &it->second;
    }

    double overlaps_of(uint64_t key) {
        std::lock_guard<std::mutex> lk(mu);
        auto it = map.find(key);
        return it == map.end() ? -1.0 : it->second.overlaps;
    }

    void set_overlaps(uint64_t key, double v) {
        std::lock_guard<std::mutex> lk(mu);
        auto it = map.find(key);
        if (it != map.end()) it->second.overlaps = v;
    }

    void put(const std::vector<int> &faces, const Eigen::MatrixXd &V,
             const Eigen::MatrixXi &F, const Eigen::MatrixXd &Vs,
             const Eigen::MatrixXi &Fs, const Eigen::MatrixXd &UV) {
        const uint64_t k = key_of(faces, V, F);
        const size_t sz = size_t(Vs.size()) * sizeof(double) +
                          size_t(Fs.size()) * sizeof(int) +
                          size_t(UV.size()) * sizeof(double);
        std::lock_guard<std::mutex> lk(mu);
        if (map.find(k) != map.end()) return;
        if (bytes + sz > cap_bytes) {          // stop growing, keep what we have
            skipped++;
            return;
        }
        Entry e;
        e.V = Vs;
        e.F = Fs;
        e.UV = UV;
        map.emplace(k, std::move(e));
        bytes += sz;
        stored++;
    }

    void dump() const {
        if (hits + misses == 0) return;
        const long long total = hits + misses;
        std::fprintf(stderr,
            "\n[unwrap cache] calls: %lld   hits: %lld (%.1f%%)   misses: %lld   "
            "stored: %lld   skipped(cap): %lld   mem: %.1f MiB\n",
            total, hits, 100.0 * double(hits) / double(total), misses,
            stored, skipped, double(bytes) / (1024.0 * 1024.0));
    }
};

inline Cache g_cache;

inline bool enabled_by_env() {
    const char *e = std::getenv("PARTUV_UNWRAP_CACHE");
    if (!e) return true;                 // on by default
    return !(e[0] == '0' || e[0] == 'n' || e[0] == 'N' || e[0] == 'f' || e[0] == 'F');
}

}  // namespace unwrap_cache