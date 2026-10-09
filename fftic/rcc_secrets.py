"""Optional RCC fiesta/easymodo changes after the source's final cleanup.

The literal source order is fiesta followed by easymodo. Neither phase uses
random draws. Native newgame code patches are supplied by a verified helper;
this module never writes disc offsets or an installed executable.
"""
from copy import deepcopy

from .rcc import rng_for
from .rcc_units import UnitEngine


FIESTA_ENTD = 0x188
FIESTA_PARTY = (0x1880,0x1882,0x1883,0x1884,0x1885)
MIME_JOB = 0x5D
EASY_JOB = 0x1C
STONE_GUN = 0x49


def apply_fiesta_units(engine):
    """RCC4650-4718 unit body, including its last-unit right-hand write."""
    required = {FIESTA_ENTD,0x183,0x184}
    if not required<=set(engine.mapunits):
        raise ValueError('Fiesta requires verified opening and starting-party ENTD records')
    units = sorted(engine.mapunits[FIESTA_ENTD],key=lambda unit:unit.index)
    funits = [unit for unit in units if unit.index in FIESTA_PARTY]
    nunits = [unit for unit in units if unit not in funits]
    if len(units)!=16 or len(funits)!=5:
        raise ValueError('Fiesta starting-party template inventory changed')
    for unit in units:
        unit.secondary = 0
        for attribute in ('reaction','support','movement'): setattr(unit,attribute,0x1FF)
    for party in funits:
        party.unlocked = 0x13
        party.unlocked_level = 1
        for attribute in ('lefthand','head','body','accessory'): setattr(party,attribute,0xFE)
        # Source writes `u`, the final variable from the preceding unit loop,
        # rather than `f`. This effective slot15 write is intentional parity.
        unit.righthand = STONE_GUN
    specs = (('ramza',MIME_JOB,69,69),('male',MIME_JOB,70,40),
             ('female',MIME_JOB,70,40),('male',MIME_JOB,70,70),
             ('female',MIME_JOB,70,70))
    for party,(gender,job,brave,faith) in zip(funits,specs):
        party.set_bit('male',gender!='female')
        party.set_bit('female',gender=='female')
        party.graphic = 1 if gender=='ramza' else 0x80 if gender=='male' else 0x81
        party.job,party.brave,party.faith = job,brave,faith
    for guest in nunits:
        if guest.index>0x1887: continue
        guest.unlocked,guest.unlocked_level = 0,1
        guest.righthand = STONE_GUN
        for attribute in ('lefthand','head','body','accessory'): setattr(guest,attribute,0xFF)
    armed = []
    for unit in set(engine.mapunits[0x183])|set(engine.mapunits[0x184]):
        if unit.get_bit('enemy_team'):
            unit.righthand = STONE_GUN
            armed.append(unit.owner)
    return dict(starting_party=[unit.owner for unit in funits],
                opening_enemies_armed=sorted(armed),last_starting_slot_armed=units[-1].owner,
                source_quirks=['The right-hand write targets the last unit, ENTD392 slot15',
                               'The direct Mime requirement patch is overwritten by final cached JobReqObject writes'])


def apply_easymodo_units(engine):
    """RCC5270-5275: every enemy level1, nonspecial sprites use job28."""
    enemies,generic = [],[]
    for unit in engine.units:
        if unit.get_bit('enemy_team'):
            unit.level = 1
            enemies.append(unit.owner)
            if not unit.has_special_graphic:
                unit.job = EASY_JOB
                generic.append(unit.owner)
    return dict(enemy_units=sorted(enemies),generic_enemy_jobs=sorted(generic),
                level=1,generic_job=EASY_JOB)


def apply_secrets(before,result,seed='',*,fiesta=False,easymodo=False,engine=None,fiesta_native=None):
    """Apply optional source secrets after cleanup and before final emission.

    `fiesta_native(before,result)` must add exact-build guarded native newgame
    patches and return a JSON audit. The native adapter can be passed by the
    parent or provided by the bundled rcc_fiesta_native module once verified.
    No extra palette cleanup follows these source phases.
    """
    if not isinstance(fiesta,bool) or not isinstance(easymodo,bool):
        raise ValueError('RCC secret mode switches must be boolean')
    audit = dict(fiesta=fiesta,easymodo=easymodo,order=[],source='RCC4650-4718,5267-5275')
    if not fiesta and not easymodo:
        result['_RCCSecretAudit'] = audit
        return audit
    if fiesta:
        if fiesta_native is None:
            try:
                from .rcc_fiesta_native import apply_fiesta_native
            except ImportError as error:
                raise ValueError('Fiesta requires its verified native newgame-job patch helper') from error
            fiesta_native = apply_fiesta_native
        audit['native_fiesta'] = fiesta_native(before,result)
    engine = engine or result.get('_RCCUnitEngine') or UnitEngine(before,result,rng_for(seed,'secrets'))
    result['_RCCUnitEngine'] = engine
    original = deepcopy(result['_RCCUnitContext'])
    if fiesta:
        audit['order'].append('fiesta')
        audit['fiesta_units'] = apply_fiesta_units(engine)
    if easymodo:
        audit['order'].append('easymodo')
        audit['easymodo_units'] = apply_easymodo_units(engine)
    changed = {owner:[field for field,value in row.items() if original[owner][field]!=value]
               for owner,row in result['_RCCUnitContext'].items() if original[owner]!=row}
    audit['changed_units'] = len(changed)
    audit['changed_fields'] = sum(map(len,changed.values()))
    audit['units'] = [dict(owner=list(owner),fields=fields) for owner,fields in sorted(changed.items())]
    result['_RCCSecretAudit'] = audit
    return audit
