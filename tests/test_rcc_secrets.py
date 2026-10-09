"""Optional secrets compared with literal RCC code, including write-order quirks."""
import ast
import copy
import json
import random
from types import SimpleNamespace
import unittest

from fftic.rcc_encounter_data import ENTRY_FIELDS,set_flag
from fftic.rcc_units import NativeUnit,JOBNAMES
from fftic.rcc_secrets import apply_fiesta_units,apply_easymodo_units,apply_secrets
from test_rcc_reference import SOURCE,source_function,compile_reference


class UnitTable:
    def __init__(self,units): self.every = units
    def __iter__(self): return iter(self.every)


class RecordingFile:
    def __init__(self): self.offset,self.writes = 0,[]
    def seek(self,offset): self.offset = offset
    def write(self,value):
        value = value.encode('latin1') if isinstance(value,str) else value
        self.writes.append((self.offset,value))
        self.offset += len(value)
    def close(self): pass


def state():
    rows = {}
    for entd in (1,0x183,0x184,0x188,519):
        for slot in range(16):
            row = dict.fromkeys(ENTRY_FIELDS,0)
            row.update(Spriteset=128 if slot%3 else 1,MainJob=74,Level=20+slot,
                       SecondarySkillset=9,Reaction=437,Support=452,Movement=467,
                       JobUnlock=7,JobLevel=4,RightHand=5,LeftHand=6,Head=7,Body=8,
                       Accessory=9,Palette=3,Bravery=50,Faith=51)
            set_flag(row,'enemy_team',slot%2==0)
            rows[entd,slot] = row
    # Explicit generic monster proves easymodo follows the source sprite
    # test, rather than adding a modern humanoid-only safety substitution.
    rows[519,2]['Spriteset'] = 130
    return {'_RCCUnitContext':rows}


def engine(result,seed=17):
    result_engine = SimpleNamespace(backups={},random=random.Random(seed),mapunits={})
    result_engine.units = [NativeUnit(result_engine,owner,row) for owner,row in sorted(result['_RCCUnitContext'].items())]
    for unit in result_engine.units: result_engine.mapunits.setdefault(unit.map_id,[]).append(unit)
    result_engine.UnitObject = UnitTable(result_engine.units)
    return result_engine


def easy_reference(environment):
    lines = (SOURCE/'randomizer.py').read_text(encoding='utf-8').splitlines()
    begin = next(index for index,line in enumerate(lines) if line.strip()=='if "easymodo" in activated_codes:')
    snippet = ['def easy_reference():']
    for line in lines[begin+1:]:
        if line.strip() and len(line)-len(line.lstrip())<=4: break
        snippet.append(line[4:])
    exec(compile(ast.parse('\n'.join(snippet)),'<RCC easymodo source>','exec'),environment)
    return environment['easy_reference']


