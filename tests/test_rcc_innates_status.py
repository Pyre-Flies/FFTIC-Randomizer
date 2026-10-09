"""Behavioral parity checks against functions compiled from the old RCC code."""
import ast
import copy
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fftic.game import read_game, JOB_FIELDS, ACTION_FIELDS, RSM_FIELDS
from fftic import rcc_innates as innates
from fftic import rcc_status as status
from fftic.rcc_stats import mutate_job_stat, apply_job_stats, apply_monster_stats_innates
from test_rcc_reference import SOURCE, source_function, reference_environment, compile_reference


JOB_NAMES = dict(zip(JOB_FIELDS, ('hpgrowth','hpmult','mpgrowth','mpmult','spdgrowth',
                                 'spdmult','pagrowth','pamult','magrowth','mamult',
                                 'move','jump','evade')))
INNATE_NAMES = {f: f'innate{i}' for i,f in enumerate(innates.INNATE_FIELDS,1)}
STATUS_NAMES = dict(InnateStatus='innate_status', ImmuneStatus='immune_status', StartingStatus='start_status')
ELEMENT_NAMES = dict(AbsorbElements='absorb_elem', NullifyElements='nullify_elem',
                     HalveElements='resist_elem', WeakElements='weak_elem')


def innate_environment(rng, tables):
    env = reference_environment(rng)
    compile_reference(env, 'mutate_bits')
    for name in ('VALID_INNATE_STATUSES','VALID_START_STATUSES','BENEFICIAL_STATUSES',
                 'RERAISE_STATUS','FAITH_STATUS','INNOCENT_STATUS','LUCAVI_INNATES','MP_RESTORE_INNATES'):
        env[name] = getattr(innates,name)
    abilities = {a:SimpleNamespace(index=a, ability_type=r['AbilityType'], jp_cost=r['JPCost'],
                                  is_reaction=r['AbilityType']==7, is_support=r['AbilityType']==8,
                                  is_movement=r['AbilityType']==9)
                 for a,r in tables['_AbilityMetadata'].items()}
    def get_abilities():
        abilities[499].jp_cost = 9999
        return [abilities[a] for a in sorted(abilities) if not 357 <= a <= 366]
    env.update(get_abilities=get_abilities, AbilityObject=SimpleNamespace(get=lambda a:abilities[a]))
    source = source_function('randomizer.py','mutate_innate',owner='JobObject')
    # Python 2 midpoint of the integer-length support list.
    for node in ast.walk(source):
        if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div):
            node.op = ast.FloorDiv()
    exec(compile(source,'<RCC innate reference>','exec'),env)
    methods = {name:compile_reference(env,name,owner='JobObject')
               for name in ('mutate_statuses','unset_positive_immunities','unset_negative_statuses')}
    return env,abilities,methods


def source_job(index, native, methods):
    obj = SimpleNamespace(index=index, equips=innates.swap_mask(native['EquippableItems']>>8,4),
                          is_lucavi=index in innates.LUCAVI_JOBS,
                          is_monster_job=index>=94 and index!=151,
                          is_altima=index in (65,73), overrides={})
    for field,name in INNATE_NAMES.items(): setattr(obj,name,native[field])
    for field,name in STATUS_NAMES.items(): setattr(obj,name,innates.swap_mask(native[field]))
    for field,name in ELEMENT_NAMES.items(): setattr(obj,name,native[field])
    for name,method in methods.items(): setattr(obj,name,lambda method=method:method(obj))
    obj.set_all_units = lambda attr,value:obj.overrides.__setitem__(attr,value)
    return obj


def options_fixture():
    return {i:dict(OptionType=0 if i in (29,30,31) or i>=122 else (16,32,64,128)[i%4],
                   Effects=0 if i in (29,30,31) or i>=122 else 1<<(i%40)) for i in range(128)}


