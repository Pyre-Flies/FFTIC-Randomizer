"""RCC JobObject innate rules, adapted without changing native enum byte order.

The source operates on little-endian integers. The loader's five-byte enums
are big-endian; convert at the boundary rather than reinterpret its flags.
``mutate_job_innate`` accepts a shared RNG so the monster phase can interleave
its stat and innate mutations in the original order.
"""
import math

from .catalog import creature_jobs
from .game import JOB_FIELDS
from .rcc import mutate_bits, mutate_normal, randint, rng_for,remember_rng


MASK40 = (1 << 40) - 1
VALID_INNATE_STATUSES = 0xCAFCE12A10
VALID_START_STATUSES = VALID_INNATE_STATUSES | 0x1402100000
BENEFICIAL_STATUSES = 0xC278600000
RERAISE_STATUS = 0x0000200000
FAITH_STATUS = 0x8000000000
INNOCENT_STATUS = 0x4000000000
LUCAVI_JOBS = frozenset((60, 62, 64, 65, 67, 69, 73, 151))
MP_RESTORE_INNATES = (0x1EE, 0x1B6, 0x1B0)
LUCAVI_INNATES = tuple(
    list(range(0x1A6, 0x1A9)) + [0x1AA] + list(range(0x1AC, 0x1B0)) +
    list(range(0x1B1, 0x1B4)) + [0x1B5, 0x1BA, 0x1BD, 0x1BE] +
    list(range(0x1C0, 0x1C6)) + list(range(0x1D1, 0x1D6)) +
    [0x1D8, 0x1DD, 0x1E3, 0x1E7, 0x1E8] + list(range(0x1EB, 0x1EE)) +
    [0x1F2, 0x1F3, 0x1FA, 0x1FB] + list(MP_RESTORE_INNATES))
INNATE_FIELDS = tuple(f'InnateAbilityId{i}' for i in range(1, 5))
STATUS_FIELDS = ('InnateStatus', 'ImmuneStatus', 'StartingStatus')
ELEMENT_FIELDS = ('AbsorbElements', 'NullifyElements', 'HalveElements', 'WeakElements')


def swap_mask(value, size=5):
    """Translate a fixed-size little-endian RCC integer and native enum mask."""
    if not isinstance(value, int) or not 0 <= value < 1 << (size * 8):
        raise ValueError(f'Mask must fit {size} bytes')
    return int.from_bytes(value.to_bytes(size, 'little'), 'big')


def innate_scopes(tables):
    """Keep RCC's literal classic indices, then include populated added jobs."""
    jobs = tables['JobData']
    creatures = creature_jobs(tables)
    human = sorted(j for j in jobs if j < 94)
    monster = sorted(j for j in jobs if 94 <= j < 160)
    for job in sorted(j for j in jobs if j >= 160):
        row = jobs[job]
        if row.get('JobCommandId', 0) and any(row.get(f, 0) for f in JOB_FIELDS):
            (monster if job in creatures else human).append(job)
    return {'i': human, 'm': monster}


def mutate_statuses(index, row, rng):
    """Mutate source-order masks in place (not the native aggregate enums)."""
    immune = mutate_bits(row['ImmuneStatus'], rng, size=40, odds_multiplier=4.)
    changed = immune ^ row['ImmuneStatus']
    for i in range(40):
        mask = 1 << i
        if mask & changed:
            if mask & BENEFICIAL_STATUSES or randint(rng, 1, 50) == 50:
                row['ImmuneStatus'] ^= mask
            else:
                row['ImmuneStatus'] |= mask
    not_innate = MASK40 ^ row['InnateStatus']
    not_start = MASK40 ^ row['StartingStatus']
    row['ImmuneStatus'] &= not_innate & not_start
    vulnerable = MASK40 ^ row['ImmuneStatus']
    innate = mutate_bits(row['InnateStatus'], rng, size=40, odds_multiplier=4.)
    innate &= vulnerable & VALID_INNATE_STATUSES
    not_innate2 = MASK40 ^ innate
    start = mutate_bits(row['StartingStatus'], rng, size=40, odds_multiplier=4.)
    start &= vulnerable & not_innate & not_innate2 & VALID_START_STATUSES
    if 74 <= index < 94 and innate & RERAISE_STATUS and randint(rng, 1, 100) != 100:
        innate ^= RERAISE_STATUS
        start |= RERAISE_STATUS
    row['InnateStatus'] |= innate
    row['StartingStatus'] |= start


