"""Literal UnitObject reference comparisons and complete native-byte coverage."""
import ast
import copy
from pathlib import Path
import random
import unittest

from fftic.game import read_game
from fftic.catalog import attach_catalog
from fftic.rcc_encounter_data import (decode_entry,encode_entry,prepare_unit_context,
                                    emit_changed_entries,ENTRY_ASSETS)
from fftic.rcc_units import NativeUnit,UnitEngine,native_rankings,apply_units
from test_rcc_reference import SOURCE,source_function,reference_environment


def source_method(name, environment):
    tree = source_function('randomizer.py',name,owner='UnitObject')
    # Python 2's division of integer operands in these literal unit methods.
    class IntegerDivision(ast.NodeTransformer):
        def visit_BinOp(self,node):
            self.generic_visit(node)
            if isinstance(node.op,ast.Div): node.op = ast.FloorDiv()
            return node
    tree = IntegerDivision().visit(tree)
    ast.fix_missing_locations(tree)
    exec(compile(tree,'<RCC UnitObject reference>','exec'),environment)
    return environment[name]


class NativeEntryTests(unittest.TestCase):
    def test_every_byte_survives_decode_encode_and_copy(self):
        raw = bytes(range(40))
        row = decode_entry(raw)
        self.assertEqual(encode_entry(raw,row),raw)
        self.assertEqual(row['Unknown33'],int.from_bytes(raw[33:35],'little'))
        self.assertEqual(row['Unknown37'],int.from_bytes(raw[37:40],'little'))
        engine = type('Engine',(),{'backups':{}})()
        donor,recipient = NativeUnit(engine,(512,0),row),NativeUnit(engine,(513,1),decode_entry(bytes(40)))
        recipient.copy_data(donor)
        self.assertEqual(encode_entry(bytes(40),recipient.row),raw)
        self.assertEqual(recipient.index,513*16+1)
        recipient.unknown2 = 0xABCD
        self.assertEqual((recipient.row['Unknown28'],recipient.row['EntryUnknown1D']),(0xCD,0xAB))

    def test_additional_asset_uses_its_actual_archive_path(self):
        blocks = {5:bytes(77*16*40)}
        row = decode_entry(bytes(40))
        original = {(519,1):row}
        desired = copy.deepcopy(original)
        desired[519,1]['MainJob'] = 77
        assets,nex,changes = emit_changed_entries(original,desired,blocks)
        self.assertEqual(set(assets),{ENTRY_ASSETS[5]})
        self.assertEqual(assets[ENTRY_ASSETS[5]][7*640+40+10],77)
        self.assertEqual(nex,{})


PROJECT = Path(__file__).resolve().parents[1]
@unittest.skipUnless((SOURCE/'randomizer.py').exists() and (PROJECT.parent/'FFT_enhanced.exe').exists(),
                     'Requires supplied RCC checkout and verified local Enhanced inputs')
class RCCUnitReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before,_ = read_game(PROJECT.parent)
        attach_catalog(cls.before,PROJECT.parent,PROJECT)
        prepare_unit_context(cls.before,PROJECT.parent,PROJECT)
        native_rankings(cls.before)

    def engines(self,seed):
        source_rng,port_rng = random.Random(seed),random.Random(seed)
        source_tables,port_tables = copy.deepcopy(self.before),copy.deepcopy(self.before)
        expected = UnitEngine(self.before,source_tables,source_rng)
        actual = UnitEngine(self.before,port_tables,port_rng)
        environment = reference_environment(source_rng)
        for name in ('JOBNAMES','JOBLEVEL_JP','DAYS_IN_MONTH','boostd','birthday_dict',
                     'SUPER_LEVEL_BOOSTED','JobObject','SkillsetObject','ItemObject',
                     'AbilityObject','JobReqObject','jobreq_indexdict','jobreq_namedict',
                     'BANNED_ITEMS','MUTATED_SKILLSETS','calculate_jp_total','get_job',
                     'get_skillset','get_ranked_secondaries','get_similar_item'):
            environment[name] = getattr(expected,name)
        environment['mutate_index'] = expected.mutate_index
        return expected,actual,environment,source_rng,port_rng

    def test_statistics_birthdays_and_normalized_levels_match_literal_source(self):
        for seed in range(8):
            expected,actual,environment,source_rng,port_rng = self.engines(seed)
            class SourceUnit(NativeUnit): pass
            SourceUnit.mutate_level = source_method('mutate_level',environment)
            SourceUnit.mutate_stats = source_method('mutate_stats',environment)
            for owner in ((0,1),(387,0),(387,3),(441,8),(519,1)):
                source = SourceUnit(expected,owner,expected.tables['_RCCUnitContext'][owner])
                port = NativeUnit(actual,owner,actual.tables['_RCCUnitContext'][owner])
                source.mutate_stats();port.mutate_stats()
                self.assertEqual(port.row,source.row)
                self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_equipment_and_rsm_match_literal_source_and_sentinels(self):
        for seed in range(8):
            expected,actual,environment,source_rng,port_rng = self.engines(seed)
            class SourceUnit(NativeUnit): pass
            for method in ('equip_appropriate_sword','mutate_equips','mutate_rsm'):
                setattr(SourceUnit,method,source_method(method,environment))
            for owner in ((387,0),(387,1),(387,3),(405,1),(441,8)):
                source = SourceUnit(expected,owner,expected.tables['_RCCUnitContext'][owner])
                port = NativeUnit(actual,owner,actual.tables['_RCCUnitContext'][owner])
                source.mutate_equips();port.mutate_equips()
                source.mutate_rsm();port.mutate_rsm()
                self.assertEqual(port.row,source.row)
                self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_progression_and_secondary_match_literal_source(self):
        for seed in range(8):
            expected,actual,environment,source_rng,port_rng = self.engines(seed)
            reference = source_method('mutate_secondary',environment)
            for owner in ((387,0),(387,1),(387,3),(405,1),(441,8)):
                source = NativeUnit(expected,owner,expected.tables['_RCCUnitContext'][owner])
                port = NativeUnit(actual,owner,actual.tables['_RCCUnitContext'][owner])
                reference(source);port.mutate_secondary()
                self.assertEqual(port.row,source.row)
                self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_actual_extra_encounters_and_degree_zero(self):
        tables = copy.deepcopy(self.before)
        self.assertEqual(len(tables['_RCCUnitContext']),589*16)
        original = copy.deepcopy(tables['_RCCUnitContext'])
        apply_units(self.before,tables,89,'u',degree=0)
        self.assertEqual(tables['_RCCUnitContext'],original)
        audit = apply_units(self.before,tables,89,'u')
        self.assertGreater(audit['changed_units'],5000)
        self.assertTrue(any(e>=512 for e,s in audit['units']))
        for row in tables['_RCCUnitContext'].values():
            encode_entry(bytes(40),row)
