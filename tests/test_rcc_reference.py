"""Compare the port with functions compiled from the user's RCC checkout.

These are behavioral reference tests, not copies of the implementation under
test. The source snippets undergo only syntax/runtime adaptations for Python 3
(``xrange`` and one Python 2 integer division). Set FFTIC_RCC_SOURCE to use a
different legal checkout; distribution users without RCC simply skip them.
"""
import ast
import copy
import os
from pathlib import Path
import random
import re
from types import SimpleNamespace
import textwrap
import unittest
from unittest.mock import patch

from fftic.game import ACTION_FIELDS, RSM_FIELDS, JOB_FIELDS
from fftic.rcc import mutate_bits, mutate_normal, _human_plan
from fftic.rcc_actions import apply_actions
from fftic.rcc_equipment import _weapons
from fftic.rcc_stats import apply_job_stats, mutate_job_stat


SOURCE = Path(os.environ.get('FFTIC_RCC_SOURCE', r'I:\rumble_chaos_crashdown'))


class ReferenceRecord:
    """RCC table records compare/hash by identity when used as pool owners."""
    def __init__(self, **fields):
        self.__dict__.update(fields)


def source_function(filename, name, *, owner=None):
    """Extract a named def without importing RCC's Python 2 entrypoint."""
    lines = (SOURCE / filename).read_text(encoding='utf-8').splitlines()
    start = 0
    if owner:
        start = next(i for i, line in enumerate(lines) if line.startswith(f'class {owner}(')) + 1
    indent = 4 if owner else 0
    begin = next(i for i in range(start, len(lines))
                 if lines[i].startswith(' ' * indent + f'def {name}('))
    end = begin + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.lstrip().startswith('#'):
            current = len(line) - len(line.lstrip())
            if current <= indent:
                break
        end += 1
    source = textwrap.dedent('\n'.join(lines[begin:end]))
    source = source.replace('xrange(', 'range(')
    source = re.sub(r'(?m)^(\s*)print .+$', r'\1pass', source)
    # RCC runs on Python 2: both operands are integers in this JP mean.
    source = source.replace('sum(jp_costs) / len(jp_costs)', 'sum(jp_costs) // len(jp_costs)')
    source = source.replace('len(actions) / 2', 'len(actions) // 2')
    return ast.parse(source, filename=str(SOURCE / filename))


def reference_environment(rng, degree=.25):
    env = dict(random=rng, get_random_degree=lambda: degree)
    for name in ('gen_random_normal', 'mutate_normal'):
        exec(compile(source_function('randomtools/tablereader.py', name), '<RCC reference>', 'exec'), env)
    exec(compile(source_function('randomizer.py', 'randint'), '<RCC reference>', 'exec'), env)
    return env


def compile_reference(env, name, owner=None):
    exec(compile(source_function('randomizer.py', name, owner=owner), '<RCC reference>', 'exec'), env)
    return env[name]


@unittest.skipUnless((SOURCE / 'randomizer.py').is_file() and
                     (SOURCE / 'randomtools/tablereader.py').is_file(),
                     'Requires the user-provided RCC source checkout')
