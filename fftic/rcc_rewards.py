"""RCC t phase: unit gil/trophies, carcass exchanges and buried rewards."""
import math
from bisect import bisect_left

from .rcc import mutate_normal, randint, rng_for,remember_rng
from .rcc_world_data import world_nex_update


def item_rank(index, items):
    if index == 0:
        return -1
    row = items[index]
    rank = row['Price']
    if rank <= 10 or index in (0x6A, 0x8F):
        rank += 65000 + row['RequiredLevel']*100
    return rank


def ranked_items(items):
    # RCC ItemObject.every has IDs0..253; native254/255 are sentinels.
    return sorted((index for index in items if 0 < index < 254), key=lambda index: (item_rank(index, items), index))


def get_similar_item(base, items, rng, boost_factor=1.0, random_degree=.25, *, extended_items=None):
    """Exact source reverse-rank boost and normal replacement selection."""
    ranked = ranked_items(items)
    if base in ranked:
        index = ranked.index(base)
    elif extended_items and base in extended_items and ranked:
        # A ushort buried reward can start with Enhanced's Materia Blade+256.
        # Place its verified metadata among RCC's eligible ranks as a guide;
        # replacements remain in the original, byte-safe item pool. Private
        # extended metadata never enters unit equipment or trophy candidates.
        index = min(bisect_left([(item_rank(item, items), item) for item in ranked],
                                (item_rank(base, extended_items), base)), len(ranked)-1)
    else:
        raise ValueError(f'Reward item {base} has no supported item metadata')
    reverse = len(ranked)-index-1
    boosted = max(0, min(int(round(reverse/boost_factor)), len(ranked)-1))
    reverse = randint(rng, min(boosted, reverse), max(boosted, reverse))
    index = mutate_normal(len(ranked)-reverse-1, 0, len(ranked)-1, rng, random_degree=random_degree)
    return ranked[index]


def _enabled(rng, degree):
    return degree == 1 or rng.random() < degree


def mutate_poaches(poaches, items, rng, chaos=1.0, random_degree=.25, degree=1.0):
    done_rare = set()
    boost = max(2.0-.5*chaos, .5)
    all_items = sorted(index for index in items if index < 254)
    for monster, row in sorted(poaches.items()):
        if not _enabled(rng, degree):
            continue
        row['common'] = get_similar_item(row['common'], items, rng, boost, random_degree)
        candidates = [index for index in all_items if item_rank(index, items) > item_rank(row['common'], items)]
        remaining = [index for index in candidates if index not in done_rare]
        if remaining:
            candidates = remaining
        if not candidates:
            # Source random.choice([]) also fails. Do not invent a lower-ranked
            # rare reward and silently violate the requested source behavior.
            raise ValueError(f'RCC poach {monster} has no item ranked above its randomized common reward')
        row['rare'] = rng.choice(candidates)
        done_rare.add(row['rare'])


def mutate_move_find(row, slot, map_id, maps, items, rng, chaos=1.0, random_degree=.25, *, extended_items=None):
    """Source half-time relocation, rewards and trap-bit order."""
    from .rcc_maps import certain_values
    special = rng.choice((True, False))
    if special:
        variants = maps.get(map_id)
        if not variants:
            return False
        width, length = variants[0]['width'], variants[0]['length']
        if width < 1 or length < 1:
            return False
        bad = certain_values(variants, 'bad')
        # RCC treats cross-variant disagreement(None) as usable. Respect that
        # predicate but bound the impossible all-blocked-map case.
        if not any(not bad[y][x] for y in range(min(16, len(bad))) for x in range(min(16, len(bad[y])))):
            return False
        while True:
            x, y = rng.randint(0, width-1), rng.randint(0, length-1)
            # Some TIC terrain variants have a dimension17/18. Those tiles
            # cannot fit the native XY byte; drawing over the original map
            # dimensions and rejecting them prevents nibble spill/corruption.
            if x >= 16 or y >= 16 or y >= len(bad) or x >= len(bad[y]) or bad[y][x]:
                continue
            break
        row[f'X{slot}'], row[f'Y{slot}'] = x, y
    common_field, rare_field, flags_field = f'CommonItemId{slot}', f'RareItemId{slot}', f'TrapFlags{slot}'
    all_items = sorted(index for index in items if index < 254)
    if row[common_field] != 0:
        row[common_field] = (rng.choice(all_items) if special else
                             get_similar_item(row[common_field], items, rng, max(2.0-.5*chaos, .5), random_degree,
                                              extended_items=extended_items))
    if row[rare_field] != 0:
        if special and rng.choice((True, False)):
            row[rare_field] = row[common_field]
        else:
            candidates = [index for index in all_items if item_rank(index, items) >= item_rank(row[common_field], items)]
            row[rare_field] = rng.choice(candidates)
    if row[common_field] or row[rare_field]:
        trap = rng.choice((True, False, False))
        if trap:
            row[flags_field] &= ~(1 << 4)
            if rng.randint(1, 5) == 5:
                row[flags_field] |= 1 << 5
            else:
                row[flags_field] &= ~(1 << 5)
            row[flags_field] &= ~15
            # Source order: sleeping_gas, steel_needle, deathtrap, degenerator.
            row[flags_field] |= rng.choice((4, 8, 2, 1))
        else:
            row[flags_field] |= 1 << 4
        if rng.randint(1, 10) == 10:
            row[common_field], row[rare_field] = row[rare_field], row[common_field]
    return True


