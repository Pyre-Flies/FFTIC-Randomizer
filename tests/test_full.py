"""Full redistribution alongside the source-compatible RCC mode."""
import copy
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest

from fftic.catalog import attach_catalog, MENUS, pools
from fftic.game import ACTION_FIELDS, RSM_FIELDS, read_game
from fftic.package import create_seed
from fftic.randomize import randomize
from fftic.rcc_equipment import apply_equipment

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT.parent
RCC_REFERENCE = ROOT / 'outputs/seed-68dd1b985af3'


def public_tables(tables):
    return {name: rows for name, rows in tables.items() if not name.startswith('_')}


def nonzero(row, fields):
    return [row[field] for field in fields if row.get(field)]


class CycleDeckTests(unittest.TestCase):
    def test_pool_is_consumed_before_refill(self):
        from fftic.full import CycleDeck
        for seed in range(10):
            deck = CycleDeck([11, 22, 33, 44], random.Random(seed))
            draws = [deck.draw() for _ in range(12)]
            for start in range(0, 12, 4):
                self.assertEqual(set(draws[start:start + 4]), {11, 22, 33, 44})
            audit = deck.audit()
            self.assertEqual(audit['pool_size'], 4)
            self.assertEqual(audit['draws'], 12)
            self.assertEqual(audit['unique_used'], 4)
            self.assertGreaterEqual(audit['refills'], 2)

    def test_row_exclusions_survive_pool_refills(self):
        from fftic.full import CycleDeck
        for seed in range(10):
            deck = CycleDeck([1, 2, 3, 4], random.Random(seed))
            for row in range(20):
                chosen = []
                for slot in range(3):
                    aid = deck.draw(excluded=chosen)
                    self.assertNotIn(aid, chosen)
                    chosen.append(aid)
                self.assertEqual(len(set(chosen)), 3)
                self.assertLessEqual(set(chosen), {1, 2, 3, 4})


