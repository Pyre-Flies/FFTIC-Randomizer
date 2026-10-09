"""RCC z weather, z+f maps and postmusic Warjilis encounter table data.

Source randomizer.py970-983,4415-4602,5167-5177,5218-5223.
Event37/script/conditional resources remain parent-owned. All mutations here
are row-backed native ENTD, Encounter, Formation and terrain state.
"""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from .rcc import rng_for,remember_rng,continuation_rng
from .rcc_formations import FormationEngine
from .rcc_specials import SourceTable,special_environment,IntegerDivision
from .rcc_music import randomize_music


FIXED_WEATHER = {415,437,450}
CANDIDATE_MAPS = (1,4,8,9,11,14,15,18,20,21,23,24,26,37,38,41,43,46,48,51,53,
                  62,65,68,71,72,73,75,76,92,93,94,95,96,97,98,99,100,101,102,104,
                  115,116,117,118,119,125)


def randomize_weather(row,rng):
    oldnight,oldweather = row['night'],row['weather']
    if row['weather']<=4:
        row['night'] = 1 if rng.randint(1,7)==7 else 0
        row['weather'] = rng.choice((1,2,3,4)) if rng.randint(1,4)==4 else 0
    if row['entd'] in FIXED_WEATHER: row['night'],row['weather'] = oldnight,oldweather


class SourceItem:
    def __init__(self,index,row): self.index,self.row = index,row
    @property
    def itemtype(self): return self.row['ItemCategory']
    @property
    def misc1(self): return self.row['TypeFlags']
    @property
    def price(self): return self.row['Price']
    @property
    def enemy_level(self): return self.row['RequiredLevel']
    @property
    def rank(self):
        return -1 if not self.index else self.price+(65000+self.enemy_level*100 if self.price<=10 or self.index in (106,143) else 0)
    def get_bit(self,name):
        names = ('z0','rare','unk1','accessory','body','head','shield','weapon')
        return bool(self.misc1&(1<<names.index(name)))


class SurpriseEncounter:
    def __init__(self,world,original):
        object.__setattr__(self,'world',world)
        object.__setattr__(self,'original',original)
        object.__setattr__(self,'index',original.index)
        object.__setattr__(self,'row',original.row)
    def __getattr__(self,name):
        if name in self.row: return self.row[name]
        return getattr(self.original,name)
    def __setattr__(self,name,value):
        if name in self.row: self.row[name] = value
        else: object.__setattr__(self,name,value)
    def copy_data(self,other): self.row.update(deepcopy(other.row))
    def randomize_weather(self): randomize_weather(self.row,self.world.unit.random)
    def randomize_music(self,prefer_unused=False,force_battle=False):
        randomize_music(self.row,self.index,self.world.unit.random,self.world.used_music,prefer_unused,force_battle)
    def mutate_map(self):
        candidates = self.world.get_candidate_maps()
        chosen = self.world.unit.random.choice(candidates)
        self.map_id = chosen.map_id
        candidates.remove(chosen)
        self.original._mutated = True
        self.world.formation.replaced.add(self.index)


class SurpriseWorld:
    def __init__(self,before,result,rng,chaos=1,random_degree=.25,*,environment=None):
        self.before,self.tables = before,result
        self.env = special_environment(before,result,rng,chaos,random_degree,environment=environment)
        self.unit = self.env['_UNIT_ENGINE']
        self.unit.items = {i:SourceItem(i,r) for i,r in result['ItemData'].items()}
        self.unit.ItemObject = SourceTable(self.unit.items,ranked=self.unit.get_ranked_items())
        self.formation = FormationEngine(before,result,rng,chaos,random_degree,unit_engine=self.unit,environment=self.env)
        self.encounters = {i:SurpriseEncounter(self,e) for i,e in self.formation.encounters.items()}
        self.used_music = result.setdefault('_RCCUsedMusic',set())
        self.candidates = None
        table = SourceTable(self.encounters)
        table.get_unused = self.get_unused
        table.get_replaceable_maps = self.get_replaceable_maps
        table.get_candidate_maps = self.get_candidate_maps
        self.env.update(EncounterObject=table,MapObject=self.formation.MapObject,
                        FormationObject=self.formation.FormationObject,ItemObject=self.unit.ItemObject,
                        RERAISE_STATUS=0x200000,JAPANESE_MODE=False)
        from itertools import product
        self.env['product'] = product
        # Nested generate_formations reads the world environment too.
        self.formation.environment.update(self.env)
    def get_unused(self):
        unused = next((e for e in self.encounters.values() if not(e.map_id or e.event or e.entd or e.next_scene or e.following)),None)
        if unused is None: raise ValueError('Native encounter capacity exhausted while restoring Warjilis')
        unused.scenario = max(e.scenario for e in self.encounters.values())+1
        return unused
    def get_replaceable_maps(self):
        eligible = [e for e in self.encounters.values() if e.event and e.entd and
                    (384<=e.entd<=469 or e.entd>=512) and e.entd not in (388,389,450)
                    and e.map_id in self.formation.maps and not self.formation.get_map(e.map_id).move_units]
        return sorted(eligible,key=lambda e:e.entd)
    def get_candidate_maps(self):
        if self.candidates is None:
            self.candidates = [self.formation.MapObject.get_most_good(m) for m in CANDIDATE_MAPS]
        return self.candidates


