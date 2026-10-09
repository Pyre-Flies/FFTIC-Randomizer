"""RCC equipment phases adapted to the verified FFTIC native tables.

Rules come from rumble_chaos_crashdown/randomizer.py:1263-1426,
1517-1565, 1938-1939, 3726-3756 and 4621-4625.  The original phases
mutate equipment definitions and shop progression, not encounter equipment.
Item elements/status immunities stay unchanged: RCC comments that code out.

FFTIC adds a fifth equipment-permission byte and bonus rows 79-84.  Preserve
those additions rather than inventing a PS1 rule for them.  Rows 74-78 are the
same empty, unreferenced bonus slots RCC uses for its five fixed +1 bonuses.
"""
import math

from .catalog import creature_jobs
from .game import JOB_FIELDS
from .rcc import mutate_bits, mutate_normal, rng_for,remember_rng


BONUS_FIELDS = ('PABonus', 'MABonus', 'SpeedBonus', 'MoveBonus', 'JumpBonus')
RCC_EMPTY_CAST_ABILITIES = frozenset((0x28, 0x2D, 0xB8, 0xDB, 0xDC))
RCC_BANNED_SHOP_ITEMS = frozenset((0x49,))
RARE_BIT = 0x02
RCC_RANDOM_DEGREE = 0.25


def _require(result, table, fields):
    """A missing verified field must fail instead of silently skipping a phase."""
    if table not in result:
        raise ValueError(f'RCC equipment requires verified {table}')
    for index, row in result[table].items():
        missing = set(fields) - row.keys()
        if missing:
            raise ValueError(f'RCC equipment requires {table}[{index}] fields: {sorted(missing)}')


def _enabled(rng, degree):
    # At 100% this consumes no extra RNG draw and retains RCC's exact internal
    # probabilities; lower degrees skip a proportion of rows before mutation.
    return degree == 1 or (degree > 0 and rng.random() < degree)


def _normal(value, maximum, rng, minimum=0, random_degree=RCC_RANDOM_DEGREE):
    return mutate_normal(value, minimum, maximum, rng, random_degree=random_degree)


def _weapons(result, rng, degree, random_degree):
    _require(result, 'ItemWeaponData', ('Range', 'Power', 'Evasion', 'Formula', 'OptionsAbilityId'))
    for index, row in sorted(result['ItemWeaponData'].items()):
        if not _enabled(rng, degree):
            continue
        for field in ('Range', 'Power', 'Evasion'):
            value = row[field]
            if rng.choice((True, False)) and 0 <= value <= 0xFD:
                candidate = _normal(value, 0xFD, rng, random_degree=random_degree)
                if field != 'Range' or not value or candidate:
                    row[field] = candidate
        # RCC captures the old options byte before possibly converting a plain
        # Formula 1 weapon to Formula 2 (25% chance to cast an 8-bit ability).
        value = row['OptionsAbilityId']
        if row['Formula'] == 1 and value == 0 and rng.randint(1, 5) == 1:
            row['Formula'] = 2
            row['OptionsAbilityId'] = 0
        if row['Formula'] == 2 and (value == 0 or rng.randint(1, 10) == 1):
            candidate = rng.randint(1, 0xFF)
            if candidate in RCC_EMPTY_CAST_ABILITIES:
                candidate = rng.randint(1, 0x1F)
            row['OptionsAbilityId'] = candidate


def _secondary_stats(result, rng, degree, random_degree):
    specs = (
        ('ItemShieldData', ('PhysicalEvasion', 'MagicalEvasion'), 0x50),
        ('ItemArmorData', ('HPBonus', 'MPBonus'), 0xFD),
        ('ItemAccessoryData', ('PhysicalEvasion', 'MagicalEvasion'), 0x3C),
    )
    for table, fields, maximum in specs:
        _require(result, table, fields)
        for index, row in sorted(result[table].items()):
            if not _enabled(rng, degree):
                continue
            for field in fields:
                value = row[field]
                if rng.choice((True, False)) and 0 <= value <= maximum:
                    row[field] = _normal(value, maximum, rng, random_degree=random_degree)
    _require(result, 'ItemConsumableData', ('Z',))
    for index, row in sorted(result['ItemConsumableData'].items()):
        if _enabled(rng, degree) and 1 <= row['Z'] <= 0xFD:
            row['Z'] = _normal(row['Z'], 0xFD, rng, minimum=1, random_degree=random_degree)


