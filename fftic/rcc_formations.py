"""RCC f formation regions, unit heatmaps and extra units on native FFTIC data.

The two large algorithms execute from the bundled RCC source bodies. Proxies
adapt native tables and terrain while preserving their source iteration,
allocation, script-mover and clone rules. No game files are written here.
"""
import ast
import builtins
from copy import deepcopy
import math
from pathlib import Path
from types import SimpleNamespace

from .rcc import rng_for,remember_rng
from .rcc_maps import certain_values, value as tile_value
from .rcc_units import UnitEngine


SOURCE_METHODS = Path(__file__).with_name('data') / 'rcc-event-methods.py'
NO_TERRAIN_MAP = 127
NO_TERRAIN_REASON = ('FFTIC map127 has no original RCC terrain mesh; preserve '
                     'its deployment grids and unit coordinates')


def _py2_sorted(values, *args, **kwargs):
    values = list(values)
    # RCC sorts the cross-variant height set before removing None. Python2
    # places None before numbers; only that mixed type occurs in these rules.
    if not args and not kwargs.get('key') and any(v is None for v in values):
        return builtins.sorted(values, key=lambda v:(v is not None,v if v is not None else 0),
                               **kwargs)
    return builtins.sorted(values, *args, **kwargs)


def slice_array_2d(data, x=0, width=0, y=0, length=0):
    result = [row[x:x+width] for row in data][y:y+length]
    if len(result) != length or not result or len(result[0]) != width:
        raise ValueError('RCC formation rectangle is outside verified terrain')
    return result


class _IntegerDivision(ast.NodeTransformer):
    def visit_BinOp(self, node):
        self.generic_visit(node)
        # These literal functions divide integer map widths, character counts,
        # integer distances and integer heatmap values, as Python2 did.
        if isinstance(node.op, ast.Div):
            node.op = ast.FloorDiv()
        return node


