"""RCC action attribute and execution requirement rules, source3758-3806.

Native values are combined with existing FFTIC Nex overrides before mutation;
only differences are sent back through OverrideAbilityActionData.
"""
from .game import ACTION_FIELDS
from .rcc import rng_for, mutate_normal,remember_rng
from .rcc_context import LUCAVI

SCALARS = ('Range','EffectArea','Vertical','Element','Formula','X','Y','InflictStatus','CT','MPCost')


def apply_actions(before, result, seed, random_degree=.25):
    rng = rng_for(seed,'ability-attributes-a')
    attrs = result['_AbilityAttributes']
    for aid, row in sorted(attrs.items()):
        for field in ('CT','MPCost','X','Y'):
            value = row[field]
            if 1<=value<=253:
                row[field] = mutate_normal(value,1,253,rng,random_degree=random_degree)
        for field in ('Range','EffectArea','Vertical'):
            value = row[field]
            if rng.choice([True,False]) and 0<=value<=253:
                new = mutate_normal(value,0,253,rng,random_degree=random_degree)
                if field=='Range' and value>0 and new==0: continue
                row[field] = new
    def assigned(table, command):
        return [result[table][command][f] for f in ACTION_FIELDS if f in result[table][command] and result[table][command][f]>0 and result[table][command][f] in attrs]
    for command in sorted(result['JobCommandData']):
        for aid in assigned('JobCommandData',command):
            row = attrs[aid]
            if command != 41 and row['Flags4']&4:
                row['Flags4'] = (row['Flags4']&~4)|8
            if 5<=command<=23:
                row['Flags3'] &= ~16
    for command in sorted(result['MonsterJobCommandData']):
        for aid in assigned('MonsterJobCommandData',command): attrs[aid]['Flags4'] &= ~12
    for job in sorted(LUCAVI & result['JobData'].keys()):
        command = result['JobData'][job]['JobCommandId']
        if command not in result['JobCommandData']: continue
        for aid in assigned('JobCommandData',command): attrs[aid]['Flags4'] &= ~12
    for command in (10,11,12,16):
        for aid in assigned('JobCommandData',command):
            row = attrs[aid]
            if not row['Flags3']&64 and rng.randint(1,5)==5: row['Flags3'] |= 64
    updates = {}
    for aid, row in attrs.items():
        original = before['_AbilityAttributes'][aid]
        fields = {f:row[f] for f in SCALARS if row[f]!=original[f]}
        if any(row[f'Flags{n}']!=original[f'Flags{n}'] for n in (1,2)):
            fields['Flags12'] = [row['Flags1'],row['Flags2']]
        if any(row[f'Flags{n}']!=original[f'Flags{n}'] for n in (3,4)):
            fields['Flags34'] = [row['Flags3'],row['Flags4']]
        row['random_hits'] = bool(row['Flags2']&8)
        row['require_sword'] = bool(row['Flags4']&8)
        row['require_materia_blade'] = bool(row['Flags4']&4)
        if fields: updates[aid] = fields
    remember_rng(result,rng)
    return dict(action_updates=updates,changed_actions=len(updates),
                source='RCC AbilityAttributesObject.mutate and mutate_abilities_attributes')
