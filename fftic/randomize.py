"""RCC rule orchestration on verified FFTIC native tables."""
import copy
import math
from .game import ACTION_FIELDS, RSM_FIELDS, JOB_FIELDS
from .catalog import pools
from .rcc import apply_abilities, apply_monsters, scopes, rng_for
from .rcc_equipment import apply_equipment
from .rcc_stats import apply_job_stats

FLAGS = {
    'r': 'Job requirements and job-level JP',
    'i': 'Job innate abilities, statuses, elements and equipment permissions',
    's': 'Job skillsets (ordinary and unique)',
    'a': 'Ability CT, MP, power, range and area',
    'y': 'Ability and weapon status effects',
    'j': 'Human job stats and skill JP costs',
    'm': 'Monster skills and stats',
    'u': 'Enemy and ally encounter units',
    'z': 'Special surprises',
    'f': 'Enemy and ally formations',
    't': 'Trophies, poaches and move-find items',
    'p': 'Prices, shop timing and rarity',
    'w': 'Equipment, consumables and equip bonuses',
    'c': 'Battle music',
    'o': 'Automatically advance event dialogue',
    'b': 'Optional six free actions for testing',
}
DEFAULT_FLAGS = 'risayjmuzftpwc'
ABILITY_MODES = {'rcc':'Shuffle','full':'Full redistribution'}


def active_jobs(tables):
    return [i for i,row in tables['JobData'].items()
            if i and row['JobCommandId'] and any(row[f] for f in JOB_FIELDS)]


def command_scopes(tables):
    return scopes(tables)[:2]


def action_pool(tables):
    return pools(tables, 'player')[1]


def starter_actions(seed, tables):
    rng = rng_for(seed, 'testing-free-actions')
    catalog = tables['_AbilityCatalog']
    paid = [a for a in action_pool(tables) if catalog[a]['jp_cost'] > 0]
    physical = [a for a in paid if catalog[a]['ai_flags'] & (1 << 16)]
    other = [a for a in paid if a not in physical]
    return tuple(rng.sample(physical, min(3,len(physical)))+
                 rng.sample(other, min(3,len(other))))


def validate(before, after, flags, degree, ability_mode='rcc'):
    ordinary, unique, creatures = scopes(before)
    allowed = ((ordinary | unique) if 's' in flags else set()) | (creatures if 'm' in flags else set())
    for command, old in before['JobCommandData'].items():
        new = after['JobCommandData'][command]
        if command not in allowed and old != new:
            raise ValueError('Disabled skillset scope changed')
        # RCC's rare final injections can repeat an ID within a row. Do not
        # impose a deduplication rule that its source does not have.
        for field in RSM_FIELDS:
            aid = new[field]
            if aid and before['_AbilityMetadata'][aid]['AbilityType'] not in (7,8,9):
                raise ValueError('A non-passive entered a passive slot')
    if ability_mode=='rcc' and before['CommandTypeData'] != after['CommandTypeData']:
        raise ValueError('Native command menu changed')
    if ability_mode=='full':
        for command,old in before['CommandTypeData'].items():
            new = after['CommandTypeData'][command]
            if old != new and (command not in allowed or not degree or new['Menu'] not in (0,1,2,3,4,7,9,10)):
                raise ValueError('Disabled or unsupported full-mode command menu changed')
        from .full import PROFILE_TYPES, profile_pools
        player_profiles = profile_pools(before)
        catalog = before['_AbilityCatalog']
        for owner in after['_RCCAbilityAudit']['selected_owners']:
            table,command,actor = owner['table'],owner['id'],owner['actor']
            row = after[table][command]
            assigned = [aid for aid in row.values() if aid]
            if len(assigned)!=len(set(assigned)):
                raise ValueError('Full mode introduced a duplicate within one skillset')
            if any(not catalog[a]['eligible'] or catalog[a]['domain'] not in (actor,'both') for a in assigned):
                raise ValueError('Full mode assigned an excluded or wrong-actor ability')
            actions = [row[f] for f in ACTION_FIELDS if f in row and row[f]]
            if not actions:
                raise ValueError('Full mode produced an empty selected action list')
            if table=='JobCommandData':
                menu = after['CommandTypeData'][command]['Menu']
                allowed_actions = set(player_profiles[menu]) if actor=='player' else set(pools(before,'monster')[1])
                if any(a not in allowed_actions for a in actions):
                    raise ValueError('Full mode action is incompatible with its command menu')
            elif not row['AbilityId4']:
                raise ValueError('Full mode omitted the hidden monster skill')
    if ('m' not in flags or degree == 0) and before['MonsterJobCommandData'] != after['MonsterJobCommandData']:
        raise ValueError('Disabled monster skillset scope changed')
    # Native unused legacy IDs can remain on their original records, but
    # they are not candidates for new assignments to another skillset.
    catalog = before['_AbilityCatalog']
    for table in ('JobCommandData','MonsterJobCommandData'):
        for command,row in after[table].items():
            original = set(before[table][command].values())
            for aid in set(row.values())-original-{0}:
                if not catalog[aid]['eligible']:
                    raise ValueError(f'Excluded ability {aid} introduced into {table}[{command}]')
    for job, row in before['JobData'].items():
        if row['JobCommandId'] != after['JobData'][job]['JobCommandId'] and not ('z' in flags and job in (33,65)):
            raise ValueError('Native job command mapping changed')
        for field in row:
            maximum = field_maximum('JobData',field)
            if not 0 <= after['JobData'][job][field] <= maximum:
                raise ValueError('Job field out of range')
    for table, rows in after.items():
        if table.startswith('_'): continue
        for row in rows.values():
            for field, value in row.items():
                maximum = field_maximum(table,field)
                if not isinstance(value,int) or not 0 <= value <= maximum:
                    raise ValueError(f'Invalid {table}.{field}')


