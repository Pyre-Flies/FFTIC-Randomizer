"""RCC z special units and ending unit data on verified native FFTIC records.

Literal source bodies: randomizer.py3881-4112,4271-4371,5224-5236.
The parent event adapter owns ending encounter/bytecode/conditionals edits.
"""
import ast
import builtins
from copy import deepcopy
import math
from pathlib import Path
from types import SimpleNamespace

from .game import JOB_FIELDS,ACTION_FIELDS
from .rcc import rng_for
from .rcc_units import UnitEngine


SOURCE_METHODS = Path(__file__).with_name('data')/'rcc-event-methods.py'
LUCAVI_ORDER = (67,60,62,69,64,65,151,73)
STAT_NAMES = dict(zip(('hpgrowth','hpmult','mpgrowth','mpmult','spdgrowth','spdmult',
                      'pagrowth','pamult','magrowth','mamult','move','jump','evade'),JOB_FIELDS))


class SourceTable:
    def __init__(self, rows, *, ranked=None):
        self.rows = rows
        self.every = list(rows.values())
        self.ranked = ranked if ranked is not None else self.every
    def get(self,index): return self.rows.get(index)
    def __iter__(self): return iter(self.every)


class SpecialJob:
    """Mutable source properties over native JobData, preserving TIC byte5."""
    def __init__(self,engine,index):
        object.__setattr__(self,'engine',engine)
        object.__setattr__(self,'index',index)
        object.__setattr__(self,'row',engine.tables['JobData'][index])
    def __getattr__(self,name):
        if name in STAT_NAMES: return self.row[STAT_NAMES[name]]
        if name=='skillset': return self.row['JobCommandId']
        if name=='immune_status': return int.from_bytes(self.row['ImmuneStatus'].to_bytes(5,'big'),'little')
        if name=='equips': return int.from_bytes(self.row['EquippableItems'].to_bytes(5,'big')[:4],'little')
        return getattr(self.engine.jobs[self.index],name)
    def __setattr__(self,name,value):
        if name in STAT_NAMES: self.row[STAT_NAMES[name]] = value
        elif name=='skillset':
            self.row['JobCommandId'] = value
            self.engine.jobs[self.index].skillset = value
        elif name=='immune_status':
            self.row['ImmuneStatus'] = int.from_bytes(value.to_bytes(5,'little'),'big')
        elif name=='equips':
            last = self.row['EquippableItems'].to_bytes(5,'big')[4:]
            self.row['EquippableItems'] = int.from_bytes(value.to_bytes(4,'little')+last,'big')
        else: object.__setattr__(self,name,value)
    @property
    def can_invite(self): return not bool(self.immune_status&0x4000)
    @property
    def innate_status(self): return int.from_bytes(self.row['InnateStatus'].to_bytes(5,'big'),'little')
    @property
    def start_status(self): return int.from_bytes(self.row['StartingStatus'].to_bytes(5,'big'),'little')
    @property
    def crippled(self):
        from .rcc_context import VALID_START_STATUSES
        return bool((self.innate_status|self.start_status)&(0xFFFFFFFFFF^VALID_START_STATUSES))
    def get_most_common(self,attribute):
        from collections import Counter
        units = [u for u in self.engine.units if u.job==self.index and u.map_id<=469]
        if not units: return None
        counts = Counter(getattr(u,attribute) for u in units)
        maximum = max(counts.values())
        choices = sorted(value for value,count in counts.items() if count==maximum)
        return self.engine.random.choice(choices) if choices else None
    @property
    def guaranteed_female(self):
        units = [u for u in self.engine.units if u.job==self.index and 384<=u.map_id<=469]
        return bool(units and any(u.get_bit('female') for u in units) and not any(u.get_bit('male') for u in units))


class IntegerDivision(ast.NodeTransformer):
    def visit_BinOp(self,node):
        self.generic_visit(node)
        if isinstance(node.op,ast.Div): node.op = ast.FloorDiv()
        return node


