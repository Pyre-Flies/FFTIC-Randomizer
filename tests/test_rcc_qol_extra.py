"""Exact-build guards and execution of native defaults in bounded test memory.

These tests never attach to, start, or modify a game process. They execute the
reviewed executable's real Win64 predicates/encounter selector with synthetic
data and a stand-in chapter getter at the original image-relative call target.
"""
import ctypes
import hashlib
import os
from pathlib import Path
import struct
import unittest

from fftic.game import ENHANCED_SHA256
from fftic.rcc_qol import apply_qol, raw_from_rva, relative_jump
from fftic.rcc_qol_extra import (
    PROPOSITION_JP, PROPOSITION_JP_TABLE, PROPOSITION_TABLE,
    SMART_ROUTE_LENGTH, SMART_ROUTE_POSITION, apply_qol_extra,
    proposition_cleanup_patches, rename_patches, legacy_rename_patches, smart_encounter_patches,
    special_proposition_patches,
)


GAME = Path(__file__).resolve().parents[2]


@unittest.skipUnless((GAME/'FFT_enhanced.exe').is_file(), 'Requires verified local Enhanced inputs')
class ExtraGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (GAME/'FFT_enhanced.exe').read_bytes()

    def test_all_extra_defaults_are_guarded_and_do_not_overlap_other_plans(self):
        self.assertEqual(hashlib.sha256(self.data).hexdigest(), ENHANCED_SHA256)
        result = {}
        apply_qol({}, result, GAME, 'jsmapw')
        audit = apply_qol_extra({}, result, GAME, 'jsmapw')
        self.assertEqual(audit['native_patch_count'], 6)
        self.assertFalse(audit['rename']['legacy_patch_installed'])
        self.assertEqual(len(audit['completed_defaults']), 3)
        used = set()
        for patch in result['_RCCNativeTablePatches']:
            start = raw_from_rva(self.data, patch['rva'], len(patch['expected']))
            self.assertEqual(self.data[start:start+len(patch['expected'])], patch['expected'])
            self.assertEqual(len(patch['expected']), len(patch['data']))
            locations = set(range(patch['rva'], patch['rva']+len(patch['data'])))
            self.assertFalse(used & locations)
            used.update(locations)

    def test_proposition_cleanup_changes_only_verified_unlock_bytes_and_jp(self):
        cleanup, rewards = proposition_cleanup_patches(self.data)
        differences = [index for index, (a,b) in enumerate(zip(cleanup['expected'], cleanup['data'])) if a != b]
        self.assertEqual(differences, [index*23+21 for index in (0,5,10,21,23,30,50,67,69)])
        self.assertTrue(all(cleanup['data'][index] == 1 for index in differences))
        self.assertEqual(cleanup['rva'], PROPOSITION_TABLE)
        self.assertEqual(rewards['rva'], PROPOSITION_JP_TABLE)
        self.assertEqual(struct.unpack('<8H', rewards['data']), tuple(jp*2 for jp in PROPOSITION_JP))

    def test_individual_predicates_fail_closed_on_changed_bytes(self):
        for factory, address in ((legacy_rename_patches,0x2850BD),
                                 (special_proposition_patches,0x2EE3B1),
                                 (rename_patches,0x2C0F3F),
                                 (rename_patches,0x2C221B),
                                 (smart_encounter_patches,0x248CBF)):
            changed = bytearray(self.data)
            changed[raw_from_rva(changed,address)] ^= 1
            with self.assertRaises(ValueError):
                factory(changed)


