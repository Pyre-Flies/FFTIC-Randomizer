"""Behavioral comparisons against the user's original RCC r/t/c methods."""
import ast
import copy
import io
from pathlib import Path
import random
import textwrap
from types import SimpleNamespace
import unittest

from fftic.game import read_game
from fftic.rcc_music import randomize_music
from fftic.rcc_requirements import mutate_job_level, mutate_job_requirements
from fftic.rcc_rewards import get_similar_item, mutate_poaches, mutate_move_find, ranked_items
from fftic.rcc_world_data import read_native_world, commit_world_patches
from test_rcc_reference import SOURCE, reference_environment, compile_reference, source_function


NAMES = ('squire', 'chemist', 'knight', 'archer', 'monk', 'priest', 'wizard',
         'timemage', 'summoner', 'thief', 'mediator', 'oracle', 'geomancer',
         'lancer', 'samurai', 'ninja', 'calculator', 'bard', 'dancer', 'mime')


def last_class_method(env, name, owner):
    # The shared extractor intentionally preserves comments. The final Poach
    # method is followed by an unindented class comment, so stop there before
    # dedenting the actual method body.
    lines = (SOURCE/'randomizer.py').read_text(encoding='utf-8').splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith('class '+owner+'('))
    start = next(index for index in range(start+1, len(lines)) if lines[index].startswith('    def '+name+'('))
    end = start+1
    while end < len(lines):
        line = lines[end]
        if line.strip() and len(line)-len(line.lstrip()) <= 4:
            break
        end += 1
    exec(compile(textwrap.dedent('\n'.join(lines[start:end])), '<RCC final class method>', 'exec'), env)
    return env[name]


class Record(SimpleNamespace):
    def __lt__(self, other):
        return self.index < other.index

    __hash__ = object.__hash__


def item_environment(rng, degree=.25):
    env = reference_environment(rng, degree)
    items = {index: dict(Price=(index*211)%65001, RequiredLevel=index%99)
             for index in range(254)}
    objects = [Record(index=index, price=row['Price'], enemy_level=row['RequiredLevel'])
               for index, row in items.items()]
    class Item(Record):
        pass
    Item.priceless = property(compile_reference(env, 'priceless', owner='ItemObject'))
    Item.rank = property(compile_reference(env, 'rank', owner='ItemObject'))
    objects = [Item(**obj.__dict__) for obj in objects]
    env['ItemObject'] = SimpleNamespace(every=objects, get=lambda index: objects[index])
    env['get_item'] = env['ItemObject'].get
    env['get_ranked_items'] = compile_reference(env, 'get_ranked_items')
    env['get_similar_item'] = compile_reference(env, 'get_similar_item')
    env['boostd'] = dict(common_item=1.5)
    return env, items