class RCCReferenceTests(unittest.TestCase):
    def test_normal_distribution_matches_source_and_rng_consumption(self):
        cases = [(0, 0, 253), (1, 1, 253), (7, 0, 80), (90.75, 1, 253),
                 (250, 1, 253), (65000, 0, 65000), (12, 12, 12)]
        for degree in (0, .25, .5, 1):
            for seed in range(12):
                source_rng, port_rng = random.Random(seed), random.Random(seed)
                env = reference_environment(source_rng, degree)
                for base, low, high in cases:
                    for wide in (False, True):
                        for floating in (False, True):
                            expected = env['mutate_normal'](base, low, high,
                                                           return_float=floating, wide=wide)
                            actual = mutate_normal(base, low, high, port_rng, random_degree=degree,
                                                   return_float=floating, wide=wide)
                            self.assertEqual(actual, expected)
                            self.assertEqual(port_rng.getstate(), source_rng.getstate())

    def test_bit_mutation_matches_source_and_rng_consumption(self):
        for seed in range(30):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env = reference_environment(source_rng)
            reference = compile_reference(env, 'mutate_bits')
            for size, odds, value in ((8, 2., 0), (8, 2., 255), (8, 2., 0x55),
                                      (32, 4., 0x90DF0044), (32, 4., 0xFFFFFFFF)):
                self.assertEqual(mutate_bits(value, port_rng, size=size, odds_multiplier=odds),
                                 reference(value, size=size, odds_multiplier=odds))
                self.assertEqual(port_rng.getstate(), source_rng.getstate())

    def test_native_action_mutation_matches_source(self):
        names = {'CT':'ct', 'MPCost':'mp', 'X':'xval', 'Y':'yval',
                 'Range':'range', 'EffectArea':'effect', 'Vertical':'vertical'}
        sample = [dict(CT=4, MPCost=6, X=10, Y=5, Range=4, EffectArea=1, Vertical=2),
                  dict(CT=0, MPCost=254, X=253, Y=0, Range=1, EffectArea=0, Vertical=255)]
        for seed in range(30):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env = reference_environment(source_rng)
            reference = compile_reference(env, 'mutate', owner='AbilityAttributesObject')
            attrs, objects = {}, []
            for aid, row in enumerate(sample, 1):
                attrs[aid] = row | dict(Flags1=0, Flags2=0, Flags3=0, Flags4=0,
                                       Element=0, Formula=1, InflictStatus=0)
                objects.append(SimpleNamespace(**{name:row[field] for field,name in names.items()}))
            commands = {c:dict.fromkeys(ACTION_FIELDS+RSM_FIELDS, 0) for c in (10, 11, 12, 16)}
            before = dict(_AbilityAttributes=attrs, JobCommandData=commands,
                          MonsterJobCommandData={}, JobData={})
            result = copy.deepcopy(before)
            for obj in objects:
                reference(obj)
            with patch('fftic.rcc_actions.rng_for', return_value=port_rng):
                apply_actions(before, result, 'reference')
            for aid, obj in enumerate(objects, 1):
                for field, name in names.items():
                    self.assertEqual(result['_AbilityAttributes'][aid][field], getattr(obj, name))
            self.assertEqual(port_rng.getstate(), source_rng.getstate())

    def test_weapon_mutation_matches_source(self):
        names = {'Range':'range', 'Power':'weapon_power', 'Evasion':'evade',
                 'Formula':'formula', 'OptionsAbilityId':'inflict_status'}
        sample = [dict(Range=1, Power=9, Evasion=5, Formula=1, OptionsAbilityId=0),
                  dict(Range=3, Power=20, Evasion=254, Formula=2, OptionsAbilityId=0),
                  dict(Range=0, Power=253, Evasion=40, Formula=2, OptionsAbilityId=225),
                  dict(Range=255, Power=0, Evasion=0, Formula=1, OptionsAbilityId=9)]
        for seed in range(40):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env = reference_environment(source_rng)
            reference = compile_reference(env, 'mutate', owner='WeaponObject')
            expected = []
            for row in sample:
                obj = SimpleNamespace(**{name:row[field] for field,name in names.items()})
                reference(obj)
                expected.append(obj)
            result = {'ItemWeaponData':dict(enumerate(copy.deepcopy(sample)))}
            _weapons(result, port_rng, 1, .25)
            for index, obj in enumerate(expected):
                for field, name in names.items():
                    self.assertEqual(result['ItemWeaponData'][index][field], getattr(obj, name))
            self.assertEqual(port_rng.getstate(), source_rng.getstate())

    def test_skill_jp_mutation_and_emitted_learn_chances_match_source(self):
        costs = {1:50, 2:200, 3:0, 4:750, 5:5000, 6:10}
        chances = {1:80, 2:100, 3:0, 4:25, 5:100, 6:100}
        definitions = {5:([1, 3], [4]), 10:([2, 4], [6]), 30:([5, 1], []), 50:([6], [])}
        for seed in range(20):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env = reference_environment(source_rng)
            abilities = {a:SimpleNamespace(index=a, jp_cost=cost, learn_chance=chances[a])
                         for a,cost in costs.items()}
            skillsets = [SimpleNamespace(index=c, actions=list(actions), rsms=list(rsms),
                                          is_generic=5<=c<=24)
                         for c,(actions,rsms) in sorted(definitions.items())]
            env.update(get_jobs_kind=lambda kind:[], SkillsetObject=SimpleNamespace(every=skillsets),
                       AbilityObject=SimpleNamespace(get=lambda aid:abilities[aid]))
            reference = compile_reference(env, 'mutate_job_stats')
            reference()
            rows = {}
            for c,(actions,rsms) in definitions.items():
                row = dict.fromkeys(ACTION_FIELDS+RSM_FIELDS, 0)
                row.update(zip(ACTION_FIELDS, actions))
                row.update(zip(RSM_FIELDS, rsms))
                rows[c] = row
            before = dict(JobData={}, JobCommandData=rows, _JobTraits={},
                          _AbilityCatalog={a:dict(jp_cost=cost) for a,cost in costs.items()},
                          _AbilityMetadata={a:dict(JPCost=costs[a],LearnChance=chance,AbilityType=1,
                                                  Flags=0,AIBehaviorFlags=0) for a,chance in chances.items()})
            with patch('fftic.rcc_stats.rng_for', return_value=port_rng):
                audit = apply_job_stats(before, copy.deepcopy(before), 'reference', 'j')
            effective = costs | audit['jp_cost_updates']
            self.assertEqual(effective, {a:obj.jp_cost for a,obj in abilities.items()})
            self.assertEqual(chances|audit['learn_chance_updates'],
                             {a:obj.learn_chance for a,obj in abilities.items()})
            self.assertEqual(port_rng.getstate(), source_rng.getstate())

    def test_native_job_stat_boost_and_lucavi_reflection_match_source(self):
        names = dict(zip(JOB_FIELDS, ('hpgrowth','hpmult','mpgrowth','mpmult','spdgrowth',
                                     'spdmult','pagrowth','pamult','magrowth','mamult',
                                     'move','jump','evade')))
        values = [11,90,11,70,100,80,40,80,50,80,4,3,10]
        for seed in range(24):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env = reference_environment(source_rng)
            reference = compile_reference(env, 'mutate_stats', owner='JobObject')
            jobs = {60:dict(zip(JOB_FIELDS,values))|dict(JobCommandId=30),
                    94:dict(zip(JOB_FIELDS,values))|dict(JobCommandId=176)}
            before = dict(JobData=jobs, _JobTraits={94:dict(MonsterPortrait=1)},
                          _RCCUnits=[dict(job=60,enemy=True,level=40,map_id=400)])
            objects = {}
            for job,row in jobs.items():
                obj = SimpleNamespace(is_lucavi=job==60,
                                      **{names[f]:row[f] for f in JOB_FIELDS})
                reference(obj, boost_factor=1.4**.75 if job==60 else 1.)
                objects[job] = obj
            result = copy.deepcopy(before)
            for job in sorted(jobs):
                mutate_job_stat(before,result,job,port_rng)
            for job,obj in objects.items():
                for field,name in names.items():
                    self.assertEqual(result['JobData'][job][field],getattr(obj,name))
            self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_native_special_commands_keep_rcc_shuffle_exclusions(self):
        from fftic.game import read_game
        from fftic.rcc import _native_restricted, _mimic_commands
        game = Path(__file__).resolve().parents[2]
        if not (game / 'FFT_enhanced.exe').exists():
            self.skipTest('Requires a local game installation')
        tables, _ = read_game(game)
        # Menu/type facts suffice here; do not extract localized Nex assets.
        tables['_AbilityCatalog'] = {a:dict(native_type=row['AbilityType'])
                                     for a,row in tables['_AbilityMetadata'].items()}
        for command in (6, 8, 17, 18, 19, 20, 21, 52, 56, 57, 59, 62, 156, 161):
            self.assertTrue(_native_restricted(tables, command), command)
        self.assertIn(24, _mimic_commands(tables))

    def test_complete_skillset_phase_matches_source(self):
        # Shared aliases, free actions, single-action classes, native special
        # menus and passive depletion all run through the unmodified RCC
        # phase. Only the story-recruit list is extended for FFTIC's records.
        catalog = {}
        def ability(aid, kind=1, cost=200):
            catalog.setdefault(aid, dict(name=f'Ability {aid}', native_type=kind,
                                         jp_cost=cost, eligible=True, ai_flags=0))
            return aid
        rows = {c:dict.fromkeys(ACTION_FIELDS+RSM_FIELDS, 0) for c in range(60)}
        menus = {c:dict(Menu=0) for c in rows}
        jobs = {j:dict(JobCommandId=j-69) for j in range(74,94)}
        story_jobs = (13,15,22,26,30,31,41,42,50,144,145,160,162,163)
        for offset, job in enumerate(story_jobs):
            jobs[job] = dict(JobCommandId=30+offset)
        for c in range(5,24):
            actions = [ability(c*5+i, cost=100+i*100) for i in range(5)]
            actions[0] = ability(1, cost=0)
            rows[c].update(zip(ACTION_FIELDS, actions))
            passives = [ability(423+c, 7, 100), ability(450+c, 8, 250), ability(478+c, 9, 200)]
            rows[c].update(zip(RSM_FIELDS, passives))
        for c in range(30,44):
            rows[c].update(zip(ACTION_FIELDS, [ability(150+c+i, cost=i*150) for i in range(4)]))
            rows[c].update(zip(RSM_FIELDS, [ability(425+c%5,7), ability(450+c%5,8)]))
        # A duplicate variant contributes no unseen actions; a singleton is
        # skipped by the exchange but remains eligible for rare injections.
        rows[50].update(zip(ACTION_FIELDS, [ability(250)]))
        rows[51] = copy.deepcopy(rows[30])
        native = {6:(1,2,368), 8:(10,5,406), 17:(4,1,126), 18:(9,4,394),
                  19:(7,1,76), 20:(2,3,382), 21:(3,6,414)}
        for c,(menu,kind,start) in native.items():
            for field in ACTION_FIELDS:
                rows[c][field] = 0
            rows[c].update(zip(ACTION_FIELDS, [ability(start+i,kind,100) for i in range(4)]))
            menus[c]['Menu'] = menu
        ability(471,8,200); catalog[471]['name'] = 'Poach'
        ability(499,9,0); catalog[499]['name'] = 'Master Teleportation'
        for seed in range(24):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env = reference_environment(source_rng)
            objects = {a:SimpleNamespace(index=a, ability_type=r['native_type'], jp_cost=r['jp_cost'])
                       for a,r in catalog.items()}
            source_skillsets = {c:ReferenceRecord(index=c,
                                    actions=[rows[c][f] for f in ACTION_FIELDS if rows[c][f]],
                                    rsms=[rows[c][f] for f in RSM_FIELDS if rows[c][f]])
                                for c in rows}
            method = compile_reference(env,'mutate_abilities',owner='SkillsetObject')
            for obj in source_skillsets.values():
                obj.has_learnable_actions = any(objects[a].jp_cost>0 for a in obj.actions)
                obj.mutate_abilities = lambda obj=obj:method(obj)
            def get_abilities():
                objects[499].jp_cost = 9999
                return [objects[a] for a in sorted(objects)]
            env.update(get_skillsets=lambda:[source_skillsets[c] for c in sorted(rows) if c>=5],
                       get_skillset=lambda c:source_skillsets[c],
                       get_abilities=get_abilities, get_ability=lambda aid:objects[aid],
                       SkillsetObject=SimpleNamespace(get=lambda c:source_skillsets[c]),
                       JobObject=SimpleNamespace(get=lambda j:SimpleNamespace(skillset=jobs[j]['JobCommandId'])),
                       STORYLINE_RECRUITABLE_JOBS=story_jobs,
                       BANNED_SKILLSET_SHUFFLE=[0,1,2,3,6,8,17,18,19,20,21,24,52,56,57,59,62,156,161],
                       BANNED_RSMS=[443,471,481,484,485,497], BANNED_ANYTHING=[24], BANNED_SKILLS=[])
            reference = compile_reference(env,'mutate_skillsets')
            reference()
            table = dict(JobData=jobs, JobCommandData=rows, CommandTypeData=menus, _AbilityCatalog=catalog)
            actual, costs = _human_plan(table,port_rng,1,dict(limitations=[]))
            for c in rows:
                self.assertEqual([actual[c][f] for f in ACTION_FIELDS if actual[c][f]],
                                 source_skillsets[c].actions, (seed,c,'actions'))
                self.assertEqual([actual[c][f] for f in RSM_FIELDS if actual[c][f]],
                                 source_skillsets[c].rsms, (seed,c,'passives'))
            self.assertEqual({a:r['jp_cost'] for a,r in catalog.items()}|costs,
                             {a:obj.jp_cost for a,obj in objects.items()})
            self.assertEqual(port_rng.getstate(),source_rng.getstate())


if __name__ == '__main__':
    unittest.main()
