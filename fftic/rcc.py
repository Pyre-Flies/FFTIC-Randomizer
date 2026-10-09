"""RCC skillset phases adapted to FFTIC's verified native command tables.

The probabilities and list operations below come from the checked-out RCC
``randomizer.py`` and ``randomtools/tablereader.py``. The engine works on command
records, never encounter units: actors sharing a command keep the same skills.
Python 3's RNG and FFTIC's extra records mean this is a semantic port, not a
byte-for-byte reproduction of a PlayStation seed.
"""
import copy
import hashlib
import math
import random

from .game import ACTION_FIELDS, RSM_FIELDS
from .catalog import creature_commands, creature_jobs


def rng_for(seed, phase):
    digest = hashlib.sha256(f'fftic-rcc-v1\0{seed}\0{phase}'.encode()).digest()
    return random.Random(int.from_bytes(digest, 'big'))


def remember_rng(result, rng):
    """Preserve source continuation without storing identity-based RNG objects."""
    result['_RCCLastRNGState'] = rng.getstate()


def continuation_rng(result, seed):
    rng = rng_for(seed,'cleanup')
    if '_RCCLastRNGState' in result:
        rng.setstate(result['_RCCLastRNGState'])
    return rng


def randint(rng, a, b):
    """RCC randomizer.py:121-125, including its rounded numeric endpoints."""
    if not isinstance(a, int) or not isinstance(b, int):
        a, b = int(round(a)), int(round(b))
    return rng.randint(min(a, b), max(a, b))


def mutate_bits(value, rng, size=8, odds_multiplier=2.0):
    """RCC randomizer.py:108-118."""
    set_bits = value.bit_count()
    if set_bits > size or not 0 <= value < (1 << size):
        raise ValueError('Bit field exceeds its native size')
    low = max(min(set_bits, size - set_bits), 1)
    for bit in range(size):
        if rng.randint(1, int(round(size * odds_multiplier))) <= low:
            value ^= 1 << bit
    return value


def mutate_normal(base, minimum, maximum, rng, random_degree=.25,
                  return_float=False, wide=False):
    """RCC randomtools/tablereader.py:334-382; preserve rejection sampling."""
    if not minimum <= base <= maximum:
        raise ValueError('Normal mutation base is outside its bounds')
    if not 0 <= random_degree <= 1:
        raise ValueError('Normal mutation degree must be between zero and one')
    if minimum == maximum:
        return base
    while True:
        # Keep the source's literal addition: recent Python sum() uses
        # compensated floating summation and can change a boundary result.
        value_a = (rng.random() + rng.random() + rng.random()) / 3.0
        value_b = rng.random()
        if random_degree > .5:
            factor = 2 * random_degree - 1
            factor = value_a * (1 - factor) + value_b * factor
        else:
            factor = .5 * (1 - 2 * random_degree) + value_a * 2 * random_degree
        base_value, width = base - minimum, maximum - minimum
        max_width = max(base_value, width - base_value)
        min_width = min(base_value, width - base_value)
        if wide:
            sub_width = max_width
        else:
            width_factor = 1.0
            for _ in range(7):
                width_factor *= rng.uniform(random_degree, width_factor)
            sub_width = min_width * (1 - width_factor) + max_width * width_factor
        if factor > .5:
            subfactor = (factor - .5) * 2
            modifier = sub_width * subfactor
            value = base_value + modifier
        else:
            subfactor = 1 - factor * 2
            modifier = sub_width * subfactor
            value = base_value - modifier
        value += minimum
        if not return_float:
            value = int(round(value))
        if minimum <= value <= maximum:
            return value


def _chance(rng, denominator, degree):
    # Degree one retains RCC's exact source draw. Lower degrees add a gate;
    # they never turn RCC's 1/50 rare injections into full-table replacement.
    return rng.randint(1, denominator) == denominator and (degree == 1 or rng.random() < degree)


def _values(row, fields):
    return [row[f] for f in fields if row[f]]


