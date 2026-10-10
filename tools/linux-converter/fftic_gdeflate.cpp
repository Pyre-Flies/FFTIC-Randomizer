// Bounded adapter for the official Microsoft/NVIDIA GDeflate reference format.
// Codec and format definitions: microsoft/DirectStorage, pinned by build.py.
#include "fftic_gdeflate.h"
#include <libdeflate.h>
#include <algorithm>
#include <memory>

namespace {
constexpr size_t tile_size = 65536;

uint32_t read_le32(const uint8_t* p) {
    return uint32_t(p[0]) | (uint32_t(p[1]) << 8) |
           (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}

struct DecompressorDeleter {
    void operator()(libdeflate_gdeflate_decompressor* p) const {
        libdeflate_free_gdeflate_decompressor(p);
    }
};
}

extern "C" FFTIC_GDEFLATE_API int fftic_gdeflate_decompress(
    const uint8_t* input, size_t input_size,
    uint8_t* output, size_t output_capacity, size_t* output_size) {
    if (!output_size)
        return -1;
    *output_size = 0;
    if (!input || !output)
        return -1;
    if (input_size < 8)
        return -2;

    // Parse bytes explicitly: the upstream packed header contains bitfields.
    // Codec id 4, its complemented magic byte, and the 64 KiB tile index are
    // required. Reserved bits and impossible final-tile sizes are rejected.
    const size_t tile_count = size_t(input[2]) | (size_t(input[3]) << 8);
    const uint32_t sizes = read_le32(input + 4);
    const size_t tail_size = (sizes >> 2) & 0x3ffffu;
    if (input[0] != 4 || input[1] != uint8_t(4 ^ 0xff) || !tile_count ||
        (sizes & 3u) != 1u || (sizes >> 20) || tail_size >= tile_size)
        return -2;
    const size_t decoded_size = (tile_count - 1) * tile_size +
                               (tail_size ? tail_size : tile_size);
    if (decoded_size > output_capacity)
        return -3;
    const size_t table_end = 8 + tile_count * 4;
    if (table_end > input_size)
        return -2;
    const uint8_t* table = input + 8;
    const uint8_t* data = input + table_end;
    const size_t data_size = input_size - table_end;
    const size_t last_compressed_size = read_le32(table);
    if (!last_compressed_size)
        return -2;

    // Validate every page boundary before giving the reference decoder a pointer.
    // Offset 0 stores the final page's compressed size; page 0 starts at zero.
    size_t previous = 0;
    for (size_t tile = 1; tile < tile_count; ++tile) {
        const size_t offset = read_le32(table + tile * 4);
        if (offset <= previous || offset >= data_size)
            return -2;
        previous = offset;
    }
    if (previous > data_size || last_compressed_size > data_size - previous)
        return -2;

    std::unique_ptr<libdeflate_gdeflate_decompressor, DecompressorDeleter>
        decompressor(libdeflate_alloc_gdeflate_decompressor());
    if (!decompressor)
        return -5;

    for (size_t tile = 0; tile < tile_count; ++tile) {
        const size_t offset = tile ? read_le32(table + tile * 4) : 0;
        const size_t compressed_size = tile + 1 < tile_count
            ? read_le32(table + (tile + 1) * 4) - offset
            : last_compressed_size;
        const size_t expected_size = std::min(tile_size, decoded_size - tile * tile_size);
        libdeflate_gdeflate_in_page page{data + offset, compressed_size};
        size_t actual_size = 0;
        const libdeflate_result result = libdeflate_gdeflate_decompress(
            decompressor.get(), &page, 1, output + tile * tile_size,
            expected_size, &actual_size);
        if (result != LIBDEFLATE_SUCCESS || actual_size != expected_size)
            return -4;
    }
    *output_size = decoded_size;
    return 0;
}
