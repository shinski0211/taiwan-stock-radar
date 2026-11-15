import unittest
from pathlib import Path

from robot_supply import DEFAULT_PATH, FIELDS, TIES, UNDISCLOSED, companies_frame, load_companies

ROOT = Path(__file__).resolve().parents[1]


class RobotSupplyConfigTest(unittest.TestCase):
    def test_default_file_loads(self):
        rows = load_companies(DEFAULT_PATH)
        self.assertGreaterEqual(len(rows), 30)
        codes = {row['code'] for row in rows}
        for code in ('2464', '2049', '2395', '2330', '6215', '2317', '3665'):
            self.assertIn(code, codes)
        self.assertEqual(sum(row['code'] == '2308' for row in rows), 2)

    def test_required_fields_and_ties(self):
        for row in load_companies():
            for field in FIELDS:
                self.assertIn(field, row)
            self.assertIn(row['optimus_tie'], TIES)
            self.assertRegex(row['code'], r'^\d{4}$')

    def test_cited_shares_have_sources(self):
        cited = {
            row['code']: row
            for row in load_companies()
            if row['robot_revenue_share'] != UNDISCLOSED
        }
        self.assertEqual(set(cited), {'2049', '2395', '6215'})
        for row in cited.values():
            self.assertTrue(row['share_source_url'].startswith('http'))
            self.assertRegex(row['share_as_of'], r'^\d{4}-\d{2}-\d{2}$')
        self.assertIn('12%', cited['2049']['robot_revenue_share'])
        self.assertIn('11.1%', cited['6215']['robot_revenue_share'])

    def test_quotes_attach_without_inventing_prices(self):
        rows = load_companies()[:1]
        frame = companies_frame(rows, {'2464': (80.5, 1.25)})
        self.assertEqual(frame.loc[0, '收盤'], 80.5)
        self.assertEqual(frame.loc[0, '漲跌幅'], 1.25)
        missing = companies_frame(rows, {})
        self.assertIsNone(missing.loc[0, '收盤'])

    def test_bad_tie_is_rejected(self):
        sample = ROOT / 'config' / 'robot_supply_chain.toml'
        text = sample.read_text(encoding='utf-8').replace('optimus_tie = "無"', 'optimus_tie = "確定"', 1)
        path = ROOT / 'config' / '_bad_robot_supply.toml'
        path.write_text(text, encoding='utf-8')
        try:
            with self.assertRaises(ValueError):
                load_companies(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
