// Owned startup bridge: preserve Nenkai's original scan signatures until its
// dependency-ordered initialization callback has completed scans and XML/PAC
// application. Do not load the native patch DLL from Start/StartEx.
// Exact installed scanner/loader IL evidence:
// research/reloaded-finalized-scanner-il.txt
// research/reloaded-scanner-barrier-il.txt
using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Threading;
using Reloaded.Mod.Interfaces;
using Reloaded.Mod.Interfaces.Internal;

[assembly: AssemblyVersion("1.0.0.0")]
[assembly: TargetFramework(".NETCoreApp,Version=v9.0")]

namespace Fftic.Randomizer.Startup
{
    public sealed class RuntimeBridge : IMod
    {
        private IModLoader? _loader;
        private ILogger? _logger;
        private string? _directory;
        private int _registered;
        private int _invoked;
        // Patches and their native callbacks must remain loaded for the
        // process lifetime; CanUnload and CanSuspend both remain false.
        private IntPtr _nativeModule;

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private delegate void InitDelegate();

        public void Start(IModLoaderV1 loaderApi)
        {
            Register(loaderApi, "fftivc.randomizer.seed");
        }

        public void StartEx(IModLoaderV1 loaderApi, IModConfigV1 modConfig)
        {
            Register(loaderApi, modConfig.ModId);
        }

        private void Register(IModLoaderV1 loaderApi, string modId)
        {
            if (Interlocked.Exchange(ref _registered, 1) != 0)
                return;
            _loader = loaderApi as IModLoader
                ?? throw new InvalidOperationException("Reloaded API cannot provide the mod directory.");
            _logger = _loader.GetLogger() as ILogger;
            _directory = _loader.GetDirectoryForModId(modId);
            // Reloaded loads the declared Nenkai dependency before this mod.
            // Its scanner's handler completes queued callbacks synchronously,
            // then Nenkai applies its pack/XML changes, then this handler runs.
            _loader.OnModLoaderInitialized += ApplyAfterLoaderInitialization;
            _logger?.WriteLine("[fftivc.randomizer.startup] Registered native initialization after loader scans and table changes.");
        }

        private void ApplyAfterLoaderInitialization()
        {
            if (Interlocked.Exchange(ref _invoked, 1) != 0)
                return;
            if (_loader != null)
                _loader.OnModLoaderInitialized -= ApplyAfterLoaderInitialization;
            try
            {
                string path = Path.Combine(_directory
                    ?? throw new InvalidOperationException("Mod directory is unavailable."),
                    "fftic-rcc-runtime.dll");
                _logger?.WriteLine("[fftivc.randomizer.startup] Loader initialization completed; applying guarded native changes.");
                _nativeModule = NativeLibrary.Load(path);
                IntPtr entry = NativeLibrary.GetExport(_nativeModule, "Init");
                Marshal.GetDelegateForFunctionPointer<InitDelegate>(entry)();
                // Native Init records PASS/FAILED in runtime-patches.log.
                // Its void return alone does not establish successful patches.
            }
            catch (Exception error)
            {
                _logger?.WriteLine("[fftivc.randomizer.startup] FAILED: " + error);
            }
        }

        public bool CanUnload() => false;
        public bool CanSuspend() => false;
        public void Suspend() { }
        public void Resume() { }
        public void Unload() { }
        public Action Disposing => () => { };
    }
}
