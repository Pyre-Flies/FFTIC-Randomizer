"""Produce a Reloaded-II mod and reproducible audit report outside game data."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from . import VERSION
from .game import ACTION_FIELDS, RSM_FIELDS, JOB_NAMES, read_game
from .randomize import FLAGS, DEFAULT_FLAGS, ABILITY_MODES, randomize, differences, active_jobs, command_scopes
from .catalog import attach_catalog, write_catalog, pools
from .rcc import scopes

XML_TYPES = {
    "JobData": ("JobTable", "Job"),
    "JobCommandData": ("JobCommandTable", "JobCommand"),
    "ItemData": ("ItemTable", "Item"),
    "ItemWeaponData": ("ItemWeaponTable", "ItemWeapon"),
    "ItemArmorData": ("ItemArmorTable", "ItemArmor"),
    "ItemShieldData": ("ItemShieldTable", "ItemShield"),
    "ItemAccessoryData": ("ItemAccessoryTable", "ItemAccessory"),
    "MonsterJobCommandData": ("MonsterJobCommandTable", "MonsterJobCommand"),
    "CommandTypeData": ("CommandTypeTable", "CommandType"),
    "ItemConsumableData": ("ItemConsumableTable", "ItemConsumable"),
    "ItemEquipBonusData": ("ItemEquipBonusTable", "ItemEquipBonus"),
    "ItemOptionsData": ("ItemOptionsTable", "ItemOptions"),
    "JobNeedLevelData": ("JobNeedLevelTable", "JobNeedLevel"),
    "MapTrapFormationData": ("MapTrapFormationTable", "MapTrapFormation"),
}


def write_json(path, content):
    Path(path).write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def patch_bytes(table, changed_rows, randomized):
    root_name, row_name = XML_TYPES[table]
    root = ET.Element(root_name)
    ET.SubElement(root, "Version").text = "1"
    entries = ET.SubElement(root, "Entries")
    for row_id in sorted(changed_rows):
        row = ET.SubElement(entries, row_name)
        ET.SubElement(row, "Id").text = str(row_id)
        fields = changed_rows[row_id]
        if table == "JobCommandData":
            # These nullable fields have no model defaults. The loader's ID
            # setters dereference .Value, so deserialize them before any IDs.
            # Starting at zero is intentional: the complete vectors below
            # recompute every extension bit through those same setters.
            ET.SubElement(row, "ExtendAbilityIdFlagBits").text = "0"
            ET.SubElement(row, "ExtendReactionSupportMovementIdFlagBits").text = "0"
            # Loader model setters derive extension flags from the supplied
            # IDs. Supply the complete vector so untouched high IDs retain
            # their bits too. Original-value fields are ignored by its diff.
            fields = {f: randomized[table][row_id][f] for f in ACTION_FIELDS + RSM_FIELDS}
        for name, value in fields.items():
            ET.SubElement(row, name).text = str(value)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def load_names(project_root, game_dir=None):
    if game_dir is not None:
        from .report_names import prepare_report_names
        return prepare_report_names(game_dir,project_root)
    path = Path(project_root) / "research" / "names.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def label(table, row_id, names):
    if table == "JobData":
        return names.get('Job',{}).get(str(row_id),JOB_NAMES.get(row_id,f'Job {row_id}'))
    kind = {"JobCommandData": "JobCommand", "MonsterJobCommandData": "JobCommand", "ItemData": "Item"}.get(table)
    return names.get(kind, {}).get(str(row_id), f"{table} row {row_id}")


def report_text(changes, manifest, names):
    lines = ["FFTIC Randomizer seed report", "", f"Seed: {manifest['seed']}",
             f"Features: {manifest['flags']}", f"Stat randomness: {manifest['spread']:.0%}",
             f"Ability mode: {ABILITY_MODES[manifest['ability_mode']]}",
             f"Ability shuffle degree: {manifest['skill_degree']:.0%}", f"Chaos multiplier: {manifest['chaos']}",
             f"Generator: {VERSION}", "Mode: Enhanced", "",
             "This is an experimental mod. Generated and checked offline; gameplay has not been validated.",
             "The seed affects allies and enemies that use the edited shared jobs and equipment.",
             "See the encounter report and phase audits for encounter changes.", ""]
    for table in XML_TYPES:
        subset = [c for c in changes if c["table"] == table]
        if not subset:
            continue
        lines.extend([table, "-" * len(table)])
        for change in subset:
            old, new = change["before"], change["after"]
            if table in ("JobCommandData",'MonsterJobCommandData'):
                abilities = names.get("Ability", {})
                old = f"{old} ({abilities.get(str(old), 'ability')})"
                new = f"{new} ({abilities.get(str(new), 'ability')})"
            lines.append(f"  {label(table, change['id'], names)} [ID {change['id']}] {change['field']}: {old} -> {new}")
        lines.append("")
    return "\n".join(lines) + "\n"


def create_seed(game_dir, output_root, seed, flags=DEFAULT_FLAGS, spread=0.25, project_root=None, skill_degree=1.0,chaos=1.0,
                ability_mode='rcc',min_actions=6,max_actions=12,passives_per_type=1,
                fiesta=False,easymodo=False):
    game_dir, output_root = Path(game_dir).resolve(), Path(output_root).resolve()
    # Avoid putting project output into an active loader/game data location.
    for protected in (game_dir / "data", game_dir / "scripts"):
        if output_root == protected or protected in output_root.parents:
            raise ValueError("Output must be outside the game's data and scripts directories")
    before, build = read_game(game_dir)
    before['_RCCGameDirectory'] = str(game_dir)
    project_root = project_root or Path(__file__).resolve().parent.parent
    catalog = attach_catalog(before,game_dir,project_root)
    from .rcc_encounter_data import prepare_unit_context,commit_unit_assets
    from .rcc_world_data import prepare_world_data,commit_world_patches
    from .rcc_maps import attach_maps
    prepare_unit_context(before,game_dir,project_root)
    prepare_world_data(before,game_dir,project_root)
    if 'z' in flags:
        from .rcc_names import prepare_names
        prepare_names(before,game_dir,project_root)
    if set(flags)&set('ftz'):
        attach_maps(before,game_dir,project_root,seed)
    after = randomize(before, seed, flags, spread, skill_degree,chaos,
                      ability_mode=ability_mode,min_actions=min_actions,max_actions=max_actions,
                      passives_per_type=passives_per_type,fiesta=fiesta,easymodo=easymodo)
    from .rcc_events import apply_event_assets
    apply_event_assets(before,after,game_dir,project_root,flags)
    from .rcc_conditionals import apply_conditionals
    apply_conditionals(before,after,flags)
    from .rcc_qol import apply_qol
    from .rcc_qol_extra import apply_qol_extra
    qol = apply_qol(before,after,game_dir,flags)
    extra = apply_qol_extra(before,after,game_dir,flags)
    qol['pending'] = [name for name in qol['pending'] if name not in extra.get('completed_defaults',[])]
    if qol['pending']:
        raise ValueError('Default changes are incomplete: '+', '.join(qol['pending']))
    if 'b' in flags:
        from .randomize import starter_actions
        from .rcc_status import metadata_updates
        for aid in starter_actions(seed,before):
            after['_AbilityMetadata'][aid]['JPCost'] = 0
        metadata_updates(before,after)
    flags = "".join(f for f in FLAGS if f in flags)
    unit_assets = commit_unit_assets(before,after)
    commit_world_patches(before,after)
    changes = differences(before, after)
    if not changes and not unit_assets['changed_fields'] and not after.get('_RCCEventAssets') and not after.get('_RCCNativeTablePatches') and not after.get('_RCCMetadataUpdates') and not after.get('_RCCActionAudit',{}).get('action_updates') and 'b' not in flags:
        raise ValueError("These settings produce no changes; enable a job ability scope or increase stat spread")
    full_settings = dict(min_actions=min_actions,max_actions=max_actions,passives_per_type=passives_per_type,
                         pool_policy='refill after exhaustion') if ability_mode=='full' else None
    fingerprint = hashlib.sha256(json.dumps(dict(seed=seed, flags=flags, spread=spread, skill_degree=skill_degree,chaos=chaos,
                                                ability_mode=ability_mode,full_settings=full_settings,version=VERSION,
                                                secret_codes=dict(fiesta=fiesta,easymodo=easymodo),
                                                build=build["executable_sha256"]), sort_keys=True).encode()).hexdigest()[:12]
    mod_id = "fftivc.randomizer.seed"  # One active seed; prevents accidental stacking.
    folder_name = f"seed-{fingerprint}"
    destination = output_root / folder_name
    if destination.exists():
        raise FileExistsError(f"This seed already exists: {destination}. Choose a different output folder or seed.")
    output_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".fftic-build-", dir=output_root))
    try:
        mod = stage / mod_id
        tables_dir = mod / "FFTIVC" / "tables" / "enhanced"
        tables_dir.mkdir(parents=True)
        grouped = {}
        for c in changes:
            grouped.setdefault(c["table"], {}).setdefault(c["id"], {})[c["field"]] = c["after"]
        for table, rows in grouped.items():
            (tables_dir / f"{table}.xml").write_bytes(patch_bytes(table, rows, after))
        assets = after.get('_RCCEntryAssets',{}) | after.get('_RCCEventAssets',{})
        for name,data in assets.items():
            path = mod/'FFTIVC/data/enhanced'/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
        from .native import metadata_patches,write_runtime
        patches = after.get('_RCCNativeTablePatches',[])+metadata_patches(game_dir,before,after,build)
        runtime = write_runtime(game_dir,project_root,mod,patches)
        from .preview import build_rcc_nex
        nex = build_rcc_nex(game_dir,project_root,stage,mod,before,after,seed,free='b' in flags,ability_mode=ability_mode)
        preview = dict(actions=nex['testing_actions'],roundtrip=nex['roundtrip']) if 'b' in flags and nex else None
        config = dict(ModId=mod_id, ModName=f"FFTIC Randomizer - {seed}", ModAuthor="Local FFTIC Randomizer",
                      ModVersion=VERSION, ModDescription=f"{ABILITY_MODES[ability_mode]}; Enhanced seed {seed}; flags {flags}; randomness {spread:.0%}; skill degree {skill_degree:.0%}; chaos {chaos}.",
                      ModDll=runtime['bridge'] if runtime else "", ModNativeDll32="", ModNativeDll64="", ModIcon="", IsLibrary=False, IsUniversalMod=False,
                      ModDependencies=["fftivc.utility.modloader"], OptionalDependencies=[], SupportedAppId=["fft_enhanced.exe"])
        write_json(mod / "ModConfig.json", config)
        manifest = dict(generator_version=VERSION, seed=seed, flags=flags, spread=spread, skill_degree=skill_degree,
                        chaos=chaos,ability_mode=ability_mode,full_settings=full_settings,
                        secret_codes=dict(fiesta=fiesta,easymodo=easymodo),
                        rule_engine=ABILITY_MODES[ability_mode],rcc_source_commit='ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070',
                        mode="enhanced", build=build, property_changes=len(changes),
                        changes_by_table=dict(Counter(c["table"] for c in changes)),
                        validation="offline-only; gameplay untested",starting_actions=preview,
                        nex_changes=nex,encounters_randomized=bool(set(flags)&set('uzf')),
                        native_runtime=runtime,unit_assets=unit_assets,
                        rcc_phase_audits={name:after[name] for name in after if name.startswith('_RCC') and name.endswith('Audit')},
                        rcc_world_inputs=before['_RCCWorldInputs'],rcc_unit_inputs=before['_RCCUnitInputs'],
                        rcc_ability_audit=after['_RCCAbilityAudit'],rcc_equipment_audit=after['_RCCEquipmentAudit'],
                        ability_allocation_audit=after['_RCCAbilityAudit'],
                        rcc_stats_audit=after['_RCCStatAudit'],rcc_context_inputs=before['_RCCContextInputs'],
                        active_job_count=len(active_jobs(before)),
                        catalog_entries=len(catalog),eligible_abilities_by_type={k:len(v) for k,v in pools(before).items()},
                        catalog_inputs=before['_CatalogInputs'],
                        ability_scope_commands={k:sorted(v) for k,v in zip(('ordinary','unique','creature_human_format'),scopes(before))},
                        ability_scope_flags={'s':['ordinary','unique'],'m':['creature_human_format','monster_commands']})
        write_json(stage / "changes.json", changes)
        write_json(stage / 'encounter-changes.json',after.get('_RCCEntryChanges',[]))
        names = load_names(project_root,game_dir)
        names['Ability'] = {str(a):r['name'] for a,r in catalog.items()}
        write_json(stage/'ability-catalog.json',list(catalog.values()))
        write_catalog(stage/'ability-catalog.csv',catalog)
        assignments = []
        for table,commands in (('JobCommandData',set.union(*scopes(before))),('MonsterJobCommandData',set(before['MonsterJobCommandData']))):
            for c in sorted(commands):
                row = after[table][c]
                assigned = [a for a in row.values() if a]
                original_name = label(table,c,names)
                command_name = (nex or {}).get('command_labels',{}).get('JobCommand-en',{}).get(c,{}).get('Name',original_name)
                assignments.append(dict(command_id=c,command_name=command_name,original_command_name=original_name,
                                        job_ids=[j for j,r in before['JobData'].items() if r['JobCommandId']==c],
                                        menu=after['CommandTypeData'][c]['Menu'],
                                        categories={kind:[catalog[a]['name']+f' [{a}]' for a in assigned if catalog[a]['category']==kind]
                                                    for kind in ('action','item','throw','jump','aim','math','reaction','support','movement')},
                                        ability_ids=assigned))
        used = {a for assignment in assignments for a in assignment['ability_ids']}
        eligible = {a for a,r in catalog.items() if r['eligible']}
        manifest['allocation_coverage'] = dict(assigned_unique_abilities=len(used&eligible),eligible_abilities=len(eligible),
                                                unassigned_eligible_ids=sorted(eligible-used))
        write_json(stage/'job-abilities.json',assignments)
        rule_lines = (['Shuffle exchanges subsets; protected native command menus remain; mixed passives can be empty.']
                      if ability_mode=='rcc' else
                      [f'Full replacement: {min_actions}-{max_actions} actions (limited by profile pool); {passives_per_type} of each R/S/M per humanoid.',
                       'Player and creature pools are separate; shared native IDs can belong to both.',
                       'Each typed pool refills only after exhaustion; duplicates within a job are excluded.',
                       'Native menu profiles, including Aim and Jump, are redistributed between humanoid jobs.'])
        ability_lines = ['Seeded job skillsets','',f'Seed: {seed}',f'Ability mode: {ABILITY_MODES[ability_mode]}',
                         *rule_lines,'Native list limits: 16 actions / 6 passives; four-slot monster lists.','']
        for assignment in assignments:
            ability_lines += [f"{assignment['command_name']} [command {assignment['command_id']}; jobs {assignment['job_ids']}; menu {assignment['menu']}]"]
            ability_lines += [f"  {kind}: {', '.join(values)}" for kind,values in assignment['categories'].items() if values]
            ability_lines.append('')
        (stage/'job-abilities.txt').write_text('\n'.join(ability_lines)+'\n',encoding='utf-8')
        spoiler = report_text(changes,manifest,names)
        if nex:
            spoiler += '\nAbility costs and action overrides\n'
            for aid,cost in sorted(nex['jp_cost_updates'].items()): spoiler += f"  {catalog[aid]['name']} [{aid}] JP: {catalog[aid]['jp_cost']} -> {cost}\n"
            for aid,fields in sorted(nex['action_updates'].items()): spoiler += f"  {catalog[aid]['name']} [{aid}]: {fields}\n"
        (stage / "spoiler.txt").write_text(spoiler,encoding='utf-8')
        if preview:
            opening = ['Global starting actions','',f'Seed: {seed}',
                       'Every randomized human skillset uses the same global selection rule.',
                       'These additional shared actions are free wherever the allocator places them:', '']
            opening += [f"  {aid}: {names.get('Ability',{}).get(str(aid),'Ability')}" for aid in preview['actions']]
            opening += ['', 'Shared action IDs mean these cost overrides also apply to other users of these six actions.',
                        'These six shared actions have 0 JP, 0 MP and instant casting wherever used.',
                        'Other abilities keep their learning costs. Disable flag b for ordinary progression.',
                        'Command menus follow the selected ability allocation mode.',
                        'The same global action rule applies inside and outside the opening.',
                        'Knights share their skillset in every battle. Ordinary jobs, Agrias and other unique humanoid jobs all use flag s.']
            (stage/'STARTING-ACTIONS.txt').write_text('\n'.join(opening)+'\n',encoding='utf-8')
        install_text = (
            "FFTIC Randomizer - experimental Enhanced seed\n\n"
            "1. Install Reloaded-II and register FFT_enhanced.exe.\n"
            "2. Install Nenkai's FINAL FANTASY TACTICS - The Ivalice Chronicles Mod Loader, version 1.7.5 or newer.\n"
            "3. Copy this fftivc.randomizer.seed folder into Reloaded-II's Mods directory.\n"
            "4. Enable the mod loader and FFTIC Randomizer for the Enhanced application.\n"
            "5. Launch through Reloaded-II and test on a new separate save.\n\n"
            "To change seed: close the game, replace the entire fftivc.randomizer.seed folder, then relaunch.\n"
            "Use one seed at a time. Existing character stats do not necessarily recalculate in old saves.\n"
            "Job/equipment changes also affect enemies. Story encounters have not been playtested.\n"
            "Disable the randomizer in Reloaded-II and restart to remove its table, event and runtime changes. No original files were overwritten.\n"
            "The bundled managed bridge applies native edits after loader startup scans and table application.\n"
            "The native runtime checks the exact Enhanced executable and every original patch byte before applying any change.\n"
            "Inspect runtime-patches.log in this mod folder as well as the Reloaded-II log.\n\n"
            "Loader: https://github.com/Nenkai/fftivc.utility.modloader/releases\n"
            "Setup: https://nenkai.github.io/ffxvi-modding/modding/installing_mods_fft/\n"
        )
        (mod / "INSTALL.txt").write_text(install_text, encoding="utf-8")
        (mod / "CREDITS.txt").write_text(
            "FFTIC Randomizer credits\n\n"
            "Rumble Chaos Crashdown v27 by abyssonym: original randomization rules and community names.\n"
            "https://github.com/abyssonym/rumble_chaos_crashdown\n\n"
            "FF16Tools by Nenkai: game archive extraction and Nex table conversion during generation.\n"
            "https://github.com/Nenkai/FF16Tools\n\n"
            "FFTIC Mod Loader and Nex layouts by Nenkai: mod loading and data formats.\n"
            "https://github.com/Nenkai/fftivc.utility.modloader\n\n"
            "Gibbed's Ivalice Chronicles tools: script opcode metadata.\n"
            "https://github.com/gibbed/Gibbed.IvaliceChronicles\n",encoding="utf-8")
        manifest["payload_sha256"] = {p.relative_to(mod).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in sorted(mod.rglob("*")) if p.is_file()}
        write_json(stage / "manifest.json", manifest)
        with zipfile.ZipFile(stage / "randomizer-mod.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(mod.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(path.relative_to(stage).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    archive.writestr(info, path.read_bytes())
        # A same-volume directory rename exposes only a completed package.
        stage.rename(destination)
    except Exception:
        # Only our newly created staging directory is removed.
        if stage.parent == output_root and stage.name.startswith(".fftic-build-") and not stage.is_symlink():
            shutil.rmtree(stage)
        raise
    return destination, manifest
