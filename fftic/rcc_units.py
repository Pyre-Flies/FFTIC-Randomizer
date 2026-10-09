"""RCC encounter units on verified FFTIC ENTD records.

Unit mutation methods below retain RCC randomizer.py:2083-2745,3820-3878
control flow. Python 2 syntax/integer division and global state are adapted;
FFTIC creature identity comes from native traits, not a PS1 numeric cutoff.
"""
from types import SimpleNamespace
from .game import ACTION_FIELDS
from .catalog import creature_jobs
from .rcc import rng_for, randint as rcc_randint, mutate_normal as rcc_normal
from .rcc_context import LUCAVI, VALID_START_STATUSES
from .rcc_encounter_data import RCC_NAMES, get_flag, set_flag

JOBNAMES = ('squire','chemist','knight','archer','monk','priest','wizard','timemage',
            'summoner','thief','mediator','oracle','geomancer','lancer','samurai',
            'ninja','calculator','bard','dancer','mime')
DAYS_IN_MONTH = dict(enumerate((31,28,31,30,31,30,31,31,30,31,30,31),1))


def _array(value):
    import json
    return json.loads(value) if isinstance(value,str) else value


def _source_status(value):
    # Loader/public aggregate status masks are big-endian; RCC's table reader
    # interprets the same five physical bytes little-endian.
    return int.from_bytes(value.to_bytes(5,'big'),'little')


class ProgressionJob:
    def __init__(self, engine, index, requirements):
        self.engine, self.index = engine, index
        self.otherindex = index-74
        self.name = JOBNAMES[self.otherindex]
        for i,name in enumerate(JOBNAMES):
            setattr(self,name,requirements.get(i+74,0))

    @property
    def required_unlock_jp(self):
        return self.engine.calculate_jp_total([getattr(self,n) for n in JOBNAMES if getattr(self,n)])

    def reqs_are_subset_of(self, other):
        return all(getattr(self,n)<=getattr(other,n) for n in JOBNAMES)

    @property
    def calculator_potential(self):
        if not self.calculator and self.name!='calculator': return 0
        total = 0
        for name in ('priest','wizard','timemage','oracle','calculator'):
            if name==self.name: total += 8
            elif getattr(self,name): total += getattr(self,name)
            elif self.engine.jobreq_namedict[name].reqs_are_subset_of(self): total += 1
        return total


class NativeJob:
    def __init__(self, engine, index, row):
        self.engine, self.index, self.row = engine, index, row
        self.skillset = row['JobCommandId']
        traits = engine.tables['_JobTraits'][index]
        self.monster_portrait = traits['MonsterPortrait']
        self.monster_graphic = traits['MonsterGraphic']
        self.is_monster_job = index in engine.unit_monsters
        self.is_lucavi = index in LUCAVI


class NativeSkillset:
    def __init__(self, engine, index, row):
        self.engine, self.index = engine, index
        self.actions = [row[f] for f in ACTION_FIELDS]
        attributes = engine.tables['_AbilityAttributes']
        rows = [attributes[a] for a in self.actions if a in attributes]
        self.has_swordskills = any(a.get('require_sword') for a in rows)
        self.has_limitskills = any(a.get('require_materia_blade') for a in rows)
        self.not_just_swordskills = any(not(a.get('require_sword') or a.get('require_materia_blade')) for a in rows)
        self.no_randoms = not any(a.get('random_hits') for a in rows)
        self.no_balls = 393 not in self.actions
        self.lucavi_appropriate = self.not_just_swordskills and self.no_randoms and self.no_balls
        self.num_actions = sum(bool(a) for a in self.actions)
        self.num_free_actions = sum(engine.costs.get(a,0)==0 for a in self.actions)


