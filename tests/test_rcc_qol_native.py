"""Meaningful source/guard checks and isolated execution of reviewed Win64 stubs.

No game process is started, inspected or modified by these tests.
"""
import ctypes
import hashlib
import os
from pathlib import Path
import struct
import unittest

from fftic.game import ENHANCED_SHA256
from fftic.rcc_qol import (PROLOGUE, apply_qol, double_jp_patches,
                          early_unlock_stub, mighty_sword_code, raw_from_rva,
                          relative_jump)


@unittest.skipUnless(os.name == 'nt', 'Win64 machine-code execution requires Windows')
class QolMachineCodeTests(unittest.TestCase):
    def setUp(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                             ctypes.c_uint32, ctypes.c_uint32]
        self.kernel.VirtualAlloc.restype = ctypes.c_void_p
        self.kernel.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
        self.memory = self.kernel.VirtualAlloc(None, 0x1900000, 0x3000, 0x40)
        self.assertTrue(self.memory, ctypes.get_last_error())

    def tearDown(self):
        self.assertTrue(self.kernel.VirtualFree(self.memory, 0, 0x8000))

    def write(self, offset, data):
        ctypes.memmove(self.memory+offset, data, len(data))

    def read(self, offset, size):
        return ctypes.string_at(self.memory+offset, size)

    def instruction(self, start, prefix, target, suffix=b''):
        raw = bytes.fromhex(prefix)
        return raw+struct.pack('<i', target-start-len(raw)-4)+suffix

    def test_early_unlock_stub_preserves_other_flag_values(self):
        # The synthetic original getter returns flag+7. Its original first
        # instruction and stack home space are identical to the real getter.
        entry, cave, helper = 0, 64, 144
        self.write(entry, PROLOGUE+bytes.fromhex('8D 41 07 C3'))
        self.write(cave, early_unlock_stub(entry, cave, helper))
        self.write(helper, bytes.fromhex('B8 01 00 00 00 C3'))
        self.write(entry, relative_jump(entry, cave))
        getter = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)(self.memory)
        for flag in (-200, -1, 0, 22, 143, 144, 145, 146, 471, 1024):
            self.assertEqual(getter(flag), 1 if flag in (144,145) else flag+7)

    def test_double_jp_stub_preserves_team_and_valid_action_mask(self):
        data = (Path(__file__).resolve().parents[2]/'FFT_enhanced.exe').read_bytes()
        patches = double_jp_patches(data)
        entry = patches[0]['rva']
        wrapper = entry-18
        for level,job_level,valid,team in ((1,1,True,0x75),(99,8,True,0x4F),
                                         (20,4,False,0x30),(60,6,True,0x02)):
            base = 8+level//4+2*job_level
            code = bytes.fromhex('55 56 57 BD')+struct.pack('<I',base)
            code += b'\xB9'+struct.pack('<I',0xFFFFFFFF if valid else 0)
            code += b'\xBE'+struct.pack('<I',team)
            self.assertEqual(len(code),18)
            self.write(wrapper,code)
            for patch in patches:
                self.write(patch['rva'],patch['data'])
            self.write(entry+8,bytes.fromhex('8B C5 C1 E6 10 03 C6 5F 5E 5D C3'))
            calculated = ctypes.CFUNCTYPE(ctypes.c_uint32)(self.memory+wrapper)()
            self.assertEqual(calculated,(base*2 if valid else 0)+((team&0x30)<<16))

    def test_original_enhanced_fur_menu_and_entry_need_no_party_abilities(self):
        data = (Path(__file__).resolve().parents[2]/'FFT_enhanced.exe').read_bytes()
        town,labels = ctypes.create_string_buffer(64),ctypes.create_string_buffer(32)
        town[0x32] = b'\x01'
        constructor = 0x3449B0
        raw = raw_from_rva(data,constructor,0xB1)
        self.write(constructor,data[raw:raw+0xB1])
        self.write(0x693533,b'\x01')  # Native town0 is a settlement with facilities.
        self.write(0x2E9898,bytes.fromhex('B8 01 00 00 00 C3'))
        self.write(0x3DBC74,b'\x48\xB8'+struct.pack('<Q',ctypes.addressof(town))+b'\xC3')
        build_menu = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_int,ctypes.c_void_p)(self.memory+constructor)
        self.assertEqual(build_menu(0,ctypes.addressof(labels)),4)
        self.assertEqual(struct.unpack_from('<I',labels,12)[0],0xB860)
        # Run the original Poach controller's state14 activation with empty
        # widget vectors and no party/unit structures. Only its global UI-root
        # pointer relocation changes to fit our bounded synthetic allocation.
        entry,end = 0x1AF630,0x1AF7CC
        raw = raw_from_rva(data,entry,end-entry)
        code = bytearray(data[raw:raw+end-entry])
        pointer_instruction = 0x1AF78B
        self.assertEqual(code[pointer_instruction-entry:pointer_instruction-entry+3],b'\x48\x8B\x05')
        struct.pack_into('<i',code,pointer_instruction-entry+3,0x1800000-pointer_instruction-7)
        self.write(entry,bytes(code))
        root,ui,world,agent = (ctypes.create_string_buffer(0x300) for _ in range(4))
        struct.pack_into('<Q',root,0x10,ctypes.addressof(ui))
        struct.pack_into('<Q',ui,0x98,ctypes.addressof(world))
        self.write(0x1800000,struct.pack('<Q',ctypes.addressof(root)))
        self.write(0xEB65C,self.instruction(0xEB65C,'89 15',0x144,b'\xC3'))
        activate = ctypes.CFUNCTYPE(None,ctypes.c_void_p,ctypes.c_int,ctypes.c_int)(self.memory+entry)
        activate(ctypes.addressof(agent),14,0)
        self.assertEqual(struct.unpack('<I',self.read(0x144,4))[0],0x1B59)

    def _mighty_case(self, safeguard=False, missing=False, synthetic=False, evade=False):
        result = ctypes.create_string_buffer(64)
        caster = ctypes.create_string_buffer(512)
        defender = ctypes.create_string_buffer(512)
        caster[0x3E] = b'\x03'
        defender[0x9A] = b'\x04' if safeguard else b'\x00'
        result[0] = b'\x01'
        for offset, value in ((0x186AF70,ctypes.addressof(result)),
                              (0x186AF78,ctypes.addressof(caster)),
                              (0x186AF68,ctypes.addressof(defender))):
            self.write(offset, struct.pack('<Q',value))
        self.write(0x7B07AC, b'\x07')
        self.write(0x7B079E, b'\x05')
        self.write(0x7B07AE, b'\x40')
        counts = 0x100
        self.write(counts,b'\0'*32)
        # Helpers are synthetic stand-ins at the *same image-relative targets*.
        # Exercise native RIP displacements, calls, branching and stack setup.
        for address in (0x305BB8,0x306E34,0x305EB4):
            self.write(address,b'\xC3')
        for index,address in enumerate((0x278E68,0x3065C4,0x305554,0x306224,0x306944)):
            counter = self.instruction(address,'FF 05',counts+index*4)
            if address == 0x3065C4:
                code = counter+self.instruction(address+len(counter),'48 8B 05',0x186AF70)
                code += bytes.fromhex('66 C7 40 04')+struct.pack('<H',258 if synthetic else 16)
                code += bytes.fromhex('C6 40 1B 80')
                code += b'\xB8'+struct.pack('<i',-1 if missing else 0)+b'\xC3'
            elif address == 0x305554:
                code = counter+self.instruction(address+len(counter),'88 0D',counts+24,b'\xC3')
            else:
                code = counter+bytes.fromhex('33 C0 C3')
            self.write(address,code)
        self.write(0x306C90,b'\xB8'+struct.pack('<i',int(evade))+b'\xC3')
        address = 0x305F08
        code = self.instruction(address,'0F B7 05',0x7B0770)
        code += self.instruction(address+len(code),'0F B7 0D',0x7B0772)
        code += bytes.fromhex('0F AF C1')
        code += self.instruction(address+len(code),'48 8B 15',0x186AF70)
        code += bytes.fromhex('66 89 42 06 C3')
        self.write(address,code)
        self.write(0x308538,mighty_sword_code())
        ctypes.CFUNCTYPE(None)(self.memory+0x308538)()
        return bytes(result),struct.unpack('<5I',self.read(counts,20)),self.read(counts+24,1)[0]

    def test_mighty_sword_damage_break_and_source_missing_slot_rules(self):
        for kwargs,damage,break_flag,counters in (
            ({},18,4,(1,1,1,1,1)),
            ({'safeguard':True},18,0,(0,0,1,1,1)),
            ({'safeguard':True,'missing':True},18,0,(0,0,1,1,1)),
            ({'missing':True},0,0,(1,1,0,0,0)),
            ({'synthetic':True},18,0,(1,1,1,1,1)),
            ({'evade':True},0,4,(1,1,0,0,0)),
        ):
            result,seen,element = self._mighty_case(**kwargs)
            self.assertEqual(struct.unpack_from('<H',result,6)[0],damage)
            self.assertEqual(struct.unpack_from('<H',result,18)[0],break_flag)
            self.assertEqual(seen,counters)
            self.assertEqual(element,64 if counters[2] else 0)


