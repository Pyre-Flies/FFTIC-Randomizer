cmake_minimum_required(VERSION 3.19)
project(FFTICGDeflate LANGUAGES C CXX)
include(CTest)

set(DIRECTSTORAGE_SOURCE "" CACHE PATH "Pinned microsoft/DirectStorage checkout")
if(NOT EXISTS "${DIRECTSTORAGE_SOURCE}/GDeflate/3rdparty/libdeflate/libdeflate.h")
    message(FATAL_ERROR "Set DIRECTSTORAGE_SOURCE to the pinned source with its libdeflate submodule initialized")
endif()
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(LIBDEFLATE_SOURCE "${DIRECTSTORAGE_SOURCE}/GDeflate/3rdparty/libdeflate")
set(GDEFLATE_SOURCE "${DIRECTSTORAGE_SOURCE}/GDeflate/GDeflate")

set(CODEC_SOURCES
    lib/adler32.c lib/crc32.c lib/deflate_compress.c lib/deflate_decompress.c
    lib/gdeflate_compress.c lib/gdeflate_decompress.c lib/gzip_compress.c
    lib/gzip_decompress.c lib/utils.c lib/zlib_compress.c lib/zlib_decompress.c
    lib/x86/cpu_features.c)
list(TRANSFORM CODEC_SOURCES PREPEND "${LIBDEFLATE_SOURCE}/")
add_library(fftic_reference_deflate STATIC ${CODEC_SOURCES})
target_include_directories(fftic_reference_deflate PUBLIC "${LIBDEFLATE_SOURCE}")
set_target_properties(fftic_reference_deflate PROPERTIES C_VISIBILITY_PRESET hidden)

add_library(fftic_gdeflate SHARED fftic_gdeflate.cpp fftic_gdeflate.h)
target_compile_definitions(fftic_gdeflate PRIVATE FFTIC_GDEFLATE_BUILD)
target_compile_features(fftic_gdeflate PRIVATE cxx_std_17)
target_link_libraries(fftic_gdeflate PRIVATE fftic_reference_deflate)
set_target_properties(fftic_gdeflate PROPERTIES CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN ON)

if(BUILD_TESTING)
    find_package(Threads REQUIRED)
    add_library(fftic_reference_framing STATIC
        "${GDEFLATE_SOURCE}/GDeflateCompress.cpp"
        "${GDEFLATE_SOURCE}/GDeflateDecompress.cpp")
    target_include_directories(fftic_reference_framing PUBLIC "${GDEFLATE_SOURCE}")
    target_compile_features(fftic_reference_framing PRIVATE cxx_std_17)
    target_link_libraries(fftic_reference_framing PRIVATE fftic_reference_deflate Threads::Threads)
    # Upstream relies on a transitive <memory> include in its Windows build.
    if(MSVC)
        target_compile_options(fftic_reference_framing PRIVATE /FI"memory")
    else()
        target_compile_options(fftic_reference_framing PRIVATE -include memory)
    endif()
    add_executable(fftic_gdeflate_test codec_test.cpp)
    target_compile_features(fftic_gdeflate_test PRIVATE cxx_std_17)
    target_link_libraries(fftic_gdeflate_test PRIVATE fftic_gdeflate fftic_reference_framing fftic_reference_deflate)
    add_test(NAME gdeflate-reference-and-bounds COMMAND fftic_gdeflate_test)
endif()

install(TARGETS fftic_gdeflate LIBRARY DESTINATION . RUNTIME DESTINATION .)
