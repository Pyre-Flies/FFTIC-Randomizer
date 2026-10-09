"""Formation proxies and literal f behavior compared with the old RCC checkout."""
import ast
import copy
from pathlib import Path
import random
import re
import textwrap
import unittest

from fftic.game import read_game
from fftic.catalog import attach_catalog
from fftic.rcc_encounter_data import prepare_unit_context,decode_entry
from fftic.rcc_world_data import read_native_world
from fftic.rcc_maps import attach_maps
from fftic.rcc_units import native_rankings
from fftic.rcc_formations import FormationEngine,NativeMap,NativeFormation,apply_formations,_IntegerDivision
from test_rcc_reference import SOURCE,reference_environment,source_function


PROJECT = Path(__file__).resolve().parents[1]


def source_member(owner,name,environment):
    """Extract original class bodies including classes without base classes."""
    lines = (SOURCE/'randomizer.py').read_text(encoding='utf-8').splitlines()
    start = next(i for i,line in enumerate(lines) if line.startswith('class '+owner+':') or line.startswith('class '+owner+'('))
    begin = next(i for i in range(start+1,len(lines)) if lines[i].startswith('    def '+name+'('))
    end = begin+1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.lstrip().startswith('#') and len(line)-len(line.lstrip()) <= 4:
            break
        end += 1
    snippet = textwrap.dedent('\n'.join(lines[begin:end])).replace('xrange(','range(')
    snippet = re.sub(r'(?m)^(\s*)print .+$',r'\1pass',snippet)
    # Bare print only occurs in a commented/triple-quoted debug passage here.
    tree = _IntegerDivision().visit(ast.parse(snippet))
    ast.fix_missing_locations(tree)
    exec(compile(tree,'<original RCC '+owner+'.'+name+'>','exec'),environment)
    return environment[name]


class IterableTable:
    def __init__(self,objects):
        self.every = list(objects)
        self.get = {obj.index:obj for obj in self.every}.get
    def __iter__(self): return iter(self.every)


class SourceTile:
    def __init__(self,row): self.row = row
    def __getattr__(self,name): return self.row[name]
    def __setattr__(self,name,value):
        if name=='row': object.__setattr__(self,name,value)
        else: self.row[name] = value