@unittest.skipUnless((SOURCE/'randomizer.py').is_file(), 'Requires the user-provided RCC checkout')
class RCCWorldReferenceTests(unittest.TestCase):
    def test_music_choices_protections_reset_and_rng_match_source(self):
        cases = [(10, 1, [3, 6], False, False),
                 (11, 0x186, [3, 6], False, False),
                 (0x12B, 0x133, [69, 3], True, True),
                 (12, 0x133, [69, 3], False, True),
                 (13, 100, [0, 81], True, False)]
        for seed in range(40):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env = reference_environment(source_rng)
            env['range'] = lambda *args: list(range(*args))
            cls = SimpleNamespace(used_music=set(range(100)))
            env['EncounterObject'] = cls
            method = compile_reference(env, 'randomize_music', owner='EncounterObject')
            used = set(range(100))
            for index, entd, music, prefer, force in cases:
                obj = Record(index=index, entd=entd, music=list(music))
                row = dict(entd=entd, music=list(music))
                method(obj, prefer_unused=prefer, force_battle=force)
                randomize_music(row, index, port_rng, used, prefer, force)
                self.assertEqual(obj.music, row['music'])
                self.assertEqual(cls.used_music, used)
                self.assertEqual(source_rng.getstate(), port_rng.getstate())

    def test_similar_item_and_poach_match_source(self):
        for seed in range(30):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env, items = item_environment(source_rng)
            for item in (1, 106, 143, 200, 253):
                expected = env['get_similar_item'](item, boost_factor=1.5).index
                got = get_similar_item(item, items, port_rng, 1.5,
                                       extended_items={256: dict(Price=10, RequiredLevel=97)})
                self.assertEqual(expected, got)
                self.assertEqual(source_rng.getstate(), port_rng.getstate())
            env['PoachObject'] = SimpleNamespace(donerare=set())
            method = last_class_method(env, 'mutate', 'PoachObject')
            poaches = {index: dict(common=10+index, rare=150+index) for index in range(20)}
            objects = [Record(index=index, **row) for index, row in poaches.items()]
            for obj in objects:
                method(obj)
            mutate_poaches(poaches, items, port_rng)
            self.assertEqual([(obj.common, obj.rare) for obj in objects],
                             [(row['common'], row['rare']) for row in poaches.values()])
            self.assertEqual(source_rng.getstate(), port_rng.getstate())

    def test_move_find_coordinates_rewards_and_traps_match_source(self):
        grid = [[0, 1, 0], [0, 0, 0], [1, 0, 0]]
        cells = [dict(occupied=0, unreachable=0, terrain_type=0, impassable=value,
                      uncursorable=0, slope_height=0, depth=0) for row in grid for value in row]
        maps = {1: [dict(width=3, length=3, cells=cells)]}
        flags = dict(degenerator=0, deathtrap=1, sleeping_gas=2, steel_needle=3,
                     disable_trap=4, always_trap=5, unk=6, no_activation=7)
        class MoveFind(Record):
            def set_bit(self, field, enabled):
                mask = 1 << flags[field]
                self.misc1 = self.misc1 | mask if enabled else self.misc1 & ~mask
        for seed in range(40):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env, items = item_environment(source_rng)
            env['MapObject'] = SimpleNamespace(get_certain_values_map_id=lambda *_: grid)
            method = compile_reference(env, 'mutate', owner='MoveFindObject')
            MoveFind.set_coordinates = compile_reference(env, 'set_coordinates', owner='MoveFindObject')
            obj = MoveFind(index=4, map_id=1, my_map=SimpleNamespace(width=3, length=3),
                           coordinates=0x12, misc1=0x85, common=25, rare=160)
            row = dict(X1=1, Y1=2, TrapFlags1=0x85, CommonItemId1=25, RareItemId1=160)
            method(obj)
            mutate_move_find(row, 1, 1, maps, items, port_rng)
            self.assertEqual((obj.coordinates, obj.misc1, obj.common, obj.rare),
                             ((row['X1'] << 4)|row['Y1'], row['TrapFlags1'], row['CommonItemId1'], row['RareItemId1']))
            self.assertEqual(source_rng.getstate(), port_rng.getstate())

    def test_job_level_curve_matches_source_and_rng(self):
        for seed in range(30):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env = reference_environment(source_rng)
            original = [100, 200, 400, 700, 1100, 1600, 2200, 3000]
            env.update(JOBLEVEL_JP=list(original), JAPANESE_MODE=False,
                       boostd={'jp': 1.5}, open=lambda *_: SimpleNamespace(seek=lambda *_: None, close=lambda: None),
                       write_multi=lambda *_args, **_kwargs: None)
            tree = source_function('randomizer.py', 'mutate_job_level')
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                    node.op = ast.FloorDiv()
            exec(compile(ast.fix_missing_locations(tree), '<RCC job curve>', 'exec'), env)
            env['mutate_job_level']('unused')
            got = mutate_job_level(original, port_rng)
            self.assertEqual(env['JOBLEVEL_JP'], got)
            self.assertEqual(source_rng.getstate(), port_rng.getstate())

    def test_job_tree_matches_source_transitive_closure_and_rng(self):
        original = {job: ({0: 2} if job else {}) for job in range(20)}
        for seed in range(24):
            source_rng, port_rng = random.Random(seed), random.Random(seed)
            env = reference_environment(source_rng)
            env['JOBNAMES'] = list(NAMES)
            class Job(Record):
                pass
            Job.set_zero = compile_reference(env, 'set_zero', owner='JobReqObject')
            Job.remax_jobreqs = compile_reference(env, 'remax_jobreqs', owner='JobReqObject')
            jobs = [Job(index=job+74, name=NAMES[job],
                        **{name: original[job].get(index, 0) for index, name in enumerate(NAMES)})
                    for job in range(20)]
            env['jobreq_namedict'] = {job.name: job for job in jobs}
            env['get_jobreqs'] = lambda: list(jobs)
            env['ItemObject'] = SimpleNamespace(get=lambda _index: Record(enemy_level=1))
            method = compile_reference(env, 'mutate_job_requirements')
            method()
            expected = {job.index-74: {index: getattr(job, name) for index, name in enumerate(NAMES) if getattr(job, name)} for job in jobs}
            got = mutate_job_requirements(original, port_rng)
            self.assertEqual(expected, got)
            self.assertEqual(source_rng.getstate(), port_rng.getstate())


