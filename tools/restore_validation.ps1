param([Parameter(Mandatory=$true)][string]$AuditFolder)
$ErrorActionPreference='Stop'
$project=Split-Path $PSScriptRoot -Parent
$audit=[IO.Path]::GetFullPath((Resolve-Path -LiteralPath $AuditFolder).Path)
if (-not $audit.StartsWith((Join-Path $project 'research')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Audit is outside project research' }
if (@(Get-Process FFT_enhanced,FFT_classic -ErrorAction SilentlyContinue).Count) { throw 'Close the validation game before restoration' }
$launch=Get-Content -LiteralPath (Join-Path $audit 'launch.json') -Raw | ConvertFrom-Json
$deployment=Get-Content -LiteralPath (Join-Path $audit 'deployment.json') -Raw | ConvertFrom-Json
$result=Get-Content -LiteralPath (Join-Path $audit 'result.json') -Raw | ConvertFrom-Json
if ($result.result -ne 'passed' -or -not $result.graceful_close -or $result.manifest_sha256 -ne $deployment.manifest_sha256) { throw 'Completed validation identity is missing' }
$manifest=Get-Content -LiteralPath (Join-Path $launch.seed_folder 'manifest.json') -Raw | ConvertFrom-Json
$installed='C:\Reloaded-II\Mods\fftivc.randomizer.seed'
$original=[IO.Path]::GetFullPath($deployment.same_volume_backup)
if (-not $original.StartsWith('C:\Reloaded-II\RandomizerBackups\',[StringComparison]::OrdinalIgnoreCase) -or (Get-Item -LiteralPath $original).LinkType -or (Get-Item -LiteralPath $installed).LinkType) { throw 'Backup or installed path is unexpected or linked' }
foreach ($property in $manifest.payload_sha256.PSObject.Properties) {
    if ($property.Name -eq 'ModConfig.json') { continue }
    if ((Get-FileHash -LiteralPath (Join-Path $installed $property.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw ('Installed validation seed changed: '+$property.Name) }
}
$config=Get-Content -LiteralPath (Join-Path $installed 'ModConfig.json') -Raw | ConvertFrom-Json
if ($config.ModVersion -ne $deployment.version) { throw 'Installed version changed after validation' }
$overlayRoot=[IO.Path]::GetFullPath((Join-Path $deployment.backup 'overlays'))
if (-not $overlayRoot.StartsWith((Join-Path $project 'research\backups')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Overlay backup is outside project backups' }
$gameData=Join-Path (Split-Path $launch.executable -Parent) 'data\enhanced'
$overlays=@(Get-ChildItem -LiteralPath $overlayRoot -File)
if ($overlays.Count -ne @($deployment.overlay_backups).Count) { throw 'Overlay backup inventory differs' }
foreach ($file in $overlays) {
    if ($file.Name -notmatch '^modded(?:\.(?:cs|ct|de|en|fr|ja|ko))?\.pac$' -or $file.Name -notin $deployment.overlay_backups) { throw 'Unexpected overlay backup file' }
}
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$stage=[IO.Path]::GetFullPath(('C:\Reloaded-II\RandomizerStaging\restore-'+$stamp))
$completed=[IO.Path]::GetFullPath(('C:\Reloaded-II\RandomizerBackups\validation-completed-'+$stamp+'\fftivc.randomizer.seed'))
if (-not $stage.StartsWith('C:\Reloaded-II\RandomizerStaging\',[StringComparison]::OrdinalIgnoreCase) -or -not $completed.StartsWith('C:\Reloaded-II\RandomizerBackups\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe restoration paths' }
Copy-Item -LiteralPath $original -Destination $stage -Recurse
New-Item -ItemType Directory -Path (Split-Path $completed -Parent) | Out-Null
[IO.Directory]::Move($installed,$completed)
try { [IO.Directory]::Move($stage,$installed) } catch { [IO.Directory]::Move($completed,$installed); throw }
foreach ($file in Get-ChildItem -LiteralPath $original -File -Recurse) {
    $relative=[IO.Path]::GetRelativePath($original,$file.FullName)
    if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath (Join-Path $installed $relative) -Algorithm SHA256).Hash) { throw ('Restored mod differs: '+$relative) }
}
foreach ($file in $overlays) {
    $target=Join-Path $gameData $file.Name
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash) { throw ('Restored overlay differs: '+$file.Name) }
}
$restored=Get-Content -LiteralPath (Join-Path $installed 'ModConfig.json') -Raw | ConvertFrom-Json
[ordered]@{result='passed';restored_utc=[DateTime]::UtcNow.ToString('o');version=$restored.ModVersion;original_backup=$original;completed_validation_backup=$completed;installed_files_match_backup=$true;overlay_files_match_backup=$true;overlay_count=$overlays.Count} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $audit 'restoration.json') -Encoding utf8
Write-Output ('Restored prior installed '+$restored.ModVersion+' seed and '+$overlays.Count+' overlay packs; retained both backups.')