def _set_values(row, fields, values):
    if len(values) > len(fields):
        raise ValueError('RCC skillset exceeded native capacity')
    for field, value in zip(fields, list(values) + [0] * len(fields)):
        row[field] = value


def _passive_bans(catalog):
    # RCC randomizer.py:194. Its exclusions are numeric; adding names here
    # inadvertently excluded three otherwise eligible FFTIC passives.
    return {0x1BB, 0x1D7, 0x1E1, 0x1E4, 0x1E5, 0x1F1}


def scopes(tables):
    """Return ordinary, unique humanoid and creature command ownership sets."""
    generic = {tables['JobData'][i]['JobCommandId'] for i in range(74, 94)}
    creatures = creature_commands(tables)
    # Boss secondary commands do not have a primary JobData owner. Their
    # native action provenance must still put them in the creature flag.
    for command, row in tables['JobCommandData'].items():
        ids = _values(row, ACTION_FIELDS)
        if ids and all(tables['_AbilityCatalog'][a].get('domain') == 'monster' for a in ids):
            creatures.add(command)
    available = {c for c, row in tables['JobCommandData'].items()
                 if c >= 5 and (any(row.values()) or c in generic)}
    return generic, available - generic - creatures, creatures & available


def _native_restricted(tables, command):
    menu = tables['CommandTypeData'][command]['Menu']
    actions = _values(tables['JobCommandData'][command], ACTION_FIELDS)
    catalog = tables['_AbilityCatalog']
    # RCC's exclusions (191-192) protect Items, Aim, Geomancy, Jump, Iaido,
    # Throw and Math. Also protect any extra FFTIC command of the same kind.
    return menu in (1, 2, 3, 4, 7, 9, 10) or (actions and
            all(catalog[a]['native_type'] in (2, 3, 4, 5, 6) for a in actions))


def _mimic_commands(tables):
    # The ordinary Mime owns a deliberately empty command; RCC bans all
    # mutations of that record (195/1721), including passive allocation.
    return {tables['JobData'][93]['JobCommandId']}


def _story_commands(tables):
    # RCC randomizer.py:211-212, verified against current JobData mappings.
    # WOTL recruitable classes add native Dark Knight/Balthier/Luso records.
    jobs = (13, 15, 22, 26, 30, 31, 41, 42, 50, 144, 145, 160, 162, 163)
    return list(dict.fromkeys(tables['JobData'][j]['JobCommandId'] for j in jobs
                              if tables['JobData'][j]['JobCommandId'] in tables['JobCommandData']))


