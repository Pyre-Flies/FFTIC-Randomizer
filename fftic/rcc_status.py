"""RCC y: status option slots, ability infliction/AI flags, then weapon status.

Ability metadata is private native-patch input. Never emit AbilityData XML:
the pinned loader writes its lower type nibble from the flags enum by mistake.
The parent writes only changed, verified metadata bytes and preserves byte 3.
"""
import math

from .rcc import randint, rng_for,remember_rng
from .rcc_equipment import _weapon_status
from .rcc_innates import VALID_START_STATUSES, swap_mask


STATUS_FORMULAS = frozenset((1, 8, 9, 10, 11, 13, 14, 30, 31, 32, 33, 34,
                            36, 38, 40, 41, 45, 49, 51, 53, 56, 61, 63, 64,
                            65, 71, 78, 80, 81, 82, 83, 87, 90, 91, 94, 95, 96))
OPTION_CANCEL, OPTION_SEPARATE, OPTION_RANDOM, OPTION_ALL = 0x10, 0x20, 0x40, 0x80
AI_ADD_STATUS, AI_CANCEL_STATUS = 1 << 4, 1 << 5
METADATA_FIELDS = ('JPCost', 'LearnChance', 'AIBehaviorFlags')


def metadata_updates(before, result):
    """Collect all native metadata changes, with byte3 type/flags guarded."""
    updates = {}
    for aid, row in result['_AbilityMetadata'].items():
        old = before['_AbilityMetadata'][aid]
        if row['AbilityType'] != old['AbilityType'] or row['Flags'] != old['Flags']:
            raise ValueError('RCC metadata patch must preserve native ability type/flags byte')
        fields = {f: row[f] for f in METADATA_FIELDS if row[f] != old[f]}
        if not 0 <= row['JPCost'] <= 65535 or not 0 <= row['LearnChance'] <= 255:
            raise ValueError('RCC metadata exceeds the verified native field widths')
        if not 0 <= row['AIBehaviorFlags'] <= 0xFFFFFFFF:
            raise ValueError('RCC AI behavior must fit its native uint32 mask')
        if fields:
            updates[aid] = fields
    result['_RCCMetadataUpdates'] = updates
    return updates


def randomize_empty_option(index, row, rng):
    """Initialize precisely RCC's nine unused status-option slots."""
    if not (29 <= index <= 31 or 122 <= index <= 127):
        return
    to_inflict = 0
    while True:
        bit = 1 << randint(rng, 0, 39)
        if not bit & VALID_START_STATUSES:
            continue
        to_inflict |= bit
        if to_inflict and randint(rng, 1, 2**to_inflict.bit_count()) != 1:
            break
    row['Effects'] = swap_mask(to_inflict)
    choice = randint(rng, 1, 9)
    row['OptionType'] |= (OPTION_RANDOM if choice <= 3 else OPTION_SEPARATE if choice <= 6
                          else OPTION_CANCEL if choice <= 8 else OPTION_ALL)


def mutate_ability_status(result, aid, rng):
    """Apply source infliction probabilities and correct existing status AI."""
    if aid == 29:
        return
    row = result['_AbilityAttributes'][aid]
    value = row['InflictStatus']
    if value > 0 or row['Formula'] in STATUS_FORMULAS:
        if randint(rng, 1, 5) == 1:
            if value > 0 and randint(rng, 1, 10) != 1:
                return
            new = randint(rng, 1, 127)
            if new == 96 and (row['EffectArea'] > 0 or row['Flags3'] & 64 or row['Flags2'] & 2):
                return
            row['InflictStatus'] = new
            ability = result['_AbilityMetadata'][aid]
            flags = ability['AIBehaviorFlags']
            if flags & (AI_ADD_STATUS | AI_CANCEL_STATUS):
                option = result['ItemOptionsData'][new]['OptionType']
                if option & OPTION_CANCEL:
                    ability['AIBehaviorFlags'] = (flags & ~AI_ADD_STATUS) | AI_CANCEL_STATUS
                elif option & (OPTION_SEPARATE | OPTION_RANDOM | OPTION_ALL):
                    ability['AIBehaviorFlags'] = (flags | AI_ADD_STATUS) & ~AI_CANCEL_STATUS


def apply_status(before, result, seed, degree=1., *, rng=None):
    """Apply all y mutations in RCC order using one continuing RNG stream."""
    if not math.isfinite(degree) or not 0 <= degree <= 1:
        raise ValueError('Status degree must be 0 to 1')
    audit = dict(mode='RCC inflict-status rules', option_updates={}, action_updates={},
                 weapon_updates={}, metadata_updates={})
    if not degree:
        return audit
    if 'ItemOptionsData' not in result or set(result['ItemOptionsData']) != set(range(128)):
        raise ValueError('RCC status requires the verified 128-row ItemOptionsData table')
    for index, row in result['ItemOptionsData'].items():
        if not {'OptionType', 'Effects'} <= row.keys():
            raise ValueError(f'RCC status requires ItemOptionsData[{index}] type and effects')
    rng = rng or rng_for(seed, 'inflict-status-y')
    for index, row in sorted(result['ItemOptionsData'].items()):
        if degree == 1 or rng.random() < degree:
            randomize_empty_option(index, row, rng)
    for aid in sorted(result['_AbilityAttributes']):
        if degree == 1 or rng.random() < degree:
            mutate_ability_status(result, aid, rng)
    _weapon_status(result, rng, degree)
    audit['option_updates'] = {a: dict(r) for a, r in result['ItemOptionsData'].items()
                               if r != before['ItemOptionsData'][a]}
    audit['action_updates'] = {a: {'InflictStatus': r['InflictStatus']}
                               for a, r in result['_AbilityAttributes'].items()
                               if r['InflictStatus'] != before['_AbilityAttributes'][a]['InflictStatus']}
    audit['weapon_updates'] = {a: {'OptionsAbilityId': r['OptionsAbilityId']}
                               for a, r in result['ItemWeaponData'].items()
                               if r['OptionsAbilityId'] != before['ItemWeaponData'][a]['OptionsAbilityId']}
    audit['metadata_updates'] = metadata_updates(before, result)
    remember_rng(result,rng)
    return audit
