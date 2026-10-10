// Linux-only replacement for FF16Tools.Shared/GDeflate.cs, applied by build.py.
// FF16Tools is Copyright (c) 2025 Nenkai, distributed under MIT.
// This adapter uses the Microsoft/NVIDIA CPU reference codec through a bounded C ABI.
using System;
using System.IO;
using System.Runtime.InteropServices;

namespace FF16Tools.Shared;

public class GDeflate
{
    [DllImport("fftic_gdeflate", EntryPoint = "fftic_gdeflate_decompress",
        CallingConvention = CallingConvention.Cdecl)]
    private static extern unsafe int NativeDecompress(
        byte* source, nuint sourceSize, byte* destination, nuint destinationSize,
        out nuint actualSize);

    public static ulong Decompress(Span<byte> compressedData, Span<byte> decompressedData,
        bool checkSize = true)
    {
        unsafe
        {
            fixed (byte* source = compressedData)
            fixed (byte* destination = decompressedData)
            {
                int result = NativeDecompress(source, (nuint)compressedData.Length,
                    destination, (nuint)decompressedData.Length, out nuint actualSize);
                if (result != 0)
                    throw new InvalidDataException($"GDeflate decompression failed (CPU codec error {result}).");
                if (checkSize && actualSize != (nuint)decompressedData.Length)
                    throw new InvalidDataException($"Failed to decompress. Expected to decompress 0x{decompressedData.Length:X}, decompressed 0x{actualSize:X}");
                return (ulong)actualSize;
            }
        }
    }

    public static uint Compress(Span<byte> decompressedData, Span<byte> outputCompressedData)
        => throw new NotSupportedException("This Linux converter supports archive extraction and table conversion. GDeflate archive packing is unavailable.");

    public static long CompressionSize(ulong size)
        => throw new NotSupportedException("This Linux converter supports archive extraction and table conversion. GDeflate archive packing is unavailable.");
}