def compile_formation_methods(environment, *, source=None):
    """Load only f's two checked-in source functions into explicit bindings."""
    path = Path(source) if source else SOURCE_METHODS
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    names = {'generate_formations','randomize_enemy_formations'}
    functions = [node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    if {node.name for node in functions} != names:
        raise ValueError('Bundled RCC formation functions are missing')
    selected = ast.Module(body=functions,type_ignores=[])
    selected = _IntegerDivision().visit(selected)
    # Replace the original interactive debugger, which is unreachable with
    # verified rectangles, with a regular diagnostic if an input is broken.
    for node in ast.walk(selected):
        if isinstance(node,ast.ExceptHandler) and any(isinstance(n,ast.Import) and
            any(a.name=='pdb' for a in n.names) for n in node.body):
            node.body = [ast.Raise(exc=ast.Call(func=ast.Name(id='ValueError',ctx=ast.Load()),
                args=[ast.Constant('RCC formation rectangle is outside verified terrain')],keywords=[]),cause=None)]
    ast.fix_missing_locations(selected)
    environment.update(zip=lambda *args:list(builtins.zip(*args)),
                       range=lambda *args:list(builtins.range(*args)),sorted=_py2_sorted,
                       slice_array_2d=slice_array_2d)
    exec(compile(selected,str(path),'exec'),environment)
    return {name:environment[name] for name in names}


class NativeFormation:
    def __init__(self, engine, index, row):
        object.__setattr__(self,'engine',engine)
        object.__setattr__(self,'index',index)
        object.__setattr__(self,'row',row)
    def __getattr__(self,name):
        if name in self.row: return self.row[name]
        raise AttributeError(name)
    def __setattr__(self,name,value):
        if name in self.row: self.row[name] = value
        else: object.__setattr__(self,name,value)
    @property
    def my_map(self): return self.engine.get_map(self.map_number)
    @property
    def facing(self): return self.orientation >> 4
    @property
    def rotation(self): return self.orientation & 15
    @property
    def pretty_facing(self):
        return {0:'west',1:'south',2:'east',3:'north'}[(self.rotation+self.facing)%4]
    def pick_correct_orientation(self):
        # RCC FormationObject.pick_correct_orientation, original integer halves.
        margin_x = min(self.x,self.my_map.width-(self.x+1))
        margin_z = min(self.z,self.my_map.length-(self.z+1))
        if margin_x > margin_z or (margin_x == margin_z and self.engine.random.choice([True,False])):
            self.orientation = 3 if self.z < self.my_map.length//2 else 1
        else:
            self.orientation = 2 if self.x < self.my_map.width//2 else 0
    def mutate(self,reduce_formations=False):
        # f calls mutate() without the opt-in reduction flag: source no-op.
        if reduce_formations:
            raise ValueError('Formation reduction is not part of RCC f')


class NativeEncounter:
    def __init__(self,engine,index,row):
        object.__setattr__(self,'engine',engine)
        object.__setattr__(self,'index',index)
        object.__setattr__(self,'row',row)
    def __getattr__(self,name):
        if name in self.row: return self.row[name]
        raise AttributeError(name)
    def __setattr__(self,name,value):
        if name in self.row: self.row[name] = value
        else: object.__setattr__(self,name,value)
    @property
    def mutated(self):
        return bool(getattr(self,'_mutated',False) or self.index in self.engine.replaced)
    @property
    def grids(self):
        return [self.engine.formations[g] for g in (self.grid,self.grid2) if g or g == self.grid]
    @property
    def num_characters(self): return min(sum(f.num_characters for f in self.grids),5)
    @property
    def is_event(self): return 256 <= self.entd <= 469 and (self.event != 0 or self.entd == 256)
    @property
    def is_fake_event(self): return 257 <= self.entd <= 469 and self.event == 0
    def generate_formations(self,corner=False,numchar_override=None):
        return self.engine.methods['generate_formations'](self,corner,numchar_override)


class NativeMap:
    def __init__(self,engine,map_id,index,row):
        self.engine,self.map_id,self.index,self.row = engine,map_id,index,row
        self.width,self.length = row['width'],row['length']
        self.padding = {}
    @property
    def move_units(self): return sorted({u for u,x,y in self.row.get('moves',[])})
    @property
    def map_movements(self): return list(self.row.get('moves',[]))
    @property
    def encounter(self):
        return next((e for e in self.engine.encounters.values() if e.event and e.entd and e.grid
                     and e.map_id == self.map_id),None)
    @property
    def units(self):
        return sorted((u for u in self.engine.unit_engine.mapunits.get(self.encounter.entd,[])
                       if u.graphic > 0),key=lambda u:u.index) if self.encounter else []
    @property
    def unused_units(self):
        return sorted((u for u in self.engine.unit_engine.mapunits.get(self.encounter.entd,[])
                       if u.graphic == 0 and u.job == 0),key=lambda u:u.index) if self.encounter else []
    @property
    def nonmoving_units(self):
        units = self.units
        if any(u & 128 for u in self.move_units):
            units = [u for u in units if u.graphic <= 127]
        return [u for u in units if u.graphic not in self.move_units]
    @property
    def moving_units(self): return [u for u in self.units if u not in self.nonmoving_units]
    def _cell(self,x,y):
        # Source get_tile uses a flat256-tile array, without an x-bound check.
        # Preserve its row-wrap behavior when a heatmap probes adjacent tiles.
        index = x + self.width*y
        if not 0 <= index < 256:
            raise IndexError('Native terrain tile is outside original256-tile array')
        if index < len(self.row['cells']):
            return self.row['cells'][index]
        return self.padding.setdefault(index,dict(occupied=0,party=0,upper=0,unreachable=0,
            terrain_type=0,height=0,depth=0,slope_height=0,slope_type=0,impassable=0,uncursorable=0))
    def get_tile_value(self,x,y,attribute): return tile_value(self._cell(x,y),attribute)
    def get_tile_values(self,attribute):
        return [self.get_tile_value(i%self.width,i//self.width,attribute) for i in range(256)]
    def get_values_grid(self,attribute):
        return [[self.get_tile_value(x,y,attribute) for x in range(self.width)] for y in range(self.length)]
    def set_occupied(self,x,y,party=False):
        tile = self._cell(x,y)
        if party:
            if tile['occupied']:
                raise ValueError('RCC party formation overlaps occupied terrain')
            tile['party'] = 1
        tile['occupied'] = 1
    def set_entd_occupied_movers(self):
        for unit in self.moving_units:
            self.set_occupied(unit.x,unit.y)
    @property
    def tile_count_good(self):
        return sum(not self.get_tile_value(x,y,'bad_regardless') for y in range(self.length) for x in range(self.width))


class FormationEngine:
    """World adapters sharing the UnitEngine's canonical rows and source state."""
    def __init__(self,before,result,rng,chaos=1,random_degree=.25,*,unit_engine=None,environment=None):
        self.before,self.tables,self.random = before,result,rng
        self.unit_engine = unit_engine or result.get('_RCCUnitEngine') or UnitEngine(before,result,rng,chaos,random_degree)
        self.unit_engine.random = rng
        self.unit_engine.random_degree = random_degree
        self.unit_engine.boostd['difficulty_factor'] = chaos
        self.replaced = set(result.get('_RCCReplacedMaps',[]))
        self.formations = {i:NativeFormation(self,i,row) for i,row in sorted(result['_RCCFormations'].items())}
        self.encounters = {i:NativeEncounter(self,i,row) for i,row in sorted(result['_RCCEncounters'].items())}
        self.maps = {map_id:[NativeMap(self,map_id,index,row) for index,row in enumerate(variants)]
                     for map_id,variants in result['_RCCMaps'].items()}
        for variants in self.maps.values():
            for terrain in variants:
                terrain.set_entd_occupied_movers()
        self.MapObject = SimpleNamespace(get_map=self.get_map,get_by_map_id=lambda i:self.maps.get(i,[]),
            get_most_good=lambda i:max(self.maps[i],key=lambda m:(m.tile_count_good,-m.index)),
            get_certain_values_map_id=lambda i,attr:certain_values([m.row for m in self.maps[i]],attr),
            every=[m for group in self.maps.values() for m in group])
        self.FormationObject = SimpleNamespace(every=list(self.formations.values()),get=self.formations.get,
                                              get_unused=self.get_unused_formation)
        self.EncounterObject = SimpleNamespace(every=list(self.encounters.values()),get=self.encounters.get)
        self.environment = self.unit_engine.source_environment()
        self.environment.update(MapObject=self.MapObject,FormationObject=self.FormationObject,
                                EncounterObject=self.EncounterObject)
        if environment:
            self.environment.update(environment)
        self.methods = compile_formation_methods(self.environment)
    def get_map(self,map_id,index=0):
        if map_id not in self.maps:
            raise ValueError(f'RCC formation terrain is missing for map{map_id}')
        return self.maps[map_id][index]
    def get_unused_formation(self):
        candidates = [f for f in self.formations.values() if f.bitmap == 0 and f.index != 0]
        if not candidates:
            raise ValueError('Native formation capacity exhausted')
        return candidates[-1]


def apply_formations(before,result,seed,chaos=1,random_degree=.25,degree=1,*,environment=None):
    """Run f's source loop and return a JSON-serializable deployment/unit audit."""
    if not math.isfinite(degree) or not 0 <= degree <= 1:
        raise ValueError('Formation degree must be0 to1')
    if not math.isfinite(chaos) or chaos < 0:
        raise ValueError('Formation chaos must be nonnegative and finite')
    if not math.isfinite(random_degree) or not 0 <= random_degree <= 1:
        raise ValueError('Formation normal mutation degree must be0 to1')
    audit = dict(source='RCC f formation regions and enemy heatmaps',selected_encounters=[],
                 generated_encounters=[],changed_encounters=[],changed_formations=[],
                 changed_units=0,added_units=[],unsupported_encounters=[],
                 script_movers_preserved=True,clone_reserve_slots=5)
    if not degree:
        return audit
    for name in ('_RCCEncounters','_RCCFormations','_RCCMaps','_RCCUnitContext'):
        if name not in result:
            raise ValueError('RCC f requires verified '+name)
    old_encounters = deepcopy(result['_RCCEncounters'])
    old_formations = deepcopy(result['_RCCFormations'])
    old_units = deepcopy(result['_RCCUnitContext'])
    rng = (environment or {}).get('random') or rng_for(seed,'formations-f')
    initial_state = rng.getstate()
    engine = FormationEngine(before,result,rng,chaos,random_degree,environment=environment)
    candidates = []
    for enc in engine.encounters.values():
        if not (enc.map_id and enc.entd and enc.event and enc.grid):
            continue
        if enc.map_id not in engine.maps:
            if enc.map_id == NO_TERRAIN_MAP:
                audit['unsupported_encounters'].append(dict(index=enc.index,map_id=enc.map_id,
                                                          entd=enc.entd,reason=NO_TERRAIN_REASON))
                continue
            raise ValueError(f'Original RCC terrain is absent for eligible map{enc.map_id}')
        if degree == 1 or rng.random() < degree:
            candidates.append(enc)
    audit['selected_encounters'] = [enc.index for enc in candidates]
    selected = engine.unit_engine.selected
    engine.unit_engine.selected = None  # u's partial-row mask must not skip f clones.
    try:
        for formation in engine.formations.values():
            if formation.bitmap and formation.num_characters:
                formation.mutate()
        # Source5183 reseeds before generating deployment/ENEMY formations.
        rng.setstate(initial_state)
        for enc in candidates:
            while True:
                generated = enc.generate_formations()
                if generated:
                    audit['generated_encounters'].append(enc.index)
                if generated or not enc.mutated:
                    break
        # The original placement function reads every eligible encounter; a
        # partial f run exposes only its selected candidates to that function.
        engine.EncounterObject.every = candidates
        engine.methods['randomize_enemy_formations']()
    finally:
        engine.unit_engine.selected = selected
    audit['changed_encounters'] = [i for i,row in result['_RCCEncounters'].items() if row != old_encounters[i]]
    audit['changed_formations'] = [i for i,row in result['_RCCFormations'].items() if row != old_formations[i]]
    audit['changed_units'] = sum(row != old_units[owner] for owner,row in result['_RCCUnitContext'].items())
    audit['added_units'] = [list(owner) for owner,row in result['_RCCUnitContext'].items()
                            if not old_units[owner]['Spriteset'] and not old_units[owner]['MainJob'] and row['Spriteset']]
    audit['allocated_formation_count'] = len(audit['changed_formations'])
    audit['terrain_map_count'] = len(engine.maps)
    result['_RCCUnitEngine'] = engine.unit_engine
    remember_rng(result,rng)
    return audit