class RCCExtendedRewardTests(unittest.TestCase):
    """Enhanced input items guide RCC ranks without entering its byte pools."""

    def test_extended_item_guides_rank_without_becoming_a_possible_reward(self):
        # Materia Blade+ ranks between these two real RCC items. Its normal
        # replacement should follow the next item's existing reverse-rank
        # mutation, with the same RNG draws, rather than join the output pool.
        items = {0: dict(Price=0, RequiredLevel=0),
                 1: dict(Price=100, RequiredLevel=1),
                 2: dict(Price=3000, RequiredLevel=1),
                 3: dict(Price=10, RequiredLevel=98),
                 4: dict(Price=10, RequiredLevel=99)}
        extended = {256: dict(Price=10, RequiredLevel=97)}
        original_items, original_extended = copy.deepcopy(items), copy.deepcopy(extended)
        for spread in (0, .25, .5, 1):
            for seed in range(20):
                expected_rng, actual_rng = random.Random(seed), random.Random(seed)
                expected = get_similar_item(3, items, expected_rng, 1.5, spread)
                actual = get_similar_item(256, items, actual_rng, 1.5, spread,
                                          extended_items=extended)
                self.assertEqual(expected, actual)
                self.assertEqual(expected_rng.getstate(), actual_rng.getstate())
                self.assertIn(actual, (1, 2, 3, 4))
        self.assertEqual(items, original_items)
        self.assertEqual(extended, original_extended)

    def test_extended_metadata_does_not_change_ordinary_items_or_rng(self):
        items = {index: dict(Price=(index*211)%65001, RequiredLevel=index%99)
                 for index in range(256)}
        extended = {256: dict(Price=10, RequiredLevel=97)}
        for spread in (.25, .5):
            for seed in range(20):
                expected_rng, actual_rng = random.Random(seed), random.Random(seed)
                for item in (1, 32, 106, 143, 200, 253):
                    expected = get_similar_item(item, items, expected_rng, 1.5, spread)
                    actual = get_similar_item(item, items, actual_rng, 1.5, spread,
                                              extended_items=extended)
                    self.assertEqual(expected, actual)
                    self.assertEqual(expected_rng.getstate(), actual_rng.getstate())

    def test_materia_blade_plus_move_find_handles_ordinary_branch_at_half_spread(self):
        items = {index: dict(Price=(index*211)%65001, RequiredLevel=index%99)
                 for index in range(256)}
        original_items = copy.deepcopy(items)
        extended = {256: dict(Price=10, RequiredLevel=97)}
        # This is the exact original reward slot that failed for the user's
        # seed. Seed0 chooses the ordinary branch, which needs rank guidance.
        row = dict(X4=8, Y4=9, TrapFlags4=2, CommonItemId4=256, RareItemId4=256)
        self.assertFalse(random.Random(0).choice((True, False)))
        self.assertTrue(mutate_move_find(row, 4, 75, {}, items, random.Random(0),
                                        random_degree=.5, extended_items=extended))
        self.assertEqual((row['X4'], row['Y4']), (8, 9))
        for field in ('CommonItemId4', 'RareItemId4'):
            self.assertGreaterEqual(row[field], 0)
            self.assertLess(row[field], 254)
        self.assertEqual(items, original_items)
        self.assertNotIn(256, items)

    def test_unknown_extended_items_and_sentinels_are_still_rejected(self):
        items = {index: dict(Price=100+index, RequiredLevel=1) for index in range(256)}
        for item in (0, 254, 255, 256, 261):
            with self.subTest(item=item), self.assertRaises(ValueError):
                get_similar_item(item, items, random.Random(0))
        with self.assertRaises(ValueError):
            get_similar_item(261, items, random.Random(0),
                             extended_items={256: dict(Price=10, RequiredLevel=97)})

    @unittest.skipUnless((Path(__file__).resolve().parents[2]/'FFT_enhanced.exe').is_file(),
                         'Requires original Enhanced files')
    def test_actual_extended_item_metadata_is_private_and_byte_pools_stay_unchanged(self):
        tables, _ = read_game(Path(__file__).resolve().parents[2])
        extended = tables['_ExtendedItemData']
        self.assertEqual(set(extended), set(range(256, 261)))
        self.assertEqual(extended[256]['Price'], 10)
        self.assertEqual(extended[256]['RequiredLevel'], 97)
        self.assertEqual(extended[256]['AdditionalDataId'], 32)
        self.assertEqual(extended[256]['EquipBonusId'], 84)
        self.assertEqual(set(tables['ItemData']), set(range(256)))
        self.assertEqual(set(ranked_items(tables['ItemData'])), set(range(1, 254)))
        for seed in range(20):
            reward = get_similar_item(256, tables['ItemData'], random.Random(seed),
                                      1.5, .5, extended_items=extended)
            self.assertGreater(reward, 0)
            self.assertLess(reward, 254)


class RCCNativeWorldTests(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).resolve().parents[2]/'FFT_enhanced.exe').is_file(), 'Requires original Enhanced files')
    def test_native_world_anchors_and_sparse_patch_bytes(self):
        game = Path(__file__).resolve().parents[2]
        specs, tables = read_native_world(game/'FFT_enhanced.exe')
        before = dict(_RCCNativeWorldTables=specs, _RCCEncounters=tables['Encounter'], _RCCFormations=tables['Formation'])
        result = copy.deepcopy(before)
        result['_RCCEncounters'][2]['music'][1] = 3
        plans = commit_world_patches(before, result)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]['rva'], 0x8ECAB0)
        changed = [index for index, (old, new) in enumerate(zip(plans[0]['expected'], plans[0]['data'])) if old != new]
        self.assertEqual(changed, [2*24+6])
        self.assertEqual(len(tables['Formation']), 768)
        self.assertEqual(len(tables['Encounter']), 887)


if __name__ == '__main__':
    unittest.main()