@unittest.skipUnless((SOURCE/'randomizer.py').is_file(),'Requires original RCC source checkout')
class RCCSecretReferenceTests(unittest.TestCase):
    def reference(self,result):
        original_engine = engine(result)
        file = RecordingFile()
        environment = dict(JAPANESE_MODE=False,open=lambda *args:file,
                           mapunits=original_engine.mapunits,UnitObject=original_engine.UnitObject)
        return original_engine,file,environment

    def test_fiesta_matches_literal_unit_fields_and_preserves_last_unit_quirk(self):
        expected,actual = state(),state()
        original_engine,file,environment = self.reference(expected)
        new_engine = engine(actual)
        old_rng = new_engine.random.getstate()
        compile_reference(environment,'setup_fiesta')('unused.iso')
        audit = apply_fiesta_units(new_engine)
        self.assertEqual(actual,expected)
        self.assertEqual(new_engine.random.getstate(),old_rng)
        self.assertEqual(file.writes,[(0x62978,bytes.fromhex('88 33 44 43 44 43 44 00 00 00')),
                                     (0x56894,b'\x5d'),(0x568B0,b'\x5d')])
        self.assertEqual(actual['_RCCUnitContext'][392,15]['RightHand'],73)
        for slot in (0,2,3,4,5):
            self.assertEqual(actual['_RCCUnitContext'][392,slot]['RightHand'],5)
            self.assertEqual(actual['_RCCUnitContext'][392,slot]['Palette'],3)
        self.assertEqual(audit['last_starting_slot_armed'],(392,15))

    def test_easymodo_matches_literal_enemy_sprite_rule_including_monsters(self):
        expected,actual = state(),state()
        original_engine,file,environment = self.reference(expected)
        new_engine = engine(actual)
        old_rng = new_engine.random.getstate()
        easy_reference(environment)()
        audit = apply_easymodo_units(new_engine)
        self.assertEqual(actual,expected)
        self.assertEqual(new_engine.random.getstate(),old_rng)
        self.assertEqual(actual['_RCCUnitContext'][519,2]['MainJob'],28)
        self.assertEqual(actual['_RCCUnitContext'][519,2]['Level'],1)
        self.assertEqual(actual['_RCCUnitContext'][519,0]['MainJob'],74)
        self.assertEqual(actual['_RCCUnitContext'][519,1]['Level'],21)
        self.assertIn((519,2),audit['generic_enemy_jobs'])

    def test_combined_source_order_is_fiesta_then_easy_with_no_final_cleanup(self):
        expected,actual = state(),state()
        original_engine,file,environment = self.reference(expected)
        compile_reference(environment,'setup_fiesta')('unused.iso')
        easy_reference(environment)()
        new_engine = engine(actual)
        original_rng = new_engine.random.getstate()
        helper_calls = []
        def native_helper(before,result):
            helper_calls.append(copy.deepcopy(result['_RCCUnitContext']))
            return {'newgame_job':93,'verified':True}
        before = copy.deepcopy(actual)
        audit = apply_secrets(before,actual,'secret-reference',fiesta=True,easymodo=True,
                              engine=new_engine,fiesta_native=native_helper)
        self.assertEqual(actual['_RCCUnitContext'],expected['_RCCUnitContext'])
        self.assertEqual(audit['order'],['fiesta','easymodo'])
        self.assertEqual(helper_calls,[before['_RCCUnitContext']])
        self.assertEqual(new_engine.random.getstate(),original_rng)
        # This party fixture is enemy flagged, so easy runs last and replaces
        # the just-assigned Mime job. Non-enemy party palettes stay untouched.
        self.assertEqual(actual['_RCCUnitContext'][392,2]['MainJob'],28)
        self.assertEqual(actual['_RCCUnitContext'][392,3]['MainJob'],93)
        self.assertEqual(actual['_RCCUnitContext'][392,3]['Palette'],3)
        json.dumps(audit)

    def test_direct_mime_requirement_bytes_are_overwritten_by_source_final_writer(self):
        file = RecordingFile()
        class BaseWriter:
            def write_data(self,filename=None,pointer=None):
                file.seek(0x62978)
                file.write(bytes(getattr(self,name) for name in ('squche','kniarc','monpri','wiztim','sumthi','medora','geolan','samnin','calbar','danmim')))
        environment = {}
        exec(compile(source_function('randomizer.py','write_data',owner='JobReqObject'),'<RCC final JobReq writer>','exec'),environment)
        requirement_type = type('JobReqObject',(BaseWriter,),{'write_data':environment['write_data']})
        environment['JobReqObject'] = requirement_type
        requirement = requirement_type()
        for name in JOBNAMES: setattr(requirement,name,0)
        file.seek(0x62978)
        file.write(bytes.fromhex('88 33 44 43 44 43 44 00 00 00'))
        requirement.write_data()
        self.assertEqual(file.writes[-1],(0x62978,bytes(10)))
        self.assertNotEqual(file.writes[0],file.writes[-1])

    def test_disabled_switches_and_failed_native_guard_do_not_mutate_units(self):
        before,actual = state(),state()
        audit = apply_secrets(before,actual)
        self.assertEqual(audit['order'],[])
        self.assertNotIn('_RCCUnitEngine',actual)
        self.assertEqual(actual['_RCCUnitContext'],before['_RCCUnitContext'])
        def rejected(before,result): raise ValueError('Native fiesta byte guard changed')
        with self.assertRaisesRegex(ValueError,'guard'):
            apply_secrets(before,actual,fiesta=True,fiesta_native=rejected)
        self.assertEqual(actual['_RCCUnitContext'],before['_RCCUnitContext'])
        with self.assertRaisesRegex(ValueError,'boolean'):
            apply_secrets(before,actual,fiesta=1)


if __name__=='__main__': unittest.main()
