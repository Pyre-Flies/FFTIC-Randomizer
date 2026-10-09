param([Parameter(Mandatory=$true)][string]$AuditFolder)
$ErrorActionPreference='Stop'
$project=Split-Path $PSScriptRoot -Parent
$audit=[IO.Path]::GetFullPath((Resolve-Path -LiteralPath $AuditFolder).Path)
if (-not $audit.StartsWith((Join-Path $project 'research')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Audit is outside project research' }
$launch=Get-Content -LiteralPath (Join-Path $audit 'launch.json') -Raw | ConvertFrom-Json
$process=Get-Process -Id $launch.game_pid
if ($process.ProcessName -ne 'FFT_enhanced' -or $process.Path -ne $launch.executable -or $process.StartTime.ToUniversalTime().Ticks -ne ([DateTime]$launch.game_start_utc).ToUniversalTime().Ticks) { throw 'Not our recorded validation session' }
$manifest=Get-Content -LiteralPath (Join-Path $launch.seed_folder 'manifest.json') -Raw | ConvertFrom-Json
$manifestHash=(Get-FileHash -LiteralPath (Join-Path $launch.seed_folder 'manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($manifestHash -ne $launch.manifest_sha256) { throw 'Seed no longer matches launch' }
$fresh=Get-ChildItem -LiteralPath (Join-Path $env:APPDATA 'Reloaded-Mod-Loader-II\Logs') -Filter '*FFT_enhanced*' -File |
    Where-Object CreationTimeUtc -GE ([DateTime]$launch.launch_utc).ToUniversalTime() | Sort-Object CreationTimeUtc -Descending | Select-Object -First 1
if ($null -eq $fresh) { throw 'No fresh Reloaded log' }
$text=Get-Content -LiteralPath $fresh.FullName -Raw
$errors=@($text -split '\r?\n' | Where-Object { $_ -match '\bErrored\b|\[Error\]|Could not assign|\bExceptions?\b|\bConflicts?\b|\bFailed\b|cannot apply|missing from nex' })
if ($errors.Count) { throw ($errors -join "`n") }
$warnings=@($text -split '\r?\n' | Where-Object { $_ -match 'Pattern .*not found!' })
$unexpectedWarnings=@($warnings | Where-Object { $_ -notmatch 'Pattern CFILE_DAT__Decode not found!' })
if ($unexpectedWarnings.Count) { throw ('Unexpected scan warnings: '+($unexpectedWarnings -join "`n")) }
if ($warnings.Count -and $text -notmatch 'Found pattern CFILE_DAT__DecodeAlt @') { throw 'Existing Decode fallback warning lacks its alternate scan result' }
if ($text -notmatch 'Game successfully loaded modded pack') { throw 'Merged pack was not loaded' }
$tables=@(Get-ChildItem -LiteralPath (Join-Path $launch.seed_folder 'fftivc.randomizer.seed\FFTIVC\tables\enhanced') -Filter '*.xml' -File | ForEach-Object BaseName)
foreach ($table in $tables) { if ($text -notmatch ('Applying '+$table+' with \d+ change')) { throw ('XML application missing: '+$table) } }
foreach ($table in $manifest.nex_changes.tables) {
    $name=$table.ToLowerInvariant().Replace('-','.')
    if ($text -notmatch ("Processing nex changes for '"+[regex]::Escape($name)+"'")) { throw ('Nex application missing: '+$table) }
}
$nativePath='C:\Reloaded-II\Mods\fftivc.randomizer.seed\runtime-patches.log'
$native=Get-Content -LiteralPath $nativePath -Raw
if ($native -notmatch ('Starting process '+$launch.game_pid+'\b') -or $native -notmatch ('PASS: '+$manifest.native_runtime.patches.Count+' guarded patch ranges applied') -or $native -match 'REJECTED|Failed|Error') { throw 'Native patch startup failed or belongs to a different process' }
$readback=Get-Content -LiteralPath (Join-Path $audit 'readback-result.json') -Raw | ConvertFrom-Json
if ($readback.result -ne 'passed' -or $readback.game_pid -ne $launch.game_pid -or $readback.manifest_sha256 -ne $manifestHash -or $readback.launch_utc -ne $launch.launch_utc) { throw 'Readback has not passed for this seed and process' }
foreach ($property in $readback.merged.pack_sha256.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path (Split-Path $launch.executable -Parent) ('data\enhanced\'+$property.Name)) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw 'Merged pack changed after comparison' }
}
foreach ($property in $manifest.payload_sha256.PSObject.Properties) {
    if ($property.Name -eq 'ModConfig.json') { continue }
    if ((Get-FileHash -LiteralPath (Join-Path 'C:\Reloaded-II\Mods\fftivc.randomizer.seed' $property.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw ('Installed payload differs: '+$property.Name) }
}
$config=Get-Content -LiteralPath 'C:\Reloaded-II\Mods\fftivc.randomizer.seed\ModConfig.json' -Raw | ConvertFrom-Json
if ($config.ModVersion -ne $manifest.generator_version -or $config.ModDll -ne $manifest.native_runtime.bridge -or $config.ModNativeDll64 -or $config.ModNativeDll32) { throw 'Installed managed startup config identity differs' }
$originals=Get-Content -LiteralPath (Join-Path $audit 'originals.json') -Raw | ConvertFrom-Json
foreach ($property in $originals.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path (Split-Path $launch.executable -Parent) $property.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw ('Original file changed: '+$property.Name) }
}
if (-not $process.Responding) { throw 'Game is not responding' }
$seconds=[math]::Round(([DateTime]::UtcNow-$process.StartTime.ToUniversalTime()).TotalSeconds,1)
Copy-Item -LiteralPath $fresh.FullName -Destination (Join-Path $audit 'reloaded-full.log') -Force
Copy-Item -LiteralPath $nativePath -Destination (Join-Path $audit 'runtime-patches.log') -Force
if (-not $process.CloseMainWindow()) { throw 'Could not request closure of our validation session' }
$process.WaitForExit(15000) | Out-Null
if (-not $process.HasExited) { throw 'Our validation session did not close within15seconds' }
$result=[ordered]@{result='passed';seed=$manifest.seed;version=$manifest.generator_version;flags=$manifest.flags;ability_mode=$manifest.ability_mode;full_settings=$manifest.full_settings;secret_codes=$manifest.secret_codes;seed_folder=$launch.seed_folder;manifest_sha256=$manifestHash;log=$fresh.FullName;xml_tables=$tables;nex_tables=$manifest.nex_changes.tables;native_ranges=$manifest.native_runtime.patches.Count;merged_assets=$readback.merged.asset_count;errors=@();warnings=$warnings;responding=$true;runtime_seconds=$seconds;graceful_close=$true;original_files_unchanged=$true;original_file_count=@($originals.PSObject.Properties).Count;gameplay='No battle, shop interaction or save input was performed'}
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $audit 'result.json') -Encoding utf8
$result | ConvertTo-Json -Depth 10
