"""Authored RCC script references, Enhanced guards and consumed name pools.

These checks use locally extracted original scripts and the supplied RCC
checkout. They neither generate repeated packages nor launch the game.
"""
import ast
import copy
import hashlib
import os
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fftic.rcc_events import (LENGTHS, apply_event_assets, auto_mash, ending_script,
                              instructions, prepare_event_inputs, progression_scripts)
from fftic.rcc_names import consume_names


ROOT=Path(__file__).resolve().parents[1]
GAME=ROOT.parent
SOURCE=Path(os.environ.get('FFTIC_RCC_SOURCE','I:/rumble_chaos_crashdown'))


def source_tree(name):
    """Read a Python-3-compatible source function without importing RCC."""
    lines=(SOURCE/'randomizer.py').read_text(encoding='utf-8').splitlines()
    start=next(i for i,line in enumerate(lines) if line.startswith('def '+name+'('))
    end=start+1
    while end<len(lines):
        if lines[end].strip() and not lines[end].startswith((' ','#')):
            break
        end+=1
    return ast.parse('\n'.join(lines[start:end]))


class DialogueInstructionTests(unittest.TestCase):
    def test_automatic_dialogue_preserves_every_other_byte_and_is_idempotent(self):
        # Exercise every combination of wait and unrelated DisplayMessage
        # flags, preserving its expanded message ID and all other operands.
        messages=[bytes((0x10,17,flag))+bytes.fromhex('78563412')+bytes(range(11))
                  for flag in range(256)]
        original=b''.join(messages)+b'\xDB\xE6\xAA\xBB'
        self.assertEqual(len(messages[0]),LENGTHS[0x10]['enhanced']+1)
        changed,count=auto_mash(original)
        expected=bytearray(original)
        for index in range(256): expected[index*18+2]&=0x8F
        self.assertEqual(changed,bytes(expected))
        self.assertEqual(count,sum(bool(flag&0x70) for flag in range(256)))
        self.assertEqual(auto_mash(changed),(changed,0))
        self.assertEqual(original,b''.join(messages)+b'\xDB\xE6\xAA\xBB')

    def test_decoder_rejects_live_bad_or_truncated_code_and_preserves_dead_tail(self):
        for code in (b'\xE6',b'\x10\x00',b'\x11\x01\x00'):
            with self.assertRaises(ValueError): list(instructions(code))
        dead=b'\xDB\xE6\x10\x01'
        self.assertEqual(list(instructions(dead)),[(0,0xDB,b'\xDB')])
        self.assertEqual(auto_mash(dead),(dead,0))


@unittest.skipUnless((GAME/'FFT_enhanced.exe').exists() and (SOURCE/'randomizer.py').exists(),
                     'Requires legally owned Enhanced scripts and supplied RCC checkout')
class AuthoredEventReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets,cls.inputs=prepare_event_inputs(GAME,ROOT)

    def test_overworld_progression_matches_authored_source_and_retains_native_prefixes(self):
        original=copy.deepcopy(self.assets)
        changed,audit=progression_scripts(self.assets)
        assignments=[node for node in ast.walk(source_tree('randomize_overworld'))
                     if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='event_data' for t in node.targets)]
        authored=[text.encode('latin1') for text in ast.literal_eval(assignments[0].value)]
        indices={290:0,303:1,311:3,312:4,313:5,317:6,321:7}
        self.assertEqual(len(changed),8)
        for item in audit:
            event=item['event']
            if event not in indices: continue
            name=f'script/enhanced/event{event:03}.e'
            cut=int(item['boundary'],16)
            self.assertEqual(changed[name][:cut],original[name][:cut])
            actual=[raw for offset,op,raw in instructions(changed[name]) if offset>=cut and op!=0xF2]
            expected=[raw for _,op,raw in instructions(authored[indices[event]],'classic') if op!=0xF2]
            self.assertEqual(actual,expected,event)
        self.assertEqual(self.assets,original)

    def test_murond_conversion_preserves_authored_commands_and_maps_only_message_operands(self):
        changed,_=progression_scripts(self.assets)
        source=(SOURCE/'tables/entrance_murond_new.dat').read_bytes()
        old=list(instructions(source,'classic'))
        new=list(instructions(changed['script/enhanced/event309.e']))
        self.assertEqual(len(old),len(new))
        speeches=[]
        for (_,old_op,old_raw),(_,new_op,new_raw) in zip(old,new):
            self.assertEqual(old_op,new_op)
            if old_op!=0x10:
                self.assertEqual(old_raw,new_raw)
                continue
            message=int.from_bytes(old_raw[3:5],'little')
            expected={1:301508,5:301512}[message]
            self.assertEqual(new_raw[:3],old_raw[:3])
            self.assertEqual(int.from_bytes(new_raw[3:7],'little'),expected)
            self.assertEqual(new_raw[7:-1],old_raw[5:])
            self.assertEqual(new_raw[-1],0)
            speeches.append(expected)
        self.assertEqual(speeches,[301508,301512])

    def test_ending_reveal_matches_literal_source_and_checks_native_identity_anchors(self):
        original=self.assets['script/enhanced/event300.e']
        delita_id=next(raw[1] for offset,op,raw in instructions(original) if offset==0x1A0)
        writes=[node for node in ast.walk(source_tree('randomize_ending'))
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='write'
                and any(isinstance(child,ast.Name) and child.id=='delita_unit' for child in ast.walk(node))]
        environment=dict(ramza=3,x=6,y=6,north=2,delita_unit=SimpleNamespace(unit_id=delita_id))
        authored=eval(compile(ast.Expression(writes[0].args[0]),'<RCC authored ending>','eval'),environment).encode('latin1')
        changed=ending_script(original,delita_id)
        self.assertEqual(changed,original[:0x1BC]+authored)
        self.assertEqual(list(instructions(changed))[-1][1],0xDB)
        with self.assertRaisesRegex(ValueError,'Delita animation anchor'):
            ending_script(original,delita_id^1)
        bad=bytearray(original)
        bad[0x1BD]^=1
        with self.assertRaisesRegex(ValueError,'flower-scene boundary'):
            ending_script(bytes(bad),delita_id)

    def test_changed_murond_dialogue_is_rejected_and_package_audit_preserves_inputs(self):
        bad=dict(self.assets)
        name='script/enhanced/event309.e'
        offset=next(offset for offset,op,_ in instructions(bad[name]) if op==0x10)
        raw=bytearray(bad[name]);raw[offset+3]^=1;bad[name]=bytes(raw)
        with self.assertRaisesRegex(ValueError,'Murond dialogue identity anchors'):
            progression_scripts(bad)
        ending=self.assets['script/enhanced/event300.e']
        delita_id=next(raw[1] for offset,_,raw in instructions(ending) if offset==0x1A0)
        result={'_RCCUnitContext':{(307,0):{'UnitId':delita_id}}}
        snapshot=copy.deepcopy(self.assets)
        with patch('fftic.rcc_events.prepare_event_inputs',return_value=(self.assets,self.inputs)):
            audit=apply_event_assets({},result,GAME,ROOT,'z')
        self.assertTrue(audit['ending_reveal'])
        self.assertEqual(audit['warjilis_background_script'],115)
        self.assertEqual(len(result['_RCCEventAssets']),10)
        background='script/enhanced/event115.e'
        self.assertEqual(result['_RCCEventAssets'][background],b'\xF2'*9+self.assets[background][9:])
        for name,record in audit['changed_assets'].items():
            self.assertEqual(record['original_sha256'],hashlib.sha256(self.assets[name]).hexdigest())
            self.assertEqual(record['generated_sha256'],hashlib.sha256(result['_RCCEventAssets'][name]).hexdigest())
        self.assertEqual(self.assets,snapshot)


@unittest.skipUnless((SOURCE/'randomizer.py').exists(),'Requires supplied RCC name-allocation reference')
class NamePoolReferenceTests(unittest.TestCase):
    def reference(self,rng,path):
        # Source only iterates this handle. Supplying its exact text lines
        # preserves that behavior without reproducing its unclosed file.
        environment=dict(random=rng,NAMESFILE=str(path),name_to_bytes=lambda name:name,
                         open=lambda filename:Path(filename).read_text(encoding='utf-8').splitlines(keepends=True))
        for function in ('randint','get_new_names'):
            exec(compile(source_tree(function),'<RCC names reference>','exec'),environment)
        return environment['get_new_names']

    def test_name_consumption_matches_source_including_repeated_original_names(self):
        basenames=['Lena','Omar','Lena','Nora','Edith','Ada']
        candidates='frog\ntoad\nbear\nwolf\nswan\nfish\ngoat\nlion\nSnake\nEagle\nOtter\nCat\nDog\nHen\ntiny_bear\nAnOtter\nLONGWORD\nold_man\n'
        with tempfile.TemporaryDirectory() as scratch:
            path=Path(scratch)/'names.txt';path.write_text(candidates)
            for seed in range(8):
                source_rng,port_rng=random.Random(seed),random.Random(seed)
                expected=self.reference(source_rng,path)(basenames).split('\xFE')
                with patch('fftic.rcc_names.NAMES_FILE',path):
                    actual=consume_names(basenames,port_rng)
                self.assertEqual(actual,expected)
                self.assertEqual(source_rng.getstate(),port_rng.getstate())
                self.assertEqual(actual[0],actual[2])
                self.assertEqual([len(name) for name in actual],[len(name) for name in basenames])

    def test_depleted_name_bucket_is_rejected_instead_of_silently_reusing_names(self):
        with tempfile.TemporaryDirectory() as scratch:
            path=Path(scratch)/'names.txt';path.write_text('frog\ntoad\n')
            basenames=['Lena','Omar','Nora']
            with self.assertRaises(TypeError):
                self.reference(random.Random(0),path)(basenames)
            with patch('fftic.rcc_names.NAMES_FILE',path):
                with self.assertRaisesRegex(ValueError,'bucket exhausted for length 4'):
                    consume_names(basenames,random.Random(0))


if __name__=='__main__':
    unittest.main()
