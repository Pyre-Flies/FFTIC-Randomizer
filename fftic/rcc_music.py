"""RCC c phase and reusable source music choices for special encounters."""
import math

from .rcc import rng_for,remember_rng


SNEAKY_EVENTS = {
    0x186, 0x187, 0x188, 0x189, 0x18A, 0x18C, 0x18D, 0x18E,
    0x196, 0x198, 0x19C, 0x1A2, 0x1A5, 0x1A9, 0x1AB, 0x1AD,
    0x1B2, 0x1B5, 0x1BE, 0x1C3, 0x1C7, 0x1CA, 0x1D3, 0x1D5,
}
BANNED_MUSIC = (
    0, 17, 18, 19, 20, 21, 22, 23, 24, 27, 28, 29, 30, 31, 32,
    33, 35, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52,
    53, 54, 55, 56, 57, 59, 60, 63, 64, 65, 69, 70, 71, 72, 73,
    74, 75, 79, 98,
)


def randomize_music(row, index, rng, used_music, prefer_unused=False, force_battle=False):
    """RCC EncounterObject.randomize_music, including reuse and reset rules."""
    if 0xFC < row['entd'] < 0x180 or row['entd'] in SNEAKY_EVENTS:
        if not (force_battle and index == 0x12B):
            return
    banned = list(BANNED_MUSIC)
    if force_battle:
        banned += (list(range(25, 39))+list(range(40, 68))+list(range(69, 73))+
                   [78, 80]+list(range(83, 93))+list(range(93, 97)))
        for music in (73, 17, 18, 19):
            banned.remove(music)
    if rng.randint(1, 100) == 100:
        banned.remove(35)
    allowed = [music for music in range(100) if music not in banned]
    candidates = [music for music in allowed if music not in used_music]
    if not candidates:
        used_music.clear()
        candidates = allowed
    if prefer_unused:
        preferred = [music for music in candidates if 81 <= music <= 96]
        if preferred:
            candidates = preferred
    row['music'] = [music if music in banned else rng.choice(candidates) for music in row['music']]
    used_music.update(row['music'])


def apply_music(before, result, seed, flags, degree=1.0):
    if not math.isfinite(degree) or not 0 <= degree <= 1:
        raise ValueError('Music degree must be between zero and one')
    audit = dict(mode='RCC music', enabled='c' in flags and degree > 0,
                 source='randomizer.py:985-1018,5210-5215', changed_rows=0,
                 protected_rows=0, native_capacity=887)
    if not audit['enabled']:
        result['_RCCMusicAudit'] = audit
        return audit
    rng, used = rng_for(seed, 'music-c'), set()
    for index, row in sorted(result['_RCCEncounters'].items()):
        if degree < 1 and rng.random() >= degree:
            continue
        protected = 0xFC < row['entd'] < 0x180 or row['entd'] in SNEAKY_EVENTS
        audit['protected_rows'] += int(protected)
        old = list(row['music'])
        randomize_music(row, index, rng, used)
        audit['changed_rows'] += int(old != row['music'])
    result['_RCCUsedMusic'] = used
    remember_rng(result,rng)
    result['_RCCMusicAudit'] = audit
    return audit
