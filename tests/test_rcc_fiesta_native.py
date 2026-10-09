"""Exact native Fiesta instruction, caller guards and runtime plan integration."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fftic.game import ENHANCED_SHA256
from fftic.rcc_fiesta_native import (RAMZA_JOB_STORE,ORIGINAL_STORE,MIME_STORE,GUARDS,
                                    fiesta_native_patches,apply_fiesta_native)
from fftic.rcc_qol import raw_from_rva
from fftic.rcc_secrets import apply_secrets
from test_rcc_secrets import state,engine


PROJECT = Path(__file__).resolve().parents[1]
GAME = PROJECT.parent


@unittest.skipUnless((GAME/'FFT_enhanced.exe').is_file(),'Requires verified local Enhanced executable')
class FiestaNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.data = (GAME/'FFT_enhanced.exe').read_bytes()

    def test_plan_changes_only_one_same_length_ramza_job_store(self):
        plans = fiesta_native_patches(self.data)
        self.assertEqual(len(plans),1)
        plan = plans[0]
        self.assertEqual((plan['rva'],plan['expected'],plan['data']),
                         (RAMZA_JOB_STORE,ORIGINAL_STORE,MIME_STORE))
        raw = raw_from_rva(self.data,RAMZA_JOB_STORE,4)
        new = bytearray(self.data)
        new[raw:raw+4] = plan['data']
        self.assertEqual([index for index,(old,after) in enumerate(zip(self.data,new)) if old!=after],
                         list(range(raw,raw+4)))
        for address in (0x275356,0x27536D,0x275384):
            offset = raw_from_rva(self.data,address,4)
            self.assertEqual(new[offset:offset+4],bytes.fromhex('C6 41 02 4A'))
        # Graphic still comes from r13b=1; no reused loop/flag constant changes.
        address = raw_from_rva(self.data,0x27538F,3)
        self.assertEqual(new[address:address+3],bytes.fromhex('44 88 29'))

    @unittest.skipUnless(importlib.util.find_spec('capstone'),'Capstone is optional read-only research dependency')
    def test_replacement_instruction_has_same_field_and_flags_semantics(self):
        from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_OP_MEM,CS_OP_IMM
        md = Cs(CS_ARCH_X86,CS_MODE_64)
        md.detail = True
        original = list(md.disasm(ORIGINAL_STORE,RAMZA_JOB_STORE))
        modified = list(md.disasm(MIME_STORE,RAMZA_JOB_STORE))
        self.assertEqual(len(original),1)
        self.assertEqual(len(modified),1)
        for instruction in original+modified:
            self.assertEqual(instruction.mnemonic,'mov')
            self.assertEqual(instruction.size,4)
            self.assertEqual(instruction.operands[0].type,CS_OP_MEM)
            self.assertEqual(instruction.operands[0].mem.disp,2)
            self.assertEqual(instruction.reg_name(instruction.operands[0].mem.base),'rcx')
            self.assertEqual(instruction.eflags,0)
        self.assertEqual(modified[0].operands[1].type,CS_OP_IMM)
        self.assertEqual(modified[0].operands[1].imm,93)

    def test_exact_hash_and_independent_caller_guards_reject_tampering(self):
        corrupt = bytearray(self.data)
        raw = raw_from_rva(self.data,RAMZA_JOB_STORE,4)
        corrupt[raw] ^= 1
        with self.assertRaisesRegex(ValueError,'verified Enhanced'):
            fiesta_native_patches(corrupt)
        # Permit the SHA gate artificially so the independent instruction,
        # branch and caller guards are exercised rather than masked by it.
        class AcceptedHash:
            def hexdigest(self): return ENHANCED_SHA256
        for label,start,end,digest in GUARDS:
            corrupt = bytearray(self.data)
            corrupt[raw_from_rva(self.data,start,end-start)] ^= 1
            with patch('fftic.rcc_fiesta_native.hashlib.sha256',side_effect=lambda block:AcceptedHash() if len(block)==len(self.data) else __import__('hashlib').new('sha256',block)):
                with self.assertRaisesRegex(ValueError,'guard'):
                    fiesta_native_patches(corrupt)

    def test_secret_integration_uses_verified_helper_and_does_not_write_executable(self):
        before = state()
        before['_RCCGameDirectory'] = str(GAME)
        after = copy.deepcopy(before)
        audit = apply_secrets(before,after,'fiesta-reference',fiesta=True,engine=engine(after))
        self.assertEqual(audit['native_fiesta']['initial_job'],93)
        self.assertEqual(len(after['_RCCNativeTablePatches']),1)
        self.assertEqual(after['_RCCNativeTablePatches'][0]['data'],MIME_STORE)
        self.assertEqual(after['_RCCUnitContext'][392,0]['MainJob'],93)
        self.assertEqual((GAME/'FFT_enhanced.exe').read_bytes(),self.data)
        json.dumps(audit)
        with self.assertRaisesRegex(ValueError,'already planned'):
            apply_fiesta_native(before,after)


if __name__=='__main__': unittest.main()