def _human_plan(tables, rng, degree, audit):
    catalog = tables['_AbilityCatalog']
    commands = copy.deepcopy(tables['JobCommandData'])
    all_commands = [c for c in sorted(commands) if c >= 5]
    generic = set(tables['JobData'][j]['JobCommandId'] for j in range(74, 94))
    mimic = _mimic_commands(tables)
    restricted = {c for c in all_commands if _native_restricted(tables, c)}
    costs = {a: r['jp_cost'] for a, r in catalog.items()}
    # RCC get_abilities, randomizer.py:2952-2954, exposes Master Teleport as
    # a costly learnable movement before constructing its passive pool.
    if 499 in costs and catalog[499]['eligible']:
        costs[499] = 9999
    # RCC mutate_skillsets, randomizer.py:3599-3619.
    candidates = [c for c in all_commands if c not in restricted and c not in mimic
                  and any(catalog[a]['eligible'] and costs[a] > 0
                          for a in _values(commands[c], ACTION_FIELDS))]
    doing = [c for c in candidates if c in generic]
    doing += [c for c in _story_commands(tables) if c not in doing and c not in restricted and c not in mimic]
    seen = {a for c in doing for a in _values(commands[c], ACTION_FIELDS)
            if catalog[a]['eligible']}
    rng.shuffle(candidates)
    for c in candidates:
        actions = {a for a in _values(commands[c], ACTION_FIELDS) if catalog[a]['eligible']}
        if c not in doing and actions - seen:
            doing.append(c)
            seen |= actions
    rng.shuffle(doing)
    considered, pulled = set(), {}
    for c in doing:
        # FFTIC retains unimplemented WOTL IDs in latent command records.
        # Keep those original entries on their owner, but do not exchange
        # them into active jobs. RCC's PS1 source bans 0x165-0x16E and asserts
        # that they never occur in mutated skillsets (190 / 1766-1767).
        actions = [a for a in _values(commands[c], ACTION_FIELDS)
                   if catalog[a]['eligible'] and a not in considered]
        if len(actions) <= 1 and c not in generic:
            continue
        half = len(actions) // 2
        count = rng.randint(0, half) + rng.randint(0, half)
        if count > half:
            count = len(actions) - count
        if degree != 1:
            count = int(round(count * degree))
        chosen = rng.sample(actions, count)
        retained = _values(commands[c], ACTION_FIELDS)
        for a in list(chosen):
            if costs[a] > 0:
                retained.remove(a)
            else:
                chosen.remove(a)  # Free/native story actions remain on their owner.
        _set_values(commands[c], ACTION_FIELDS, retained)
        for a in actions:
            if a not in considered:
                if rng.choice((True, False)) or (a in chosen and rng.choice((True, False))):
                    considered.add(a)
        if chosen or c in generic or rng.randint(1, 4) == 4:
            pulled[c] = chosen
    exchanges = [c for c in doing if c in pulled]
    donors = list(exchanges)
    rng.shuffle(donors)
    for recipient, donor in zip(exchanges, donors):
        retained = _values(commands[recipient], ACTION_FIELDS)
        combined = retained + pulled[donor]
        if len(combined) > 16:
            combined = rng.sample(combined, 16)
        old_part = sorted({a for a in combined if a in retained})
        new_part = sorted({a for a in combined if a in pulled[donor] and a not in old_part})
        combined = old_part + new_part if rng.choice((True, False)) else new_part + old_part
        _set_values(commands[recipient], ACTION_FIELDS, combined)
    audit['exchanged_command_count'] = len(exchanges)

    # RCC randomizer.py:3664-3711: unique passives use reusable candidates;
    # generic passives use a consumed done list and reserve Poach for Thief.
    bans = _passive_bans(catalog)
    passives = [a for a, r in sorted(catalog.items()) if r['eligible'] and costs[a] > 0
                and 7 <= r['native_type'] <= 9 and a not in bans]
    order = list(all_commands)
    rng.shuffle(order)
    for c in order:
        original = _values(commands[c], RSM_FIELDS)
        if c in generic or c in mimic or not original:
            continue
        if degree != 1 and rng.random() >= degree:
            continue
        count = min(2 + rng.randint(0, 3) + rng.randint(0, 3), 6)
        chosen = rng.sample(passives, min(6, len(passives))) + original
        rng.shuffle(chosen)
        _set_values(commands[c], RSM_FIELDS, sorted(set(chosen[:count])))
    poach = next((a for a, r in catalog.items() if r['name'].casefold() == 'poach'), 0x1D7)
    done = {poach}
    thief = tables['JobData'][83]['JobCommandId']
    for c in order:
        if c not in generic or c in mimic:
            continue
        if degree != 1 and rng.random() >= degree:
            done.update(_values(commands[c], RSM_FIELDS))
            continue
        candidates = [a for a in passives if a not in done]
        if c == thief and len(candidates) < 4:
            candidates = list(passives)
        chosen = rng.sample(candidates, min(len(candidates), 6))
        chosen += [a for a in _values(commands[c], RSM_FIELDS) if a not in done]
        candidates = sorted(set(chosen))
        count = rng.randint(0, 3) + rng.randint(0, 3)
        if count <= 4 and rng.choice((True, False)):
            count += 1
        count = min(count, len(candidates), 6)
        if c == thief:
            count = min(len(candidates), max(count, 4))
            chosen = rng.sample(candidates, count)
            if len(chosen) >= 4:
                chosen[3] = poach
            elif poach not in chosen:
                chosen.append(poach)
        else:
            chosen = sorted(rng.sample(candidates, count))
        _set_values(commands[c], RSM_FIELDS, chosen)
        done.update(chosen)

    # RCC SkillsetObject.mutate_abilities, randomizer.py:1720-1776.
    # RCC's BANNED_SKILLS are ten undefined PS1 slots (0x165-0x16E).
    # FFTIC has additional native definitions at some of these IDs, so use
    # the complete inventory's undefined-entry exclusion instead of blindly
    # forbidding a now-defined War of the Lions action by its old address.
    direct = [a for a, r in sorted(catalog.items()) if r['eligible'] and r['native_type'] == 1]
    all_passives = [a for a, r in sorted(catalog.items()) if r['eligible'] and 7 <= r['native_type'] <= 9]
    attributes = tables.get('_AbilityAttributes', {})
    boss = _boss_commands(tables)
    for c in all_commands:
        if c in mimic:
            continue
        if c in boss:
            _boss_actions(c, boss[c], commands, catalog, attributes, rng, degree, audit)
            continue
        actions = _values(commands[c], ACTION_FIELDS)
        if c not in restricted:
            for i, a in enumerate(actions):
                if catalog[a]['native_type'] == 1 and _chance(rng, 50, degree):
                    chosen = rng.choice(direct)
                    _give_jp(chosen, costs, rng)
                    actions[i] = chosen
            _set_values(commands[c], ACTION_FIELDS, actions)
        rsms = _values(commands[c], RSM_FIELDS)
        for i in range(len(rsms)):
            if _chance(rng, 50, degree):
                chosen = rng.choice(all_passives)
                _give_jp(chosen, costs, rng)
                rsms[i] = chosen
        _set_values(commands[c], RSM_FIELDS, rsms)
    # RCC randomizer.py:3716-3722 removes individual native special-menu
    # parameters at 1/8 odds; it does not turn those menus into normal magic.
    for c in sorted(restricted & generic):
        actions = [a for a in _values(commands[c], ACTION_FIELDS) if not _chance(rng, 8, degree)]
        _set_values(commands[c], ACTION_FIELDS, actions)
    return commands, {a: cost for a, cost in costs.items() if cost != catalog[a]['jp_cost']}