def apply_rewards(before, result, seed, flags, degree=1.0, chaos=1.0, random_degree=.25):
    if not all(math.isfinite(value) for value in (degree, chaos, random_degree)) or not 0 <= degree <= 1 or chaos < 0 or not 0 <= random_degree <= 1:
        raise ValueError('Invalid RCC reward settings')
    audit = dict(mode='RCC treasure', enabled='t' in flags and degree > 0,
                 source='randomizer.py:1169-1258,2217-2223,4606-4618',
                 unit_rewards=0, poach_rows=0, move_find_slots=0, gil_native_clamps=0,
                 adaptations=['Enhanced poach carcass exchange target is PoachItem.Unknown2C in all seven locales',
                              'Item IDs254/255 are native sentinels and never rewards',
                              'Enhanced buried rewards use private extended-item ranks as guides; replacements stay in the byte-safe RCC pool',
                              'Gil is a native byte; rounded source values above255 are clamped to255',
                              'Move-find rejects terrain coordinates above15 rather than spilling their packed nibbles',
                              'Missing or fully blocked terrain returns without relocating that slot'])
    if not audit['enabled']:
        result['_RCCRewardAudit'] = audit
        return audit
    units, maps = result['_RCCUnitContext'], result['_RCCMaps']
    items, rng = result['ItemData'], rng_for(seed, 'treasure-t')
    for key, row in sorted(units.items()):
        if not _enabled(rng, degree):
            continue
        old = (row['Gil'], row['TrophyItemId'])
        if row['Gil'] > 0:
            value = mutate_normal(row['Gil'], 1, 65000, rng, random_degree=random_degree)
            value = int(round(value, -2))
            audit['gil_native_clamps'] += int(value > 255)
            row['Gil'] = min(255, value)
        if row['TrophyItemId']:
            row['TrophyItemId'] = get_similar_item(row['TrophyItemId'], items, rng, max(1.5-.5*chaos, .25), random_degree)
        audit['unit_rewards'] += int(old != (row['Gil'], row['TrophyItemId']))
    poaches = result['_RCCPoaches']
    mutate_poaches(poaches, items, rng, chaos, random_degree, degree)
    for monster, row in sorted(poaches.items()):
        if row != before['_RCCPoaches'][monster]:
            audit['poach_rows'] += 1
        for kind in ('common', 'rare'):
            if row[kind] == before['_RCCPoaches'][monster][kind]:
                continue
            key = row[kind+'_key']
            for table in before['_RCCPoachNexTables']:
                world_nex_update(result, table, (key,), {'Unknown2C': row[kind]})
    for map_id, row in sorted(result['MapTrapFormationData'].items()):
        for slot in range(1, 5):
            if not _enabled(rng, degree):
                continue
            old = tuple(row[field+str(slot)] for field in ('X', 'Y', 'TrapFlags', 'CommonItemId', 'RareItemId'))
            mutate_move_find(row, slot, map_id, maps, items, rng, chaos, random_degree,
                             extended_items=result.get('_ExtendedItemData'))
            new = tuple(row[field+str(slot)] for field in ('X', 'Y', 'TrapFlags', 'CommonItemId', 'RareItemId'))
            audit['move_find_slots'] += int(old != new)
    remember_rng(result,rng)
    result['_RCCRewardAudit'] = audit
    return audit


def finish_poach_ui(before, result, flags):
    """Keep Enhanced's fixed carcass prices consistent with the final items.

    RCC uses the randomized reward item's price in its old shop. Enhanced
    stores these prices, and descriptions naming the reward, on each localized
    carcass record. Reconcile after t/p/w so the UI cannot show vanilla prices
    or promise a reward that was replaced.
    """
    audit = dict(enabled=bool(set(flags)&set('tp')), price_rows=0,
                 description_rows=0, locales=7,
                 adaptation='Enhanced fixed carcass prices follow final reward item prices')
    if not audit['enabled'] or '_RCCPoachNexTables' not in before:
        result['_RCCPoachUIAudit'] = audit
        return audit
    descriptions = {
        'en':'This carcass has a randomized exchange reward.',
        'de':'Dieser Kadaver hat eine zufällige Tauschbelohnung.',
        'fr':"Cette carcasse offre une récompense d’échange aléatoire.",
        'cs':'此密猎品的交换奖励已随机化。',
        'ct':'此密獵品的交換獎勵已隨機化。',
        'ja':'この密猟品の交換報酬はランダム化されています。',
        'ko':'이 밀렵품의 교환 보상은 무작위로 변경되었습니다.',
    }
    tables = before['_RCCPoachNexTables']
    if {name.removeprefix('PoachItem-') for name in tables} != set(descriptions):
        raise ValueError('Unexpected poach locale inventory')
    baseline = tables['PoachItem-en']
    for row in result['_RCCPoaches'].values():
        for kind in ('common','rare'):
            key, reward = row[kind+'_key'], row[kind]
            original = baseline[key]
            original_cost = before['ItemData'][original['Unknown2C']]['Price']//2
            if (original['Cost'],original['SellPrice']) != (original_cost,(original_cost+1)//2):
                raise ValueError('Enhanced carcass price formula guard failed')
            cost = result['ItemData'][reward]['Price']//2
            values = dict(Cost=cost,SellPrice=(cost+1)//2)
            for table, localized in tables.items():
                old = localized[key]
                if any(old[field]!=original[field] for field in ('Unknown2C','Cost','SellPrice')):
                    raise ValueError('Localized carcass prices/rewards disagree')
                fields = {field:value for field,value in values.items() if old[field]!=value}
                if fields:
                    audit['price_rows'] += 1
                if reward != original['Unknown2C']:
                    fields['Unknown18'] = descriptions[table.removeprefix('PoachItem-')]
                    audit['description_rows'] += 1
                if fields:
                    world_nex_update(result,table,(key,),fields)
    result['_RCCPoachUIAudit'] = audit
    return audit