def _force_teleport_cost(result):
    # The source's get_abilities does this every time it initializes a pool.
    if 499 not in result['_AbilityMetadata']:
        raise ValueError('RCC innate rules require native ability 499')
    result['_AbilityMetadata'][499]['JPCost'] = 9999
    result.setdefault('_RCCMetadataUpdates', {}).setdefault(499, {})['JPCost'] = 9999


def mutate_job_innate(result, index, rng, random_degree=.25):
    """Apply exactly one job's RCC rules; return an optional Lucavi unit override.

    This routine mutates public JobData and private metadata only. It never
    writes encounter rows itself; the parent applies its explicit override to
    every native unit using the job before running encounter randomization.
    """
    native = result['JobData'][index]
    required = ('EquippableItems',) + INNATE_FIELDS + STATUS_FIELDS + ELEMENT_FIELDS
    missing = set(required) - native.keys()
    if missing:
        raise ValueError(f'RCC innates require JobData[{index}] fields: {sorted(missing)}')
    row = dict(native)
    for field in STATUS_FIELDS:
        row[field] = swap_mask(row[field])
    # FFTIC adds a fifth permission byte. Preserve it; RCC knows four bytes.
    equipment = swap_mask(native['EquippableItems'] >> 8, 4)
    equipment = mutate_bits(equipment, rng, size=32, odds_multiplier=4.)
    row['EquippableItems'] = (swap_mask(equipment, 4) << 8) | (native['EquippableItems'] & 255)
    if rng.choice([True, False]):
        row['NullifyElements'] = mutate_bits(row['NullifyElements'], rng)
        vulnerable = 255 ^ row['NullifyElements']
        row['AbsorbElements'] = mutate_bits(row['AbsorbElements'], rng) & vulnerable
        row['HalveElements'] = mutate_bits(row['HalveElements'], rng) & vulnerable
        vulnerable = 255 ^ (row['NullifyElements'] | row['HalveElements'])
        row['WeakElements'] = mutate_bits(row['WeakElements'], rng) & vulnerable
    override = None
    if index != 74:  # RCC deliberately exempts Squire after equips/elements.
        mutate_statuses(index, row, rng)
        lucavi = index in LUCAVI_JOBS
        if lucavi:
            row['ImmuneStatus'] &= MASK40 ^ BENEFICIAL_STATUSES
            if rng.choice([True, False]):
                row['ImmuneStatus'] |= FAITH_STATUS
            if rng.choice([True, False]):
                row['ImmuneStatus'] |= INNOCENT_STATUS
            if rng.choice([True, False]):
                mutate_statuses(index, row, rng)
            if randint(rng, 1, 30) != 30:
                row['InnateStatus'] &= BENEFICIAL_STATUSES
                row['StartingStatus'] &= BENEFICIAL_STATUSES
        metadata = result['_AbilityMetadata']
        if not lucavi:
            _force_teleport_cost(result)
            candidates = [a for a in sorted(metadata) if not 357 <= a <= 366
                          and metadata[a]['AbilityType'] in (7, 8, 9)]
            # Enhanced's localized Nex data overrides the native JP field.
            # Use the active cost, with explicit phase changes taking priority.
            catalog = result.get('_AbilityCatalog', {})
            changed_costs = result.get('_RCCMetadataUpdates', {})
            candidates.sort(key=lambda a: changed_costs.get(a, {}).get('JPCost',
                            catalog.get(a, {}).get('jp_cost', metadata[a]['JPCost'])))
            monster = (index >= 94 and index != 151) if index < 160 else index in creature_jobs(result)
            innates = []
            for field in INNATE_FIELDS:
                value = row[field]
                chance = randint(rng, 1, 20)
                if chance == 20 or (monster and chance > 10):
                    position = None
                    if value:
                        if value not in candidates:
                            raise ValueError(f'Native innate {value} has no RCC passive type')
                        kind = metadata[value]['AbilityType']
                        typed = [a for a in candidates if metadata[a]['AbilityType'] == kind]
                        position = typed.index(value)
                    else:
                        typed = [a for a in candidates if metadata[a]['AbilityType'] == 8]
                    if not value and randint(rng, 1, 2) == 2:
                        typed = [a for a in candidates if metadata[a]['AbilityType'] == 8]
                        position = len(typed) // 2
                    if typed and position is not None:
                        position = mutate_normal(position, 0, len(typed)-1, rng,
                                                 random_degree=random_degree)
                        value = typed[position]
                innates.append(value)
            row.update(zip(INNATE_FIELDS, sorted(innates, reverse=True)))
        else:
            candidates = list(LUCAVI_INNATES) + [row[f] for f in INNATE_FIELDS if row[f] > 0]
            supports = [a for a in candidates if metadata[a]['AbilityType'] == 8 and a != 482]
            reactions = [a for a in candidates if metadata[a]['AbilityType'] == 7]
            movements = [a for a in candidates if metadata[a]['AbilityType'] == 9]
            nreaction = 1 + randint(rng, 0, 1) + randint(rng, 0, 1)
            nsupport = 6 - nreaction
            if len(set(supports)) < nsupport or len(set(reactions)) < nreaction:
                raise ValueError('Native Lucavi passive types differ from the verified RCC rules')
            while True:
                chosen_reactions = rng.sample(reactions, nreaction)
                if 445 not in chosen_reactions and set(chosen_reactions) & set(MP_RESTORE_INNATES):
                    continue
                if len(set(chosen_reactions)) == nreaction:
                    break
            while True:
                chosen_supports = rng.sample(supports, nsupport)
                if len(set(chosen_supports)) == nsupport:
                    break
            if 483 not in chosen_supports and 482 not in chosen_supports:
                chosen_supports[-1] = 482
            abilities = chosen_reactions + sorted(chosen_supports)
            if len(set(abilities)) != 6:
                raise ValueError('RCC Lucavi sampling did not produce six distinct passives')
            row.update(zip(INNATE_FIELDS, abilities))
            if index == 65:
                movement = 499
            else:
                if 445 not in chosen_reactions:
                    movements = [a for a in movements if a not in MP_RESTORE_INNATES]
                movement = rng.choice(movements)
            override = dict(job=index, ReactionAbilityId=abilities[4],
                            SupportAbilityId=abilities[5], MovementAbilityId=movement)
    for field in STATUS_FIELDS:
        row[field] = swap_mask(row[field])
    native.update({field: row[field] for field in required})
    # Keep trait consumers aligned with the now-mutated public job fields.
    if index in result.get('_JobTraits', {}):
        result['_JobTraits'][index].update(InnateStatus=native['InnateStatus'],
                                          StartStatus=native['StartingStatus'],
                                          StartingStatus=native['StartingStatus'])
    return override