@unittest.skipUnless((SOURCE/'randomizer.py').is_file(), 'Requires the user-provided RCC checkout')
class RCCInnateStatusReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        game = Path(__file__).resolve().parents[2]
        if not (game/'FFT_enhanced.exe').exists():
            raise unittest.SkipTest('Requires a local game installation')
        cls.tables,_ = read_game(game)

    def test_native_endian_boundaries_match_status_semantics(self):
        self.assertEqual(innates.swap_mask(innates.FAITH_STATUS),0x80)
        self.assertEqual(innates.swap_mask(innates.RERAISE_STATUS),0x200000)
        for value in (0,1,0x123456789A,0xFFFFFFFFFF):
            self.assertEqual(innates.swap_mask(innates.swap_mask(value)),value)

    def test_every_innate_branch_matches_source_and_rng(self):
        for seed in range(32):
            for job in (0,13,60,65,74,75,94,151):
                source_rng,port_rng = random.Random(seed),random.Random(seed)
                expected = copy.deepcopy(self.tables)
                actual = copy.deepcopy(self.tables)
                env,abilities,methods = innate_environment(source_rng,expected)
                obj = source_job(job,expected['JobData'][job],methods)
                env['mutate_innate'](obj)
                override = innates.mutate_job_innate(actual,job,port_rng)
                row = actual['JobData'][job]
                self.assertEqual(row['EquippableItems']>>8,innates.swap_mask(obj.equips,4),(seed,job,'equips'))
                self.assertEqual(row['EquippableItems']&255,expected['JobData'][job]['EquippableItems']&255)
                for field,name in (INNATE_NAMES|ELEMENT_NAMES).items():
                    self.assertEqual(row[field],getattr(obj,name),(seed,job,field))
                for field,name in STATUS_NAMES.items():
                    self.assertEqual(row[field],innates.swap_mask(getattr(obj,name)),(seed,job,field))
                expected_override = dict(job=job,**{dict(reaction='ReactionAbilityId',support='SupportAbilityId',
                                                       movement='MovementAbilityId')[k]:v
                                                  for k,v in obj.overrides.items()}) if obj.overrides else None
                self.assertEqual(override,expected_override,(seed,job))
                self.assertEqual(actual['_AbilityMetadata'][499]['JPCost'],abilities[499].jp_cost)
                self.assertEqual(port_rng.getstate(),source_rng.getstate(),(seed,job))

    def test_squire_exemption_preserves_statuses_and_innates(self):
        for seed in range(12):
            result = copy.deepcopy(self.tables)
            innates.mutate_job_innate(result,74,random.Random(seed))
            for field in innates.STATUS_FIELDS+innates.INNATE_FIELDS:
                self.assertEqual(result['JobData'][74][field],self.tables['JobData'][74][field])

    def test_active_nex_jp_order_is_used_for_innate_candidates(self):
        before = copy.deepcopy(self.tables)
        before['_AbilityCatalog'] = {a:dict(jp_cost=20000-r['JPCost'])
                                     for a,r in before['_AbilityMetadata'].items()}
        for seed in range(12):
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            expected = copy.deepcopy(before)
            # The source has one JP field; adapt it to the active Enhanced value.
            for aid,row in expected['_AbilityMetadata'].items():
                row['JPCost'] = expected['_AbilityCatalog'][aid]['jp_cost']
            env,_,methods = innate_environment(source_rng,expected)
            obj = source_job(94,expected['JobData'][94],methods)
            env['mutate_innate'](obj)
            actual = copy.deepcopy(before)
            innates.mutate_job_innate(actual,94,port_rng)
            for field,name in INNATE_NAMES.items():
                self.assertEqual(actual['JobData'][94][field],getattr(obj,name))
            self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_empty_status_options_match_source_and_rng(self):
        for seed in range(24):
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            env = reference_environment(source_rng)
            env['VALID_START_STATUSES'] = innates.VALID_START_STATUSES
            reference = compile_reference(env,'randomize_empty',owner='InflictStatusObject')
            for index,row in options_fixture().items():
                obj = SimpleNamespace(index=index,statuses_to_inflict=innates.swap_mask(row['Effects']),
                                      inflict_type=row['OptionType'])
                obj.set_bit = lambda name,value,obj=obj:setattr(obj,'inflict_type',obj.inflict_type|
                                                dict(random=64,separate=32,cancel=16,all_or_nothing=128)[name])
                reference(obj)
                actual = dict(row)
                status.randomize_empty_option(index,actual,port_rng)
                self.assertEqual(actual['Effects'],innates.swap_mask(obj.statuses_to_inflict))
                self.assertEqual(actual['OptionType'],obj.inflict_type)
                self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_full_status_phase_matches_source_including_ai_and_weapons(self):
        for seed in range(20):
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            before = copy.deepcopy(self.tables)
            before['ItemOptionsData'] = options_fixture()
            actual = copy.deepcopy(before)
            env = reference_environment(source_rng)
            env.update(VALID_START_STATUSES=innates.VALID_START_STATUSES,STATUS_FORMULAS=status.STATUS_FORMULAS)
            option_method = compile_reference(env,'randomize_empty',owner='InflictStatusObject')
            action_method = compile_reference(env,'mutate_status',owner='AbilityAttributesObject')
            weapon_method = compile_reference(env,'mutate_status',owner='WeaponObject')
            options = {}
            for index,row in before['ItemOptionsData'].items():
                obj = SimpleNamespace(index=index,statuses_to_inflict=innates.swap_mask(row['Effects']),
                                      inflict_type=row['OptionType'])
                bits = dict(random=64,separate=32,cancel=16,all_or_nothing=128)
                obj.set_bit = lambda name,value,obj=obj,bits=bits:setattr(obj,'inflict_type',obj.inflict_type|bits[name])
                obj.get_bit = lambda name,obj=obj,bits=bits:bool(obj.inflict_type&bits[name])
                options[index] = obj
                option_method(obj)
            abilities = {}
            for aid,row in before['_AbilityMetadata'].items():
                obj = SimpleNamespace(ai=row['AIBehaviorFlags'])
                ai_bits = dict(add_status=16,cancel_status=32)
                obj.get_bit = lambda name,obj=obj:bool(obj.ai&ai_bits[name])
                obj.set_bit = lambda name,value,obj=obj:setattr(obj,'ai',(obj.ai|ai_bits[name]) if value else (obj.ai&~ai_bits[name]))
                abilities[aid] = obj
            env.update(get_ability=lambda aid:abilities[aid],InflictStatusObject=SimpleNamespace(get=lambda index:options[index]))
            actions = {}
            for aid,row in sorted(before['_AbilityAttributes'].items()):
                obj = SimpleNamespace(index=aid,formula=row['Formula'],inflict_status=row['InflictStatus'],effect=row['EffectArea'])
                bits = dict(math_skill=bool(row['Flags3']&64),**{'3_directions':bool(row['Flags2']&2)})
                obj.get_bit = lambda name,bits=bits:bits[name]
                actions[aid] = obj
                action_method(obj)
            weapons = {}
            for index,row in sorted(before['ItemWeaponData'].items()):
                obj = SimpleNamespace(index=index,formula=row['Formula'],inflict_status=row['OptionsAbilityId'])
                weapons[index] = obj
                weapon_method(obj)
            audit = status.apply_status(before,actual,'reference',rng=port_rng)
            for index,obj in options.items():
                self.assertEqual(actual['ItemOptionsData'][index],dict(OptionType=obj.inflict_type,Effects=innates.swap_mask(obj.statuses_to_inflict)))
            for aid,obj in actions.items():
                self.assertEqual(actual['_AbilityAttributes'][aid]['InflictStatus'],obj.inflict_status,(seed,aid))
            for aid,obj in abilities.items():
                self.assertEqual(actual['_AbilityMetadata'][aid]['AIBehaviorFlags'],obj.ai,(seed,aid))
                self.assertEqual(actual['_AbilityMetadata'][aid]['AbilityType'],before['_AbilityMetadata'][aid]['AbilityType'])
                self.assertEqual(actual['_AbilityMetadata'][aid]['Flags'],before['_AbilityMetadata'][aid]['Flags'])
            for index,obj in weapons.items():
                self.assertEqual(actual['ItemWeaponData'][index]['OptionsAbilityId'],obj.inflict_status,(seed,index))
            self.assertEqual(audit['metadata_updates'],actual['_RCCMetadataUpdates'])
            self.assertEqual(port_rng.getstate(),source_rng.getstate(),seed)

    def test_monster_phase_interleaves_stats_and_innates_in_source_order(self):
        before = copy.deepcopy(self.tables)
        before['JobData'] = {j:before['JobData'][j] for j in (94,95,151)}
        before['_RCCUnits'] = []
        source_rng,port_rng = random.Random(41),random.Random(41)
        env,abilities,methods = innate_environment(source_rng,before)
        stats = compile_reference(env,'mutate_stats',owner='JobObject')
        expected = {}
        for job,native in before['JobData'].items():
            obj = source_job(job,native,methods)
            for field,name in JOB_NAMES.items(): setattr(obj,name,native[field])
            stats(obj,boost_factor=1.)
            env['mutate_innate'](obj)
            expected[job] = obj
        actual = copy.deepcopy(before)
        audit = apply_monster_stats_innates(before,actual,'reference',rng=port_rng)
        self.assertEqual(audit['selected_jobs'],[94,95,151])
        for job,obj in expected.items():
            for field,name in JOB_NAMES.items(): self.assertEqual(actual['JobData'][job][field],getattr(obj,name))
            for field,name in INNATE_NAMES.items(): self.assertEqual(actual['JobData'][job][field],getattr(obj,name))
        self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_metadata_collection_guards_flags_and_emits_learn_rate(self):
        before = copy.deepcopy(self.tables)
        after = copy.deepcopy(before)
        after['_AbilityMetadata'][1].update(LearnChance=42,AIBehaviorFlags=0xFFFFFFFF)
        update = status.metadata_updates(before,after)[1]
        self.assertEqual(update,dict(LearnChance=42,AIBehaviorFlags=0xFFFFFFFF))
        self.assertNotIn('AbilityType',update)
        self.assertNotIn('Flags',update)
        after['_AbilityMetadata'][1]['AbilityType'] ^= 1
        with self.assertRaisesRegex(ValueError,'preserve'):
            status.metadata_updates(before,after)

    def test_job_jp_and_learn_chances_match_source_and_are_emitted(self):
        before = copy.deepcopy(self.tables)
        before.update(JobData={},_JobTraits={},_RCCUnits=[],_AbilityCatalog={
            a:dict(jp_cost=r['JPCost']) for a,r in before['_AbilityMetadata'].items()})
        for aid,cost,chance in ((1,0,0),(2,150,40),(3,600,100),(4,50,0),(437,400,90)):
            before['_AbilityCatalog'][aid]['jp_cost'] = cost
            before['_AbilityMetadata'][aid].update(JPCost=cost,LearnChance=chance)
        rows = {c:dict.fromkeys(ACTION_FIELDS+RSM_FIELDS,0) for c in (0,5,6,30)}
        rows[5].update(zip(ACTION_FIELDS,(1,2,3)))
        rows[6][ACTION_FIELDS[0]] = 4
        rows[30][RSM_FIELDS[0]] = 437
        before['JobCommandData'] = rows
        for seed in range(24):
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            env = reference_environment(source_rng)
            abilities = {a:SimpleNamespace(index=a,jp_cost=r['JPCost'],learn_chance=r['LearnChance'])
                         for a,r in before['_AbilityMetadata'].items()}
            skillsets = [SimpleNamespace(index=c,is_generic=5<=c<=24,
                                         actions=[row[f] for f in ACTION_FIELDS if row[f]],
                                         rsms=[row[f] for f in RSM_FIELDS if row[f]]) for c,row in rows.items()]
            env.update(get_jobs_kind=lambda kind:[],SkillsetObject=SimpleNamespace(every=skillsets),
                       AbilityObject=SimpleNamespace(get=lambda a:abilities[a]))
            compile_reference(env,'mutate_job_stats')()
            result = copy.deepcopy(before)
            with patch('fftic.rcc_stats.rng_for',return_value=port_rng):
                audit = apply_job_stats(before,result,'reference','j')
            for aid,obj in abilities.items():
                self.assertEqual(result['_AbilityMetadata'][aid]['JPCost'],obj.jp_cost,(seed,aid))
                self.assertEqual(result['_AbilityMetadata'][aid]['LearnChance'],obj.learn_chance,(seed,aid))
            self.assertTrue(audit['learn_chance_updates'])
            for aid,chance in audit['learn_chance_updates'].items():
                self.assertEqual(result['_RCCMetadataUpdates'][aid]['LearnChance'],chance)
            self.assertEqual(port_rng.getstate(),source_rng.getstate(),seed)

    def test_zero_degree_and_disabled_innates_leave_native_tables_unchanged(self):
        for flags,degree in (('im',0),('',1)):
            result = copy.deepcopy(self.tables)
            audit = innates.apply_innates(self.tables,result,'no-op',flags,degree)
            self.assertEqual(result,self.tables)
            self.assertEqual(audit['selected_jobs'],[])


if __name__ == '__main__':
    unittest.main()