def _bonuses(before, result, rng, degree, random_degree):
    _require(result, 'ItemEquipBonusData', BONUS_FIELDS)
    # These are native empty rows, not dynamically allocated IDs.  Do not
    # overwrite meaningful bonus rows if a future input changes their use.
    referenced = {row['EquipBonusId'] for row in before['ItemData'].values()}
    for index in range(0x4A, 0x4F):
        if index not in before['ItemEquipBonusData']:
            raise ValueError('RCC single-stat bonus slots are absent')
        if index in referenced or any(before['ItemEquipBonusData'][index][field] for field in BONUS_FIELDS):
            raise ValueError(f'RCC reserved bonus slot {index} is no longer unused')
    for index, row in sorted(result['ItemEquipBonusData'].items()):
        if not index:
            continue
        if index <= 0x49:
            if not _enabled(rng, degree):
                continue
            for field in BONUS_FIELDS:
                value = row[field]
                if rng.choice((True, False)) and 0 <= value <= 0xFD:
                    row[field] = _normal(value, 0xFD, rng, random_degree=random_degree)
        elif 0x4A <= index <= 0x4E:
            row[BONUS_FIELDS[index - 0x4A]] = 1
    _require(result, 'ItemData', ('EquipBonusId',))
    for index, row in sorted(result['ItemData'].items()):
        # Items 254/255 are the random-item/empty sentinels in FFTIC.  RCC's
        # original item table has only 254 entries (0-253).
        if 0 < index < 254 and _enabled(rng, degree) and row['EquipBonusId'] == 0 and rng.randint(1, 10) == 1:
            row['EquipBonusId'] = rng.randint(0x4A, 0x4E)


def _shops(result, rng, degree, chaos, random_degree):
    _require(result, 'ItemData', ('Price', 'ShopAvailability', 'TypeFlags', 'RequiredLevel'))
    equipment_boost = 1.1 ** min(max(chaos, 0), 500)
    for index, row in sorted(result['ItemData'].items()):
        if index >= 254 or not _enabled(rng, degree):
            continue
        # RCC includes item row 0; all its zero/default values remain legal.
        row['Price'] = int(round(_normal(row['Price'], 65000, rng, random_degree=random_degree), -1))
        if row['Price'] > 500:
            row['Price'] = int(round(row['Price'], -2))
        if 1 <= row['ShopAvailability'] <= 16:
            row['ShopAvailability'] = _normal(row['ShopAvailability'], 16, rng, minimum=1,
                                              random_degree=random_degree)
        if row['TypeFlags'] & RARE_BIT and rng.randint(1, 4) != 4:
            if index not in RCC_BANNED_SHOP_ITEMS or rng.randint(1, 3) == 3:
                if row['RequiredLevel'] <= 5:
                    row['RequiredLevel'] = 50
                row['TypeFlags'] &= ~RARE_BIT
        if row['RequiredLevel'] >= 1:
            # Very high chaos can round RCC's enemy-level base to zero.  The
            # native field still requires 1-99: clamp before the shared helper.
            base = max(1, min(99, int(round(row['RequiredLevel'] / equipment_boost))))
            row['RequiredLevel'] = _normal(base, 99, rng, minimum=1, random_degree=random_degree)


def _weapon_status(result, rng, degree):
    _require(result, 'ItemWeaponData', ('Formula', 'OptionsAbilityId'))
    for index, row in sorted(result['ItemWeaponData'].items()):
        if not _enabled(rng, degree) or row['Formula'] == 2 or rng.randint(1, 10) != 1:
            continue
        if row['OptionsAbilityId'] > 0 and rng.randint(1, 10) != 1:
            continue
        candidate = rng.randint(0, 0x79)
        if candidate != 0x60:  # RCC excludes Crystal.
            row['OptionsAbilityId'] = candidate


