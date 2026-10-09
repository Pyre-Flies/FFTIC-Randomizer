"""Complete job replacements, with typed menus and actor-specific ability pools.

This mode deliberately rebuilds skillsets instead of retaining RCC's native
special-command exceptions. Equipment/stat rules remain in their own modules.
Each pool is shuffled, consumed without replacement, and refilled only after
exhaustion. Native command records remain the unit of ownership.
"""
from collections import Counter
import math

from .game import ACTION_FIELDS, RSM_FIELDS
from .catalog import pools
from .rcc import rng_for, scopes


PROFILE_TYPES = {0:1, 1:2, 2:3, 3:6, 4:1, 7:1, 9:4, 10:5}
PROFILE_NAMES = {0:'direct', 1:'items', 2:'throw', 3:'math', 4:'geomancy',
                 7:'iaido', 9:'jump', 10:'aim'}
PASSIVE_NAMES = {7:'reaction', 8:'support', 9:'movement'}


class CycleDeck:
    """A complete shuffled cycle with no duplicate ability inside an owner row."""
    def __init__(self, ids, rng):
        self.ids = tuple(sorted(set(ids)))
        self.rng = rng
        self.remaining = []
        self.cycles = 0
        self.draws = 0
        self.used = Counter()

    def draw(self, excluded=(), prefer_not=()):
        excluded, prefer_not = set(excluded), set(prefer_not)
        if not self.ids or set(self.ids) <= excluded:
            raise ValueError('Full mode has no distinct compatible ability for this row')
        if not self.remaining:
            self.remaining = list(self.ids)
            self.rng.shuffle(self.remaining)
            self.cycles += 1
        available = [i for i, aid in enumerate(self.remaining) if aid not in excluded]
        if not available:
            # With a row target no greater than this pool's size this cannot
            # occur. Do not secretly discard remaining cards or refill early.
            raise ValueError('Full mode row exhausted its distinct cycle candidates')
        preferred = [i for i in available if self.remaining[i] not in prefer_not]
        index = (preferred or available)[0]
        aid = self.remaining.pop(index)
        self.draws += 1
        self.used[aid] += 1
        return aid

    def audit(self):
        return dict(pool_size=len(self.ids), draws=self.draws, cycles=self.cycles,
                    refills=max(0, self.cycles-1), unique_used=len(self.used),
                    remaining=len(self.remaining), usage=dict(sorted(self.used.items())))


def owner_scopes(tables):
    """Full and RCC share flags, including creature secondary command owners."""
    ordinary, unique, creatures = scopes(tables)
    return dict(s=[('JobCommandData', c) for c in sorted(ordinary | unique)],
                m=sorted([('JobCommandData', c) for c in creatures] +
                         [('MonsterJobCommandData', c) for c in tables['MonsterJobCommandData']],
                         key=lambda item:(item[1], item[0])))


def profile_pools(tables):
    """Keep item/parameter/terrain/katana mechanics in their native menu."""
    catalog = tables['_AbilityCatalog']
    player = pools(tables, 'player')
    special = {}
    for menu in (4, 7):
        special[menu] = sorted({row[f] for c, row in tables['JobCommandData'].items()
                                if tables['CommandTypeData'][c]['Menu'] == menu
                                for f in ACTION_FIELDS if row[f] and catalog[row[f]]['eligible']
                                and catalog[row[f]]['domain'] in ('player', 'both')
                                and catalog[row[f]]['native_type'] == 1})
    reserved = set(special[4]) | set(special[7])
    result = {menu:(special[menu] if menu in special else
                    [a for a in player[kind] if menu != 0 or a not in reserved])
              for menu, kind in PROFILE_TYPES.items()}
    return result


