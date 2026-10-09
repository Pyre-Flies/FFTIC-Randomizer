"""Exact-build RCC default patches with verified Enhanced native equivalents.

This module returns guarded in-memory changes. It never edits the executable.
Features still being investigated are reported explicitly, not approximated.
"""
import hashlib
from pathlib import Path
import struct

from .game import ENHANCED_SHA256, sections, unique_match


FREE_OFFICE_FLAGS = frozenset('rujimtpsazfyw')
FLAG_GETTERS = (
    # Each original first instruction only stores RBX in caller home space.
    # The trampoline executes it before resuming all other flags at entry+5.
    ('World', 0x2E9898, 0x5A731B, 0x5A7368),
    ('Battle', 0x2332D8, 0x5B02BB, 0x5B0252),
)
SPAWN_SIGNATURE = bytes.fromhex('1E 0E 06 05 04 9D BA FF 13 FF FF FF 1C 0F 06 04 05 9D BA FF 13 FF FF FF')
PROLOGUE = bytes.fromhex('48 89 5C 24 08')
PENDING_DEFAULTS = (
    'Rename humans and special characters',
    'Special characters can undertake propositions',
    'Smart Encounters destination-only random battles',
)


class _Code:
    """Small relocatable encoder for reviewed, fixed-build instruction plans."""
    def __init__(self, start):
        self.start, self.code, self.labels, self.fixups = start, bytearray(), {}, []

    def emit(self, hex_bytes):
        self.code.extend(bytes.fromhex(hex_bytes))

    def call(self, target):
        at = self.start+len(self.code)
        self.code.extend(b'\xE8'+struct.pack('<i', target-at-5))

    def rip(self, hex_prefix, target):
        prefix = bytes.fromhex(hex_prefix)
        at = self.start+len(self.code)
        self.code.extend(prefix+struct.pack('<i', target-at-len(prefix)-4))

    def branch(self, hex_opcode, label):
        self.emit(hex_opcode)
        self.fixups.append((len(self.code), label))
        self.code.extend(b'\0'*4)

    def label(self, name):
        self.labels[name] = len(self.code)

    def finish(self):
        for position, label in self.fixups:
            struct.pack_into('<i', self.code, position, self.labels[label]-position-4)
        return bytes(self.code)


def mighty_sword_code(start=0x308538):
    """RCC Razele Formula46 port, retaining the native Win64 stack frame.

    Source's missing-slot branch exits without damage. Safeguard bypasses
    breaking and continues to damage; the guaranteed100% roll still advances
    native battle RNG. Native synthetic equipment257..260 stays unbreakable.
    """
    code = _Code(start)
    code.emit('48 83 EC 28')
    code.rip('48 8B 05', 0x186AF68)  # defender BWORK
    code.emit('F6 80 9A 00 00 00 04')  # native Safeguard bit
    code.branch('0F 85', 'damage')
    code.emit('B9 64 00 00 00 BA 64 00 00 00')
    code.call(0x278E68)  # native range/chance RNG, returns0 on success
    code.emit('85 C0')
    code.branch('0F 85', 'damage')
    code.call(0x3065C4)  # original gear-slot selection and missing-slot guard
    code.emit('85 C0')
    code.branch('0F 85', 'end')
    code.rip('48 8B 05', 0x186AF70)  # current target result
    code.emit('0F B7 48 04 81 E9 01 01 00 00 83 F9 03')
    code.branch('0F 86', 'synthetic')
    code.emit('66 C7 40 12 04 00')  # destroy-equipment result flag
    code.branch('E9', 'damage')
    code.label('synthetic')
    code.emit('C6 40 1B 00 66 C7 40 04 00 00')
    code.label('damage')
    code.rip('48 8B 05', 0x186AF70)
    code.emit('C6 00 01 C6 40 02 00')
    code.call(0x306C90)  # original physical accuracy and action prerequisites
    code.emit('85 C0')
    code.branch('0F 85', 'end')
    code.rip('48 8B 05', 0x186AF78)  # caster source BWORK
    code.emit('0F B6 48 3E')
    code.rip('0F B6 05', 0x7B07AC)  # weapon power
    code.rip('66 89 0D', 0x7B0770)  # PA factor
    code.rip('0F B6 0D', 0x7B079E)  # action Y
    code.emit('66 03 C8')
    code.rip('66 89 0D', 0x7B0772)  # WP+Y factor
    for target in (0x305BB8, 0x306E34, 0x305EB4, 0x305F08):
        code.call(target)
    code.rip('48 8B 05', 0x186AF70)
    code.emit('0F B7 48 06 D1 E9 66 89 48 06')  # source unsigned damage/2
    code.rip('8A 0D', 0x7B07AE)  # action element
    code.call(0x305554)  # native element absorption/weakness/halving
    code.rip('48 8B 05', 0x186AF70)
    code.emit('80 38 00')
    code.branch('0F 84', 'end')
    code.call(0x306224)  # transfer elemental absorb into HP healing result
    code.call(0x306944)  # native post-result cleanup preserving hit/type/CT
    code.label('end')
    code.emit('48 83 C4 28 C3')
    result = code.finish()
    if len(result) > 299:
        raise ValueError('Mighty Sword replacement exceeds native function')
    return result+b'\xCC'*(299-len(result))