def _give_jp(aid, costs, rng):
    if costs[aid] == 0:
        # RCC randomizer.py:1762-1764 / 1773-1775.
        value = 100 + rng.randint(0, 700) + rng.randint(0, 700)
        costs[aid] = int(round(value * 2, -2) / 2)


def _boss_commands(tables):
    # Verified native Enhanced primary/secondary Ultima action records keep
    # the PS1 0x7B-0x7E identities, even though no localized menu names exist.
    expected = {123: [229], 124: [350], 125: [230, 350], 126: [231, 232, 233]}
    return {c: role for role, (c, actions) in enumerate(expected.items())
            if c in tables['JobCommandData'] and _values(tables['JobCommandData'][c], ACTION_FIELDS) == actions}


def _boss_actions(c, role, commands, catalog, attributes, rng, degree, audit):
    if degree != 1 and rng.random() >= degree:
        return
    if not attributes:
        audit['limitations'].append('Ultima complete-magic phases retained: missing native random-hit metadata')
        return
    # RCC randomizer.py:1724-1754. Unlike ordinary exchange, its final boss
    # fills secondary records to 16 with AI-usable non-random-hit attacks.
    candidates = [a for a, r in sorted(catalog.items()) if a > 0 and r['eligible']
                  and r['native_type'] == 1 and not attributes.get(a, {}).get('random_hits', True)
                  and r['ai_flags'] & (1 << 31)]
    candidates += [a for a in list(range(0x170, 0x17E)) + list(range(0x196, 0x19E))
                   if a in catalog and catalog[a]['eligible']]
    candidates = sorted(set(candidates))
    if not candidates:
        audit['limitations'].append('Ultima complete-magic phases retained: no verified AI candidates')
        return
    base = ([229, 350], [], [230, 350, 231, 232, 233], [])[role]
    if role == 1:
        bans = _passive_bans(catalog)
        passives = [a for a, r in catalog.items() if r['eligible'] and 7 <= r['native_type'] <= 9 and a not in bans]
        _set_values(commands[c], RSM_FIELDS, sorted(rng.sample(passives, min(6, len(passives)))))
    if role in (1, 2, 3):
        while len(base) < 16 and len(set(candidates) - set(base)):
            chosen = rng.choice(candidates)
            if chosen not in base:
                base.append(chosen)
    _set_values(commands[c], ACTION_FIELDS, base)