def _profile_plan(tables, commands, available, rng):
    """Spread complete native profiles and move every original special menu."""
    menus = sorted(menu for menu, ids in available.items() if ids)
    if not menus:
        raise ValueError('Full mode has no eligible player action profile')
    specials = [menu for menu in menus if menu]
    quota = max(1, len(commands)//12) if specials else 0
    quota = min(quota, len(commands)//len(specials)) if specials else 0
    planned = [menu for menu in specials for _ in range(quota)]
    planned += [0 if 0 in menus else menus[0]] * (len(commands)-len(planned))
    rng.shuffle(planned)
    for index, command in enumerate(commands):
        original = tables['CommandTypeData'][command]['Menu']
        if not original or planned[index] != original:
            continue
        # Moving an old Aim/Jump/etc. profile is part of Total mode's promise.
        # Prefer a swap that does not give another special owner its old menu.
        candidates = [j for j, menu in enumerate(planned) if j != index and menu != original
                      and (not tables['CommandTypeData'][commands[j]]['Menu'] or
                           planned[index] != tables['CommandTypeData'][commands[j]]['Menu'])]
        if candidates:
            other = rng.choice(candidates)
            planned[index], planned[other] = planned[other], planned[index]
        elif len(menus) > 1:
            # Tiny synthetic inputs may not permit a quota-preserving swap.
            # Compatibility and a changed identity take precedence there.
            planned[index] = rng.choice([menu for menu in menus if menu != original])
    return dict(zip(commands, planned))


def _draw_row(before, fields, target, deck):
    values, used = [], set()
    target = min(target, len(deck.ids), len(fields))
    originals = set(before.values()) - {0}
    for index in range(target):
        # This preference does not discard unused cycle entries. It helps the
        # first action establish a visibly different identity when possible.
        aid = deck.draw(used, originals if index == 0 else (before[fields[index]],))
        values.append(aid)
        used.add(aid)
    return dict(zip(fields, values + [0] * (len(fields)-len(values))))


def _player_plan(tables, commands, seed, min_actions, max_actions, passives_per_type):
    rng = rng_for(seed, 'full-player-plan')
    profiles = profile_pools(tables)
    eligible = pools(tables, 'player')
    decks = {PROFILE_NAMES[menu]:CycleDeck(ids, rng) for menu, ids in profiles.items()}
    decks.update({PASSIVE_NAMES[kind]:CycleDeck(eligible[kind], rng) for kind in (7,8,9)})
    for kind in (7,8,9):
        if not eligible[kind]:
            raise ValueError(f'Full mode requires an eligible player {PASSIVE_NAMES[kind]} pool')
    menu_plan = _profile_plan(tables, commands, profiles, rng)
    plan = {}
    for command in commands:
        old = tables['JobCommandData'][command]
        menu = menu_plan[command]
        row = _draw_row(old, ACTION_FIELDS, rng.randint(min_actions, max_actions),
                        decks[PROFILE_NAMES[menu]])
        row.update(dict.fromkeys(RSM_FIELDS, 0))
        slot = 0
        for kind in (7,8,9):
            deck = decks[PASSIVE_NAMES[kind]]
            for _ in range(min(passives_per_type, len(deck.ids))):
                field = RSM_FIELDS[slot]
                row[field] = deck.draw(set(row.values()), (old[field],))
                slot += 1
        plan[('JobCommandData', command)] = row, menu, 'player'
    return plan, {name:deck.audit() for name,deck in decks.items()}


def _creature_plan(tables, owners, seed, min_actions, max_actions, passives_per_type):
    rng = rng_for(seed, 'full-creature-plan')
    eligible = pools(tables, 'monster')
    direct = CycleDeck(eligible[1], rng)
    passives = {kind:CycleDeck(eligible[kind], rng) for kind in (7,8,9)}
    if not direct.ids:
        raise ValueError('Full mode requires an eligible monster action pool')
    plan = {}
    for table, command in owners:
        old = tables[table][command]
        four_slot = table == 'MonsterJobCommandData'
        if four_slot and len(direct.ids) < 2:
            raise ValueError('Full mode requires two distinct monster actions for ordinary and hidden skills')
        fields = ACTION_FIELDS[:4] if four_slot else ACTION_FIELDS
        target = min(4, len(direct.ids)) if four_slot else rng.randint(min_actions, max_actions)
        row = _draw_row(old, fields, target, direct)
        # A four-slot record's fourth field keeps the native Monster Skill
        # role. All four receive fresh distinct monster actions; never rotate
        # the original hidden action into an ordinary role as an exception.
        if four_slot and not row[fields[-1]] and target:
            # Extremely small custom fixtures still need a hidden skill; keep
            # a filled fourth slot without duplicating its normal action.
            row[fields[-1]] = row[fields[target-1]]
            row[fields[target-1]] = 0
        if not four_slot:
            row.update(dict.fromkeys(RSM_FIELDS, 0))
            slot = 0
            for kind in (7,8,9):
                deck = passives[kind]
                for _ in range(min(passives_per_type, len(deck.ids))):
                    field = RSM_FIELDS[slot]
                    row[field] = deck.draw(set(row.values()), (old[field],))
                    slot += 1
        plan[(table,command)] = row, None if four_slot else 0, 'monster'
    audit = {'direct':direct.audit()}
    audit.update({PASSIVE_NAMES[kind]:deck.audit() for kind,deck in passives.items()})
    return plan, audit


def apply_full(before, result, seed, flags, degree=1.0, pool_policy='cycle',
               min_actions=6, max_actions=12, passives_per_type=1):
    """Rebuild selected complete command owners from compatible shuffled pools.

    At 100% every selected humanoid gets a fresh profile and one of each
    passive type (or two if requested). Lower degrees replace a seeded
    percentage of complete owners, avoiding incompatible mixed-type menus.
    Creature actors use their own pools even when stored in human-format
    command records; no player passive categories are invented for them.
    """
    if not math.isfinite(degree) or not 0 <= degree <= 1:
        raise ValueError('Full replacement degree must be between zero and one')
    if pool_policy != 'cycle':
        raise ValueError('Full mode uses shuffled pools refilled after exhaustion')
    if not isinstance(min_actions, int) or not isinstance(max_actions, int) or not 1 <= min_actions <= max_actions <= 16:
        raise ValueError('Full action count must be an integer range within 1 to 16')
    if passives_per_type not in (1,2):
        raise ValueError('Full passives per type must be one or two')
    owned = owner_scopes(before)
    audit = dict(engine='Full complete job replacement', pool_policy=pool_policy,
                 degree=degree, degree_interpretation='Percentage of complete command owners replaced',
                 min_actions=min_actions, max_actions=max_actions,
                 passives_per_type=passives_per_type, jp_cost_updates={},
                 selected_owners=[], changed_human_commands=[], changed_monster_commands=[],
                 decks={}, limitations=[])
    if degree == 0 or not set(flags)&set('sm'):
        return audit
    ordinary, unique, _ = scopes(before)
    player_commands = sorted(ordinary | unique)
    player_plan, player_decks = _player_plan(before, player_commands, seed,
                                            min_actions, max_actions, passives_per_type)
    creature_plan, creature_decks = _creature_plan(before, owned['m'], seed,
                                                 min_actions, max_actions, passives_per_type)
    plan = player_plan | creature_plan
    selected = set()
    for flag in 'sm':
        if flag in flags:
            owners = owned[flag]
            count = min(len(owners), math.ceil(len(owners)*degree))
            selection_rng = rng_for(seed, 'full-selected-'+flag)
            selected.update(selection_rng.sample(owners,count))
            from .rcc import remember_rng
            remember_rng(result,selection_rng)
    for table, command in sorted(selected, key=lambda owner:(owner[1],owner[0])):
        row, menu, actor = plan[(table,command)]
        result[table][command] = row.copy()
        if menu is not None:
            result['CommandTypeData'][command]['Menu'] = menu
        audit['selected_owners'].append(dict(table=table,id=command,actor=actor,menu=menu))
        if before[table][command] != row or (menu is not None and before['CommandTypeData'][command]['Menu'] != menu):
            target = 'changed_monster_commands' if table=='MonsterJobCommandData' else 'changed_human_commands'
            audit[target].append(command)
    audit['decks'] = dict(player=player_decks, monster=creature_decks)
    audit['deck_scope'] = 'Complete allocation plan across all scopes; selected owners determine installed coverage'
    audit['coverage'] = {}
    for actor, decks in audit['decks'].items():
        assigned = {a for owner in audit['selected_owners'] if owner['actor']==actor
                    for a in result[owner['table']][owner['id']].values() if a}
        configured = {a for name in decks for a in plan_deck_ids(before, actor, name)}
        planned = {a for deck in decks.values() for a in deck['usage']}
        audit['coverage'][actor] = dict(unique_used=len(assigned), configured_pool_size=len(configured),
                                       assigned_ids=sorted(assigned), unassigned_ids=sorted(configured-assigned),
                                       plan_unique_used=len(planned))
    audit['scope_sizes'] = {flag:len(owners) for flag,owners in owned.items()}
    audit['native_limits'] = dict(actions=16,passives=6,monster_actions=4)
    audit['shared_native_ids'] = sorted(a for a,r in before['_AbilityCatalog'].items()
                                       if r['eligible'] and r['domain']=='both')
    audit['creature_passive_categories'] = {kind:len(pools(before,'monster')[kind]) for kind in (7,8,9)}
    return audit


def plan_deck_ids(tables, actor, name):
    """Expose audited pool membership without private mutable deck state."""
    eligible = pools(tables, actor)
    if name in PASSIVE_NAMES.values():
        return eligible[next(kind for kind,label in PASSIVE_NAMES.items() if label==name)]
    if actor=='monster':
        return eligible[1]
    profiles = profile_pools(tables)
    return profiles[next(menu for menu,label in PROFILE_NAMES.items() if label==name)]
