import copy
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from fftic.game import ACTION_FIELDS, RSM_FIELDS, JOB_NAMES, decode_commands, read_game, unique_match
from fftic.randomize import randomize, DEFAULT_FLAGS, FLAGS, starter_actions
from fftic.catalog import attach_catalog, pools
from fftic.rcc import apply_abilities, mutate_bits, mutate_normal, rng_for, scopes, _passive_bans
from fftic.rcc_equipment import apply_equipment, BONUS_FIELDS
from fftic.package import create_seed, patch_bytes, XML_TYPES

ROOT=Path(__file__).resolve().parents[1]
GAME=ROOT.parent
RCC=Path('I:/rumble_chaos_crashdown')


def public_tables(tables):
    return {name: rows for name, rows in tables.items() if not name.startswith('_')}


def deterministic_outputs(tables):
    # Execution context can contain random.Random instances and live adapter
    # objects. Compare generated data and audits, not those object identities.
    return {name:rows for name,rows in tables.items()
            if not name.startswith('_') or name.endswith('Audit')
            or name in ('_AbilityMetadata','_AbilityAttributes','_RCCMetadataUpdates','_RCCLastRNGState')}


def values(row, fields):
    return [row[field] for field in fields if row[field]]


class BinaryTests(unittest.TestCase):
    def test_skillset_flags_initialized_before_ability_setters(self):
        row_values=dict.fromkeys(ACTION_FIELDS+RSM_FIELDS,0)
        row_values['AbilityId1']=1
        row_values['ReactionSupportMovementId1']=428
        xml=patch_bytes('JobCommandData',{10:{'AbilityId1':1}},{'JobCommandData':{10:row_values}})
        row=ET.fromstring(xml).find('Entries/JobCommand')
        self.assertEqual([e.tag for e in row[:4]],['Id','ExtendAbilityIdFlagBits','ExtendReactionSupportMovementIdFlagBits','AbilityId1'])
        self.assertEqual(row.findtext('ExtendAbilityIdFlagBits'),'0')
        self.assertEqual(row.findtext('ExtendReactionSupportMovementIdFlagBits'),'0')

    def test_extended_ids_use_reverse_bits_per_byte(self):
        row=bytearray(25)
        row[0],row[1],row[2]=0x81,0x80,0x84
        row[3:19]=bytes(range(16))
        row[19:25]=bytes(range(6))
        result=decode_commands(bytes(row),1)[0]
        self.assertEqual([result[ACTION_FIELDS[i]] for i in (0,1,7,8,15)],[256,1,263,264,15])
        self.assertEqual([result[f] for f in RSM_FIELDS],[256,1,2,3,4,261])

    def test_ambiguous_and_missing_signatures_rejected(self):
        for content in (b'not present',b'same same'):
            with self.assertRaises(ValueError): unique_match(content,b'same')

    def test_rcc_normal_and_bits_respect_native_bounds(self):
        for seed in range(20):
            for degree in (0,.25,.5,1):
                for base in (0,1,127,253):
                    result=mutate_normal(base,0,253,random.Random(seed),random_degree=degree)
                    self.assertTrue(0<=result<=253)
                    if degree==0: self.assertEqual(result,base)
            for mask in (0,0xFFFFFFFF,0xD04006FF):
                self.assertTrue(0<=mutate_bits(mask,random.Random(seed),size=32)<=0xFFFFFFFF)
        with self.assertRaises(ValueError): mutate_bits(1<<32,random.Random(0),size=32)