@unittest.skipUnless((GAME / 'FFT_enhanced.exe').exists(), 'Requires a local legally owned game installation')
class InstalledFullModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables, _ = read_game(GAME)
        attach_catalog(cls.tables, GAME, ROOT)

    def owners(self):
        from fftic.full import owner_scopes
        return owner_scopes(self.tables)

    def assert_owner_compatible(self, result, owner, domain, min_actions=6, max_actions=12,
                                passives_per_type=1):
        table, command = owner
        row = result[table][command]
        catalog = self.tables['_AbilityCatalog']
        fields = ACTION_FIELDS[:4] if table == 'MonsterJobCommandData' else ACTION_FIELDS
        actions = nonzero(row, fields)
        maximum = 4 if table == 'MonsterJobCommandData' else max_actions
        self.assertGreaterEqual(len(actions), 1)
        self.assertLessEqual(len(actions), maximum)
        self.assertTrue(row['AbilityId1'])
        ids = [aid for aid in row.values() if aid]
        self.assertEqual(len(ids), len(set(ids)), (owner, ids))
        for aid in ids:
            self.assertTrue(catalog[aid]['eligible'], (owner, aid))
            self.assertIn(catalog[aid]['domain'], (domain, 'both'), (owner, aid, catalog[aid]['domain']))
        if table == 'MonsterJobCommandData':
            # The normal and Monster Skill slots remain distinct native roles.
            self.assertTrue(row['AbilityId4'])
            self.assertTrue(all(catalog[aid]['native_type'] == 1 for aid in actions))
            return
        menu = result['CommandTypeData'][command]['Menu']
        if menu in (4, 7):
            legal = {aid for source, source_row in self.tables['JobCommandData'].items()
                     if self.tables['CommandTypeData'][source]['Menu'] == menu
                     for aid in nonzero(source_row, ACTION_FIELDS) if catalog[aid]['eligible']}
            self.assertLessEqual(set(actions), legal)
        else:
            kind = next(kind for kind, native_menu in MENUS.items() if native_menu == menu)
            legal = set(pools(self.tables, domain)[kind])
            self.assertTrue(all(catalog[aid]['native_type'] == kind for aid in actions))
        self.assertGreaterEqual(len(actions), min(min_actions, len(legal)))
        passives = nonzero(row, RSM_FIELDS)
        self.assertTrue(all(catalog[aid]['native_type'] in (7, 8, 9) for aid in passives))
        counts = Counter(catalog[aid]['native_type'] for aid in passives)
        for kind in (7, 8, 9):
            if domain == 'player':
                self.assertEqual(counts[kind], passives_per_type)
            else:
                self.assertLessEqual(counts[kind], passives_per_type)

    def test_full_is_seeded_and_does_not_mutate_input(self):
        original = copy.deepcopy(self.tables)
        first = randomize(self.tables, 'full-deterministic', 'sm', ability_mode='full')
        repeated = randomize(self.tables, 'full-deterministic', 'ms', ability_mode='full')
        changed = randomize(self.tables, 'other-full-seed', 'sm', ability_mode='full')
        self.assertEqual(public_tables(first), public_tables(repeated))
        self.assertNotEqual(public_tables(first), public_tables(changed))
        self.assertEqual(self.tables, original)

    def test_full_covers_ordinary_unique_creature_and_mime_owners(self):
        from fftic.full import apply_full
        owners = self.owners()
        for seed in range(10):
            result = copy.deepcopy(self.tables)
            apply_full(self.tables, result, str(seed), 'sm')
            for flag, selected in owners.items():
                for owner in selected:
                    self.assert_owner_compatible(result, owner, 'monster' if flag == 'm' else 'player')
            self.assertEqual(result['JobData'], self.tables['JobData'])
        for job in (2, 23, 52, 76, 77, 87, 93, 160, 162, 163):
            command = self.tables['JobData'][job]['JobCommandId']
            self.assertTrue(nonzero(result['JobCommandData'][command], ACTION_FIELDS))
            self.assertEqual(len(nonzero(result['JobCommandData'][command], RSM_FIELDS)), 3)
        # Archer, Dragoon, Mime and unique jobs are available for complete
        # redistribution instead of inheriting RCC's native-menu exclusions.
        self.assertTrue(any(result['CommandTypeData'][owner[1]] != self.tables['CommandTypeData'][owner[1]]
                            for owner in owners['s'] if owner[0] == 'JobCommandData'))

    def test_disabled_scopes_and_degree_zero_preserve_native_rows(self):
        owners = self.owners()
        self.assertEqual(set(owners), {'s', 'm'})
        human_commands = {command for table, command in owners['s'] if table == 'JobCommandData'}
        self.assertLessEqual({5, 8, 18, 24, 25, 26, 27, 28, 32, 33, 224, 225, 226}, human_commands)
        for flag in ('s', 'm'):
            result = randomize(self.tables, 'full-scopes', flag, ability_mode='full')
            enabled = set(owners[flag])
            for table in ('JobCommandData', 'MonsterJobCommandData'):
                for command, row in self.tables[table].items():
                    if (table, command) not in enabled:
                        self.assertEqual(result[table][command], row)
                        if table == 'JobCommandData':
                            self.assertEqual(result['CommandTypeData'][command], self.tables['CommandTypeData'][command])
        # Use the engine directly: m's separate stat flag is outside this
        # ability-degree control and remains governed by RCC orchestration.
        from fftic.full import apply_full
        zero = copy.deepcopy(self.tables)
        apply_full(self.tables, zero, 'full-zero', 'sm', degree=0)
        self.assertEqual(zero, self.tables)

    def test_partial_full_replaces_whole_owners_with_compatible_profiles(self):
        from fftic.full import apply_full
        owners = self.owners()
        result = copy.deepcopy(self.tables)
        audit = apply_full(self.tables, result, 'partial-full', 'sm', degree=.25)
        changed, unchanged = 0, 0
        for flag, selected in owners.items():
            for owner in selected:
                table, command = owner
                row_changed = result[table][command] != self.tables[table][command]
                menu_changed = table == 'JobCommandData' and result['CommandTypeData'][command] != self.tables['CommandTypeData'][command]
                if row_changed or menu_changed:
                    changed += 1
                    self.assert_owner_compatible(result, owner, 'monster' if flag == 'm' else 'player')
                else:
                    unchanged += 1
        self.assertGreater(changed, 0)
        self.assertGreater(unchanged, changed)
        self.assertIn('full', json.dumps(audit).casefold())

    def test_requested_action_and_passive_counts_are_respected(self):
        result = randomize(self.tables, 'full-sizes', 'sm', ability_mode='full',
                           min_actions=8, max_actions=8, passives_per_type=2)
        for flag, selected in self.owners().items():
            for owner in selected:
                self.assert_owner_compatible(result, owner, 'monster' if flag == 'm' else 'player',
                                             min_actions=8, max_actions=8, passives_per_type=2)

    def test_modes_preserve_shared_job_equipment_and_action_stat_rules(self):
        rcc = randomize(self.tables, 'independent-mode-features', 'jsmapw', ability_mode='rcc')
        full = randomize(self.tables, 'independent-mode-features', 'jsmapw', ability_mode='full')
        from fftic.rcc_innates import innate_scopes
        for job in innate_scopes(self.tables)['i']:
            self.assertEqual(rcc['JobData'][job],full['JobData'][job],job)
        for table in ('ItemData', 'ItemWeaponData', 'ItemShieldData', 'ItemArmorData',
                      'ItemAccessoryData', 'ItemConsumableData', 'ItemEquipBonusData'):
            self.assertEqual(rcc[table], full[table], table)
        def scalar_updates(result):
            updates = result.get('_RCCActionAudit', {}).get('action_updates', {})
            scalars = {aid: {field: value for field, value in row.items()
                             if field not in ('Flags12', 'Flags34')}
                       for aid, row in updates.items()}
            return {aid: row for aid, row in scalars.items() if row}
        self.assertEqual(scalar_updates(rcc), scalar_updates(full))
        # j's human stats and equipment stay independent. Its skill JP results
        # depend on assigned lists; m subsequently sorts innate candidates by
        # those costs, so monster innate/stat rows can legitimately differ.
        self.assertNotEqual(rcc['JobCommandData'], full['JobCommandData'])

    @unittest.skipUnless((RCC_REFERENCE / 'manifest.json').exists(), 'Requires the prior locally generated RCC reference seed')
    def test_equipment_changes_preserve_previous_rcc_reference_seed(self):
        # The old whole-payload golden predates corrected ability/monster
        # phases and new native defaults. Its independent p/w reference is
        # still useful: compare every field in each equipment table directly.
        golden = json.loads((RCC_REFERENCE / 'manifest.json').read_text())
        tables=('ItemData','ItemWeaponData','ItemShieldData','ItemArmorData',
                'ItemAccessoryData','ItemConsumableData','ItemEquipBonusData')
        actual=copy.deepcopy(self.tables)
        apply_equipment(self.tables,actual,golden['seed'],'pw',
                        chaos=golden['chaos'],random_degree=golden['spread'])
        expected=copy.deepcopy(self.tables)
        changes=json.loads((RCC_REFERENCE/'changes.json').read_text())
        equipment=[change for change in changes if change['table'] in tables]
        self.assertTrue(equipment)
        for change in equipment:
            self.assertEqual(self.tables[change['table']][change['id']][change['field']],change['before'])
            expected[change['table']][change['id']][change['field']]=change['after']
        for table in tables:
            self.assertEqual(actual[table],expected[table],table)

    def test_package_records_mode_and_full_settings_in_identity(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'research') as scratch:
            base = Path(scratch)
            rcc, rcc_manifest = create_seed(GAME, base, 'mode-identity', flags='sm', ability_mode='rcc')
            full, full_manifest = create_seed(GAME, base, 'mode-identity', flags='sm', ability_mode='full')
            sized, sized_manifest = create_seed(GAME, base, 'mode-identity', flags='sm', ability_mode='full',
                                                min_actions=8, max_actions=8, passives_per_type=2)
            self.assertEqual(len({rcc.name, full.name, sized.name}), 3)
            self.assertEqual(rcc_manifest['ability_mode'], 'rcc')
            self.assertEqual(full_manifest['ability_mode'], 'full')
            self.assertEqual(full_manifest['full_settings']['pool_policy'], 'refill after exhaustion')
            self.assertEqual(sized_manifest['full_settings']['min_actions'], 8)
            self.assertEqual(sized_manifest['full_settings']['max_actions'], 8)
            self.assertEqual(sized_manifest['full_settings']['passives_per_type'], 2)
            # Full-only controls are canonicalized out of RCC's identity.
            with self.assertRaises(FileExistsError):
                create_seed(GAME, base, 'mode-identity', flags='sm', ability_mode='rcc',
                            min_actions=8, max_actions=8, passives_per_type=2)

    def test_full_command_labels_follow_profiles_without_changing_native_fields(self):
        from fftic.preview import prepare_inputs
        _, baseline, _ = prepare_inputs(GAME, ROOT, include_commands=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'research') as scratch:
            for degree, flags in ((1, 'jsmapw'), (.25, 's')):
                output, manifest = create_seed(GAME, Path(scratch), '89f597b5', flags=flags,
                                               skill_degree=degree, ability_mode='full')
                nex = manifest['nex_changes']
                self.assertEqual(nex['roundtrip'], 'exact rows and cells matched')
                selected = {owner['id'] for owner in manifest['ability_allocation_audit']['selected_owners']
                            if owner['table'] == 'JobCommandData'}
                self.assertEqual(len(nex['command_labels']), 7)
                self.assertEqual(set(nex['command_labels']),
                                 {'JobCommand-'+locale for locale in ('en','de','fr','ja','ko','cs','ct')})
                self.assertLessEqual(set(nex['command_labels']),set(nex['tables']))
                with closing(sqlite3.connect(baseline)) as old, closing(sqlite3.connect(output / 'nex-work/rebuilt.sqlite')) as new:
                    for table, labels in nex['command_labels'].items():
                        self.assertEqual({int(command) for command in labels}, selected)
                        columns = [row[1] for row in old.execute(f'PRAGMA table_info("{table}")')]
                        before = old.execute(f'SELECT * FROM "{table}" ORDER BY "Key"').fetchall()
                        after = new.execute(f'SELECT * FROM "{table}" ORDER BY "Key"').fetchall()
                        self.assertEqual(len(before), len(after))
                        for old_row, new_row in zip(before, after):
                            command = new_row[columns.index('Key')]
                            for column, previous, current in zip(columns, old_row, new_row):
                                if previous != current:
                                    self.assertIn(command, selected)
                                    self.assertIn(column, ('Name', 'Description', 'Description2'))
                    english = {row[0]: row[1] for row in new.execute('SELECT "Key",Name FROM "JobCommand-en"')}
                    if degree == 1:
                        for command in (8, 18, 24):
                            original = old.execute('SELECT Name FROM "JobCommand-en" WHERE "Key"=?',
                                                   (command,)).fetchone()[0]
                            self.assertNotEqual(english[command], original)
                assignments = json.loads((output / 'job-abilities.json').read_text())
                for row in assignments:
                    if row['command_id'] in selected:
                        self.assertEqual(row['command_name'], english[row['command_id']])
                        self.assertIn('original_command_name', row)

    def test_invalid_full_settings_are_rejected(self):
        for settings in (dict(ability_mode='unknown'), dict(min_actions=0), dict(max_actions=17),
                         dict(min_actions=9, max_actions=8), dict(passives_per_type=3)):
            with self.assertRaises(ValueError):
                randomize(self.tables, 'invalid-full', 'sm', **(dict(ability_mode='full') | settings))


if __name__ == '__main__':
    unittest.main()
