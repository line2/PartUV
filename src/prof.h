// Lightweight always-on accumulator used to localise PartUV's cost.
// Header-only, thread-safe enough for OpenMP (atomic adds; map insert behind a mutex).
#pragma once

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace prof {

struct Entry {
    std::atomic<long long> ns{0};
    std::atomic<long long> calls{0};
    std::atomic<long long> work{0};   // optional extra counter (faces, triangles...)
};

inline std::unordered_map<std::string, Entry *> &table() {
    static std::unordered_map<std::string, Entry *> t;
    return t;
}
inline std::mutex &mtx() {
    static std::mutex m;
    return m;
}

inline Entry *entry(const std::string &name) {
    {
        std::lock_guard<std::mutex> lk(mtx());
        auto it = table().find(name);
        if (it != table().end()) return it->second;
        auto *e = new Entry();
        table()[name] = e;
        return e;
    }
}

inline void add_work(const std::string &name, long long w) {
    entry(name)->work += w;
}

class Scope {
    std::string name_;
    std::chrono::high_resolution_clock::time_point t0_;
public:
    explicit Scope(std::string n) : name_(std::move(n)),
        t0_(std::chrono::high_resolution_clock::now()) {}
    ~Scope() {
        const long long ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now() - t0_).count();
        Entry *e = entry(name_);
        e->ns += ns;
        e->calls += 1;
    }
};

inline void dump_txt(const char *path) {
    std::vector<std::pair<std::string, Entry *>> rows(table().begin(), table().end());
    // sort by total time desc
    for (size_t i = 0; i < rows.size(); ++i)
        for (size_t j = i + 1; j < rows.size(); ++j)
            if (rows[j].second->ns.load() > rows[i].second->ns.load())
                std::swap(rows[i], rows[j]);

    FILE *fh = fopen(path, "w");
    if (!fh) return;
    long long grand = 0;
    for (auto &r : rows) if (r.first.rfind("total:", 0) == 0) grand += r.second->ns.load();

    fprintf(fh, "%-26s %12s %10s %12s %12s\n", "block", "total_s", "calls", "ms/call", "work");
    for (auto &r : rows) {
        const long long ns = r.second->ns.load();
        const long long c = r.second->calls.load();
        fprintf(fh, "%-26s %12.3f %10lld %12.4f %12lld\n", r.first.c_str(),
                ns / 1e9, c, c ? (ns / 1e6 / c) : 0.0, r.second->work.load());
    }
    fclose(fh);
    fprintf(stderr, "[prof] wrote %s\n", path);
}

inline bool enabled() {
    static const bool on = getenv("PARTUV_PROF") != nullptr;
    return on;
}

}  // namespace prof