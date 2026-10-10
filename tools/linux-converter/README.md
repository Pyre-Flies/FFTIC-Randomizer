# Linux FF16Tools converter

This build overlay gives the randomizer a native Linux archive extractor. It
replaces the Windows DirectStorage `GDeflate.cs` adapter in a private, pinned
FF16Tools checkout. NXD/SQLite conversion and the archive reader are unchanged.
The resulting converter includes its .NET runtime and does not need Wine,
Proton, Windows DirectStorage, or a separately installed .NET runtime.
The build retains the original layout filenames and adds byte-identical
lowercase copies because native NXD filenames are lowercase and Linux lookup
is case sensitive. Layout parsing and table-name metadata are unchanged.

Install Git, CMake 3.19 or newer, a C/C++ compiler, Python, and .NET SDK 9.0.318.
From the randomizer source root, run:

```sh
python3 tools/linux-converter/build.py --output research/linux-build/converter
```

The output contains `FF16Tools.CLI`, `libfftic_gdeflate.so`, runtime and managed
dependencies, layouts, notices, and a build receipt with file hashes. The main
Linux packager bundles that folder. Developer checkouts and game files are
never modified. Build inputs and logs remain under `research`.
The helper writes a pinned `global.json` in its private build work folder so
an installed newer SDK does not replace SDK 9.0.318.

The converter is for extraction and table conversion. GDeflate archive packing
throws an explicit `NotSupportedException`. The randomizer writes loose mod
files and does not need archive packing.

## Pinned sources

- FF16Tools 1.13.3 source: `14361aefa1e1265096b42cad95cd9f01550a0457`
- Microsoft DirectStorage: `c53f1499d5f67a61b69a1a348d22dcd2b4cb4ede`
- Its NVIDIA libdeflate submodule: `8ba9502fb30d2bf728592d121f0d402e40c8cb05`
- FFTIC layouts: `d4a60952531d82bfd8a4fbb76b1f9b363f721dc1`
- FF16 layouts: `d3ad0627a29af168916ad574dadbca6759e2ac48`
- .NET runtime: 9.0.20; SDK: 9.0.318

FF16Tools and the layout repositories are MIT. The DirectStorage repository
includes MIT terms; its GDeflate reference code and NVIDIA additions use
Apache-2.0. NVIDIA libdeflate's `COPYING` retains both the original Eric Biggers
MIT terms and NVIDIA Apache-2.0 notice. The build copies their full notices plus
the runtime and NuGet dependency notices into the output's `licenses` folder.
Notice archives must match the exact packages restored by the SDK. Their raw
SHA512 hashes are checked against NuGet's archive receipts; their separate
unsigned-content hashes are checked against project assets, published dependency
metadata, and NuGet content receipts. Both hashes are recorded in the notices.

## Codec checks

The native wrapper explicitly validates the stream header, offsets, output
capacity, and decoded size of every page. It calls the official CPU page decoder
with the exact remaining capacity. It returns the stream's actual output size,
including when the caller disables the exact-buffer-size check.

The CMake test creates 24 deterministic zero-filled, repeating, and pseudo-random
fixtures, from 1 byte through multiple 64 KiB tiles and 3 MiB. It compares the
wrapper with the official reference compressor and whole-stream decoder, checks
malformed/truncated streams and guard bytes, and writes fixtures for the managed
adapter test. No game data is included in these synthetic fixtures.

The published converter is also tested end to end: two hand-authored PACK
archives exercise specific and shared compressed chunks through the actual CLI,
with byte-for-byte output checks. A hand-authored SQLite table is converted to
NXD and back, retaining integer, UTF-8 string, and float cells exactly. This tests
the converter's native codec and SQLite library loading, layout discovery, and
Linux path handling together.

To run only the native tests, initialize the pinned DirectStorage libdeflate
submodule and run:

```sh
cmake -S tools/linux-converter -B research/gdeflate-test \
  -DCMAKE_BUILD_TYPE=Release -DDIRECTSTORAGE_SOURCE=/path/to/DirectStorage
cmake --build research/gdeflate-test --config Release
ctest --test-dir research/gdeflate-test --build-config Release --output-on-failure
```

This CMake target also supports MSVC x64 for comparing the CPU decoder against
the Windows DirectStorage decoder. That diagnostic DLL is not bundled in the
Windows randomizer. Its exported C ABI is `fftic_gdeflate_decompress` in
`fftic_gdeflate.h`.