def original_world(engine):
    """Replace the proxy operations with compiled original Map/Tile methods."""
    env = engine.environment
    env.update(reference_environment(engine.random))
    encounter_table = IterableTable(engine.encounters.values())
    env['EncounterObject'] = encounter_table
    for name in ('bad','bad_regardless'):
        setattr(SourceTile,name,property(source_member('TileObject',name,env)))
    for name in ('set_occupied','set_party'):
        setattr(SourceTile,name,source_member('TileObject',name,env))
    class SourceMap(NativeMap): pass
    for name in ('encounter','unused_units','units','nonmoving_units','moving_units','map_movements','move_units','tile_grid'):
        setattr(SourceMap,name,property(source_member('MapObject',name,env)))
    for name in ('set_occupied','set_entd_occupied_movers','get_tile','get_tile_value','get_tile_values','get_values_grid'):
        setattr(SourceMap,name,source_member('MapObject',name,env))
    engine.MapObject.all_map_movements = {mid:list(group[0].row.get('moves',[])) for mid,group in engine.maps.items()}
    engine.MapObject.all_move_units = {mid:sorted({u for u,x,y in group[0].row.get('moves',[])}) for mid,group in engine.maps.items()}
    for mid,group in list(engine.maps.items()):
        originals = []
        for obj in group:
            replacement = SourceMap(engine,mid,obj.index,obj.row)
            replacement.tiles = [SourceTile(replacement._cell(i%replacement.width,i//replacement.width)) for i in range(256)]
            originals.append(replacement)
        engine.maps[mid] = originals
    class SourceFormation(NativeFormation): pass
    SourceFormation.pick_correct_orientation = source_member('FormationObject','pick_correct_orientation',env)
    engine.formations = {i:SourceFormation(engine,i,f.row) for i,f in engine.formations.items()}
    engine.FormationObject.every = list(engine.formations.values())
    engine.FormationObject.get = engine.formations.get
    generate = source_member('EncounterObject','generate_formations',env)
    tree = _IntegerDivision().visit(source_function('randomizer.py','randomize_enemy_formations'))
    ast.fix_missing_locations(tree)
    exec(compile(tree,'<original RCC enemy formations>','exec'),env)
    enemies = env['randomize_enemy_formations']
    return generate,enemies,encounter_table


def flat_map(width=16,length=16,moves=()):
    tile = dict(terrain_type=0,height=3,depth=0,slope_height=0,slope_type=0,
                impassable=0,uncursorable=0,occupied=0,party=0,upper=0,unreachable=0)
    return dict(width=width,length=length,cells=[dict(tile) for _ in range(width*length)],moves=list(moves))


@unittest.skipUnless((SOURCE/'randomizer.py').is_file() and (PROJECT.parent/'FFT_enhanced.exe').is_file(),
                     'Requires supplied RCC source and verified local game')
class RCCFormationReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before,_ = read_game(PROJECT.parent)
        attach_catalog(cls.before,PROJECT.parent,PROJECT)
        prepare_unit_context(cls.before,PROJECT.parent,PROJECT)
        native_rankings(cls.before)
        _,world = read_native_world(PROJECT.parent/'FFT_enhanced.exe')
        cls.before.update(_RCCEncounters=world['Encounter'],_RCCFormations=world['Formation'])
        attach_maps(cls.before,PROJECT.parent,PROJECT,'formation-reference')

    def fixture(self,*,moves=(),variants=1):
        before = copy.deepcopy(self.before)
        encounter = dict(before['_RCCEncounters'][2])
        encounter.update(map_id=1,entd=387,event=100,grid=1,grid2=0)
        before['_RCCEncounters'] = {2:encounter}
        before['_RCCMaps'] = {1:[flat_map(moves=moves) for _ in range(variants)]}
        before['_RCCFormations'][1].update(bitmap=0x1F,num_characters=5,map_number=1)
        before['_RCCUnitContext'] = {owner:row for owner,row in before['_RCCUnitContext'].items() if owner[0]==387}
        # Native opening rows contain dormant jobs rather than truly unused
        # records. Provide six actual empty slots to exercise RCC's5-slot reserve.
        for slot in range(10,16):
            before['_RCCUnitContext'][387,slot] = decode_entry(bytes(40))
        return before

    def test_all_native_maps_initialize_with_script_movers_and_exact_capacity(self):
        result = copy.deepcopy(self.before)
        engine = FormationEngine(self.before,result,random.Random(89))
        self.assertEqual(len(engine.maps),121)
        self.assertEqual(len(engine.encounters),887)
        self.assertEqual(len(engine.formations),768)
        for group in engine.maps.values():
            for terrain in group:
                for unit in terrain.moving_units:
                    self.assertTrue(terrain.get_tile_value(unit.x,unit.y,'occupied'))
        self.assertEqual(engine.get_unused_formation().index,
                         max(i for i,row in self.before['_RCCFormations'].items() if i and not row['bitmap']))

    def test_orientation_matches_original_source_and_rng(self):
        before = self.fixture()
        for seed in range(12):
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            expected = FormationEngine(before,copy.deepcopy(before),source_rng)
            actual = FormationEngine(before,copy.deepcopy(before),port_rng)
            original = source_member('FormationObject','pick_correct_orientation',expected.environment)
            for x,y in ((2,2),(13,2),(2,13),(13,13),(8,8),(7,7)):
                for engine in (expected,actual):
                    engine.formations[1].x,engine.formations[1].z = x,y
                original(expected.formations[1])
                actual.formations[1].pick_correct_orientation()
                self.assertEqual(actual.formations[1].orientation,expected.formations[1].orientation)
                self.assertEqual(port_rng.getstate(),source_rng.getstate())

    def test_generated_regions_match_original_bitmap_centers_and_rng(self):
        for seed in range(8):
            before = self.fixture(variants=2)
            # A disagreement between variants produces None in the source
            # certainty map, including the mixed None/numeric height set.
            before['_RCCMaps'][1][1]['cells'][40]['height'] = 7
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            source_tables,port_tables = copy.deepcopy(before),copy.deepcopy(before)
            expected = FormationEngine(before,source_tables,source_rng)
            actual = FormationEngine(before,port_tables,port_rng)
            original,_,_ = original_world(expected)
            expected_result = original(expected.encounters[2])
            actual_result = actual.encounters[2].generate_formations()
            self.assertEqual(actual_result,expected_result)
            self.assertEqual(port_tables['_RCCEncounters'],source_tables['_RCCEncounters'])
            self.assertEqual(port_tables['_RCCFormations'],source_tables['_RCCFormations'])
            self.assertEqual(port_tables['_RCCMaps'],source_tables['_RCCMaps'])
            self.assertEqual(port_rng.getstate(),source_rng.getstate())
            for key in ('grid','grid2'):
                index = port_tables['_RCCEncounters'][2][key]
                if index and index != 1:
                    row = port_tables['_RCCFormations'][index]
                    self.assertGreaterEqual(row['bitmap'].bit_count(),row['num_characters'])
                    self.assertLess(row['bitmap'],1<<25)

    def test_complete_heatmap_cloning_team_flags_and_reserve_match_source(self):
        before = self.fixture()
        added = 0
        for seed in (1,4,7,11):
            source_rng,port_rng = random.Random(seed),random.Random(seed)
            source_tables,port_tables = copy.deepcopy(before),copy.deepcopy(before)
            expected = FormationEngine(before,source_tables,source_rng)
            original,enemies,table = original_world(expected)
            original(expected.encounters[2])
            enemies()
            audit = apply_formations(before,port_tables,str(seed),environment={'random':port_rng})
            self.assertEqual(port_tables['_RCCEncounters'],source_tables['_RCCEncounters'])
            self.assertEqual(port_tables['_RCCFormations'],source_tables['_RCCFormations'])
            for owner,row in port_tables['_RCCUnitContext'].items():
                self.assertEqual(row,source_tables['_RCCUnitContext'][owner],(seed,owner))
            self.assertEqual(port_rng.getstate(),source_rng.getstate())
            added += len(audit['added_units'])
            remaining = [r for (entd,slot),r in port_tables['_RCCUnitContext'].items()
                         if entd==387 and not r['Spriteset'] and not r['MainJob']]
            self.assertGreaterEqual(len(remaining),5)
            for owner in audit['added_units']:
                row = port_tables['_RCCUnitContext'][tuple(owner)]
                self.assertEqual(row['UnitId'],128|owner[1])
                self.assertEqual(row['NameId'],255)
                self.assertTrue(row['Flags2']&128)
                self.assertFalse(row['Flags2']&64)
        self.assertGreater(added,0,'The reference seeds must exercise clone allocation')

    def test_script_mover_properties_match_original(self):
        before = self.fixture(moves=((128,3,3),(1,4,4)))
        expected = FormationEngine(before,copy.deepcopy(before),random.Random(0))
        actual = FormationEngine(before,copy.deepcopy(before),random.Random(0))
        original_world(expected)
        for attr in ('units','unused_units','moving_units','nonmoving_units'):
            self.assertEqual([u.index for u in getattr(actual.get_map(1),attr)],
                             [u.index for u in getattr(expected.get_map(1),attr)])
        for unit in actual.get_map(1).moving_units:
            self.assertTrue(actual.get_map(1).get_tile_value(unit.x,unit.y,'occupied'))

    def test_unsupported_added_map_is_preserved_and_reported(self):
        before = self.fixture()
        before['_RCCEncounters'] = {506:copy.deepcopy(self.before['_RCCEncounters'][506])}
        result = copy.deepcopy(before)
        audit = apply_formations(before,result,'unsupported')
        self.assertEqual(result['_RCCEncounters'],before['_RCCEncounters'])
        self.assertEqual(result['_RCCFormations'],before['_RCCFormations'])
        self.assertEqual(result['_RCCUnitContext'],before['_RCCUnitContext'])
        self.assertEqual(audit['unsupported_encounters'][0]['map_id'],127)
        self.assertEqual(audit['unsupported_encounters'][0]['entd'],519)
        self.assertEqual(audit['selected_encounters'],[])

    def test_zero_degree_and_missing_original_terrain_are_explicit(self):
        result = {}
        audit = apply_formations({},result,'zero',degree=0)
        self.assertEqual(result,{})
        self.assertEqual(audit['changed_units'],0)
        before = self.fixture()
        before['_RCCEncounters'][2]['map_id'] = 126
        with self.assertRaisesRegex(ValueError,'terrain.*map126'):
            apply_formations(before,copy.deepcopy(before),'missing')


if __name__ == '__main__':
    unittest.main()