def apply_weather(before,result,seed,flags,*,environment=None):
    if 'z' not in flags: return dict(changed_rows=0)
    env = environment or result.get('_RCCSpecialEnvironment')
    rng = env['random'] if env else rng_for(seed,'specials-z')
    changed = []
    for i,row in sorted(result['_RCCEncounters'].items()):
        old = row['night'],row['weather'];randomize_weather(row,rng)
        if old!=(row['night'],row['weather']): changed.append(i)
    remember_rng(result,rng)
    return dict(source='RCC970-983,5157-5158',changed_rows=len(changed),rows=changed,
                protected_entds=sorted(FIXED_WEATHER))


def apply_map_surprises(before,result,seed,flags,chaos=1,random_degree=.25,*,environment=None):
    if not {'z','f'}<=set(flags): return dict(changed_rows=0)
    rng = (environment or {}).get('random') or rng_for(seed,'maps-zf')
    world = SurpriseWorld(before,result,rng,chaos,random_degree,environment=environment)
    choices = world.get_replaceable_maps()
    if not choices: return dict(changed_rows=0,rows=[])
    count = world.unit.mutate_normal(len(choices)//2,0,len(choices))
    count = max(count,1)
    count = world.unit.randint(count,world.unit.randint(count,len(choices)))
    selected = rng.sample(choices,count)
    changes = []
    for e in selected:
        old = e.map_id;e.mutate_map();changes.append(dict(index=e.index,entd=e.entd,before=old,after=e.map_id))
    result['_RCCReplacedMaps'] = sorted(world.formation.replaced)
    remember_rng(result,rng)
    return dict(source='RCC5167-5177',changed_rows=len(changes),rows=changes,
                candidates=len(choices),unsupported_maps=[127] if any(e.event and e.entd>=512 and e.map_id==127 for e in world.encounters.values()) else [])


def compile_restore_warjilis(environment):
    tree = IntegerDivision().visit(ast.parse(WARJILIS_SOURCE,filename='<RCC restore_warjilis table source>'))
    ast.fix_missing_locations(tree)
    import builtins
    environment.update(range=lambda *a:list(builtins.range(*a)),xrange=range)
    exec(compile(tree,'<RCC restore_warjilis table source>','exec'),environment)
    return environment['restore_warjilis_data']


def apply_warjilis(before,result,seed,flags,chaos=1,random_degree=.25,*,environment=None):
    if 'z' not in flags: return dict(changed_units=0,encounters=[])
    # This phase intentionally continues the preceding music/items/shop RNG.
    rng = (environment or {}).get('random') or continuation_rng(result,seed)
    world = SurpriseWorld(before,result,rng,chaos,random_degree,environment=environment)
    original = before['_RCCEncounters']
    for index,expected in {9:(22,388),171:(43,282),449:(48,328),450:(48,328)}.items():
        row = original[index]
        if (row['map_id'],row['entd'])!=expected: raise ValueError('Native source Warjilis encounter anchor changed')
    old_units,old_encounters,old_formations = deepcopy(result['_RCCUnitContext']),deepcopy(result['_RCCEncounters']),deepcopy(result['_RCCFormations'])
    first = rng.choice((True,False));restore = compile_restore_warjilis(world.env)
    selected = world.unit.selected;world.unit.selected = None
    try:
        restore(before=171,new_entd=476,map_id=42,monsters=first)
        restore(before=[449,450],new_entd=477,map_id=33,monsters=not first)
    finally: world.unit.selected = selected
    new_encounters = [e for i,e in world.encounters.items() if not old_encounters[i]['scenario'] and e.scenario]
    metadata = result.get('_RCCBattleMetadata')
    if metadata is None: raise ValueError('Warjilis requires verified native Battle metadata before adding scenarios')
    template = metadata.get(10)
    if template is None or set(template)!= {'Key','DLCFlags'} or template['DLCFlags']!=0:
        raise ValueError('Native Battle10 clone metadata changed')
    inserts = result.setdefault('_RCCWorldNexInserts',{}).setdefault('Battle',{})
    for enc in new_encounters:
        if enc.scenario not in metadata:
            inserts[enc.scenario] = dict(template,Key=enc.scenario)
    result['_RCCPostmusicEnvironment'] = world.env
    remember_rng(result,rng)
    return dict(source='RCC4415-4602,5218-5223',changed_units=sum(r!=old_units[o] for o,r in result['_RCCUnitContext'].items()),
                encounters=[i for i,r in result['_RCCEncounters'].items() if r!=old_encounters[i]],
                formations=[i for i,r in result['_RCCFormations'].items() if r!=old_formations[i]],
                new_entds=[476,477],monster_entd=476 if first else 477,
                new_encounters=[dict(index=e.index,scenario=e.scenario,entd=e.entd) for e in new_encounters],
                battle_metadata_inserts=sorted(inserts),
                script_resources=['event37 (DeepDungeon END), parent-owned background-END patch'],
                used_music=sorted(world.used_music))


# RCC randomizer.py:4425-4602; binary background-END bytes are parent-owned.
WARJILIS_SOURCE = '''
def restore_warjilis_data(before=171, new_entd=476, map_id=42, monsters=False):
    gariland = EncounterObject.get(9)
    new_enc = EncounterObject.get_unused()
    scenario = new_enc.scenario
    new_enc.copy_data(gariland)
    new_enc.scenario = scenario
    new_enc.event = 37
    new_enc.map_id = map_id
    new_enc.ramza = 0
    new_enc.randomize_music(prefer_unused=True)
    new_enc.randomize_weather()
    new_enc.entd = new_entd
    blank_unit = UnitObject.get(29)
    assert blank_unit.job == blank_unit.graphic == 0
    for u in mapunits[new_entd]:
        u.copy_data(blank_unit)
    new_enc.generate_formations(numchar_override=1)
    mymap = MapObject.get_map(map_id)
    special_jobs = [j for j in get_jobs() if not 5 <= j.skillset <= 24 and j.skillset not in [0, 45, 46, 50] and (not 74 <= j.index <= 143) and (not j.index >= 146) and (not j.index < 4) and (not j.crippled) and (not j.is_lucavi) and (not j.start_status & RERAISE_STATUS) and (not j.innate_status & RERAISE_STATUS) and (j.get_most_common('name') not in [None, 255]) and (j.get_most_common('graphic') not in [None, 128, 129, 130])]
    partner_job = random.choice(special_jobs)
    partner = mapunits[new_entd][14]
    if not monsters:
        special_jobs = [j for j in special_jobs if j.skillset != partner_job.skillset]
        enemy_job = random.choice(special_jobs)
        real_jobs = sorted(set(range(74, 94) + [enemy_job.index]))
        random.shuffle(real_jobs)
    else:
        special_jobs = [j for j in get_jobs() if j.index >= 94 and j.skillset >= 176 and (j.get_most_common('graphic') == 130)]
        portraits = [j.monster_portrait for j in special_jobs]
        portraits = sorted(set(portraits))
        portraits = random.sample(portraits, 7)
        portraits = sorted(portraits * 2)
        chosen_monsters = []
        for p in portraits:
            candidates = [j for j in special_jobs if j.monster_portrait == p and j not in chosen_monsters]
            c = random.choice(candidates)
            chosen_monsters.append(c)
        assert len(set(chosen_monsters)) == 14
        random.shuffle(chosen_monsters)
        for u in UnitObject.every:
            if u.graphic == 130 and u.job >= 94 and (u.name == 255) and (JobObject.get(u.job).skillset >= 176):
                base_monster = u
                break
    units = mapunits[new_entd][:15]
    for unit in units:
        if unit == partner:
            job = partner_job
            for attr in ['name', 'month', 'day', 'brave', 'faith', 'secondary', 'reaction', 'movement', 'palette', 'graphic', 'misc1', 'misc2']:
                setattr(unit, attr, job.get_most_common(attr))
            unit.job = job.index
        elif monsters:
            unit.copy_data(base_monster)
            unit.job = chosen_monsters.pop().index
        else:
            job = enemy_job
            for attr in ['misc1', 'misc2', 'palette', 'graphic']:
                setattr(unit, attr, job.get_most_common(attr))
            for attr in ['month', 'day', 'brave', 'faith', 'secondary']:
                setattr(unit, attr, 254)
            for attr in ['reaction', 'movement']:
                setattr(unit, attr, 510)
            unit.name = 255
            unit.job = real_jobs.pop()
            if unit.job == job.index:
                for attr in ['name', 'day', 'brave', 'faith']:
                    setattr(unit, attr, job.get_most_common(attr))
        unit.set_bit('always_present', True)
        for bit in ['save_formation', 'load_formation', 'hidden_stats', 'test_teta', 'randomly_present', 'join_after_event', 'alternate_team', 'immortal']:
            unit.set_bit(bit, False)
        if unit == partner:
            unit.set_bit('enemy_team', False)
            unit.set_bit('control', False)
            unit.set_bit('hidden_stats', True)
            unit.set_bit('immortal', True)
            unit.level = randint(randint(50, 99), 99)
        else:
            unit.level = randint(1, randint(1, randint(1, 99)))
            unit.set_bit('enemy_team', True)
            unit.set_bit('control', True)
        if not monsters:
            unit.unlocked_level = 8
            unit.mutate(preserve_job=True, preserve_gender=True)
            unit.unlocked_level = 8
        unit.trophy = 0
        unit.gil = 0
        if unit == partner:
            unit.righthand = 37
            unit.head = 171
            unit.body = 184
            unit.accessory = 236
            unit.secondary = 254
            unit.lefthand = 254
            unit.support = 475
        elif monsters:
            pass
        else:
            unit.support = random.choice(range(456, 479) + [482, 483])
            unit.reaction = 0
            for attr in ['lefthand', 'head', 'body', 'accessory']:
                setattr(unit, attr, 255)
            unit.righthand = 254
            item_level = randint(randint(20, 40), 100)
            attr = random.choice(['righthand', 'lefthand', 'head', 'body', 'accessory'])
            if attr == 'righthand':
                candidates = [c for c in ItemObject if c.get_bit('weapon')]
                setattr(unit, random.choice(['lefthand', 'head', 'body', 'accessory']), 254)
            elif attr == 'lefthand':
                candidates = [c for c in ItemObject if c.get_bit('shield')]
            else:
                candidates = [c for c in ItemObject if c.get_bit(attr)]
            candidates = [c for c in candidates if c.enemy_level <= item_level]
            if candidates:
                candidates = random.sample(candidates, min(len(candidates), 3))
                setattr(unit, attr, max(candidates, key=lambda c: c.enemy_level).index)
        bads = mymap.get_values_grid('bad')
        candidates = []
        backups = []
        for j in xrange(mymap.length):
            for i in xrange(mymap.width):
                backed_up = False
                for a, b in product(range(-1, 2), range(-1, 2)):
                    i2, j2 = (i + a, j + b)
                    if i2 < 0 or j2 < 0 or i2 >= mymap.width or (j2 >= mymap.length):
                        continue
                    value = bads[j2][i2]
                    if value:
                        if a * b == 0:
                            break
                        else:
                            backed_up = True
                else:
                    if backed_up:
                        backups.append((i, j))
                    else:
                        candidates.append((i, j))
        if not candidates:
            candidates = backups
        unit.x, unit.y = random.choice(candidates)
        unit.fix_facing(mymap)
        mymap.set_occupied(unit.x, unit.y)
    try:
        len(before)
    except TypeError:
        before = [before]
    for b in before:
        before_event = EncounterObject.get(b)
        before_event.following = 129
        before_event.next_scene = new_enc.scenario
'''