def _ranked_skills(tables, commands, kind, audit, costs=None):
    """RCC get_ranked_skills, randomizer.py:3255-3323."""
    catalog = tables['_AbilityCatalog']
    costs = costs or {}
    rank = tables.get('_RCCRankedJobs')
    if rank is None:
        rank = sorted(tables['JobData'])
        audit['limitations'].append('Monster proximity ranks use native job order: encounter-derived ranks unavailable')
    else:
        rank = list(rank) + [j for j in sorted(tables['JobData']) if j not in rank]
    monsters = creature_jobs(tables)
    jobs = [j for j in rank if kind is None or j in monsters]
    human, monster = [], []
    for j in jobs:
        command = tables['JobData'][j]['JobCommandId']
        if command in commands:
            for a in _values(commands[command], ACTION_FIELDS):
                if a not in human:
                    human.append(a)
        elif command in tables['MonsterJobCommandData']:
            for a in _values(tables['MonsterJobCommandData'][command], ACTION_FIELDS[:3]):
                if a not in monster:
                    monster.append(a)
    for j in jobs:
        command = tables['JobData'][j]['JobCommandId']
        if command in tables['MonsterJobCommandData']:
            a = tables['MonsterJobCommandData'][command]['AbilityId4']
            if a and a not in monster:
                monster.append(a)
    if not human:
        ranked = monster
    else:
        human = sorted([a for a in human if catalog[a]['native_type'] == 1
                        and costs.get(a, catalog[a]['jp_cost']) > 0],
                       key=lambda a: costs.get(a, catalog[a]['jp_cost']))
        if len(human) < len(monster) / 4:
            ranked = monster
        elif len(monster) < len(human) / 4:
            ranked = human
        elif monster:
            ranked = list(human)
            factor = float(len(human)) / len(monster)
            for i, a in reversed(list(enumerate(monster))):
                index = max(0, min(int(round(factor * i)), len(human) - 1))
                ranked.insert(index, a)
        else:
            ranked = human
    return list(dict.fromkeys(a for a in ranked if catalog[a]['eligible']))


def _monster_plan(tables, commands, rng, degree, audit, costs=None):
    # RCC MonsterSkillsObject.mutate, randomizer.py:1134-1166. The fourth
    # action retains the special Monster Skill role instead of being shuffled
    # into the first three ordinary action slots.
    monster = _ranked_skills(tables, commands, 'monster', audit, costs)
    mixed = _ranked_skills(tables, commands, None, audit, costs)
    plan = copy.deepcopy(tables['MonsterJobCommandData'])
    for c, row in sorted(plan.items()):
        if degree != 1 and rng.random() >= degree:
            continue
        pool = mixed if rng.randint(1, 12) == 12 else monster
        if not pool:
            continue
        original = [row[f] for f in ACTION_FIELDS[:4]]
        changed = []
        for a in original:
            if a == 0:
                if rng.choice((True, False)):
                    continue
                a = rng.choice(original)
                if a == 0:
                    continue
            elif rng.choice((True, False)):
                changed.append(a)
                continue
            if a not in pool:
                # RCC's ranked source pool includes every native original.
                # A remade mixed human table can remove a referenced boss ID;
                # retain its action rather than invent a nearest rank.
                changed.append(a)
                continue
            index = mutate_normal(pool.index(a), 0, len(pool) - 1, rng)
            changed.append(pool[index])
        if not changed:
            changed = [next(a for a in original if a)]
        ordinary, special = changed[:-1], changed[-1]
        ordinary = [a for a in ordinary if a != special]
        if not ordinary:
            ordinary = [special]
            special = rng.choice(pool)
        ordinary = sorted(set(ordinary))
        ordinary = ordinary[:3] + [0] * (3 - len(ordinary))
        _set_values(row, ACTION_FIELDS[:4], ordinary + [special])
    return plan


