"""Authored conditional deltas, Enhanced route preservation and Nex roundtrip."""
import copy
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from fftic.rcc_conditionals import (TABLES,PRIVATE_ROWS,load_deltas,decode_table,
    group_native_rows,native_battle_op,native_world_op,encode_op,
    build_conditional_plan,apply_conditionals,validate_replacements)
from fftic.rcc_world_data import prepare_world_data
from fftic.preview import (build_rcc_nex,_apply_conditional_replacements,
                            _verify_nex_roundtrip,_table_rows)


PROJECT = Path(__file__).resolve().parents[1]
SOURCE = Path('I:/rumble_chaos_crashdown')
LEGAL_ASSETS = PROJECT/'research/rcc-script-assets/fftpack'


def fixture():
    controls = {unit if unit else 256:dict(Unknown8=unit) for unit in range(256)}
    before = {'_RCCCharaControls':controls}
    for family,private in PRIVATE_ROWS.items():
        rows = {}
        for raw_key,delta in load_deltas()['families'][family]['changed_groups'].items():
            for clause,program in enumerate(delta['before']):
                for index,op in enumerate(program):
                    key = (int(raw_key),clause,index)
                    rows[key] = encode_op(op,family,key,controls)
        before[private] = rows
    return before


def semantic(tables,family):
    decoder = (lambda row:native_battle_op(row,tables['_RCCCharaControls'])) if family=='battle' else native_world_op
    groups = group_native_rows(tables[PRIVATE_ROWS[family]])
    result = {}
    for (key,clause),rows in groups.items():
        result.setdefault(key,[]).append([decoder(row) for row in rows])
    return result


class AuthoredConditionalTests(unittest.TestCase):
    def test_source_exact_fixture_matches_every_authored_program(self):
        before = fixture()
        after = copy.deepcopy(before)
        audit = apply_conditionals(before,after,'z')
        for family in TABLES:
            expected = {int(key):delta['after'] for key,delta in load_deltas()['families'][family]['changed_groups'].items()}
            self.assertEqual(semantic(after,family),expected)
        self.assertEqual(audit['families']['battle']['added_clauses'],27)
        self.assertEqual(audit['families']['world']['added_clauses'],6)
        self.assertEqual(before,fixture())
        json.dumps(audit)

    def test_default_world_and_z_battle_scope_and_guarded_plan(self):
        before = fixture()
        after = copy.deepcopy(before)
        apply_conditionals(before,after,'')
        self.assertEqual(after['_RCCBattleConditions'],before['_RCCBattleConditions'])
        self.assertEqual(set(after['_RCCConditionalReplacements']),{'EnhancedWorldEvent'})
        validate_replacements(before,after['_RCCConditionalReplacements'])
        damaged = copy.deepcopy(after['_RCCConditionalReplacements'])
        damaged['EnhancedWorldEvent'][(18,1)]['rows'][0]['Unknown10'] = 777
        with self.assertRaisesRegex(ValueError,'authored'):
            validate_replacements(before,damaged)
        after = copy.deepcopy(before)
        self.assertEqual(apply_conditionals(before,after,'',world=False)['families'],{})
        self.assertNotIn('_RCCConditionalReplacements',after)

    def test_world29_and_nonzero_unit_zero_alias(self):
        controls = {0:dict(Unknown8=0),256:dict(Unknown8=0),1:dict(Unknown8=1)}
        row = encode_op([29,0],'world',(18,0,0),controls)
        self.assertEqual(row['Type'],29)
        self.assertEqual(row['Unknown8'],[0])
        self.assertEqual(native_world_op(row),[29,0])
        row = encode_op([4,0],'battle',(1,0,0),controls)
        self.assertEqual(row['CharaControlId'],256)
        self.assertEqual(native_battle_op(row,controls),[4,0])

    @unittest.skipUnless((SOURCE/'tables/conditionals.dat').is_file() and (LEGAL_ASSETS/'world_wldcore_bin.en.bin').is_file(),'Requires legal source/reference assets')
    def test_bundled_delta_is_the_exact_raw_two_level_source_difference(self):
        for family,path,offset in (('battle',LEGAL_ASSETS/'overlay/event_attack_out.en.bin',0x14938),
                                   ('world',LEGAL_ASSETS/'world_wldcore_bin.en.bin',0x30234)):
            native = path.read_bytes()[offset:]
            modified = (SOURCE/'tables'/('conditionals.dat' if family=='battle' else 'world_conditionals.dat')).read_bytes()
            if len(modified)%2: modified += native[len(modified):len(modified)+1]
            original,target = decode_table(native,family),decode_table(modified,family)
            changes = {str(key):dict(before=original[key],after=target[key]) for key in original if original[key]!=target[key]}
            self.assertEqual(changes,load_deltas()['families'][family]['changed_groups'])
            self.assertEqual(len(original),146 if family=='battle' else 44)
            with self.assertRaisesRegex(ValueError,'TOC'):
                decode_table(b'\x03\x00'+native[2:],family)