class NativeUnit:
    """A source-compatible object backed by the shared mutable canonical row."""
    def __init__(self, engine, owner, row):
        object.__setattr__(self,'engine',engine)
        object.__setattr__(self,'owner',owner)
        object.__setattr__(self,'row',row)
        object.__setattr__(self,'index',owner[0]*16+owner[1])
        if owner in engine.backups: self.backup_jp_total = engine.backups[owner]

    def __getattr__(self, name):
        if name=='unknown2': return self.row['Unknown28']|(self.row['EntryUnknown1D']<<8)
        if name in RCC_NAMES: return self.row[RCC_NAMES[name]]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name=='unknown2':
            if not 0<=value<=65535: raise ValueError('Native unknown2 must fit two bytes')
            self.row['Unknown28'],self.row['EntryUnknown1D'] = value&255,value>>8
            return
        if name in RCC_NAMES: self.row[RCC_NAMES[name]] = value
        else: object.__setattr__(self,name,value)

    def get_bit(self, name): return get_flag(self.row,name)
    def set_bit(self, name, value): set_flag(self.row,name,value)
    @property
    def has_monster_job(self): return self.job in self.engine.unit_monsters
    @property
    def monster_portrait(self): return self.engine.get_job(self.job).monster_portrait
    @property
    def is_lucavi(self): return self.job in LUCAVI
    @property
    def is_altima(self): return self.job in (65,73)

    def copy_data(self, other):
        # TableObject.copy_data copies declared fields, not the owner's index.
        self.row.update(other.row)

    @property
    def is_native_placeholder(self):
        return (self.map_id>=512 and self.job==0 and self.unlocked not in range(20)
                and not(self.get_bit('always_present') or self.get_bit('randomly_present')))


    # RCC randomizer.py:2085-2087
    @property
    def map_id(self):
        return self.index >> 4

    # RCC randomizer.py:2089-2091
    @property
    def has_special_graphic(self):
        return self.graphic not in [128, 129, 130]

    # RCC randomizer.py:2110-2120
    @property
    def has_swordskills(self):
        job = self.engine.get_job(self.job)
        ss = self.engine.get_skillset(job.skillset)
        ss2 = self.engine.get_skillset(self.secondary)
        for s in [ss, ss2]:
            if s is None:
                continue
            if s.has_swordskills:
                return True
        return False

    # RCC randomizer.py:2122-2132
    @property
    def has_limitskills(self):
        job = self.engine.get_job(self.job)
        ss = self.engine.get_skillset(job.skillset)
        ss2 = self.engine.get_skillset(self.secondary)
        for s in [ss, ss2]:
            if s is None:
                continue
            if s.has_limitskills:
                return True
        return False

    # RCC randomizer.py:2133-2144
    def clean(self):
        if self.job not in range(74, 94):
            return
        if self.get_bit('alternate_team'):
            map_enemy_palettes = [u.palette for u in self.engine.UnitObject.every if u.map_id == self.map_id and u.get_bit('enemy_team')]
            candidates = sorted(set(range(1, 5)) - set(map_enemy_palettes))
            self.palette = self.engine.random.choice(candidates)
        elif not self.get_bit('enemy_team'):
            self.palette = 0

    # RCC randomizer.py:2145-2158
    def fix_facing(self, m):
        dirdict = {'west': self.x, 'south': self.y, 'east': m.width - self.x, 'north': m.length - self.y}
        facedict = {'west': 3, 'south': 2, 'east': 1, 'north': 0}
        lowest = min(list(dirdict.values()))
        candidates = sorted([v for k, v in facedict.items() if dirdict[k] == lowest])
        chosen = self.engine.random.choice(candidates)
        self.facing &= 252
        self.facing |= chosen

    # RCC randomizer.py:2159-2168
    def has_similar_monster_graphic(self, other):
        if not (self.graphic == 130 and other.graphic == 130):
            return False
        if self.engine.get_job(self.job).monster_graphic == self.engine.get_job(other.job).monster_graphic:
            return True
        else:
            return False

    # RCC randomizer.py:2170-2172
    @property
    def named(self):
        return bool(self.name != 255)

    # RCC randomizer.py:2174-2176
    @property
    def level_normalized(self):
        return self.level >= 100 or self.level == 0

    # RCC randomizer.py:2177-2183
    def normalize_level(self, boost=None):
        if boost is None:
            self.level = 254
        else:
            self.level = 100 + self.engine.randint(0, boost) + self.engine.randint(0, boost)
            self.level = max(100, min(self.level, 199))

    # RCC randomizer.py:2184-2189
    def set_backup_jp_total(self):
        value = self.jp_total
        if value < self.engine.JOBLEVEL_JP[0]:
            value = self.engine.random.choice([value, self.engine.JOBLEVEL_JP[0]])
        self.backup_jp_total = value

    # RCC randomizer.py:2191-2216
    @property
    def jp_total(self):
        if hasattr(self, 'backup_jp_total'):
            return self.backup_jp_total
        if self.is_native_placeholder:
            return 0
        if self.job in self.engine.jobreq_indexdict:
            base_job = self.engine.jobreq_indexdict[self.job]
        else:
            if self.unlocked == 0 and self.unlocked_level == 0 and (not self.level_normalized):
                total = self.engine.mutate_normal(175 * self.level, minimum=0, maximum=500000)
                return total
            base_job = self.engine.jobreq_indexdict[74]
        unlocked_job = self.engine.jobreq_indexdict[self.unlocked + 74]
        joblevels = []
        for name in self.engine.JOBNAMES:
            value = max(getattr(base_job, name), getattr(unlocked_job, name))
            if name == unlocked_job.name:
                value = max(value, self.unlocked_level)
            if value:
                joblevels.append(value)
        total = self.engine.calculate_jp_total(joblevels)
        return total

    # RCC randomizer.py:2225-2378
    def mutate_secondary(self, base_job=None, jp_remaining=None, boost_factor=None):
        if self.get_bit('load_formation'):
            return
        if self.is_altima and self.engine.MUTATED_SKILLSETS:
            if self.index == 7064:
                assert self.job == 73
                factor = self.engine.boostd['difficulty_factor'] - 1.0
                factor = min(max(factor, 0.0), 1.0)
                candidates = [j for j in self.engine.JobReqObject.every if j.calculator_potential >= 1]
                candidates.append(self.engine.JobReqObject.get_by_name('squire'))
                while len(candidates) < 3:
                    candidates.append(self.engine.JobReqObject.get_by_name('squire'))
                candidates = sorted(candidates, key=lambda j: (j.calculator_potential, j.index))
                low_index = self.engine.randint(0, self.engine.randint(0, len(candidates) // 2))
                high_index = self.engine.mutate_normal(len(candidates) // 2, minimum=0, maximum=len(candidates) - 1)
                high_index = self.engine.randint(high_index, self.engine.randint(high_index, len(candidates) - 1))
                if low_index > high_index:
                    low_index, high_index = (high_index, low_index)
                index = factor * high_index + (1 - factor) * low_index
                unlocked = candidates[int(round(index))]
                low_level = self.engine.randint(1, self.engine.randint(1, 8))
                high_level = self.engine.randint(self.engine.randint(1, 8), 8)
                if low_level > high_level:
                    low_level, high_level = (high_level, low_level)
                level = int(round(factor * high_level + (1 - factor) * low_level))
                if unlocked.calculator_potential >= 1:
                    self.unlocked = unlocked.otherindex
                    self.unlocked_level = level
                    self.secondary = 21
                    return
        if boost_factor is None:
            boost_factor = self.engine.boostd['jp']
        if base_job is None:
            job = self.job
            if job in self.engine.jobreq_indexdict:
                base_job = self.engine.jobreq_indexdict[job]
            else:
                base_job = None
        if jp_remaining is None:
            jp_remaining = self.jp_total
            jp_remaining = self.engine.randint(jp_remaining, int(jp_remaining * boost_factor))
        jobs = list(self.engine.jobreq_namedict.values())
        jobs = [j for j in jobs if j.required_unlock_jp <= jp_remaining]
        jobs = sorted(jobs, key=lambda j: j.required_unlock_jp)
        goal_length = len(jobs) // 2 + 1
        while len(jobs) > goal_length:
            if self.engine.randint(1, len(jobs)) == 1:
                break
            else:
                jobs = jobs[1:]
        if base_job is not None:
            if self.engine.randint(1, 20) != 20 and base_job.otherindex > 0:
                base_name = base_job.name
                tempjobs = [j for j in jobs if getattr(j, base_name) > 0 or j == base_job]
                if tempjobs:
                    jobs = tempjobs
            self.engine.random.shuffle(jobs)
            while True:
                if not jobs:
                    required_jp = base_job.required_unlock_jp
                    unlocked_job = base_job
                    break
                unlocked_job = jobs.pop()
                joblevels = []
                for name in self.engine.JOBNAMES:
                    value = max(getattr(base_job, name), getattr(unlocked_job, name))
                    if value:
                        joblevels.append(value)
                required_jp = self.engine.calculate_jp_total(joblevels)
                if required_jp <= jp_remaining:
                    break
        else:
            required_jp = 0
            unlocked_job = self.engine.random.choice(jobs)
        jp_remaining -= required_jp
        if self.is_lucavi:
            unlocked_level = 8
        else:
            unlocked_level = len([j for j in self.engine.JOBLEVEL_JP if j <= jp_remaining])
            if self.engine.random.choice([True, False]):
                unlocked_level += 1
            while self.engine.randint(1, 7) == 7:
                unlocked_level += 1
        unlocked_level = min(unlocked_level, 8)
        self.unlocked = unlocked_job.otherindex
        self.unlocked_level = unlocked_level
        if self.is_lucavi and self.engine.randint(1, 15) != 15:
            self.unlocked = 0
            candidates = self.engine.get_ranked_secondaries()
            candidates = [self.engine.SkillsetObject.get(c) for c in candidates]
            candidates = [ss.index for ss in candidates if ss.lucavi_appropriate]
            index = None
            if self.secondary in candidates:
                index = candidates.index(self.secondary)
            elif self.engine.randint(1, 5) == 5:
                index = 2 * (len(candidates) // 3)
            if index is not None and self.engine.random.choice([True, False]):
                index = self.engine.mutate_normal(index, minimum=0, maximum=len(candidates) - 1)
                self.secondary = candidates[index]
            return True
        if self.engine.randint(1, 20) == 20:
            candidates = self.engine.get_ranked_secondaries()
            index = len(candidates) // 3
            index = self.engine.mutate_normal(index, minimum=0, maximum=len(candidates) - 1)
            self.secondary = candidates[index]
        elif unlocked_job != base_job and unlocked_level > 1 and (self.engine.randint(1, 3) != 3) and (unlocked_job.name != 'mime'):
            assert unlocked_job.otherindex in range(19)
            self.secondary = unlocked_job.otherindex + 5
        elif self.engine.randint(1, 5) == 5:
            cands = []
            for name in self.engine.JOBNAMES:
                if name == 'mime':
                    continue
                value = max(getattr(base_job, name) if base_job else 0, getattr(unlocked_job, name))
                if value:
                    cands.append(name)
            if cands:
                chosen = self.engine.jobreq_namedict[self.engine.random.choice(cands)]
                self.secondary = chosen.otherindex + 5
            else:
                self.secondary = 254
        elif self.secondary != 0 or self.engine.random.choice([True, False]):
            self.secondary = 254
        if self.is_lucavi and self.secondary != 254 and (not self.engine.SkillsetObject.get(self.secondary).lucavi_appropriate):
            self.secondary = 254
        return True

    # RCC randomizer.py:2379-2465
    def mutate_monster_job(self, preserve_graphic=False):
        monster_check = self.engine.monster_check
        if not monster_check(self):
            return True
        oldjob = self.job
        if self.named and (self.name, oldjob) in self.engine.named_jobs:
            self.job = self.engine.named_jobs[self.name, self.job]
            return True
        if self.named and (self.name, self.job) == (118, 94):
            self.job = self.engine.random.choice(self.engine.boco_candidates())
            self.engine.named_jobs[self.name, oldjob] = self.job
            return True
        all_ranked_monster_jobs = self.engine.get_ranked_monster_jobs()
        if self.map_id not in self.engine.monster_selection and (not preserve_graphic):
            assert self in self.engine.mapunits[self.map_id]
            assert self.graphic == 130
            ranked_monster_jobs = list(all_ranked_monster_jobs)
            map_monster_jobs = [self.engine.JobObject.get(u.job) for u in self.engine.mapunits[self.map_id] if monster_check(u)]
            map_monster_jobs = sorted(map_monster_jobs, key=lambda u: u.index)
            assert self.engine.JobObject.get(self.job) in map_monster_jobs
            lowjob = min(map_monster_jobs, key=lambda j: ranked_monster_jobs.index(j))
            index = ranked_monster_jobs.index(lowjob)
            index = max(0, index - 1)
            while index > 0 and self.engine.random.choice([True, False]):
                index -= 1
            ranked_monster_jobs = ranked_monster_jobs[index:]
            ranked_monster_sprites = []
            for m in ranked_monster_jobs:
                if m.monster_portrait not in ranked_monster_sprites:
                    ranked_monster_sprites.append(m.monster_portrait)
            selected_sprites = []
            monster_sprites = set([m.monster_portrait for m in map_monster_jobs])
            for s in sorted(monster_sprites):
                temp_sprites = [t for t in ranked_monster_sprites if t not in selected_sprites or t == s]
                index = temp_sprites.index(s)
                index = self.engine.mutate_index(index, len(temp_sprites), [True, False], (-2, 3), (-1, 1))
                selected = temp_sprites[index]
                selected_sprites.append(selected)
            selected_monsters = [m for m in ranked_monster_jobs if m.monster_portrait in selected_sprites]
            if len(selected_monsters) <= 3:
                selected_monsters = [m for m in all_ranked_monster_jobs if m.monster_portrait in selected_sprites]
            self.engine.monster_selection[self.map_id] = selected_monsters
        if preserve_graphic:
            selection = [m for m in all_ranked_monster_jobs if m.monster_portrait == self.engine.JobObject.get(self.job).monster_portrait]
        else:
            selection = self.engine.monster_selection[self.map_id]
        myjob = self.engine.get_job(self.job)
        ranked_selection = [m for m in all_ranked_monster_jobs if m in selection or m == myjob]
        if not self.get_bit('enemy_team'):
            index = -2
            while self.engine.random.choice([True, False]):
                index -= 1
            newjob = self.engine.random.choice(ranked_selection[index:])
        else:
            index = ranked_selection.index(myjob)
            if myjob not in selection:
                ranked_selection.remove(myjob)
            if self.get_bit('always_present'):
                index = self.engine.mutate_index(index, len(ranked_selection), [True, False, False], (-1, 2), (-1, 1))
            else:
                index = self.engine.mutate_index(index, len(ranked_selection), [True, False], (-2, 3), (-1, 2))
            newjob = ranked_selection[index]
        self.job = newjob.index
        self.engine.named_jobs[self.name, oldjob] = self.job
        return True

    # RCC randomizer.py:2466-2599
    def mutate(self, boost_factor=None, preserve_gender=False, preserve_job=False):
        if self.is_native_placeholder:
            return
        if self.engine.selected is not None and self.owner not in self.engine.selected:
            return
        if self.graphic == 0 and self.job == 0:
            return
        if boost_factor is None:
            boost_factor = self.engine.boostd['jp']
        self.mutate_stats()
        if self.is_lucavi:
            self.mutate_secondary()
            return
        if self.has_monster_job:
            self.mutate_monster_job(preserve_graphic=preserve_job)
            return
        if preserve_job or self.job not in self.engine.jobreq_indexdict:
            self.mutate_equips()
            self.mutate_rsm()
            self.mutate_secondary()
            return
        jp_remaining = self.jp_total
        jp_remaining = self.engine.randint(jp_remaining, int(jp_remaining * boost_factor))
        generic_r, monster_r, other_r = self.engine.mapsprite_restrictions[self.map_id]
        selection = sorted(self.engine.mapsprite_selection[self.map_id], key=lambda item: (item[0].index, item[1]))
        done_jobs = [j for j, g in selection]
        male_sel = [(j, g) for j, g in selection if g == 'male']
        female_sel = [(j, g) for j, g in selection if g == 'female']
        gender = None
        if self.named:
            preserve_gender = True
        if preserve_gender:
            if self.get_bit('male'):
                gender = 'male'
            elif self.get_bit('female'):
                gender = 'female'
            else:
                raise Exception('No gender.')
        if preserve_gender and (not self.has_special_graphic):
            if gender == 'male':
                assert male_sel or len(selection) < generic_r
            elif gender == 'female':
                assert female_sel or len(selection) < generic_r
        assert self.job in self.engine.jobreq_indexdict.keys()
        jobs = list(self.engine.jobreq_namedict.values())
        jobs = [j for j in jobs if j.required_unlock_jp < jp_remaining]
        base_job = None
        if base_job is None and self.named and (not self.has_special_graphic):
            if (self.name, self.job) in self.engine.named_jobs:
                base_job = self.engine.named_jobs[self.name, self.job]
            elif len(selection) >= generic_r:
                sel = [(j, g) for j, g in selection if g == gender]
                base_job, gen = self.engine.random.choice(sel)
                assert gen == gender
        if base_job is None and (self.has_special_graphic or len(selection) < generic_r):
            if gender is None:
                gender = self.engine.random.choice(['male', 'female'])
                if self.map_id in [269, 400, 424]:
                    gender = 'female'
            cands = [j for j in jobs if j not in done_jobs]
            if not cands:
                cands = jobs
            if gender == 'male':
                cands = [c for c in cands if c.name != 'dancer']
            elif gender == 'female':
                cands = [c for c in cands if c.name != 'bard']
            if cands:
                cands = sorted(cands, key=lambda j: j.required_unlock_jp)
                goal_length = len(cands) // 2 + 1
                while len(cands) > goal_length:
                    if self.engine.randint(1, len(cands)) == 1:
                        break
                    else:
                        cands = cands[1:]
                base_job = self.engine.random.choice(cands)
            else:
                base_job = self.engine.jobreq_namedict['squire']
        if base_job is None:
            if self.named:
                assert (self.name, self.job) not in self.engine.named_jobs
                if gender == 'male':
                    cands = male_sel
                elif gender == 'female':
                    cands = female_sel
                if not cands:
                    pass
                    base_job, gender = self.engine.random.choice(selection)
                    raise ValueError('RCC native sprite constraint failed')
                else:
                    base_job, gender = self.engine.random.choice(cands)
            else:
                base_job, gender = self.engine.random.choice(selection)
        assert base_job is not None
        if not self.has_special_graphic:
            if self.named and (self.name, self.job) in self.engine.named_jobs:
                assert self.engine.named_jobs[self.name, self.job] == base_job
            else:
                self.engine.named_jobs[self.name, self.job] = base_job
            self.engine.named_map_jobs[self.map_id, self.job, gender] = base_job
            if (self.map_id in self.engine.extra_entds and (base_job,gender) not in self.engine.mapsprite_selection[self.map_id]
                    and len(self.engine.mapsprite_selection[self.map_id])>=generic_r):
                # Enhanced's additional story templates repeat Alicia/Lavian
                # with one shared native Knight sprite. Their global named-job
                # mappings may now require two different job sprites. Spend
                # only unused capacity in the same nine-sprite budget.
                capacity = 9-monster_r-other_r
                generic_r = min(capacity,len(self.engine.mapsprite_selection[self.map_id])+1)
                self.engine.mapsprite_restrictions[self.map_id] = (generic_r,monster_r,other_r)
            self.engine.mapsprite_selection[self.map_id].add((base_job, gender))
        self.job = base_job.index
        try:
            assert len(self.engine.mapsprite_selection[self.map_id]) <= generic_r
        except Exception:
            pass
            raise ValueError(f'RCC native sprite constraint failed at {self.owner}: {generic_r} allowed, {[(j.index,g) for j,g in self.engine.mapsprite_selection[self.map_id]]}')
        if not self.has_special_graphic:
            self.set_gender(gender)
        self.mutate_equips()
        self.mutate_rsm()
        self.mutate_secondary()
        return True

    # RCC randomizer.py:2600-2609
    def set_gender(self, gender):
        if gender == 'male':
            self.set_bit('male', True)
            self.set_bit('female', False)
            self.graphic = 128
        elif gender == 'female':
            self.set_bit('female', True)
            self.set_bit('male', False)
            self.graphic = 129

    # RCC randomizer.py:2610-2644
    def mutate_equips(self):
        if self.get_bit('load_formation'):
            return
        for attr in ['lefthand', 'righthand', 'head', 'body', 'accessory']:
            if attr == 'righthand' and (not 1 <= self.level <= 5) and (self.has_swordskills or self.has_limitskills) and (self.engine.randint(1, 10) != 10) and self.get_bit('enemy_team'):
                if self.has_limitskills:
                    self.righthand = 32
                elif self.has_swordskills:
                    self.equip_appropriate_sword()
            elif self.has_special_graphic:
                value = getattr(self, attr)
                if value in [0, 255]:
                    setattr(self, attr, self.engine.random.choice([255, 254]))
                elif attr != 'righthand' and value != 254 and self.engine.random.choice([True, False]):
                    if self.get_bit('enemy_team'):
                        bf = self.engine.boostd['special_equipment']
                    else:
                        bf = self.engine.boostd['equipment']
                    value = self.engine.get_similar_item(value, same_equip=True, boost_factor=bf).index
                    if value in self.engine.BANNED_ITEMS and (not self.get_bit('enemy_team')):
                        continue
                    setattr(self, attr, value)
                elif self.engine.randint(1, 3) == 3:
                    setattr(self, attr, 254)
            elif self.engine.random.choice([True, False]):
                setattr(self, attr, 254)

    # RCC randomizer.py:2645-2680
    def equip_appropriate_sword(self):
        if self.level_normalized:
            if self.engine.random.choice([True, False]):
                self.righthand = 254
                return
            else:
                level = self.engine.randint(1, self.engine.randint(1, 40))
        else:
            level = self.level
        candidates = [i for i in self.engine.ItemObject.every if i.itemtype in [3, 4]]
        candidates = sorted(candidates, key=lambda c: (c.enemy_level, c.index))
        try:
            max_index = max([n for n, c in enumerate(candidates) if c.enemy_level <= level])
        except ValueError:
            max_index = 0
        exindex = None
        try:
            existing = self.engine.ItemObject.get(self.righthand)
            if existing and existing.itemtype in [3, 4]:
                exindex = candidates.index(existing)
                max_index = max(exindex, max_index)
        except KeyError:
            pass
        booster = self.engine.randint(2, self.engine.randint(3, 8))
        if self.has_special_graphic:
            pass
        else:
            booster = self.engine.randint(1, booster)
        max_index += booster
        index = self.engine.randint(self.engine.randint(1, max_index), max_index)
        if self.has_special_graphic and exindex:
            index = max(index, exindex + 1)
        chosen = candidates[:index][-1]
        self.righthand = chosen.index

    # RCC randomizer.py:2681-2696
    def mutate_rsm(self):
        if self.get_bit('load_formation'):
            return
        job = self.engine.JobObject.get(self.job)
        for attr in ['reaction', 'support', 'movement']:
            cands = [a for a in self.engine.AbilityObject.every if getattr(a, 'is_%s' % attr) is True]
            if self.has_special_graphic and self.engine.randint(1, 3) == 3:
                cands = sorted(cands, key=lambda a: a.jp_cost)
                index = len(cands) // 2
                index = self.engine.mutate_normal(index, minimum=0, maximum=len(cands) - 1)
                setattr(self, attr, cands[index].index)
            elif self.engine.random.choice([True, False]):
                setattr(self, attr, 510)

    # RCC randomizer.py:2697-2722
    def mutate_level(self):
        if self.index <= 4095 and self.get_bit('randomly_present') and (self.engine.randint(1, 15) == 15):
            if not self.level_normalized:
                self.level += self.engine.randint(0, 10) + self.engine.randint(0, 10)
                self.level = min(self.level, 99)
            else:
                if self.level > 199:
                    self.level = 100
                self.level += self.engine.randint(0, 10) + self.engine.randint(0, 10)
                self.level = min(self.level, 199)
            self.engine.SUPER_LEVEL_BOOSTED.append(self)
            return
        if not self.level_normalized:
            if self.is_lucavi:
                level = self.engine.mutate_normal(self.level, minimum=1, maximum=99)
                level = int(round((level + self.level) // 2))
                if level < self.level:
                    self.level += self.level - level
                else:
                    self.level = level
            if 5 <= self.level <= 99:
                self.level = self.engine.mutate_index(self.level, 99, (True, False), (-2, 3), (-1, 2))
            self.level = min(99, max(1, self.level))

    # RCC randomizer.py:2723-2747
    def mutate_stats(self):
        if self.job <= 3 or self.graphic <= 3:
            return
        self.mutate_level()
        for attr in ['brave', 'faith']:
            value = getattr(self, attr)
            if 0 <= value <= 100:
                value = self.engine.mutate_normal(value, minimum=0, maximum=100)
                setattr(self, attr, value)
        if self.named and self.name in self.engine.birthday_dict:
            self.month, self.day = self.engine.birthday_dict[self.name]
        elif self.named or self.engine.randint(1, 8) == 8:
            if self.engine.random.choice([True, False, False]):
                self.month = self.engine.randint(1, 12)
                self.day = self.engine.randint(1, self.engine.DAYS_IN_MONTH[self.month])
            elif not self.named and self.engine.randint(1, 10) == 10:
                self.month, self.day = (254, 254)
        if self.named and 1 <= self.month <= 12:
            self.engine.birthday_dict[self.name] = (self.month, self.day)


def _requirements(tables):
    if '_RCCJobRequirements' in tables: return tables['_RCCJobRequirements']
    general = tables['_RCCGeneralJobs']
    import json
    done = {}
    def expand(index, visiting=()):
        if index in done: return done[index]
        if index in visiting: raise ValueError('Native job requirements contain a cycle')
        result = {}
        row = general.get(index,{})
        for job,level in zip(_array(row.get('RequiredJobIds',[])),_array(row.get('RequiredJobLevels',[]))):
            if not level: continue
            result[job+74] = max(result.get(job+74,0),level)
            for upstream,needed in expand(job,visiting+(index,)).items():
                result[upstream] = max(result.get(upstream,0),needed)
        done[index] = result
        return result
    return {j+74:expand(j) for j in range(20)}


def _job_levels(tables):
    if '_RCCJobLevelJP' in tables: return tables['_RCCJobLevelJP']
    import json
    values = _array(tables['_RCCGeneralJobs'][0]['RequiredJobExp'])
    # Native GeneralJob has a level-zero entry, unlike RCC's eight thresholds.
    return values[1:] if len(values)==9 and values[0]==0 else values[:8]


def native_rankings(tables):
    """Baseline RCC make_rankings (3016-3177), including ENTD feature inference."""
    if '_RCCUnitRankings' in tables: return tables['_RCCUnitRankings']
    rows = tables['_RCCEffectiveUnitContext']
    occupied = [r for r in rows.values() if r['Spriteset']]
    good = sorted({r['MainJob'] for r in occupied}&tables['JobData'].keys())
    features = ('HPMultiplier','MPMultiplier','SpeedMultiplier','PAMultiplier',
                'MAMultiplier','Move','CharacterEvasion','MonsterPortrait')
    def value(job, field):
        result = tables['JobData'][job].get(field,tables['_JobTraits'][job].get(field,0))
        return result&15 if field=='Move' else result
    bounds = {}
    for field in features:
        values = [value(j,field) for j in good if value(j,field)>0]
        bounds[field] = (min(values),max(values)) if values else (0,0)
    ranks = {}
    for job in good:
        if sum(value(job,f)==0 for f in features)>len(features)//2:
            score = job*.0000001
        else:
            scores = [(value(job,f)-bounds[f][0])/(bounds[f][1]-bounds[f][0])
                      for f in features if value(job,f) and bounds[f][0]!=bounds[f][1]]
            scores = sorted(scores)[1:]
            score = sum(scores)/len(scores) if scores else 0
            traits = tables['_JobTraits'][job]
            score *= 1.5 if job in LUCAVI else 1.3 if not traits['MonsterPortrait'] else 1
            if _source_status(traits.get('InnateStatus',0)|traits.get('StartStatus',0))&(0xFFFFFFFFFF^VALID_START_STATUSES): score /= 10
        ranks['job',job] = score
    ranks.update({('level',i):i for i in range(100)})
    fieldmap = ('unlocked','unlocked_level','righthand','lefthand','head','body',
                'accessory','job','secondary','reaction','support','movement')
    units = [(owner,row) for owner,row in sorted(rows.items()) if row['Spriteset'] and
             (1<=owner[0]<254 or 384<=owner[0]<469 or owner[0]>=512)]
    previous = None
    for iteration in range(300):
        temporary, unitvalues = {}, []
        for owner,row in units:
            values = {'map_id':owner[0],**{f:row[RCC_NAMES[f]] for f in fieldmap}}
            inputs = [row['Level']] if 0<row['Level']<100 else []
            inputs.extend(ranks[f,v] for f,v in values.items() if (f,v) in ranks)
            rank = sum(inputs)/len(inputs) if inputs else None
            if rank is not None:
                for f,v in values.items():
                    if v&255 in (0,254,255): continue
                    if (f,v) not in temporary:
                        temporary[f,v] = [ranks[f,v]] if (f,v) in ranks else []
                    temporary[f,v].append(rank)
            result = row['Level'] if 0<row['Level']<100 else rank
            if result is not None: unitvalues.append(int(round(result)))
        ranks.update({key:sum(vals)/len(vals) for key,vals in temporary.items() if vals})
        if unitvalues==previous: break
        previous = unitvalues
    # Restore original job scores after iterative propagation (RCC3149-3150).
    original_jobs = native_job_scores(tables)
    ranks.update({('job',j):v for j,v in original_jobs.items()})
    jobvals = sorted(original_jobs.values())
    secvals = sorted(v for (kind,_),v in ranks.items() if kind=='secondary')
    for job in good:
        command = tables['JobData'][job]['JobCommandId']
        if ('secondary',command) in ranks or len(secvals)<2: continue
        index = jobvals.index(original_jobs[job])/len(jobvals)*max(len(secvals)-1,0)
        index = min(int(index),len(secvals)-2)
        ranks['secondary',command] = (secvals[index]+secvals[index+1])/2
    return ranks


def native_job_scores(tables):
    # Use the already independently verified baseline ordering/score calculation.
    traits = tables['_JobTraits']; jobs = tables['JobData']
    good = sorted({r['MainJob'] for r in tables['_RCCEffectiveUnitContext'].values() if r['Spriteset']}&jobs.keys())
    features = ('HPMultiplier','MPMultiplier','SpeedMultiplier','PAMultiplier','MAMultiplier','Move','CharacterEvasion','MonsterPortrait')
    def val(j,f):
        n = jobs[j].get(f,traits[j].get(f,0)); return n&15 if f=='Move' else n
    bounds = {f:(min(v),max(v)) for f in features if (v:=[val(j,f) for j in good if val(j,f)>0])}
    result = {}
    for j in good:
        if sum(not val(j,f) for f in features)>len(features)//2: result[j] = j*.0000001; continue
        scores = sorted((val(j,f)-bounds[f][0])/(bounds[f][1]-bounds[f][0]) for f in features
                        if val(j,f) and bounds[f][0]!=bounds[f][1])[1:]
        result[j] = (sum(scores)/len(scores) if scores else 0)*(1.5 if j in LUCAVI else 1.3 if not traits[j]['MonsterPortrait'] else 1)
        if _source_status(traits[j].get('InnateStatus',0)|traits[j].get('StartStatus',0))&(0xFFFFFFFFFF^VALID_START_STATUSES): result[j] /= 10
    return result


class UnitEngine:
    def __init__(self, before, tables, rng, chaos=1, random_degree=.25, requirements=None):
        self.before, self.tables, self.random = before, tables, rng
        self.random_degree = random_degree
        self.creatures = creature_jobs(tables)
        # Classic creature-shaped unique jobs 60..73 retain unique-unit
        # secondary/equipment handling in RCC. Ordinary monster species begin
        # at the independently anchored 94..141 table; 151 is Lucavi, while
        # FFTIC's additional real creature jobs use their native trait identity.
        self.unit_monsters = {j for j in self.creatures if j>=94 and j!=151}
        self.extra_entds = {e for e,s in tables['_RCCUnitContext'] if e>=512}
        self.selected = None
        self.backups = tables.get('_RCCUnitJPBackups',{})
        self.JOBNAMES, self.DAYS_IN_MONTH = JOBNAMES, DAYS_IN_MONTH
        self.JOBLEVEL_JP = _job_levels(tables)
        self.boostd = dict(jp=1.5**chaos,equipment=1.1**chaos,special_equipment=1.5**chaos,difficulty_factor=chaos)
        self.MUTATED_SKILLSETS = bool(tables.get('_RCCAbilityAudit',{}).get('exchanged_command_count') or tables.get('_RCCSkillsetsMutated'))
        self.BANNED_ITEMS = (73,)
        self.named_jobs, self.named_map_jobs, self.birthday_dict = {},{},{}
        self.monster_selection, self.mapsprite_restrictions, self.mapsprite_selection = {},{},{}
        self.SUPER_LEVEL_BOOSTED = []
        self.jobreq_indexdict = {j:ProgressionJob(self,j,r) for j,r in (requirements or _requirements(tables)).items()}
        self.jobreq_namedict = {j.name:j for j in self.jobreq_indexdict.values()}
        self.JobReqObject = SimpleNamespace(every=list(self.jobreq_indexdict.values()),get_by_name=self.jobreq_namedict.get,get=self.jobreq_indexdict.get)
        self.jobs = {j:NativeJob(self,j,r) for j,r in tables['JobData'].items()}
        self.JobObject = SimpleNamespace(get=self.jobs.get,every=list(self.jobs.values()))
        self.costs = {a:r['JPCost'] for a,r in tables['_AbilityMetadata'].items()}
        self.costs.update(tables.get('_RCCAbilityAudit',{}).get('jp_cost_updates',{}))
        self.costs.update(tables.get('_RCCStatAudit',{}).get('jp_cost_updates',{}))
        self.skills = {i:NativeSkillset(self,i,r) for i,r in tables['JobCommandData'].items()}
        self.SkillsetObject = SimpleNamespace(get=self.skills.get,every=list(self.skills.values()))
        self.abilities = [SimpleNamespace(index=a,jp_cost=self.costs[a],
                         is_reaction=r['AbilityType']==7,is_support=r['AbilityType']==8,
                         is_movement=r['AbilityType']==9) for a,r in tables['_AbilityMetadata'].items()]
        self.AbilityObject = SimpleNamespace(every=self.abilities)
        self.items = {}
        for i,r in tables['ItemData'].items():
            misc = r['TypeFlags']
            item = SimpleNamespace(index=i,itemtype=r['ItemCategory'],
                 price=r.get('Price',0),enemy_level=r['RequiredLevel'],misc1=misc)
            item.rank = -1 if not i else item.price+(65000+item.enemy_level*100 if item.price<=10 or i in (106,143) else 0)
            self.items[i] = item
        self.ItemObject = SimpleNamespace(every=list(self.items.values()),get=lambda i:self.items[i])
        self.units = [NativeUnit(self,owner,row) for owner,row in sorted(tables['_RCCUnitContext'].items())]
        self.UnitObject = SimpleNamespace(every=self.units,get=lambda i:self.units[i])
        self.mapunits, self.mapsprites = {},{}
        for u in self.units:
            self.mapunits.setdefault(u.map_id,[]).append(u)
            self.mapsprites.setdefault(u.map_id,set()).add((u.graphic,u.job))
        self.ranks = tables.get('_RCCUnitRankings') or native_rankings(before)
        tables['_RCCUnitRankings'] = self.ranks
        self.secondaries = self._rank_secondaries()

    def randint(self,a,b): return rcc_randint(self.random,a,b)
    def mutate_normal(self,v,minimum=0,maximum=255,**kwargs):
        return rcc_normal(v,minimum,maximum,self.random,random_degree=self.random_degree,**kwargs)
    def mutate_index(self,index,length,continuation=None,basic_range=None,extended_range=None):
        continuation = [True,False] if continuation is None else continuation
        basic_range = (-3,3) if basic_range is None else basic_range
        extended_range = (-1,1) if extended_range is None else extended_range
        index = min(max(index+self.random.randint(*basic_range),0),length-1)
        while self.random.choice(continuation):
            index = min(max(index+self.random.randint(*extended_range),0),length-1)
        return index
    def calculate_jp_total(self,levels): return sum(self.JOBLEVEL_JP[level-1] for level in levels if level)
    def get_job(self,j): return self.jobs.get(j)
    def get_skillset(self,s): return self.skills.get(s)
    def get_ranked_secondaries(self): return list(self.secondaries)
    def get_ranked(self,category,full=False):
        values = sorted((rank,value) for (kind,value),rank in self.ranks.items() if kind==category)
        return {value:rank for rank,value in values} if full else [value for rank,value in values]
    def get_ranked_items(self):
        return sorted((i for i in self.items.values() if i.index),key=lambda i:(i.rank,i.index))
    def source_environment(self):
        """Bindings for other source-adapted encounter/formation functions.

        The world adapter adds map/event objects; it should retain these live
        dictionaries and unit wrappers so phases operate on the same rows.
        """
        names = ('random','randint','mutate_normal','mutate_index','get_job','get_skillset',
                 'JobObject','SkillsetObject','UnitObject','ItemObject','AbilityObject','JobReqObject',
                 'get_ranked','get_ranked_items','get_ranked_monster_jobs','get_ranked_secondaries',
                 'get_similar_item','calculate_jp_total','JOBLEVEL_JP','JOBNAMES','DAYS_IN_MONTH',
                 'boostd','birthday_dict','named_jobs','named_map_jobs','monster_selection','mapunits',
                 'mapsprites','mapsprite_restrictions','mapsprite_selection','SUPER_LEVEL_BOOSTED',
                 'MUTATED_SKILLSETS','jobreq_indexdict','jobreq_namedict','BANNED_ITEMS')
        result = {name:getattr(self,name) for name in names}
        result.update(get_units=lambda:list(self.units),get_unit=self.UnitObject.get,
                      get_jobs=lambda:list(self.jobs.values()),get_skillsets=lambda:list(self.skills.values()),
                      get_items=lambda:list(self.items.values()),xrange=range,LUCAVI_JOBS=sorted(LUCAVI),
                      set_progress_counter=lambda *args:None,check_progress_counter=lambda *args:None)
        return result
    def get_ranked_monster_jobs(self):
        return [self.jobs[j] for j in sorted(self.jobs,key=lambda j:(self.ranks.get(('job',j),0),j))
                if j in self.unit_monsters and ('job',j) in self.ranks]
    def monster_check(self,u):
        return u.graphic==130 and u.has_monster_job and u.job not in (145,151) and (u.map_id<=469 or u.map_id in self.extra_entds)
    def boco_candidates(self):
        # Source2379-2397 plus FFTIC's native added monster variants. Keep
        # only occupied, real monster jobs; unused WOTL placeholders stay out.
        classic = list(range(94,142))+[144,145,150,153,154]
        extras = sorted(j for j in self.unit_monsters if j>=169)
        return [j for j in classic+extras if j in self.unit_monsters]
    def get_similar_item(self,base_item,same_type=False,same_equip=False,boost_factor=1.):
        base = self.items[base_item] if isinstance(base_item,int) else base_item
        items = sorted((i for i in self.items.values() if i.index),key=lambda i:(i.rank,i.index))
        if same_type: items = [i for i in items if i.itemtype==base.itemtype]
        if same_equip: items = [i for i in items if i.misc1&248==base.misc1&248]
        index = items.index(base); reverse = len(items)-index-1
        boost = min(max(int(round(reverse/boost_factor)),0),len(items)-1)
        reverse = self.randint(min(boost,reverse),max(boost,reverse))
        index = self.mutate_normal(len(items)-reverse-1,0,len(items)-1)
        return items[index]
    def _rank_secondaries(self):
        def clean(kind):
            ranks = {v:r for (k,v),r in self.ranks.items() if k==kind}
            low,high = min(ranks.values()),max(ranks.values())
            return {v:(r-low)/(high-low) if high!=low else 0 for v,r in ranks.items()}
        ranks = clean('secondary')
        for job,rank in clean('job').items(): ranks[self.jobs[job].skillset] = rank
        candidates = {}
        for command,skill in self.skills.items():
            if command not in ranks: continue
            rank = ranks[command]**2*skill.num_actions
            if rank>0:
                costs = [min(self.costs[a],1000) if self.costs.get(a,0)>0 else 1000 for a in skill.actions]
                if costs: rank *= sum(costs)//len(costs)
                elif not skill.num_free_actions: rank = 0
                if command<=24: rank /= 2
            candidates[command] = rank
        return sorted((c for c,r in candidates.items() if r>0),key=lambda c:(candidates[c],c))


    # RCC randomizer.py:3820-3880
    def mutate_units(self):
        units = list(self.units)
        for key, value in sorted(self.mapsprites.items()):
            value = sorted(value)
            generic = len([_ for g, _ in value if g in (128, 129)])
            monster = len([_ for g, _ in value if g == 130])
            other = len([_ for g, _ in value if g not in (128, 129, 130, 0)])
            if key in [411, 426]:
                other = max(other, 3)
            remaining = 9 - (generic + monster + other)
            if remaining > 0 and key in range(256, 331):
                generic += remaining
            elif key >= 384 and generic > 2 and (other > 2):
                generic -= 1
            self.mapsprite_restrictions[key] = (generic, monster, other)
            self.mapsprite_selection[key] = set([])
        named_units = {}
        for u in units:
            if u.named and (not u.has_special_graphic):
                if u.map_id not in named_units:
                    named_units[u.map_id] = []
                named_units[u.map_id].append(u)
        pass
        map_ids = sorted(named_units, key=lambda m: len(named_units[m]))
        map_ids = reversed(map_ids)
        for m in map_ids:
            nus = named_units[m]
            nuslen = len(nus)
            self.random.shuffle(nus)
            males = [u for u in nus if u.get_bit('male')]
            females = [u for u in nus if u.get_bit('female')]
            monsters = [u for u in nus if u.get_bit('monster')]
            nus = males[1:] + females[1:] + monsters[1:]
            self.random.shuffle(nus)
            nus = males[:1] + females[:1] + monsters[:1] + nus
            assert len(set(nus)) == nuslen
            for u in nus:
                assert not u.has_special_graphic
                u.mutate()
                u.job_mutated = True
        self.random.shuffle(units)
        unnamed = [u for u in units if u.has_special_graphic or not u.named]

        for i, u in enumerate(unnamed):
            if u.index >> 4 == 307:
                continue

            u.mutate()


def apply_job_unit_overrides(result, overrides):
    """RCC Lucavi/innate unit RSM writes, before the independent u phase."""
    mapping = {o['job']:o for o in overrides}
    count = 0
    for row in result['_RCCUnitContext'].values():
        override = mapping.get(row['MainJob'])
        if override is None: continue
        for source,native in (('ReactionAbilityId','Reaction'),('SupportAbilityId','Support'),('MovementAbilityId','Movement')):
            if source in override: row[native] = override[source]
        count += 1
    return count


def prepare_unit_backups(before,result,rng,random_degree=.25):
    """Invoke in r after JP thresholds mutate and BEFORE the tree changes."""
    requirements = result.get('_RCCOriginalJobRequirements',_requirements(before))
    engine = UnitEngine(before,result,rng,random_degree=random_degree,requirements=requirements)
    backups = {}
    for u in engine.units:
        u.set_backup_jp_total()
        backups[u.owner] = u.backup_jp_total
    result['_RCCUnitJPBackups'] = backups
    return backups


def apply_units(before,result,seed,flags,degree=1,chaos=1,random_degree=.25):
    if not 0<=degree<=1: raise ValueError('Unit degree must be between zero and one')
    if 'u' not in flags or not degree: return dict(changed_units=0,changed_fields=0)
    rng = rng_for(seed,'units-u')
    engine = UnitEngine(before,result,rng,chaos,random_degree)
    engine.MUTATED_SKILLSETS = 's' in flags and bool(result.get('_RCCAbilityAudit',{}))
    # Source probabilities stay exact at 100%. Lower degrees select complete
    # templates: mixing old and new species/job sprites within a partially
    # changed roster can exceed its native graphics budget.
    snapshot = {owner:row.copy() for owner,row in result['_RCCUnitContext'].items()}
    selected_maps = None if degree==1 else {m for m in sorted(engine.mapunits) if rng.random()<degree}
    selected = None if selected_maps is None else {u.owner for u in engine.units if u.map_id in selected_maps}
    engine.selected = selected
    engine.mutate_units()
    changed,fields = [],0
    for owner,row in result['_RCCUnitContext'].items():
        differences = sum(row[k]!=snapshot[owner][k] for k in snapshot[owner])
        if differences: changed.append(owner); fields += differences
    result['_RCCUnitEngine'] = engine
    from .rcc import remember_rng
    remember_rng(result,rng)
    return dict(changed_units=len(changed),changed_fields=fields,
                units=changed,elite_units=[u.owner for u in engine.SUPER_LEVEL_BOOSTED],
                sprite_restrictions={m:r for m,r in engine.mapsprite_restrictions.items()},
                ranking_source='native original ENTD baseline; RCC3016-3177',
                degree_semantics='fraction of complete encounter templates')


def finalize_cleanup(before,result,seed,flags,*,rng=None,engine=None):
    """RCC5239-5260 palette cleanup, recruit normalization and Orbonne control.

    ``rng`` is the last phase's RNG for the unconditional palette cleanup.
    Recruit normalization resets its own seed just as the original does.
    Parent applies this once after unit/formation/reward/surprise phases.
    """
    engine = engine or result.get('_RCCUnitEngine') or UnitEngine(before,result,rng or rng_for(seed,'cleanup'))
    if rng is not None: engine.random = rng
    palettes = 0
    for u in engine.units:
        old = u.palette
        u.clean()
        palettes += u.palette!=old
    normalized,controlled = [],[]
    if set(flags)&set('rujimtpsazfyw'):
        anchors = {0x1951:(12,12,12),0x19d0:(30,30,30),0x1a10:(21,21,21),
                   0x1ac0:(25,25,25),0x1b10:(41,41,41)}
        original = before['_RCCEffectiveUnitContext']
        engine.random = rng_for(seed,'cleanup-recruits')
        for index,expected in anchors.items():
            owner = (index>>4,index&15)
            row = original[owner]
            if (row['Spriteset'],row['NameId'],row['MainJob'])!=expected:
                raise ValueError(f'Native RCC recruit anchor changed at ENTD {owner}')
            unit = engine.UnitObject.get(index)
            unit.normalize_level(engine.randint(1,3))
            normalized.append(owner)
        for u in engine.mapunits[387]:
            if not u.get_bit('enemy_team'):
                u.set_bit('control',True)
                controlled.append(u.owner)
    return dict(palette_units=palettes,normalized_recruits=normalized,
                controlled_orbonne_allies=controlled)
