"""RCC job stat and skill JP rules (randomizer.py:1889-1940,3529-3584)."""
from .game import JOB_FIELDS, ACTION_FIELDS, RSM_FIELDS
from .rcc import rng_for, mutate_normal, randint,remember_rng
from .rcc_context import LUCAVI
from .rcc_innates import innate_scopes, apply_innates
from .rcc_status import metadata_updates


def stat_boost(tables, job, chaos):
    if 74 <= job < 94:
        level = tables['_RCCGenericRanks'][job]*50-25
    else:
        units = [u for u in tables['_RCCUnits'] if u['job']==job and u['enemy']
                 and 0<u['level']<100 and 384<=u['map_id']<=469]
        if not units: return 1.0
        levels = sorted(u['level'] for u in units)[-2:]
        level = sum(levels)/len(levels)
    return (1+level/100)**((.75 if job in LUCAVI else .6)*chaos)


def mutate_job_stat(before, result, job, rng, random_degree=.25, chaos=1):
    """One source JobObject.mutate_stats call, including zero/dummy records."""
    row = result['JobData'][job]
    boost = stat_boost(before,job,chaos)
    for field in JOB_FIELDS:
        old = row[field]
        factor = boost**.5 if 'Growth' in field or 'Multiplier' in field or field=='Move' else boost
        value = old/factor if 'Growth' in field else old*factor
        value = max(1,min(value,253))
        new = mutate_normal(value,1,253,rng,random_degree=random_degree)
        if job in LUCAVI:
            if 'Growth' in field and new>old: new = old-abs(old-new)
            elif 'Growth' not in field and new<old: new = old+abs(old-new)
        row[field] = max(1,min(new,253))


def apply_monster_stats_innates(before, result, seed, random_degree=.25, chaos=1,
                               degree=1., *, rng=None):
    """RCC m stats/innates interleaved; continue the passed RNG into abilities."""
    rng = rng or rng_for(seed,'monster-phase-m')
    def stat_before_innate(flag, job, shared_rng):
        mutate_job_stat(before,result,job,shared_rng,random_degree,chaos)
    return apply_innates(before,result,seed,'m',degree,random_degree,
                         rngs={'m':rng},before_job=stat_before_innate)


def apply_job_stats(before, result, seed, flags, random_degree=.25, chaos=1):
    """RCC j human stats followed by JP/learn rates in one source-order stream.

    The m branch is retained as a low-level stats-only interface. Production
    m uses apply_monster_stats_innates and passes its RNG onward to abilities.
    """
    changed = []
    scopes = innate_scopes(before)
    rng_j = None
    for flag, jobs in (('j',scopes['i']),('m',scopes['m'])):
        if flag not in flags: continue
        rng = rng_for(seed,'stats-'+flag)
        if flag == 'j': rng_j = rng
        for job in sorted(jobs):
            mutate_job_stat(before,result,job,rng,random_degree,chaos)
            changed.append(job)
    updates = dict(result.get('_RCCAbilityAudit',{}).get('jp_cost_updates',{}))
    if 'j' in flags:
        rng = rng_j
        costs = {a:r['jp_cost'] for a,r in before['_AbilityCatalog'].items()}
        # Innate/pool setup may already have forced Master Teleportation 9999.
        costs.update({a:r['JPCost'] for a,r in result.get('_RCCMetadataUpdates',{}).items()
                      if 'JPCost' in r})
        costs.update(updates)
        chances = {a:r['LearnChance'] for a,r in result['_AbilityMetadata'].items()}
        commands = sorted(result['JobCommandData'])
        rng.shuffle(commands)
        commands = [c for c in commands if not 5<=c<=24]+[c for c in commands if 5<=c<=24]
        for command in commands:
            row = result['JobCommandData'][command]
            abilities = [row[f] for f in ACTION_FIELDS+RSM_FIELDS if row[f]]
            count = len(abilities)
            if not count: continue
            average = sum(costs[a] for a in abilities)//count
            for index,aid in enumerate(abilities):
                old = costs[aid]
                if old<=0:
                    chances[aid] = 100
                    continue
                value = mutate_normal(min(old,3000),1,max(old,3000),rng,random_degree=random_degree)
                value = int(round(value*2,-2)/2) if value>200 else int(round(value,-1))
                costs[aid] = value
                if count==1:
                    chances[aid] = 100
                elif 1<=chances[aid]<=99 or randint(rng,1,20)==20:
                    factor = index/(count-1)
                    jp_factor = value/float(average) if average else 0
                    k = min(average/500.,1)
                    rate = 100
                    if jp_factor:
                        rate = factor*110+(1-factor)*(25/jp_factor)
                        rate = (rate**2)/90
                        rate = k*rate+(1-k)*100
                    rate = min(90,max(rate,randint(rng,10,40)))
                    chances[aid] = mutate_normal(rate,0,100,rng,random_degree=random_degree)
                if not 0 <= chances[aid] <= 100:
                    raise ValueError('RCC learn chance exceeded 0-100')
        for aid,value in costs.items():
            result['_AbilityMetadata'][aid]['JPCost'] = value
        for aid,value in chances.items():
            result['_AbilityMetadata'][aid]['LearnChance'] = value
        updates = {a:v for a,v in costs.items() if v!=before['_AbilityCatalog'][a]['jp_cost']}
    native_updates = metadata_updates(before,result) if 'j' in flags else {}
    learn_updates = {a:r['LearnChance'] for a,r in native_updates.items() if 'LearnChance' in r}
    if set(flags)&set('jm'):
        remember_rng(result,rng)
    return dict(changed_jobs=changed,jp_cost_updates=updates,
                learn_chance_updates=learn_updates,metadata_updates=native_updates,
                limitations=[])