@unittest.skipUnless((GAME/'FFT_enhanced.exe').exists(),'Requires a local legally owned game installation')
class InstalledGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables,cls.build=read_game(GAME)
        attach_catalog(cls.tables,GAME,ROOT)

    def test_known_rvas_layouts_and_job_relationships(self):
        self.assertEqual(self.build['tables']['JobData']['rva'],'0x785E30')
        self.assertEqual(self.build['tables']['JobCommandData']['rva'],'0x67E210')
        self.assertEqual(len(self.tables['JobData']),174)
        self.assertEqual(len(self.tables['JobCommandData']),179)
        self.assertEqual(len(self.tables['MonsterJobCommandData']),48)
        self.assertEqual(len(self.tables['ItemConsumableData']),14)
        self.assertEqual(len(self.tables['ItemEquipBonusData']),85)
        for job in JOB_NAMES: self.assertEqual(self.tables['JobData'][job]['JobCommandId'],job-69)

    def test_determinism_different_seeds_and_no_input_mutation(self):
        original=copy.deepcopy(self.tables)
        first=randomize(self.tables,'same seed','jsmapw')
        self.assertEqual(deterministic_outputs(first),
                         deterministic_outputs(randomize(self.tables,'same seed','wpamsj')))
        self.assertNotEqual(deterministic_outputs(first),
                            deterministic_outputs(randomize(self.tables,'different seed','jsmapw')))
        self.assertEqual(self.tables,original)

    def test_native_menu_parameters_and_mime_are_preserved(self):
        for seed in range(20):
            result=randomize(self.tables,str(seed),'sm')
            self.assertEqual(result['CommandTypeData'],self.tables['CommandTypeData'])
            for command in (6,8,17,18,19,20,21):
                self.assertLessEqual(set(values(result['JobCommandData'][command],ACTION_FIELDS)),
                                     set(values(self.tables['JobCommandData'][command],ACTION_FIELDS)))
            self.assertEqual(result['JobCommandData'][24],self.tables['JobCommandData'][24])

    def test_disabled_scopes_and_shared_native_command_ownership(self):
        ordinary,unique,creatures=scopes(self.tables)
        self.assertEqual(len(ordinary),20)
        self.assertFalse(ordinary&unique)
        self.assertFalse((ordinary|unique)&creatures)
        for flag,enabled in (('s',ordinary|unique),('m',creatures)):
            result=randomize(self.tables,'scopes',flag)
            for command,row in self.tables['JobCommandData'].items():
                if command not in enabled: self.assertEqual(result['JobCommandData'][command],row)
            if flag!='m': self.assertEqual(result['MonsterJobCommandData'],self.tables['MonsterJobCommandData'])
        self.assertEqual(self.tables['JobData'][76]['JobCommandId'],7)
        self.assertEqual(self.tables['JobData'][53]['JobCommandId'],self.tables['JobData'][75]['JobCommandId'])
        self.assertEqual({self.tables['JobData'][j]['JobCommandId'] for j in (1,2,3,4)},{25,26,27,28})
        for job in (60,72,144,145,150,151,153,154):
            self.assertIn(self.tables['JobData'][job]['JobCommandId'],creatures)

    def test_all_feature_defaults_and_s_covers_unique_jobs(self):
        ordinary,unique,creatures=scopes(self.tables)
        self.assertEqual(DEFAULT_FLAGS,'risayjmuzftpwc')
        self.assertEqual(set(DEFAULT_FLAGS),set(FLAGS)-{'o','b'})
        self.assertEqual(len(DEFAULT_FLAGS),len(set(DEFAULT_FLAGS)))
        for mode in ('rcc','full'):
            result=randomize(self.tables,'scopes','s',ability_mode=mode)
            changed={c for c,row in self.tables['JobCommandData'].items()
                     if row!=result['JobCommandData'][c]}
            self.assertTrue(changed&ordinary)
            self.assertTrue(changed&unique)
            self.assertFalse(changed&creatures)
            disabled=randomize(self.tables,'scopes','j',ability_mode=mode)
            self.assertEqual(disabled['JobCommandData'],self.tables['JobCommandData'])

    def test_prepared_u_randomizes_units_in_both_ability_modes(self):
        from fftic.rcc_encounter_data import prepare_unit_context, get_flag
        from fftic.rcc_world_data import prepare_world_data
        prepared=copy.deepcopy(self.tables)
        prepare_unit_context(prepared,GAME,ROOT)
        prepare_world_data(prepared,GAME,ROOT)
        snapshot=copy.deepcopy(prepared)
        results=[]
        for mode in ('rcc','full'):
            result=randomize(prepared,'units-orchestration','u',ability_mode=mode)
            self.assertGreater(result['_RCCUnitAudit']['changed_units'],0)
            self.assertGreater(result['_RCCUnitAudit']['changed_fields'],0)
            self.assertEqual(result['JobCommandData'],prepared['JobCommandData'])
            self.assertEqual(result['MonsterJobCommandData'],prepared['MonsterJobCommandData'])
            # Unconditional RCC cleanup makes opening allies controllable.
            allies=[row for owner,row in result['_RCCUnitContext'].items()
                    if owner[0]==387 and not get_flag(row,'enemy_team')]
            self.assertTrue(allies)
            self.assertTrue(all(get_flag(row,'control') for row in allies))
            results.append(result['_RCCUnitContext'])
        self.assertEqual(results[0],results[1])
        self.assertEqual(prepared,snapshot)

    def test_complete_catalog_actor_pools_and_explicit_shared_ids(self):
        catalog=self.tables['_AbilityCatalog']
        eligible={a for a,r in catalog.items() if r['eligible']}
        player={a for ids in pools(self.tables,'player').values() for a in ids}
        monster={a for ids in pools(self.tables,'monster').values() for a in ids}
        shared={a for a,r in catalog.items() if r['eligible'] and r.get('domain')=='both'}
        self.assertEqual(len(catalog),512)
        self.assertEqual(len(eligible),487)
        self.assertEqual(player|monster,eligible)
        self.assertEqual(player&monster,shared)
        for name in ('Ultima','Zodiark'):
            matching=[a for a,r in catalog.items() if r['eligible'] and r['name']==name]
            self.assertTrue(matching,name)
            self.assertTrue(any(a in shared for a in matching),name)
        for a in (267,330,332,333,334,337,338,339): self.assertIn(a,monster)
        for a in (155,422,463,507): self.assertIn(a,player)
        for a in (0,40,184,443,508,510,511): self.assertFalse(catalog[a]['eligible'])
        with self.assertRaises(ValueError): pools(self.tables,'unknown')

    def test_passive_exclusions_match_rcc_numeric_list(self):
        # The source list is numeric. Similar localized names in FFTIC must
        # not add exclusions that were absent from RCC's initialization.
        expected={0x1BB,0x1D7,0x1E1,0x1E4,0x1E5,0x1F1}
        self.assertEqual(_passive_bans(self.tables['_AbilityCatalog']),expected)
        self.assertFalse({473,478,509}&expected)

    def test_excluded_native_entries_never_spread_to_new_skillsets(self):
        catalog=self.tables['_AbilityCatalog']
        excluded={a for a,row in catalog.items() if not row['eligible']}
        original_excluded={
            (table,command):set(row.values())&excluded-{0}
            for table in ('JobCommandData','MonsterJobCommandData')
            for command,row in self.tables[table].items()
        }
        # These positive-JP WOTL leftovers were entering the exchange pool
        # through original command rows even though the full catalog excluded
        # them. They may stay on their original owner but cannot be donated.
        self.assertTrue(any(ids for ids in original_excluded.values()))
        self.assertTrue(any(original_excluded['JobCommandData',c] for c in (224,225)))
        for seed in ['89f597b5']+[str(i) for i in range(40)]:
            result=copy.deepcopy(self.tables)
            apply_abilities(self.tables,result,seed,'sm')
            for table in ('JobCommandData','MonsterJobCommandData'):
                for command,row in result[table].items():
                    introduced=(set(row.values())&excluded-{0})-original_excluded[table,command]
                    self.assertFalse(introduced,(seed,table,command,introduced))

    def test_disabled_ability_phase_preserves_original_excluded_entries(self):
        # A cleanup filter must act on candidates, not erase native command
        # contents while the ability phase is disabled or has degree zero.
        for flags,degree in (('',1),('sm',0)):
            result=copy.deepcopy(self.tables)
            apply_abilities(self.tables,result,'retain-native',flags,degree=degree)
            self.assertEqual(result,self.tables)

    def test_rcc_skillset_capacity_monster_fourth_slot_and_reuse_policy(self):
        catalog=self.tables['_AbilityCatalog']
        original=copy.deepcopy(self.tables)
        observed_counts=set()
        for seed in range(40):
            result=copy.deepcopy(self.tables)
            audit=apply_abilities(self.tables,result,str(seed),'sm')
            self.assertIn('exchange',audit['engine'].casefold())
            self.assertIn('reusable',audit['rcc_reuse_policy'])
            for row in result['JobCommandData'].values():
                actions,passives=values(row,ACTION_FIELDS),values(row,RSM_FIELDS)
                self.assertLessEqual(len(actions),16)
                self.assertLessEqual(len(passives),6)
                self.assertTrue(all(catalog[a]['native_type']<=6 for a in actions))
                self.assertTrue(all(catalog[a]['native_type'] in (7,8,9) for a in passives))
                observed_counts.add(len(actions))
            for row in result['MonsterJobCommandData'].values():
                self.assertTrue(row['AbilityId1'])
                self.assertTrue(row['AbilityId4'])
                normal=values(row,ACTION_FIELDS[:3])
                self.assertEqual(len(normal),len(set(normal)))
            self.assertEqual(result['CommandTypeData'],self.tables['CommandTypeData'])
            self.assertEqual(result['JobData'],self.tables['JobData'])
        self.assertGreater(len(observed_counts),6)
        self.assertEqual(self.tables,original)

    def test_generic_passive_done_pool_before_rare_injections(self):
        ordinary,_,_=scopes(self.tables)
        thief=self.tables['JobData'][83]['JobCommandId']
        for seed in range(10):
            result=copy.deepcopy(self.tables)
            # Isolate the consumed generic-passive phase. RCC intentionally
            # allows rare later injections and the Thief exhaustion fallback.
            with patch('fftic.rcc._chance',return_value=False):
                apply_abilities(self.tables,result,str(seed),'s')
            assigned=[a for c in ordinary-{thief} for a in values(result['JobCommandData'][c],RSM_FIELDS)]
            self.assertEqual(len(assigned),len(set(assigned)))
            poach=[a for a,r in self.tables['_AbilityCatalog'].items() if r['name'].casefold()=='poach']
            self.assertEqual(len(poach),1)
            self.assertEqual(result['JobCommandData'][thief][RSM_FIELDS[3]],poach[0])

    def test_zero_ability_degree_and_free_costs_do_not_replace_skillsets(self):
        zero=randomize(self.tables,'zero','sm',skill_degree=0)
        for table in ('JobCommandData','MonsterJobCommandData','CommandTypeData'):
            self.assertEqual(zero[table],self.tables[table])
        self.assertEqual(public_tables(randomize(self.tables,'free','smb')),public_tables(randomize(self.tables,'free','sm')))
        for a in starter_actions('free',self.tables): self.assertIn(a,pools(self.tables,'player')[1])
        for degree in (.25,.5,1):
            result=copy.deepcopy(self.tables)
            audit=apply_abilities(self.tables,result,'partial','sm',degree=degree)
            self.assertIn('jp_cost_updates',audit)
            for row in result['JobCommandData'].values():
                self.assertLessEqual(len(values(row,ACTION_FIELDS)),16)
                self.assertLessEqual(len(values(row,RSM_FIELDS)),6)

    def test_equipment_bounds_sentinels_and_independent_phase_streams(self):
        original=copy.deepcopy(self.tables)
        for seed in range(40):
            result=copy.deepcopy(self.tables)
            audit=apply_equipment(self.tables,result,str(seed),'wpyi')
            self.assertEqual(audit['random_degree'],.25)
            for i,row in result['ItemWeaponData'].items():
                self.assertTrue(all(0<=v<=255 for v in row.values()))
                if self.tables['ItemWeaponData'][i]['Range']: self.assertGreater(row['Range'],0)
                if row['Formula']==2 and row['OptionsAbilityId']!=self.tables['ItemWeaponData'][i]['OptionsAbilityId']:
                    self.assertTrue(1<=row['OptionsAbilityId']<=255)
                    self.assertNotIn(row['OptionsAbilityId'],(40,45,184,219,220))
            for i,row in result['JobData'].items():
                self.assertEqual(row['EquippableItems']&255,self.tables['JobData'][i]['EquippableItems']&255)
            for i in (254,255): self.assertEqual(result['ItemData'][i],self.tables['ItemData'][i])
            for i in (0,79,80,81,82,83,84):
                self.assertEqual(result['ItemEquipBonusData'][i],self.tables['ItemEquipBonusData'][i])
            for i,field in zip(range(74,79),BONUS_FIELDS): self.assertEqual(result['ItemEquipBonusData'][i][field],1)
            for i,row in result['ItemData'].items():
                self.assertTrue(0<=row['Price']<=65000)
                self.assertEqual(row['AdditionalDataId'],self.tables['ItemData'][i]['AdditionalDataId'])
                self.assertEqual(row['ItemCategory'],self.tables['ItemData'][i]['ItemCategory'])
                self.assertIn(row['TypeFlags']^self.tables['ItemData'][i]['TypeFlags'],(0,2))
                if self.tables['ItemData'][i]['ShopAvailability'] not in range(1,17):
                    self.assertEqual(row['ShopAvailability'],self.tables['ItemData'][i]['ShopAvailability'])
        self.assertEqual(self.tables,original)
        unchanged=copy.deepcopy(self.tables)
        apply_equipment(self.tables,unchanged,'zero','wpyi',degree=0)
        self.assertEqual(unchanged,self.tables)
        weapon_only,combined=copy.deepcopy(self.tables),copy.deepcopy(self.tables)
        apply_equipment(self.tables,weapon_only,'independent','w')
        apply_equipment(self.tables,combined,'independent','wp')
        for table in ('ItemWeaponData','ItemShieldData','ItemArmorData','ItemAccessoryData','ItemConsumableData','ItemEquipBonusData'):
            self.assertEqual(weapon_only[table],combined[table])
        for i in self.tables['ItemData']:
            self.assertEqual(weapon_only['ItemData'][i]['EquipBonusId'],combined['ItemData'][i]['EquipBonusId'])

    @unittest.skipUnless((RCC/'randomizer.py').exists(),'Requires original RCC checkout')
    def test_equipment_phase_matches_original_rcc_source_methods(self):
        source=(RCC/'randomizer.py').read_text()
        names=('WeaponObject','ShieldObject','ArmorObject','AccessoryObject','ChemistItemObject','ItemAttributesObject','ItemObject')
        selected='\n\n'.join(source[source.index('class '+name+'('):source.find('\nclass ',source.index('class '+name+'(')+1)] for name in names)
        mapping={
            'ItemWeaponData':('WeaponObject',{'Range':'range','Power':'weapon_power','Evasion':'evade','Formula':'formula','OptionsAbilityId':'inflict_status'}),
            'ItemShieldData':('ShieldObject',{'PhysicalEvasion':'physical_evade','MagicalEvasion':'magic_evade'}),
            'ItemArmorData':('ArmorObject',{'HPBonus':'hp_bonus','MPBonus':'mp_bonus'}),
            'ItemAccessoryData':('AccessoryObject',{'PhysicalEvasion':'physical_evade','MagicalEvasion':'magic_evade'}),
            'ItemConsumableData':('ChemistItemObject',{'Z':'zval'}),
            'ItemEquipBonusData':('ItemAttributesObject',dict(zip(BONUS_FIELDS,('pa','ma','speed','move','jump')))),
        }
        for seed in range(10):
            rng=rng_for(str(seed),'equipment-w')
            namespace={'TableObject':object,'random':rng,'randint':rng.randint,
                       'mutate_normal':lambda base,minimum,maximum:mutate_normal(base,minimum,maximum,rng)}
            exec(selected,namespace)
            expected=copy.deepcopy(self.tables)
            for table,(name,fields) in mapping.items():
                for i,row in expected[table].items():
                    model=namespace[name]()
                    model.index=i
                    for field,attribute in fields.items(): setattr(model,attribute,row[field])
                    model.mutate()
                    for field,attribute in fields.items(): row[field]=getattr(model,attribute)
            for i,row in expected['ItemData'].items():
                if i>=254: continue
                model=namespace['ItemObject']()
                model.index,model.attributes=i,row['EquipBonusId']
                model.mutate_attributes()
                row['EquipBonusId']=model.attributes
            actual=copy.deepcopy(self.tables)
            apply_equipment(self.tables,actual,str(seed),'w')
            for table in (*mapping,'ItemData'): self.assertEqual(actual[table],expected[table],(seed,table))

    def test_configurable_normal_degree_and_chaos(self):
        narrow,broad=copy.deepcopy(self.tables),copy.deepcopy(self.tables)
        apply_equipment(self.tables,narrow,'width','wp',random_degree=0)
        apply_equipment(self.tables,broad,'width','wp',random_degree=1)
        self.assertNotEqual(narrow['ItemWeaponData'],broad['ItemWeaponData'])
        high=copy.deepcopy(self.tables)
        apply_equipment(self.tables,high,'chaos','p',chaos=500)
        for row in high['ItemData'].values(): self.assertTrue(0<=row['RequiredLevel']<=99)
        for kwargs in (dict(degree=-1),dict(degree=float('nan')),dict(chaos=-1),dict(random_degree=1.1),dict(random_degree=float('nan'))):
            with self.assertRaises(ValueError): apply_equipment(self.tables,copy.deepcopy(self.tables),'invalid','w',**kwargs)

    @unittest.skipUnless((RCC/'randomizer.py').exists(),'Requires original RCC checkout')
    def test_shop_and_weapon_status_phases_match_original_rcc_source(self):
        source=(RCC/'randomizer.py').read_text()
        selected='\n\n'.join(source[source.index('class '+name+'('):source.find('\nclass ',source.index('class '+name+'(')+1)]
                             for name in ('WeaponObject','ItemObject'))
        class ItemBase:
            def get_bit(self,name):
                if name!='rare': raise ValueError(name)
                return bool(self.flags&2)
            def set_bit(self,name,enabled):
                if name!='rare': raise ValueError(name)
                self.flags=(self.flags|2) if enabled else (self.flags&~2)
        for phase,rng_name in (('p','shops-p'),('y','weapon-status-y')):
            for seed in range(10):
                rng=rng_for(str(seed),rng_name)
                namespace={'TableObject':ItemBase,'random':rng,'randint':rng.randint,
                           'BANNED_ITEMS':[0x49],'boostd':{'equipment':1.1},
                           'mutate_normal':lambda base,minimum,maximum:mutate_normal(base,minimum,maximum,rng)}
                exec(selected,namespace)
                expected=copy.deepcopy(self.tables)
                if phase=='p':
                    for index,row in expected['ItemData'].items():
                        if index>=254: continue
                        item=namespace['ItemObject']()
                        item.index,item.flags=index,row['TypeFlags']
                        item.price,item.time_available,item.enemy_level=row['Price'],row['ShopAvailability'],row['RequiredLevel']
                        item.mutate_shop()
                        row.update(TypeFlags=item.flags,Price=item.price,ShopAvailability=item.time_available,RequiredLevel=item.enemy_level)
                    table='ItemData'
                else:
                    for row in expected['ItemWeaponData'].values():
                        weapon=namespace['WeaponObject']()
                        weapon.formula,weapon.inflict_status=row['Formula'],row['OptionsAbilityId']
                        weapon.mutate_status()
                        row['OptionsAbilityId']=weapon.inflict_status
                    table='ItemWeaponData'
                actual=copy.deepcopy(self.tables)
                apply_equipment(self.tables,actual,str(seed),phase)
                self.assertEqual(actual[table],expected[table],(phase,seed))

    def test_invalid_randomizer_settings(self):
        for kwargs in (dict(seed=''),dict(seed='x'*129),dict(seed='x',flags='?'),dict(seed='x',flags=''),
                       dict(seed='x',spread=float('nan')),dict(seed='x',spread=1.1),dict(seed='x',skill_degree=1.1),
                       dict(seed='x',skill_degree=float('nan')),dict(seed='x',chaos=-1)):
            with self.assertRaises(ValueError): randomize(self.tables,**kwargs)

    def test_changed_build_rejected_before_generation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "research") as scratch:
            exe = Path(scratch) / "FFT_enhanced.exe"
            exe.write_bytes(b"a changed executable")
            with self.assertRaisesRegex(ValueError, "verified build"):
                read_game(scratch)

    def test_package_integrity_sparse_fields_and_reproducibility(self):
        exe_before = hashlib.sha256((GAME / "FFT_enhanced.exe").read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(dir=ROOT / "research") as scratch:
            a, manifest = create_seed(GAME, Path(scratch) / "a", "test-output", flags='jsmpw')
            b, _ = create_seed(GAME, Path(scratch) / "b", "test-output", flags='jsmpw')
            self.assertEqual((a / "randomizer-mod.zip").read_bytes(), (b / "randomizer-mod.zip").read_bytes())
            config = json.loads((a / "fftivc.randomizer.seed/ModConfig.json").read_text())
            self.assertEqual(config["SupportedAppId"], ["fft_enhanced.exe"])
            self.assertEqual(config["ModDependencies"], ["fftivc.utility.modloader"])
            mod = a / "fftivc.randomizer.seed"
            for path, digest in manifest["payload_sha256"].items():
                self.assertEqual(hashlib.sha256((mod / path).read_bytes()).hexdigest(), digest)
            changes = json.loads((a / "changes.json").read_text())
            expected = {(c["table"], c["id"], c["field"]): c["after"] for c in changes}
            for path in (mod / "FFTIVC/tables/enhanced").glob("*.xml"):
                root = ET.parse(path).getroot()
                self.assertEqual(root.tag, XML_TYPES[path.stem][0])
                self.assertEqual(root.findtext("Version"), "1")
                for row in root.find("Entries"):
                    row_id = int(row.findtext("Id"))
                    for element in row:
                        if element.tag == "Id":
                            continue
                        if element.tag in ('ExtendAbilityIdFlagBits', 'ExtendReactionSupportMovementIdFlagBits'):
                            self.assertEqual(path.stem, 'JobCommandData')
                            self.assertEqual(element.text, '0')
                            continue
                        key = path.stem, row_id, element.tag
                        if key in expected:
                            self.assertEqual(int(element.text), expected[key])
                        else:
                            self.assertEqual(path.stem, "JobCommandData")
                            self.assertEqual(int(element.text), self.tables[path.stem][row_id][element.tag])
            with zipfile.ZipFile(a / "randomizer-mod.zip") as archive:
                self.assertIsNone(archive.testzip())
                for name in archive.namelist():
                    self.assertTrue(name.startswith("fftivc.randomizer.seed/"))
                    self.assertFalse(name.endswith((".exe", ".pac", ".sqlite")))
            with self.assertRaises(FileExistsError):
                create_seed(GAME, Path(scratch) / "a", "test-output", flags='jsmpw')
        self.assertEqual(hashlib.sha256((GAME / "FFT_enhanced.exe").read_bytes()).hexdigest(), exe_before)

    def test_refuses_active_game_output_directories(self):
        for folder in (GAME / "data", GAME / "data/enhanced/seeds", GAME / "scripts"):
            with self.assertRaises(ValueError):
                create_seed(GAME, folder, "unsafe-output")

    @unittest.skipUnless(shutil.which('pwsh') and Path('C:/Reloaded-II/Mods/fftivc.utility.modloader/fftivc.utility.modloader.Serializers.dll').exists(),
                         'Requires PowerShell Core and an installed FFTIC mod loader')
    def test_actual_loader_deserialization_and_regression(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'research') as scratch:
            destination, _ = create_seed(GAME, Path(scratch) / 'fixed', 'loader-regression',flags='jsmpw')
            folder = destination / 'fftivc.randomizer.seed/FFTIVC/tables/enhanced'
            cmd = [shutil.which('pwsh'), '-NoProfile', '-File', str(ROOT / 'tests/validate_loader_xml.ps1'), '-InputFolder']
            success = subprocess.run(cmd + [str(folder)], capture_output=True, text=True)
            self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
            bad_folder = Path(scratch) / 'broken'
            bad_folder.mkdir()
            bad_xml = ET.parse(folder / 'JobCommandData.xml')
            for row in bad_xml.getroot().find('Entries'):
                for field in ('ExtendAbilityIdFlagBits', 'ExtendReactionSupportMovementIdFlagBits'):
                    row.remove(row.find(field))
            bad_xml.write(bad_folder / 'JobCommandData.xml', encoding='utf-8', xml_declaration=True)
            failure = subprocess.run(cmd + [str(bad_folder)], capture_output=True, text=True)
            self.assertNotEqual(failure.returncode, 0)
            self.assertIn('AbilityId1', failure.stderr)

    def test_global_starter_nex_roundtrip_and_packaging(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'research') as scratch:
            a,manifest = create_seed(GAME,Path(scratch)/'a','global-starters',flags='jsmapwb',project_root=ROOT)
            b,_ = create_seed(GAME,Path(scratch)/'b','global-starters',flags='jsmapwb',project_root=ROOT)
            self.assertEqual((a/'randomizer-mod.zip').read_bytes(),(b/'randomizer-mod.zip').read_bytes())
            self.assertEqual(manifest['starting_actions']['roundtrip'],'exact rows and cells matched')
            self.assertEqual(manifest['starting_actions']['actions'],list(starter_actions('global-starters',self.tables)))
            mod = a/'fftivc.randomizer.seed'
            # Other default cleanup/conditional tables may also be packaged.
            nex=manifest['nex_changes']
            self.assertEqual(nex['roundtrip'],'exact rows and cells matched')
            localized=[table for table in nex['tables'] if table.startswith('Ability-')]
            self.assertEqual(len(localized),7)
            for table in localized:
                self.assertTrue((mod/'FFTIVC/data/enhanced/nxd'/('ability.'+table.split('-')[1]+'.nxd')).exists())


if __name__ == "__main__":
    unittest.main()
