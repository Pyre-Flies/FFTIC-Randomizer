"""Enhanced-only poach UI reconciliation against original localized inputs."""
import copy
from pathlib import Path
import unittest

from fftic.game import read_game
from fftic.rcc_world_data import prepare_world_data
from fftic.rcc_rewards import finish_poach_ui

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT.parent/'FFT_enhanced.exe').is_file(),'Requires original Enhanced files')
class PoachUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before,_ = read_game(ROOT.parent)
        prepare_world_data(cls.before,ROOT.parent,ROOT)

    def test_rewards_and_final_prices_reconcile_all_locales_without_touching_other_columns(self):
        before = self.before
        result = copy.deepcopy(before)
        reward = 100
        result['_RCCPoaches'][0]['common'] = reward
        result['ItemData'][reward]['Price'] = 2002
        audit = finish_poach_ui(before,result,'tpw')
        key = result['_RCCPoaches'][0]['common_key']
        self.assertGreater(audit['price_rows'],0)
        self.assertGreaterEqual(audit['description_rows'],7)
        for table in before['_RCCPoachNexTables']:
            fields = result['_RCCWorldNexUpdates'][table][(key,)]
            self.assertEqual((fields['Cost'],fields['SellPrice']),(1001,501))
            self.assertNotEqual(fields['Unknown18'],before['_RCCPoachNexTables'][table][key]['Unknown18'])
            self.assertLessEqual(set(fields),{'Cost','SellPrice','Unknown18'})
        self.assertEqual(result['_RCCPoachNexTables'],before['_RCCPoachNexTables'])

    def test_original_price_guard_and_disabled_phase(self):
        changed = copy.deepcopy(self.before)
        key = changed['_RCCPoaches'][0]['common_key']
        changed['_RCCPoachNexTables']['PoachItem-en'][key]['Cost'] += 1
        with self.assertRaisesRegex(ValueError,'formula guard'):
            finish_poach_ui(changed,copy.deepcopy(changed),'p')
        result = copy.deepcopy(self.before)
        self.assertFalse(finish_poach_ui(self.before,result,'w')['enabled'])
        self.assertNotIn('_RCCWorldNexUpdates',result)


if __name__=='__main__':
    unittest.main()
