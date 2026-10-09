"""RCC r phase: global JP thresholds and an acyclic ordinary job tree.

Port of randomizer.py:3350-3527. Extra WOTL requirement rows are preserved.
"""
import copy
import json
import math

from .rcc import mutate_normal, randint, rng_for,remember_rng
from .rcc_world_data import JOB_REQUIREMENT_FIELDS, world_nex_update


MAGES = (5, 6, 7, 11)
CALCULATOR = 16
GENDER_JOBS = {17, 18}


def _array(value):
    return json.loads(value) if isinstance(value, str) else list(value)


def expand_requirements(general):
    """Return the source's transitive maximum job-level requirements."""
    direct = {}
    for job in range(20):
        row = general[job]
        direct[job] = {source: level for source, level in zip(_array(row['RequiredJobIds']), _array(row['RequiredJobLevels'])) if level > 0}
    def expand(job, trail=()):
        if job in trail:
            raise ValueError('Job requirements contain a cycle')
        values = dict(direct[job])
        for source in list(values):
            if source not in direct or not 1 <= values[source] <= 8:
                raise ValueError('Invalid ordinary job requirement')
            for upstream, level in expand(source, trail+(job,)).items():
                values[upstream] = max(values.get(upstream, 0), level)
        return values
    return {job: expand(job) for job in range(20)}


def mutate_job_level(thresholds, rng, chaos=1.0, random_degree=.25):
    """RCC's US difficulty boost on the verified Enhanced baseline curve."""
    if len(thresholds) != 8 or any(a > b for a, b in zip([0]+thresholds, thresholds)):
        raise ValueError('Expected eight cumulative job JP thresholds')
    cumulative = [0]
    for a, b in zip([0]+thresholds, thresholds):
        diff = b-a
        diff = randint(rng, diff, int(diff*(1.5**min(chaos, 500))))
        diff = mutate_normal(min(diff, 800), 0, 800, rng, random_degree=random_degree)
        diff = int(round(diff*2, -2))//2
        cumulative.append(cumulative[-1]+diff)
    return cumulative[1:]


def mutate_job_requirements(original, rng):
    """Source list/set choices, branch balancing and Calculator protection."""
    requirements = copy.deepcopy(original)
    done = [0]
    levels = ([rng.randint(0, 1)] + [rng.randint(1, 2) for _ in range(2)] +
              [rng.randint(2, 3) for _ in range(2)] + [rng.randint(3, 5) for _ in range(4)] +
              [rng.randint(5, 8) for _ in range(4)] + [rng.randint(8, 13)+rng.randint(0, 8) for _ in range(3)] +
              [rng.randint(13, 21)+rng.randint(0, 13) for _ in range(2)] + [rng.randint(34, 55)])
    jobpools = [set() for _ in range(2+rng.choice((0, 0, 1)))]
    allpool = {0}
    jobs = list(range(1, 20))
    while True:
        rng.shuffle(jobs)
        mages = [job for job in MAGES if jobs.index(job) < jobs.index(CALCULATOR)]
        if mages:
            break
    def remax(job, trail=()):
        if job in trail:
            raise ValueError('RCC generated a cyclic job tree')
        for prerequisite in list(requirements[job]):
            remax(prerequisite, trail+(job,))
            for source, needed in requirements[prerequisite].items():
                requirements[job][source] = max(requirements[job].get(source, 0), needed)
    for job, numlevels in zip(jobs, levels):
        base_numlevels = numlevels
        requirements[job] = {}
        sublevels = []
        pool_candidates = [pool for pool in jobpools if pool & set(mages)] if job == CALCULATOR else []
        if not pool_candidates:
            shortest = min(map(len, jobpools))
            pool_candidates = [pool for pool in jobpools if len(pool) == shortest]
        jobpool = rng.choice(pool_candidates)
        if base_numlevels >= 30 or rng.randint(1, 15) == 15:
            candidates = [candidate for candidate in done if candidate not in GENDER_JOBS]
        else:
            effective = set(jobpool)
            while len(effective) < base_numlevels:
                if allpool <= effective:
                    break
                all_candidates = sorted(allpool-effective)
                if len(all_candidates) > 1:
                    all_candidates = [candidate for candidate in all_candidates if candidate != 0]
                effective.add(rng.choice(all_candidates))
            candidates = [candidate for candidate in done if candidate in effective and candidate not in GENDER_JOBS]
        while numlevels > 1:
            sublevel = min(rng.randint(2, 3)+rng.randint(0, 1), numlevels)
            if len(sublevels) == 14 or len(sublevels) == len(candidates):
                index = 0 if len(sublevels) == 1 else rng.randint(0, len(sublevels)-1)
                sublevels[index] = min(sublevels[index]+sublevel, 8)
            else:
                sublevels.append(sublevel)
            numlevels -= sublevel
        if numlevels == 1:
            if sublevels:
                index = rng.randint(0, len(sublevels)-1)
                sublevels[index] = min(sublevels[index]+1, 8)
            else:
                sublevels = [1]
        if len(sublevels) > min(len(candidates), 14):
            raise ValueError('RCC requirement allocation exceeded its source capacity')
        if job != CALCULATOR:
            if len(candidates) >= len(sublevels)+1:
                candidates = candidates[:-1]
            if len(candidates) >= len(sublevels)+1 and rng.choice((True, False)):
                candidates = candidates[1:]
        while True:
            remaining, prerequisites = list(candidates), []
            for _ in range(len(sublevels)):
                eligible = [candidate for candidate in remaining
                            if not any(requirements[prerequisite].get(candidate, 0) > 0 for prerequisite in prerequisites)]
                if not eligible:
                    eligible = list(remaining)
                index = len(eligible)-1
                while index > 0:
                    if rng.choice((True, False)):
                        if index <= 3 and rng.choice((True, False)):
                            break
                        index -= 1
                    else:
                        break
                prerequisite = eligible[index]
                prerequisites.append(prerequisite)
                remaining.remove(prerequisite)
            if job != CALCULATOR or set(prerequisites) & set(mages):
                break
        if job == CALCULATOR:
            sublevels.sort()
            chosen = rng.choice(sorted(set(prerequisites) & set(mages)))
            prerequisites.remove(chosen)
            rng.shuffle(prerequisites)
            prerequisites.append(chosen)
        requirements[job] = dict(zip(prerequisites, sublevels))
        for other in jobs:
            remax(other)
        done.append(job)
        if job not in GENDER_JOBS:
            if base_numlevels >= rng.randint(0, 1)+rng.randint(0, 1):
                jobpool.add(job)
            else:
                allpool.add(job)
    return requirements