def compile_special_methods(environment,*,source=None):
    path = Path(source) if source else SOURCE_METHODS
    tree = ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
    names = {'mutate_units_special','generate_balmafula'}
    methods = [node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    if {node.name for node in methods}!=names: raise ValueError('Literal RCC special-unit source bodies are absent')
    selected = IntegerDivision().visit(ast.Module(body=methods,type_ignores=[]))
    # Preserve the exact classic loop and append verified Enhanced ENTD rows.
    # This adapter introduces no extra rolls for the original template list.
    for node in ast.walk(selected):
        if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='map_id':
            node.iter = ast.BinOp(node.iter,ast.Add(),ast.Name('_ENHANCED_ENTDS',ast.Load()))
    ast.fix_missing_locations(selected)
    environment.update(range=lambda *a:list(builtins.range(*a)))
    exec(compile(selected,str(path),'exec'),environment)
    return {name:environment[name] for name in names}


def special_environment(before,result,rng,chaos=1,random_degree=.25,*,environment=None):
    unit = result.get('_RCCUnitEngine') or UnitEngine(before,result,rng,chaos,random_degree)
    unit.random,unit.random_degree = rng,random_degree
    unit.boostd.update(jp=1.5**chaos,equipment=1.1**chaos,special_equipment=1.5**chaos,
                      difficulty_factor=chaos,random_special_unit=.5+chaos,story_special_unit=chaos)
    jobs = {j:SpecialJob(unit,j) for j in unit.jobs}
    env = unit.source_environment()
    if environment: env.update(environment)
    from collections import Counter
    env.update(random=rng,Counter=Counter,JobObject=SourceTable(jobs),get_job=jobs.get,
               get_jobs=lambda:list(jobs.values()),
               UnitObject=SourceTable({u.index:u for u in unit.units}),
               ItemObject=SourceTable(unit.items,ranked=unit.get_ranked_items()),
               SUPER_SPECIAL=[],LUCAVI_ORDER=list(LUCAVI_ORDER),INVITE_STATUS=0x4000,
               USED_MAPS=list(range(331))+list(range(384,470))+sorted(unit.extra_entds),
               _ENHANCED_ENTDS=sorted(unit.extra_entds))
    env['_UNIT_ENGINE'] = unit
    result['_RCCUnitEngine'] = unit
    return env


def _check_settings(chaos,random_degree):
    if not math.isfinite(chaos) or chaos<0: raise ValueError('Special-unit chaos must be finite and nonnegative')
    if not math.isfinite(random_degree) or not 0<=random_degree<=1: raise ValueError('Special-unit normal mutation degree must be0 to1')


def apply_special_units(before,result,seed,flags,chaos=1,random_degree=.25,*,environment=None):
    audit = dict(source='RCC z special-unit templates',changed_units=0,changed_jobs=[],special_units=[])
    if 'z' not in flags: return audit
    _check_settings(chaos,random_degree)
    old_units,old_jobs = deepcopy(result['_RCCUnitContext']),deepcopy(result['JobData'])
    rng = (environment or {}).get('random') or rng_for(seed,'specials-z')
    env = special_environment(before,result,rng,chaos,random_degree,environment=environment)
    selected = env['_UNIT_ENGINE'].selected
    env['_UNIT_ENGINE'].selected = None
    try:
        methods = compile_special_methods(env)
        methods['mutate_units_special']()
    finally:
        env['_UNIT_ENGINE'].selected = selected
    result['_RCCSpecialEnvironment'] = env
    from .rcc import remember_rng
    remember_rng(result,rng)
    audit.update(changed_units=sum(r!=old_units[o] for o,r in result['_RCCUnitContext'].items()),
                 changed_jobs=[j for j,r in result['JobData'].items() if r!=old_jobs[j]],
                 special_units=[u.owner for u in env['SUPER_SPECIAL']],
                 balmafula_command=result['JobData'][33]['JobCommandId'],
                 enhanced_templates=len(env['_ENHANCED_ENTDS']))
    return audit


def _anchor(before,index,expected):
    row = before['_RCCEffectiveUnitContext'][index>>4,index&15]
    got = (row['Spriteset'],row['MainJob'],row['NameId'])
    if got!=expected: raise ValueError(f'Native special-unit anchor changed at {index>>4,index&15}: {got}')


def apply_ending_units(before,result,seed,flags,chaos=1,random_degree=.25,*,environment=None):
    """RCC ending unit/job/funeral data; source4271-4371 before f.

    Event bytecode and the ending encounter/conditionals are parent-owned.
    Reuses the z RNG continuation when called after apply_special_units.
    """
    if 'z' not in flags: return dict(changed_units=0,changed_jobs=[])
    _check_settings(chaos,random_degree)
    env = environment or result.get('_RCCSpecialEnvironment')
    if env is None: env = special_environment(before,result,rng_for(seed,'specials-z'),chaos,random_degree)
    engine = env['_UNIT_ENGINE']
    for index,expected in {0x1330:(6,6,6),0x1331:(12,12,12),0x1332:(130,94,255),0x1333:(3,3,3)}.items():
        _anchor(before,index,expected)
    old_units,old_jobs = deepcopy(result['_RCCUnitContext']),deepcopy(result['JobData'])
    methods = _compile_ending_units(env)
    selected = engine.selected;engine.selected = None
    try: methods()
    finally: engine.selected = selected
    result['_RCCSpecialEnvironment'] = env
    from .rcc import remember_rng
    remember_rng(result,env['random'])
    return dict(source='RCC ending unit/job/funeral data',
                changed_units=sum(r!=old_units[o] for o,r in result['_RCCUnitContext'].items()),
                changed_jobs=[j for j,r in result['JobData'].items() if r!=old_jobs[j]],
                ending_units=[(307,i) for i in range(4)],funeral_units=[(308,i) for i in range(1,9)])


def _compile_ending_units(environment):
    # These source fragments are checked in alongside the other RCC methods.
    path = '<RCC randomize_ending unit-only source>'
    tree = ast.parse(ENDING_UNIT_SOURCE,filename=path)
    tree = IntegerDivision().visit(tree)
    ast.fix_missing_locations(tree)
    environment.update(range=lambda *a:list(builtins.range(*a)))
    exec(compile(tree,str(path),'exec'),environment)
    return environment['randomize_ending_units']


def apply_special_postmusic(before,result,seed,flags,*,environment=None):
    if 'z' not in flags: return dict(changed_units=0,altima_command=None)
    for index,expected in {0x1921:(130,151,119),0x192a:(130,144,255)}.items(): _anchor(before,index,expected)
    result['JobData'][65]['JobCommandId'] = 123
    engine = result.get('_RCCUnitEngine')
    if engine: engine.jobs[65].skillset = 123
    units = result['_RCCUnitContext'];changed=[]
    from .rcc_encounter_data import get_flag,set_flag
    for index in [0x1921,*range(0x1922,0x1928),0x192a]:
        owner = (index>>4,index&15)
        if not get_flag(units[owner],'join_after_event'): changed.append(owner)
        set_flag(units[owner],'join_after_event',True)
    return dict(source='RCC5224-5228 postmusic',changed_units=len(changed),
                units=changed,altima_command=123)


def guarantee_invite(before,result,seed,flags,*,environment=None):
    """RCC5150-5154 force-add Invite to Ramza if the source ten jobs lack it."""
    if 'z' not in flags: return dict(added=False)
    commands = result['JobCommandData']
    source_commands = (7,9,10,11,12,13,14,15,16,22)
    if any(116 in [commands[c][f] for f in ACTION_FIELDS] for c in source_commands):
        return dict(added=False,reason='Invite already occurs in a source checked job')
    env = environment or result.get('_RCCSpecialEnvironment')
    rng = env['random'] if env else rng_for(seed,'specials-z')
    row = commands[27]
    adapted = False;donor = None
    oldmenu = result['CommandTypeData'][27]['Menu']
    if oldmenu!=0:
        # Full has moved complete special profiles. A direct action cannot be
        # inserted into Items/Throw/Jump/Aim/Math/Geomancy/Iaido parameters.
        from .catalog import creature_commands
        creatures = creature_commands(before)
        candidates = [c for c,r in sorted(commands.items()) if c>=5 and c not in creatures
                      and result['CommandTypeData'][c]['Menu']==0 and any(r[f] for f in ACTION_FIELDS)]
        if not candidates: raise ValueError('z Invite compatibility requires one existing human direct-action profile')
        donor = rng.choice(candidates)
        for field in ACTION_FIELDS: row[field] = commands[donor][field]
        result['CommandTypeData'][27]['Menu'] = 0
        adapted = True
    actions = [row[f] for f in ACTION_FIELDS if row[f]]
    added = 116 not in actions
    if added:
        if len(actions)==16: actions[rng.randint(0,15)] = 116
        else: actions.append(116)
        for field,value in zip(ACTION_FIELDS,actions+[0]*(16-len(actions))): row[field] = value
    ability_audit = result.get('_RCCAbilityAudit',{})
    for owner in ability_audit.get('selected_owners',[]):
        if owner['table']=='JobCommandData' and owner['id']==27:
            owner['menu'] = 0;owner['action_count'] = len(actions)
    audit = dict(source='RCC5150-5154 guaranteed Invite',added=added,command=27,
                 full_menu_adapted=adapted,original_menu=oldmenu,direct_profile_donor=donor,
                 final_menu=0,action_count=len(actions),passives_preserved=True)
    ability_audit['z_guaranteed_invite'] = audit
    return audit


def apply_alma_math_cleanup(before,result):
    """Unconditional source5231-5236, after postmusic z and before palette cleanup."""
    units = result['_RCCUnitContext'];altima = units[441,8]
    if altima['SecondarySkillset']!=21: return dict(changed_units=0)
    _anchor(before,0x1b98,(73,73,73))
    for index,expected in {0x1a40:(48,48,48),0x1b92:(20,20,20)}.items(): _anchor(before,index,expected)
    for owner in ((420,0),(441,2)):
        for field in ('SecondarySkillset','JobUnlock','JobLevel'): units[owner][field] = altima[field]
    return dict(source='RCC5231-5236 Alma math compatibility',changed_units=2,
                units=[(420,0),(441,2)])


# RCC randomizer.py:4285-4326,4356-4371; file/event operations are parent-owned.
ENDING_UNIT_SOURCE = '''
def randomize_ending_units():
    ramza_unit = UnitObject.get(4915)
    delita_unit = UnitObject.get(4912)
    ovelia_unit = UnitObject.get(4913)
    chocobo_unit = UnitObject.get(4914)
    delita_unit.backup_jp_total = 500000
    ovelia_unit.backup_jp_total = 500000
    delita_unit.mutate(preserve_job=True)
    ovelia_unit.mutate(preserve_job=True)
    chocobo_unit.mutate(preserve_job=True)
    maxlevel = (boostd['difficulty_factor'] - 1.0) * 100
    maxlevel = max(maxlevel, 0)
    level = int(round(maxlevel ** 0.5))
    level = randint(level, randint(level, randint(level, maxlevel)))
    delita_unit.level = min(level + 100, 199)
    ramza_unit.set_bit('always_present', False)
    ramza_unit.set_bit('load_formation', True)
    ramza_unit.set_bit('control', True)
    ramza_unit.set_bit('enemy_team', False)
    delita_unit.set_bit('enemy_team', True)
    del_job = JobObject.get(delita_unit.job)
    del_job.immune_status &= 2 ** 40 - 1 ^ INVITE_STATUS
    del_job.equips &= 4280221696
    del_job.equips |= 24
    knives = range(1, 11)
    knives = [k for k in ItemObject.ranked if k.index in knives]
    index = len(knives) - 1
    index = randint(randint(0, index), index)
    for attr in ['lefthand', 'righthand', 'head', 'body', 'accessory']:
        setattr(delita_unit, attr, 254)
        setattr(ovelia_unit, attr, 254)
        setattr(chocobo_unit, attr, 0)
    ovelia_unit.righthand = knives[index].index
    chocobo_unit.unknown4 = 1024
    ovelia_unit.unknown4 = 1024
    chocobo_unit.behavior = 8
    ovelia_unit.behavior = 8
    delita_unit.behavior = 88
    delita_unit.target_id = 3
    ramza_unit.unit_id = 3
    henchmen = [UnitObject.get(u).graphic for u in range(7059, 7063)]
    used_graphics = sorted(set([u.graphic for u in UnitObject if u.named and 1 <= u.graphic <= 119 and (u.graphic not in henchmen)]))
    chosen = random.sample(used_graphics, 4)
    priest, others = (chosen[0], chosen[1:])
    others += henchmen
    assert len(others) == 7
    random.shuffle(others)
    otherunits = [u for u in mapunits[308] if 4929 <= u.index <= 4935]
    otherunits = sorted(otherunits, key=lambda u: u.index)
    for u, g in zip(otherunits, others):
        u.graphic = g
    UnitObject.get(4936).graphic = priest
'''
