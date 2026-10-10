using FF16Tools.Shared;

if (args.Length != 1)
    throw new ArgumentException("Supply the synthetic fixture directory.");

void Require(bool condition, string detail)
{
    if (!condition)
        throw new InvalidOperationException(detail);
}

void Invalid(Action action)
{
    try { action(); }
    catch (InvalidDataException) { return; }
    throw new InvalidOperationException("Invalid buffer was accepted by the managed adapter.");
}

int tested = 0;
foreach (string fixture in Directory.GetFiles(args[0], "*.gdeflate"))
{
    byte[] compressed = File.ReadAllBytes(fixture);
    byte[] expected = File.ReadAllBytes(Path.ChangeExtension(fixture, ".bin"));
    byte[] output = new byte[expected.Length];
    Require(GDeflate.Decompress(compressed, output) == (ulong)expected.Length,
        "Managed adapter returned the wrong size.");
    Require(output.SequenceEqual(expected), "Managed adapter returned different bytes.");
    byte[] larger = new byte[expected.Length + 32];
    Require(GDeflate.Decompress(compressed, larger, checkSize: false) == (ulong)expected.Length,
        "checkSize=false returned the destination capacity instead of the stream size.");
    Require(larger.AsSpan(0, expected.Length).SequenceEqual(expected), "Oversized output changed decoded bytes.");
    Invalid(() => GDeflate.Decompress(compressed, larger));
    Invalid(() => GDeflate.Decompress(compressed, new byte[expected.Length - 1]));
    Invalid(() => GDeflate.Decompress(compressed.AsSpan(0, compressed.Length - 1), output));
    tested++;
}
Require(tested == 24, "Expected all 24 native-generated fixtures.");
try { GDeflate.Compress(new byte[1], new byte[32]); throw new Exception("Packing was accepted."); }
catch (NotSupportedException) { }
try { GDeflate.CompressionSize(1); throw new Exception("Packing bound was accepted."); }
catch (NotSupportedException) { }
Console.WriteLine($"Managed GDeflate adapter: {tested} reference fixtures and unsupported-packing checks passed.");
