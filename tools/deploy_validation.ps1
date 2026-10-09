param([Parameter(Mandatory=$true)][string]$SeedFolder,
      [string]$AuditFolder='research\live-validation-0.6.0',
      [string]$ExpectedSettingsFile,
      [string]$TestLogFile='research\live-validation-0.6.0-test-run.txt')
$ErrorActionPreference='Stop'
$project=Split-Path $PSScriptRoot -Parent
$game=Split-Path $project -Parent
$seed=[IO.Path]::GetFullPath((Resolve-Path -LiteralPath $SeedFolder).Path)
$outputs=[IO.Path]::GetFullPath((Join-Path $project 'outputs'))
if (-not $seed.StartsWith($outputs+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Seed must be inside project outputs' }
$manifestPath=Join-Path $seed 'manifest.json'
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$sourceVersion=[regex]::Match((Get-Content -LiteralPath (Join-Path $project 'fftic\__init__.py') -Raw),'VERSION = "([^"]+)"').Groups[1].Value
if (-not $sourceVersion -or $manifest.generator_version -ne $sourceVersion) { throw 'Seed version differs from current sources' }
$expected=if ($ExpectedSettingsFile) { Get-Content -LiteralPath $ExpectedSettingsFile -Raw | ConvertFrom-Json } else {
    [pscustomobject]@{seed='89f597b5';flags='risayjmuzftpwc';ability_mode='full';spread=0.25;skill_degree=1;chaos=1;secret_codes=[pscustomobject]@{fiesta=$false;easymodo=$false};full_settings=[pscustomobject]@{min_actions=6;max_actions=12;passives_per_type=1}}
}
foreach ($field in @('seed','flags','ability_mode','spread','skill_degree','chaos')) {
    if ($null -eq $expected.$field -or $manifest.$field -ne $expected.$field) { throw ('Validation settings differ: '+$field) }
}
foreach ($field in @('fiesta','easymodo')) {
    if ($null -eq $expected.secret_codes.$field -or $manifest.secret_codes.$field -ne $expected.secret_codes.$field) { throw ('Validation secret differs: '+$field) }
}
if ($expected.ability_mode -eq 'full') {
    foreach ($field in @('min_actions','max_actions','passives_per_type')) {
        if ($null -eq $expected.full_settings.$field -or $manifest.full_settings.$field -ne $expected.full_settings.$field) { throw ('Validation count differs: '+$field) }
    }
} elseif ($null -ne $manifest.full_settings -or $null -ne $expected.full_settings) {
    throw 'RCC mode must not contain Full-only counts'
}
if (@(Get-Process FFT_enhanced,FFT_classic -ErrorAction SilentlyContinue).Count) { throw 'Game is already running' }
$source=Join-Path $seed 'fftivc.randomizer.seed'
$installed='C:\Reloaded-II\Mods\fftivc.randomizer.seed'
if ([IO.Path]::GetFullPath($installed) -ne 'C:\Reloaded-II\Mods\fftivc.randomizer.seed' -or (Get-Item -LiteralPath $installed).LinkType) { throw 'Installed mod path is unexpected or linked' }
foreach ($property in $manifest.payload_sha256.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path $source $property.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw ('Generated payload changed: '+$property.Name) }
}
$audit=[IO.Path]::GetFullPath((Join-Path $project $AuditFolder))
if (-not $audit.StartsWith((Join-Path $project 'research')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Audit must stay inside project research' }
New-Item -ItemType Directory -Path $audit -Force | Out-Null
$suite=Join-Path $project $TestLogFile
if (-not (Test-Path -LiteralPath $suite -PathType Leaf)) { throw 'Run and record the final automated suite first' }
if ((Get-Content -LiteralPath $suite -Raw) -notmatch '(?m)^OK\s*$') { throw 'Final automated suite did not pass' }
Copy-Item -LiteralPath $suite -Destination (Join-Path $audit 'test-run.txt') -Force
$closure=Join-Path $project 'research\live-validation-0.6.0-closure-tests.txt'
if (-not (Test-Path -LiteralPath $closure -PathType Leaf) -or (Get-Content -LiteralPath $closure -Raw) -notmatch '(?m)^OK\s*$') { throw 'Run and record the corrected native closure checks first' }
Copy-Item -LiteralPath $closure -Destination (Join-Path $audit 'closure-tests.txt') -Force
& (Join-Path $project 'tests\validate_loader_xml.ps1') -InputFolder (Join-Path $source 'FFTIVC\tables\enhanced') |
    Set-Content -LiteralPath (Join-Path $audit 'serializer-result.json') -Encoding utf8
$originals=[ordered]@{}
$originals['FFT_enhanced.exe']=(Get-FileHash -LiteralPath (Join-Path $game 'FFT_enhanced.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($originals['FFT_enhanced.exe'] -ne $manifest.build.executable_sha256) { throw 'Original executable differs from generated input' }
foreach ($file in Get-ChildItem -LiteralPath (Join-Path $game 'data\enhanced') -File | Where-Object Name -Match '^\d{4}(?:\.[^.]+)?\.pac$') {
    $originals['data/enhanced/'+$file.Name]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$originals | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $audit 'originals.json') -Encoding utf8
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$backup=Join-Path $project ('research\backups\installed-seed-before-'+$manifest.generator_version+'-'+$stamp)
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item -LiteralPath $installed -Destination (Join-Path $backup 'fftivc.randomizer.seed') -Recurse
$overlayBackup=Join-Path $backup 'overlays'
New-Item -ItemType Directory -Path $overlayBackup | Out-Null
$overlays=@(Get-ChildItem -LiteralPath (Join-Path $game 'data\enhanced') -Filter 'modded*.pac' -File)
foreach ($file in $overlays) { Copy-Item -LiteralPath $file.FullName -Destination $overlayBackup }
$oldConfig=Get-Content -LiteralPath (Join-Path $installed 'ModConfig.json') -Raw | ConvertFrom-Json
$oldVersion=$oldConfig.ModVersion
$newConfig=Get-Content -LiteralPath (Join-Path $source 'ModConfig.json') -Raw | ConvertFrom-Json
foreach ($property in $newConfig.PSObject.Properties) { $oldConfig | Add-Member -MemberType NoteProperty -Name $property.Name -Value $property.Value -Force }
$stagingRoot='C:\Reloaded-II\RandomizerStaging'
$backupRoot='C:\Reloaded-II\RandomizerBackups'
$stage=Join-Path $stagingRoot $stamp
$archived=Join-Path $backupRoot ($stamp+'\fftivc.randomizer.seed')
if (-not [IO.Path]::GetFullPath($stage).StartsWith($stagingRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or -not [IO.Path]::GetFullPath($archived).StartsWith($backupRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe staging or archive path' }
New-Item -ItemType Directory -Path $stagingRoot,(Split-Path $archived -Parent) -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $stage -Recurse
[IO.File]::WriteAllText((Join-Path $stage 'ModConfig.json'),($oldConfig | ConvertTo-Json -Depth 30),[Text.UTF8Encoding]::new($false))
[IO.Directory]::Move($installed,$archived)
try { [IO.Directory]::Move($stage,$installed) } catch { [IO.Directory]::Move($archived,$installed); throw }
$manifestHash=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{backup=$backup;same_volume_backup=$archived;previous_version=$oldVersion;version=$manifest.generator_version;seed_folder=$seed;manifest_sha256=$manifestHash;seed=$manifest.seed;flags=$manifest.flags;ability_mode=$manifest.ability_mode;full_settings=$manifest.full_settings;secret_codes=$manifest.secret_codes;overlay_backups=@($overlays.Name)} |
    ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $audit 'deployment.json') -Encoding utf8
$launchUtc=[DateTime]::UtcNow
$exe=Join-Path $game 'FFT_enhanced.exe'
$launcher=Start-Process -FilePath 'C:\Reloaded-II\Reloaded-II.exe' -ArgumentList @('--launch',('"'+$exe+'"')) -WorkingDirectory 'C:\Reloaded-II' -WindowStyle Hidden -PassThru
$ownGame=$null
for ($attempt=0;$attempt -lt 15 -and $null -eq $ownGame;$attempt++) {
    Start-Sleep -Milliseconds 1000
    $ownGame=Get-Process FFT_enhanced -ErrorAction SilentlyContinue | Where-Object { $_.StartTime.ToUniversalTime() -ge $launchUtc -and $_.Path -eq $exe } | Select-Object -First 1
}
if ($null -eq $ownGame) { throw 'Reloaded did not create the expected game process' }
[ordered]@{launch_utc=$launchUtc.ToString('o');launcher_pid=$launcher.Id;game_pid=$ownGame.Id;game_start_utc=$ownGame.StartTime.ToUniversalTime().ToString('o');main_module_base=('0x{0:X}' -f $ownGame.MainModule.BaseAddress.ToInt64());executable=$exe;seed_folder=$seed;manifest_sha256=$manifestHash;version=$manifest.generator_version;ability_mode=$manifest.ability_mode} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $audit 'launch.json') -Encoding utf8
Write-Output ('Backed up previous seed, installed '+$manifest.generator_version+' and launched validation PID '+$ownGame.Id)