@unittest.skipUnless((Path(__file__).resolve().parents[2]/'FFT_enhanced.exe').is_file(),
                     'Requires verified local Enhanced inputs')
class QolGuardTests(unittest.TestCase):
    def test_current_build_patch_guards_and_no_overlaps(self):
        game = Path(__file__).resolve().parents[2]
        data = (game/'FFT_enhanced.exe').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),ENHANCED_SHA256)
        result = {}
        audit = apply_qol({},result,game,'jsmapw')
        self.assertEqual(audit['native_patch_count'],14)
        used = set()
        for patch in result['_RCCNativeTablePatches']:
            raw = raw_from_rva(data,patch['rva'],len(patch['expected']))
            self.assertEqual(data[raw:raw+len(patch['expected'])],patch['expected'])
            self.assertEqual(len(patch['expected']),len(patch['data']))
            addresses = set(range(patch['rva'],patch['rva']+len(patch['data'])))
            self.assertFalse(used&addresses)
            used.update(addresses)
        altered = bytearray(data)
        altered[raw_from_rva(data,0x283595)] ^= 1
        with self.assertRaises(ValueError):
            double_jp_patches(altered)

    def test_free_office_uses_original_rcc_flag_condition(self):
        game = Path(__file__).resolve().parents[2]
        result = {}
        audit = apply_qol({},result,game,'ocb')
        self.assertEqual(audit['native_patch_count'],9)
        self.assertFalse(any('free office' in p['name'] for p in result['_RCCNativeTablePatches']))


if __name__ == '__main__':
    unittest.main()