def mighty_sword_patches(data):
    dispatch = raw_from_rva(data, 0x682BC8+46*8, 8)
    if struct.unpack_from('<Q', data, dispatch)[0] != 0x140308538:
        raise ValueError('Formula46 dispatch no longer targets the verified function')
    raw = raw_from_rva(data, 0x308538, 299)
    old = data[raw:raw+299]
    if hashlib.sha256(old).hexdigest() != '24cf31dc124e77d5a65789c4fa77fa325e3fdad4fee038b39dd568ce7fad7522':
        raise ValueError('Mighty Sword native function guard failed')
    return [_patch(data, 'RCC Mighty Sword Formula46 source rewrite', 0x308538,
                   old, mighty_sword_code())]


def double_jp_patches(data):
    # Native baseJP=(8+level//4+2*jobLevel), masked for a valid action.
    # Double it before party spillover/4, scenario multiplier and JPBoost.
    # The source MIPS patch also doubles before its team-mask instructions.
    entry, cave = 0x283595, 0x410AC1
    old = bytes.fromhex('40 80 E6 30 23 E9 33 FF')
    _outside_functions(data, cave, 15)
    stub = bytes.fromhex('40 80 E6 30 23 E9 D1 E5 33 FF')
    stub += relative_jump(cave+10, entry+8)
    return [
        _patch(data, 'RCC double battle earned JP', entry, old,
               relative_jump(entry, cave)+b'\x90'*3),
        _patch(data, 'RCC double battle JP trampoline', cave, b'\xCC'*15, stub),
    ]


def raw_from_rva(data, rva, length=1):
    for section in sections(data):
        if section['rva'] <= rva < rva+length <= section['rva']+section['rawsize']:
            return rva-section['rva']+section['raw']
    raise ValueError('QoL patch is outside a mapped executable section')


def _rva_from_raw(data, raw):
    for section in sections(data):
        if section['raw'] <= raw < section['raw']+section['rawsize']:
            return raw-section['raw']+section['rva']
    raise ValueError('QoL data is outside a mapped executable section')


def relative_jump(start, target):
    return b'\xE9'+struct.pack('<i', target-start-5)


def early_unlock_stub(entry, cave, return_one):
    """Flags144/145 return1; all other inputs execute the original getter."""
    # unsigned(flag-144)<=1 selects exactly144/145, including when inputs
    # are negative. LEA leaves ECX intact and EAX is caller-clobbered.
    branch = return_one-(cave+11)
    if not -128 <= branch <= 127:
        raise ValueError('Return-one helper is beyond a short conditional jump')
    code = bytes.fromhex('8D 81 70 FF FF FF 83 F8 01 76')+struct.pack('<b', branch)
    code += PROLOGUE+relative_jump(cave+16, entry+5)
    if len(code) != 21:
        raise ValueError('Unexpected early-unlock stub size')
    return code


def _outside_functions(data, rva, size):
    pdata = next(section for section in sections(data) if section['name'] == '.pdata')
    for raw in range(pdata['raw'], pdata['raw']+pdata['rawsize']-11, 12):
        start, end, _ = struct.unpack_from('<III', data, raw)
        if start < end and start < rva+size and rva < end:
            raise ValueError('QoL code padding intersects a native runtime function')