def _equippability(before, result, rng, degree):
    _require(result, 'JobData', ('EquippableItems',))
    creatures = creature_jobs(before)
    for index, row in sorted(result['JobData'].items()):
        if not index or not row['JobCommandId'] or not any(row[field] for field in JOB_FIELDS):
            continue
        # RCC's original "human" iterator means IDs below 94, including its
        # Lucavi jobs.  Extend that rule to the additional humanoid WOTL jobs.
        if index >= 94 and index in creatures:
            continue
        if not _enabled(rng, degree):
            continue
        mask = row['EquippableItems']
        if not 0 <= mask < (1 << 40):
            raise ValueError('Equipment permissions exceed the native 40-bit mask')
        changed = mutate_bits(mask >> 8, rng, size=32, odds_multiplier=4.0)
        row['EquippableItems'] = (changed << 8) | (mask & 0xFF)


def apply_equipment(before, result, seed, flags, degree=1.0, chaos=1.0, random_degree=RCC_RANDOM_DEGREE):
    """Apply enabled RCC equipment phases to result and return their audit.

    ``w`` mutates equipment/consumable definitions and bonus assignments;
    ``p`` mutates shop prices, availability, rarity and required item level;
    ``y`` mutates weapon status options; ``i`` mutates job equipment permissions.
    The parent ability engine owns ability/status/innate parts of ``y``/``i``.
    At degree=1 internal probabilities remain RCC's originals; normal mutation
    width defaults to RCC's 0.25 and can be configured independently.  Partial
    degree selects fewer rows without replacing those internal odds.
    """
    if not math.isfinite(degree) or not 0 <= degree <= 1:
        raise ValueError('Equipment degree must be 0 to 1')
    if not math.isfinite(chaos) or chaos < 0:
        raise ValueError('Chaos must be a nonnegative finite number')
    if not math.isfinite(random_degree) or not 0 <= random_degree <= 1:
        raise ValueError('Normal mutation degree must be 0 to 1')
    audit = dict(
        mode='RCC equipment phases', degree=degree, chaos=chaos,
        random_degree=random_degree, phases=[],
        adaptations=[
            'FFTIC random/empty item sentinels 254 and 255 are preserved',
            'FFTIC fifth equipment-permission byte is preserved',
            'WOTL-added equip-bonus rows 79-84 are preserved',
            'High-chaos required-item-level bases are clamped to native range 1-99',
        ],
        unchanged=[
            'Encounter units, starting equipment, drops, poaches and move-find items',
            'Item elements and status immunity/innate/start fields (disabled in RCC source)',
        ])
    if not degree:
        return audit
    # Match RCC's phase order: innate permissions, status mutations, shops,
    # then equipment definitions.  A status weapon may consequently avoid the
    # Formula 1->2 conversion when the later equipment phase sees its options.
    if 'i' in flags:
        _equippability(before, result, rng_for(seed, 'equipment-permissions-i'), degree)
        audit['phases'].append('i equipment permissions')
    if 'y' in flags:
        _weapon_status(result, rng_for(seed, 'weapon-status-y'), degree)
        audit['phases'].append('y weapon status')
    if 'p' in flags:
        rng = rng_for(seed, 'shops-p')
        _shops(result,rng,degree,chaos,random_degree)
        remember_rng(result,rng)
        audit['phases'].append('p shops and rarity')
    if 'w' in flags:
        rng = rng_for(seed, 'equipment-w')
        _weapons(result, rng, degree, random_degree)
        _secondary_stats(result, rng, degree, random_degree)
        _bonuses(before, result, rng, degree, random_degree)
        remember_rng(result,rng)
        audit['phases'].append('w equipment, consumables and bonuses')
    return audit
