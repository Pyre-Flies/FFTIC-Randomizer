#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#ifdef FFTIC_GDEFLATE_BUILD
#define FFTIC_GDEFLATE_API __declspec(dllexport)
#else
#define FFTIC_GDEFLATE_API __declspec(dllimport)
#endif
#else
#define FFTIC_GDEFLATE_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Returns 0 on success; output_size is reset to zero on failure.
 * The declared stream size may be smaller than output_capacity, never larger.
 * Error codes: -1 invalid argument, -2 malformed framing, -3 output too small,
 * -4 malformed compressed page or decoded size mismatch, -5 allocation failure.
 */
FFTIC_GDEFLATE_API int fftic_gdeflate_decompress(
    const uint8_t* input, size_t input_size,
    uint8_t* output, size_t output_capacity, size_t* output_size);

#ifdef __cplusplus
}
#endif
