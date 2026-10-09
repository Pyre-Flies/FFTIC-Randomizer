"""Additional RCC defaults, guarded against the verified Enhanced executable.

Plans change in-memory native data/code through the existing preview loader.
The original executable remains untouched. Addresses belong only to the
937233f7 Enhanced build; guards deliberately reject any other build.
"""
import hashlib
from pathlib import Path
import struct

from .game import ENHANCED_SHA256
from .rcc_qol import _Code, _patch, raw_from_rva, relative_jump


PROPOSITION_TABLE = 0x7B768C
PROPOSITION_JP_TABLE = 0x7B80C0
PROPOSITION_HEADER = 0x7B7650
PROPOSITION_JP = (10, 20, 30, 40, 50, 80, 100, 120)
SMART_CHANCE = 0x248CBF
SMART_ROUTE_POSITION = 0xD8DC08
SMART_ROUTE_LENGTH = 0xD8DC0C
SMART_ORIGINAL_CHANCE = bytes.fromhex(
    '44 8B 1D 0E D3 69 00 45 8B C3 8B 0D F9 D2 69 00 '
    '8B 35 F7 D2 69 00 8B 2D F5 D2 69 00 44 8B 0D 36 6E C3 02 '
    '41 C1 E8 0B C1 E1 0B 33 0D D9 D2 69 00 44 33 C1 '
    '89 35 D0 D2 69 00 41 C1 E8 08 45 33 C3 89 2D C7 D2 69 00 '
    '44 33 C1 44 89 1D C1 D2 69 00 41 8B C0 44 89 05 BB D2 69 00 '
    '25 FF 7F 00 00 6B C8 64 C1 F9 0F 41 83 E9 01 74 0B '
    '41 83 F9 01 75 08 8D 4A 01 EB 03 8D 4A FF 3B D1 7D 35')


def proposition_cleanup_patches(data):
    """RCC PropositionObject/PropositionJPObject.clean, source2889–2898.

    Native helper2CCDC4 expands these96 records (23bytes each) into a ushort
    buffer. Reward routine2D29C0 obtains its8 JP amounts through aggregate
    header+0x20. Thus these are active native tables, not archive lookalikes.
    """
    header = raw_from_rva(data, PROPOSITION_HEADER, 0x3C)
    if struct.unpack_from('<I', data, header)[0] != 0x3C:
        raise ValueError('Native proposition aggregate header guard failed')
    if struct.unpack_from('<I', data, header+0x20)[0] != 0xA70:
        raise ValueError('Native proposition JP offset guard failed')
    start = raw_from_rva(data, PROPOSITION_TABLE, 96*23)
    original = data[start:start+96*23]
    updated = bytearray(original)
    changed = []
    for index in range(96):
        offset = index*23+21
        if 1 <= original[offset] <= 5:
            updated[offset] = 1
            if original[offset] != 1:
                changed.append(index)
    if changed != [0, 5, 10, 21, 23, 30, 50, 67, 69]:
        raise ValueError('Native proposition unlock bytes differ from verified baseline')
    jp = struct.pack('<8H', *PROPOSITION_JP)
    return [
        _patch(data, 'RCC proposition unlock cleanup', PROPOSITION_TABLE,
               original, bytes(updated)),
        _patch(data, 'RCC double proposition JP rewards', PROPOSITION_JP_TABLE,
               jp, struct.pack('<8H', *(value*2 for value in PROPOSITION_JP))),
    ]


def special_proposition_patches(data):
    """Razele.xml CD9C/E834: generic threshold74 becomes4.

    Enhanced predicate2EE37C feeds availability count2EDE98 and modern
    participant count1A32DE. Retain every existing availability/name/monster
    check and Enhanced162/163 exclusions. Source still excludes Ramza1..3.
    """
    start = raw_from_rva(data, 0x2EE399, 0x2D)
    guard = bytes.fromhex(
        '80 B8 1E 01 00 00 00 75 21 80 78 01 FF 74 1B F6 40 04 20 75 15 '
        '0F B6 10 83 FA 4A 72 0D 81 EA A2 00 00 00 74 05 83 FA 01 75 02 33 C0 C3')
    if data[start:start+len(guard)] != guard:
        raise ValueError('Native proposition participant predicate guard failed')
    return [_patch(data, 'RCC special characters can undertake propositions',
                   0x2EE3B1, bytes.fromhex('83 FA 4A'), bytes.fromhex('83 FA 04'))]


def rename_patches(data):
    """Active Enhanced party Rename adaptation of Razele.xml631.

    The current UI already allows generic humans, replacing source's gender
    rejection with a generic-job-only condition. Native office mode26 uses
    party presentation3; its commit at2EF142..2EF1C2 writes the chosen
    actor's UTF8 name at+126. Remove only the job conditions in presentation
    and navigation, preserving all earlier availability/status checks.
    Recruit naming state4BB is a different flow and proves no Rename parity.
    """
    navigation = bytes.fromhex(
        '49 8B 04 D8 0F B6 48 72 83 F9 4A 72 0D 81 E9 A2 00 00 00 '
        '74 05 83 F9 01 75 03 45 8A F9')
    presentation = bytes.fromhex(
        '0F B6 4D 82 83 F9 4A 72 11 81 E9 A2 00 00 00 74 09 '
        '83 F9 01 0F 85 FF 00 00 00')
    for address, expected in ((0x2C0F37, navigation), (0x2C2217, presentation)):
        offset = raw_from_rva(data, address, len(expected))
        if data[offset:offset+len(expected)] != expected:
            raise ValueError(f'Native office Rename party-list guard failed at {address:X}')
    return [
        _patch(data, 'RCC Soldier Office Rename any party character navigation',
               0x2C0F37, navigation,
               relative_jump(0x2C0F37,0x2C0F54)+b'\x90'*(len(navigation)-5)),
        _patch(data, 'RCC Soldier Office Rename any party character presentation',
               0x2C2217, presentation,
               relative_jump(0x2C2217,0x2C2330)+b'\x90'*(len(presentation)-5)),
    ]


