"""Read-only PE table discovery. Layouts credited to Nenkai's FFTIVC loader.

File offsets are discovered from signatures, then translated to RVAs through
the PE section table. Neither the executable nor game archives are patched.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

ENHANCED_SHA256 = "937233f7fe76182a665c487c8802f5cec6662ddd09967e87cd09fb146fc6b5d5"
LOADER_COMMIT = "c74047dc1b36bfe1bf6a466cf3645f1fe9815425"
JOB_NAMES = dict(enumerate([
    "Squire", "Chemist", "Knight", "Archer", "Monk", "White Mage",
    "Black Mage", "Time Mage", "Summoner", "Thief", "Orator", "Mystic",
    "Geomancer", "Dragoon", "Samurai", "Ninja", "Arithmetician", "Bard",
    "Dancer", "Mime",
], 74))


@dataclass(frozen=True)
class TableSpec:
    signature: str
    stride: int
    count: int
    back: int = 0


SPECS = {
    "JobData": TableSpec("19 00 00 00 00 00 00 00 00 D0 40 06 FF 00 0B 78 0B 69 5F 64 32 6E 30 64 04 03 0A 00 00 00 00 00 00 40", 49, 174, 49),
    "JobCommandData": TableSpec("00 00 FC 92 93 94 95 00 00 00 00 00 00 00 00 00 00 00 00", 25, 176, 125),
    "ItemData": TableSpec("00 00 00 80 00 00 00 00 00 00 00 00 00 01 01 80 01 01 00 00 64 00 01 00 00 02 03 80 02 01 00 00", 12, 256),
    # Enhanced's five extra items occupy a separate native table. Keep their
    # metadata private: ENTD equipment/trophies still store one-byte IDs.
    "ItemDataExtended": TableSpec("0D 15 61 82 20 03 00 54 0A 00 01 00 0D 0C 08 82", 12, 5),
    "ItemWeaponData": TableSpec("01 88 01 FF 00 00 00 00 01 8A 01 FF 03 05 00 00 01 8A 01 FF 04 05 00 00 01 8A 01 FF 04 05 00 09", 8, 128),
    "ItemArmorData": TableSpec("0A 00 14 00 1E 00 28 00 32 00 3C 00 46 00 50 00 5A 00 64 00 78 00 82 00 96 00 08 00 10 05 18 08", 2, 64),
    "ItemShieldData": TableSpec("0A 03 0D 03 10 00 13 00 16 05 19 00 1C 00 1F 00 0A 32 22 0F 25 0A 28 0F 2B 00 2E 14 32 19 4B 32", 2, 16),
    "ItemAccessoryData": TableSpec("00 00 00 00 00 00 00 00 00 00 0A 0A 0F 0F 12 12 19 19 1C 1C 28 1E 23 00 00 00 00 00 00 00 00 00", 2, 32, 32),
    "ItemConsumableData": TableSpec("48 03 00 48 07 00 48 0F 00 49 02 00 49 05 00 4A 00 00 38 00 01 38 00 02", 3, 14),
    "ItemEquipBonusData": TableSpec("00 02 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 20", 26, 85, 26),
    "JobCommandDataWOTL": TableSpec("08 00 F0 2D B8 DB DC 65 00 00 00 00", 25, 3),
    "MonsterJobCommandData": TableSpec("D0 09 0D 00 0C F0 09 0A 0C 0B F0 09 0A 0B 0D D0 0E 11 00 0F", 5, 48),
    "CommandTypeData": TableSpec("0F 08 0B 0C 0D 00 01 00 0A 00 00 00 00 00 00 00 00 04 09 07 02 03 00 00 00 00 00 00 00 00 00", 1, 256),
    "AbilityMetadata": TableSpec("00 00 00 00 82 02 01 81 32 00 5A 41 81 75 00 80", 8, 512),
    "ItemOptionsData": TableSpec("10 00 00 00 80 00 10 00 20 00 00 00 10 00 08 00 00 00 10 00 00 02 00 00 10 00 80 00 00 00", 6, 128, 6),
    # Native secondary action data expands the original 14-byte RCC record
    # to 20 bytes. This unique anchor is Cure (row 1), followed by Cura.
    "AbilityAttributes": TableSpec("04 01 01 00 00 E2 00 00 0C 00 0E 00 04 06 00 00 FF FF FF FF 04 01 01 00 00 E2 00 00 0C", 20, 368, 20),
}
JOB_FIELDS = [
    "HPGrowth", "HPMultiplier", "MPGrowth", "MPMultiplier", "SpeedGrowth",
    "SpeedMultiplier", "PAGrowth", "PAMultiplier", "MAGrowth", "MAMultiplier",
    "Move", "Jump", "CharacterEvasion",
]
ACTION_FIELDS = [f"AbilityId{i}" for i in range(1, 17)]
RSM_FIELDS = [f"ReactionSupportMovementId{i}" for i in range(1, 7)]


def sections(data):
    if data[:2] != b"MZ":
        raise ValueError("Not a Windows executable")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Invalid PE signature")
    machine, count = struct.unpack_from("<HH", data, pe + 4)
    if machine != 0x8664:
        raise ValueError("Expected a 64-bit executable")
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    result = []
    for i in range(count):
        pos = pe + 24 + optsize + i * 40
        name = data[pos:pos + 8].rstrip(b"\0").decode("ascii")
        vsize, rva, rawsize, raw = struct.unpack_from("<IIII", data, pos + 8)
        result.append(dict(name=name, rva=rva, raw=raw, rawsize=rawsize, vsize=vsize))
    return result


def unique_match(data, pattern):
    first = data.find(pattern)
    if first < 0 or data.find(pattern, first + 1) >= 0:
        raise ValueError("Table signature is absent or ambiguous; this build needs investigation")
    return first


def decode_commands(block, count):
    rows = {}
    for i in range(count):
        row = block[i * 25:(i + 1) * 25]
        values = {}
        for slot, name in enumerate(ACTION_FIELDS):
            extended = bool(row[slot // 8] & (1 << (7 - slot % 8)))
            values[name] = row[3 + slot] + (256 if extended else 0)
        for slot, name in enumerate(RSM_FIELDS):
            values[name] = row[19 + slot] + (256 if row[2] & (1 << (7 - slot)) else 0)
        rows[i] = values
    return rows


def read_game(game_dir, *, require_supported=True):
    path = Path(game_dir).resolve() / "FFT_enhanced.exe"
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if require_supported and digest != ENHANCED_SHA256:
        raise ValueError("Enhanced executable differs from the verified build. Run inspect and revalidate layouts before adding support.")
    pe_sections = sections(data)
    tables, locations = {}, {}
    for name, spec in SPECS.items():
        pos = unique_match(data, bytes.fromhex(spec.signature)) - spec.back
        end = pos + spec.stride * spec.count
        section = next((s for s in pe_sections if s["raw"] <= pos and end <= s["raw"] + s["rawsize"]), None)
        if pos < 0 or end > len(data) or section is None:
            raise ValueError(f"{name} is outside a file-backed PE section")
        block = data[pos:end]
        locations[name] = dict(file_offset=f"0x{pos:X}", rva=f"0x{section['rva'] + pos - section['raw']:X}",
                               section=section["name"], stride=spec.stride, count=spec.count,
                               sha256=hashlib.sha256(block).hexdigest())
        if name == "JobCommandData":
            tables[name] = decode_commands(block, spec.count)
            continue
        if name == "JobCommandDataWOTL":
            tables['JobCommandData'].update({i + 224: row for i, row in decode_commands(block, 3).items()})
            continue
        rows = {}
        for i in range(spec.count):
            row = block[i * spec.stride:(i + 1) * spec.stride]
            if name == 'AbilityMetadata':
                jp, chance, flags, ai = struct.unpack('<HBBI', row)
                rows[i] = dict(JPCost=jp, LearnChance=chance, AbilityType=flags & 15,
                               Flags=flags >> 4, AIBehaviorFlags=ai)
            elif name == 'AbilityAttributes':
                fields = ('Range','EffectArea','Vertical','Flags1','Flags2','Flags3','Flags4',
                          'Element','Formula','X','Y','InflictStatus','CT','MPCost')
                rows[i] = dict(zip(fields,row[:14]))
            elif name == 'CommandTypeData':
                rows[i] = dict(Menu=row[0])
            elif name == 'MonsterJobCommandData':
                rows[i + 176] = {f'AbilityId{slot + 1}': row[slot + 1] + (256 if row[0] & (1 << (7-slot)) else 0)
                                 for slot in range(4)}
            elif name == "JobData":
                rows[i] = dict(zip(JOB_FIELDS, row[14:27])) | {
                    "JobCommandId": row[0], "EquippableItems": int.from_bytes(row[9:14], 'big'),
                    **{f'InnateAbilityId{slot+1}':struct.unpack_from('<H',row,1+slot*2)[0] for slot in range(4)},
                    'InnateStatus':int.from_bytes(row[27:32],'big'),
                    'ImmuneStatus':int.from_bytes(row[32:37],'big'),
                    'StartingStatus':int.from_bytes(row[37:42],'big'),
                    **dict(zip(('AbsorbElements','NullifyElements','HalveElements','WeakElements'),row[42:46]))}
                # JOB_DATA is 49 bytes in the supported Enhanced build. These
                # final native fields identify creature jobs, including those
                # whose commands use the 16-action human table. Keep them
                # private so actor classification never emits trait patches.
                tables.setdefault('_JobTraits', {})[i] = dict(
                    MonsterPortrait=row[46], MonsterPalette=row[47], MonsterGraphic=row[48],
                    InnateStatus=int.from_bytes(row[27:32], 'big'),
                    StartStatus=int.from_bytes(row[37:42], 'big'),
                    StartingStatus=int.from_bytes(row[37:42], 'big'))
            elif name == "ItemOptionsData":
                rows[i] = dict(OptionType=row[0],Effects=int.from_bytes(row[1:6],'big'))
            elif name in ("ItemData", "ItemDataExtended"):
                item_id = i + 256 if name == "ItemDataExtended" else i
                rows[item_id] = dict(TypeFlags=row[3], AdditionalDataId=row[4], ItemCategory=row[5],
                               RequiredLevel=row[2], EquipBonusId=row[7],
                               Price=int.from_bytes(row[8:10], "little"), ShopAvailability=row[10])
            elif name == "ItemWeaponData":
                rows[i] = dict(Range=row[0], Formula=row[2], Power=row[4], Evasion=row[5],
                               OptionsAbilityId=row[7])
            elif name == "ItemConsumableData":
                rows[i] = dict(Formula=row[0], Z=row[1], StatusEffectId=row[2])
            elif name == "ItemEquipBonusData":
                rows[i] = dict(zip(('PABonus','MABonus','SpeedBonus','MoveBonus','JumpBonus'),row[:5]))
            else:
                fields, start = {
                    "ItemWeaponData": (["Power", "Evasion"], 4),
                    "ItemArmorData": (["HPBonus", "MPBonus"], 0),
                    "ItemShieldData": (["PhysicalEvasion", "MagicalEvasion"], 0),
                    "ItemAccessoryData": (["PhysicalEvasion", "MagicalEvasion"], 0),
                }[name]
                rows[i] = dict(zip(fields, row[start:start + 2]))
        private_name = {'AbilityMetadata':'_AbilityMetadata','AbilityAttributes':'_AbilityAttributes',
                        'ItemDataExtended':'_ExtendedItemData'}.get(name,name)
        tables[private_name] = rows
    for job in JOB_NAMES:
        if tables["JobData"][job]["JobCommandId"] != job - 69:
            raise ValueError("Ordinary job/skillset relationship failed validation")
        if any(tables["JobData"][job][field] == 0 for field in JOB_FIELDS[:12]):
            raise ValueError("Ordinary job has an invalid zero stat")
    report = dict(mode="enhanced", executable=path.name, executable_sha256=digest,
                  supported=digest == ENHANCED_SHA256, loader_source_commit=LOADER_COMMIT,
                  tables=locations)
    return tables, report
