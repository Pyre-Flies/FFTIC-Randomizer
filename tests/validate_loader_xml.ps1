param(
    [Parameter(Mandatory = $true)][string]$InputFolder,
    [string]$LoaderFolder = 'C:\Reloaded-II\Mods\fftivc.utility.modloader'
)

# Read-only integration check against the installed loader's actual models and
# YAX serializer. No game process, table manager, or native hook is invoked.
$ErrorActionPreference = 'Stop'
foreach ($dllName in @('YAXLib.dll', 'fftivc.utility.modloader.Interfaces.dll', 'fftivc.utility.modloader.Serializers.dll')) {
    [System.Reflection.Assembly]::LoadFrom((Join-Path $LoaderFolder $dllName)) | Out-Null
}
$serializerType = [Type]::GetType('fftivc.utility.modloader.Serializers.XmlModelFormatSerializer, fftivc.utility.modloader.Serializers', $true)
$serializer = [Activator]::CreateInstance($serializerType)
$deserialize = $serializerType.GetMethods() | Where-Object {
    $_.Name -eq 'Deserialize' -and $_.GetParameters()[0].ParameterType -eq [System.IO.Stream]
} | Select-Object -First 1
$types = @{
    JobData = 'JobTable'
    JobCommandData = 'JobCommandTable'
    ItemData = 'ItemTable'
    ItemWeaponData = 'ItemWeaponTable'
    ItemArmorData = 'ItemArmorTable'
    ItemShieldData = 'ItemShieldTable'
    ItemAccessoryData = 'ItemAccessoryTable'
    MonsterJobCommandData = 'MonsterJobCommandTable'
    CommandTypeData = 'CommandTypeTable'
    ItemConsumableData = 'ItemConsumableTable'
    ItemEquipBonusData = 'ItemEquipBonusTable'
    ItemOptionsData = 'ItemOptionsTable'
    JobNeedLevelData = 'JobNeedLevelTable'
    MapTrapFormationData = 'MapTrapFormationTable'
}
$files = @(Get-ChildItem -LiteralPath $InputFolder -Filter '*.xml' -File)
if ($files.Count -eq 0) { throw 'No XML table patches found' }
$results = foreach ($file in $files) {
    if (-not $types.ContainsKey($file.BaseName)) { throw "Unexpected table: $($file.Name)" }
    $tableType = [Type]::GetType(('fftivc.utility.modloader.Interfaces.Tables.Models.' + $types[$file.BaseName] + ', fftivc.utility.modloader.Interfaces'), $true)
    $method = $deserialize.MakeGenericMethod($tableType)
    $stream = [IO.File]::OpenRead($file.FullName)
    try {
        $table = $method.Invoke($serializer, @($stream))
    } catch {
        throw ($file.Name + ': ' + $_.Exception.GetBaseException().Message)
    } finally {
        $stream.Dispose()
    }
    [xml]$xml = Get-Content -LiteralPath $file.FullName -Raw
    $xmlRows = @($xml.DocumentElement.Entries.ChildNodes | Where-Object NodeType -EQ Element)
    if ($table.Version -ne 1 -or $table.Entries.Count -ne $xmlRows.Count) {
        throw "Version or row count mismatch: $($file.Name)"
    }
    foreach ($xmlRow in $xmlRows) {
        $models = @($table.Entries | Where-Object Id -EQ ([int]$xmlRow.Id))
        if ($models.Count -ne 1) { throw "Missing or duplicate row: $($xmlRow.Id)" }
        $model = $models[0]
        foreach ($element in $xmlRow.ChildNodes | Where-Object NodeType -EQ Element) {
            if ($element.Name -in @('ExtendAbilityIdFlagBits', 'ExtendReactionSupportMovementIdFlagBits')) { continue }
            $property = $model.GetType().GetProperty($element.Name)
            if ($null -eq $property -or [long]$property.GetValue($model) -ne [long]$element.InnerText) {
                throw "Deserialized value mismatch: $($file.Name) ID $($model.Id) $($element.Name)"
            }
        }
        foreach ($property in $model.GetType().GetProperties()) {
            if ($null -ne [Nullable]::GetUnderlyingType($property.PropertyType) -and
                $null -eq $xmlRow.SelectSingleNode($property.Name) -and
                $null -ne $property.GetValue($model)) {
                throw "Omitted property acquired a value: $($file.Name) ID $($model.Id) $($property.Name)"
            }
        }
        if ($file.BaseName -eq 'JobCommandData') {
            $actionBits = 0
            for ($slot = 0; $slot -lt 16; $slot++) {
                if ([int]$model.('AbilityId' + ($slot + 1)) -ge 256) {
                    $bit = [int][Math]::Floor($slot / 8) * 8 + 7 - ($slot % 8)
                    $actionBits = $actionBits -bor (1 -shl $bit)
                }
            }
            $rsmBits = 0
            for ($slot = 0; $slot -lt 6; $slot++) {
                if ([int]$model.('ReactionSupportMovementId' + ($slot + 1)) -ge 256) {
                    $rsmBits = $rsmBits -bor (1 -shl (7 - $slot))
                }
            }
            if ([int]$model.ExtendAbilityIdFlagBits -ne $actionBits -or
                [int]$model.ExtendReactionSupportMovementIdFlagBits -ne $rsmBits) {
                throw "Extended ID bits mismatch: $($file.Name) ID $($model.Id)"
            }
        }
    }
    [pscustomobject]@{ File = $file.Name; Rows = $table.Entries.Count; Result = 'passed' }
}
$results | ConvertTo-Json
