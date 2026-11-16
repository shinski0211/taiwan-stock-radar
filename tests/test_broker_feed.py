import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from broker_feed import BrokerSourceError, collect, parse_stocks, recent_weekdays, rejection_message, rows_from_payload

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'


class BrokerFeedTest(unittest.TestCase):
    def test_weekdays_skip_weekend(self):
        days = recent_weekdays(3, today=date(2024, 11, 18))
        self.assertEqual(days, ['2024-11-13', '2024-11-14', '2024-11-15'])

    def test_stock_limit(self):
        with self.assertRaises(BrokerSourceError):
            parse_stocks('2330,2317,2454,2308,2412,3008')

    def test_schema_fixture_aggregates_price_levels(self):
        payload = json.loads((FIXTURES / 'finmind_broker_report.json').read_text(encoding='utf-8'))
        frame = rows_from_payload(payload['data'])
        self.assertEqual(list(frame.columns), ['date', 'stock', 'broker_id', 'broker', 'buy_qty', 'sell_qty', 'buy_price', 'sell_price', 'available_date'])
        first = frame[frame.broker == '凱基-城中'].iloc[0]
        self.assertEqual(first.buy_qty, 3000)
        self.assertEqual(first.sell_qty, 500)
        self.assertAlmostEqual(first.buy_price, (100 * 2000 + 101 * 1000) / 3000)
        self.assertEqual(first.sell_price, 101)
        self.assertEqual(first.available_date, '2024-11-14')

    def test_recorded_denial(self):
        body = json.loads((FIXTURES / 'finmind_broker_denied.json').read_text(encoding='utf-8'))
        self.assertIn('Sponsor', rejection_message(body))

    def test_cache_skips_second_request(self):
        payload = json.loads((FIXTURES / 'finmind_broker_report.json').read_text(encoding='utf-8'))
        calls = []

        def transport(stock, day, token):
            calls.append((stock, day, token))
            return 200, payload

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'reports.sqlite'
            first = collect(['2330'], ['2024-11-14'], 'token', path, transport, pause=0)
            second = collect(['2330'], ['2024-11-14'], 'token', path, transport, pause=0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)

    def test_missing_token_does_not_call_network(self):
        def transport(stock, day, token):
            raise AssertionError('should not request')

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(BrokerSourceError) as caught:
                collect(['2330'], ['2024-11-14'], '', Path(folder) / 'reports.sqlite', transport, pause=0)
        self.assertIn('FINMIND_TOKEN', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
