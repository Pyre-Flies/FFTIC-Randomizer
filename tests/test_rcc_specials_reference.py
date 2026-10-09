"""Literal-source z/weather/Warjilis comparisons with complete native tables."""
import ast
import copy
from pathlib import Path
import random
import unittest

from fftic.game import read_game,ACTION_FIELDS,RSM_FIELDS
from fftic.catalog import attach_catalog
from fftic.rcc_encounter_data import prepare_unit_context,decode_entry,emit_changed_entries
from fftic.rcc_world_data import prepare_world_data
from fftic.rcc_maps import attach_maps
from fftic.rcc_units import native_rankings
from fftic.rcc_specials import (special_environment,compile_special_methods,guarantee_invite,
                                apply_alma_math_cleanup,IntegerDivision,SpecialJob)
from fftic.rcc_surprises_world import SurpriseWorld,compile_restore_warjilis,randomize_weather
from test_rcc_reference import SOURCE,source_function


PROJECT = Path(__file__).resolve().parents[1]


def reference_function(name,environment,owner=None):
    tree = IntegerDivision().visit(source_function('randomizer.py',name,owner=owner))
    ast.fix_missing_locations(tree)
    exec(compile(tree,'<RCC z reference>','exec'),environment)
    return environment[name]


class SparseEntryRegressionTests(unittest.TestCase):
    def test_new_owner_directions_and_disable_need_no_nex_rows(self):
        row = decode_entry(bytes(40));old = {(519,0):row};new = copy.deepcopy(old)
        new[519,0]['InitialDirection'] = 130
        assets,nex,_ = emit_changed_entries(old,new,{5:bytes(77*640)})
        self.assertTrue(assets);self.assertEqual(nex,{})


@unittest.skipUnless((SOURCE/'randomizer.py').exists() and (PROJECT.parent/'FFT_enhanced.exe').exists(),
                     'Requires supplied RCC checkout and verified local Enhanced inputs')
class RCCSpecialReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before,_ = read_game(PROJECT.parent)
        attach_catalog(cls.before,PROJECT.parent,PROJECT)
        prepare_unit_context(cls.before,PROJECT.parent,PROJECT)
        prepare_world_data(cls.before,PROJECT.parent,PROJECT)
        attach_maps(cls.before,PROJECT.parent,PROJECT,89)
        native_rankings(cls.before)

    def test_special_units_and_balmafula_match_source_and_rng(self):
        for seed in (1,89,567):
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            expected,actual = copy.deepcopy(self.before),copy.deepcopy(self.before)
            reference_env = special_environment(self.before,expected,source_rng)
            port_env = special_environment(self.before,actual,port_rng)
            reference_env.update(range=lambda *args:list(range(*args)))
            reference_function('generate_balmafula',reference_env)
            reference = reference_function('mutate_units_special',reference_env)
            # The source has no Enhanced templates: compare its literal classic
            # loop, then separately exercise extra templates in integration.
            port_env['_ENHANCED_ENTDS'] = []
            port = compile_special_methods(port_env)['mutate_units_special']
            reference();port()
            self.assertEqual(actual['JobData'],expected['JobData'])
            self.assertEqual(actual['_RCCUnitContext'],expected['_RCCUnitContext'])
            self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_weather_matches_literal_source_including_fixed_weather_rolls(self):
        for seed in range(8):
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            env = dict(random=source_rng,randint=source_rng.randint,FIXED_WEATHER=[415,437,450])
            reference = reference_function('randomize_weather',env,owner='EncounterObject')
            for entd,weather,night in ((1,0,0),(415,3,1),(450,4,1),(550,2,0),(0,255,4)):
                expected = type('Encounter',(),dict(entd=entd,weather=weather,night=night))()
                actual = dict(entd=entd,weather=weather,night=night)
                reference(expected);randomize_weather(actual,port_rng)
                self.assertEqual((actual['weather'],actual['night']),(expected.weather,expected.night))
                self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_warjilis_table_body_matches_literal_source_and_rng(self):
        class DummyFile:
            def seek(self,*args): pass
            def write(self,*args): pass
            def close(self): pass
        for seed,monsters in ((89,False),(321,True)):
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            expected,actual = copy.deepcopy(self.before),copy.deepcopy(self.before)
            source_world = SurpriseWorld(self.before,expected,source_rng)
            port_world = SurpriseWorld(self.before,actual,port_rng)
            source_world.env.update(open=lambda *args:DummyFile(),
                                    range=lambda *args:list(range(*args)))
            reference = reference_function('restore_warjilis',source_world.env)
            port = compile_restore_warjilis(port_world.env)
            reference('unused',before=171,new_entd=476,map_id=42,monsters=monsters)
            port(before=171,new_entd=476,map_id=42,monsters=monsters)
            self.assertEqual(actual['_RCCUnitContext'],expected['_RCCUnitContext'])
            self.assertEqual(actual['_RCCEncounters'],expected['_RCCEncounters'])
            self.assertEqual(actual['_RCCFormations'],expected['_RCCFormations'])
            self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_full_invite_adapts_typed_menu_and_preserves_passives(self):
        result = copy.deepcopy(self.before)
        for command in (7,9,10,11,12,13,14,15,16,22):
            for field in ACTION_FIELDS:
                if result['JobCommandData'][command][field]==116:
                    result['JobCommandData'][command][field] = 0
        result['CommandTypeData'][27]['Menu'] = 9
        passives = {f:result['JobCommandData'][27][f] for f in RSM_FIELDS}
        result['_RCCAbilityAudit'] = dict(selected_owners=[dict(table='JobCommandData',id=27,menu=9)])
        audit = guarantee_invite(self.before,result,89,'z')
        self.assertTrue(audit['full_menu_adapted'])
        self.assertEqual(result['CommandTypeData'][27]['Menu'],0)
        self.assertIn(116,[result['JobCommandData'][27][f] for f in ACTION_FIELDS])
        self.assertEqual(passives,{f:result['JobCommandData'][27][f] for f in RSM_FIELDS})
        self.assertEqual(result['_RCCAbilityAudit']['selected_owners'][0]['menu'],0)

    def test_alma_math_fix_copies_native_job_unlock_and_command(self):
        result = copy.deepcopy(self.before)
        result['_RCCUnitContext'][441,8].update(SecondarySkillset=21,JobUnlock=16,JobLevel=8)
        self.assertEqual(apply_alma_math_cleanup(self.before,result)['changed_units'],2)
        for owner in ((420,0),(441,2)):
            self.assertEqual([result['_RCCUnitContext'][owner][f] for f in ('SecondarySkillset','JobUnlock','JobLevel')],[21,16,8])
