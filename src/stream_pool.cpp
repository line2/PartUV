#include "stream_pool.h"

#ifdef PARTUV_HAS_CUDA
#include <thread>
#include <atomic>
#include <functional> // For std::hash
#include <iostream>

namespace StreamPool {
    std::vector<cudaStream_t> streams;
    std::mutex streams_mutex;
    std::condition_variable streams_cv;
    bool streams_initialized = false;

    void asyncInitializeStreams(int num_streams) {
        std::cout << "Initializing " << num_streams << " streams" << std::endl;
        std::thread([num_streams]() {
            std::vector<cudaStream_t> temp_streams;
            temp_streams.reserve(num_streams);


            for (int i = 0; i < num_streams; ++i) {
                cudaStream_t stream;
                cudaError_t err = cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking);
                if (err != cudaSuccess) {
                    // Handle error (e.g., log, throw, or skip)
                    continue;
                }
                // cudaMemPool_t mempool;
                // cudaMemPoolCreate(&mempool, nullptr);

                // cudaStreamSetAttribute(stream, cudaStreamAttributeMemPool, &mempool);

                temp_streams.push_back(stream);
            }

            {
                std::lock_guard<std::mutex> lock(streams_mutex);
                streams = std::move(temp_streams);
                streams_initialized = true;
            }
            streams_cv.notify_all();
        }).detach();
    }

    cudaStream_t getStream() {
        std::unique_lock<std::mutex> lock(streams_mutex);
        streams_cv.wait(lock, []{ return streams_initialized; });

        // Assign a stream based on thread ID hash
        thread_local size_t thread_index = 
            std::hash<std::thread::id>{}(std::this_thread::get_id()) % streams.size();
        
        return streams[thread_index];
    }


    cudaStream_t getStream(int thread_id) {
        std::unique_lock<std::mutex> lock(streams_mutex);
        streams_cv.wait(lock, []{ return streams_initialized; });

        // std::cout << "initialized " << streams.size() << " streams" << std::endl;

        // Assign a stream based on thread ID hash  
        thread_local size_t thread_index = 
            thread_id % streams.size();
        
        return streams[thread_index];
    }

    void destroyStreams() {
        std::lock_guard<std::mutex> lock(streams_mutex);
        for (auto& stream : streams) {
            cudaStreamDestroy(stream);
        }
        streams.clear();
        streams_initialized = false;
    }
}

#else   // !PARTUV_HAS_CUDA ------------------------------------------------
// No GPU: the pool is a stub, but it must hand back a *non-null* handle.
// UnwrapPlane.cpp decides whether to take the proxy path with
//     const bool use_pamo = (CONFIG_unwrapPamo && stream != nullptr);
// so returning nullptr silently rewrites the charting -- measured on the welded 500k
// model: 93 parts / 499,804 faces became 49 parts / 113,793 faces.  The CPU backends
// never dereference the handle, so a sentinel keeps every control-flow decision intact.
namespace StreamPool {
    static void *const kNoCudaStream = reinterpret_cast<void *>(0x1);
    void asyncInitializeStreams(int) {}
    cudaStream_t getStream() { return kNoCudaStream; }
    cudaStream_t getStream(int) { return kNoCudaStream; }
    void destroyStreams() {}
}  // namespace StreamPool

#endif  // PARTUV_HAS_CUDA