def apply_requirements(before, result, seed, flags, degree=1.0, chaos=1.0, random_degree=.25):
    if not all(math.isfinite(value) for value in (degree, chaos, random_degree)) or not 0 <= degree <= 1 or chaos < 0 or not 0 <= random_degree <= 1:
        raise ValueError('Invalid RCC requirement settings')
    general = result['_RCCGeneralJobs']
    original = expand_requirements(before['_RCCGeneralJobs'])
    curves = {tuple(_array(row['RequiredJobExp'])) for job, row in before['_RCCGeneralJobs'].items() if job < 20}
    if len(curves) != 1:
        raise ValueError('RCC global job JP curve requires a shared ordinary-job baseline')
    curve = list(next(iter(curves)))
    if len(curve) != 9 or curve[0] != 0:
        raise ValueError('Enhanced job curve must include the initial level-one zero')
    thresholds, requirements = curve[1:], original
    enabled = 'r' in flags and degree > 0
    rng = rng_for(seed, 'requirements-r')
    # A tree is selected as a whole; partial independent rows can create cycles.
    if enabled and degree < 1 and rng.random() >= degree:
        enabled = False
    if enabled:
        thresholds = mutate_job_level(thresholds, rng, chaos, random_degree)
        result['_RCCOriginalJobRequirements'] = {job+74: {source+74: level for source, level in req.items()} for job, req in original.items()}
        result['_RCCJobLevelJP'] = list(thresholds)
        # RCC5094-5096 consumes backup-unit JP draws in this same r stream,
        # after the curve changes but before the requirement tree changes.
        from .rcc_units import prepare_unit_backups
        prepare_unit_backups(before, result, rng, random_degree=random_degree)
        requirements = mutate_job_requirements(original, rng)
        for item in (0x7A, 0x7D):
            result['ItemData'][item]['RequiredLevel'] = max(result['ItemData'][item]['RequiredLevel'], 5)
        for job in range(20):
            req = requirements[job]
            # RCC's displayed prereq dictionary removes requirements already
            # implied by another prerequisite. Native JobNeedLevel still
            # receives its complete transitive closure below.
            sources = [source for source in sorted(req)
                       if not any(other != source and requirements[other].get(source, 0) >= req[source] for other in req)]
            original_positions = dict(zip(_array(before['_RCCGeneralJobs'][job]['RequiredJobIds']),
                                          _array(before['_RCCGeneralJobs'][job]['RequiredJobPositions'])))
            positions = [original_positions.get(source, 3) for source in sources]
            fields = dict(RequiredJobExp=[0]+thresholds, RequiredJobIds=sources,
                          RequiredJobLevels=[req[source] for source in sources],
                          RequiredJobPositions=positions)
            general[job].update(copy.deepcopy(fields))
            world_nex_update(result, 'GeneralJob', (job,), fields)
            if job:
                row = result['JobNeedLevelData'][job-1]
                for source, field in enumerate(JOB_REQUIREMENT_FIELDS[:20]):
                    row[field] = req.get(source, 0)
    result['_RCCOriginalJobRequirements'] = {job+74: {source+74: level for source, level in req.items()} for job, req in original.items()}
    result['_RCCJobRequirements'] = {job+74: {source+74: level for source, level in req.items()} for job, req in requirements.items()}
    result['_RCCJobLevelJP'] = list(thresholds)
    audit = dict(mode='RCC job requirements', enabled=enabled, jp_thresholds=list(thresholds),
                 ordinary_jobs=20, preserved_extra_requirement_rows=[19, 20, 21],
                 calculator_has_mage=bool(set(requirements[CALCULATOR]) & set(MAGES)),
                 source='randomizer.py:3350-3527',
                 adaptations=['Enhanced baseline JP curve is retained as the input',
                              'RequiredJobExp has a native level-one zero before eight thresholds',
                              'WOTL-only requirement rows are preserved',
                              'GeneralJob receives source-reduced immediate prerequisites; native rows retain full closure',
                              'Existing prerequisite label positions survive; new labels use valid native position3'])
    result['_RCCRequirementAudit'] = audit
    if enabled:
        remember_rng(result,rng)
    return audit