def _patch(data, name, rva, old, new):
    raw = raw_from_rva(data, rva, len(old))
    if data[raw:raw+len(old)] != old or len(old) != len(new):
        raise ValueError('QoL instruction/data guard failed: '+name)
    return dict(name=name, rva=rva, expected=old, data=new)


def early_unlock_patches(data):
    patches = []
    for scope, entry, cave, helper in FLAG_GETTERS:
        _outside_functions(data, cave, 21)
        _outside_functions(data, helper, 6)
        patches.append(_patch(data, 'RCC early shops/propositions '+scope+' getter', entry,
                              PROLOGUE, relative_jump(entry, cave)))
        patches.append(_patch(data, 'RCC early unlocks '+scope+' trampoline', cave,
                              b'\xCC'*21, early_unlock_stub(entry, cave, helper)))
        patches.append(_patch(data, 'RCC early unlocks '+scope+' return-one', helper,
                              b'\xCC'*6, bytes.fromhex('B8 01 00 00 00 C3')))
    return patches


def free_office_patches(data):
    patches = []
    # Modern recruitment frontend reads gil with get-variable44 and rejects
    # below1500; the native office routine has a second affordability guard.
    # Preserve both control flows and change only the fixed cost immediate.
    patches.append(_patch(data, 'RCC free office frontend affordability', 0x1AE6E1,
                          bytes.fromhex('3D DC 05 00 00'), bytes.fromhex('3D 00 00 00 00')))
    patches.append(_patch(data, 'RCC free office native affordability', 0x33343D,
                          bytes.fromhex('81 B8 8C 34 00 00 DC 05 00 00'),
                          bytes.fromhex('81 B8 8C 34 00 00 00 00 00 00')))
    for name, rva in (('RCC free office displayed fee', 0x337197),
                      ('RCC free office fixed debit', 0x3374CC)):
        patches.append(_patch(data, name, rva, bytes.fromhex('BA DC 05 00 00'),
                              bytes.fromhex('BA 00 00 00 00')))
    # Source free_soldier_office sets the seven equip bytes toFF in its male
    # and female12-byte profiles. Native loader SpawnData uses the same12-byte
    # stride and four profiles. Stats and Ramza/monster profiles survive.
    raw = unique_match(data, SPAWN_SIGNATURE)
    old = data[raw:raw+48]
    if len(old) != 48:
        raise ValueError('Incomplete native spawn profiles')
    new = bytearray(old)
    new[5:12] = b'\xFF'*7
    new[17:24] = b'\xFF'*7
    patches.append(_patch(data, 'RCC free office empty generic starter equipment',
                          _rva_from_raw(data, raw), old, bytes(new)))
    return patches


def apply_qol(before, result, game_dir, flags):
    """Append verified default plans and disclose outstanding parity work."""
    data = (Path(game_dir)/'FFT_enhanced.exe').read_bytes()
    if hashlib.sha256(data).hexdigest() != ENHANCED_SHA256:
        raise ValueError('RCC QoL patches require the verified Enhanced executable')
    patches = early_unlock_patches(data)+mighty_sword_patches(data)+double_jp_patches(data)
    implemented = ['Fur Shop unlocked from start', 'Propositions unlocked from start',
                   'Mighty Sword source damage/break rewrite at100% break chance',
                   'Double battle earned JP before spillover and JPBoost']
    if set(flags) & FREE_OFFICE_FLAGS:
        patches += free_office_patches(data)
        implemented.append('Free Soldier Office with empty generic starter equipment')
    result.setdefault('_RCCNativeTablePatches', []).extend(patches)
    audit = dict(implemented=implemented, pending=list(PENDING_DEFAULTS),
                 existing_native_equivalents=['Poach ability not needed for Enhanced Fur Shop entry'],
                 auto_mash=('owned by the separate RCC event adapter' if 'o' in flags else 'disabled'),
                 native_patch_count=len(patches),
                 guard='exact Enhanced executable hash, original instructions and unused padding outside .pdata functions',
                 source='patches.cfg active entries; randomizer.py4722-4757,5251-5265')
    result['_RCCQolAudit'] = audit
    return audit