def legacy_rename_patches(data):
    """Razele.xml631: disable only source roster mode2's gender rejection.

    MIPS WORLD_WORLD_BIN41205 changes srl6 to srl22 on an unsigned byte;
    its result therefore becomes zero for every actor. Native284F6C mode2
    expresses the same predicate as flags<0x40. Keep the earlier flag4
    exclusion and every remaining membership/action filter unchanged.
    This is a reference translation of the original roster branch. Active
    Existing-party Rename uses modern office mode26 instead. State4BB names
    newly generated recruit offers, and does not establish party Rename
    eligibility. Consequently this reference patch is not installed.
    """
    start = raw_from_rva(data, 0x2850AB, 0x1F)
    guard = bytes.fromhex(
        '41 83 FE 02 75 19 8A 44 33 70 A8 04 0F 85 68 01 00 00 '
        '3C 40 0F 82 1F 01 00 00 E9 5B 01 00 00')
    if data[start:start+len(guard)] != guard:
        raise ValueError('Native office rename roster mode2 guard failed')
    return [_patch(data, 'RCC Soldier Office renames humans and special characters',
                   0x2850BD, bytes.fromhex('3C 40 0F 82 1F 01 00 00'),
                   relative_jump(0x2850BD, 0x2851E4)+b'\x90'*3)]


def smart_encounter_code():
    """Replace travel's chance roll with the source's route-end comparison.

    Xifanie.xml1521-1535 compares PS1 route position800D0B7C with route
    length800D0B80. Native2482F8 increments D8DC08 at24845C, compares it
    with D8DC0C at24865D, and calls the same selector248BE4 at2485B7.
    Jump through248D57 to load the unchanged RNG state for the variant draw;
    source Smart Encounters also removes the discarded chance RNG draw.
    """
    code = _Code(SMART_CHANCE)
    code.rip('8B 05', SMART_ROUTE_LENGTH)
    code.rip('3B 05', SMART_ROUTE_POSITION)
    code.code.extend(b'\x0F\x85'+struct.pack('<i', 0x248D3C-(SMART_CHANCE+18)))
    code.code.extend(relative_jump(SMART_CHANCE+18, 0x248D57))
    code.code.extend(b'\x90'*(len(SMART_ORIGINAL_CHANCE)-len(code.code)))
    return bytes(code.code)


def smart_encounter_patches(data):
    """Keep eligibility, zero-chance and explicit Enhanced battle guards.

    Native248BE4 has two verified callers. Ordinary travel2485B7 passes
    r8b=0. Explicit battle selection2D134A passes r8b=1 and already jumps
    around the chance phase at248CB6..248CBF. Preserve that native path.
    Only travel changes: destinations always select an eligible encounter,
    passing nodes never do. Chapter/entrance/area guards and the variant
    bitmask remain native; this does not turn every map into a battle map.
    """
    prefix = bytes.fromhex('85 D2 0F 84 86 00 00 00 40 84 F6 0F 85 98 00 00 00')
    start = raw_from_rva(data, 0x248CAE, len(prefix))
    if data[start:start+len(prefix)] != prefix:
        raise ValueError('Native random-battle eligibility/forced-selection guard failed')
    return [_patch(data, 'RCC Smart Encounters destination-only travel battles',
                   SMART_CHANCE, SMART_ORIGINAL_CHANCE, smart_encounter_code())]


def apply_qol_extra(before, result, game_dir, flags):
    """Append native default plans; neither phase flags nor RNG gate cleanup."""
    data = (Path(game_dir)/'FFT_enhanced.exe').read_bytes()
    if hashlib.sha256(data).hexdigest() != ENHANCED_SHA256:
        raise ValueError('RCC QoL defaults require the verified Enhanced executable')
    patches = (proposition_cleanup_patches(data)+special_proposition_patches(data)
               +rename_patches(data)+smart_encounter_patches(data))
    result.setdefault('_RCCNativeTablePatches', []).extend(patches)
    audit = dict(
        implemented=['Proposition unlock cleanup', 'Double proposition JP rewards',
                     'Special human characters can undertake propositions (source excludes Ramza)',
                     'Soldier Office renames humans and special characters',
                     'Smart Encounters: destination100%, passing nodes0%; eligible maps only'],
        completed_defaults=['Rename humans and special characters',
                            'Special characters can undertake propositions',
                            'Smart Encounters destination-only random battles'],
        native_patch_count=len(patches),
        rename=dict(implementation='active Enhanced party navigation and presentation patches',
                    native_office_mode=26, presentation_type=3, navigation_type=6,
                    party_selection_state=hex(0x5EC),
                    all_job_identity_restrictions_removed=True,
                    availability_status_checks_preserved=True, legacy_patch_installed=False),
        source=('randomizer.py2889-2898 unconditional clean phase; '
                'Razele.xml245-261,631; Xifanie.xml1521-1535'),
        smart_encounters=dict(native_selector=hex(0x248BE4),
                              route_position=hex(SMART_ROUTE_POSITION),
                              route_length=hex(SMART_ROUTE_LENGTH),
                              chance_rng_draw_removed=True,
                              explicit_enhanced_selection_preserved=True),
        guard='exact Enhanced executable hash and active native table bytes',
    )
    result['_RCCQolExtraAudit'] = audit
    return audit
