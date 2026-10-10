#include "fftic_gdeflate.h"
#include <GDeflate.h>
#include <algorithm>
#include <array>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool result, const char* detail) {
    if (!result)
        throw std::runtime_error(detail);
}

void write_file(const std::filesystem::path& path, const std::vector<uint8_t>& bytes) {
    std::ofstream stream(path, std::ios::binary);
    stream.write(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    require(bool(stream), "Could not write synthetic fixture");
}

std::vector<uint8_t> make_input(size_t size, unsigned pattern) {
    std::vector<uint8_t> input(size);
    uint32_t state = 0x13579bdu;
    for (size_t i = 0; i < size; ++i) {
        state = state * 1664525u + 1013904223u;
        input[i] = pattern == 0 ? 0 : pattern == 1 ? uint8_t(i % 251) : uint8_t(state >> 24);
    }
    return input;
}

std::vector<uint8_t> compress(const std::vector<uint8_t>& input) {
    std::vector<uint8_t> compressed(GDeflate::CompressBound(input.size()));
    size_t size = compressed.size();
    require(GDeflate::Compress(compressed.data(), &size, input.data(), input.size(),
        6, GDeflate::COMPRESS_SINGLE_THREAD), "Reference compression failed");
    require(size <= compressed.size(), "Reference output exceeded its bound");
    compressed.resize(size);
    return compressed;
}

void expect_failure(const std::vector<uint8_t>& stream, size_t capacity) {
    std::vector<uint8_t> output(capacity + 32, 0xa5);
    size_t written = 999;
    const int result = fftic_gdeflate_decompress(stream.data(), stream.size(),
        output.data(), capacity, &written);
    require(result != 0 && written == 0, "Malformed stream was accepted");
    require(std::all_of(output.begin() + capacity, output.end(),
        [](uint8_t byte) { return byte == 0xa5; }), "Decoder crossed the output capacity");
}

void test_corruption(const std::vector<uint8_t>& valid, size_t size) {
    for (size_t length = 0; length < std::min(size_t(24), valid.size()); ++length)
        expect_failure(std::vector<uint8_t>(valid.begin(), valid.begin() + length), size);
    expect_failure(std::vector<uint8_t>(valid.begin(), valid.end() - 1), size);
    expect_failure(valid, size - 1);
    for (size_t offset : {size_t(0), size_t(1), size_t(4), size_t(7)}) {
        auto corrupt = valid;
        corrupt[offset] ^= offset == 7 ? 0x80 : 1;
        expect_failure(corrupt, size);
    }
    auto corrupt = valid;
    corrupt[2] = corrupt[3] = 0;
    expect_failure(corrupt, size);
    corrupt = valid;
    corrupt[8] = corrupt[9] = corrupt[10] = corrupt[11] = 0xff;
    expect_failure(corrupt, size);
    if (size > 65536) {
        corrupt = valid;
        corrupt[12] = corrupt[13] = corrupt[14] = corrupt[15] = 0;
        expect_failure(corrupt, size);
    }
    // The header declares 1 byte less while the bitstream remains valid:
    // the decoder must detect a page-size mismatch, without writing past it.
    if (size % 65536 > 1) {
        corrupt = valid;
        uint32_t field = uint32_t(corrupt[4]) | (uint32_t(corrupt[5]) << 8) |
            (uint32_t(corrupt[6]) << 16) | (uint32_t(corrupt[7]) << 24);
        field -= 4;
        for (size_t i = 0; i < 4; ++i)
            corrupt[4 + i] = uint8_t(field >> (8 * i));
        expect_failure(corrupt, size - 1);
    }
}
}

int main(int argc, char** argv) {
    try {
        std::filesystem::path fixture_directory;
        if (argc == 3 && std::string(argv[1]) == "--fixtures") {
            fixture_directory = argv[2];
            std::filesystem::create_directories(fixture_directory);
        } else if (argc != 1) {
            throw std::runtime_error("Usage: fftic_gdeflate_test [--fixtures DIRECTORY]");
        }
        size_t cases = 0;
        for (size_t size : {size_t(1), size_t(32), size_t(65535), size_t(65536),
                size_t(65537), size_t(131072), size_t(131089), size_t(3145759)}) {
            for (unsigned pattern = 0; pattern < 3; ++pattern) {
                auto input = make_input(size, pattern);
                auto compressed = compress(input);
                std::vector<uint8_t> output(size + 64, 0xa5);
                size_t written = 0;
                require(fftic_gdeflate_decompress(compressed.data(), compressed.size(),
                    output.data(), size, &written) == 0, "Bounded CPU decoder rejected reference stream");
                require(written == size && std::equal(input.begin(), input.end(), output.begin()),
                    "Reference stream did not decode to the expected bytes");
                require(std::all_of(output.begin() + size, output.end(),
                    [](uint8_t byte) { return byte == 0xa5; }), "Successful decoder crossed output capacity");
                // Valid-stream comparison with the official whole-stream decoder.
                std::vector<uint8_t> reference((size + 65535) / 65536 * 65536);
                require(GDeflate::Decompress(reference.data(), reference.size(), compressed.data(),
                    compressed.size(), 2), "Official decoder rejected its reference fixture");
                require(std::equal(input.begin(), input.end(), reference.begin()), "Official decoder mismatch");
                written = 0;
                require(fftic_gdeflate_decompress(compressed.data(), compressed.size(),
                    output.data(), output.size(), &written) == 0 && written == size,
                    "Oversized destination changed the decoded size");
                test_corruption(compressed, size);
                if (!fixture_directory.empty()) {
                    const auto stem = std::to_string(size) + "-" + std::to_string(pattern);
                    write_file(fixture_directory / (stem + ".bin"), input);
                    write_file(fixture_directory / (stem + ".gdeflate"), compressed);
                }
                ++cases;
            }
        }
        size_t written = 9;
        require(fftic_gdeflate_decompress(nullptr, 0, nullptr, 0, &written) == -1 && written == 0,
            "Invalid null buffers were accepted");
        std::cout << "GDeflate CPU codec: " << cases
            << " reference fixtures passed; framing, truncation, size and output-bound checks passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