def field_maximum(table,field):
    if field in ('EquippableItems','InnateStatus','ImmuneStatus','StartingStatus','Effects'):
        return (1<<40)-1
    if field=='Price' or field.startswith(('RareItemId','CommonItemId')):
        return 65535
    if field in ACTION_FIELDS+RSM_FIELDS or field.startswith('InnateAbilityId'):
        return 511
    if table=='JobNeedLevelData' or table=='MapTrapFormationData' and field.startswith(('X','Y')):
        return 15
    return 255


def randomize(tables, seed, flags=DEFAULT_FLAGS, spread=.25, skill_degree=1.0, chaos=1.0,
              ability_mode='rcc',min_actions=6,max_actions=12,passives_per_type=1,
              fiesta=False,easymodo=False):
    if not isinstance(seed,str) or not 1 <= len(seed) <= 128:
        raise ValueError('Seed must contain 1 to 128 characters')
    if not isinstance(fiesta,bool) or not isinstance(easymodo,bool):
        raise ValueError('Optional mode switches must be boolean')
    if not flags and not (fiesta or easymodo) or set(flags)-FLAGS.keys():
        raise ValueError('Supported flags: '+''.join(FLAGS))
    if not math.isfinite(spread) or not 0 <= spread <= 1:
        raise ValueError('Stat randomness must be 0 to 1')
    if not math.isfinite(skill_degree) or not 0 <= skill_degree <= 1:
        raise ValueError('Ability shuffle degree must be 0 to 1')
    if not math.isfinite(chaos) or not 0 <= chaos <= 10:
        raise ValueError('Chaos multiplier must be 0 to 10')
    if ability_mode not in ABILITY_MODES:
        raise ValueError('Ability mode must be rcc or full')
    if not isinstance(min_actions,int) or not isinstance(max_actions,int) or not 1<=min_actions<=max_actions<=16:
        raise ValueError('Full-mode action range must be integers within 1 to 16')
    if passives_per_type not in (1,2):
        raise ValueError('Full-mode passives per type must be 1 or 2')
    result = copy.deepcopy(tables)
    # Original RCC order is r,i,s,a,y,j,m,u,z,f,t,p,w,c. Innate and
    # monster mutations share their source phase's RNG with its later steps.
    if '_RCCGeneralJobs' in result:
        from .rcc_requirements import apply_requirements
        result['_RCCRequirementAudit'] = apply_requirements(tables,result,seed,flags,chaos=chaos,random_degree=spread)
    elif set(flags)&set('ruftz'):
        raise ValueError('Encounter/world flags require prepare_world_data and prepare_unit_context')
    from .rcc_innates import apply_innates
    from .rcc_status import metadata_updates
    result['_RCCInnateAudit'] = apply_innates(tables,result,seed,''.join(f for f in flags if f=='i'),random_degree=spread)
    if '_RCCUnitContext' in result:
        from .rcc_units import apply_job_unit_overrides
        apply_job_unit_overrides(result,result['_RCCInnateAudit']['unit_overrides'])
    if ability_mode=='rcc':
        result['_RCCAbilityAudit'] = apply_abilities(tables,result,seed,flags,skill_degree,include_monsters=False)
    else:
        from .full import apply_full
        result['_RCCAbilityAudit'] = apply_full(tables,result,seed,flags,degree=skill_degree,
                                               min_actions=min_actions,max_actions=max_actions,
                                               passives_per_type=passives_per_type)
    for aid,cost in result['_RCCAbilityAudit'].get('jp_cost_updates',{}).items():
        result['_AbilityMetadata'][aid]['JPCost'] = cost
    if 'a' in flags:
        from .rcc_actions import apply_actions
        result['_RCCActionAudit'] = apply_actions(tables,result,seed,spread)
    if 'y' in flags:
        from .rcc_status import apply_status
        result['_RCCStatusAudit'] = apply_status(tables,result,seed)
    result['_RCCStatAudit'] = apply_job_stats(tables,result,seed,''.join(f for f in flags if f=='j'),spread,chaos)
    if 'm' in flags:
        from .rcc_stats import apply_monster_stats_innates
        monster_rng = rng_for(seed,'monster-phase-m')
        result['_RCCMonsterInnateAudit'] = apply_monster_stats_innates(tables,result,seed,spread,chaos,rng=monster_rng)
        if '_RCCUnitContext' in result:
            apply_job_unit_overrides(result,result['_RCCMonsterInnateAudit']['unit_overrides'])
    if ability_mode=='rcc' and 'm' in flags and skill_degree:
        costs = {a:r['JPCost'] for a,r in result['_AbilityMetadata'].items()}
        result['_RCCAbilityAudit']['monster_phase'] = apply_monsters(tables,result,seed,skill_degree,costs,rng=monster_rng)
    if '_RCCUnitContext' in result:
        from .rcc_units import apply_units
        result['_RCCUnitAudit'] = apply_units(tables,result,seed,flags,chaos=chaos,random_degree=spread)
    if 'z' in flags:
        from .rcc_specials import apply_special_units,apply_ending_units,guarantee_invite
        result['_RCCSpecialAudit'] = apply_special_units(tables,result,seed,flags,chaos=chaos,random_degree=spread)
        result['_RCCEndingAudit'] = apply_ending_units(tables,result,seed,flags,chaos=chaos,random_degree=spread)
        result['_RCCEncounters'][299]['following'] = 0
        result['_RCCEncounters'][299]['music'][0] = 69
        result['_RCCInviteAudit'] = guarantee_invite(tables,result,seed,flags)
        if '_RCCNameTables' in tables:
            from .rcc_names import apply_names
            result['_RCCNameAudit'] = apply_names(tables,result,seed,flags)
        from .rcc_surprises_world import apply_weather,apply_map_surprises
        result['_RCCWeatherAudit'] = apply_weather(tables,result,seed,flags)
        result['_RCCMapSurpriseAudit'] = apply_map_surprises(tables,result,seed,flags,chaos,spread)
    if 'f' in flags:
        from .rcc_formations import apply_formations
        result['_RCCFormationAudit'] = apply_formations(tables,result,seed,chaos=chaos,random_degree=spread)
    if 't' in flags:
        from .rcc_rewards import apply_rewards
        result['_RCCRewardAudit'] = apply_rewards(tables,result,seed,flags,chaos=chaos,random_degree=spread)
    result['_RCCEquipmentAudit'] = apply_equipment(tables,result,seed,''.join(f for f in flags if f in 'pw'),degree=1,chaos=chaos,random_degree=spread)
    from .rcc_rewards import finish_poach_ui
    finish_poach_ui(tables,result,flags)
    if 'c' in flags:
        from .rcc_music import apply_music
        result['_RCCMusicAudit'] = apply_music(tables,result,seed,flags)
    if '_RCCUnitContext' in result:
        from .rcc_units import finalize_cleanup
        if 'z' in flags:
            from .rcc_surprises_world import apply_warjilis
            result['_RCCWarjilisAudit'] = apply_warjilis(tables,result,seed,flags,chaos,spread)
            from .rcc_specials import apply_special_postmusic
            result['_RCCSpecialPostAudit'] = apply_special_postmusic(tables,result,seed,flags)
        from .rcc_specials import apply_alma_math_cleanup
        apply_alma_math_cleanup(tables,result)
        from .rcc import continuation_rng
        result['_RCCCleanupAudit'] = finalize_cleanup(tables,result,seed,flags,rng=continuation_rng(result,seed))
    from .rcc_secrets import apply_secrets
    apply_secrets(tables,result,seed,fiesta=fiesta,easymodo=easymodo)
    result['_RCCMetadataUpdates'] = metadata_updates(tables,result)
    result['_RCCStatAudit']['jp_cost_updates'] = {a:r['JPCost'] for a,r in result['_RCCMetadataUpdates'].items() if 'JPCost' in r}
    validate(tables,result,flags,skill_degree,ability_mode)
    return result


def differences(before, after):
    return [dict(table=t,id=i,field=f,before=v,after=after[t][i][f])
            for t in before if not t.startswith('_') for i in sorted(before[t]) for f,v in before[t][i].items()
            if v != after[t][i][f]]