def apply_innates(before, result, seed, flags, degree=1., random_degree=.25,
                  *, rngs=None, before_job=None):
    """Apply i/m innate rules and return scope, field and unit-override audit.

    ``before_job(flag, job, rng)`` permits the monster stat mutation to consume
    this same RNG immediately before each monster's innate rules, as in RCC.
    The returned RNGs can continue into MonsterSkillsObject's phase.
    """
    if not math.isfinite(degree) or not 0 <= degree <= 1:
        raise ValueError('Innate degree must be 0 to 1')
    if not math.isfinite(random_degree) or not 0 <= random_degree <= 1:
        raise ValueError('Normal mutation degree must be 0 to 1')
    scopes = innate_scopes(before)
    audit = dict(mode='RCC job innate rules', selected_jobs=[], changed_jobs=[],
                 unit_overrides=[], scopes=scopes, jp_cost_updates={})
    if not degree:
        return audit
    for flag in ('i', 'm'):
        if flag not in flags:
            continue
        rng = (rngs or {}).get(flag) or rng_for(seed, 'job-innates-'+flag)
        for index in scopes[flag]:
            if degree != 1 and rng.random() >= degree:
                continue
            old = dict(result['JobData'][index])
            if before_job:
                before_job(flag, index, rng)
            override = mutate_job_innate(result, index, rng, random_degree)
            audit['selected_jobs'].append(index)
            if old != result['JobData'][index]:
                audit['changed_jobs'].append(index)
            if override:
                audit['unit_overrides'].append(override)
        remember_rng(result,rng)
    audit['jp_cost_updates'] = {a: r['JPCost'] for a, r in result['_AbilityMetadata'].items()
                                if r['JPCost'] != before['_AbilityMetadata'][a]['JPCost']}
    return audit