@unittest.skipUnless(os.name == 'nt', 'Native Win64 execution requires Windows')
class ExtraNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (GAME/'FFT_enhanced.exe').read_bytes()

    def setUp(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                             ctypes.c_uint32, ctypes.c_uint32]
        self.kernel.VirtualAlloc.restype = ctypes.c_void_p
        self.kernel.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
        self.memory = self.kernel.VirtualAlloc(None, 0x3000000, 0x3000, 0x40)
        self.assertTrue(self.memory, ctypes.get_last_error())

    def tearDown(self):
        self.assertTrue(self.kernel.VirtualFree(self.memory, 0, 0x8000))

    def write(self, address, data):
        ctypes.memmove(self.memory+address, data, len(data))

    def read(self, address, size):
        return ctypes.string_at(self.memory+address, size)

    def original(self, start, size):
        offset = raw_from_rva(self.data,start,size)
        self.write(start,self.data[offset:offset+size])

    def patch(self, patches):
        for patch in patches:
            self.write(patch['rva'],patch['data'])

    def test_rename_retains_unavailable_filter_and_removes_gender_filter(self):
        # Original mode2 only: RBX is the synthetic converted roster, RSI=0,
        # R14D=2. Save/restore all nonvolatile registers used by this fragment.
        wrapper = 0x285080
        code = bytes.fromhex('53 56 41 56 41 BE 02 00 00 00 48 8B D9 33 F6')
        self.write(wrapper,code+relative_jump(wrapper+len(code),0x2850AB))
        self.original(0x2850AB,0x1F)
        restore = bytes.fromhex('41 5E 5E 5B C3')
        self.write(0x2851E4,bytes.fromhex('B8 01 00 00 00')+restore)
        self.write(0x285225,bytes.fromhex('33 C0')+restore)
        roster = ctypes.create_string_buffer(0x80)
        allowed = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p)(self.memory+wrapper)
        for value in (0,0x20,0x40,0x80,0xC0,4,0x44,0x84):
            roster[0x70] = bytes([value])
            self.assertEqual(allowed(ctypes.addressof(roster)),int(value<0x40 and not value&4))
        self.patch(legacy_rename_patches(self.data))
        for value in (0,0x20,0x40,0x80,0xC0,4,0x44,0x84):
            roster[0x70] = bytes([value])
            self.assertEqual(allowed(ctypes.addressof(roster)),int(not value&4))

    def test_special_propositions_keep_source_ramza_and_native_monster_guards(self):
        entry = 0x2EE37C
        self.original(entry,0x4B)
        choose = ctypes.CFUNCTYPE(ctypes.c_uint64,ctypes.c_int)(self.memory+entry)
        unit = 0x11A7D10
        for job in (1,3,4,73,74,93,162,163):
            self.write(unit,bytes([job,0,0,0,0]))
            self.assertEqual(bool(choose(0)),job>=74 and job not in (162,163))
        self.patch(special_proposition_patches(self.data))
        for job in (1,3,4,73,74,93,162,163):
            self.write(unit,bytes([job,0,0,0,0]))
            self.assertEqual(bool(choose(0)),job>=4 and job not in (162,163))
        self.write(unit,bytes([74,0,0,0,0x20]))
        self.assertFalse(choose(0))
        self.write(unit,bytes([74,0xFF,0,0,0]))
        self.assertFalse(choose(0))
        self.write(unit,bytes([74,0,0,0,0]))
        self.write(unit+0x11E,b'\x01')
        self.assertFalse(choose(0))

    def test_active_party_rename_navigation_and_presentation_allow_all_jobs(self):
        # Execute the actual duplicated native job predicates; surrounding
        # availability/status checks are unchanged and covered by the complete
        # world predicate above. No invented actor or job definitions are used.
        unit = ctypes.create_string_buffer(0x180)
        pointer = ctypes.c_void_p(ctypes.addressof(unit))
        self.write(0x1800F50,struct.pack('<Q',ctypes.addressof(unit)))
        wrapper = 0x2C0E50
        code = bytes.fromhex('55 53 56 41 54 41 57 48 83 EC 20 4C 8B C1 33 ED 45 33 C9 45 33 E4 41 BF 01 00 00 00')
        self.write(wrapper,code+relative_jump(wrapper+len(code),0x2C0EEC))
        self.original(0x2C0EEC,0x68)
        self.original(0x2C0F54,0xB)
        self.write(0x2C069C,b'\x33\xC0\xC3')  # No current assignment/injury.
        self.write(0x2C0FE6,bytes.fromhex('41 0F B6 C7 48 83 C4 20 41 5F 41 5C 5E 5B 5D C3'))
        navigation = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p)(self.memory+wrapper)

        frame = ctypes.create_string_buffer(1)
        wrapper2 = 0x2C21E0
        code = bytes.fromhex('55 48 8D 69 7E')
        self.write(wrapper2,code+relative_jump(wrapper2+len(code),0x2C2217))
        self.original(0x2C2217,0x1A)
        self.write(0x2C2231,bytes.fromhex('B8 03 00 00 00 5D C3'))
        self.write(0x2C2330,bytes.fromhex('B8 01 00 00 00 5D C3'))
        presentation = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p)(self.memory+wrapper2)
        for patched in (False,True):
            if patched:
                self.patch(rename_patches(self.data))
            for job in (1,3,4,73,74,93,162,163):
                unit[0x72] = bytes([job])
                frame[0] = bytes([job])
                eligible = patched or (job >= 74 and job not in (162,163))
                self.assertEqual(navigation(ctypes.addressof(pointer)),int(eligible))
                self.assertEqual(presentation(ctypes.addressof(frame)),1 if eligible else 3)
            if patched:
                unit[0x72] = b'\x01'  # Ramza permitted when available.
                for flags, unavailable in ((0,0),(4,0),(0x40,0),(0x80,0),(0,1)):
                    unit[0x70] = bytes([flags])
                    unit[0x167] = bytes([unavailable])
                    self.assertEqual(navigation(ctypes.addressof(pointer)),int(not flags&4 and not unavailable))

    def test_recruit_naming_and_party_navigation_profiles_are_distinct(self):
        # The native state dispatch115FAC maps recruit naming4BB to type1.
        # Enter after unchanged game/UI readiness checks, using its actual
        # dispatch and return block. Name entry's successor is4BC.
        wrapper = 0x115F80
        code = bytes.fromhex('53 48 83 EC 20 8B D1')
        self.write(wrapper,code+relative_jump(wrapper+len(code),0x115FFC))
        self.original(0x115FFC,0x101)
        self.original(0x115FCD,11)
        mode = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_int)(self.memory+wrapper)
        self.assertEqual(mode(0x4BB),1)
        self.assertEqual(mode(0x457),3)
        self.assertEqual(mode(0x5EC),6)
        # Type1's actual navigation dispatch bypasses every actor predicate.
        wrapper0 = 0x2C0E50
        code = bytes.fromhex('56 BE 01 00 00 00 8B C1')
        self.write(wrapper0,code+relative_jump(wrapper0+len(code),0x2C0E84))
        self.original(0x2C0E84,9)
        self.write(0x2C106E,b'\x5E\xC3')
        navigation1 = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_int)(self.memory+wrapper0)
        for index in (0,1,17,49):
            self.assertEqual(navigation1(index),index)

        # The more restrictive type3 branch likewise has no job/gender gate;
        # unavailable bit4 remains the only actor restriction in that branch.
        wrapper = 0x2C0FB0
        code = bytes.fromhex('55 41 54 41 57 4C 8B C1 33 ED 41 BF 01 00 00 00')
        self.write(wrapper,code+relative_jump(wrapper+len(code),0x2C0FD6))
        self.original(0x2C0FD6,0x10)
        restore = bytes.fromhex('41 5F 41 5C 5D C3')
        self.write(0x2C0FE6,relative_jump(0x2C0FE6,0x2C1100))
        self.write(0x2C0FEB,relative_jump(0x2C0FEB,0x2C1120))
        self.write(0x2C1100,bytes.fromhex('B8 01 00 00 00')+restore)
        self.write(0x2C1120,bytes.fromhex('33 C0')+restore)
        actor = ctypes.create_string_buffer(0x80)
        pointer = ctypes.c_void_p(ctypes.addressof(actor))
        navigation = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p)(self.memory+wrapper)
        for job in (1,4,9,73,74,93,159,162,163):
            actor[0x72] = bytes([job])
            for flags in (0,0x20,0x40,0x80,0xC0,4,0x44,0x84):
                actor[0x70] = bytes([flags])
                self.assertEqual(navigation(ctypes.addressof(pointer)),int(not flags&4))

    @staticmethod
    def advance(state):
        x,y,z,w = state
        t = (x ^ (x<<11)) & 0xFFFFFFFF
        return y,z,w,(w ^ (w>>19) ^ t ^ (t>>8)) & 0xFFFFFFFF

    def encounter(self, *, patched=True, position=3, length=3, area=24,
                  entrance=1, chapter=1, chance=None, forced=False):
        entry = 0x248BE4
        self.original(entry,0x222)
        self.original(0x7B69D0,19*3*24)
        if chance is not None:
            self.write(0x7B69D0+3,bytes([chance]))
        self.write(0x2E9898,b'\xB8'+struct.pack('<I',chapter)+b'\xC3')
        state = (123456789,362436069,521288629,88675123)
        self.write(0x8E5FC8,struct.pack('<4I',*state))
        self.write(SMART_ROUTE_POSITION,struct.pack('<I',position))
        self.write(SMART_ROUTE_LENGTH,struct.pack('<I',length))
        # Native encounter preference2 disables ordinary chance success. Smart
        # still succeeds at destinations because source removes chance rolls.
        self.write(0x2E7FB18,struct.pack('<I',2))
        if patched:
            self.patch(smart_encounter_patches(self.data))
        select = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int)(self.memory+entry)
        accepted = select(area,entrance,int(forced))
        resulting_state = struct.unpack('<4I',self.read(0x8E5FC8,16))
        selected = struct.unpack('<I',self.read(0xD494C8,4))[0]
        return accepted,resulting_state,selected,state

    def test_smart_destinations_always_select_passing_nodes_never_select(self):
        accepted,state,variant,original = self.encounter(patched=False)
        self.assertEqual(accepted,0)
        self.assertEqual(state,self.advance(original))
        for position,length in ((0,3),(1,3),(2,3),(4,3),(1,1),(3,3)):
            accepted,state,variant,original = self.encounter(position=position,length=length)
            self.assertEqual(accepted,int(position==length))
            self.assertEqual(state,self.advance(original) if accepted else original)
            if accepted:
                self.assertEqual(variant,157)  # Native eligible maskC0 selects record14/15.

    def test_smart_keeps_native_eligibility_and_explicit_battle_selection(self):
        for case in ({'area':23},{'area':43},{'entrance':99},{'chapter':100},{'chance':0}):
            accepted,state,variant,original = self.encounter(**case)
            self.assertEqual(accepted,0)
            self.assertEqual(state,original)
        accepted,state,variant,original = self.encounter(forced=True,position=1,length=3)
        self.assertEqual(accepted,1)
        self.assertEqual(state,self.advance(original))
        self.assertEqual(variant,157)


if __name__ == '__main__':
    unittest.main()
