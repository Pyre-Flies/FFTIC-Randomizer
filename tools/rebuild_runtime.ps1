param([string]$ReloadedSdkPath='C:\Reloaded-II\Reloaded.Mod.Interfaces.dll')
$ErrorActionPreference='Stop'
$project=Split-Path $PSScriptRoot -Parent
$target=Join-Path $project 'native\runtime'
& (Join-Path $PSScriptRoot 'build_native.ps1') -OutputFolder $target
& (Join-Path $PSScriptRoot 'build_startup.ps1') -OutputFolder $target -ReloadedSdkPath $ReloadedSdkPath
$joined=[Collections.Generic.List[byte]]::new()
foreach ($relative in @('native\RuntimePatches.cpp','tools\build_native.ps1')) {
    $joined.AddRange([IO.File]::ReadAllBytes((Join-Path $project $relative)))
}
$receiptPath=Join-Path $target 'build.json'
$receipt=Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json -AsHashtable
$receipt['source_sha256']=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($joined.ToArray())).ToLowerInvariant()
$receipt['dll_sha256']=(Get-FileHash -LiteralPath (Join-Path $target 'fftic-rcc-runtime.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($receiptPath,($receipt | ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'Both runtime DLLs and their source/binary receipt are ready in native/runtime.'
