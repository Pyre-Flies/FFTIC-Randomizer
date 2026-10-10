// Authored Linux converter diagnostic. Included by the private build overlay;
// ordinary FF16Tools commands continue through the original upstream entry point.
using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;

namespace FFTIC.LinuxConverter;

internal static class GlobalizationProbe
{
    private const string IcuVersion = "72.1.0.3";

    [ModuleInitializer]
    internal static void RunIfRequested()
    {
        if (!Environment.GetCommandLineArgs().Contains("--fftic-globalization-probe"))
            return;
        Console.OutputEncoding = Encoding.UTF8;
        string configured = AppContext.GetData("System.Globalization.AppLocalIcu")?.ToString() ?? "";
        Require(!AppContext.TryGetSwitch("System.Globalization.Invariant", out bool invariant) || !invariant,
            "Globalization invariant mode was enabled.");

        var french = CultureInfo.GetCultureInfo("fr-FR");
        var turkish = CultureInfo.GetCultureInfo("tr-TR");
        var japanese = CultureInfo.GetCultureInfo("ja-JP");
        var chinese = CultureInfo.GetCultureInfo("zh-CN");
        string frenchNumber = 1234.5.ToString(french);
        string turkishUpper = "istanbul".ToUpper(turkish);
        Require(frenchNumber == "1234,5", "French decimal formatting is unavailable.");
        Require(turkishUpper == "İSTANBUL", "Turkish Unicode casing is unavailable.");
        Require(japanese.DateTimeFormat.GetDayName(DayOfWeek.Monday).Contains('月'),
            "Japanese culture data is unavailable.");
        Require(chinese.DateTimeFormat.GetMonthName(1).Contains('月'),
            "Chinese culture data is unavailable.");
        Require("Cafe\u0301".Normalize(NormalizationForm.FormC) == "Café",
            "Unicode normalization is unavailable.");
        // Initialize real globalization before checking the configured version.
        // A negative control with a missing ICU version must exercise the CLR's
        // native-library loading failure, rather than fail our version assertion.
        Require(configured == IcuVersion, "The converter is not configured for its pinned app-local ICU.");

        string[] libraries = { $"libicudata.so.{IcuVersion}", $"libicuuc.so.{IcuVersion}",
            $"libicui18n.so.{IcuVersion}" };
        string[] maps = File.ReadAllLines("/proc/self/maps");
        foreach (string library in libraries)
        {
            string expectedPath = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, library));
            string[] loaded = maps.Where(line => line.Contains(library, StringComparison.Ordinal)).ToArray();
            Require(loaded.Length > 0 && loaded.All(line => line.EndsWith(expectedPath, StringComparison.Ordinal)),
                $"ICU library {library} was not loaded exclusively from the converter directory.");
        }
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            result = "passed",
            icu_version = IcuVersion,
            invariant_mode = false,
            icu_from_app_directory = true,
            icu_libraries = libraries,
            culture_checks = new[] { "fr-FR", "tr-TR", "ja-JP", "zh-CN" },
            normalization = "passed",
            french_decimal = frenchNumber,
            turkish_upper = turkishUpper,
        }));
        Environment.Exit(0);
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
            throw new InvalidOperationException(message);
    }
}