def apply_abilities(before, result, seed, flags, degree=1.0, *, include_monsters=True):
    """Apply scoped RCC ability phases to an already deep-copied result.

    ``s`` selects ordinary and unique humanoid commands, ``m`` creature
    commands in either native table. ``degree=1`` uses RCC's original pull and
    injection odds. Degree zero is a no-op. Returned JP updates must be applied
    to localized ability NXD tables by the package writer; changing private
    metadata would not change the live game.
    """
    if not math.isfinite(degree) or not 0 <= degree <= 1:
        raise ValueError('RCC ability degree must be between zero and one')
    audit = dict(engine='RCC skillset exchange', exchanged_command_count=0,
                 jp_cost_updates={}, limitations=[])
    if degree == 0 or not set(flags) & set('sm'):
        return audit
    generic, unique, creatures = scopes(before)
    selected = (((generic | unique) if 's' in flags else set()) |
                (creatures if 'm' in flags else set()))
    rng = rng_for(seed, 'skillsets')
    plan, costs = _human_plan(before, rng, degree, audit)
    for c in selected:
        result['JobCommandData'][c] = plan[c]
    if 'm' in flags and include_monsters:
        # RCC runs monster mutation after the selected skillset phase
        # (randomizer.py:5112-5138). Rank the commands actually installed,
        # including unchanged humanoid records when that scope is disabled.
        rng = rng_for(seed, 'monsters')
        result['MonsterJobCommandData'] = _monster_plan(before,result['JobCommandData'],rng,degree,audit,costs)
    assigned = {a for c in selected for a in plan[c].values() if a}
    if 'm' in flags:
        assigned |= {a for row in result['MonsterJobCommandData'].values() for a in row.values() if a}
    audit['jp_cost_updates'] = {a: cost for a, cost in costs.items() if a in assigned or a == 499}
    audit['changed_human_commands'] = sorted(c for c in selected if before['JobCommandData'][c] != plan[c])
    audit['changed_monster_commands'] = sorted(c for c, row in result['MonsterJobCommandData'].items()
                                               if before['MonsterJobCommandData'][c] != row)
    audit['limitations'] = list(dict.fromkeys(audit['limitations']))
    audit['rcc_reuse_policy'] = 'Exchanged actions; unique passives and rare injections reusable; ordinary passives depleted'
    remember_rng(result,rng)
    return audit


def apply_monsters(before, result, seed, degree=1.0, costs=None, *, rng=None):
    """Separate final phase for RCC's skillsets -> JP/job stats -> monsters order.

    Call ``apply_abilities(..., include_monsters=False)`` first, apply the job
    and JP mutations, and pass their combined JP costs here. Encounter data
    and command menus remain untouched.
    """
    if not math.isfinite(degree) or not 0 <= degree <= 1:
        raise ValueError('RCC ability degree must be between zero and one')
    audit = dict(engine='RCC monster proximity mutation', limitations=[], changed_monster_commands=[])
    if degree == 0:
        return audit
    rng = rng or rng_for(seed, 'monsters')
    result['MonsterJobCommandData'] = _monster_plan(before, result['JobCommandData'],rng,degree,audit,costs)
    audit['changed_monster_commands'] = sorted(c for c, row in result['MonsterJobCommandData'].items()
                                               if before['MonsterJobCommandData'][c] != row)
    audit['limitations'] = list(dict.fromkeys(audit['limitations']))
    remember_rng(result,rng)
    return audit