@unittest.skipUnless((PROJECT.parent/'FFT_enhanced.exe').is_file(),'Requires verified local Enhanced inputs')
class EnhancedConditionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = {}
        prepare_world_data(cls.before,PROJECT.parent,PROJECT)

    def test_native_additions_aliases_and_ending_sibling_routes_are_preserved(self):
        before = self.before
        after = copy.deepcopy(before)
        audit = apply_conditionals(before,after,'z')
        self.assertEqual(audit['families']['battle']['replaced_clauses'],162)
        self.assertEqual(audit['families']['battle']['added_clauses'],27)
        self.assertEqual(audit['families']['world']['replaced_clauses'],1)
        self.assertEqual(audit['families']['world']['added_clauses'],6)
        changes = after['_RCCConditionalReplacements']
        for family,table in TABLES.items():
            touched = set(changes[table])
            old = group_native_rows(before[PRIVATE_ROWS[family]])
            new = group_native_rows(after[PRIVATE_ROWS[family]])
            for key,rows in old.items():
                if key not in touched: self.assertEqual(new[key],rows)
            # No new first-level key may replace added Enhanced content.
            self.assertEqual({key[0] for key in new},{key[0] for key in old})
        old,new = semantic(before,'battle'),semantic(after,'battle')
        self.assertEqual(new[70][:3],old[70][:3])  # modern opcode39 initializer routes.
        for clause in new[144][1:5]:
            self.assertNotIn([1,509,0],clause)
        self.assertEqual(new[144][2][-3:],[[33,31],[33,72],[25,487]])
        self.assertEqual(new[144][3][-2:],[[34,31],[25,491]])
        self.assertEqual(new[144][4][-2:],[[34,72],[25,491]])
        for clause in (1,2,3,4):
            original_aliases = [row['CharaControlId'] for row in group_native_rows(before['_RCCBattleConditions'])[(144,clause)] if row['CharaControlId']]
            new_aliases = [row['CharaControlId'] for row in group_native_rows(after['_RCCBattleConditions'])[(144,clause)] if row['CharaControlId']]
            self.assertEqual(new_aliases,original_aliases)
        # Added Enhanced HP/death dialogues retain their own conditions.
        self.assertIn([8,133,95],new[15][4])
        self.assertEqual(new[15][4],old[15][4])
        old_world,new_world = semantic(before,'world'),semantic(after,'world')
        self.assertEqual(new_world[1][:14],old_world[1])
        self.assertEqual(new_world[18][:2],old_world[18][:2])
        self.assertEqual(new_world[18][2],[[1,110,53],[25,301,2]])
        self.assertEqual(new_world[18][-1],[[1,110,58],[26,55,322,0,0,0,0,0,0]])

    def test_converter_roundtrip_checks_all_compound_rows_and_rejects_unrelated_edits(self):
        before = self.before
        after = copy.deepcopy(before)
        apply_conditionals(before,after,'z')
        after['_RCCAbilityAudit'] = {}
        with tempfile.TemporaryDirectory(dir=PROJECT/'research') as scratch:
            root = Path(scratch)
            report = build_rcc_nex(PROJECT.parent,PROJECT,root,root/'mod',before,after,'conditional-reference')
            self.assertEqual(set(report['tables']),set(TABLES.values()))
            self.assertEqual(report['roundtrip'],'exact rows and cells matched')
            self.assertEqual(len(report['conditional_groups']),196)
            json.dumps(report)
            combined,edited,rebuilt = (root/'nex-work'/name for name in ('combined-baseline.sqlite','edited.sqlite','rebuilt.sqlite'))
            with closing(sqlite3.connect(combined)) as con, closing(sqlite3.connect(rebuilt)) as actual:
                self.assertEqual(len(_table_rows(actual,'EnhancedBattleEvent')[2]),2061)
                self.assertEqual(len(_table_rows(actual,'EnhancedWorldEvent')[2]),552)
                # All new Enhanced first-level tables survive exactly.
                for table,bound in (('EnhancedBattleEvent',146),('EnhancedWorldEvent',44)):
                    query = 'SELECT * FROM '+table+' WHERE Key>=? ORDER BY Key,Key2,Key3'
                    self.assertEqual(actual.execute(query,(bound,)).fetchall(),con.execute(query,(bound,)).fetchall())
            allowed = {}
            with closing(sqlite3.connect(':memory:')) as con:
                # A plan may not fabricate even one complete conditional row.
                bad = copy.deepcopy(after['_RCCConditionalReplacements'])
                bad['EnhancedWorldEvent'][(1,14)]['rows'][0]['Unknown10'] = 111
                with self.assertRaisesRegex(ValueError,'authored'):
                    _apply_conditional_replacements(con,bad,before,allowed)


if __name__=='__main__': unittest.main()
