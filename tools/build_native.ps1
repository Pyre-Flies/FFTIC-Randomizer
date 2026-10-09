param([string]$OutputFolder)
$ErrorActionPreference='Stop'
$project=Split-Path $PSScriptRoot -Parent
if ([string]::IsNullOrWhiteSpace($OutputFolder)) { $OutputFolder=Join-Path $project 'research\native-build' }
$OutputFolder=[IO.Path]::GetFullPath($OutputFolder)
if (-not $OutputFolder.StartsWith($project+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Native output must stay inside the project' }
New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
$vswhere='C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
$toolchain=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $toolchain) { throw 'MSVC x64 tools are required to build the runtime component' }
$vcvars=Join-Path $toolchain 'VC\Auxiliary\Build\vcvars64.bat'
$source=Join-Path $project 'native\RuntimePatches.cpp'
$build=Join-Path $OutputFolder 'build.cmd'
$dll=Join-Path $OutputFolder 'fftic-rcc-runtime.dll'
$command="@call `"$vcvars`" >nul`r`n@cl /nologo /LD /std:c++17 /O2 /MT /EHsc /W4 /Fe:`"$dll`" /Fo:`"$OutputFolder\RuntimePatches.obj`" `"$source`" /link /DYNAMICBASE /NXCOMPAT`r`n@exit /b %errorlevel%`r`n"
[IO.File]::WriteAllText($build,$command,[Text.UTF8Encoding]::new($false))
Push-Location $OutputFolder
try { & cmd.exe /d /c $build; if ($LASTEXITCODE -ne 0) { throw 'Native runtime build failed' } }
finally { Pop-Location }
Write-Output $dll
