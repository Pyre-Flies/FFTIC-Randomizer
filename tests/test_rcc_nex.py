"""Merged Nex baselines, compound-key edits and complete-cell roundtrips."""
import copy
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from fftic.preview import (build_rcc_nex,_apply_sparse_updates,
                           _verify_nex_roundtrip,_table_rows,_apply_battle_inserts)
from fftic.game import read_game
from fftic.catalog import attach_catalog
from fftic.rcc_encounter_data import prepare_unit_context
from fftic.rcc_world_data import prepare_world_data


PROJECT = Path(__file__).resolve().parents[1]


class CompoundNexTests(unittest.TestCase):
    def database(self,path):
        with closing(sqlite3.connect(path)) as con:
            con.execute('CREATE TABLE Sample(Key INTEGER,Key2 INTEGER,Data TEXT,Other TEXT)')
            con.executemany('INSERT INTO Sample VALUES(?,?,?,?)',[(1,0,'[1,2]','first'),(1,1,'[2,3]','second')])
            con.commit()

    def test_exact_compound_key_update_and_array_roundtrip(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            baseline,edited,rebuilt = (root/(name+'.sqlite') for name in ('base','edited','rebuilt'))
            self.database(baseline)
            shutil.copyfile(baseline,edited)
            allowed = {}
            with closing(sqlite3.connect(edited)) as con:
                _apply_sparse_updates(con,'Sample',{(1,0):{'Data':[3,4]}},{'Data'},allowed)
                con.commit()
                self.assertEqual(con.execute('SELECT Data FROM Sample WHERE Key2=1').fetchone()[0],'[2,3]')
            shutil.copyfile(edited,rebuilt)
            with closing(sqlite3.connect(rebuilt)) as con:
                con.execute('UPDATE Sample SET Data=? WHERE Key=1 AND Key2=0',('[3, 4]',))
                con.commit()
            self.assertEqual(_verify_nex_roundtrip(baseline,edited,rebuilt,['Sample'],allowed),1)
            with closing(sqlite3.connect(rebuilt)) as con:
                con.execute('DELETE FROM Sample WHERE Key2=1')
                con.commit()
            with self.assertRaisesRegex(ValueError,'inventory'):
                _verify_nex_roundtrip(baseline,edited,rebuilt,['Sample'],allowed)

    def test_unrelated_column_or_compound_owner_is_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            baseline,edited,rebuilt = (root/(name+'.sqlite') for name in ('base','edited','rebuilt'))
            self.database(baseline)
            shutil.copyfile(baseline,edited)
            allowed = {}
            with closing(sqlite3.connect(edited)) as con:
                with self.assertRaisesRegex(ValueError,'columns'):
                    _apply_sparse_updates(con,'Sample',{(1,0):{'Other':'bad'}},{'Data'},allowed)
                with self.assertRaisesRegex(ValueError,'compound'):
                    _apply_sparse_updates(con,'Sample',{1:{'Data':[3]}},{'Data'},allowed)
                with self.assertRaisesRegex(ValueError,'Missing'):
                    _apply_sparse_updates(con,'Sample',{(1,99):{'Data':[3]}},{'Data'},allowed)
                con.execute('UPDATE Sample SET Other=? WHERE Key2=1',('unrelated',))
                con.commit()
            shutil.copyfile(edited,rebuilt)
            with self.assertRaisesRegex(ValueError,'Unrelated'):
                _verify_nex_roundtrip(baseline,edited,rebuilt,['Sample'],allowed)

    def test_battle_insert_accepts_only_verified_complete_new_templates(self):
        with closing(sqlite3.connect(':memory:')) as con:
            con.execute('CREATE TABLE Battle(Key INTEGER,DLCFlags INTEGER)')
            con.execute('INSERT INTO Battle VALUES(10,0)')
            before = {'_RCCEncounters':{0:dict(scenario=743)}}
            for updates in ({743:dict(Key=743,DLCFlags=0)},
                            {744:dict(Key=744,DLCFlags=1)},
                            {744:dict(Key=744)},
                            {10:dict(Key=10,DLCFlags=0)}):
                with self.assertRaises(ValueError):
                    _apply_battle_inserts(con,updates,before,{})
            allowed = {}
            inserts = _apply_battle_inserts(con,{744:dict(Key=744,DLCFlags=0)},before,allowed)
            self.assertEqual(inserts,{(744,):dict(Key=744,DLCFlags=0)})
            self.assertEqual(allowed,{'Battle':{(744,):{'Key','DLCFlags'}}})


@unittest.skipUnless((PROJECT.parent/'FFT_enhanced.exe').is_file(), 'Requires verified local Enhanced inputs')
class RCCMergedNexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before,_ = read_game(PROJECT.parent)
        attach_catalog(cls.before,PROJECT.parent,PROJECT)
        prepare_unit_context(cls.before,PROJECT.parent,PROJECT)
        prepare_world_data(cls.before,PROJECT.parent,PROJECT)

    def test_real_converter_merges_all_families_preserving_every_other_cell(self):
        before = self.before
        after = copy.deepcopy(before)
        after['_RCCStatAudit'] = dict(jp_cost_updates={1:300})
        after['_RCCMetadataUpdates'] = {1:dict(JPCost=450,LearnChance=42)}
        after['_RCCActionAudit'] = dict(action_updates={1:dict(CT=10,InflictStatus=22,Flags12=[4,0])})
        after['_RCCStatusAudit'] = dict(action_updates={1:dict(InflictStatus=29)})
        after['_RCCAbilityAudit'] = dict(selected_owners=[dict(table='JobCommandData',id=8,menu=3)])
        levels = json.loads(before['_RCCGeneralJobs'][0]['RequiredJobExp']) if isinstance(before['_RCCGeneralJobs'][0]['RequiredJobExp'],str) else list(before['_RCCGeneralJobs'][0]['RequiredJobExp'])
        levels[-1] += 30
        after['_RCCWorldNexUpdates'] = {'GeneralJob':{(0,):dict(RequiredJobExp=levels)}}
        for table,rows in before['_RCCPoachNexTables'].items():
            key = min(rows)
            after['_RCCWorldNexUpdates'][table] = {(key,):dict(Unknown2C=8)}
        after['_RCCEntryNexUpdates'] = {(387,0):dict(Reaction=437,InitialDirection=3,HigherElevation=1)}
        after['_RCCWorldNexInserts'] = {'Battle':{744:dict(Key=744,DLCFlags=0),745:dict(Key=745,DLCFlags=0)}}
        with tempfile.TemporaryDirectory(dir=PROJECT/'research') as scratch:
            stage = Path(scratch)
            report = build_rcc_nex(PROJECT.parent,PROJECT,stage,stage/'mod',before,after,'nex-reference',ability_mode='full')
            self.assertEqual(report['roundtrip'],'exact rows and cells matched')
            self.assertEqual(report['jp_cost_updates'][1],450)
            self.assertEqual(report['action_updates'][1]['InflictStatus'],29)
            self.assertEqual(len(report['tables']),25)
            self.assertEqual({row['kind'] for row in report['merged_sources']},{'world','unit context'})
            json.dumps(report)  # Compound keys must be represented as lists in reports.
            with closing(sqlite3.connect(stage/'nex-work/rebuilt.sqlite')) as con, closing(sqlite3.connect(stage/'nex-work/combined-baseline.sqlite')) as original:
                self.assertEqual(con.execute('SELECT JpCost1,JpCost2 FROM "Ability-en" WHERE Key=1').fetchone(),(194,1))
                self.assertEqual(con.execute('SELECT CT,InflictStatus,Flags12 FROM OverrideAbilityActionData WHERE Key=1').fetchone(),(10,29,'[4,0]'))
                self.assertEqual(json.loads(con.execute('SELECT RequiredJobExp FROM GeneralJob WHERE Key=0').fetchone()[0]),levels)
                self.assertEqual(con.execute('SELECT Reaction,InitialDirection,HigherElevation FROM OverrideEntryData WHERE Key=387 AND Key2=0').fetchone(),(437,3,1))
                self.assertEqual(con.execute('SELECT * FROM OverrideEntryData WHERE Key=387 AND Key2=1').fetchone(),
                                 original.execute('SELECT * FROM OverrideEntryData WHERE Key=387 AND Key2=1').fetchone())
                expected_name = original.execute('SELECT Name FROM "JobCommand-en" WHERE Key=21').fetchone()[0]
                self.assertEqual(con.execute('SELECT Name FROM "JobCommand-en" WHERE Key=8').fetchone()[0],expected_name)
                for table in report['tables']:
                    extra = {(744,),(745,)} if table=='Battle' else set()
                    self.assertEqual(set(_table_rows(con,table)[2]),set(_table_rows(original,table)[2])|extra)
                self.assertEqual(con.execute('SELECT Key,DLCFlags FROM Battle WHERE Key>=744 ORDER BY Key').fetchall(),[(744,0),(745,0)])
                self.assertEqual(report['inserted_rows'],[dict(table='Battle',key=[744],fields=dict(Key=744,DLCFlags=0)),
                                                         dict(table='Battle',key=[745],fields=dict(Key=745,DLCFlags=0))])


if __name__ == '__main__':
    unittest.main()
