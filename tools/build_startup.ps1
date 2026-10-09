param([string]$OutputFolder, [string]$ReloadedSdkPath='C:\Reloaded-II\Reloaded.Mod.Interfaces.dll')
$ErrorActionPreference='Stop'
$project=Split-Path $PSScriptRoot -Parent
if ([string]::IsNullOrWhiteSpace($OutputFolder)) { $OutputFolder=Join-Path $project 'research\startup-build' }
$OutputFolder=[IO.Path]::GetFullPath($OutputFolder)
if (-not $OutputFolder.StartsWith($project+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Startup output must stay inside the project' }
if (-not (Test-Path -LiteralPath $ReloadedSdkPath -PathType Leaf)) { throw 'Local Reloaded.Mod.Interfaces.dll is required to build the startup bridge' }
# PowerShell supplies Roslyn. Its own runtime may be newer than Reloaded's;
# use explicit .NET9 metadata references so this output never requires NET10.
$runtimeRoot=Join-Path $env:ProgramFiles 'dotnet\shared\Microsoft.NETCore.App'
$runtime=Get-ChildItem -LiteralPath $runtimeRoot -Directory | Where-Object { $_.Name -match '^9\.[0-9]+\.[0-9]+$' } | Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1
if ($null -eq $runtime) { throw 'Local .NET9 runtime metadata is required to build the startup bridge' }
foreach ($assemblyName in @('Microsoft.CodeAnalysis.dll','Microsoft.CodeAnalysis.CSharp.dll')) {
    $assemblyPath=Join-Path $PSHOME $assemblyName
    if (-not (Test-Path -LiteralPath $assemblyPath -PathType Leaf)) { throw 'PowerShell7 bundled Roslyn is unavailable' }
    [Reflection.Assembly]::LoadFrom($assemblyPath) | Out-Null
}
$source=Join-Path $project 'native\startup\RuntimeBridge.cs'
$paths=@('System.Private.CoreLib.dll','System.Runtime.dll','System.Runtime.InteropServices.dll','System.Threading.dll','System.Drawing.Primitives.dll') | ForEach-Object { Join-Path $runtime.FullName $_ }
$paths+=([IO.Path]::GetFullPath($ReloadedSdkPath))
$references=[Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
foreach ($path in $paths) { $references.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($path)) }
$parseOptions=[Microsoft.CodeAnalysis.CSharp.CSharpParseOptions]::Default.WithLanguageVersion([Microsoft.CodeAnalysis.CSharp.LanguageVersion]::Latest)
$tree=[Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([IO.File]::ReadAllText($source),$parseOptions,$source,[Text.Encoding]::UTF8)
$options=[Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]::DynamicallyLinkedLibrary)
$options=$options.WithOptimizationLevel([Microsoft.CodeAnalysis.OptimizationLevel]::Release).WithPlatform([Microsoft.CodeAnalysis.Platform]::X64).WithNullableContextOptions([Microsoft.CodeAnalysis.NullableContextOptions]::Enable).WithDeterministic($true)
$trees=[Collections.Generic.List[Microsoft.CodeAnalysis.SyntaxTree]]::new();$trees.Add($tree)
$compilation=[Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create('fftic-rcc-startup',$trees,$references,$options)
New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
$dll=Join-Path $OutputFolder 'fftic-rcc-startup.dll'
$stream=[IO.File]::Open($dll,[IO.FileMode]::Create,[IO.FileAccess]::Write)
try { $result=$compilation.Emit($stream) } finally { $stream.Dispose() }
if (-not $result.Success) {
    $result.Diagnostics | ForEach-Object { Write-Output $_.ToString() }
    throw 'Startup bridge compilation failed'
}
$joined=[Collections.Generic.List[byte]]::new()
foreach ($path in @($source,$PSCommandPath)) { $joined.AddRange([IO.File]::ReadAllBytes($path)) }
$sourceHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($joined.ToArray())).ToLowerInvariant()
$receiptPath=Join-Path $OutputFolder 'build.json'
# The shipped directory also contains the native build receipt. Preserve its
# fields and append only the startup bridge's separately guarded identity.
$receipt=if(Test-Path -LiteralPath $receiptPath -PathType Leaf) { Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json -AsHashtable } else { [ordered]@{} }
$receipt['bridge_source_sha256']=$sourceHash
$receipt['bridge_dll_sha256']=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
$receipt['bridge_source']='native/startup/RuntimeBridge.cs'
$receipt['bridge_target_framework']='.NETCoreApp,Version=v9.0'
$receipt['bridge_compiler']='PowerShell7 bundled Roslyn; explicit local .NET9 runtime metadata; deterministic x64 Release'
$receipt['bridge_runtime_metadata_version']=$runtime.Name
$receipt['bridge_reloaded_interfaces_sha256']=(Get-FileHash -LiteralPath $ReloadedSdkPath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($receiptPath,($receipt | ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output $dll
